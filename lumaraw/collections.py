"""Portable hierarchical collections and durable Quick/target collection state.

Inputs: validated commands, expected revisions and catalog-owned SQLite access.
Outputs: bounded collection pages, predicates and atomic membership changes.
Sets contain collections, never photos directly. Originals and photo recipes are
untouched. Ancestor revisions cover descendant edits so stale subtree deletion
cannot erase changes the caller has not seen. No pixels or platform UI.
Collection identities are never reused after deletion, including after restart.
Membership validation reads only bounded IDs, never full photo/keyword details.
"""
import json
import re
import time

from .organization import criteria

UNSET = object()
TREE = ('WITH RECURSIVE tree(id) AS (SELECT id FROM collections WHERE id=? '
        'UNION ALL SELECT c.id FROM collections c JOIN tree t ON c.parent_id=t.id) ')


def migrate(db):
    if db.execute('PRAGMA user_version').fetchone()[0] >= 2:
        return
    with db:
        columns={row[1] for row in db.execute('PRAGMA table_info(collections)')}
        if 'parent_id' not in columns:
            db.execute('ALTER TABLE collections ADD COLUMN parent_id INTEGER')
        db.execute('CREATE INDEX IF NOT EXISTS collection_parent ON collections(parent_id,name COLLATE NOCASE,id)')
        db.execute('CREATE TABLE IF NOT EXISTS collection_state (id INTEGER PRIMARY KEY CHECK(id=1), '
                   'quick_id INTEGER NOT NULL, target_id INTEGER NOT NULL, revision INTEGER NOT NULL DEFAULT 0)')
        if not db.execute('SELECT 1 FROM collection_state WHERE id=1').fetchone():
            quick=db.execute("INSERT INTO collections(name,kind,created) VALUES('Quick Collection','quick',?)",
                             (time.time(),)).lastrowid
            db.execute('INSERT INTO collection_state(id,quick_id,target_id) VALUES(1,?,?)',(quick,quick))
        db.execute('PRAGMA user_version=2')


def migrate_identities(db):
    """v5: retain every live collection/reference while preventing future ID reuse."""
    if db.execute('PRAGMA user_version').fetchone()[0] >= 5:
        return
    with db:
        db.execute('BEGIN IMMEDIATE')
        schema=db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='collections'").fetchone()[0]
        if not re.search(r'\bid\s+INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT\b',schema,re.I):
            schema,replaced=re.subn(r'\bid\s+INTEGER\s+PRIMARY\s+KEY\b',
                'id INTEGER PRIMARY KEY AUTOINCREMENT',schema,flags=re.I)
            if replaced != 1:
                raise ValueError('Unsupported collections schema; identity migration was not applied')
            schema,replaced=re.subn(r'CREATE TABLE\s+(?:IF NOT EXISTS\s+)?["`\[]?collections["`\]]?',
                                   'CREATE TABLE collections_v5',schema,count=1,flags=re.I)
            if replaced != 1:
                raise ValueError('Unsupported collections table declaration')
            objects=[row[0] for row in db.execute("SELECT sql FROM sqlite_master WHERE tbl_name='collections' "
                "AND type IN ('index','trigger') AND sql IS NOT NULL")]
            db.execute(schema)
            db.execute('INSERT INTO collections_v5 SELECT * FROM collections')
            db.execute('DROP TABLE collections')
            db.execute('ALTER TABLE collections_v5 RENAME TO collections')
            for statement in objects:
                db.execute(statement)
        db.execute('PRAGMA user_version=5')


class Collections:
    def __init__(self,catalog):
        self.catalog=catalog
        self.db=catalog.db

    def get(self,id_):
        row=self.db.execute('SELECT * FROM collections WHERE id=?',(id_,)).fetchone()
        if row is None: raise ValueError('Collection does not exist')
        result=dict(row);result['rules']=json.loads(result['rules'])
        return result

    def checked(self,id_,revision):
        row=self.get(id_)
        if row['revision'] != revision: raise ValueError('Collection conflict; reload the collection before editing')
        return row

    def ancestors(self,id_):
        result=[];seen=set()
        while id_ is not None:
            if id_ in seen or len(result)>=64: raise ValueError('Collection hierarchy is cyclic or too deep')
            seen.add(id_);row=self.get(id_);result.append(row);id_=row['parent_id']
        return result

    def touch_ancestors(self,parent):
        for row in self.ancestors(parent):
            self.db.execute('UPDATE collections SET revision=revision+1 WHERE id=?',(row['id'],))

    def validate_parent(self,parent,id_=None):
        if parent is None: return
        ancestors=self.ancestors(parent)
        if ancestors[0]['kind'] != 'set': raise ValueError('Only a collection set can contain collections')
        if any(row['id']==id_ for row in ancestors): raise ValueError('A collection set cannot contain itself or its ancestor')
        if len(ancestors)>=32: raise ValueError('Collection nesting exceeds 32 levels')

    def list(self,offset=0,parent_id=UNSET):
        where="kind!='quick'";params=[]
        if parent_id is not UNSET:
            if parent_id is not None and self.get(parent_id)['kind'] != 'set':
                raise ValueError('Only a collection set has child collections')
            where+=' AND parent_id IS ?';params.append(parent_id)
        total=self.db.execute('SELECT count(*) FROM collections WHERE '+where,params).fetchone()[0]
        offset=min(offset,max(0,((total-1)//60)*60))
        rows=self.db.execute('SELECT id FROM collections WHERE '+where+
                             ' ORDER BY name COLLATE NOCASE,id LIMIT 60 OFFSET ?',[*params,offset]).fetchall()
        return {'collections':[self.get(row[0]) for row in rows],'offset':offset,'total':total,'page_size':60}

    def save(self,name,kind='regular',rules=None,match='all',collection_id=None,
             expected_revision=None,parent_id=UNSET,photo_ids=None):
        name=name.strip();rules=rules or {}
        if not name: raise ValueError('Collection name cannot be blank')
        if kind not in ('regular','smart','set'): raise ValueError('Unsupported collection type')
        criteria(rules,match)
        if kind != 'smart' and rules: raise ValueError('Only smart collections can have rules')
        old=None
        if collection_id is not None:
            old=self.checked(collection_id,expected_revision)
            if old['kind'] != kind: raise ValueError('Collection type cannot be changed')
        if photo_ids and (old or kind != 'regular'):
            raise ValueError('Initial photos are only supported for new regular collections')
        if any(not self.catalog.photo(id_) for id_ in photo_ids or []):
            raise ValueError('Photo does not exist')
        parent=(old['parent_id'] if old else None) if parent_id is UNSET else parent_id
        self.validate_parent(parent,collection_id)
        if old and kind=='set':
            height=self.db.execute('WITH RECURSIVE depth(id,n) AS (SELECT ?,1 UNION ALL '
                'SELECT c.id,d.n+1 FROM collections c JOIN depth d ON c.parent_id=d.id WHERE d.n<=32) '
                'SELECT max(n) FROM depth',(collection_id,)).fetchone()[0]
            if len(self.ancestors(parent))+height>32: raise ValueError('Collection nesting exceeds 32 levels')
        with self.db:
            if old:
                self.db.execute('UPDATE collections SET name=?,rules=?,match=?,parent_id=?,revision=revision+1 WHERE id=?',
                                (name,json.dumps(rules),match,parent,collection_id))
                self.touch_ancestors(old['parent_id'])
                if parent != old['parent_id']: self.touch_ancestors(parent)
            else:
                collection_id=self.db.execute('INSERT INTO collections(name,kind,rules,match,parent_id,created) '
                    'VALUES(?,?,?,?,?,?)',(name,kind,json.dumps(rules),match,parent,time.time())).lastrowid
                self.touch_ancestors(parent)
                if photo_ids:
                    self.db.executemany('INSERT OR IGNORE INTO collection_photos VALUES(?,?)',
                                        [(collection_id,id_) for id_ in photo_ids])
        return self.get(collection_id)

    def predicate(self,id_,*,ordered_page=False):
        row=self.get(id_)
        if row['kind']=='smart': return criteria(row['rules'],row['match'],ordered_page=ordered_page)
        if row['kind'] != 'set':
            return 'id IN (SELECT photo_id FROM collection_photos WHERE collection_id=?)',[id_]
        # One relational query covers arbitrarily many regular members. Compile
        # only descendant smart predicates, with an explicit expression bound.
        smart=self.db.execute(TREE+"SELECT c.rules,c.match FROM collections c JOIN tree t ON c.id=t.id "
                              "WHERE c.kind='smart' LIMIT 129",(id_,)).fetchall()
        if len(smart)>128: raise ValueError('Open a smaller set; aggregate views support up to 128 smart collections')
        clauses=['id IN ('+TREE+'SELECT photo_id FROM collection_photos WHERE collection_id IN (SELECT id FROM tree))']
        values=[id_]
        for item in smart:
            clause,args=criteria(json.loads(item[0]),item[1],ordered_page=ordered_page);clauses.append(clause);values.extend(args)
        return '('+' OR '.join(clauses)+')',values

    def membership(self,collection_id,expected_revision,ids,action):
        row=self.checked(collection_id,expected_revision)
        if row['kind']=='smart': raise ValueError('Smart collection membership is determined by its rules')
        if row['kind']=='set': raise ValueError('Collection sets contain collections, not photos')
        ids=list(dict.fromkeys(ids))
        if not ids or len(ids)>60:
            raise ValueError('Choose between 1 and 60 photos')
        slots=','.join('?' for _ in ids)
        if self.db.execute(f'SELECT COUNT(*) FROM photos WHERE id IN ({slots})',ids).fetchone()[0] != len(ids):
            raise ValueError('Photo does not exist')
        if action not in ('add','remove'): raise ValueError('Unsupported membership action')
        with self.db:
            if action=='add':
                self.db.executemany('INSERT OR IGNORE INTO collection_photos VALUES(?,?)',[(collection_id,i) for i in ids])
            else:
                self.db.executemany('DELETE FROM collection_photos WHERE collection_id=? AND photo_id=?',[(collection_id,i) for i in ids])
            self.db.execute('UPDATE collections SET revision=revision+1 WHERE id=?',(collection_id,))
            self.touch_ancestors(row['parent_id'])
        return self.get(collection_id)

    def state(self,photo_ids=()):
        row=dict(self.db.execute('SELECT * FROM collection_state WHERE id=1').fetchone())
        result={'revision':row['revision'],'quick':self.get(row['quick_id']),'target':self.get(row['target_id']),'members':[]}
        if photo_ids:
            slots=','.join('?' for _ in photo_ids)
            result['members']=[r[0] for r in self.db.execute(
                f'SELECT photo_id FROM collection_photos WHERE collection_id=? AND photo_id IN ({slots})',
                [row['target_id'],*photo_ids])]
        return result

    def set_target(self,expected_revision,collection_id=None):
        current=self.state()
        if current['revision'] != expected_revision: raise ValueError('Target collection conflict; refresh before changing target')
        id_=collection_id or current['quick']['id']
        if self.get(id_)['kind'] not in ('regular','quick'): raise ValueError('Only a regular or Quick Collection can be targeted')
        with self.db:
            self.db.execute('UPDATE collection_state SET target_id=?,revision=revision+1 WHERE id=1',(id_,))
        return self.state()

    def target_membership(self,expected_state_revision,collection_id,expected_revision,photo_ids,action):
        current=self.state()
        if current['revision'] != expected_state_revision or current['target']['id'] != collection_id:
            raise ValueError('Target collection conflict; refresh before adding photos')
        self.membership(collection_id,expected_revision,photo_ids,action)
        return self.state(photo_ids)

    def delete(self,collection_id,expected_revision):
        row=self.checked(collection_id,expected_revision)
        if row['kind']=='quick': raise ValueError('The Quick Collection cannot be deleted; clear it instead')
        current=self.state()
        target_inside=self.db.execute(TREE+'SELECT 1 FROM tree WHERE id=?',(collection_id,current['target']['id'])).fetchone()
        with self.db:
            if target_inside:
                self.db.execute('UPDATE collection_state SET target_id=quick_id,revision=revision+1 WHERE id=1')
            self.db.execute(TREE+'DELETE FROM collection_photos WHERE collection_id IN (SELECT id FROM tree)',(collection_id,))
            self.db.execute(TREE+'DELETE FROM collections WHERE id IN (SELECT id FROM tree)',(collection_id,))
            self.touch_ancestors(row['parent_id'])
        return {'deleted':collection_id,'state':self.state()}

    def quick(self,expected_revision,action,name=None,clear_after=False,parent_id=None):
        row=self.state()['quick'];self.checked(row['id'],expected_revision)
        if action not in ('clear','save'): raise ValueError('Unsupported Quick Collection action')
        if action=='save':
            if not name or not name.strip(): raise ValueError('Saved collection name cannot be blank')
            self.validate_parent(parent_id)
        with self.db:
            saved=None
            if action=='save':
                id_=self.db.execute("INSERT INTO collections(name,kind,parent_id,created) VALUES(?,'regular',?,?)",
                                   (name.strip(),parent_id,time.time())).lastrowid
                self.db.execute('INSERT INTO collection_photos SELECT ?,photo_id FROM collection_photos WHERE collection_id=?',(id_,row['id']))
                from .stacks import Stacks
                Stacks(self.catalog).duplicate_collection(row['id'],id_)
                self.touch_ancestors(parent_id);saved=self.get(id_)
            if action=='clear' or clear_after:
                self.db.execute('DELETE FROM collection_photos WHERE collection_id=?',(row['id'],))
                self.db.execute('UPDATE collections SET revision=revision+1 WHERE id=?',(row['id'],))
        return {'saved':saved,'state':self.state()}

    def duplicate(self,collection_id,expected_revision,name):
        original=self.checked(collection_id,expected_revision)
        if original['kind']=='quick': raise ValueError('Use Save Quick Collection for the Quick Collection')
        if not name.strip(): raise ValueError('Collection name cannot be blank')
        ids=[row[0] for row in self.db.execute(TREE+'SELECT id FROM tree LIMIT 1001',(collection_id,))]
        if len(ids)>1000: raise ValueError('Duplicate a smaller set; at most 1000 collections can be copied together')
        mapping={}
        with self.db:
            # Allocate every copy first; never depend on recursive SQL row order.
            for id_ in ids:
                row=self.get(id_)
                new_id=self.db.execute('INSERT INTO collections(name,kind,rules,match,parent_id,created) VALUES(?,?,?,?,?,?)',
                    (name.strip() if id_==collection_id else row['name'],row['kind'],json.dumps(row['rules']),row['match'],None,time.time())).lastrowid
                mapping[id_]=new_id
                self.db.execute('INSERT INTO collection_photos SELECT ?,photo_id FROM collection_photos WHERE collection_id=?',(new_id,id_))
                from .stacks import Stacks
                Stacks(self.catalog).duplicate_collection(id_,new_id)
            for old_id,new_id in mapping.items():
                parent=original['parent_id'] if old_id==collection_id else mapping[self.get(old_id)['parent_id']]
                self.db.execute('UPDATE collections SET parent_id=? WHERE id=?',(parent,new_id))
            self.touch_ancestors(original['parent_id'])
        return {**self.get(mapping[collection_id]),'copied_collections':len(ids)}

"""Portable, source-scoped photo stacks with bounded library projection.

Inputs: ordered selections (at most 60), a captured stack revision and an optional
regular collection. Outputs: atomic grouping, visibility and ordering changes,
plus bounded page projections with true 1-based member ordinals. Ordinals use
the complete scoped stack order, not sparse position values or filtered pages;
disjoint indexed ranges avoid repeating each row's full prefix count. A deep page
still scans its prefix once per stack on that page. Folder and collection stacks
remain independent. Collapsed members never become implicit mutation targets.
No pixels, original writes or recipe edits. The catalog-wide revision rejects
concurrent structural changes; SQLite triggers preserve stack integrity.
"""
import os


def migrate(db):
    if db.execute('PRAGMA user_version').fetchone()[0] >= 4:
        return
    statements = [
        'CREATE TABLE stack_state(id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL DEFAULT 0)',
        'INSERT OR IGNORE INTO stack_state(id) VALUES(1)',
        "CREATE TABLE photo_stacks(id INTEGER PRIMARY KEY AUTOINCREMENT, scope TEXT NOT NULL, "
        "folder TEXT NOT NULL DEFAULT '', collapsed INTEGER NOT NULL DEFAULT 0, top_id INTEGER, size INTEGER NOT NULL DEFAULT 0)",
        'CREATE INDEX stack_scope ON photo_stacks(scope,folder,id)',
        'CREATE TABLE stack_members(scope TEXT NOT NULL, photo_id INTEGER NOT NULL, stack_id INTEGER NOT NULL, '
        'position INTEGER NOT NULL, PRIMARY KEY(scope,photo_id))',
        'CREATE INDEX stack_order ON stack_members(stack_id,position,photo_id)',
        'CREATE INDEX stack_photo ON stack_members(photo_id,scope)',
        'CREATE TRIGGER stack_deleted AFTER DELETE ON photo_stacks BEGIN '
        'DELETE FROM stack_members WHERE stack_id=OLD.id; END',
        'CREATE TRIGGER stack_member_deleted AFTER DELETE ON stack_members BEGIN '
        'UPDATE photo_stacks SET size=(SELECT count(*) FROM stack_members WHERE stack_id=OLD.stack_id), '
        'top_id=(SELECT photo_id FROM stack_members WHERE stack_id=OLD.stack_id ORDER BY position,photo_id LIMIT 1) '
        'WHERE id=OLD.stack_id; DELETE FROM photo_stacks WHERE id=OLD.stack_id AND size<2; END',
        'CREATE TRIGGER stacked_photo_deleted AFTER DELETE ON photos BEGIN '
        'DELETE FROM stack_members WHERE photo_id=OLD.id; END',
        "CREATE TRIGGER stacked_membership_deleted AFTER DELETE ON collection_photos BEGIN "
        "DELETE FROM stack_members WHERE photo_id=OLD.photo_id AND scope='collection:'||OLD.collection_id; END",
        "CREATE TRIGGER stacked_collection_deleted AFTER DELETE ON collections BEGIN "
        "DELETE FROM photo_stacks WHERE scope='collection:'||OLD.id; "
        "UPDATE stack_state SET revision=revision+1 WHERE id=1; END",
    ]
    for table in ('photo_stacks', 'stack_members'):
        for event in ('INSERT', 'UPDATE', 'DELETE'):
            statements.append(f'CREATE TRIGGER {table}_{event.lower()}_revision AFTER {event} ON {table} BEGIN '
                              'UPDATE stack_state SET revision=revision+1 WHERE id=1; END')
    with db:
        db.execute('BEGIN IMMEDIATE')
        for statement in statements:
            for kind in ('TABLE','INDEX','TRIGGER'):
                statement=statement.replace('CREATE '+kind+' ', 'CREATE '+kind+' IF NOT EXISTS ',1)
            db.execute(statement)
        # Existing variants remain visible. Only newly created copies are grouped
        # automatically; migration never invents an organization the user did not see.
        db.execute('PRAGMA user_version=4')


class Stacks:
    def __init__(self, catalog):
        self.catalog = catalog
        self.db = catalog.db

    def revision(self):
        return self.db.execute('SELECT revision FROM stack_state WHERE id=1').fetchone()[0]

    def scope(self, collection_id=None, writable=False):
        if collection_id is None:
            return 'folder'
        from .collections import Collections
        row = Collections(self.catalog).get(collection_id)
        if row['kind'] not in ('regular', 'quick'):
            if writable:
                raise ValueError('Stacks require a regular collection or a single folder')
            return None
        return f'collection:{collection_id}'

    def check(self, revision):
        if revision != self.revision():
            raise ValueError('Stack conflict; refresh the library before changing stacks')

    def member(self, scope, photo_id):
        return self.db.execute('SELECT * FROM stack_members WHERE scope=? AND photo_id=?',
                               (scope, photo_id)).fetchone()

    def recalculate(self, stack_id):
        self.db.execute('UPDATE photo_stacks SET size=(SELECT count(*) FROM stack_members WHERE stack_id=?), '
                        'top_id=(SELECT photo_id FROM stack_members WHERE stack_id=? ORDER BY position,photo_id LIMIT 1) '
                        'WHERE id=?', (stack_id, stack_id, stack_id))

    def append(self, stack_id, scope, ids):
        position = self.db.execute('SELECT COALESCE(max(position),-1)+1 FROM stack_members WHERE stack_id=?',
                                   (stack_id,)).fetchone()[0]
        self.db.executemany('INSERT INTO stack_members VALUES(?,?,?,?)',
                            [(scope, id_, stack_id, position+i) for i, id_ in enumerate(ids)])
        self.recalculate(stack_id)

    def create(self, scope, folder, ids, collapsed=True):
        id_ = self.db.execute('INSERT INTO photo_stacks(scope,folder,collapsed) VALUES(?,?,?)',
                              (scope, folder, int(collapsed))).lastrowid
        self.append(id_, scope, ids)
        return id_

    def copy_created(self, original, copy_id):
        """Join the origin's folder stack inside the caller's copy transaction."""
        member = self.member('folder', original['id'])
        if member:
            id_ = member['stack_id']
            self.db.execute('UPDATE stack_members SET position=position+1 WHERE stack_id=? AND position>?',
                            (id_, member['position']))
            self.db.execute("INSERT INTO stack_members VALUES('folder',?,?,?)",
                            (copy_id, id_, member['position']+1))
            self.recalculate(id_)
            self.db.execute('UPDATE photo_stacks SET collapsed=0 WHERE id=?', (id_,))
        else:
            self.create('folder', os.path.dirname(original['path']), [original['id'], copy_id], False)

    def duplicate_collection(self, original, destination):
        """Copy only stack organization inside the enclosing collection transaction."""
        scope=f'collection:{destination}'
        for row in self.db.execute('SELECT * FROM photo_stacks WHERE scope=?', (f'collection:{original}',)):
            id_=self.db.execute('INSERT INTO photo_stacks(scope,folder,collapsed,top_id,size) VALUES(?,?,?,?,?)',
                               (scope,'',row['collapsed'],row['top_id'],row['size'])).lastrowid
            self.db.execute('INSERT INTO stack_members SELECT ?,photo_id,?,position FROM stack_members WHERE stack_id=?',
                            (scope,id_,row['id']))

    def change(self, action, photo_ids, expected_revision, collection_id=None, active_id=None):
        if not 1 <= len(photo_ids) <= 60 or len(set(photo_ids)) != len(photo_ids):
            raise ValueError('Stack actions require 1 to 60 distinct photos')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            self.check(expected_revision)
            scope = self.scope(collection_id, writable=True)
            rows = self.catalog.summaries(photo_ids)
            if len(rows) != len(photo_ids):
                raise ValueError('A selected photo no longer exists')
            if collection_id is not None:
                count = self.db.execute('SELECT count(*) FROM collection_photos WHERE collection_id=? '
                    'AND photo_id IN ('+','.join('?' for _ in photo_ids)+')', [collection_id,*photo_ids]).fetchone()[0]
                if count != len(photo_ids):
                    raise ValueError('Every selected photo must belong to this collection')
            members = {id_:self.member(scope,id_) for id_ in photo_ids}
            stacks = {row['stack_id'] for row in members.values() if row}
            if action == 'group':
                if len(photo_ids) < 2:
                    raise ValueError('Select at least two photos to group')
                folders = {os.path.dirname(row['path']) for row in rows}
                if scope == 'folder' and len(folders) != 1:
                    raise ValueError('Folder stacks require photos from the same folder')
                active = active_id if active_id is not None else photo_ids[0]
                if active not in photo_ids:
                    raise ValueError('The active photo must be selected')
                ordered = [active]+[id_ for id_ in photo_ids if id_ != active]
                anchor = next((members[id_] for id_ in ordered if members[id_]), None)
                if anchor:
                    destination = anchor['stack_id']
                    moving = [id_ for id_ in photo_ids if not members[id_] or members[id_]['stack_id'] != destination]
                    # Moving a collapsed cover transfers only that selected photo;
                    # other members of its former stack retain their own grouping.
                    for id_ in moving:
                        self.db.execute('DELETE FROM stack_members WHERE scope=? AND photo_id=?', (scope,id_))
                    self.append(destination, scope, moving)
                    self.db.execute('UPDATE photo_stacks SET collapsed=1 WHERE id=?', (destination,))
                else:
                    self.create(scope, next(iter(folders)) if scope == 'folder' else '', ordered)
            elif action == 'split':
                if len(stacks)!=1 or any(row is None for row in members.values()):
                    raise ValueError('Select photos from one expanded stack to split')
                old=self.db.execute('SELECT * FROM photo_stacks WHERE id=?',(next(iter(stacks)),)).fetchone()
                if old['collapsed'] or photo_ids==[old['top_id']]:
                    raise ValueError('Expand the stack and select photos beyond its cover to split')
                if len(photo_ids)>=old['size']:
                    raise ValueError('Leave at least one photo in the original stack')
                ordered=sorted(photo_ids,key=lambda id_:members[id_]['position'])
                for id_ in ordered:
                    self.db.execute('DELETE FROM stack_members WHERE scope=? AND photo_id=?',(scope,id_))
                if len(ordered)>=2:self.create(scope,old['folder'],ordered,False)
            elif action in ('expand', 'collapse', 'toggle', 'unstack'):
                for id_ in stacks:
                    if action == 'unstack':
                        self.db.execute('DELETE FROM photo_stacks WHERE id=?', (id_,))
                    else:
                        value = '1-collapsed' if action == 'toggle' else '0' if action == 'expand' else '1'
                        self.db.execute(f'UPDATE photo_stacks SET collapsed={value} WHERE id=?', (id_,))
            elif action == 'remove':
                for id_ in photo_ids:
                    self.db.execute('DELETE FROM stack_members WHERE scope=? AND photo_id=?', (scope,id_))
            elif action in ('top', 'up', 'down'):
                if len(photo_ids) != 1 or not members[photo_ids[0]]:
                    raise ValueError('Select one photo in a stack to reorder')
                member = members[photo_ids[0]]
                id_, position = member['stack_id'], member['position']
                if action == 'top':
                    value = self.db.execute('SELECT min(position)-1 FROM stack_members WHERE stack_id=?', (id_,)).fetchone()[0]
                    self.db.execute('UPDATE stack_members SET position=? WHERE scope=? AND photo_id=?',
                                    (value,scope,photo_ids[0]))
                else:
                    op, direction = ('<','DESC') if action == 'up' else ('>','ASC')
                    neighbor = self.db.execute(f'SELECT photo_id,position FROM stack_members WHERE stack_id=? '
                        f'AND position{op}? ORDER BY position {direction} LIMIT 1', (id_,position)).fetchone()
                    if neighbor:
                        self.db.execute('UPDATE stack_members SET position=? WHERE scope=? AND photo_id=?',
                                        (position,scope,neighbor['photo_id']))
                        self.db.execute('UPDATE stack_members SET position=? WHERE scope=? AND photo_id=?',
                                        (neighbor['position'],scope,photo_ids[0]))
                self.recalculate(id_)
            else:
                raise ValueError('Unsupported stack action')
            if collection_id is not None and self.revision() != expected_revision:
                from .collections import Collections
                collection=Collections(self.catalog).get(collection_id)
                self.db.execute('UPDATE collections SET revision=revision+1 WHERE id=?',(collection_id,))
                Collections(self.catalog).touch_ancestors(collection['parent_id'])
        return {'revision':self.revision()}

    def visibility(self, collapsed, expected_revision, collection_id=None, folder=None,include_subfolders=True):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            self.check(expected_revision)
            scope=self.scope(collection_id,writable=True)
            where='scope=? AND collapsed!=?'
            params=[scope,int(collapsed)]
            if folder is not None:
                if collection_id is not None:
                    raise ValueError('Choose either a collection or folder stack source')
                path=os.path.abspath(os.path.expanduser(folder)).rstrip(os.sep) or os.sep
                prefix=path.rstrip(os.sep)+os.sep
                if include_subfolders:
                    where+=' AND (folder=? OR substr(folder,1,?)=?)'
                    params.extend((path,len(prefix),prefix))
                else:
                    where+=' AND folder=?'
                    params.append(path)
            count=self.db.execute('UPDATE photo_stacks SET collapsed=? WHERE '+where,
                                  [int(collapsed),*params]).rowcount
            if collection_id is not None and count:
                from .collections import Collections
                row=Collections(self.catalog).get(collection_id)
                self.db.execute('UPDATE collections SET revision=revision+1 WHERE id=?',(collection_id,))
                Collections(self.catalog).touch_ancestors(row['parent_id'])
        return {'revision':self.revision(),'changed':count}

    def annotate_ordinals(self, rows, scope):
        """Add full-stack ordinals to at most one already-fetched page of rows.

        The caller owns presentation scope and has already bounded `rows` to 60.
        Rows without stack membership receive null. For each expanded stack, a
        strict prefix before its first visible member and non-overlapping intervals
        between later visible members cover the needed index range once; filters
        may omit members, which are still counted. Collapsed covers are ordinal 1
        by the maintained top_id invariant. Each stack ID is checked against the
        requested scope once; range counts then use only the covering order index.
        No member rows are materialized.
        """
        if len(rows) > 60:
            raise ValueError('Stack ordinal projection is limited to one 60-row page')
        for row in rows:
            row['stack_ordinal'] = None

        if not scope:
            return rows

        groups = {}
        for row in rows:
            stack_id = row.get('stack_id')
            if stack_id is None or row.get('stack_position') is None:
                continue
            groups.setdefault(stack_id, []).append(row)

        def count_before(stack_id, position, photo_id):
            # Two disjoint ranges preserve the composite stack_order index and
            # implement the strict lexicographic prefix (position, photo_id).
            # The stack's scope is checked once before ranking; stack_id is the
            # leading index key and uniquely identifies that scoped stack.
            return self.db.execute(
                'SELECT (SELECT count(*) FROM stack_members WHERE stack_id=? AND position<?) '
                '+ (SELECT count(*) FROM stack_members WHERE stack_id=? AND position=? AND photo_id<?)',
                (stack_id, position, stack_id, position, photo_id)).fetchone()[0]

        def count_interval(stack_id, previous, current):
            before_position, before_id = previous
            position, photo_id = current
            if before_position == position:
                return self.db.execute(
                    'SELECT count(*) FROM stack_members WHERE stack_id=? AND position=? '
                    'AND photo_id>? AND photo_id<=?',
                    (stack_id, position, before_id, photo_id)).fetchone()[0]
            # These ranges are disjoint: the remainder of the previous position,
            # all intervening positions, and the prefix through the current row.
            return self.db.execute(
                'SELECT (SELECT count(*) FROM stack_members WHERE stack_id=? '
                'AND position=? AND photo_id>?) '
                '+ (SELECT count(*) FROM stack_members WHERE stack_id=? '
                'AND position>? AND position<?) '
                '+ (SELECT count(*) FROM stack_members WHERE stack_id=? '
                'AND position=? AND photo_id<=?)',
                (stack_id, before_position, before_id,
                 stack_id, before_position, position,
                 stack_id, position, photo_id)).fetchone()[0]

        for stack_id, members in groups.items():
            # Page projection already joined membership on this scope. Verify
            # the globally unique stack ID belongs to that same scope once, then
            # let stack_order cover every scalar range count without table reads.
            if not self.db.execute('SELECT 1 FROM photo_stacks WHERE id=? AND scope=?',
                                   (stack_id, scope)).fetchone():
                continue
            members = [row for row in members if not (
                row.get('stack_collapsed') and row.get('stack_top') == row.get('id'))]
            if not members:
                # A collapsed projection contains only its cover; top_id is
                # maintained as the first (position, photo_id) member.
                for row in groups[stack_id]:
                    if row.get('stack_collapsed') and row.get('stack_top') == row.get('id'):
                        row['stack_ordinal'] = 1
                continue
            members.sort(key=lambda row: (row['stack_position'], row['id']))
            first = members[0]
            first_key = (first['stack_position'], first['id'])
            # top_id is always the first member in canonical stack order. This
            # avoids a prefix count when the visible page includes the cover.
            ordinal = 1 if first.get('stack_top') == first['id'] else count_before(
                stack_id, *first_key) + 1
            first['stack_ordinal'] = ordinal
            previous = first_key
            for row in members[1:]:
                current = (row['stack_position'], row['id'])
                ordinal += count_interval(stack_id, previous, current)
                row['stack_ordinal'] = ordinal
                previous = current
        return rows

    def projection(self, where, params, collection_id, sort='imported', descending=True, offset=None):
        """SQL-page stack members, then annotate the returned rows with ordinals."""
        from .organization import SORTS
        from .catalog import SUMMARY_COLUMNS
        if sort not in SORTS:
            raise ValueError('Unsupported library sort')
        scope = self.scope(collection_id)
        direction = 'DESC' if descending else 'ASC'
        if scope is None or not self.db.execute('SELECT 1 FROM photo_stacks WHERE scope=? LIMIT 1',(scope,)).fetchone():
            if offset is None:
                return self.db.execute('SELECT count(*) FROM photos'+where,params).fetchone()[0]
            return [dict(row) for row in self.db.execute('SELECT '+SUMMARY_COLUMNS+
                ',NULL AS stack_id,NULL AS stack_count,NULL AS stack_collapsed,NULL AS stack_top,NULL AS stack_position,NULL AS stack_ordinal '
                f'FROM photos{where} ORDER BY {SORTS[sort]} {direction},id {direction} LIMIT 60 OFFSET ?',
                [*params,max(0,offset)])]
        if offset is None:
            if not where and scope == 'folder':
                # All Photos can count covers from maintained stack sizes without
                # joining every photo. Filtered sources still count exact matches.
                return self.db.execute("SELECT (SELECT count(*) FROM photos)-COALESCE("
                    "(SELECT sum(size-1) FROM photo_stacks WHERE scope='folder' AND collapsed=1),0)").fetchone()[0]
            return self.db.execute('SELECT count(*) FROM (SELECT id FROM photos'+where+') AS p '
                'LEFT JOIN stack_members m ON m.photo_id=p.id AND m.scope=? '
                'LEFT JOIN photo_stacks s ON s.id=m.stack_id '
                'WHERE s.id IS NULL OR s.collapsed=0 OR s.top_id=p.id', [*params,scope]).fetchone()[0]
        column = {'imported':'id','name':'name','rating':'rating','captured':'taken','color':'color_label'}[sort]
        collation = ' COLLATE NOCASE' if sort == 'name' else ''
        # Page narrow IDs/sort keys before fetching summaries or family subqueries.
        # LIMIT prevents SQLite from flattening this into per-catalog-row hydration.
        source = (f'(SELECT photos.id AS photo_id, s.id AS stack_id,s.size AS stack_count,s.collapsed AS stack_collapsed, '
                  f's.top_id AS stack_top,m.position AS stack_position,COALESCE(top.{column},photos.value) AS stack_sort, '
                  f'COALESCE(s.top_id,photos.id) AS stack_sort_id FROM (SELECT id,{column} AS value FROM photos'+where+') AS photos '
                  'LEFT JOIN stack_members m ON m.photo_id=photos.id AND m.scope=? '
                  'LEFT JOIN photo_stacks s ON s.id=m.stack_id LEFT JOIN photos top ON top.id=s.top_id '
                  'WHERE s.id IS NULL OR s.collapsed=0 OR s.top_id=photos.id '
                  f'ORDER BY stack_sort{collation} {direction},stack_sort_id {direction},stack_position ASC,photos.id ASC LIMIT 60 OFFSET ?) AS page')
        params = [*params,scope]
        columns = SUMMARY_COLUMNS+',stack_id,stack_count,stack_collapsed,stack_top,stack_position'
        rows = [dict(row) for row in self.db.execute('SELECT '+columns+' FROM '+source+
            ' JOIN photos ON photos.id=page.photo_id'+
            f' ORDER BY stack_sort{collation} {direction},stack_sort_id {direction},stack_position ASC,page.photo_id ASC',
            [*params,max(0,offset)])]
        return self.annotate_ordinals(rows, scope)

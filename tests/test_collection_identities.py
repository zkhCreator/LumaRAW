"""Collection identity lifetime and real v4-to-v5 migration evidence.

Inputs: disposable catalogs built with the published pre-v5 migration chain.
Outputs: non-reused IDs, rejected stale commands and preserved dependent state.
No original writes, desktop UI or compatibility claim for arbitrary user schemas.
"""
import json
import sqlite3

import pytest

from lumaraw import catalog as catalog_module
from lumaraw.catalog import Catalog
from lumaraw.collections import Collections, migrate, migrate_identities
from lumaraw.organization import migrate_metadata
from lumaraw.virtual_copies import migrate as migrate_copies
from lumaraw.stacks import migrate as migrate_stacks
from lumaraw.model import Recipe
from lumaraw.runtime import CATALOG_VERSION
from lumaraw.service import Service


def v4(db):
    migrate_metadata(db);migrate(db);migrate_copies(db);migrate_stacks(db)


def test_v4_migration_preserves_live_references_and_schema_objects(tmp_path,monkeypatch):
    root=tmp_path/'catalog'
    with monkeypatch.context() as patch:
        patch.setattr(catalog_module,'migrate',v4)
        c=Catalog(root);store=Collections(c)
        parent=store.save('Set',kind='set')
        album=store.save('Album',parent_id=parent['id'])
        smart=store.save('Smart',kind='smart',rules={'rating_min':4},parent_id=parent['id'])
        store.set_target(0,album['id'])
        with c.db:
            c.db.execute("ALTER TABLE collections ADD COLUMN notes TEXT DEFAULT ''")
            c.db.execute("UPDATE collections SET notes='retained' WHERE id=?",(album['id'],))
            c.db.execute('CREATE INDEX collection_notes ON collections(notes)')
            c.db.execute('CREATE TABLE collection_audit(id INTEGER)')
            c.db.execute('CREATE TRIGGER collection_audited AFTER UPDATE ON collections BEGIN '
                         'INSERT INTO collection_audit VALUES(NEW.id); END')
            for i in range(2):
                c.db.execute('INSERT INTO photos(path,name,bytes,mtime,recipe,created) VALUES(?,?,0,0,?,0)',
                    (str(tmp_path/f'{i}.png'),f'{i}.png',json.dumps(Recipe().dict())))
        # Build the v4 fixture with its own schema. Current domain commands read
        # current keyword tables, which deliberately do not exist before upgrade.
        with c.db:
            c.db.executemany('INSERT INTO collection_photos VALUES(?,?)', [(album['id'],1),(album['id'],2)])
            scope=f"collection:{album['id']}"
            stack=c.db.execute('INSERT INTO photo_stacks(scope,folder,collapsed,top_id,size) VALUES(?,?,0,1,2)',
                               (scope,'')).lastrowid
            c.db.executemany('INSERT INTO stack_members(scope,photo_id,stack_id,position) VALUES(?,?,?,?)',
                            [(scope,1,stack,0),(scope,2,stack,1)])
        tables=('collections','collection_state','collection_photos','photo_stacks','stack_members','stack_state','collection_audit')
        before={table:[tuple(row) for row in c.db.execute(f'SELECT * FROM {table}')] for table in tables}
        assert c.db.execute('PRAGMA user_version').fetchone()[0]==4
        c.close()
    c=Catalog(root)
    assert c.db.execute('PRAGMA user_version').fetchone()[0]==CATALOG_VERSION
    for table in tables:
        assert [tuple(row) for row in c.db.execute(f'SELECT * FROM {table}')]==before[table]
    assert c.db.execute("SELECT count(*) FROM sqlite_master WHERE name IN ('collection_notes','collection_audited','stacked_collection_deleted')").fetchone()[0]==3
    with c.db:c.db.execute("UPDATE collections SET notes='updated' WHERE id=?",(album['id'],))
    assert c.db.execute('SELECT id FROM collection_audit ORDER BY rowid DESC LIMIT 1').fetchone()[0]==album['id']
    state=Collections(c).state();assert state['target']['id']==album['id']
    current=Collections(c).get(album['id']);Collections(c).delete(album['id'],current['revision'])
    assert c.db.execute('SELECT count(*) FROM photo_stacks').fetchone()[0]==0
    assert Collections(c).state()['target']['kind']=='quick'
    assert c.db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    c.close()


def test_deleted_highest_collection_id_is_not_reused_after_restart(tmp_path):
    root=tmp_path/'catalog';c=Catalog(root);store=Collections(c)
    parent=store.save('Set',kind='set');album=store.save('Album',parent_id=parent['id'])
    high=album['id'];parent=store.get(parent['id'])
    store.delete(parent['id'],parent['revision']);c.close()
    c=Catalog(root);new=Collections(c).save('Replacement')
    assert new['id']>high
    assert c.db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    c.close()


def test_stale_service_collection_commands_never_retarget_new_collection(tmp_path):
    s=Service(tmp_path/'catalog')
    try:
        old=s.dispatch('save_collection',{'name':'Old','kind':'regular'})
        s.dispatch('delete_collection',{'collection_id':old['id'],'expected_revision':old['revision']})
        new=s.dispatch('save_collection',{'name':'New','kind':'regular'})
        assert new['id']>old['id']
        commands=[('save_collection',{'name':'Stale rename','kind':'regular'}),
                  ('delete_collection',{}),('duplicate_collection',{'name':'Stale duplicate'}),
                  ('collection_membership',{'action':'add','photo_ids':[1]})]
        for method,extra in commands:
            with pytest.raises(ValueError,match='does not exist'):
                s.dispatch(method,{'collection_id':old['id'],'expected_revision':old['revision'],**extra})
        state=s.dispatch('collection_state')
        with pytest.raises(ValueError,match='does not exist'):
            s.dispatch('set_target_collection',{'collection_id':old['id'],'expected_revision':state['revision']})
        assert s.dispatch('get_collection',{'collection_id':new['id']})=={**new,'ancestors':[]}
    finally:s.close()


def test_failed_migration_rolls_back_without_dropping_old_collection(tmp_path,monkeypatch):
    root=tmp_path/'catalog'
    with monkeypatch.context() as patch:
        patch.setattr(catalog_module,'migrate',v4)
        c=Catalog(root);album=Collections(c).save('Keep')
    # Refuse DROP TABLE through SQLite's authorizer after the new table is built.
    c.db.set_authorizer(lambda action,a,b,d,t:sqlite3.SQLITE_DENY if action==sqlite3.SQLITE_DROP_TABLE else sqlite3.SQLITE_OK)
    with pytest.raises(sqlite3.DatabaseError):migrate_identities(c.db)
    c.db.set_authorizer(None)
    assert c.db.execute('PRAGMA user_version').fetchone()[0]==4
    assert Collections(c).get(album['id'])==album
    assert c.db.execute("SELECT count(*) FROM sqlite_master WHERE name='collections_v5'").fetchone()[0]==0
    migrate_identities(c.db)
    assert Collections(c).get(album['id'])==album
    c.close()

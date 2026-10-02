"""Upgrade genuinely old Copy journals without changing retained output paths.

Inputs: schema-29 tables, generated originals and optionally published transfers.
Outputs: explicit recovery with one new provenance range and preserved bytes.
The fixture uses pre-counter journal operations, never a downgraded modern schema.
"""
import json

import pytest

from lumaraw.catalog import Catalog
from lumaraw.service import Service
from lumaraw.import_copy import ImportCopy
from lumaraw import import_copy_io as io
from lumaraw.relocations import identity
from legacy_catalog import migrate_to
from test_import_review import picture


@pytest.mark.parametrize('published', [False, True])
def test_schema_29_copy_resume_allocates_provenance_once_without_retargeting(tmp_path, monkeypatch, published):
    from lumaraw import catalog as module
    source = picture(tmp_path/'source'/'old.jpg')
    destination = tmp_path/'output'
    destination.mkdir()
    with monkeypatch.context() as patch:
        patch.setattr(module, 'migrate', lambda db: migrate_to(db,29))
        catalog = Catalog(tmp_path/'catalog')
    value = io.validate_destination(destination, [], catalog.root)
    with catalog.db:
        plan_id = catalog.db.execute("INSERT INTO import_plans(state,phase,include_subfolders,selected_count,"
            "file_count,created) VALUES('interrupted','copying',1,1,1,1)").lastrowid
        catalog.db.execute("INSERT INTO import_files(plan_id,path,name,extension,state,bytes,mtime,fingerprints) "
            "VALUES(?,?,?,'jpg','new',?,?,?)",
            (plan_id,str(source),source.name,source.stat().st_size,source.stat().st_mtime_ns,
             json.dumps({str(source):identity(source)})))
        domain = ImportCopy(catalog)
        # Seed the old contract directly; current capture writes a newer option.
        catalog.db.execute('INSERT INTO import_copy_plans(plan_id,destination,destination_identity,organization,subfolder,roots,owner) '
            'VALUES(?,?,?,?,?,?,?)',(plan_id,value['destination'],json.dumps(value['destination_identity']),
            value['organization'],value['subfolder'],json.dumps(value['roots']),str(catalog.root)))
    value.update(naming='{}', backup='{}')
    rows = [dict(row) for row in catalog.db.execute('SELECT * FROM import_files')]
    domain.stage(plan_id,rows,value)
    if published:
        for row in domain.page(plan_id):
            io.transfer(row,value,domain.save,lambda:False)
    assert catalog.db.execute('PRAGMA user_version').fetchone()[0] == 29
    catalog.close()

    service = Service(tmp_path/'catalog',presets_root=tmp_path/'presets')
    try:
        plan = service.dispatch('get_import')['plan']
        assert not plan['sequence']['frozen']
        result = service.dispatch('resume_import_copy', {
            'plan_id':plan_id,'expected_revision':plan['revision'],
        })['plan']
        assert result['state'] == 'applied' and result['imported'] == 1
        assert result['sequence']['frozen']
        assert (destination/'old.jpg').read_bytes() == source.read_bytes()
        assert len(list(destination.iterdir())) == 1
        photo = service.dispatch('get_photo',{'photo_id':1})
        assert (photo['import_number'],photo['image_number']) == (1,1)
        state = service.dispatch('get_import_sequence')
        assert (state['next_import'],state['next_image']) == (2,2)
        with pytest.raises(ValueError):
            service.dispatch('resume_import_copy',{'plan_id':plan_id,'expected_revision':result['revision']})
        assert service.dispatch('get_import_sequence') == state
    finally:
        service.close()

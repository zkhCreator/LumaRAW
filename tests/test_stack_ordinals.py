"""One-based member ordinals for complete, scoped photo stacks.

Generated catalogs cover reorder, split, virtual-copy, auto-stack, paging and
filtering behavior. VM-work evidence guards against repeating a stack-prefix
count for every returned row; it does not claim desktop or Lightroom parity.
"""
import json
from pathlib import Path

from lumaraw.catalog import Catalog
from lumaraw.model import Recipe
from lumaraw.stacks import Stacks
from test_stacks import change, page, service


def ranks(s, **extra):
    return {row['id']: row['stack_ordinal'] for row in page(s, **extra)['photos']}


def test_ordinals_follow_moves_and_compress_negative_sparse_positions(service):
    s = service
    change(s, 'group', [1, 2, 3, 4, 5])
    change(s, 'expand', [1])
    assert {key: ranks(s)[key] for key in range(1, 6)} == {
        1: 1, 2: 2, 3: 3, 4: 4, 5: 5,
    }

    change(s, 'top', [4])
    assert [ranks(s)[key] for key in (4, 1, 2, 3, 5)] == [1, 2, 3, 4, 5]
    with s.catalog() as c:
        assert c.db.execute('SELECT position FROM stack_members WHERE photo_id=4').fetchone()[0] < 0

    change(s, 'up', [2])
    assert [ranks(s)[key] for key in (4, 2, 1, 3, 5)] == [1, 2, 3, 4, 5]
    change(s, 'down', [2])
    assert [ranks(s)[key] for key in (4, 1, 2, 3, 5)] == [1, 2, 3, 4, 5]

    change(s, 'remove', [1])
    result = ranks(s)
    assert {key: result[key] for key in (4, 2, 3, 5)} == {4: 1, 2: 2, 3: 3, 5: 4}
    assert result[1] is None
    with s.catalog() as c:
        positions = [row[0] for row in c.db.execute(
            'SELECT position FROM stack_members WHERE stack_id=(SELECT stack_id FROM stack_members '
            'WHERE photo_id=4) ORDER BY position,photo_id')]
    assert positions[0] < 0 and any(right - left > 1 for left, right in zip(positions, positions[1:]))


def test_split_and_virtual_copy_recompute_each_stack_ordinal(service):
    s = service
    change(s, 'group', [1, 2, 3, 4, 5])
    change(s, 'expand', [1])
    change(s, 'split', [4, 2])
    result = ranks(s)
    assert {key: result[key] for key in (1, 2, 3, 4, 5)} == {
        1: 1, 2: 1, 3: 2, 4: 2, 5: 3,
    }
    change(s, 'split', [4])
    result = ranks(s)
    assert result[2] is None and result[4] is None

    change(s, 'unstack', [1])
    change(s, 'group', [1, 2])
    copied = s.dispatch('create_virtual_copies', {
        'targets': [{'photo_id': 1, 'expected_revision': 0, 'expected_metadata_revision': 0}],
    })['photos'][0]['id']
    result = ranks(s)
    assert {key: result[key] for key in (1, copied, 2)} == {1: 1, copied: 2, 2: 3}


def test_auto_stacks_start_each_member_sequence_at_one(service):
    s = service
    folder = str(Path(s.dispatch('get_photo', {'photo_id': 1})['path']).parent)
    capture_times = (0, 50_000, 300_000, 350_000, 600_000, 650_000)
    with s.catalog() as c:
        with c.db:
            c.db.executemany(
                "UPDATE photos SET taken_us=?,capture_clock='camera' WHERE id=?",
                [(taken, photo_id) for photo_id, taken in enumerate(capture_times, 1)],
            )
    plan = s.dispatch('preview_auto_stack', {'folder': folder, 'seconds': 0.1})
    s.dispatch('apply_auto_stack', {'folder': folder, 'seconds': 0.1, 'token': plan['token']})
    assert {key: ranks(s)[key] for key in (1, 3, 5)} == {1: 1, 3: 1, 5: 1}
    change(s, 'expand', [1, 3, 5])
    result = ranks(s)
    assert {key: result[key] for key in range(1, 7)} == {
        1: 1, 2: 2, 3: 1, 4: 2, 5: 1, 6: 2,
    }


def test_collection_ordinals_are_independent_of_folder_stack(service):
    s = service
    album = s.dispatch('save_collection', {
        'name': 'Independent order', 'kind': 'regular', 'photo_ids': [1, 2, 3],
    })['id']
    change(s, 'group', [1, 2, 3])
    change(s, 'expand', [1])
    change(s, 'group', [1, 3, 2], collection_id=album, active_id=3)
    change(s, 'expand', [3], collection_id=album)

    folder = ranks(s)
    collection = ranks(s, collection_id=album)
    assert {key: folder[key] for key in (1, 2, 3)} == {1: 1, 2: 2, 3: 3}
    assert {key: collection[key] for key in (1, 2, 3)} == {1: 2, 2: 3, 3: 1}


def test_tied_positions_use_photo_id_as_the_stable_order(service):
    s = service
    change(s, 'group', [1, 2, 3])
    change(s, 'expand', [1])
    with s.catalog() as c:
        with c.db:
            stack_id = c.db.execute('SELECT stack_id FROM stack_members WHERE photo_id=1').fetchone()[0]
            c.db.execute('UPDATE stack_members SET position=-7 WHERE stack_id=?', (stack_id,))
            Stacks(c).recalculate(stack_id)
    result = ranks(s)
    assert {key: result[key] for key in (1, 2, 3)} == {1: 1, 2: 2, 3: 3}
    with s.catalog() as c:
        assert c.db.execute('SELECT top_id FROM photo_stacks WHERE id=?', (stack_id,)).fetchone()[0] == 1


def test_raw_unstacked_and_smart_scope_rows_have_null_ordinals(service):
    s = service
    change(s, 'group', [1, 2, 3])
    raw = page(s, stacked=False)['photos']
    assert all(row['stack_ordinal'] is None for row in raw)

    smart = s.dispatch('save_collection', {'name': 'All photos', 'kind': 'smart'})['id']
    smart_rows = page(s, collection_id=smart)['photos']
    assert smart_rows and all(row['stack_ordinal'] is None for row in smart_rows)


def test_full_stack_ordinals_cross_pages_and_ignore_filter_subset(tmp_path):
    catalog = Catalog(tmp_path / 'catalog')
    recipe = json.dumps(Recipe().dict())
    with catalog.db:
        catalog.db.executemany(
            'INSERT INTO photos(path,name,bytes,mtime,recipe,created) VALUES(?,?,0,0,?,0)',
            [(str(tmp_path / f'{i:03}.png'), f'{i:03}.png', recipe) for i in range(130)],
        )
    stacks = Stacks(catalog)
    for members in (list(range(1, 61)), [1, *range(61, 120)], [1, *range(120, 131)]):
        stacks.change('group', members, stacks.revision())
    stacks.change('expand', [1], stacks.revision())

    pages = [catalog.filtered_page(offset, sort='name', descending=True) for offset in (0, 60, 120)]
    assert [row['stack_ordinal'] for rows in pages for row in rows] == list(range(1, 131))

    with catalog.db:
        catalog.db.executemany('UPDATE photos SET rating=5 WHERE id=?', [(photo_id,) for photo_id in (2, 63, 130)])
    filtered = catalog.filtered_page(0, filters={'rating_min': 5}, sort='imported', descending=False)
    assert [(row['id'], row['stack_ordinal']) for row in filtered] == [(2, 2), (63, 63), (130, 130)]
    catalog.close()


def test_ordinal_annotation_uses_bounded_grouped_prefix_work(tmp_path):
    member_count = 100_000
    catalog = Catalog(tmp_path / 'large-catalog')
    recipe = json.dumps(Recipe().dict())
    folder = str(tmp_path)
    with catalog.db:
        catalog.db.executemany(
            'INSERT INTO photos(path,name,bytes,mtime,recipe,created) VALUES(?,?,0,0,?,0)',
            ((str(tmp_path / f'{i:06}.jpg'), f'{i:06}.jpg', recipe) for i in range(member_count)),
        )
        stack_id = catalog.db.execute(
            "INSERT INTO photo_stacks(scope,folder,collapsed,top_id,size) VALUES('folder',?,0,1,?)",
            (folder, member_count),
        ).lastrowid
        catalog.db.executemany(
            'INSERT INTO stack_members(scope,photo_id,stack_id,position) VALUES(?,?,?,?)',
            (('folder', photo_id, stack_id, photo_id - 1) for photo_id in range(1, member_count + 1)),
        )

    first_position = 90_000
    rows = [{
        'id': position + 1,
        'stack_id': stack_id,
        'stack_position': position,
        'stack_top': 1,
    } for position in range(first_position, first_position + 60)]
    steps = [0]

    def progress():
        steps[0] += 1_000
        return 0

    catalog.db.set_progress_handler(progress, 1_000)
    try:
        annotated = Stacks(catalog).annotate_ordinals(rows, 'folder')
    finally:
        catalog.db.set_progress_handler(None, 0)
    assert [row['stack_ordinal'] for row in annotated] == list(range(first_position + 1, first_position + 61))
    assert steps[0] < 2_000_000
    catalog.close()

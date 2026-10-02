"""Collection and collection-set color labels over the portable catalog API.

Inputs: disposable current and genuine schema-32 catalogs plus revision-bound
label commands. Outputs: coverage for color assignment, flat filtered pages,
tree revisions, rollback, preservation and additive migration. No desktop
equivalence, custom label-set editing or performance timing claims.
"""
import hashlib
import json
import sqlite3

from PIL import Image
import jsonschema
import pytest

from lumaraw import catalog as catalog_module
from lumaraw.catalog import Catalog
from lumaraw.collections import Collections
from lumaraw.runtime import CATALOG_VERSION
from lumaraw.service import Service
from legacy_catalog import migrate_to, seed_photo


COLORS = ("none", "red", "yellow", "green", "blue", "purple")
DOMAIN_OR_SCHEMA_ERROR = (ValueError, jsonschema.ValidationError)


@pytest.fixture
def service(tmp_path):
    instance = Service(tmp_path / "catalog")
    try:
        yield instance
    finally:
        instance.close()


def create(service, name, kind="regular", parent=None, **extra):
    return service.dispatch("save_collection", {
        "name": name, "kind": kind, "parent_id": parent, **extra,
    })


def get(service, collection_id):
    return service.dispatch("get_collection", {"collection_id": collection_id})


def set_labels(service, collections, color):
    return service.dispatch("set_collection_labels", {
        "targets": [
            {"collection_id": row["id"], "expected_revision": row["revision"]}
            for row in collections
        ],
        "color_label": color,
    })


def rows_by_id(page):
    return {row["id"]: row for row in page["collections"]}


def test_labels_cover_regular_smart_and_sets_clear_and_leave_target_state_alone(service):
    state = service.dispatch("collection_state")
    quick = state["quick"]
    root = create(service, "Portfolio", "set")
    regular = create(service, "Finals", parent=root["id"])
    smart = create(service, "Rated", "smart", root["id"], rules={"rating_min": 4})
    service.dispatch("set_target_collection", {
        "collection_id": regular["id"], "expected_revision": state["revision"],
    })
    before = service.dispatch("collection_state")

    selected = [get(service, row["id"]) for row in (root, regular, smart)]
    result = set_labels(service, selected, "green")
    assert [row["id"] for row in result["collections"]] == [row["id"] for row in selected]
    assert result["tree_revision"] > before["tree_revision"]
    assert {row["color_label"] for row in result["collections"]} == {"green"}
    listed = rows_by_id(service.dispatch("list_collections", {"color_label": "green"}))
    assert listed[root["id"]]["parent_name"] is None
    assert listed[regular["id"]]["parent_name"] == "Portfolio"
    assert listed[smart["id"]]["parent_name"] == "Portfolio"

    after = service.dispatch("collection_state")
    assert after["revision"] == before["revision"]
    assert after["quick"]["id"] == quick["id"]
    assert after["target"]["id"] == regular["id"]
    assert after["target"]["revision"] == get(service, regular["id"])["revision"]
    assert set(rows_by_id(service.dispatch("list_collections", {"color_label": "green"}))) == {
        root["id"], regular["id"], smart["id"],
    }

    labeled_tree_revision = after["tree_revision"]
    unchanged = [get(service, row["id"]) for row in (root, regular, smart)]
    set_labels(service, unchanged, "green")
    no_op = service.dispatch("collection_state")
    assert no_op["tree_revision"] == labeled_tree_revision
    assert no_op["revision"] == before["revision"]
    assert {row["id"]: get(service, row["id"])["revision"] for row in unchanged} == {
        row["id"]: row["revision"] for row in unchanged
    }

    clear_targets = [get(service, row["id"]) for row in (root, regular, smart)]
    set_labels(service, clear_targets, "none")
    cleared = service.dispatch("collection_state")
    assert cleared["tree_revision"] > no_op["tree_revision"]
    assert service.dispatch("list_collections", {"color_label": "green"})["total"] == 0
    assert set(rows_by_id(service.dispatch("list_collections", {"color_label": "none"}))) >= {
        root["id"], regular["id"], smart["id"],
    }
    assert quick["color_label"] == "none"


def test_batch_validates_all_targets_before_mutating_and_touches_ancestor_union(service):
    parent = create(service, "Parent", "set")
    child = create(service, "Child", parent=parent["id"])
    other = create(service, "Other")

    set_labels(service, [get(service, parent["id"])], "red")
    parent_red = get(service, parent["id"])
    child_before = get(service, child["id"])
    tree_before = service.dispatch("collection_state")["tree_revision"]

    # The parent already has this label, but it is still a changed ancestor of
    # the child and must be invalidated once as part of the same logical batch.
    set_labels(service, [parent_red, child_before], "red")
    parent_after = get(service, parent["id"])
    child_after = get(service, child["id"])
    assert parent_after["color_label"] == child_after["color_label"] == "red"
    assert parent_after["revision"] == parent_red["revision"] + 1
    assert child_after["revision"] == child_before["revision"] + 1
    assert service.dispatch("collection_state")["tree_revision"] > tree_before

    current_parent = get(service, parent["id"])
    stale_other = get(service, other["id"])
    set_labels(service, [stale_other], "yellow")
    before_rows = [get(service, row["id"]) for row in (parent, child, other)]
    before_tree = service.dispatch("collection_state")["tree_revision"]
    with pytest.raises(ValueError, match="conflict|reload|revision"):
        set_labels(service, [current_parent, stale_other], "blue")
    assert [get(service, row["id"]) for row in (parent, child, other)] == before_rows
    assert service.dispatch("collection_state")["tree_revision"] == before_tree

    for invalid_color in ("orange", "", None):
        with pytest.raises(DOMAIN_OR_SCHEMA_ERROR):
            set_labels(service, [get(service, row["id"]) for row in (parent, child)], invalid_color)
        assert [get(service, row["id"]) for row in (parent, child)] == before_rows[:2]

    state = service.dispatch("collection_state")
    quick = state["quick"]
    with pytest.raises(ValueError, match="Quick|quick"):
        set_labels(service, [get(service, parent["id"]), quick], "blue")
    with pytest.raises(ValueError, match="unique|duplicate|distinct"):
        set_labels(service, [get(service, parent["id"]), get(service, parent["id"])], "blue")
    assert [get(service, row["id"]) for row in (parent, child, other)] == before_rows
    assert service.dispatch("collection_state")["tree_revision"] == before_tree


def test_mid_batch_sql_failure_rolls_back_targets_ancestors_and_tree_revision(service):
    root = create(service, "Root", "set")
    first = create(service, "First", parent=root["id"])
    second = create(service, "Second", parent=root["id"])
    before_rows = [get(service, row["id"]) for row in (root, first, second)]
    before_tree = service.dispatch("collection_state")["tree_revision"]
    with service.catalog() as catalog:
        with catalog.db:
            catalog.db.execute(
                "CREATE TRIGGER fail_second_collection_label "
                "BEFORE UPDATE OF color_label ON collections "
                f"WHEN OLD.id={second['id']} BEGIN SELECT RAISE(ABORT,'simulated mid-batch failure'); END"
            )

    with pytest.raises(sqlite3.IntegrityError, match="simulated mid-batch failure"):
        set_labels(service, [get(service, first["id"]), get(service, second["id"])], "red")

    assert [get(service, row["id"]) for row in (root, first, second)] == before_rows
    assert service.dispatch("collection_state")["tree_revision"] == before_tree
    with service.catalog() as catalog:
        with catalog.db:
            catalog.db.execute("DROP TRIGGER fail_second_collection_label")


def test_label_mutations_preserve_full_photo_record_recipe_history_and_original(service, tmp_path):
    service.dispatch("queue_control", {"action": "pause"})
    path = tmp_path / "untouched-original.png"
    Image.new("RGB", (37, 23), (35, 90, 145)).save(path)
    original_digest = hashlib.sha256(path.read_bytes()).digest()
    result = service.dispatch("import_photos", {"paths": [str(path)]})
    assert result["imported"] == 1

    with service.catalog() as catalog:
        photo_id = catalog.db.execute("SELECT id FROM photos WHERE path=?", (str(path.resolve()),)).fetchone()[0]
        row = dict(catalog.db.execute("SELECT * FROM photos WHERE id=?", (photo_id,)).fetchone())
        recipe = json.loads(row["recipe"])
        recipe["exposure"] = 1.25
        with catalog.db:
            catalog.db.execute(
                "UPDATE photos SET recipe=?,metadata=?,title=?,caption=?,copyright=?,color_label=?,"
                "metadata_revision=metadata_revision+1 WHERE id=?",
                (json.dumps(recipe), json.dumps({"source": "regression"}), "Photo title", "Caption",
                 "Copyright", "purple", photo_id),
            )
        photo_before = tuple(catalog.db.execute("SELECT * FROM photos WHERE id=?", (photo_id,)).fetchone())
        source_id = catalog.db.execute("SELECT source_id FROM photos WHERE id=?", (photo_id,)).fetchone()[0]
        source_before = tuple(catalog.db.execute("SELECT * FROM photo_sources WHERE id=?", (source_id,)).fetchone())
        history_before = [tuple(row) for row in catalog.db.execute(
            "SELECT * FROM history WHERE photo_id=? ORDER BY id", (photo_id,)
        )]

    root = create(service, "Set", "set")
    collection = create(service, "Collection", parent=root["id"], photo_ids=[photo_id])
    set_labels(service, [get(service, collection["id"])], "blue")
    set_labels(service, [get(service, root["id"])], "green")
    assert get(service, collection["id"])["color_label"] == "blue"

    with service.catalog() as catalog:
        assert tuple(catalog.db.execute("SELECT * FROM photos WHERE id=?", (photo_id,)).fetchone()) == photo_before
        assert tuple(catalog.db.execute("SELECT * FROM photo_sources WHERE id=?", (source_id,)).fetchone()) == source_before
        assert [tuple(row) for row in catalog.db.execute(
            "SELECT * FROM history WHERE photo_id=? ORDER BY id", (photo_id,)
        )] == history_before
    assert hashlib.sha256(path.read_bytes()).digest() == original_digest


def test_filtered_collection_pages_are_flat_global_stable_and_exclude_quick(service):
    root = create(service, "Nested Set", "set")
    nested = create(service, "Nested Red", parent=root["id"])
    ordinary = [create(service, f"Album {index:03d}") for index in range(124)]
    targets = [get(service, row["id"]) for row in ordinary[:65]] + [get(service, nested["id"])]
    set_labels(service, targets[:60], "red")
    set_labels(service, targets[60:], "red")
    set_labels(service, [get(service, row["id"]) for row in ordinary[65:72]], "blue")

    first = service.dispatch("list_collections", {"color_label": "red"})
    second = service.dispatch("list_collections", {"color_label": "red", "offset": 60})
    assert first["total"] == second["total"] == 66
    assert first["page_size"] == second["page_size"] == 60
    assert first["offset"] == 0 and second["offset"] == 60
    first_rows = first["collections"]
    second_rows = second["collections"]
    assert len(first_rows) == 60 and len(second_rows) == 6
    assert {row["id"] for row in first_rows}.isdisjoint({row["id"] for row in second_rows})
    assert all(row["color_label"] == "red" for row in first_rows + second_rows)
    all_red_rows = first_rows + second_rows
    assert [(row["name"].casefold(), row["id"]) for row in all_red_rows] == sorted(
        (row["name"].casefold(), row["id"]) for row in all_red_rows
    )
    assert nested["id"] in {row["id"] for row in all_red_rows}
    assert rows_by_id({"collections": all_red_rows})[nested["id"]]["parent_id"] == root["id"]

    labeled = service.dispatch("list_collections", {"color_label": "labeled"})
    none = service.dispatch("list_collections", {"color_label": "none"})
    blue = service.dispatch("list_collections", {"color_label": "blue"})
    assert labeled["total"] == 73
    assert blue["total"] == 7
    assert all(row["color_label"] != "none" for row in labeled["collections"])
    assert all(row["color_label"] == "none" for row in none["collections"])
    assert all(row["kind"] != "quick" for page in (first, second, labeled, none, blue)
               for row in page["collections"])

    # Filter results span nested levels; the ordinary tree path remains intact.
    child_page = service.dispatch("list_collections", {"parent_id": root["id"]})
    assert [row["id"] for row in child_page["collections"]] == [nested["id"]]
    assert child_page["collections"][0]["parent_name"] == root["name"]

    # A parent rename updates flat-filter context without changing the child's
    # own revision or the target pointer/state revision.
    nested_before_rename = get(service, nested["id"])
    target_before = service.dispatch("collection_state")
    service.dispatch("set_target_collection", {
        "collection_id": nested["id"], "expected_revision": target_before["revision"],
    })
    target_state = service.dispatch("collection_state")
    current_root = get(service, root["id"])
    service.dispatch("save_collection", {
        "collection_id": root["id"], "expected_revision": current_root["revision"],
        "name": "Renamed Set", "kind": "set", "parent_id": None,
    })
    renamed_child = get(service, nested["id"])
    assert renamed_child["revision"] == nested_before_rename["revision"]
    current_state = service.dispatch("collection_state")
    assert current_state["revision"] == target_state["revision"]
    assert current_state["target"]["id"] == nested["id"]
    assert current_state["target"]["revision"] == nested_before_rename["revision"]
    refreshed_red = service.dispatch("list_collections", {"color_label": "red", "offset": 60})
    refreshed_nested = rows_by_id(refreshed_red)[nested["id"]]
    assert refreshed_nested["parent_name"] == "Renamed Set"

    with pytest.raises(DOMAIN_OR_SCHEMA_ERROR, match="parent|filter|flat"):
        service.dispatch("list_collections", {"parent_id": root["id"], "color_label": "red"})
    with pytest.raises(DOMAIN_OR_SCHEMA_ERROR):
        service.dispatch("list_collections", {"color_label": "orange"})


def test_duplicate_move_and_quick_save_have_explicit_label_behavior(service):
    root = create(service, "Original Set", "set")
    nested_set = create(service, "Inner Set", "set", root["id"])
    album = create(service, "Album", parent=nested_set["id"])
    smart = create(service, "Smart", "smart", root["id"], rules={"rating_min": 4})
    set_labels(service, [get(service, root["id"])], "purple")
    set_labels(service, [get(service, nested_set["id"]), get(service, album["id"])], "yellow")
    set_labels(service, [get(service, smart["id"])], "blue")

    # Copying a subtree preserves labels as local catalog metadata.
    root = get(service, root["id"])
    copied = service.dispatch("duplicate_collection", {
        "collection_id": root["id"], "expected_revision": root["revision"], "name": "Copy Set",
    })
    copied_root = get(service, copied["id"])
    assert copied_root["color_label"] == "purple"
    copied_children = service.dispatch("list_collections", {"parent_id": copied_root["id"]})["collections"]
    copied_inner = next(row for row in copied_children if row["kind"] == "set")
    copied_smart = next(row for row in copied_children if row["kind"] == "smart")
    copied_album = service.dispatch("list_collections", {"parent_id": copied_inner["id"]})["collections"][0]
    assert copied_inner["color_label"] == copied_album["color_label"] == "yellow"
    assert copied_smart["color_label"] == "blue"

    destination = create(service, "Destination", "set")
    album = get(service, album["id"])
    moved = service.dispatch("save_collection", {
        "collection_id": album["id"], "expected_revision": album["revision"],
        "name": album["name"], "kind": album["kind"], "parent_id": destination["id"],
        "rules": album["rules"], "match": album["match"],
    })
    assert moved["color_label"] == "yellow"
    assert moved["parent_id"] == destination["id"]

    state = service.dispatch("collection_state")
    saved = service.dispatch("quick_collection", {
        "action": "save", "name": "Saved Quick", "expected_revision": state["quick"]["revision"],
    })["saved"]
    assert saved["color_label"] == "none"
    with pytest.raises(ValueError, match="Quick|quick"):
        set_labels(service, [get(service, state["quick"]["id"])], "red")


def test_collection_state_poll_is_compact_and_independent_of_tree_labels(service):
    root = create(service, "Large Set", "set")
    with service.catalog() as catalog:
        store = Collections(catalog)
        with catalog.db:
            catalog.db.executemany(
                "INSERT INTO collections(name,kind,rules,match,parent_id,created) VALUES(?, 'regular', '{}', 'all', ?, 0)",
                [(f"Album {index:05d}", root["id"]) for index in range(500)],
            )
        statements = []
        catalog.db.set_trace_callback(statements.append)
        try:
            state = store.state()
        finally:
            catalog.db.set_trace_callback(None)
    assert isinstance(state["tree_revision"], int)
    assert state["quick"]["kind"] == "quick"
    assert not any("SELECT" in sql.upper() and "FROM COLLECTIONS WHERE KIND" in sql.upper()
                   for sql in statements)
    assert sum("FROM COLLECTIONS WHERE ID" in sql.upper() for sql in statements) <= 2


def test_collection_label_indexes_cover_count_and_bounded_ordered_pages(service):
    create(service, "Index Set", "set")
    with service.catalog() as catalog:
        db = catalog.db
        names = {row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name IN "
            "('collection_flat_name_color','collection_label_name','collection_labeled_name')"
        )}
        assert {
            "collection_flat_name_color", "collection_label_name", "collection_labeled_name",
        } <= names

        plans = (
            ("collection_flat_name_color", "SELECT id FROM collections WHERE kind!='quick' "
             "ORDER BY name COLLATE NOCASE,id LIMIT 60"),
            ("collection_label_name", "SELECT id FROM collections WHERE kind!='quick' AND color_label='red' "
             "ORDER BY name COLLATE NOCASE,id LIMIT 60"),
            ("collection_labeled_name", "SELECT id FROM collections WHERE kind!='quick' AND color_label!='none' "
             "ORDER BY name COLLATE NOCASE,id LIMIT 60"),
        )
        for index_name, query in plans:
            detail = " ".join(row[3] for row in db.execute("EXPLAIN QUERY PLAN " + query))
            assert index_name in detail
            assert len(db.execute(query).fetchall()) <= 60

        count_plan = " ".join(row[3] for row in db.execute(
            "EXPLAIN QUERY PLAN SELECT count(*) FROM collections "
            "WHERE kind!='quick' AND color_label='red'"
        ))
        assert "collection_label_name" in count_plan


def test_schema32_migration_is_additive_atomic_idempotent_and_preserves_dependents(
    tmp_path, monkeypatch,
):
    root = tmp_path / "schema32"
    first_path = tmp_path / "legacy-a.raw"
    second_path = tmp_path / "legacy-b.raw"
    first_path.write_bytes(b"a")
    second_path.write_bytes(b"b")

    with monkeypatch.context() as patch:
        patch.setattr(catalog_module, "migrate", lambda db: migrate_to(db, 32))
        catalog = Catalog(root)
        with catalog.db:
            quick_id = catalog.db.execute("SELECT quick_id FROM collection_state WHERE id=1").fetchone()[0]
            catalog.db.execute("ALTER TABLE collections ADD COLUMN user_note TEXT NOT NULL DEFAULT ''")
            catalog.db.execute("CREATE INDEX custom_collection_note ON collections(user_note)")
            catalog.db.execute("CREATE TABLE custom_collection_audit(collection_id INTEGER NOT NULL)")
            catalog.db.execute(
                "CREATE TRIGGER custom_collection_note_audit AFTER UPDATE OF user_note ON collections "
                "BEGIN INSERT INTO custom_collection_audit VALUES(NEW.id); END"
            )

            root_id = catalog.db.execute(
                "INSERT INTO collections(name,kind,rules,match,parent_id,created,user_note) "
                "VALUES('Root','set','{}','all',NULL,1,'root-note')"
            ).lastrowid
            child_id = catalog.db.execute(
                "INSERT INTO collections(name,kind,rules,match,parent_id,created,user_note) "
                "VALUES('Child','set','{}','all',?,2,'child-note')", (root_id,)
            ).lastrowid
            album_id = catalog.db.execute(
                "INSERT INTO collections(name,kind,rules,match,parent_id,created,user_note) "
                "VALUES('Album','regular','{}','all',?,3,'album-note')", (child_id,)
            ).lastrowid
            smart_id = catalog.db.execute(
                "INSERT INTO collections(name,kind,rules,match,parent_id,created,user_note) "
                "VALUES('Smart','smart',?,'any',?,4,'smart-note')",
                (json.dumps({"rating_min": 3}), root_id),
            ).lastrowid
            catalog.db.execute("UPDATE collection_state SET target_id=? WHERE id=1", (album_id,))
            photo_a = seed_photo(catalog.db, first_path)
            photo_b = seed_photo(catalog.db, second_path)
            catalog.db.executemany("INSERT INTO collection_photos VALUES(?,?)", [
                (album_id, photo_a), (album_id, photo_b),
            ])
            stack_id = catalog.db.execute(
                "INSERT INTO photo_stacks(scope,folder,collapsed,top_id,size) VALUES(?,?,1,?,2)",
                (f"collection:{album_id}", "", photo_a),
            ).lastrowid
            catalog.db.executemany("INSERT INTO stack_members VALUES(?,?,?,?)", [
                (f"collection:{album_id}", photo_a, stack_id, 0),
                (f"collection:{album_id}", photo_b, stack_id, 1),
            ])

        collection_columns = ("id", "name", "kind", "rules", "match", "revision", "created",
                             "parent_id", "user_note")
        old_collections = [tuple(row) for row in catalog.db.execute(
            "SELECT " + ",".join(collection_columns) + " FROM collections ORDER BY id"
        )]
        old_state = tuple(catalog.db.execute("SELECT * FROM collection_state WHERE id=1").fetchone())
        old_members = [tuple(row) for row in catalog.db.execute(
            "SELECT collection_id,photo_id FROM collection_photos ORDER BY collection_id,photo_id"
        )]
        old_stacks = [tuple(row) for row in catalog.db.execute("SELECT * FROM photo_stacks ORDER BY id")]
        old_stack_members = [tuple(row) for row in catalog.db.execute(
            "SELECT * FROM stack_members ORDER BY scope,photo_id"
        )]
        assert catalog.db.execute("PRAGMA user_version").fetchone()[0] == 32
        catalog.close()

    # Deny trigger creation after migration has begun. SQLite DDL, the new tree
    # state table and user_version must all roll back together.
    real_connect = sqlite3.connect
    denied = []

    def deny_migration_trigger(*args, **kwargs):
        db = real_connect(*args, **kwargs)

        def authorize(action, arg1, arg2, database, trigger):
            if action == sqlite3.SQLITE_CREATE_TRIGGER:
                denied.append(arg1)
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        db.set_authorizer(authorize)
        return db

    with monkeypatch.context() as patch:
        patch.setattr(catalog_module.sqlite3, "connect", deny_migration_trigger)
        with pytest.raises(sqlite3.DatabaseError):
            Catalog(root)
    assert denied
    with sqlite3.connect(root / "catalog.sqlite") as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 32
        assert "color_label" not in {row[1] for row in db.execute("PRAGMA table_info(collections)")}
        assert db.execute("SELECT count(*) FROM collections").fetchone()[0] == len(old_collections)
        assert db.execute("SELECT count(*) FROM collection_photos").fetchone()[0] == len(old_members)

    catalog = Catalog(root)
    assert catalog.db.execute("PRAGMA user_version").fetchone()[0] == CATALOG_VERSION == 33
    assert tuple(catalog.db.execute(
        "SELECT quick_id,target_id,revision FROM collection_state WHERE id=1"
    ).fetchone()) == old_state[1:]
    assert [tuple(row) for row in catalog.db.execute(
        "SELECT " + ",".join(collection_columns) + " FROM collections ORDER BY id"
    )] == old_collections
    labels = dict(catalog.db.execute("SELECT id,color_label FROM collections"))
    assert set(labels) == {quick_id, root_id, child_id, album_id, smart_id}
    assert set(labels.values()) == {"none"}
    assert [tuple(row) for row in catalog.db.execute(
        "SELECT collection_id,photo_id FROM collection_photos ORDER BY collection_id,photo_id"
    )] == old_members
    assert [tuple(row) for row in catalog.db.execute("SELECT * FROM photo_stacks ORDER BY id")] == old_stacks
    assert [tuple(row) for row in catalog.db.execute(
        "SELECT * FROM stack_members ORDER BY scope,photo_id"
    )] == old_stack_members
    assert catalog.db.execute(
        "SELECT count(*) FROM sqlite_master WHERE type='index' AND name='custom_collection_note'"
    ).fetchone()[0] == 1
    assert catalog.db.execute(
        "SELECT count(*) FROM sqlite_master WHERE type='trigger' AND name='custom_collection_note_audit'"
    ).fetchone()[0] == 1
    with catalog.db:
        catalog.db.execute("UPDATE collections SET user_note='updated' WHERE id=?", (album_id,))
    assert catalog.db.execute("SELECT collection_id FROM custom_collection_audit").fetchone()[0] == album_id
    assert catalog.db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    catalog.close()

    # Reopening is a no-op: labels, revisions, identities and trigger count stay stable.
    catalog = Catalog(root)
    assert catalog.db.execute("PRAGMA user_version").fetchone()[0] == 33
    assert dict(catalog.db.execute("SELECT id,color_label FROM collections")) == labels
    assert catalog.db.execute(
        "SELECT count(*) FROM sqlite_master WHERE type='trigger' AND name LIKE 'collection_tree_%'"
    ).fetchone()[0] >= 1
    assert catalog.db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    catalog.close()

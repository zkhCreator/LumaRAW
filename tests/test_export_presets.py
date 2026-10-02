"""Saved export settings, shared/catalog storage and frozen queue snapshots.

Inputs: isolated catalog/shared-preset roots and revision-bound preset commands.
Outputs: coverage for exact settings, bounded name pages, storage tokens,
additive migration and real queued exports. Presets contain no photo or recipe
state; saved destinations are literal data and are never inspected by preset IO.
"""
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import time
import uuid

from PIL import Image, ImageCms
import jsonschema
import numpy as np
import pytest
import tifffile

from lumaraw import catalog as catalog_module
from lumaraw.catalog import Catalog
from lumaraw.color import icc_profile
from lumaraw.model import ExportOptions
from lumaraw.runtime import CATALOG_VERSION
from lumaraw.service import Service
from legacy_catalog import migrate_to, seed_photo


EXPORT_OPTIONS = {
    "space": "p3",
    "max_edge": 120,
    "quality": 94,
    "output_sharpen": 17.5,
    "name": "{stem}-deliverable-{space}",
    "priority": 4,
    "metadata": "catalog",
    "keyword_hierarchy": True,
}
EXPORT_SETTINGS = {"format": "jpeg", "options": EXPORT_OPTIONS, "destination": None}
DOMAIN_OR_SCHEMA_ERROR = (ValueError, jsonschema.ValidationError)


@pytest.fixture
def library(tmp_path, monkeypatch):
    preset_root = tmp_path / "preset-root"
    monkeypatch.setenv("LUMARAW_PRESETS_ROOT", str(preset_root))
    service = Service(tmp_path / "catalog", presets_root=preset_root)
    service.dispatch("queue_control", {"action": "pause"})
    try:
        yield service, preset_root
    finally:
        if not service.stopping.is_set():
            service.close()


def page(service, **query):
    return service.dispatch("list_export_presets", query)


def get(service, preset_id, revision=None):
    revision = page(service)["revision"] if revision is None else revision
    return service.dispatch("get_export_preset", {
        "preset_id": preset_id, "expected_revision": revision,
    })


def save(service, name, settings, preset_id=None, revision=None):
    params = {
        "name": name,
        "settings": copy.deepcopy(settings),
        "expected_revision": page(service)["revision"] if revision is None else revision,
    }
    if preset_id is not None:
        params["preset_id"] = preset_id
    return service.dispatch("save_export_preset", params)


def action(service, kind, preset_id=None, name=None, store_with_catalog=None, revision=None):
    params = {
        "action": kind,
        "expected_revision": page(service)["revision"] if revision is None else revision,
    }
    if preset_id is not None:
        params["preset_id"] = preset_id
    if name is not None:
        params["name"] = name
    if store_with_catalog is not None:
        params["store_with_catalog"] = store_with_catalog
    return service.dispatch("export_preset_action", params)


def default_options(**overrides):
    return {**ExportOptions().dict(), **overrides}


def wait_for_jobs(service, expected):
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        result = service.dispatch("list_jobs")
        if not any(job["state"] in ("pending", "running") for job in result["jobs"]):
            assert sum(result["counts"].values()) >= expected
            return result
        time.sleep(0.05)
    raise AssertionError("export queue did not finish within one minute")


def test_full_settings_roundtrip_defaults_and_payload_free_names(library):
    service, _ = library
    created = save(service, "旅行 %_ Preset", EXPORT_SETTINGS)
    preset_id = created["preset_id"]
    assert created["total"] == 1
    assert created["store_with_catalog"] is False
    assert len(created["revision"]) == 64
    assert set(created["revision"]) <= set("0123456789abcdef")

    listed = page(service, search="%_")
    assert listed["total"] == 1
    assert listed["offset"] == 0 and listed["page_size"] == 30
    assert listed["presets"] == [{"id": preset_id, "name": "旅行 %_ Preset"}]
    assert not any("settings" in row or "options" in row for row in listed["presets"])

    captured = get(service, preset_id, listed["revision"])
    assert captured["revision"] == listed["revision"]
    assert captured["preset"] == {
        "id": preset_id,
        "name": "旅行 %_ Preset",
        "settings": EXPORT_SETTINGS,
    }
    assert set(captured["preset"]["settings"]) == {"format", "options", "destination"}
    assert set(captured["preset"]["settings"]["options"]) == set(ExportOptions().dict())

    # Omitted option fields normalize to the complete current ExportOptions set.
    partial = {"format": "tiff16", "options": {"quality": 73}, "destination": None}
    partial_id = save(service, "Partial", partial)["preset_id"]
    expected = default_options(quality=73)
    assert get(service, partial_id)["preset"]["settings"] == {
        "format": "tiff16", "options": expected, "destination": None,
    }


@pytest.mark.parametrize("settings", [
    {"format": "png", "options": {}, "destination": None},
    {"format": "jpeg", "options": {}, "destination": "relative/output"},
    {"format": "jpeg", "options": {}, "destination": ""},
    {"format": "jpeg", "options": {}, "destination": "/tmp/out\x00escape"},
    {"format": "jpeg", "options": {}, "destination": None, "request_key": "bad"},
    {"format": "jpeg", "options": {"quality": 90, "unowned": True}, "destination": None},
    {"format": "jpeg", "options": {"space": "aces"}, "destination": None},
    {"format": "jpeg", "options": {"max_edge": 16001}, "destination": None},
    {"format": "jpeg", "options": {"quality": 0}, "destination": None},
    {"format": "jpeg", "options": {"output_sharpen": 151}, "destination": None},
    {"format": "jpeg", "options": {"priority": 10}, "destination": None},
    {"format": "jpeg", "options": {"metadata": "all-files"}, "destination": None},
    {"format": "jpeg", "options": {"keyword_hierarchy": 1}, "destination": None},
])
def test_invalid_settings_are_rejected_without_mutating_library(library, settings):
    service, _ = library
    before = page(service)
    with pytest.raises(DOMAIN_OR_SCHEMA_ERROR):
        save(service, "Rejected", settings)
    after = page(service)
    assert after["revision"] == before["revision"]
    assert after["presets"] == [] and after["total"] == 0


def test_saved_destination_is_literal_and_never_probed_or_created(library, tmp_path, monkeypatch):
    service, _ = library
    sentinel = Path("/lumaraw-export-preset-destination-" + uuid.uuid4().hex)
    destination = sentinel / "nested" / "deliverables"
    original = EXPORT_SETTINGS | {"destination": str(destination)}

    def touches(value):
        try:
            candidate = Path(os.fspath(value))
        except (TypeError, ValueError, OSError):
            return False
        return candidate == sentinel or sentinel in candidate.parents

    def prohibit(original_fn):
        def guarded(value, *args, **kwargs):
            if touches(value):
                raise AssertionError("preset IO inspected or wrote the saved export destination")
            return original_fn(value, *args, **kwargs)
        return guarded

    with monkeypatch.context() as patch:
        for method in ("stat", "exists", "is_dir", "mkdir", "resolve", "open"):
            patch.setattr(Path, method, prohibit(getattr(Path, method)))
        for method in ("stat", "mkdir", "makedirs"):
            patch.setattr(os, method, prohibit(getattr(os, method)))
        for method in ("exists", "isdir", "realpath"):
            patch.setattr(os.path, method, prohibit(getattr(os.path, method)))

        preset_id = save(service, "Literal Destination", original)["preset_id"]
        row = get(service, preset_id)["preset"]
        assert row["settings"]["destination"] == str(destination)
        assert row["settings"]["format"] == "jpeg"

    # A path containing lexical dot segments remains exactly the user value.
    lexical = str(tmp_path / "not-created" / ".." / "literal-output")
    literal_settings = {**EXPORT_SETTINGS, "destination": lexical}
    literal_id = save(service, "Lexical Path", literal_settings)["preset_id"]
    assert get(service, literal_id)["preset"]["settings"]["destination"] == lexical
    assert not (tmp_path / "not-created").exists()
    assert not sentinel.exists()


def test_casefold_unique_names_and_literal_bounded_search(library):
    service, _ = library
    preset_id = save(service, "Straße %_ Export", EXPORT_SETTINGS)["preset_id"]
    with pytest.raises(ValueError, match="name|exists|another"):
        save(service, "STRASSE %_ EXPORT", EXPORT_SETTINGS)
    found = page(service, search="%_")
    assert found["total"] == 1 and found["presets"][0]["id"] == preset_id
    assert page(service, search="strasse")["total"] == 1


def test_name_pages_are_payload_free_bounded_and_index_ordered(library):
    service, preset_root = library
    page(service)  # Initialize the isolated shared preset store.
    shared_path = preset_root / "export" / "presets.sqlite"
    settings = json.dumps(EXPORT_SETTINGS, ensure_ascii=False, separators=(",", ":"))
    entries = []
    for prefix, count in (("Album", 67), ("Camera", 9)):
        for index in range(count):
            name = f"{prefix} {index:03}"
            entries.append((str(uuid.uuid4()), name, name.casefold(), settings))
    with sqlite3.connect(shared_path) as db:
        db.executemany("INSERT INTO export_presets(id,name,normalized,settings) VALUES(?,?,?,?)", entries)
        db.execute("UPDATE export_preset_state SET revision=revision+1 WHERE id=1")

    first = page(service, offset=0)
    middle = page(service, offset=30)
    deep = page(service, offset=60)
    clamped = page(service, offset=1000)
    assert [len(first["presets"]), len(middle["presets"]), len(deep["presets"])] == [30, 30, 16]
    assert first["total"] == middle["total"] == deep["total"] == 76
    assert [first["offset"], middle["offset"], deep["offset"], clamped["offset"]] == [0, 30, 60, 60]
    all_rows = first["presets"] + middle["presets"] + deep["presets"]
    assert len({row["id"] for row in all_rows}) == 76
    assert all(set(row) == {"id", "name"} for row in all_rows)
    assert [row["name"] for row in all_rows] == sorted(row["name"] for row in all_rows)

    sparse = page(service, search="Camera 008", offset=30)
    assert sparse["total"] == 1 and sparse["offset"] == 0
    assert sparse["presets"] == [{"id": entries[-1][0], "name": "Camera 008"}]
    assert page(service, search="absent", offset=30)["offset"] == 0

    with sqlite3.connect(shared_path) as db:
        db.row_factory = sqlite3.Row
        page_plan = [row["detail"] for row in db.execute(
            "EXPLAIN QUERY PLAN SELECT id,name FROM export_presets "
            "ORDER BY normalized,id LIMIT 30 OFFSET 60"
        )]
        count_plan = [row["detail"] for row in db.execute(
            "EXPLAIN QUERY PLAN SELECT COUNT(*) FROM export_presets"
        )]
    # The unique normalized-name index also satisfies this order: normalized
    # names cannot tie. SQLite may prefer it to the explicit composite index.
    assert any("USING INDEX" in detail.upper() or "USING COVERING INDEX" in detail.upper()
               for detail in page_plan)
    assert all("TEMP B-TREE" not in detail.upper() for detail in page_plan + count_plan)


def test_revision_tokens_guard_get_save_rename_delete_and_mode_changes(library):
    service, _ = library
    empty = page(service)
    created = save(service, "First", EXPORT_SETTINGS, revision=empty["revision"])
    preset_id = created["preset_id"]
    after_create = created["revision"]
    with pytest.raises(ValueError, match="changed|refresh"):
        get(service, preset_id, empty["revision"])
    with pytest.raises(ValueError, match="changed|refresh"):
        save(service, "Stale Update", EXPORT_SETTINGS, preset_id=preset_id, revision=empty["revision"])
    with pytest.raises(ValueError, match="changed|refresh"):
        action(service, "rename", preset_id=preset_id, name="Stale Rename", revision=empty["revision"])
    with pytest.raises(ValueError, match="changed|refresh"):
        action(service, "delete", preset_id=preset_id, revision=empty["revision"])
    assert get(service, preset_id)["preset"]["name"] == "First"

    renamed = action(service, "rename", preset_id=preset_id, name="Second", revision=after_create)
    assert renamed["preset_id"] == preset_id
    after_rename = renamed["revision"]
    with pytest.raises(ValueError, match="changed|refresh"):
        action(service, "delete", preset_id=preset_id, revision=after_create)

    current = page(service)
    updated = save(service, "Second", EXPORT_SETTINGS | {"format": "tiff16"},
                   preset_id=preset_id, revision=current["revision"])
    assert updated["preset_id"] == preset_id
    assert get(service, preset_id)["preset"]["settings"]["format"] == "tiff16"
    with pytest.raises(ValueError, match="changed|refresh"):
        action(service, "delete", preset_id=preset_id, revision=after_rename)

    latest = page(service)
    deleted = action(service, "delete", preset_id=preset_id, revision=latest["revision"])
    assert deleted["total"] == 0 and deleted["presets"] == []
    with pytest.raises(ValueError, match="does not exist"):
        get(service, preset_id)

    current_token = page(service)["revision"]
    with pytest.raises(ValueError, match="does not exist"):
        action(service, "delete", preset_id=str(uuid.uuid4()), revision=current_token)
    with pytest.raises((ValueError, jsonschema.ValidationError), match="exactly|additional|unexpected"):
        service.dispatch("export_preset_action", {
            "action": "delete", "preset_id": str(uuid.uuid4()),
            "name": "Unexpected", "expected_revision": current_token,
        })
    assert page(service)["revision"] == current_token

    before_same_mode = page(service)
    noop = action(service, "storage", store_with_catalog=False, revision=before_same_mode["revision"])
    assert noop["store_with_catalog"] is False
    assert noop["revision"] == before_same_mode["revision"]


def test_shared_catalog_local_scope_tokens_no_copy_and_catalog_restore(library, tmp_path):
    first, preset_root = library
    second = Service(tmp_path / "second-catalog", presets_root=preset_root)
    try:
        first_initial = page(first)
        alternate_root = tmp_path / "alternate-preset-root"
        alternate = Service(first.root, presets_root=alternate_root)
        try:
            alternate_initial = page(alternate)
            assert alternate_initial["store_with_catalog"] is first_initial["store_with_catalog"] is False
            assert alternate_initial["revision"] != first_initial["revision"]
            with pytest.raises(ValueError, match="changed|refresh"):
                get(alternate, str(uuid.uuid4()), first_initial["revision"])
        finally:
            alternate.close()

        shared_id = save(first, "Shared", EXPORT_SETTINGS)["preset_id"]
        first_page = page(first)
        second_page = page(second)
        assert first_page["store_with_catalog"] is second_page["store_with_catalog"] is False
        assert first_page["revision"] != second_page["revision"]  # catalog-root-bound opaque tokens
        assert second_page["presets"] == [{"id": shared_id, "name": "Shared"}]
        with pytest.raises(ValueError, match="changed|refresh"):
            get(second, shared_id, first_page["revision"])

        stale_shared = page(first)["revision"]
        # A mutation through another catalog invalidates the shared revision.
        save(second, "Other Shared", EXPORT_SETTINGS)
        with pytest.raises(ValueError, match="changed|refresh"):
            get(first, shared_id, stale_shared)

        switch = action(first, "storage", store_with_catalog=True)
        assert switch["store_with_catalog"] is True
        assert switch["presets"] == []  # changing mode never copies shared rows
        assert page(second)["store_with_catalog"] is True
        assert page(second)["presets"] == []  # mode is shared; rows remain catalog-local

        local_id = save(first, "Local", EXPORT_SETTINGS)["preset_id"]
        assert page(first)["presets"] == [{"id": local_id, "name": "Local"}]
        assert page(second)["presets"] == []
        to_shared = action(first, "storage", store_with_catalog=False)
        assert {row["name"] for row in to_shared["presets"]} == {"Shared", "Other Shared"}
        assert get(first, shared_id)["preset"]["settings"] == EXPORT_SETTINGS
        assert {row["name"] for row in page(second)["presets"]} == {"Shared", "Other Shared"}

        # An unselected local-store mutation is still part of the opaque token.
        captured_shared = page(first)["revision"]
        action(first, "storage", store_with_catalog=True)
        with pytest.raises(ValueError, match="changed|refresh"):
            get(first, local_id, captured_shared)
        save(first, "Local Again", EXPORT_SETTINGS)
        action(first, "storage", store_with_catalog=False)
        with pytest.raises(ValueError, match="changed|refresh"):
            get(first, shared_id, captured_shared)

        action(first, "storage", store_with_catalog=True)
        local_names = {row["name"] for row in page(first)["presets"]}
        assert local_names == {"Local", "Local Again"}
        backup_path = tmp_path / "catalog-backup.sqlite"
        assert first.dispatch("backup_catalog", {"path": str(backup_path)})["backup"] == str(backup_path)
        restored_root = tmp_path / "restored-catalog"
        assert first.dispatch("restore_catalog", {
            "path": str(backup_path), "destination": str(restored_root),
        })["catalog"] == str(restored_root.resolve())
        restored = Service(restored_root, presets_root=preset_root)
        try:
            restored_page = page(restored)
            assert restored_page["store_with_catalog"] is True
            assert {row["name"] for row in restored_page["presets"]} == local_names
            assert get(restored, local_id)["preset"]["settings"] == EXPORT_SETTINGS
        finally:
            restored.close()
    finally:
        second.close()


def test_future_shared_storage_version_is_refused(library):
    service, preset_root = library
    page(service)  # create the isolated shared repository
    shared_path = preset_root / "export" / "presets.sqlite"
    service.close()
    with sqlite3.connect(shared_path) as db:
        db.execute("PRAGMA user_version=2")
    reopened = Service(service.root, presets_root=preset_root)
    try:
        with pytest.raises(ValueError, match="newer engine"):
            page(reopened)
    finally:
        reopened.close()


def test_genuine_schema33_upgrade_is_additive_atomic_and_idempotent(tmp_path, monkeypatch):
    root = tmp_path / "schema33"
    source = tmp_path / "legacy-source.png"
    Image.new("RGB", (20, 12), (70, 90, 110)).save(source)

    with monkeypatch.context() as patch:
        patch.setattr(catalog_module, "migrate", lambda db: migrate_to(db, 33))
        catalog = Catalog(root)
        with catalog.db:
            collection_id = catalog.db.execute(
                "INSERT INTO collections(name,kind,rules,match,parent_id,created,color_label) "
                "VALUES('Legacy Collection','regular','{}','all',NULL,1,'purple')"
            ).lastrowid
            photo_id = seed_photo(catalog.db, source)
            catalog.db.execute("INSERT INTO collection_photos VALUES(?,?)", (collection_id, photo_id))
            catalog.db.execute(
                "INSERT INTO jobs(photo_id,source,recipe,destination,format,created) "
                "VALUES(?,?,?,?,?,0)",
                (photo_id, str(source), "{}", str(tmp_path / "old-output"), "jpeg"),
            )
            catalog.db.execute("CREATE TABLE custom_export_migration_note(value TEXT NOT NULL)")
            catalog.db.execute("INSERT INTO custom_export_migration_note VALUES('retain')")
            catalog.db.execute("CREATE INDEX custom_export_migration_name ON collections(name)")
            catalog.db.execute(
                "CREATE TRIGGER custom_export_migration_trigger AFTER UPDATE OF name ON collections "
                "BEGIN INSERT INTO custom_export_migration_note VALUES(NEW.name); END"
            )
        old_photo = tuple(catalog.db.execute("SELECT * FROM photos WHERE id=?", (photo_id,)).fetchone())
        old_job = tuple(catalog.db.execute("SELECT id,photo_id,source,recipe,destination,format,state,created FROM jobs").fetchone())
        old_collection = tuple(catalog.db.execute(
            "SELECT id,name,kind,revision,parent_id,color_label FROM collections WHERE id=?", (collection_id,)
        ).fetchone())
        old_tree_revision = catalog.db.execute(
            "SELECT revision FROM collection_tree_state WHERE id=1"
        ).fetchone()[0]
        assert catalog.db.execute("PRAGMA user_version").fetchone()[0] == 33
        catalog.close()

    # Deny the second new table after the migration creates its local state row;
    # the complete migration must roll back to genuine schema 33.
    real_connect = sqlite3.connect
    denied = []

    def deny_export_table(*args, **kwargs):
        db = real_connect(*args, **kwargs)

        def authorize(action_code, name, detail, database, trigger):
            if action_code == sqlite3.SQLITE_CREATE_TABLE and name == "export_presets":
                denied.append(name)
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        db.set_authorizer(authorize)
        return db

    with monkeypatch.context() as patch:
        patch.setattr(catalog_module.sqlite3, "connect", deny_export_table)
        with pytest.raises(sqlite3.DatabaseError):
            Catalog(root)
    assert denied == ["export_presets"]
    with sqlite3.connect(root / "catalog.sqlite") as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 33
        assert not db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='export_preset_state'"
        ).fetchone()
        assert not db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='export_presets'"
        ).fetchone()
        assert tuple(db.execute("SELECT * FROM photos WHERE id=?", (photo_id,)).fetchone()) == old_photo
        assert tuple(db.execute(
            "SELECT id,photo_id,source,recipe,destination,format,state,created FROM jobs"
        ).fetchone()) == old_job
        assert tuple(db.execute(
            "SELECT id,name,kind,revision,parent_id,color_label FROM collections WHERE id=?", (collection_id,)
        ).fetchone()) == old_collection

    catalog = Catalog(root)
    assert catalog.db.execute("PRAGMA user_version").fetchone()[0] == CATALOG_VERSION
    assert tuple(catalog.db.execute("SELECT * FROM photos WHERE id=?", (photo_id,)).fetchone()) == old_photo
    assert tuple(catalog.db.execute(
        "SELECT id,photo_id,source,recipe,destination,format,state,created FROM jobs"
    ).fetchone()) == old_job
    assert tuple(catalog.db.execute(
        "SELECT id,name,kind,revision,parent_id,color_label FROM collections WHERE id=?", (collection_id,)
    ).fetchone()) == old_collection
    assert catalog.db.execute(
        "SELECT revision FROM collection_tree_state WHERE id=1"
    ).fetchone()[0] == old_tree_revision
    assert catalog.db.execute(
        "SELECT value FROM custom_export_migration_note"
    ).fetchone()[0] == "retain"
    assert catalog.db.execute(
        "SELECT count(*) FROM sqlite_master WHERE type='index' AND name='custom_export_migration_name'"
    ).fetchone()[0] == 1
    assert catalog.db.execute(
        "SELECT count(*) FROM sqlite_master WHERE type='trigger' AND name='custom_export_migration_trigger'"
    ).fetchone()[0] == 1
    with catalog.db:
        catalog.db.execute("UPDATE collections SET name='Updated' WHERE id=?", (collection_id,))
    assert catalog.db.execute(
        "SELECT value FROM custom_export_migration_note ORDER BY rowid DESC LIMIT 1"
    ).fetchone()[0] == "Updated"
    catalog.close()

    catalog = Catalog(root)
    assert catalog.db.execute("PRAGMA user_version").fetchone()[0] == CATALOG_VERSION
    assert catalog.db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert catalog.db.execute("SELECT count(*) FROM export_presets").fetchone()[0] == 0
    catalog.close()


def test_resolved_preset_settings_freeze_export_jobs_and_keep_collision_behavior(library, tmp_path):
    service, _ = library
    rng = np.random.default_rng(217)
    pixels = rng.integers(0, 256, (160, 240, 3), dtype=np.uint8)
    original = tmp_path / "pattern.png"
    Image.fromarray(pixels, "RGB").save(original)
    original_digest = hashlib.sha256(original.read_bytes()).digest()
    service.dispatch("import_photos", {"paths": [str(original)]})
    photo_id = service.dispatch("list_photos")["photos"][0]["id"]
    destination = tmp_path / "exports"

    high_settings = {
        "format": "jpeg",
        "options": default_options(space="p3", max_edge=120, quality=96,
                                    output_sharpen=0, name="Collision", priority=3),
        "destination": str(destination),
    }
    preset_id = save(service, "Frozen Delivery", high_settings)["preset_id"]
    resolved_high = get(service, preset_id)["preset"]["settings"]

    def enqueue(settings, key):
        return service.dispatch("enqueue_exports", {
            "photo_ids": [photo_id],
            "destination": settings["destination"],
            "format": settings["format"],
            "options": settings["options"],
            "request_key": key,
        })["job_ids"][0]

    first_job = enqueue(resolved_high, "preset-high-1")
    collision_job = enqueue(resolved_high, "preset-high-2")
    frozen_first = service.dispatch("get_job", {"job_id": first_job})
    frozen_collision = service.dispatch("get_job", {"job_id": collision_job})
    assert frozen_first["format"] == "jpeg"
    assert frozen_first["options"] == resolved_high["options"]
    assert frozen_first["destination"] == resolved_high["destination"]

    updated_settings = {
        "format": "tiff16",
        "options": default_options(space="p3", max_edge=120, quality=91,
                                    output_sharpen=2, name="Tiff Preset", priority=2),
        "destination": str(destination),
    }
    save(service, "Frozen Delivery", updated_settings, preset_id=preset_id)
    resolved_tiff = get(service, preset_id)["preset"]["settings"]
    tiff_job = enqueue(resolved_tiff, "preset-tiff")
    low_settings = {
        **resolved_high,
        "options": {**resolved_high["options"], "quality": 25, "name": "Low Quality"},
    }
    low_job = enqueue(low_settings, "preset-low-quality")
    frozen_tiff = service.dispatch("get_job", {"job_id": tiff_job})
    action(service, "delete", preset_id=preset_id)
    assert page(service)["total"] == 0
    assert service.dispatch("get_job", {"job_id": first_job}) == frozen_first
    assert service.dispatch("get_job", {"job_id": collision_job}) == frozen_collision
    assert service.dispatch("get_job", {"job_id": tiff_job}) == frozen_tiff
    assert service.dispatch("get_job", {"job_id": low_job})["options"]["quality"] == 25
    assert hashlib.sha256(original.read_bytes()).digest() == original_digest

    service.dispatch("queue_control", {"action": "resume"})
    result = wait_for_jobs(service, 4)
    jobs = {job["id"]: job for job in result["jobs"]}
    assert len(jobs) == 4
    assert all(job["state"] == "done" for job in jobs.values())
    high_path = Path(jobs[first_job]["output"])
    collision_path = Path(jobs[collision_job]["output"])
    tiff_path = Path(jobs[tiff_job]["output"])
    low_path = Path(jobs[low_job]["output"])
    assert high_path.name == "Collision.jpg"
    assert collision_path.name == "Collision-1.jpg"
    assert high_path.exists() and collision_path.exists() and low_path.exists() and tiff_path.exists()
    with Image.open(high_path) as rendered:
        assert rendered.format == "JPEG" and rendered.size == (120, 80)
        profile = rendered.info.get("icc_profile")
        assert profile
        ImageCms.ImageCmsProfile(io.BytesIO(profile))
        assert profile == icc_profile("p3")
    assert high_path.stat().st_size > low_path.stat().st_size
    with tifffile.TiffFile(tiff_path) as rendered:
        assert rendered.asarray().shape == (80, 120, 3)
        assert rendered.asarray().dtype == np.uint16
        assert rendered.pages[0].tags[34675].value == icc_profile("p3")
    assert service.dispatch("get_job", {"job_id": tiff_job})["format"] == "tiff16"
    assert hashlib.sha256(original.read_bytes()).digest() == original_digest

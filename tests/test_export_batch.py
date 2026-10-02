"""Atomic multi-preset export batches and durable job summaries.

Inputs: isolated catalogs, generated raster originals, captured export presets,
and explicit batch requests. Outputs: evidence for revision-bound capture,
transactional immutable jobs, bounded history, safe naming, queue controls,
migration, backup/restore, and actual worker output. Batches never rewrite
originals, saved presets, Develop recipes, or Previous export settings.
"""
import hashlib
import json
import sqlite3
import threading
import time
from pathlib import Path

from PIL import Image
import jsonschema
import pytest

from lumaraw import catalog as catalog_module
from lumaraw import render
from lumaraw.catalog import Catalog
from lumaraw.model import ExportOptions, Recipe
from lumaraw.runtime import CATALOG_VERSION
from lumaraw.service import Service
from legacy_catalog import migrate_to, seed_job, seed_photo


DOMAIN_OR_SCHEMA_ERROR = (ValueError, jsonschema.ValidationError)


@pytest.fixture
def library(tmp_path, monkeypatch):
    preset_root = tmp_path / "presets"
    monkeypatch.setenv("LUMARAW_PRESETS_ROOT", str(preset_root))
    service = Service(tmp_path / "catalog", presets_root=preset_root)
    service.dispatch("queue_control", {"action": "pause"})
    try:
        yield service, tmp_path, preset_root
    finally:
        if not service.stopping.is_set():
            service.close()


def options(**overrides):
    return {**ExportOptions().dict(), **overrides}


def settings(destination=None, *, fmt="jpeg", **option_overrides):
    return {
        "format": fmt,
        "options": options(**option_overrides),
        "destination": None if destination is None else str(destination),
    }


def save_preset(service, name, preset_settings, preset_id=None):
    params = {
        "name": name,
        "settings": preset_settings,
        "expected_revision": service.dispatch("list_export_presets")["revision"],
    }
    if preset_id is not None:
        params["preset_id"] = preset_id
    return service.dispatch("save_export_preset", params)


def rename_preset(service, preset_id, name):
    return service.dispatch("export_preset_action", {
        "action": "rename",
        "preset_id": preset_id,
        "name": name,
        "expected_revision": service.dispatch("list_export_presets")["revision"],
    })


def captured_presets(service, preset_ids):
    revision = service.dispatch("list_export_presets")["revision"]
    return service.dispatch("get_export_presets", {
        "preset_ids": list(preset_ids),
        "expected_revision": revision,
    })


def enqueue_batch(service, photo_ids, entries, request_key, *, revision=None,
                  parent_destination=None):
    if revision is None:
        revision = service.dispatch("list_export_presets")["revision"]
    params = {
        "photo_ids": list(photo_ids),
        "presets": [dict(entry) for entry in entries],
        "expected_revision": revision,
        "request_key": request_key,
    }
    if parent_destination is not None:
        params["parent_destination"] = str(parent_destination)
    return service.dispatch("enqueue_export_batch", params)


def get_batch(service, batch_id, offset=0):
    params = {"batch_id": batch_id}
    if offset:
        params["offset"] = offset
    return service.dispatch("get_export_batch", params)


def make_photos(root, count=2, size=(64, 48)):
    paths = []
    for index in range(count):
        path = root / f"photo-{index:04}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        color = (index % 256, (index * 17) % 256, (index * 43) % 256)
        Image.new("RGB", size, color).save(path)
        paths.append(path)
    return paths


def import_photos(service, paths):
    service.dispatch("import_photos", {"paths": [str(path) for path in paths]})
    with service.catalog() as catalog:
        return [row[0] for row in catalog.db.execute(
            "SELECT id FROM photos WHERE path IN (" + ",".join("?" for _ in paths) + ") ORDER BY id",
            [str(path.resolve()) for path in paths],
        )]


def batch_counts(service):
    with service.catalog() as catalog:
        return {
            "batches": catalog.db.execute("SELECT COUNT(*) FROM export_batches").fetchone()[0],
            "jobs": catalog.db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0],
            "receipts": catalog.db.execute("SELECT COUNT(*) FROM requests").fetchone()[0],
        }


def request_exists(service, key):
    with service.catalog() as catalog:
        return catalog.db.execute("SELECT 1 FROM requests WHERE key=?", (key,)).fetchone() is not None


def get_job(service, job_id):
    return service.dispatch("get_job", {"job_id": job_id})


def wait_for_batch_terminal(service, batch_id, timeout=90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = get_batch(service, batch_id)
        if not any(job["state"] in ("pending", "running") for job in result["jobs"]):
            return result
        time.sleep(0.05)
    raise AssertionError("export batch did not reach terminal states")


def test_captured_presets_freeze_jobs_and_batch_survives_preset_edits_and_backup(library):
    service, root, preset_root = library
    originals = make_photos(root / "originals", count=2)
    originals_digest = {path: hashlib.sha256(path.read_bytes()).digest() for path in originals}
    photo_ids = import_photos(service, originals)

    first_destination = root / "saved-first"
    second_destination = root / "saved-second"
    first_settings = settings(first_destination, fmt="jpeg", space="p3", max_edge=32,
                              quality=87, name="Frozen-{stem}", metadata="catalog")
    second_settings = settings(second_destination, fmt="tiff16", space="adobe", max_edge=24,
                               output_sharpen=4.5, name="Archive-{stem}", metadata="copyright")
    first_id = save_preset(service, "First delivery", first_settings)["preset_id"]
    second_id = save_preset(service, "Second archive", second_settings)["preset_id"]
    captured = captured_presets(service, [second_id, first_id])
    assert set(captured) == {"presets", "revision"}
    assert [row["id"] for row in captured["presets"]] == [second_id, first_id]
    assert captured["presets"][0]["settings"] == second_settings
    assert captured["presets"][1]["settings"] == first_settings

    keyword_id = service.dispatch("save_keyword", {
        "name": "Captured batch keyword",
        "expected_revision": service.dispatch("library_state")["keyword_revision"],
    })["keyword_id"]
    service.dispatch("edit_metadata", {
        "targets": [{"photo_id": photo_id,
                     "expected_metadata_revision": service.dispatch(
                         "get_photo", {"photo_id": photo_id})["metadata_revision"]}
                    for photo_id in photo_ids],
        "patch": {"title": "Submitted before batch"},
    })
    service.dispatch("keyword_membership", {
        "keyword_id": keyword_id,
        "expected_revision": service.dispatch("library_state")["keyword_revision"],
        "targets": [{"photo_id": photo_id,
                     "expected_metadata_revision": service.dispatch(
                         "get_photo", {"photo_id": photo_id})["metadata_revision"]}
                    for photo_id in photo_ids],
        "action": "add",
    })

    previous_params = {
        "photo_ids": [photo_ids[0]], "destination": str(root / "previous-output"),
        "format": "jpeg", "request_key": "batch-previous-baseline",
        "remember_previous": True,
    }
    service.dispatch("enqueue_exports", previous_params)
    previous = service.dispatch("get_previous_export")
    assert previous["available"] is True
    request = enqueue_batch(service, photo_ids, [
        {"preset_id": second_id},
        {"preset_id": first_id, "destination": str(root / "override-first")},
    ], "frozen-batch", revision=captured["revision"])
    assert request["queued"] == 4
    assert request["photo_count"] == 2 and request["preset_count"] == 2
    assert len(request["batch_id"]) == 36
    assert service.dispatch("get_previous_export") == previous

    # Recipe and metadata edits after acceptance cannot change the job snapshots.
    for photo_id in photo_ids:
        current = service.dispatch("get_photo", {"photo_id": photo_id})
        service.dispatch("edit_photo", {
            "photo_id": photo_id, "expected_revision": current["revision"],
            "patch": {"exposure": 1.25},
        })
        current = service.dispatch("get_photo", {"photo_id": photo_id})
        service.dispatch("edit_metadata", {
            "targets": [{"photo_id": photo_id,
                         "expected_metadata_revision": current["metadata_revision"]}],
            "patch": {"title": "Edited after batch", "caption": "Current metadata"},
        })

    service.dispatch("keyword_membership", {
        "keyword_id": keyword_id,
        "expected_revision": service.dispatch("library_state")["keyword_revision"],
        "targets": [{"photo_id": photo_id,
                     "expected_metadata_revision": service.dispatch(
                         "get_photo", {"photo_id": photo_id})["metadata_revision"]}
                    for photo_id in photo_ids],
        "action": "remove",
    })
    for photo_id in photo_ids:
        current = service.dispatch("get_photo", {"photo_id": photo_id})
        assert current["title"] == "Edited after batch"
        assert keyword_id not in current["keyword_ids"]

    first_update = save_preset(service, "First delivery", settings(
        root / "changed-first", fmt="tiff16", max_edge=9, name="Changed-{stem}"), first_id)
    assert first_update["preset_id"] == first_id
    latest_revision = service.dispatch("list_export_presets")["revision"]
    service.dispatch("export_preset_action", {
        "action": "delete", "preset_id": second_id, "expected_revision": latest_revision,
    })

    detail = get_batch(service, request["batch_id"])
    assert detail["batch"]["batch_id"] == request["batch_id"]
    assert detail["batch"]["revision"] == captured["revision"]
    assert detail["batch"]["destination_mode"] == "individual"
    assert detail["batch"]["parent_destination"] is None
    assert detail["total"] == 4 and detail["counts"] == {"pending": 4}
    assert [row["preset_id"] for row in detail["presets"]] == [second_id, first_id]
    assert detail["presets"] == [
        {"preset_id": second_id, "name": "Second archive", "format": "tiff16",
         "options": second_settings["options"], "destination": str(second_destination.resolve()),
         "subfolder": None, "filename_suffix": "Second archive"},
        {"preset_id": first_id, "name": "First delivery", "format": "jpeg",
         "options": first_settings["options"], "destination": str((root / "override-first").resolve()),
         "subfolder": None, "filename_suffix": "First delivery"},
    ]
    assert all("recipe" not in job and "metadata_snapshot" not in job and "export_metadata" not in job
               for job in detail["jobs"])
    assert all(job["batch_id"] == request["batch_id"] for job in detail["jobs"])
    assert {job["preset_name"] for job in detail["jobs"]} == {"First delivery", "Second archive"}
    assert {job["collision_suffix"] for job in detail["jobs"]} == {"First delivery", "Second archive"}

    captured_jobs = [get_job(service, row["id"]) for row in detail["jobs"]]
    placeholders = ",".join("?" for _ in captured_jobs)
    with service.catalog() as catalog:
        frozen_metadata = {
            job_id: json.loads(packet)
            for job_id, packet in catalog.db.execute(
                f"SELECT id,metadata_snapshot FROM jobs WHERE id IN ({placeholders})",
                [job["id"] for job in captured_jobs],
            )
        }
    for job in captured_jobs:
        expected = first_settings if job["preset_name"] == "First delivery" else second_settings
        assert job["format"] == expected["format"]
        assert job["options"] == expected["options"]
        assert job["recipe"]["exposure"] == 0
        assert "metadata_snapshot" not in job
        assert job["export_metadata"]["mode"] == expected["options"]["metadata"]
        snapshot = frozen_metadata[job["id"]]
        if expected["options"]["metadata"] == "catalog":
            assert snapshot["fields"]["title"] == "Submitted before batch"
            assert snapshot["keywords"] == ["Captured batch keyword"]
        else:
            assert snapshot["fields"].get("title", "") == ""
            assert snapshot["keywords"] == []
    assert service.dispatch("get_previous_export") == previous
    assert {path: hashlib.sha256(path.read_bytes()).digest() for path in originals} == originals_digest

    backup = root / "batch-backup.sqlite"
    service.dispatch("backup_catalog", {"path": str(backup)})
    restored_root = root / "restored"
    service.dispatch("restore_catalog", {"path": str(backup), "destination": str(restored_root)})
    restored = Service(restored_root, presets_root=preset_root)
    try:
        restored_detail = get_batch(restored, request["batch_id"])
        assert restored_detail["batch"] == detail["batch"]
        assert restored_detail["presets"] == detail["presets"]
        assert [row["id"] for row in restored_detail["jobs"]] == [row["id"] for row in detail["jobs"]]
    finally:
        restored.close()


def test_parent_destination_and_strict_subfolders_are_captured_atomically(library):
    service, root, _ = library
    photo_ids = import_photos(service, make_photos(root / "originals"))
    first_id = save_preset(service, "One", settings(None, name="{stem}"))["preset_id"]
    second_id = save_preset(service, "Two", settings(None, name="{stem}"))["preset_id"]
    token = service.dispatch("list_export_presets")["revision"]

    # Null saved destinations require a per-entry path in individual mode.
    before = batch_counts(service)
    no_destination = root / "no-destination"
    with pytest.raises(ValueError, match="destination"):
        enqueue_batch(service, [photo_ids[0]], [{"preset_id": first_id}], "missing-output", revision=token)
    assert batch_counts(service) == before
    assert not request_exists(service, "missing-output")

    # Parent mode captures one path plus distinct literal child components.
    parent = root / "旅行输出"
    result = enqueue_batch(service, photo_ids, [
        {"preset_id": first_id, "subfolder": "旅行-A", "filename_suffix": "旅行 A"},
        {"preset_id": second_id, "subfolder": "📷" * 60, "filename_suffix": "📷" * 30},
    ], "unicode-parent", revision=token, parent_destination=parent)
    detail = get_batch(service, result["batch_id"])
    assert detail["batch"]["destination_mode"] == "parent"
    assert detail["batch"]["parent_destination"] == str(parent.resolve())
    assert [row["destination"] for row in detail["presets"]] == [
        str((parent / "旅行-A").resolve()), str((parent / ("📷" * 60)).resolve()),
    ]
    assert [row["subfolder"] for row in detail["presets"]] == ["旅行-A", "📷" * 60]
    assert [row["filename_suffix"] for row in detail["presets"]] == ["旅行 A", "📷" * 30]

    invalid_parent = root / "must-not-exist"
    invalid_cases = [
        ([{"preset_id": first_id}], "missing-subfolder"),
        ([{"preset_id": first_id, "subfolder": ".."}], "dot-subfolder"),
        ([{"preset_id": first_id, "subfolder": "../escape"}], "traversal-subfolder"),
        ([{"preset_id": first_id, "subfolder": "a/b"}], "separator-subfolder"),
        ([{"preset_id": first_id, "subfolder": "bad."}], "trailing-dot-subfolder"),
        ([{"preset_id": first_id, "subfolder": "📷" * 64}], "oversized-unicode-subfolder"),
        ([{"preset_id": first_id, "subfolder": "safe", "destination": str(root / "mixed")}],
         "mixed-destination-mode"),
        ([{"preset_id": first_id, "subfolder": "safe", "filename_suffix": "../escape"}],
         "traversal-filename-suffix"),
        ([{"preset_id": first_id, "subfolder": "safe", "filename_suffix": "x" * 121}],
         "long-filename-suffix"),
        ([{"preset_id": first_id, "subfolder": "safe", "filename_suffix": "📷" * 31}],
         "oversized-unicode-filename-suffix"),
    ]
    for entry_list, key in invalid_cases:
        with pytest.raises(DOMAIN_OR_SCHEMA_ERROR):
            enqueue_batch(service, [photo_ids[0]], entry_list, key,
                          revision=token, parent_destination=invalid_parent)
        assert not request_exists(service, key)
    with pytest.raises(ValueError, match="subfolder|duplicate|unique"):
        enqueue_batch(service, [photo_ids[0]], [
            {"preset_id": first_id, "subfolder": "Å"},
            {"preset_id": second_id, "subfolder": "A\u030a"},
        ], "normalized-duplicate-folders", revision=token, parent_destination=invalid_parent)
    assert not request_exists(service, "normalized-duplicate-folders")
    assert not invalid_parent.exists()
    assert batch_counts(service)["batches"] == before["batches"] + 1

    # Individual destinations and parent subfolders cannot be mixed; normal mode
    # also rejects subfolder values rather than silently ignoring them.
    with pytest.raises(DOMAIN_OR_SCHEMA_ERROR):
        enqueue_batch(service, [photo_ids[0]], [
            {"preset_id": first_id, "destination": str(root / "individual"), "subfolder": "child"},
        ], "mixed-individual-fields", revision=token)
    assert not request_exists(service, "mixed-individual-fields")


def test_destination_preflight_rejects_escaping_symlink_and_non_directory_before_writes(library):
    service, root, _ = library
    photo_ids = import_photos(service, make_photos(root / "originals"))
    first_id = save_preset(service, "First", settings(None))["preset_id"]
    second_id = save_preset(service, "Second", settings(None))["preset_id"]
    token = service.dispatch("list_export_presets")["revision"]
    baseline = batch_counts(service)

    parent = root / "parent-with-symlink"
    parent.mkdir()
    outside = root / "outside-parent"
    outside.mkdir()
    (parent / "linked-child").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="symbolic|symlink|outside|escape|contain"):
        enqueue_batch(service, [photo_ids[0]], [
            {"preset_id": first_id, "subfolder": "linked-child"},
        ], "symlink-child-escape", revision=token, parent_destination=parent)
    assert batch_counts(service) == baseline
    assert not request_exists(service, "symlink-child-escape")
    assert list(outside.iterdir()) == []

    # Validate every individual destination before creating any missing sibling.
    would_be_created = root / "first-output-not-created"
    blocked_file = root / "second-output-is-file"
    blocked_file.write_bytes(b"existing non-directory")
    with pytest.raises(ValueError, match="directory|destination|file"):
        enqueue_batch(service, [photo_ids[0]], [
            {"preset_id": first_id, "destination": str(would_be_created)},
            {"preset_id": second_id, "destination": str(blocked_file)},
        ], "all-destinations-preflight", revision=token)
    assert batch_counts(service) == baseline
    assert not request_exists(service, "all-destinations-preflight")
    assert not would_be_created.exists()
    assert blocked_file.read_bytes() == b"existing non-directory"


def test_preset_revision_validation_and_batch_replay_precede_stale_check(library):
    service, root, _ = library
    photo_ids = import_photos(service, make_photos(root / "originals"))
    first_id = save_preset(service, "First", settings(root / "first", max_edge=32))["preset_id"]
    second_id = save_preset(service, "Second", settings(root / "second", max_edge=16))["preset_id"]
    token = service.dispatch("list_export_presets")["revision"]
    selected = service.dispatch("get_export_presets", {
        "preset_ids": [second_id, first_id], "expected_revision": token,
    })
    assert selected["revision"] == token
    assert [row["id"] for row in selected["presets"]] == [second_id, first_id]

    before = batch_counts(service)
    with pytest.raises(DOMAIN_OR_SCHEMA_ERROR):
        service.dispatch("get_export_presets", {
            "preset_ids": [first_id, first_id], "expected_revision": token,
        })
    with pytest.raises(ValueError, match="does not exist"):
        service.dispatch("get_export_presets", {
            "preset_ids": [first_id, "missing-preset"], "expected_revision": token,
        })
    with pytest.raises(ValueError, match="changed|refresh"):
        service.dispatch("get_export_presets", {
            "preset_ids": [first_id], "expected_revision": "0" * 64,
        })
    assert batch_counts(service) == before

    request_params = {
        "photo_ids": [photo_ids[0]],
        "presets": [{"preset_id": first_id}, {"preset_id": second_id}],
        "expected_revision": token,
        "request_key": "batch-replay-before-stale",
    }
    request = service.dispatch("enqueue_export_batch", request_params)
    rename_preset(service, first_id, "Changed after batch")
    assert service.dispatch("enqueue_export_batch", request_params) == request
    assert batch_counts(service)["batches"] == before["batches"] + 1
    with pytest.raises(ValueError, match="different export request"):
        service.dispatch("enqueue_export_batch", {
            **request_params, "photo_ids": [photo_ids[1]],
        })
    with pytest.raises(ValueError, match="different export request"):
        service.dispatch("enqueue_exports", {
            "photo_ids": [photo_ids[0]], "destination": str(root / "cross-method"),
            "format": "jpeg", "request_key": request_params["request_key"],
        })

    current = service.dispatch("list_export_presets")["revision"]
    with pytest.raises(ValueError, match="changed|refresh"):
        enqueue_batch(service, [photo_ids[0]], [{"preset_id": first_id}], "stale-batch",
                      revision=token)
    assert not request_exists(service, "stale-batch")
    with pytest.raises(ValueError, match="Photo does not exist"):
        enqueue_batch(service, [photo_ids[0], photo_ids[-1] + 100000],
                      [{"preset_id": first_id, "destination": str(root / "not-created")}],
                      "invalid-photo-target", revision=current)
    assert not (root / "not-created").exists()
    assert not request_exists(service, "invalid-photo-target")

    # Storage is part of the token. A shared snapshot cannot be consumed after
    # switching to an empty catalog-local store.
    service.dispatch("export_preset_action", {
        "action": "storage", "store_with_catalog": True,
        "expected_revision": current,
    })
    with pytest.raises(ValueError, match="changed|refresh"):
        enqueue_batch(service, [photo_ids[0]], [{"preset_id": second_id}], "stale-storage",
                      revision=current)
    assert not request_exists(service, "stale-storage")


def test_batch_inserts_jobs_presets_and_receipt_as_one_transaction(library):
    service, root, _ = library
    photo_ids = import_photos(service, make_photos(root / "originals"))
    first_id = save_preset(service, "First", settings(root / "first"))["preset_id"]
    second_id = save_preset(service, "Second", settings(root / "second"))["preset_id"]
    token = service.dispatch("list_export_presets")["revision"]
    baseline = batch_counts(service)

    def install_trigger(sql):
        with service.catalog() as catalog, catalog.db:
            catalog.db.execute(sql)

    def assert_unchanged(key):
        assert batch_counts(service) == baseline
        assert not request_exists(service, key)

    install_trigger(
        "CREATE TRIGGER fail_second_batch_job BEFORE INSERT ON jobs "
        f"WHEN NEW.photo_id={photo_ids[1]} "
        "BEGIN SELECT RAISE(ABORT,'injected batch job failure'); END"
    )
    with pytest.raises(sqlite3.DatabaseError, match="batch job failure"):
        enqueue_batch(service, photo_ids, [{"preset_id": first_id}, {"preset_id": second_id}],
                      "batch-second-job-failure", revision=token)
    install_trigger("DROP TRIGGER fail_second_batch_job")
    assert_unchanged("batch-second-job-failure")

    install_trigger(
        "CREATE TRIGGER fail_batch_receipt BEFORE INSERT ON requests "
        "WHEN NEW.key='batch-receipt-failure' "
        "BEGIN SELECT RAISE(ABORT,'injected batch receipt failure'); END"
    )
    with pytest.raises(sqlite3.DatabaseError, match="batch receipt failure"):
        enqueue_batch(service, photo_ids, [{"preset_id": first_id}, {"preset_id": second_id}],
                      "batch-receipt-failure", revision=token)
    install_trigger("DROP TRIGGER fail_batch_receipt")
    assert_unchanged("batch-receipt-failure")


def test_batch_pages_and_product_limit_deduplicates_photos_but_rejects_duplicate_presets(library):
    service, root, _ = library
    photo_ids = import_photos(service, make_photos(root / "originals", count=101, size=(4, 4)))
    preset_ids = [
        save_preset(service, f"Preset {index:02}", settings(root / f"saved-{index:02}",
                   metadata="none"))["preset_id"]
        for index in range(10)
    ]
    token = service.dispatch("list_export_presets")["revision"]
    entries = [{"preset_id": preset_id} for preset_id in preset_ids]

    with pytest.raises(DOMAIN_OR_SCHEMA_ERROR):
        enqueue_batch(service, photo_ids[:2], [entries[0], entries[0]], "duplicate-presets", revision=token)
    assert not request_exists(service, "duplicate-presets")

    # Repeated photo IDs preserve first-occurrence ordering but do not multiply
    # the job count. Exactly 100 photos × 10 presets reaches the product limit.
    accepted = enqueue_batch(service, [photo_ids[0], photo_ids[0], *photo_ids[1:100]], entries,
                             "batch-maximum-product", revision=token)
    assert accepted == {
        "batch_id": accepted["batch_id"], "queued": 1000,
        "photo_count": 100, "preset_count": 10,
    }
    detail = get_batch(service, accepted["batch_id"], 960)
    assert detail["total"] == 1000 and detail["offset"] == 960
    assert len(detail["jobs"]) == 40
    assert detail["page_size"] == 60
    assert len({job["id"] for job in detail["jobs"]}) == 40

    before = batch_counts(service)
    too_many_destination = root / "product-limit"
    over_limit_entries = [
        {"preset_id": preset_id, "subfolder": f"over-{index:02}"}
        for index, preset_id in enumerate(preset_ids)
    ]
    with pytest.raises(ValueError, match="1000 photo/preset jobs"):
        enqueue_batch(service, photo_ids, over_limit_entries, "batch-over-product-limit", revision=token,
                      parent_destination=too_many_destination)
    assert batch_counts(service) == before
    assert not too_many_destination.exists()
    assert not request_exists(service, "batch-over-product-limit")

    # More than sixty jobs are returned as two stable summary pages.
    photos_31 = photo_ids[:31]
    large = enqueue_batch(service, photos_31, entries[:2], "batch-sixty-two-jobs", revision=token)
    page0 = get_batch(service, large["batch_id"], 0)
    page1 = get_batch(service, large["batch_id"], 60)
    assert page0["total"] == 62 and page0["offset"] == 0 and len(page0["jobs"]) == 60
    assert page1["total"] == 62 and page1["offset"] == 60 and len(page1["jobs"]) == 2
    assert {row["id"] for row in page0["jobs"]}.isdisjoint({row["id"] for row in page1["jobs"]})

    # Thirty-row batch history pages include only bounded counts and summaries.
    for index in range(31):
        enqueue_batch(service, [photo_ids[index]], [entries[index % 10]], f"small-batch-{index:02}",
                      revision=token)
    first_page = service.dispatch("list_export_batches", {"offset": 0})
    next_page = service.dispatch("list_export_batches", {"offset": 30})
    assert first_page["total"] == next_page["total"] == 33
    assert len(first_page["batches"]) == 30 and len(next_page["batches"]) == 3
    all_summaries = first_page["batches"] + next_page["batches"]
    assert len({row["batch_id"] for row in all_summaries}) == 33
    assert all("counts" in row and sum(row["counts"].values()) == row["queued"] for row in all_summaries)


def test_batch_cancel_retry_isolated_and_cancels_an_active_worker(library, monkeypatch):
    service, root, _ = library
    photo_ids = import_photos(service, make_photos(root / "originals", count=3, size=(8, 8)))
    preset_id = save_preset(service, "Cancelable", settings(root / "output", metadata="none"))["preset_id"]
    token = service.dispatch("list_export_presets")["revision"]
    active_batch = enqueue_batch(service, photo_ids[:2], [{"preset_id": preset_id}],
                                 "active-batch", revision=token)
    other_batch = enqueue_batch(service, photo_ids[2:], [{"preset_id": preset_id}],
                                "other-batch", revision=token)

    started = threading.Event()

    class FakeStdin:
        def write(self, payload):
            self.payload = payload
            return len(payload)

        def close(self):
            return None

    class FakeProcess:
        def __init__(self, *args, **kwargs):
            self.stdin = FakeStdin()
            self.pid = 999999999
            self.return_code = None
            started.set()

        def poll(self):
            return self.return_code

        def kill(self):
            self.return_code = -9

        def wait(self, timeout=None):
            return self.return_code

    monkeypatch.setattr("lumaraw.service.subprocess.Popen", FakeProcess)
    service.dispatch("queue_control", {"action": "resume"})
    assert started.wait(10), "worker did not start"
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if service.active and service.active.get("operation") == "export":
            break
        time.sleep(0.01)
    assert service.active and service.active.get("operation") == "export"

    service.dispatch("queue_control", {"action": "pause"})
    cancelled = service.dispatch("queue_control", {
        "action": "cancel", "batch_id": active_batch["batch_id"],
    })
    assert cancelled["batch_id"] == active_batch["batch_id"]
    assert sum(cancelled["batch_counts"].values()) == active_batch["queued"]
    assert cancelled["batch_counts"] == {"cancelled": 2}

    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and service.active is not None:
        time.sleep(0.01)
    assert service.active is None
    active_state = get_batch(service, active_batch["batch_id"])
    other_state = get_batch(service, other_batch["batch_id"])
    assert active_state["counts"] == {"cancelled": 2}
    assert other_state["counts"] == {"pending": 1}

    retried = service.dispatch("queue_control", {
        "action": "retry_cancelled", "batch_id": active_batch["batch_id"],
    })
    assert retried["batch_id"] == active_batch["batch_id"]
    assert retried["batch_counts"] == {"pending": 2}
    assert get_batch(service, other_batch["batch_id"])["counts"] == {"pending": 1}
    with pytest.raises((ValueError, jsonschema.ValidationError)):
        service.dispatch("queue_control", {
            "action": "pause", "batch_id": active_batch["batch_id"],
        })
    with pytest.raises((ValueError, jsonschema.ValidationError)):
        service.dispatch("queue_control", {
            "action": "cancel", "job_id": 1, "batch_id": active_batch["batch_id"],
        })


def test_real_worker_renders_two_photos_two_presets_and_preserves_colliding_file(library):
    service, root, _ = library
    originals = make_photos(root / "originals", count=2)
    digests = {path: hashlib.sha256(path.read_bytes()).digest() for path in originals}
    photo_ids = import_photos(service, originals)
    destination = root / "batch-output"
    long_unicode_name = "影" * 100
    collision_suffix = "交付" * 20  # Exactly 120 UTF-8 bytes.
    first_id = save_preset(service, "Small", settings(
        destination, max_edge=32, name=long_unicode_name, quality=91, metadata="none"))["preset_id"]
    second_id = save_preset(service, "Tiny", settings(
        destination, max_edge=16, name=long_unicode_name, quality=82, metadata="none"))["preset_id"]
    token = service.dispatch("list_export_presets")["revision"]

    # Simulate an existing output. The batch must preserve it and create distinct
    # hard-link-published alternatives using its captured suffix and numeric fallback.
    # The 300-byte template stem is clipped at a UTF-8 boundary. This existing
    # base path forces the captured 120-byte Unicode suffix into the final name.
    existing = destination / ("影" * 83 + ".jpg")
    existing.parent.mkdir(parents=True)
    existing_bytes = b"keep the user's existing export"
    existing.write_bytes(existing_bytes)
    batch = enqueue_batch(service, photo_ids, [
        {"preset_id": first_id, "filename_suffix": collision_suffix},
        {"preset_id": second_id, "filename_suffix": collision_suffix},
    ], "real-batch-worker", revision=token)
    detail = get_batch(service, batch["batch_id"])
    assert batch["queued"] == 4 and detail["total"] == 4
    assert {row["collision_suffix"] for row in detail["jobs"]} == {collision_suffix}

    # Captured options drive the worker even after later presets could change.
    service.dispatch("queue_control", {"action": "resume"})
    finished = wait_for_batch_terminal(service, batch["batch_id"])
    jobs = finished["jobs"]
    assert len(jobs) == 4 and all(job["state"] == "done" for job in jobs)
    outputs = [Path(job["output"]) for job in jobs]
    assert len(set(outputs)) == 4 and all(path.is_file() for path in outputs)
    assert existing.read_bytes() == existing_bytes
    assert any(path.stem.endswith("-1") for path in outputs)
    assert all(("-" + collision_suffix) in path.stem for path in outputs)
    assert all(path.stem.startswith("影") for path in outputs)
    assert all(len(path.name.encode("utf-8")) <= 255 for path in outputs)
    sizes_by_suffix = {}
    for summary in jobs:
        job = get_job(service, summary["id"])
        sizes_by_suffix[job["options"]["max_edge"]] = Path(job["output"])
    with Image.open(sizes_by_suffix[32]) as rendered:
        assert rendered.format == "JPEG" and rendered.size == (32, 24)
    with Image.open(sizes_by_suffix[16]) as rendered:
        assert rendered.format == "JPEG" and rendered.size == (16, 12)
    assert all(hashlib.sha256(path.read_bytes()).digest() == digest for path, digest in digests.items())


@pytest.mark.parametrize("collision_suffix", ["../unsafe", "reserved/name", "📷" * 31])
def test_direct_renderer_rejects_unsafe_suffix_before_source_or_pixel_work(
        monkeypatch, collision_suffix):
    def pixels_must_not_start(*args, **kwargs):
        raise AssertionError("pixel decode began before collision suffix validation")

    monkeypatch.setattr(render, "base_image", pixels_must_not_start)
    with pytest.raises(ValueError, match="filename_suffix"):
        render.export_image(
            "/missing/source.raw", Recipe(), "/missing/destination", "jpeg", 1024,
            "batch-validation", collision_suffix=collision_suffix,
        )


def test_genuine_schema35_upgrade_rolls_back_batch_ddl_and_preserves_legacy_jobs(tmp_path, monkeypatch):
    root = tmp_path / "schema35"
    source = root / "original.png"
    source.parent.mkdir(parents=True)
    Image.new("RGB", (16, 12), (75, 95, 115)).save(source)

    with monkeypatch.context() as patch:
        patch.setattr(catalog_module, "migrate", lambda db: migrate_to(db, 35))
        catalog = Catalog(root)
        photo_id = seed_photo(catalog.db, source)
        old_job_id = seed_job(catalog.db, photo_id, root / "old-output", "jpeg")
        old_job = tuple(catalog.db.execute(
            "SELECT id,photo_id,source,recipe,destination,format,options,metadata_snapshot,export_metadata "
            "FROM jobs WHERE id=?", (old_job_id,)
        ).fetchone())
        assert catalog.db.execute("PRAGMA user_version").fetchone()[0] == 35
        before_columns = {row[1] for row in catalog.db.execute("PRAGMA table_info(jobs)")}
        assert not {"batch_id", "preset_name", "collision_suffix"} & before_columns
        catalog.close()

    real_connect = sqlite3.connect
    denied = []

    def deny_schema_version(*args, **kwargs):
        db = real_connect(*args, **kwargs)

        def authorize(action_code, name, detail, database, trigger):
            if action_code == sqlite3.SQLITE_PRAGMA and name == "user_version" and detail == "36":
                denied.append(f"{name}={detail}")
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        db.set_authorizer(authorize)
        return db

    with monkeypatch.context() as patch:
        patch.setattr(catalog_module.sqlite3, "connect", deny_schema_version)
        with pytest.raises(sqlite3.DatabaseError):
            Catalog(root)
    assert denied == ["user_version=36"]
    with sqlite3.connect(root / "catalog.sqlite") as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 35
        columns = {row[1] for row in db.execute("PRAGMA table_info(jobs)")}
        assert not {"batch_id", "preset_name", "collision_suffix"} & columns
        assert not db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='export_batches'"
        ).fetchone()
        assert not db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='export_batch_presets'"
        ).fetchone()
        assert tuple(db.execute(
            "SELECT id,photo_id,source,recipe,destination,format,options,metadata_snapshot,export_metadata "
            "FROM jobs WHERE id=?", (old_job_id,)
        ).fetchone()) == old_job

    catalog = Catalog(root)
    assert catalog.db.execute("PRAGMA user_version").fetchone()[0] == CATALOG_VERSION
    assert tuple(catalog.db.execute(
        "SELECT id,photo_id,source,recipe,destination,format,options,metadata_snapshot,export_metadata "
        "FROM jobs WHERE id=?", (old_job_id,)
    ).fetchone()) == old_job
    assert {row[1] for row in catalog.db.execute("PRAGMA table_info(jobs)")} >= {
        "batch_id", "preset_name", "collision_suffix",
    }
    assert catalog.db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    catalog.close()
    catalog = Catalog(root)
    assert catalog.db.execute("PRAGMA user_version").fetchone()[0] == CATALOG_VERSION
    assert catalog.db.execute("SELECT count(*) FROM export_batches").fetchone()[0] == 0
    catalog.close()

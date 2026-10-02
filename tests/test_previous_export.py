"""Catalog-local Export With Previous state and transactional queue behavior.

Inputs: isolated catalogs, generated raster originals, and explicit export
submissions. Outputs: coverage for accepted-session persistence, revision checks,
idempotent immutable jobs, migration, backup/restore, and worker outcomes. Previous
stores only effective settings; selections, recipes, metadata and request keys stay
in their existing queue/catalog contracts. Originals remain read-only.
"""
import hashlib
import json
import sqlite3
import time
from pathlib import Path

from PIL import Image
import jsonschema
import pytest

from lumaraw import catalog as catalog_module
from lumaraw.catalog import Catalog
from lumaraw.export_previous import state as previous_state
from lumaraw.model import ExportOptions
from lumaraw.runtime import CATALOG_VERSION
from lumaraw.service import Service
from legacy_catalog import migrate_to, seed_photo


def options(**overrides):
    return {**ExportOptions().dict(), **overrides}


@pytest.fixture
def library(tmp_path, monkeypatch):
    presets_root = tmp_path / "presets"
    monkeypatch.setenv("LUMARAW_PRESETS_ROOT", str(presets_root))
    service = Service(tmp_path / "catalog", presets_root=presets_root)
    service.dispatch("queue_control", {"action": "pause"})
    try:
        yield service, tmp_path
    finally:
        if not service.stopping.is_set():
            service.close()


def make_photo(root, name="original.png", size=(64, 48), color=(55, 105, 155)):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path)
    return path


def import_photo(service, path):
    service.dispatch("import_photos", {"paths": [str(path)]})
    row = next(row for row in service.dispatch("list_photos", {"stacked": False})["photos"]
               if row["path"] == str(path))
    return row["id"]


def manual_enqueue(service, photo_ids, destination, request_key, *, fmt="jpeg", export_options=None,
                   remember=None):
    params = {
        "photo_ids": list(photo_ids),
        "destination": str(destination),
        "format": fmt,
        "request_key": request_key,
    }
    if export_options is not None:
        params["options"] = dict(export_options)
    if remember is not None:
        params["remember_previous"] = remember
    return service.dispatch("enqueue_exports", params)


def previous_enqueue(service, photo_ids, revision, request_key):
    return service.dispatch("enqueue_previous_exports", {
        "photo_ids": list(photo_ids),
        "expected_revision": revision,
        "request_key": request_key,
    })


def stored_job(service, job_id):
    with service.catalog() as catalog:
        row = catalog.db.execute(
            "SELECT id,photo_id,source,recipe,destination,format,options,metadata_snapshot,export_metadata,state,output "
            "FROM jobs WHERE id=?", (job_id,)
        ).fetchone()
        assert row is not None
        result = dict(row)
    for key in ("recipe", "options", "metadata_snapshot", "export_metadata"):
        result[key] = json.loads(result[key])
    return result


def job_total(service):
    with service.catalog() as catalog:
        return catalog.db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]


def receipt_exists(service, request_key):
    with service.catalog() as catalog:
        return catalog.db.execute("SELECT 1 FROM requests WHERE key=?", (request_key,)).fetchone() is not None


def wait_for_terminal(service, job_id, timeout=45):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = service.dispatch("get_job", {"job_id": job_id})
        if job["state"] not in ("pending", "running"):
            return job
        time.sleep(0.05)
    raise AssertionError("previous export did not reach a terminal state")


def test_empty_previous_rejects_use_and_legacy_enqueue_receipt_survives_later_state(library):
    service, root = library
    photo_id = import_photo(service, make_photo(root))
    empty = service.dispatch("get_previous_export")
    assert empty == {"available": False, "revision": 0, "settings": None}

    with pytest.raises(ValueError, match="Previous"):
        previous_enqueue(service, [photo_id], empty["revision"], "empty-previous")
    assert job_total(service) == 0
    assert not receipt_exists(service, "empty-previous")
    assert service.dispatch("get_previous_export") == empty

    # Omitting the new flag preserves the pre-feature command and raw-params
    # receipt digest. Its replay remains valid even after a session is saved.
    legacy_args = {
        "photo_ids": [photo_id], "destination": str(root / "legacy-output"),
        "format": "jpeg", "options": {"quality": 61, "name": "Legacy-{stem}"},
        "request_key": "legacy-receipt",
    }
    legacy_result = service.dispatch("enqueue_exports", legacy_args)
    assert legacy_result["queued"] == 1
    assert service.dispatch("get_previous_export") == empty

    new_options = options(space="p3", max_edge=40, quality=73,
                          output_sharpen=3.5, name="Remember-{stem}", priority=4,
                          metadata="catalog", keyword_hierarchy=True)
    accepted = manual_enqueue(service, [photo_id], root / "remembered-output", "remembered-session",
                              fmt="tiff16", export_options=new_options, remember=True)
    assert accepted["queued"] == 1
    saved = service.dispatch("get_previous_export")
    assert saved["available"] is True and saved["revision"] == 1
    assert saved["settings"] == {
        "format": "tiff16", "options": new_options,
        "destination": str((root / "remembered-output").resolve()),
    }
    assert set(saved["settings"]["options"]) == set(ExportOptions().dict())

    assert service.dispatch("enqueue_exports", legacy_args) == legacy_result
    assert service.dispatch("get_previous_export") == saved
    assert job_total(service) == 2


def test_previous_enqueue_freezes_current_photo_and_metadata_and_replays_before_revision_check(library):
    service, root = library
    path = make_photo(root, size=(96, 64), color=(120, 75, 35))
    source_digest = hashlib.sha256(path.read_bytes()).digest()
    photo_id = import_photo(service, path)
    first_options = options(space="p3", max_edge=48, quality=83,
                            output_sharpen=2.5, name="First-{stem}", priority=2,
                            metadata="catalog", keyword_hierarchy=False)
    manual_enqueue(service, [photo_id], root / "first-output", "manual-first",
                   fmt="jpeg", export_options=first_options, remember=True)
    previous = service.dispatch("get_previous_export")

    current = service.dispatch("get_photo", {"photo_id": photo_id})
    service.dispatch("edit_photo", {
        "photo_id": photo_id, "expected_revision": current["revision"],
        "patch": {"exposure": 1.375},
    })
    current = service.dispatch("get_photo", {"photo_id": photo_id})
    service.dispatch("edit_metadata", {
        "targets": [{"photo_id": photo_id, "expected_metadata_revision": current["metadata_revision"]}],
        "patch": {"title": "Current title", "caption": "Current caption", "iptc": {"city": "Current city"}},
    })

    request = previous_enqueue(service, [photo_id], previous["revision"], "previous-photos")
    assert request["queued"] == 1
    first_previous_job = request["job_ids"][0]
    captured = stored_job(service, first_previous_job)
    assert captured["format"] == "jpeg"
    assert captured["destination"] == previous["settings"]["destination"]
    assert captured["options"] == previous["settings"]["options"]
    assert captured["recipe"]["exposure"] == 1.375
    fields = captured["metadata_snapshot"]["fields"]
    assert fields["title"] == "Current title"
    assert fields["caption"] == "Current caption"
    assert fields["iptc"]["city"] == "Current city"
    assert service.dispatch("get_previous_export") == previous
    assert hashlib.sha256(path.read_bytes()).digest() == source_digest

    next_options = options(space="srgb", max_edge=24, quality=69,
                           output_sharpen=7, name="Second-{stem}", priority=1,
                           metadata="copyright", keyword_hierarchy=False)
    manual_enqueue(service, [photo_id], root / "second-output", "manual-second",
                   fmt="tiff16", export_options=next_options, remember=True)
    newer = service.dispatch("get_previous_export")
    assert newer["revision"] == previous["revision"] + 1
    assert newer["settings"]["format"] == "tiff16"

    # An exact replay is answered from its old receipt before checking the now
    # stale Previous revision. Method and argument changes cannot reuse its key.
    assert previous_enqueue(service, [photo_id], previous["revision"], "previous-photos") == request
    with pytest.raises(ValueError, match="different export request"):
        previous_enqueue(service, [photo_id, photo_id], previous["revision"], "previous-photos")
    with pytest.raises(ValueError, match="different export request"):
        manual_enqueue(service, [photo_id], root / "cross-method", "previous-photos")
    assert job_total(service) == 3
    assert service.dispatch("get_previous_export") == newer

    fresh = previous_enqueue(service, [photo_id], newer["revision"], "previous-fresh")
    fresh_job = stored_job(service, fresh["job_ids"][0])
    assert fresh_job["format"] == "tiff16"
    assert fresh_job["destination"] == newer["settings"]["destination"]
    assert fresh_job["options"] == newer["settings"]["options"]
    assert service.dispatch("get_previous_export") == newer  # Reuse does not advance Previous.
    assert hashlib.sha256(path.read_bytes()).digest() == source_digest


def test_previous_revision_and_all_photo_validation_leave_jobs_and_receipts_untouched(library):
    service, root = library
    photo_id = import_photo(service, make_photo(root))
    options_value = options(quality=78, metadata="none")
    manual_enqueue(service, [photo_id], root / "accepted", "accepted", export_options=options_value,
                   remember=True)
    state = service.dispatch("get_previous_export")
    jobs = job_total(service)

    with pytest.raises(ValueError, match="changed|refresh"):
        previous_enqueue(service, [photo_id], state["revision"] - 1, "stale-previous")
    assert not receipt_exists(service, "stale-previous")
    assert job_total(service) == jobs
    assert service.dispatch("get_previous_export") == state

    with pytest.raises(jsonschema.ValidationError):
        service.dispatch("enqueue_previous_exports", {"photo_ids": [photo_id], "request_key": "missing-revision"})
    assert not receipt_exists(service, "missing-revision")
    assert job_total(service) == jobs
    assert service.dispatch("get_previous_export") == state

    with pytest.raises(ValueError, match="Photo does not exist"):
        previous_enqueue(service, [photo_id, photo_id + 100000], state["revision"], "partial-invalid")
    assert not receipt_exists(service, "partial-invalid")
    assert job_total(service) == jobs
    assert service.dispatch("get_previous_export") == state

    # Failed manual preflight cannot create a remembered session or destination.
    failed_destination = root / "must-not-be-created"
    with pytest.raises(ValueError, match="Photo does not exist"):
        manual_enqueue(service, [photo_id, photo_id + 100000], failed_destination, "manual-invalid",
                       export_options=options(quality=25), remember=True)
    assert not failed_destination.exists()
    assert not receipt_exists(service, "manual-invalid")
    assert job_total(service) == jobs
    assert service.dispatch("get_previous_export") == state


def test_manual_enqueue_settings_jobs_and_request_receipt_share_one_transaction(library):
    service, root = library
    photo_id = import_photo(service, make_photo(root))
    second_photo_id = import_photo(service, make_photo(root, "second.png", color=(85, 125, 65)))
    initial_options = options(quality=80, name="Baseline-{stem}")
    manual_enqueue(service, [photo_id], root / "baseline", "baseline",
                   export_options=initial_options, remember=True)
    original_state = service.dispatch("get_previous_export")

    # A new accepted job with identical canonical settings must not advance the
    # Previous revision even though the queue itself changes.
    same_settings = manual_enqueue(service, [photo_id], root / "baseline", "baseline-noop",
                                   export_options=initial_options, remember=True)
    assert same_settings["queued"] == 1
    assert service.dispatch("get_previous_export") == original_state
    original_jobs = job_total(service)

    def install_trigger(sql):
        with service.catalog() as catalog, catalog.db:
            catalog.db.execute(sql)

    def assert_unchanged(request_key):
        assert service.dispatch("get_previous_export") == original_state
        assert job_total(service) == original_jobs
        assert not receipt_exists(service, request_key)

    install_trigger(
        "CREATE TRIGGER fail_previous_export_job BEFORE INSERT ON jobs "
        f"WHEN NEW.photo_id={second_photo_id} BEGIN SELECT RAISE(ABORT,'injected enqueue failure'); END"
    )
    with pytest.raises(sqlite3.DatabaseError, match="injected enqueue failure"):
        manual_enqueue(service, [photo_id, second_photo_id], root / "job-failure", "job-failure",
                       export_options=options(quality=70), remember=True)
    install_trigger("DROP TRIGGER fail_previous_export_job")
    assert_unchanged("job-failure")

    install_trigger(
        "CREATE TRIGGER fail_previous_export_save BEFORE UPDATE ON previous_export_session "
        "BEGIN SELECT RAISE(ABORT,'injected Previous save failure'); END"
    )
    with pytest.raises(sqlite3.DatabaseError, match="Previous save failure"):
        manual_enqueue(service, [photo_id], root / "save-failure", "save-failure",
                       export_options=options(quality=69), remember=True)
    install_trigger("DROP TRIGGER fail_previous_export_save")
    assert_unchanged("save-failure")

    install_trigger(
        "CREATE TRIGGER fail_previous_export_receipt BEFORE INSERT ON requests "
        "WHEN NEW.key='receipt-failure' BEGIN SELECT RAISE(ABORT,'injected receipt failure'); END"
    )
    with pytest.raises(sqlite3.DatabaseError, match="receipt failure"):
        manual_enqueue(service, [photo_id], root / "receipt-failure", "receipt-failure",
                       export_options=options(quality=68), remember=True)
    install_trigger("DROP TRIGGER fail_previous_export_receipt")
    assert_unchanged("receipt-failure")

    install_trigger(
        "CREATE TRIGGER fail_previous_request_receipt BEFORE INSERT ON requests "
        "WHEN NEW.key='previous-receipt-failure' "
        "BEGIN SELECT RAISE(ABORT,'injected Previous receipt failure'); END"
    )
    with pytest.raises(sqlite3.DatabaseError, match="Previous receipt failure"):
        previous_enqueue(service, [photo_id, second_photo_id], original_state["revision"],
                         "previous-receipt-failure")
    install_trigger("DROP TRIGGER fail_previous_request_receipt")
    assert_unchanged("previous-receipt-failure")


def test_worker_failure_does_not_clear_or_advance_previous(library, monkeypatch):
    service, root = library
    path = make_photo(root)
    original_digest = hashlib.sha256(path.read_bytes()).digest()
    photo_id = import_photo(service, path)
    manual = manual_enqueue(service, [photo_id], root / "saved-output", "remember-before-failure",
                            export_options=options(max_edge=32, metadata="none"), remember=True)
    service.dispatch("queue_control", {"action": "cancel", "job_id": manual["job_ids"][0]})
    previous = service.dispatch("get_previous_export")
    queued = previous_enqueue(service, [photo_id], previous["revision"], "failing-worker-job")

    def fail_worker(request):
        raise RuntimeError("injected export worker failure")

    monkeypatch.setattr(service, "run_worker", fail_worker)
    service.dispatch("queue_control", {"action": "resume"})
    result = wait_for_terminal(service, queued["job_ids"][0])
    assert result["state"] == "failed"
    assert "injected export worker failure" in result["error"]
    assert service.dispatch("get_previous_export") == previous
    assert hashlib.sha256(path.read_bytes()).digest() == original_digest


def test_job_polling_reports_previous_revision_without_decoding_settings(library):
    service, root = library
    photo_id = import_photo(service, make_photo(root))
    manual_enqueue(service, [photo_id], root / "saved-output", "saved-for-poll",
                   export_options=options(metadata="none"), remember=True)
    previous = service.dispatch("get_previous_export")

    with service.catalog() as catalog, catalog.db:
        catalog.db.execute("UPDATE previous_export_session SET settings='not-json' WHERE id=1")

    summary = service.dispatch("list_jobs")["previous_export"]
    assert summary == {"available": True, "revision": previous["revision"]}
    with pytest.raises(ValueError, match="Stored Previous export settings are invalid"):
        service.dispatch("get_previous_export")
    assert job_total(service) == 1


def test_previous_exports_use_the_real_worker_and_preserve_original_bytes(library):
    service, root = library
    path = make_photo(root, size=(64, 48), color=(25, 95, 165))
    digest = hashlib.sha256(path.read_bytes()).digest()
    photo_id = import_photo(service, path)
    manual = manual_enqueue(service, [photo_id], root / "worker-output", "remember-for-worker",
                            fmt="jpeg", export_options=options(max_edge=32, quality=92,
                                name="Previous-{stem}", metadata="none"), remember=True)
    service.dispatch("queue_control", {"action": "cancel", "job_id": manual["job_ids"][0]})
    previous = service.dispatch("get_previous_export")
    queued = previous_enqueue(service, [photo_id], previous["revision"], "real-previous-worker")
    service.dispatch("queue_control", {"action": "resume"})
    job = wait_for_terminal(service, queued["job_ids"][0])
    assert job["state"] == "done"
    output = Path(job["output"])
    assert output.exists() and output.suffix.lower() == ".jpg"
    with Image.open(output) as rendered:
        assert rendered.format == "JPEG" and rendered.size == (32, 24)
        assert rendered.info.get("icc_profile")
    assert service.dispatch("get_previous_export") == previous
    assert hashlib.sha256(path.read_bytes()).digest() == digest


def test_previous_state_survives_product_catalog_backup_restore(library):
    service, root = library
    photo_id = import_photo(service, make_photo(root))
    saved_options = options(space="adobe", max_edge=37, quality=77,
                            output_sharpen=6.5, name="Restored-{stem}", priority=5,
                            metadata="copyright", keyword_hierarchy=False)
    manual_enqueue(service, [photo_id], root / "restored-output", "save-before-backup",
                   fmt="tiff16", export_options=saved_options, remember=True)
    saved = service.dispatch("get_previous_export")
    backup_path = root / "catalog-backup.sqlite"
    assert service.dispatch("backup_catalog", {"path": str(backup_path)})["backup"] == str(backup_path)
    restored_root = root / "restored-catalog"
    result = service.dispatch("restore_catalog", {
        "path": str(backup_path), "destination": str(restored_root),
    })
    assert result["catalog"] == str(restored_root.resolve())

    restored = Service(restored_root, presets_root=root / "presets")
    try:
        assert restored.dispatch("get_previous_export") == saved
    finally:
        restored.close()


def test_genuine_schema34_upgrade_adds_empty_previous_without_inference_or_partial_ddl(tmp_path, monkeypatch):
    root = tmp_path / "schema34"
    source = make_photo(tmp_path, "historical.png")
    historical_destination = tmp_path / "historical-output"
    historical_params = {
        "photo_ids": [],  # Filled with the genuine schema-34 photo ID below.
        "destination": str(historical_destination),
        "format": "jpeg",
        "options": ExportOptions().dict(),
        "request_key": "historical-v34-export",
    }
    with monkeypatch.context() as patch:
        patch.setattr(catalog_module, "migrate", lambda db: migrate_to(db, 34))
        catalog = Catalog(root)
        photo_id = seed_photo(catalog.db, source)
        historical_params["photo_ids"] = [photo_id]
        with catalog.db:
            historical_job = catalog.enqueue_one(
                catalog.photo(photo_id), historical_destination, "jpeg", ExportOptions()
            )
            # Schema 34 installations that have used the service already own
            # this runtime receipt table. Seed its exact pre-35 digest/result so
            # the upgraded implementation must replay the historical receipt.
            catalog.db.execute(
                "CREATE TABLE requests(key TEXT PRIMARY KEY,digest TEXT NOT NULL,result TEXT NOT NULL)"
            )
            historical_result = {"job_ids": [historical_job], "queued": 1}
            historical_digest = hashlib.sha256(
                json.dumps(historical_params, sort_keys=True).encode()
            ).hexdigest()
            catalog.db.execute(
                "INSERT INTO requests VALUES(?,?,?)",
                (historical_params["request_key"], historical_digest, json.dumps(historical_result)),
            )
        old_job = tuple(catalog.db.execute(
            "SELECT id,photo_id,source,recipe,destination,format,options,metadata_snapshot,export_metadata "
            "FROM jobs WHERE id=?", (historical_job,)
        ).fetchone())
        old_request = tuple(catalog.db.execute(
            "SELECT key,digest,result FROM requests WHERE key=?", (historical_params["request_key"],)
        ).fetchone())
        assert catalog.db.execute("PRAGMA user_version").fetchone()[0] == 34
        catalog.close()

    real_connect = sqlite3.connect
    denied = []

    def deny_previous_version(*args, **kwargs):
        db = real_connect(*args, **kwargs)

        def authorize(action_code, name, detail, database, trigger):
            # The migration has already created its table inside the open
            # transaction; deny the version bump to prove rollback removes DDL.
            if (action_code == sqlite3.SQLITE_PRAGMA and name == "user_version"
                    and detail == "35"):
                denied.append(f"{name}={detail}")
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        db.set_authorizer(authorize)
        return db

    with monkeypatch.context() as patch:
        patch.setattr(catalog_module.sqlite3, "connect", deny_previous_version)
        with pytest.raises(sqlite3.DatabaseError):
            Catalog(root)
    assert denied == ["user_version=35"]
    with sqlite3.connect(root / "catalog.sqlite") as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 34
        assert not db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='previous_export_session'"
        ).fetchone()
        assert tuple(db.execute(
            "SELECT id,photo_id,source,recipe,destination,format,options,metadata_snapshot,export_metadata "
            "FROM jobs WHERE id=?", (historical_job,)
        ).fetchone()) == old_job
        assert tuple(db.execute(
            "SELECT key,digest,result FROM requests WHERE key=?", (historical_params["request_key"],)
        ).fetchone()) == old_request

    catalog = Catalog(root)
    assert catalog.db.execute("PRAGMA user_version").fetchone()[0] == CATALOG_VERSION
    assert previous_state(catalog.db) == {"available": False, "revision": 0, "settings": None}
    assert tuple(catalog.db.execute(
        "SELECT id,photo_id,source,recipe,destination,format,options,metadata_snapshot,export_metadata "
        "FROM jobs WHERE id=?", (historical_job,)
    ).fetchone()) == old_job
    assert tuple(catalog.db.execute(
        "SELECT key,digest,result FROM requests WHERE key=?", (historical_params["request_key"],)
    ).fetchone()) == old_request
    catalog.close()

    # The v35 enqueue path must honor the old raw-params SHA-256 receipt and
    # return the original job rather than creating a fresh export.
    service = Service(root, presets_root=tmp_path / "presets")
    try:
        assert service.dispatch("enqueue_exports", historical_params) == historical_result
        assert job_total(service) == 1
        assert service.dispatch("get_previous_export") == {
            "available": False, "revision": 0, "settings": None,
        }
    finally:
        service.close()

    catalog = Catalog(root)
    assert catalog.db.execute("PRAGMA user_version").fetchone()[0] == CATALOG_VERSION
    assert catalog.db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert catalog.db.execute("SELECT COUNT(*) FROM previous_export_session").fetchone()[0] == 0
    assert previous_state(catalog.db) == {"available": False, "revision": 0, "settings": None}
    catalog.close()

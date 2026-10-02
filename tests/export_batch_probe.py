"""Measure bounded multi-preset queue submissions with metadata-heavy photos.

Inputs: a new work directory, photo count, preset-count cases, and direct keyword
assignments per photo. Outputs: first plus five warm preset-capture and batch-submit
times, catalog transaction durations, reply bytes, and sampled RSS. Service/SQLite
connection setup, schema validation, path preflight and keyword snapshot creation
are included in submit timing; photo seeding, IPC, UI, pixels and workers are not.
"""
import argparse
import json
import platform
import sqlite3
import statistics
import threading
import time
from pathlib import Path

import psutil
from PIL import Image

from lumaraw.model import ExportOptions
from lumaraw.service import Service


class CatalogTransactionTrace:
    """Count catalog BEGIN-to-COMMIT time only during measured dispatches."""

    def __init__(self, catalog_path):
        self.catalog_path = str(Path(catalog_path).resolve())
        self.enabled = False
        self.transactions_ms = []
        self.opened = {}
        self.real_connect = sqlite3.connect

    def connect(self, database, *args, **kwargs):
        db = self.real_connect(database, *args, **kwargs)
        try:
            is_catalog = str(Path(str(database)).resolve()) == self.catalog_path
        except (OSError, TypeError, ValueError):
            is_catalog = False
        if is_catalog:
            connection_id = id(db)

            def trace(statement):
                if not self.enabled:
                    return
                normalized = statement.strip().upper()
                if normalized.startswith("BEGIN"):
                    self.opened[connection_id] = time.perf_counter()
                elif normalized in ("COMMIT", "ROLLBACK"):
                    started = self.opened.pop(connection_id, None)
                    if started is not None:
                        self.transactions_ms.append((time.perf_counter() - started) * 1000)

            db.set_trace_callback(trace)
        return db


def options(**overrides):
    return {**ExportOptions().dict(), **overrides}


def source_images(root, count):
    root.mkdir(parents=True)
    paths = []
    for index in range(count):
        path = root / f"probe-{index:04}.png"
        Image.new("RGB", (8, 8), (index % 256, (index * 19) % 256, (index * 47) % 256)).save(path)
        paths.append(path)
    return paths


def timed_call(trace, operation):
    before = len(trace.transactions_ms)
    trace.enabled = True
    started = time.perf_counter()
    try:
        result = operation()
    finally:
        elapsed = (time.perf_counter() - started) * 1000
        trace.enabled = False
    transaction_ms = sum(trace.transactions_ms[before:])
    return result, elapsed, transaction_ms


def measure_series(operation, trace, process, repeats=5):
    baseline = process.memory_info().rss
    peak = [baseline]
    stopped = threading.Event()

    def sample_rss():
        while not stopped.wait(0.005):
            peak[0] = max(peak[0], process.memory_info().rss)

    sampler = threading.Thread(target=sample_rss, daemon=True)
    sampler.start()
    calls = []
    first_result = None
    try:
        for index in range(repeats + 1):
            result, elapsed, transaction_ms = timed_call(trace, operation)
            if index == 0:
                first_result = result
            calls.append({"dispatch_ms": round(elapsed, 3),
                          "catalog_transaction_ms": round(transaction_ms, 3),
                          "reply_bytes": len(json.dumps(result, separators=(",", ":")).encode("utf-8"))})
    finally:
        stopped.set()
        sampler.join()
    peak[0] = max(peak[0], process.memory_info().rss)
    warm = calls[1:]
    return first_result, {
        "first": calls[0],
        "warm": warm,
        "warm_dispatch_median_ms": round(statistics.median(row["dispatch_ms"] for row in warm), 3),
        "warm_transaction_median_ms": round(
            statistics.median(row["catalog_transaction_ms"] for row in warm), 3),
        "baseline_rss_mb": round(baseline / 1024**2, 2),
        "sampled_peak_rss_mb": round(peak[0] / 1024**2, 2),
        "sampled_rss_delta_mb": round(max(0, peak[0] - baseline) / 1024**2, 2),
    }


def measure_case(work, originals, photo_count, preset_count, keyword_count):
    case = work / f"photos-{photo_count}-presets-{preset_count}"
    case.mkdir()
    preset_root = case / "presets"
    catalog_root = case / "catalog"
    trace = CatalogTransactionTrace(catalog_root / "catalog.sqlite")
    original_connect = sqlite3.connect
    sqlite3.connect = trace.connect
    service = None
    try:
        service = Service(catalog_root, presets_root=preset_root)
        service.dispatch("queue_control", {"action": "pause"})
        service.dispatch("import_photos", {"paths": [str(path) for path in originals[:photo_count]]})
        with service.catalog() as catalog:
            photo_ids = [row[0] for row in catalog.db.execute(
                "SELECT id FROM photos ORDER BY id LIMIT ?", (photo_count,))]
            with catalog.db:
                keyword_ids = []
                for index in range(keyword_count):
                    name = f"Batch Keyword {index:03}"
                    keyword_ids.append(catalog.db.execute(
                        "INSERT INTO keywords(name,normalized) VALUES(?,?)",
                        (name, name.casefold()),
                    ).lastrowid)
                catalog.db.executemany(
                    "INSERT INTO keyword_photos(photo_id,keyword_id) VALUES(?,?)",
                    ((photo_id, keyword_id) for photo_id in photo_ids for keyword_id in keyword_ids),
                )

        preset_ids = []
        for index in range(preset_count):
            listing = service.dispatch("list_export_presets")
            result = service.dispatch("save_export_preset", {
                "name": f"Batch Preset {index:02}",
                "settings": {
                    "format": "jpeg",
                    "options": options(space="srgb", max_edge=0, quality=92,
                                        name="{stem}-batch", metadata="catalog",
                                        keyword_hierarchy=True),
                    "destination": None,
                },
                "expected_revision": listing["revision"],
            })
            preset_ids.append(result["preset_id"])

        capture_params = {
            "preset_ids": preset_ids,
            "expected_revision": service.dispatch("list_export_presets")["revision"],
        }
        process = psutil.Process()
        captured, capture_timing = measure_series(
            lambda: service.dispatch("get_export_presets", capture_params), trace, process)
        assert [row["id"] for row in captured["presets"]] == preset_ids

        parent = case / "outputs"
        parent.mkdir()
        entries = []
        for index, preset_id in enumerate(preset_ids):
            child = parent / f"Preset-{index:02}"
            child.mkdir()
            entries.append({"preset_id": preset_id, "subfolder": child.name,
                            "filename_suffix": f"Preset {index:02}"})

        submit_index = [0]

        def submit():
            ordinal = submit_index[0]
            submit_index[0] += 1
            return service.dispatch("enqueue_export_batch", {
                "photo_ids": photo_ids,
                "presets": entries,
                "expected_revision": captured["revision"],
                "request_key": f"probe-{photo_count}-{preset_count}-{ordinal}",
                "parent_destination": str(parent),
            })

        accepted, submit_timing = measure_series(submit, trace, process)
        expected_jobs = photo_count * preset_count * 6
        with service.catalog() as catalog:
            queued_jobs = catalog.db.execute(
                "SELECT count(*) FROM jobs WHERE batch_id IS NOT NULL"
            ).fetchone()[0]
            batch_count = catalog.db.execute("SELECT count(*) FROM export_batches").fetchone()[0]
        assert queued_jobs == expected_jobs and batch_count == 6
        return {
            "photos": photo_count,
            "presets_per_batch": preset_count,
            "jobs_per_batch": photo_count * preset_count,
            "direct_keywords_per_photo": keyword_count,
            "total_keyword_assignments": photo_count * keyword_count,
            "queue_state": "paused; no export workers or pixel rendering",
            "preset_capture": capture_timing,
            "batch_submission": submit_timing,
            "submitted_batches": batch_count,
            "submitted_jobs": queued_jobs,
            "first_batch": accepted,
            "filesystem_setup": "parent/subfolder directories pre-created outside timing",
        }
    finally:
        if service is not None:
            service.close()
        sqlite3.connect = original_connect


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--photos", type=int, default=100)
    parser.add_argument("--preset-counts", type=int, nargs="+", default=[1, 5, 10])
    parser.add_argument("--keywords-per-photo", type=int, default=25)
    args = parser.parse_args()
    if args.work.exists():
        raise SystemExit("Choose a new work directory")
    if not 1 <= args.photos <= 1000:
        raise SystemExit("--photos must be between 1 and 1000")
    if not 1 <= args.keywords_per_photo <= 100:
        raise SystemExit("--keywords-per-photo must be between 1 and 100")
    if not args.preset_counts or any(not 1 <= count <= 30 for count in args.preset_counts):
        raise SystemExit("--preset-counts values must be between 1 and 30")
    if any(args.photos * count > 1000 for count in args.preset_counts):
        raise SystemExit("Each photo/preset product must be at most 1000 jobs")

    work = args.work.resolve()
    work.mkdir(parents=True)
    originals = source_images(work / "originals", args.photos)
    report = {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "scope": "In-process Service plus catalog SQLite transactions; excludes IPC/UI, source seeding, and pixel workers",
        "warm_caveat": "SQLite/OS warm after first call; cold disk and desktop responsiveness are not measured",
        "transaction_metric": "catalog SQLite BEGIN-to-COMMIT elapsed time from trace callbacks; shared preset-store transactions excluded",
        "rss_sampling_interval_ms": 5,
        "repeats": "one first call plus five warm calls per capture and submission series",
        "cases": [measure_case(work, originals, args.photos, count, args.keywords_per_photo)
                  for count in args.preset_counts],
    }
    (work / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

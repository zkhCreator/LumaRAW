"""Opt-in scale probe for collection-label counts and filtered pages.

Inputs: row counts and an empty output directory. Outputs: explicit first-page
and five-repeat warm timings, result/reply sizes, query plans, SQLite VM work,
compact state-poll cost and sampled process RSS. Catalogs are built from a
genuine schema-32 seed and upgraded; this is not a desktop-performance claim.
"""
import argparse
import json
import statistics
import sys
import threading
import time
from pathlib import Path
from unittest.mock import patch

import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from lumaraw import catalog as catalog_module
from lumaraw.catalog import Catalog
from lumaraw.collections import Collections
from legacy_catalog import migrate_to


PAGE_SIZE = 60
WARM_REPEATS = 5


def create_schema32_catalog(root, size):
    with patch.object(catalog_module, "migrate", lambda db: migrate_to(db, 32)):
        catalog = Catalog(root)
    quick_id = catalog.db.execute("SELECT quick_id FROM collection_state WHERE id=1").fetchone()[0]
    rows = (
        (f"Collection {index:07d}", "regular", "{}", "all", None, float(index))
        for index in range(size)
    )
    with catalog.db:
        catalog.db.executemany(
            "INSERT INTO collections(name,kind,rules,match,parent_id,created) VALUES(?,?,?,?,?,?)",
            rows,
        )
    catalog.close()

    # Exercise the real additive upgrade on a populated v32 file. Label setup
    # and migration time are excluded from request timings.
    catalog = Catalog(root)
    with catalog.db:
        catalog.db.execute(
            "UPDATE collections SET color_label='red' "
            "WHERE kind!='quick' AND (id-?)%10=0", (quick_id,),
        )
    catalog.close()


def sample_peak_rss(stop, peak):
    process = psutil.Process()
    while not stop.wait(0.005):
        peak[0] = max(peak[0], process.memory_info().rss)


def timed_open(root):
    started = time.perf_counter()
    catalog = Catalog(root)
    return catalog, time.perf_counter() - started


def query(catalog, offset, color_label):
    store = Collections(catalog)
    if color_label is None:
        return store.list(offset=offset)
    return store.list(offset=offset, color_label=color_label)


def reply_bytes(result):
    return len(json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def measure_vm_work(catalog, offset, color_label):
    callbacks = [0]
    catalog.db.set_progress_handler(
        lambda: callbacks.__setitem__(0, callbacks[0] + 1) or 0, 1000,
    )
    try:
        result = query(catalog, offset, color_label)
    finally:
        catalog.db.set_progress_handler(None, 0)
    return {"progress_callbacks_per_1000_ops": callbacks[0], "reply_bytes": reply_bytes(result)}


def measure_page(root, offset, color_label):
    catalog, open_seconds = timed_open(root)
    try:
        started = time.perf_counter()
        first = query(catalog, offset, color_label)
        first_seconds = time.perf_counter() - started

        # Keep timing probes free of progress callbacks; measure VM work in its
        # own request below so instrumentation cannot distort latency.
        warm_seconds = []
        for _ in range(WARM_REPEATS):
            started = time.perf_counter()
            query(catalog, offset, color_label)
            warm_seconds.append(time.perf_counter() - started)
        vm = measure_vm_work(catalog, offset, color_label)
        return {
            "offset": offset,
            "rows": len(first["collections"]),
            "total": first["total"],
            "connection_open_ms": round(open_seconds * 1000, 3),
            "first_page_ms": round(first_seconds * 1000, 3),
            "warm_page_samples_ms": [round(value * 1000, 3) for value in warm_seconds],
            "warm_page_median_ms": round(statistics.median(warm_seconds) * 1000, 3),
            "reply_bytes": reply_bytes(first),
            "vm": vm,
        }
    finally:
        catalog.close()


def measure_case(root, color_label, mode_name):
    near_start = measure_page(root, 0, color_label)
    deep_offset = max(0, ((near_start["total"] - 1) // PAGE_SIZE) * PAGE_SIZE)
    deep = measure_page(root, deep_offset, color_label)
    return {"filter": mode_name, "total": near_start["total"],
            "pages": {"near_start": near_start, "deep": deep}}


def measure_state_poll(root):
    catalog, open_seconds = timed_open(root)
    try:
        store = Collections(catalog)
        started = time.perf_counter()
        first = store.state()
        first_seconds = time.perf_counter() - started
        warm = []
        for _ in range(WARM_REPEATS):
            started = time.perf_counter()
            store.state()
            warm.append(time.perf_counter() - started)
        callbacks = [0]
        catalog.db.set_progress_handler(
            lambda: callbacks.__setitem__(0, callbacks[0] + 1) or 0, 1000,
        )
        try:
            state = store.state()
        finally:
            catalog.db.set_progress_handler(None, 0)
        return {
            "connection_open_ms": round(open_seconds * 1000, 3),
            "first_state_ms": round(first_seconds * 1000, 3),
            "warm_state_samples_ms": [round(value * 1000, 3) for value in warm],
            "warm_state_median_ms": round(statistics.median(warm) * 1000, 3),
            "vm_progress_callbacks_per_1000_ops": callbacks[0],
            "reply_bytes": reply_bytes(state),
            "tree_revision": state["tree_revision"],
            "target_collection_id": state["target"]["id"],
            "reply_fields": sorted(first),
        }
    finally:
        catalog.close()


def query_plans(catalog):
    queries = {
        # Match Collections.list's bounded payload query. Selecting only id
        # would make the page look covering and hide the table-row fetches.
        "all_page": "SELECT * FROM collections WHERE kind!='quick' "
                    "ORDER BY name COLLATE NOCASE,id LIMIT 60",
        "red_page": "SELECT * FROM collections WHERE kind!='quick' AND color_label='red' "
                    "ORDER BY name COLLATE NOCASE,id LIMIT 60",
        "none_page": "SELECT * FROM collections WHERE kind!='quick' AND color_label='none' "
                     "ORDER BY name COLLATE NOCASE,id LIMIT 60",
        "labeled_page": "SELECT * FROM collections WHERE kind!='quick' AND color_label!='none' "
                        "ORDER BY name COLLATE NOCASE,id LIMIT 60",
        "red_count": "SELECT count(*) FROM collections WHERE kind!='quick' AND color_label='red'",
        "none_count": "SELECT count(*) FROM collections WHERE kind!='quick' AND color_label='none'",
        "labeled_count": "SELECT count(*) FROM collections WHERE kind!='quick' AND color_label!='none'",
    }
    return {
        name: [row[3] for row in catalog.db.execute("EXPLAIN QUERY PLAN " + sql)]
        for name, sql in queries.items()
    }


def sample_rss(stop, peak):
    process = psutil.Process()
    while not stop.wait(0.005):
        peak[0] = max(peak[0], process.memory_info().rss)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True,
                        help="new or empty directory for separate catalogs and report.json")
    parser.add_argument("--rows", nargs="+", type=int, default=[10_000, 100_000])
    args = parser.parse_args()
    if any(size < 1 for size in args.rows):
        parser.error("row counts must be positive")
    if args.work.exists() and any(args.work.iterdir()):
        parser.error("--work must be new or empty so existing data is preserved")
    args.work.mkdir(parents=True, exist_ok=True)

    report = {"schema_seed": 32, "page_size": PAGE_SIZE, "warm_repeats": WARM_REPEATS,
              "catalogs": []}
    for size in args.rows:
        root = args.work / f"catalog-{size}"
        create_schema32_catalog(root, size)
        process = psutil.Process()
        rss_baseline = process.memory_info().rss
        peak = [rss_baseline]
        stop = threading.Event()
        sampler = threading.Thread(target=sample_rss, args=(stop, peak), daemon=True)
        sampler.start()
        catalog = Catalog(root)
        try:
            plans = query_plans(catalog)
            if any("TEMP B-TREE" in line.upper() for plan in plans.values() for line in plan):
                raise AssertionError("collection-label count/page query plan uses a temporary B-tree")
            quick_count = catalog.db.execute(
                "SELECT count(*) FROM collections WHERE kind='quick'"
            ).fetchone()[0]
        finally:
            catalog.close()
        try:
            cases = [
                measure_case(root, None, "any"),
                measure_case(root, "labeled", "labeled"),
                measure_case(root, "none", "none"),
                measure_case(root, "red", "red"),
            ]
            state_poll = measure_state_poll(root)
        finally:
            stop.set()
            sampler.join(timeout=1)
        report["catalogs"].append({
            "collection_rows_excluding_quick": size,
            "quick_rows": quick_count,
            "query_plans": plans,
            "cases": cases,
            "state_poll": state_poll,
            "rss_baseline_after_seed_bytes": rss_baseline,
            "sampled_peak_rss_after_seed_bytes": peak[0],
            "catalog_path": str(root),
        })

    output = args.work / "report.json"
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()

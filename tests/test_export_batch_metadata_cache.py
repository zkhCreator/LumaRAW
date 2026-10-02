"""Transaction-local export metadata cache regressions for batch submissions.

Inputs: generated originals, catalog metadata, and multi-preset requests. Outputs:
evidence that equivalent photo/policy snapshots are reused within one batch while
serialized job receipts, ordering, options, recipes, orientation, and later batch
state remain exact. The cache never spans transactions or ordinary submissions.
"""
from collections import Counter
import json

import pytest

from lumaraw.batch_export_metadata import BatchExportMetadataCache, MAX_BYTES
from lumaraw.keyword_exports import KeywordExports, encode, receipt
from lumaraw.model import ExportOptions
from test_export_batch import (
    enqueue_batch,
    import_photos,
    library,
    make_photos,
    save_preset,
    settings,
)


def set_titles(service, photo_ids, values):
    for photo_id in photo_ids:
        current = service.dispatch("get_photo", {"photo_id": photo_id})
        service.dispatch("edit_metadata", {
            "targets": [{"photo_id": photo_id,
                         "expected_metadata_revision": current["metadata_revision"]}],
            "patch": {"title": values[photo_id]},
        })


def save_keyword(service, name, parent_id=None):
    params = {
        "name": name,
        "expected_revision": service.dispatch("library_state")["keyword_revision"],
    }
    if parent_id is not None:
        params["parent_id"] = parent_id
    return service.dispatch("save_keyword", params)["keyword_id"]


def membership(service, keyword_id, photo_ids, action):
    return service.dispatch("keyword_membership", {
        "keyword_id": keyword_id,
        "expected_revision": service.dispatch("library_state")["keyword_revision"],
        "targets": [
            {"photo_id": photo_id,
             "expected_metadata_revision": service.dispatch(
                 "get_photo", {"photo_id": photo_id})["metadata_revision"]}
            for photo_id in photo_ids
        ],
        "action": action,
    })


def policy_key(options):
    hierarchy = bool(options.keyword_hierarchy) if options.metadata == "catalog" else False
    return options.metadata, hierarchy


def raw_jobs(service, batch_id):
    with service.catalog() as catalog:
        return [dict(row) for row in catalog.db.execute(
            "SELECT id,photo_id,preset_name,format,options,recipe,orientation,"
            "metadata_snapshot,export_metadata FROM jobs WHERE batch_id=? ORDER BY id",
            (batch_id,),
        )]


def serialized_pair(service, job_id):
    with service.catalog() as catalog:
        row = catalog.db.execute(
            "SELECT metadata_snapshot,export_metadata FROM jobs WHERE id=?", (job_id,)
        ).fetchone()
        return row[0], row[1]


def uncached_pair(catalog, photo_id, options):
    snapshot = KeywordExports(catalog).snapshot(photo_id, options)
    return encode(snapshot), json.dumps(receipt(snapshot))


def set_rating(service, photo_ids, rating):
    service.dispatch("rate_photos", {"photo_ids": list(photo_ids), "rating": rating})


def test_batch_reuses_equivalent_photo_policies_and_keeps_job_payloads_exact(library, monkeypatch):
    service, root, _ = library
    photo_ids = import_photos(service, make_photos(root / "cache-originals", count=6))
    set_titles(service, photo_ids, {photo_id: f"Before {index}"
                                    for index, photo_id in enumerate(photo_ids)})
    parent_id = save_keyword(service, "Batch hierarchy")
    leaf_id = save_keyword(service, "Shared leaf", parent_id)
    membership(service, leaf_id, photo_ids, "add")
    rotated = photo_ids[0]
    service.dispatch("orient_photos", {
        "targets": [{"photo_id": rotated, "expected_revision": service.dispatch(
            "get_photo", {"photo_id": rotated})["revision"]}],
        "action": "rotate_right",
    })

    policy_specs = [
        ("Catalog flat A", "catalog", False),
        ("Catalog flat B", "catalog", False),
        ("Catalog hierarchy A", "catalog", True),
        ("Catalog hierarchy B", "catalog", True),
        ("Copyright A", "copyright", False),
        ("Copyright hierarchy option", "copyright", True),
        ("None A", "none", False),
        ("None hierarchy option", "none", True),
    ]
    destination = root / "cache-output"
    presets = []
    for index, (name, mode, hierarchy) in enumerate(policy_specs):
        preset_settings = settings(
            destination, fmt="jpeg" if index % 2 == 0 else "tiff16",
            metadata=mode, keyword_hierarchy=hierarchy, name=f"{{stem}}-cache-{index}",
            max_edge=100 + index, quality=90 + index, priority=index,
        )
        presets.append({
            "name": name,
            "preset_id": save_preset(service, name, preset_settings)["preset_id"],
            "settings": preset_settings,
        })

    unique_policies = {}
    for item in presets:
        options = ExportOptions.parse(item["settings"]["options"])
        unique_policies.setdefault(policy_key(options), options)
    expected_pairs = {}
    with service.catalog() as catalog:
        for photo_id in photo_ids:
            for key, options in unique_policies.items():
                expected_pairs[(photo_id, key)] = uncached_pair(catalog, photo_id, options)
        photo_state = {
            photo_id: tuple(catalog.db.execute(
                "SELECT recipe,orientation FROM photos WHERE id=?", (photo_id,)
            ).fetchone())
            for photo_id in photo_ids
        }

    snapshot_calls = Counter()
    project_calls = Counter()
    original_snapshot = KeywordExports.snapshot
    original_project = KeywordExports.project

    def count_snapshot(instance, photo_id, options):
        snapshot_calls[(photo_id, *policy_key(options))] += 1
        return original_snapshot(instance, photo_id, options)

    def count_project(instance, photo_id):
        project_calls[photo_id] += 1
        return original_project(instance, photo_id)

    monkeypatch.setattr(KeywordExports, "snapshot", count_snapshot)
    monkeypatch.setattr(KeywordExports, "project", count_project)
    token = service.dispatch("list_export_presets")["revision"]
    params = {
        "photo_ids": photo_ids,
        "presets": [{"preset_id": item["preset_id"]} for item in presets],
        "expected_revision": token,
        "request_key": "metadata-cache-equivalent-policies",
    }
    accepted = service.dispatch("enqueue_export_batch", params)

    expected_snapshot_calls = Counter({
        (photo_id, *key): 1
        for photo_id in photo_ids for key in unique_policies
    })
    assert snapshot_calls == expected_snapshot_calls
    assert project_calls == Counter({photo_id: 2 for photo_id in photo_ids})

    jobs = raw_jobs(service, accepted["batch_id"])
    assert [(job["preset_name"], job["photo_id"]) for job in jobs] == [
        (item["name"], photo_id) for item in presets for photo_id in photo_ids
    ]
    by_name = {item["name"]: item for item in presets}
    for job in jobs:
        item = by_name[job["preset_name"]]
        options = item["settings"]["options"]
        parsed_options = ExportOptions.parse(options)
        key = policy_key(parsed_options)
        assert job["format"] == item["settings"]["format"]
        assert json.loads(job["options"]) == options
        assert json.loads(job["recipe"]) == json.loads(photo_state[job["photo_id"]][0])
        assert job["orientation"] == photo_state[job["photo_id"]][1]
        assert (job["metadata_snapshot"], job["export_metadata"]) == expected_pairs[
            (job["photo_id"], key)
        ]

    before_replay = (snapshot_calls.copy(), project_calls.copy())
    assert service.dispatch("enqueue_export_batch", params) == accepted
    assert (snapshot_calls, project_calls) == before_replay

    ordinary_options = presets[0]["settings"]["options"]
    ordinary = service.dispatch("enqueue_exports", {
        "photo_ids": [photo_ids[0]],
        "destination": str(root / "ordinary-output"),
        "format": "jpeg",
        "options": ordinary_options,
        "request_key": "metadata-cache-ordinary-enqueue",
    })
    assert snapshot_calls[(photo_ids[0], "catalog", False)] == 2
    assert project_calls[photo_ids[0]] == 3
    ordinary_job = ordinary["job_ids"][0]
    assert serialized_pair(service, ordinary_job) == expected_pairs[(photo_ids[0], ("catalog", False))]


@pytest.mark.parametrize("limit_kind", ["entries", "bytes", "oversize", "zero-budget"])
def test_cache_lru_byte_budget_and_oversize_bypass_are_bounded(library, monkeypatch, limit_kind):
    service, root, _ = library
    photo_ids = import_photos(service, make_photos(root / f"cache-{limit_kind}", count=4))
    set_titles(service, photo_ids, {
        photo_ids[0]: "界A", photo_ids[1]: "界B", photo_ids[2]: "界C", photo_ids[3]: "界" * 400,
    })
    options = ExportOptions(metadata="catalog", keyword_hierarchy=False)
    with service.catalog() as catalog:
        baseline = {photo_id: uncached_pair(catalog, photo_id, options) for photo_id in photo_ids}
        payload_sizes = {
            photo_id: sum(len(value.encode("utf-8")) for value in pair)
            for photo_id, pair in baseline.items()
        }
    assert payload_sizes[photo_ids[0]] == payload_sizes[photo_ids[1]] == payload_sizes[photo_ids[2]]
    assert payload_sizes[photo_ids[3]] > payload_sizes[photo_ids[0]]

    calls = Counter()
    original_snapshot = KeywordExports.snapshot

    def count_snapshot(instance, photo_id, requested_options):
        calls[photo_id] += 1
        return original_snapshot(instance, photo_id, requested_options)

    monkeypatch.setattr(KeywordExports, "snapshot", count_snapshot)
    with service.catalog() as catalog:
        if limit_kind == "entries":
            cache = BatchExportMetadataCache(catalog, max_bytes=MAX_BYTES, max_entries=1)
            sequence = [photo_ids[0], photo_ids[1], photo_ids[1], photo_ids[0]]
            expected_calls = Counter({photo_ids[0]: 2, photo_ids[1]: 1})
        elif limit_kind == "bytes":
            exact_two_entry_budget = payload_sizes[photo_ids[0]] + payload_sizes[photo_ids[1]]
            cache = BatchExportMetadataCache(
                catalog, max_bytes=exact_two_entry_budget, max_entries=10
            )
            sequence = [photo_ids[0], photo_ids[1], photo_ids[0], photo_ids[2],
                        photo_ids[0], photo_ids[1]]
            expected_calls = Counter({photo_ids[0]: 1, photo_ids[1]: 2, photo_ids[2]: 1})
        elif limit_kind == "oversize":
            cache = BatchExportMetadataCache(
                catalog, max_bytes=payload_sizes[photo_ids[0]], max_entries=10
            )
            sequence = [photo_ids[0], photo_ids[3], photo_ids[0], photo_ids[3]]
            expected_calls = Counter({photo_ids[0]: 1, photo_ids[3]: 2})
        else:
            cache = BatchExportMetadataCache(catalog, max_bytes=0, max_entries=10)
            sequence = [photo_ids[0], photo_ids[0]]
            expected_calls = Counter({photo_ids[0]: 2})

        catalog.db.execute("BEGIN IMMEDIATE")
        for photo_id in sequence:
            assert cache.get(photo_id, options) == baseline[photo_id]
        catalog.db.commit()
    assert calls == expected_calls


def test_new_batch_observes_metadata_keyword_and_rating_changes(library, monkeypatch):
    service, root, _ = library
    photo_ids = import_photos(service, make_photos(root / "batch-refresh", count=3))
    set_titles(service, photo_ids, {photo_id: "Before batch" for photo_id in photo_ids})
    set_rating(service, photo_ids, 1)
    old_keyword = save_keyword(service, "Before keyword")
    membership(service, old_keyword, photo_ids, "add")
    preset_settings = settings(
        root / "refresh-output", metadata="catalog", keyword_hierarchy=False,
    )
    preset_id = save_preset(service, "Catalog export", preset_settings)["preset_id"]

    calls = Counter()
    original_snapshot = KeywordExports.snapshot
    original_project = KeywordExports.project

    def count_snapshot(instance, photo_id, options):
        calls[("snapshot", photo_id)] += 1
        return original_snapshot(instance, photo_id, options)

    def count_project(instance, photo_id):
        calls[("project", photo_id)] += 1
        return original_project(instance, photo_id)

    monkeypatch.setattr(KeywordExports, "snapshot", count_snapshot)
    monkeypatch.setattr(KeywordExports, "project", count_project)
    token = service.dispatch("list_export_presets")["revision"]
    first = enqueue_batch(service, photo_ids, [{"preset_id": preset_id}],
                          "metadata-cache-before-edit", revision=token)
    first_jobs = raw_jobs(service, first["batch_id"])
    first_snapshots = {job["photo_id"]: json.loads(job["metadata_snapshot"]) for job in first_jobs}
    assert all(snapshot["fields"]["title"] == "Before batch" for snapshot in first_snapshots.values())
    assert all(snapshot["fields"]["rating"] == 1 for snapshot in first_snapshots.values())
    assert all(snapshot["keywords"] == ["Before keyword"] for snapshot in first_snapshots.values())
    assert calls == Counter({(kind, photo_id): 1 for kind in ("snapshot", "project")
                             for photo_id in photo_ids})

    set_titles(service, photo_ids, {photo_id: "After batch" for photo_id in photo_ids})
    set_rating(service, photo_ids, 5)
    new_keyword = save_keyword(service, "After keyword")
    membership(service, old_keyword, photo_ids, "remove")
    membership(service, new_keyword, photo_ids, "add")

    second = enqueue_batch(service, photo_ids, [{"preset_id": preset_id}],
                           "metadata-cache-after-edit", revision=token)
    second_jobs = raw_jobs(service, second["batch_id"])
    second_snapshots = {job["photo_id"]: json.loads(job["metadata_snapshot"]) for job in second_jobs}
    assert all(snapshot["fields"]["title"] == "After batch" for snapshot in second_snapshots.values())
    assert all(snapshot["fields"]["rating"] == 5 for snapshot in second_snapshots.values())
    assert all(snapshot["keywords"] == ["After keyword"] for snapshot in second_snapshots.values())
    assert calls == Counter({(kind, photo_id): 2 for kind in ("snapshot", "project")
                             for photo_id in photo_ids})

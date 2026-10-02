"""Transaction-local reuse of frozen export metadata for multi-preset batches.

Inputs: a catalog connection inside the batch write transaction and one photo's
validated export metadata policy. Outputs: the exact serialized snapshot and
receipt stored on each queued job. The bounded LRU never survives the batch
transaction, never changes ordinary enqueue behavior, and never holds pixels,
recipes, or export settings.
"""
from collections import OrderedDict
import json

from .keyword_exports import KeywordExports, encode, receipt

MAX_BYTES = 16 * 1024 * 1024
MAX_ENTRIES = 1000


class BatchExportMetadataCache:
    """Reuse one photo/policy snapshot only while its batch transaction is open."""

    def __init__(self, catalog, *, max_bytes=MAX_BYTES, max_entries=MAX_ENTRIES):
        if type(max_bytes) is not int or max_bytes < 0:
            raise ValueError('Metadata cache byte budget must be a nonnegative integer')
        if type(max_entries) is not int or max_entries < 0:
            raise ValueError('Metadata cache entry limit must be a nonnegative integer')
        self.catalog = catalog
        self.max_bytes = max_bytes
        self.max_entries = max_entries
        self._entries = OrderedDict()
        self._bytes = 0

    @staticmethod
    def _key(photo_id, options):
        hierarchy = bool(options.keyword_hierarchy) if options.metadata == 'catalog' else False
        return photo_id, options.metadata, hierarchy

    def get(self, photo_id, options):
        """Return serialized job metadata, computing and validating a cache miss."""
        if not self.catalog.db.in_transaction:
            raise RuntimeError('Batch metadata cache requires an active catalog transaction')

        key = self._key(photo_id, options)
        cached = self._entries.get(key)
        if cached is not None:
            self._entries.move_to_end(key)
            return cached[0], cached[1]

        snapshot = KeywordExports(self.catalog).snapshot(photo_id, options)
        snapshot_json = encode(snapshot)
        receipt_json = json.dumps(receipt(snapshot))
        payload_bytes = len(snapshot_json.encode('utf-8')) + len(receipt_json.encode('utf-8'))

        # Oversize records still serve this job, but are never retained. A zero
        # budget/entry limit similarly disables reuse without rejecting exports.
        if payload_bytes > self.max_bytes or self.max_entries == 0:
            return snapshot_json, receipt_json

        while self._entries and (
                self._bytes + payload_bytes > self.max_bytes
                or len(self._entries) >= self.max_entries):
            _, evicted = self._entries.popitem(last=False)
            self._bytes -= evicted[2]

        self._entries[key] = (snapshot_json, receipt_json, payload_bytes)
        self._bytes += payload_bytes
        return snapshot_json, receipt_json

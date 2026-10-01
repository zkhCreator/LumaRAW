"""Explicit Copy orchestration between bounded catalog pages and filesystem I/O.

Inputs: a revision-bound import, cancellation and read-only source verification.
Outputs: collision preflight, durable copy progress and one catalog transaction.
No pixels or automatic replay. A failed transfer remains interrupted for explicit
resume/cancel. Cancellation removes owned scratch links and retains completed files.
"""
from .import_copy import ImportCopy, settings, COPY_PHASES
from .import_review import ImportReview
from . import import_copy_io as io


class CopyRunner:
    def __init__(self, service):
        self.service = service

    def pages(self, plan_id):
        after = 0
        while True:
            with self.service.catalog() as catalog:
                rows = ImportCopy(catalog).page(plan_id, after)
            if not rows:
                return
            yield rows
            after = rows[-1]['id']

    def save(self, row, **patch):
        with self.service.catalog() as catalog:
            ImportCopy(catalog).save(row, **patch)

    def resume(self, plan_id, expected_revision):
        with self.service.catalog() as catalog, catalog.db:
            plan = ImportReview(catalog).check(plan_id, expected_revision, ('interrupted',))
            if plan['phase'] not in COPY_PHASES or settings(catalog.db, plan_id) is None:
                raise ValueError('This import has no interrupted Copy transfer')
            catalog.db.execute("UPDATE import_plans SET state='verifying',error='',checked=0,revision=revision+1 WHERE id=?", (plan_id,))
            return ImportReview(catalog).row(plan_id)

    def execute(self, plan, cancelled, verify_sources):
        plan_id, revision = plan['id'], plan['revision']
        with self.service.catalog() as catalog:
            value = settings(catalog.db, plan_id)
        if value['owner'] != str(self.service.root):
            raise ValueError('This Copy plan belongs to another catalog; cancel it and create a fresh review')
        io.check_destination(value)
        if plan['phase'] != 'copying':
            # No destination writes are allowed until the entire selected scope
            # has passed collision preflight. A crash here can rebuild staging.
            with self.service.catalog() as catalog, catalog.db:
                ImportReview(catalog).check(plan_id, revision, ('verifying',))
                catalog.db.execute("UPDATE import_plans SET phase='copy_preparing' WHERE id=?", (plan_id,))
                catalog.db.execute('DELETE FROM import_transfers WHERE plan_id=?', (plan_id,))
                catalog.db.execute("UPDATE import_files SET catalog_path='' WHERE plan_id=?", (plan_id,))
                catalog.db.execute('UPDATE import_copy_plans SET transfer_count=0,copied=0,copied_bytes=0 WHERE plan_id=?', (plan_id,))
            after = 0
            while True:
                io.check_cancel(cancelled)
                with self.service.catalog() as catalog:
                    rows = ImportReview(catalog).pages(plan_id, revision, 'files', after)
                    if not rows:
                        break
                    ImportCopy(catalog).stage(plan_id, rows, value)
                after = rows[-1]['id']
            for rows in self.pages(plan_id):
                for row in rows:
                    io.check_cancel(cancelled)
                    io.preflight(row, value)
            with self.service.catalog() as catalog, catalog.db:
                catalog.db.execute("UPDATE import_plans SET phase='copying' WHERE id=?", (plan_id,))
        for rows in self.pages(plan_id):
            for row in rows:
                io.transfer(row, value, self.save, cancelled)
        # Recheck source observations as well as the newly published files before
        # committing catalog references. No source/target I/O holds a SQL lock.
        verify_sources(plan, cancelled, count=False)
        for rows in self.pages(plan_id):
            for row in rows:
                io.check_cancel(cancelled)
                io.verify_published(row, value)
        with self.service.catalog() as catalog:
            return ImportReview(catalog).apply(plan_id, revision, cancelled)

    def interrupt(self, plan_id, error):
        with self.service.catalog() as catalog, catalog.db:
            plan = ImportReview(catalog).row(plan_id)
            if plan['state'] == 'verifying':
                catalog.db.execute("UPDATE import_plans SET state='interrupted',revision=revision+1,error=? WHERE id=?",
                    (str(error)+' Completed copies are retained. Inspect the destination, then resume or cancel explicitly.', plan_id))
            return ImportReview(catalog).get(plan_id)

    def cancel(self, plan_id):
        warnings = 0
        with self.service.catalog() as catalog:
            value = settings(catalog.db, plan_id)
            plan = ImportReview(catalog).row(plan_id)
        if plan['state'] in ('applied', 'cancelled', 'failed'):
            with self.service.catalog() as catalog:
                return ImportReview(catalog).get(plan_id)
        for rows in self.pages(plan_id):
            for row in rows:
                try:
                    if value['owner'] == str(self.service.root):
                        io.check_destination(value)
                        io.cleanup(row)
                    else:
                        warnings += 1
                except (OSError, ValueError):
                    warnings += 1
        message = 'Copy cancelled. Completed files remain at the destination.'
        if warnings:
            message += ' Some scratch files could not be safely removed; inspect the destination.'
        with self.service.catalog() as catalog:
            return ImportReview(catalog).terminal(plan_id, 'cancelled', message)

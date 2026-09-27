from datetime import datetime

import pytest

from app.orchestration.models import ManagedAccount
from app.orchestration.workers import GoogleSheetsOutboxWorker
from app.schemas import TutorLead


def lead() -> TutorLead:
    return TutorLead(
        post_id="post-1", collected_at=datetime.now(), posted_at=None, platform="facebook",
        group="Group", content="Can tim gia su Toan lop 8", post_url="https://www.facebook.com/groups/g/posts/1/",
        confidence=0.8,
    )


class Store:
    def __init__(self):
        self.entries = [(17, lead())]
        self.exported = []
        self.retries = []

    def claim_sheet_outbox(self, limit):
        entries, self.entries = self.entries, []
        return entries

    def mark_sheet_exported(self, ids):
        self.exported.extend(ids)

    def mark_sheet_retry(self, ids, error):
        self.retries.append((ids, error))


class Writer:
    sheet_id = "sheet"
    service_account_file = "account.json"

    def __init__(self, failure=False):
        self.failure, self.batches = failure, []

    def append_many(self, leads):
        if self.failure:
            raise ConnectionError("temporary failure")
        self.batches.append(leads)


def test_outbox_writer_marks_exported_only_after_success():
    store, writer = Store(), Writer()
    assert GoogleSheetsOutboxWorker(store, writer).flush_once() == 1
    assert store.exported == [17]
    assert len(writer.batches) == 1


def test_outbox_writer_retries_after_write_failure():
    store = Store()
    with pytest.raises(ConnectionError):
        GoogleSheetsOutboxWorker(store, Writer(failure=True)).flush_once()
    assert store.exported == []
    assert store.retries[0][0] == [17]


def test_outbox_writer_never_marks_unconfigured_sheet_as_exported():
    class UnconfiguredWriter(Writer):
        sheet_id = None

    store = Store()
    with pytest.raises(RuntimeError, match="Google Sheets"):
        GoogleSheetsOutboxWorker(store, UnconfiguredWriter()).flush_once()
    assert store.exported == []

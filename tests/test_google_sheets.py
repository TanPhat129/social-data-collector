from datetime import datetime

from app.integrations.google_sheets import GoogleSheetsWriter
from app.schemas import TutorLead


def test_google_sheet_row_matches_configured_header_order():
    lead = TutorLead(
        post_id="p1",
        collected_at=datetime(2026, 9, 20, 10),
        posted_at=datetime(2026, 9, 20, 9),
        platform="facebook",
        group="Tutor Group",
        subject="Toan",
        grade="lop 8",
        location="Quan 3",
        mode="Online",
        budget="200k",
        phone="0901234567",
        content="Can gia su",
        post_url="https://example.com/post",
        author_url="https://facebook.com/example.author",
        confidence=0.8,
    )

    assert GoogleSheetsWriter.to_row(lead, 2) == [
        "=ROW()-1",
        "Tutor Group",
        "Toan",
        "facebook",
        "lop 8",
        "Quan 3",
        "Online",
        "200k",
        "0901234567",
        "Can gia su",
        "https://example.com/post",
        "https://facebook.com/example.author",
        "2026-09-20 09:00:00",
        "2026-09-20 10:00:00",
    ]


def test_first_empty_row_ignores_stt_formula_only_rows():
    class Worksheet:
        def get_all_values(self):
            return [["STT", "Group"], ["1", "Group A"], ["=ROW()-1", ""]]

    assert GoogleSheetsWriter._first_empty_row(Worksheet()) == 3

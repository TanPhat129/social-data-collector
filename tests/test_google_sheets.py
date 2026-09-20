from datetime import datetime

from app.integrations.google_sheets import GoogleSheetsWriter
from app.schemas import TutorLead


def test_google_sheet_row_matches_configured_header_order():
    lead = TutorLead(post_id="p1", collected_at=datetime(2026, 9, 20, 10), posted_at=datetime(2026, 9, 20, 9),
        platform="facebook", group="Tutor Group", subject="Toán", grade="lớp 8", location="Quận 3", mode="Online",
        budget="200k", phone="0901234567", content="Cần gia sư", post_url="https://example.com/post", confidence=0.8)

    assert GoogleSheetsWriter.to_row(lead, 2) == [
        "=ROW()-1", "Tutor Group", "Toán", "facebook", "lớp 8", "Quận 3", "Online", "200k", "0901234567",
        "Cần gia sư", "https://example.com/post", "2026-09-20T09:00:00", "2026-09-20T10:00:00",
    ]


def test_first_empty_row_ignores_stt_formula_only_rows():
    class Worksheet:
        def get_all_values(self):
            return [["STT", "Group"], ["1", "Group A"], ["=ROW()-1", ""]]

    assert GoogleSheetsWriter._first_empty_row(Worksheet()) == 3

import logging
from app.schemas import TutorLead
logger = logging.getLogger(__name__)


class GoogleSheetsWriter:
    # Matches the header row in the configured Google Sheet:
    # STT, Group, Subject, Platform, Grade, Location, Mode, Budget, Phone,
    # Content, URL, Author URL, Posted At, Collected At.
    HEADERS = ("STT", "Group", "Subject", "Platform", "Grade", "Location", "Mode", "Budget", "Phone", "Content", "URL", "Author URL", "Posted At", "Collected At")

    def __init__(self, sheet_id: str | None = None, service_account_file: str | None = None):
        self.sheet_id, self.service_account_file = sheet_id, service_account_file

    def append(self, lead: TutorLead) -> None:
        self.append_many([lead])

    def append_many(self, leads: list[TutorLead]) -> None:
        if not leads:
            return
        if not self.sheet_id or not self.service_account_file:
            logger.info("Google Sheets not configured; accepted locally: %s", ", ".join(lead.post_id for lead in leads))
            return
        import gspread
        worksheet = gspread.service_account(filename=self.service_account_file).open_by_key(self.sheet_id).sheet1
        first_row = self._first_empty_row(worksheet)
        rows = [self.to_row(lead, first_row + offset) for offset, lead in enumerate(leads)]
        last_row = first_row + len(rows) - 1
        worksheet.update(f"A{first_row}:N{last_row}", rows, value_input_option="USER_ENTERED")

    @staticmethod
    def _first_empty_row(worksheet) -> int:
        """Find the first data row without lead fields, ignoring leftover STT formulas."""
        rows = worksheet.get_all_values()
        for row_number, row in enumerate(rows[1:], start=2):
            fields = row[1:14]  # Group through Collected At; column A is STT.
            if not any(value.strip() for value in fields):
                return row_number
        return max(2, len(rows) + 1)

    @staticmethod
    def to_row(lead: TutorLead, row_number: int) -> list[str]:
        """Serialize one lead in the exact configured Sheet column order."""
        return [
            f"=ROW()-1",  # Calculated by Sheets because USER_ENTERED is used.
            lead.group,
            lead.subject or "",
            lead.platform,
            lead.grade or "",
            lead.location or "",
            lead.mode or "",
            lead.budget or "",
            lead.phone or "",
            lead.content,
            lead.post_url or "",
            lead.author_url or "",
            GoogleSheetsWriter._format_datetime(lead.posted_at),
            GoogleSheetsWriter._format_datetime(lead.collected_at),
        ]

    @staticmethod
    def _format_datetime(value) -> str:
        return value.strftime("%Y-%m-%d %H:%M:%S") if value else ""

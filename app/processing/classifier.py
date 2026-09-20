from dataclasses import dataclass
import re


@dataclass(frozen=True)
class Classification:
    intent: str
    confidence: float


class TutorIntentClassifier:
    """Deterministic MVP classifier; replace with an evaluated AI adapter."""
    POSITIVE = ("gia sư", "người dạy", "người kèm", "giáo viên", "thầy", "cô")
    ABBREVIATIONS = ("gs",)
    DEMAND = ("cần", "tìm", "nhờ")
    # "Tuyển gia sư" is a demand post (a parent/centre is hiring a tutor),
    # not an offer from a tutor. Keep offer-only wording here.
    EXCLUDED = ("nhận dạy", "tìm học viên", "có nhận dạy")

    def classify(self, content: str) -> Classification:
        text = content.lower()
        if any(item in text for item in self.EXCLUDED): return Classification("OTHER", 0.85)
        has_positive = any(item in text for item in self.POSITIVE) or any(
            re.search(rf"(?<!\w){re.escape(item)}(?!\w)", text) for item in self.ABBREVIATIONS
        )
        if has_positive and any(item in text for item in self.DEMAND): return Classification("FIND_TUTOR", 0.80)
        return Classification("OTHER", 0.75)

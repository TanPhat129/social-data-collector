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
    OFFER_SIGNALS = (
        "nhận dạy", "tìm học viên", "có nhận dạy", "nhận học sinh",
        "học thử", "đăng ký học", "chiêu sinh", "khóa học", "lộ trình học",
        "trung tâm gia sư", "bên em có gia sư", "đội ngũ gia sư",
    )
    PRICE = re.compile(r"(?:chỉ|từ)?\s*\d+[.,]?\d*\s*(?:k|nghìn|triệu|đ|vnđ)\s*(?:/|mỗi)?\s*(?:tháng|buổi)?", re.I)

    def classify(self, content: str) -> Classification:
        text = content.lower()
        # Marketing often starts with a rhetorical "bạn đang tìm gia sư?".
        # Supply-side signals take precedence over that wording: the author is
        # selling tutoring, not looking to hire a tutor.
        if any(item in text for item in self.OFFER_SIGNALS) or (
            "bạn đang tìm gia sư" in text and self.PRICE.search(text)
        ):
            return Classification("TUTOR_OFFER", 0.92)
        has_positive = any(item in text for item in self.POSITIVE) or any(
            re.search(rf"(?<!\w){re.escape(item)}(?!\w)", text) for item in self.ABBREVIATIONS
        )
        if has_positive and any(item in text for item in self.DEMAND): return Classification("FIND_TUTOR", 0.80)
        return Classification("OTHER", 0.75)

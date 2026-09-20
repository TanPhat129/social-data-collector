import re
from app.schemas import RawPost, TutorLead


class LeadExtractor:
    PHONE = re.compile(r"(?<!\d)(?:\+84|0)(?:\d[ .-]?){8,10}\d(?!\d)")
    SUBJECT = re.compile(r"\b(Toán|Văn|Anh|Tiếng Anh|Lý|Hóa|Sinh|IELTS)\b", re.I)
    GRADE = re.compile(r"\blớp\s*(\d{1,2})\b", re.I)
    LOCATION = re.compile(r"\b(Quận\s*\d+|Q\.\s*\d+|Thủ Đức|Bình Thạnh|Gò Vấp|Tân Bình)\b", re.I)
    FREQUENCY = re.compile(r"\b\d+\s*buổi\s*/?\s*(?:tuần|tháng)\b", re.I)

    def extract(self, post: RawPost, confidence: float) -> TutorLead:
        find = lambda pattern: (m.group(0) if (m := pattern.search(post.content)) else None)
        text = post.content.lower()
        return TutorLead(post_id=post.post_id, collected_at=post.collected_at, posted_at=post.posted_at,
            platform=post.source.platform, group=post.source.name, subject=find(self.SUBJECT), grade=find(self.GRADE),
            location=find(self.LOCATION), mode="Online" if "online" in text else "Offline" if "offline" in text else None,
            frequency=find(self.FREQUENCY), phone=find(self.PHONE), content=post.content, post_url=post.post_url, confidence=confidence)


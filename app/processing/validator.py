from app.schemas import TutorLead


class LeadValidator:
    """Business validation performed before a lead is sent downstream."""
    def validate(self, lead: TutorLead) -> bool:
        return bool(lead.post_id and lead.content.strip() and lead.platform and lead.group and lead.confidence >= 0.60)

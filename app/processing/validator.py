from app.schemas import TutorLead


class LeadValidator:
    """Business validation performed before a lead is sent downstream."""
    def validate(self, lead: TutorLead) -> bool:
        # A lead without the original post URL cannot be reviewed or verified,
        # so it must never be exported. Author URL is deliberately optional:
        # Facebook does not expose it for anonymous posts and some private
        # group layouts.
        return bool(
            lead.post_id
            and lead.content.strip()
            and lead.platform
            and lead.group
            and lead.post_url
            and lead.post_url.strip()
            and lead.confidence >= 0.60
        )

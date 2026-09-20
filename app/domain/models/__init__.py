"""Canonical domain models.

The MVP retains the existing Pydantic schemas while clients migrate to this
package, avoiding a breaking change in integrations.
"""

from app.schemas import RawPost, Source, TutorLead

__all__ = ["RawPost", "Source", "TutorLead"]

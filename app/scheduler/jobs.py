import logging
from app.pipeline import LeadPipeline
from app.schemas import Source

logger = logging.getLogger(__name__)


def collect_source(pipeline: LeadPipeline, source: Source) -> None:
    leads = pipeline.run(source)
    logger.info("source=%s accepted_leads=%d", source.id, len(leads))

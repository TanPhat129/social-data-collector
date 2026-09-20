from app.pipeline import LeadPipeline
from app.schemas import Source, TutorLead


class ProcessLeads:
    def __init__(self, pipeline: LeadPipeline):
        self.pipeline = pipeline

    def execute(self, source: Source) -> list[TutorLead]:
        return self.pipeline.run(source)

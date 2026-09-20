"""OpenAI Responses API adapter with structured output and bounded retries."""
from dataclasses import dataclass
import json
import time

from openai import OpenAI

from app.processing.classifier import Classification
from app.schemas import RawPost, TutorLead


@dataclass(frozen=True)
class TutorAnalysis:
    intent: str
    confidence: float
    fields: dict[str, str | None]


class OpenAITutorAnalyzer:
    SCHEMA = {
        "type": "object", "additionalProperties": False,
        "properties": {
            "intent": {"type": "string", "enum": ["FIND_TUTOR", "OTHER"]},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            **{field: {"type": ["string", "null"]} for field in ("subject", "grade", "location", "mode", "schedule", "frequency", "budget", "phone")},
        },
        "required": ["intent", "confidence", "subject", "grade", "location", "mode", "schedule", "frequency", "budget", "phone"],
    }

    def __init__(self, api_key: str, model: str, max_retries: int = 3):
        self.client, self.model, self.max_retries = OpenAI(api_key=api_key), model, max_retries
        self._cache: dict[str, TutorAnalysis] = {}

    def analyze(self, content: str) -> TutorAnalysis:
        if content in self._cache:
            return self._cache[content]
        for attempt in range(self.max_retries):
            try:
                response = self.client.responses.create(model=self.model, store=False,
                    instructions="Classify Vietnamese social posts. FIND_TUTOR only means a person is seeking to hire a tutor. Extract only explicit facts; otherwise use null.",
                    input=content, text={"format": {"type": "json_schema", "name": "tutor_lead", "schema": self.SCHEMA, "strict": True}})
                data = json.loads(response.output_text)
                result = TutorAnalysis(data["intent"], float(data["confidence"]), {key: data[key] for key in self.SCHEMA["required"][2:]})
                self._cache[content] = result
                return result
            except Exception:
                if attempt + 1 == self.max_retries:
                    raise
                time.sleep(2 ** attempt)
        raise RuntimeError("unreachable")


class OpenAIIntentClassifier:
    def __init__(self, analyzer: OpenAITutorAnalyzer): self.analyzer = analyzer
    def classify(self, content: str) -> Classification:
        result = self.analyzer.analyze(content)
        return Classification(result.intent, result.confidence)


class OpenAILeadExtractor:
    def __init__(self, analyzer: OpenAITutorAnalyzer, fallback): self.analyzer, self.fallback = analyzer, fallback
    def extract(self, post: RawPost, confidence: float) -> TutorLead:
        lead = self.fallback.extract(post, confidence)
        return lead.model_copy(update={key: value for key, value in self.analyzer.analyze(post.content).fields.items() if value is not None})

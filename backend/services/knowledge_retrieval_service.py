import json
import re
from dataclasses import dataclass
from pathlib import Path


TOKEN_PATTERN = re.compile(r"[\w\-]+", re.UNICODE)
STOP_WORDS = {
    "and", "are", "for", "from", "how", "the", "this", "what", "who", "with",
    "der", "die", "das", "ein", "eine", "ist", "und", "von", "was", "wie", "wer",
    "для", "как", "какие", "какой", "кто", "между", "это", "чем", "что",
}
CYRILLIC_SUFFIXES = (
    "иями", "ями", "ами", "ого", "ему", "ому", "иях", "ах", "ях", "ия", "ии",
    "ый", "ий", "ой", "ая", "яя", "ое", "ее", "ые", "ие", "ов", "ев", "ам",
    "ям", "ом", "ем", "у", "ю", "а", "я", "ы", "и", "е",
)


@dataclass(frozen=True)
class KnowledgeResult:
    title: str
    content: str
    source: str
    score: float


class LocalKnowledgeBase:
    """Small, deterministic retrieval layer for grounding local AI answers.

    The JSON corpus is deliberately independent from Ollama so a vector store
    or remote verified source can replace this implementation later without
    changing the assistant route.
    """

    def __init__(self, paths=None):
        default_path = Path(__file__).resolve().parents[2] / "data" / "knowledge" / "core_facts.json"
        self.paths = [Path(path) for path in (paths or [default_path])]
        self._documents = None

    @staticmethod
    def _stem(token):
        token = str(token or "").casefold()
        if len(token) > 5 and re.search(r"[а-яё]", token):
            for suffix in CYRILLIC_SUFFIXES:
                if token.endswith(suffix) and len(token) - len(suffix) >= 4:
                    return token[:-len(suffix)]
        if len(token) > 5 and token.endswith("s"):
            return token[:-1]
        return token

    @classmethod
    def _tokens(cls, value):
        return {
            cls._stem(token)
            for token in TOKEN_PATTERN.findall(str(value or ""))
            if len(token) > 2 and token.casefold() not in STOP_WORDS
        }

    def _load(self):
        if self._documents is not None:
            return self._documents
        documents = []
        for path in self.paths:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError):
                continue
            for item in payload if isinstance(payload, list) else []:
                if not isinstance(item, dict):
                    continue
                title = str(item.get("title", "")).strip()
                content = str(item.get("content", "")).strip()
                source = str(item.get("source", "")).strip()
                if title and content and source:
                    documents.append((title, content, source, self._tokens(f"{title} {content}")))
        self._documents = documents
        return documents

    def search(self, query, limit=3, minimum_score=0.12):
        query_tokens = self._tokens(query)
        if not query_tokens:
            return []
        ranked = []
        for title, content, source, document_tokens in self._load():
            overlap = query_tokens & document_tokens
            minimum_overlap = 1 if len(query_tokens) <= 2 else 2
            if len(overlap) < minimum_overlap:
                continue
            score = len(overlap) / max(len(query_tokens), 1)
            if score >= minimum_score:
                ranked.append(KnowledgeResult(title, content, source, score))
        ranked.sort(key=lambda item: (-item.score, item.title.casefold()))
        return ranked[:max(1, min(int(limit), 5))]

    def context(self, query, limit=3):
        results = self.search(query, limit=limit)
        if not results:
            return "", []
        blocks = [f"[{index}] {item.title}\n{item.content}\nSource: {item.source}" for index, item in enumerate(results, 1)]
        return "\n\n".join(blocks), [item.source for item in results]


_knowledge_base = LocalKnowledgeBase()


def retrieve_verified_context(query, limit=3):
    return _knowledge_base.context(query, limit=limit)

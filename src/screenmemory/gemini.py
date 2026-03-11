from __future__ import annotations

import json
from datetime import datetime

import requests

from screenmemory.config import ScreenMemoryConfig
from screenmemory.models import AnswerCitation, QueryPlan, SearchResult


class GeminiClient:
    def __init__(self, config: ScreenMemoryConfig) -> None:
        # We talk to Gemini over HTTPS directly so we are not blocked on SDK-specific behavior.
        self.config = config
        self.api_key = config.gemini_api_key
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _post(self, path: str, payload: dict) -> dict:
        if not self.api_key:
            raise RuntimeError(
                "Gemini is not configured. Set GEMINI_API_KEY or GOOGLE_API_KEY first."
            )

        response = requests.post(
            f"{self.base_url}/{path}",
            params={"key": self.api_key},
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
        return response.json()

    def embed_text(self, text: str, task_type: str) -> list[float]:
        # We embed OCR chunks and user queries as text, not raw images, in this v1.
        payload = {
            "model": f"models/{self.config.gemini_embedding_model}",
            "content": {"parts": [{"text": text}]},
            "taskType": task_type,
        }
        data = self._post(
            f"models/{self.config.gemini_embedding_model}:embedContent",
            payload,
        )
        return data["embedding"]["values"]

    def plan_query(self, raw_query: str, now: datetime) -> QueryPlan:
        # Gemini is only used here for the richer natural-language time parsing in semantic mode.
        prompt = f"""
You convert a user's screenshot-search request into structured JSON.
The user's local timezone is {self.config.timezone_name}.
The current local datetime is {now.isoformat()}.

Return JSON only with these keys:
- semantic_query: string
- start_epoch: integer or null
- end_epoch: integer or null
- sort_mode: one of relevance, newest, oldest
- answer_mode: boolean
- filters_applied: array of short strings

User query:
{raw_query}
""".strip()

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
            },
        }
        data = self._post(
            f"models/{self.config.gemini_generation_model}:generateContent",
            payload,
        )
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(text)
        return QueryPlan(
            mode="semantic",
            raw_query=raw_query,
            semantic_query=parsed.get("semantic_query") or raw_query,
            start_epoch=parsed.get("start_epoch"),
            end_epoch=parsed.get("end_epoch"),
            sort_mode=parsed.get("sort_mode") or "relevance",
            answer_mode=bool(parsed.get("answer_mode", True)),
            filters_applied=list(parsed.get("filters_applied") or []),
        )

    def answer_with_context(
        self,
        question: str,
        results: list[SearchResult],
    ) -> tuple[str, list[AnswerCitation]]:
        # The answer is optional. The retrieved snippets stay the real evidence shown to the user.
        context_blocks = []
        for index, result in enumerate(results[:8], start=1):
            context_blocks.append(
                "\n".join(
                    [
                        f"Source {index}",
                        f"Timestamp: {result.captured_at_local}",
                        f"Path: {result.file_path}",
                        f"Snippet: {result.snippet}",
                        f"OCR Preview: {result.ocr_text_preview}",
                    ]
                )
            )
        joined_context = "\n\n".join(context_blocks)
        prompt = f"""
Answer the user's screenshot-history question using only the supplied OCR context.
If the evidence is weak or incomplete, say that clearly.
When you make a factual claim, cite one or more sources using square-bracket footnotes like [1] or [2].
Only use source numbers that appear in the provided context.

Return JSON only with these keys:
- answer: string
- citations: array of objects with:
  - footnote: integer
  - source_number: integer

Question:
{question}

Context:
{joined_context}
""".strip()

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
            },
        }
        data = self._post(
            f"models/{self.config.gemini_generation_model}:generateContent",
            payload,
        )
        parsed = json.loads(data["candidates"][0]["content"]["parts"][0]["text"])
        answer = str(parsed.get("answer") or "").strip()

        citations: list[AnswerCitation] = []
        for raw_citation in parsed.get("citations") or []:
            try:
                footnote = int(raw_citation["footnote"])
                source_number = int(raw_citation["source_number"])
            except (KeyError, TypeError, ValueError):
                continue

            result_index = source_number - 1
            if result_index < 0 or result_index >= len(results):
                continue

            result = results[result_index]
            citations.append(
                AnswerCitation(
                    footnote=footnote,
                    result_index=result_index,
                    file_path=result.file_path,
                    captured_at_local=result.captured_at_local,
                    snippet=result.snippet,
                )
            )

        # Keep one citation per footnote number in stable footnote order.
        unique_by_footnote: dict[int, AnswerCitation] = {}
        for citation in citations:
            unique_by_footnote.setdefault(citation.footnote, citation)
        ordered_citations = [
            unique_by_footnote[number]
            for number in sorted(unique_by_footnote)
        ]

        return answer, ordered_citations

"""LLM-powered code review analysis for DiffMind warnings."""

from __future__ import annotations

import json
import re
from typing import List, Optional

from ..models import ReviewComment, ReviewReport, ReviewWarning
from .config import ConnectConfig, LLMConfig
from .prompts import build_review_prompt, build_summary_prompt


class LLMReviewer:
    """Analyze DiffMind warnings using LLM for detailed code review comments.

    Supports multiple providers:
      - claude (Anthropic API)
      - openai (OpenAI API)
      - ollama (local models)

    Usage:
        reviewer = LLMReviewer(provider="claude")
        comment = reviewer.analyze_warning(warning)
        report = reviewer.analyze_all(warnings)
    """

    def __init__(
        self,
        provider: str = "claude",
        model: str = "",
        api_key: str = "",
        base_url: str = "",
        temperature: float = 0.3,
        max_tokens: int = 2048,
        language: str = "en",
        config: Optional[ConnectConfig] = None,
    ):
        if config:
            llm = config.llm
            self.provider = llm.provider
            self.model = llm.resolve_model()
            self.api_key = llm.resolve_api_key()
            self.base_url = llm.base_url
            self.temperature = llm.temperature
            self.max_tokens = llm.max_tokens
            self.language = llm.language
        else:
            cfg = LLMConfig(
                provider=provider, model=model, api_key=api_key,
                base_url=base_url, temperature=temperature,
                max_tokens=max_tokens, language=language,
            )
            self.provider = provider
            self.model = cfg.resolve_model()
            self.api_key = cfg.resolve_api_key()
            self.base_url = base_url
            self.temperature = temperature
            self.max_tokens = max_tokens
            self.language = language

        self._client = None

    def _get_client(self):
        """Lazy-load the appropriate API client."""
        if self._client is not None:
            return self._client

        if self.provider == "claude":
            import anthropic
            self._client = anthropic.Anthropic(api_key=self.api_key)

        elif self.provider == "openai":
            import openai
            kwargs = {"api_key": self.api_key}
            if self.base_url:
                kwargs["base_url"] = self.base_url
            self._client = openai.OpenAI(**kwargs)

        elif self.provider == "ollama":
            import openai
            base = self.base_url or "http://localhost:11434/v1"
            self._client = openai.OpenAI(
                base_url=base, api_key="ollama",
            )
        else:
            raise ValueError(f"Unknown provider: {self.provider}")

        return self._client

    def _call_llm(self, system: str, user: str) -> str:
        """Send a prompt to the LLM and return the raw response text."""
        client = self._get_client()

        if self.provider == "claude":
            response = client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            return response.content[0].text

        else:  # openai / ollama
            response = client.chat.completions.create(
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
            return response.choices[0].message.content

    def _parse_json_response(self, text: str) -> dict:
        """Extract and parse JSON from LLM response, handling markdown fences."""
        # Try direct parse
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try extracting from markdown code block
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1).strip())
            except json.JSONDecodeError:
                pass

        # Try finding first { ... } block
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        # Fallback
        return {
            "risk_level": "LOW",
            "summary": "Unable to parse LLM response",
            "explanation": text[:500],
            "suggestion": "Please review manually",
            "suggested_code": "",
            "confidence": 0.0,
        }

    def analyze_warning(self, warning: ReviewWarning) -> ReviewComment:
        """Analyze a single DiffMind warning and produce an AI review comment.

        Args:
            warning: A ReviewWarning from DiffMind's review engine.

        Returns:
            ReviewComment with AI-generated analysis.
        """
        system, user = build_review_prompt(warning, language=self.language)
        raw = self._call_llm(system, user)
        data = self._parse_json_response(raw)

        risk = data.get("risk_level", warning.risk_level).upper()
        if risk not in ("HIGH", "MEDIUM", "LOW", "FALSE_POSITIVE"):
            risk = warning.risk_level

        past = warning.similar_hunk
        pr_ref = f" (PR #{past.pr_number})" if past.pr_number else ""

        return ReviewComment(
            file_path=warning.current_hunk.file_path,
            line_range=warning.current_hunk.hunk_header or "",
            risk_level=risk,
            summary=data.get("summary", ""),
            explanation=data.get("explanation", ""),
            suggestion=data.get("suggestion", ""),
            suggested_code=data.get("suggested_code", ""),
            past_bug_reference=f"{past.short_hash()} - {past.commit_message}{pr_ref}",
            confidence=float(data.get("confidence", 0.0)),
        )

    def analyze_all(self, warnings: List[ReviewWarning]) -> ReviewReport:
        """Analyze all warnings and produce a comprehensive review report.

        Args:
            warnings: List of ReviewWarning from DiffMind.

        Returns:
            ReviewReport with all comments and overall summary.
        """
        if not warnings:
            return ReviewReport(
                comments=[],
                overall_risk="CLEAN",
                summary="No warnings to analyze.",
                provider=self.provider,
                model_used=self.model,
                total_warnings_analyzed=0,
                false_positives=0,
            )

        comments: List[ReviewComment] = []
        for w in warnings:
            comment = self.analyze_warning(w)
            comments.append(comment)

        # Calculate overall risk
        false_positives = sum(
            1 for c in comments if c.risk_level == "FALSE_POSITIVE"
        )
        real_comments = [
            c for c in comments if c.risk_level != "FALSE_POSITIVE"
        ]

        if not real_comments:
            overall_risk = "CLEAN"
        else:
            risk_order = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
            max_risk = max(
                risk_order.get(c.risk_level, 0) for c in real_comments
            )
            overall_risk = {3: "HIGH", 2: "MEDIUM", 1: "LOW"}.get(
                max_risk, "LOW"
            )

        # Generate summary
        try:
            summary_prompt = build_summary_prompt(
                comments, language=self.language
            )
            summary = self._call_llm(
                "You are a concise technical writer.", summary_prompt
            )
        except Exception:
            # If summary generation fails, create a simple one
            summary = (
                f"Analyzed {len(warnings)} warnings. "
                f"{false_positives} false positives. "
                f"Overall risk: {overall_risk}."
            )

        return ReviewReport(
            comments=comments,
            overall_risk=overall_risk,
            summary=summary.strip(),
            provider=self.provider,
            model_used=self.model,
            total_warnings_analyzed=len(warnings),
            false_positives=false_positives,
        )

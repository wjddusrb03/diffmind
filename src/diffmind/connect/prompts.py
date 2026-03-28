"""Prompt templates for LLM code review analysis."""

from __future__ import annotations

REVIEW_SYSTEM_PROMPT = """\
You are a senior code reviewer with deep expertise in bug pattern analysis.
Your role is to analyze code changes that have been flagged by DiffMind as
similar to past bug-fix commits. You must determine whether the current
change is likely to introduce the same kind of bug that was previously fixed.

Rules:
- Be precise and specific about what the potential issue is.
- If the similarity is coincidental and the code is actually safe, say so
  (mark as FALSE_POSITIVE).
- Always provide a concrete code suggestion when there is a real risk.
- Keep explanations concise but informative.
- Respond ONLY with the requested JSON format.
"""

REVIEW_SYSTEM_PROMPT_KO = """\
당신은 버그 패턴 분석에 깊은 전문성을 가진 시니어 코드 리뷰어입니다.
DiffMind가 과거 버그 수정 커밋과 유사하다고 플래그한 코드 변경을 분석하는 것이
당신의 역할입니다. 현재 변경이 이전에 수정된 것과 같은 종류의 버그를 도입할
가능성이 있는지 판단해야 합니다.

규칙:
- 잠재적 문제가 무엇인지 정확하고 구체적으로 설명하세요.
- 유사성이 우연이고 코드가 실제로 안전하다면, 그렇게 말하세요 (FALSE_POSITIVE로 표시).
- 실제 위험이 있을 때는 항상 구체적인 코드 수정 제안을 포함하세요.
- 설명은 간결하되 유익하게 작성하세요.
- 요청된 JSON 형식으로만 응답하세요.
"""

REVIEW_USER_PROMPT = """\
DiffMind detected a similarity between a current code change and a past bug fix.
Analyze whether this is a real risk or a false positive.

## Current Change
File: {current_file}
Language: {language}
Author: {current_author}
```diff
{current_diff}
```

## Past Bug Fix (Similarity: {similarity}%)
Commit: {past_commit} by {past_author} on {past_date}
Message: {past_message}
{pr_info}
```diff
{past_diff}
```

Analyze and respond in this exact JSON format:
{{
  "risk_level": "HIGH | MEDIUM | LOW | FALSE_POSITIVE",
  "summary": "One-line summary of the risk",
  "explanation": "Detailed explanation of why this is/isn't a risk",
  "suggestion": "What the developer should do",
  "suggested_code": "Corrected code snippet (or empty string if no fix needed)",
  "confidence": 0.0
}}
"""

REVIEW_USER_PROMPT_KO = """\
DiffMind가 현재 코드 변경과 과거 버그 수정 사이의 유사성을 감지했습니다.
이것이 실제 위험인지 오탐인지 분석하세요.

## 현재 변경사항
파일: {current_file}
언어: {language}
작성자: {current_author}
```diff
{current_diff}
```

## 과거 버그 수정 (유사도: {similarity}%)
커밋: {past_commit} by {past_author} ({past_date})
메시지: {past_message}
{pr_info}
```diff
{past_diff}
```

분석 후 아래 JSON 형식으로 정확히 응답하세요:
{{
  "risk_level": "HIGH | MEDIUM | LOW | FALSE_POSITIVE",
  "summary": "위험에 대한 한 줄 요약",
  "explanation": "이것이 왜 위험한지/위험하지 않은지 상세 설명",
  "suggestion": "개발자가 해야 할 일",
  "suggested_code": "수정된 코드 스니펫 (수정이 필요 없으면 빈 문자열)",
  "confidence": 0.0
}}
"""

REPORT_SUMMARY_PROMPT = """\
You are summarizing a code review. Given these individual warning analyses,
write a brief overall summary (2-3 sentences).

Warnings analyzed: {count}
False positives: {false_positives}
Risk levels found: {risk_levels}

Individual analyses:
{analyses}

Respond with a single paragraph summary.
"""

REPORT_SUMMARY_PROMPT_KO = """\
코드 리뷰를 요약하고 있습니다. 다음 개별 경고 분석을 바탕으로
간략한 전체 요약을 작성하세요 (2-3문장).

분석된 경고: {count}개
오탐: {false_positives}개
발견된 위험 수준: {risk_levels}

개별 분석:
{analyses}

한 문단으로 요약하세요.
"""


def format_diff(old_code: str, new_code: str, max_lines: int = 30) -> str:
    """Format old/new code as a unified-ish diff for prompt inclusion."""
    lines = []
    for line in old_code.split("\n")[:max_lines]:
        if line.strip():
            lines.append(f"- {line}")
    for line in new_code.split("\n")[:max_lines]:
        if line.strip():
            lines.append(f"+ {line}")
    return "\n".join(lines) if lines else "(no code changes)"


def build_review_prompt(
    warning,
    language: str = "en",
) -> tuple[str, str]:
    """Build system + user prompt pair for a single ReviewWarning.

    Returns:
        (system_prompt, user_prompt)
    """
    current = warning.current_hunk
    past = warning.similar_hunk

    current_diff = format_diff(current.old_code, current.new_code)
    past_diff = format_diff(past.old_code, past.new_code)

    pr_info = f"PR: #{past.pr_number}" if past.pr_number else ""

    if language == "ko":
        system = REVIEW_SYSTEM_PROMPT_KO
        user_tpl = REVIEW_USER_PROMPT_KO
    else:
        system = REVIEW_SYSTEM_PROMPT
        user_tpl = REVIEW_USER_PROMPT

    user = user_tpl.format(
        current_file=current.file_path,
        language=current.language,
        current_author=current.author,
        current_diff=current_diff,
        similarity=f"{warning.similarity:.0%}",
        past_commit=f"{past.short_hash()} - {past.commit_message}",
        past_author=past.author,
        past_date=past.time_str(),
        past_message=past.commit_message,
        pr_info=pr_info,
        past_diff=past_diff,
    )

    return system, user


def build_summary_prompt(
    comments,
    language: str = "en",
) -> str:
    """Build a summary prompt from individual ReviewComments."""
    risk_levels = set()
    false_positives = 0
    analyses = []

    for c in comments:
        risk_levels.add(c.risk_level)
        if c.risk_level == "FALSE_POSITIVE":
            false_positives += 1
        analyses.append(f"- [{c.risk_level}] {c.file_path}: {c.summary}")

    tpl = REPORT_SUMMARY_PROMPT_KO if language == "ko" else REPORT_SUMMARY_PROMPT

    return tpl.format(
        count=len(comments),
        false_positives=false_positives,
        risk_levels=", ".join(sorted(risk_levels)) or "none",
        analyses="\n".join(analyses) or "(none)",
    )

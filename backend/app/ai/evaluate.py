import re
from collections.abc import AsyncIterator

from app.ai.client import AIClientError, OpenRouterClient, get_ai_client
from app.ai.json_parsing import extract_json_value

EVALUATION_TEMPERATURE = 0.0

SYSTEM_PROMPT = (
    "You are an experienced interviewer evaluating a candidate's answer to an "
    "interview question. Score the answer from 0 to 10 (integer). For technical "
    "questions, judge accuracy and depth of knowledge. For behavioral questions, "
    "judge whether the answer follows the STAR structure (Situation, Task, Action, "
    "Result) and demonstrates real impact. Respond with STRICT JSON ONLY: an object "
    'with exactly four fields: "score" (integer 0-10), "feedback" (string), '
    '"strengths" (array of strings), and "gaps" (array of strings). Do not include '
    "any prose, explanation, or markdown fences outside the JSON object."
)

# Strict JSON can't be shown to a user as it streams in (you'd be watching raw
# braces and quotes form character by character), so the streaming path uses
# this separate plain-text format instead - readable live, still cheaply
# parseable line-by-line.
STREAM_SYSTEM_PROMPT = (
    "You are an experienced interviewer evaluating a candidate's answer to an "
    "interview question. Score the answer from 0 to 10 (integer). For technical "
    "questions, judge accuracy and depth of knowledge. For behavioral questions, "
    "judge whether the answer follows the STAR structure (Situation, Task, Action, "
    "Result) and demonstrates real impact. Respond using EXACTLY this plain-text "
    "format, with no extra commentary before or after it:\n"
    "SCORE: <integer 0-10>\n"
    "FEEDBACK: <one or two sentences of feedback>\n"
    "STRENGTHS:\n"
    "- <short strength>\n"
    "GAPS:\n"
    "- <short gap>\n"
    "If there are no strengths or gaps, write a single line under that heading: "
    "- (none)"
)

_STREAM_SCORE_RE = re.compile(r"^SCORE:\s*(.+)$", re.IGNORECASE)
_STREAM_FEEDBACK_RE = re.compile(r"^FEEDBACK:\s*(.*)$", re.IGNORECASE)
_STREAM_STRENGTHS_RE = re.compile(r"^STRENGTHS:\s*$", re.IGNORECASE)
_STREAM_GAPS_RE = re.compile(r"^GAPS:\s*$", re.IGNORECASE)
_STREAM_BULLET_RE = re.compile(r"^-\s*(.+)$")


def _coerce_score(value) -> int:
    try:
        score = int(round(float(value)))
    except (TypeError, ValueError):
        return 0
    return max(0, min(10, score))


def _coerce_str_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _parse_evaluation(raw: str) -> dict | None:
    data = extract_json_value(raw, "{", "}")
    if not isinstance(data, dict):
        return None

    feedback = data.get("feedback")
    return {
        "score": _coerce_score(data.get("score")),
        "feedback": feedback if isinstance(feedback, str) else "",
        "strengths": _coerce_str_list(data.get("strengths")),
        "gaps": _coerce_str_list(data.get("gaps")),
    }


async def evaluate_answer(
    question: str,
    answer: str,
    context: str,
    ai_client: OpenRouterClient | None = None,
) -> dict:
    client = ai_client or get_ai_client()

    user_prompt = (
        f"Knowledge base context:\n{context}\n\n"
        f"Interview question:\n{question}\n\n"
        f"Candidate's answer:\n{answer}\n\n"
        "Evaluate the answer and respond with a strict JSON object only, "
        "no prose, no markdown fences."
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    raw = await client.complete(messages, temperature=EVALUATION_TEMPERATURE)
    evaluation = _parse_evaluation(raw)
    if evaluation is None:
        raw = await client.complete(messages, temperature=EVALUATION_TEMPERATURE)
        evaluation = _parse_evaluation(raw)
    if evaluation is None:
        raise AIClientError("Could not parse AI response as JSON")
    return evaluation


def _parse_stream_evaluation(raw: str) -> dict | None:
    score: int | None = None
    feedback_parts: list[str] = []
    strengths: list[str] = []
    gaps: list[str] = []
    section: str | None = None

    for line in (line.strip() for line in raw.splitlines()):
        if not line:
            continue

        score_match = _STREAM_SCORE_RE.match(line)
        if score_match:
            score = _coerce_score(score_match.group(1))
            section = None
            continue

        feedback_match = _STREAM_FEEDBACK_RE.match(line)
        if feedback_match:
            feedback_parts.append(feedback_match.group(1).strip())
            section = None
            continue

        if _STREAM_STRENGTHS_RE.match(line):
            section = "strengths"
            continue
        if _STREAM_GAPS_RE.match(line):
            section = "gaps"
            continue

        bullet_match = _STREAM_BULLET_RE.match(line)
        if bullet_match and section in ("strengths", "gaps"):
            item = bullet_match.group(1).strip()
            if item.lower() not in ("(none)", "none"):
                (strengths if section == "strengths" else gaps).append(item)
            continue

    if score is None:
        return None

    return {
        "score": score,
        "feedback": " ".join(feedback_parts).strip(),
        "strengths": strengths,
        "gaps": gaps,
    }


async def evaluate_answer_stream(
    question: str,
    answer: str,
    context: str,
    ai_client: OpenRouterClient | None = None,
) -> AsyncIterator[tuple[str | None, dict | None]]:
    """Yields (delta_text, None) per streamed chunk, then (None, evaluation) once done."""
    client = ai_client or get_ai_client()

    user_prompt = (
        f"Knowledge base context:\n{context}\n\n"
        f"Interview question:\n{question}\n\n"
        f"Candidate's answer:\n{answer}\n\n"
        "Evaluate the answer using exactly the plain-text format described above."
    )
    messages = [
        {"role": "system", "content": STREAM_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    raw_parts: list[str] = []
    async for delta in client.stream_complete(messages, temperature=EVALUATION_TEMPERATURE):
        raw_parts.append(delta)
        yield delta, None

    evaluation = _parse_stream_evaluation("".join(raw_parts))
    if evaluation is None:
        raw = await client.complete(messages, temperature=EVALUATION_TEMPERATURE)
        evaluation = _parse_stream_evaluation(raw)
    if evaluation is None:
        raise AIClientError("Could not parse AI response in the expected format")

    yield None, evaluation

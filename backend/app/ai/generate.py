import json
import re

from app.ai.client import AIClientError, OpenRouterClient, get_ai_client
from app.config import settings
from app.models import Section

MODE_INSTRUCTIONS = {
    "technical": "Ask only technical questions that test depth of knowledge and accuracy.",
    "behavioral": "Ask only behavioral questions the candidate can answer using the STAR method.",
    "mixed": "Ask a mix of roughly half technical and half behavioral questions.",
}

SYSTEM_PROMPT = (
    "You are an experienced interviewer preparing a candidate for a job interview. "
    "Generate interview questions based ONLY on the knowledge-base content the user "
    "provides. Respond with STRICT JSON ONLY: a JSON array of objects, each with "
    'exactly two string fields: "question" and "category" (either "technical" or '
    '"behavioral"). Do not include any prose, explanation, or markdown fences '
    "outside the JSON array."
)

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _build_context(sections: list[Section], char_budget: int) -> str:
    parts: list[str] = []
    remaining = char_budget
    for section in sections:
        if remaining <= 0:
            break
        header = f"## Section: {section.name}\n"
        appended = header[:remaining]
        parts.append(appended)
        remaining -= len(appended)

        for document in section.documents:
            if remaining <= 0:
                break
            chunk = f"### {document.title}\n{document.content}\n"
            appended_chunk = chunk[:remaining]
            parts.append(appended_chunk)
            remaining -= len(appended_chunk)
    return "".join(parts)


def _try_json_loads(text: str):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _parse_questions(raw: str) -> list[dict[str, str]] | None:
    fence_match = _FENCE_RE.search(raw)
    text = fence_match.group(1) if fence_match else raw.strip()

    data = _try_json_loads(text)
    if data is None:
        start, end = text.find("["), text.rfind("]")
        if start != -1 and end != -1 and end > start:
            data = _try_json_loads(text[start : end + 1])

    if not isinstance(data, list):
        return None

    questions: list[dict[str, str]] = []
    for item in data:
        if not isinstance(item, dict):
            return None
        question, category = item.get("question"), item.get("category")
        if not isinstance(question, str) or not isinstance(category, str):
            return None
        questions.append({"question": question, "category": category})
    return questions


async def generate_questions(
    sections: list[Section],
    mode: str,
    count: int,
    ai_client: OpenRouterClient | None = None,
) -> list[dict[str, str]]:
    client = ai_client or get_ai_client()
    context = _build_context(sections, settings.max_generation_context_chars)

    user_prompt = (
        f"Knowledge base content:\n{context}\n\n"
        f"Generate exactly {count} interview questions. {MODE_INSTRUCTIONS[mode]}\n"
        "Respond with a strict JSON array only, no prose, no markdown fences."
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    raw = await client.complete(messages)
    questions = _parse_questions(raw)
    if questions is None:
        raw = await client.complete(messages)
        questions = _parse_questions(raw)
    if questions is None:
        raise AIClientError("Could not parse AI response as JSON")
    return questions

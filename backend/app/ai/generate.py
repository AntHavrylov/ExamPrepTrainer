from app.ai.client import AIClientError, OpenRouterClient, get_ai_client
from app.ai.context import build_context
from app.ai.json_parsing import extract_json_value
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


def _parse_questions(raw: str) -> list[dict[str, str]] | None:
    data = extract_json_value(raw, "[", "]")
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
    context = build_context(sections, settings.max_generation_context_chars)

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

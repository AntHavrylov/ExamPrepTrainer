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

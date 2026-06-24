from app.ai.client import AIClientError
from app.ai.context import build_context
from app.ai.json_parsing import extract_json_value
from app.ai.provider import AIProvider
from app.config import settings
from app.models import Section

MODE_INSTRUCTIONS = {
    "technical": "Ask only technical questions that test depth of knowledge and accuracy.",
    "behavioral": "Ask only behavioral questions the candidate can answer using the STAR method.",
    "mixed": "Ask a mix of roughly half technical and half behavioral questions.",
}

DIFFICULTY_INSTRUCTIONS = {
    "easy": "Keep questions straightforward, testing basic recall and fundamental understanding.",
    "medium": "Use a moderate difficulty suitable for a competent practitioner.",
    "hard": "Make questions challenging, probing edge cases, trade-offs, and deeper understanding.",
}

LANGUAGE_NAMES = {
    "en": "English",
    "uk": "Ukrainian",
    "ru": "Russian",
}


def _language_line(language: str) -> str:
    name = LANGUAGE_NAMES.get(language, LANGUAGE_NAMES["en"])
    return (
        f"Write all natural-language text (question, options if present, theme, "
        f"hint, and explanation) in {name}. The \"category\" field must still be "
        'exactly "technical" or "behavioral" in English, regardless of the '
        "response language.\n"
    )

SYSTEM_PROMPT = (
    "You are an experienced interviewer preparing a candidate for a job interview. "
    "Generate interview questions based ONLY on the knowledge-base content the user "
    "provides. Respond with STRICT JSON ONLY: a JSON array of objects, each with "
    'exactly five string fields: "question", "category" (either "technical" or '
    '"behavioral"), "theme" (a short 2-6 word topic label for this question, used '
    'to detect duplicate topics, e.g. "binary search complexity"), "hint" (a short '
    "nudge toward the answer that does NOT reveal it, shown to the candidate before "
    'they answer), and "explanation" (a few sentences on what a strong answer '
    "should cover, shown to the candidate only after they answer). Do not include "
    "any prose, explanation, or markdown fences outside the JSON array."
)

QUIZ_SYSTEM_PROMPT = (
    "You are an experienced interviewer preparing a multiple-choice quiz for a "
    "candidate's job interview prep. Generate multiple-choice questions based ONLY "
    "on the knowledge-base content the user provides. Respond with STRICT JSON "
    'ONLY: a JSON array of objects, each with exactly seven fields: "question" '
    '(string), "category" (either "technical" or "behavioral"), "options" (an '
    'array of exactly 4 short string choices), "correct_index" (an integer 0-3, '
    'the index of the correct option in "options"), "theme" (a short 2-6 word '
    'topic label for this question, used to detect duplicate topics, e.g. "binary '
    'search complexity"), "hint" (a short nudge toward the answer that does NOT '
    'reveal which option is correct, shown to the candidate before they answer), '
    'and "explanation" (a few sentences on why the correct option is correct, '
    "shown to the candidate only after they answer). Exactly one option must be "
    "correct. Do not include any prose, explanation, or markdown fences outside "
    "the JSON array."
)


def _avoid_themes_line(avoid_themes: list[str] | None) -> str:
    if not avoid_themes:
        return ""
    return f"Avoid repeating these previously covered topics: {', '.join(avoid_themes)}.\n"


def _parse_questions(raw: str) -> list[dict[str, str]] | None:
    data = extract_json_value(raw, "[", "]")
    if not isinstance(data, list):
        return None

    questions: list[dict[str, str]] = []
    for item in data:
        if not isinstance(item, dict):
            return None
        question = item.get("question")
        category = item.get("category")
        theme = item.get("theme")
        hint = item.get("hint")
        explanation = item.get("explanation")
        if not all(isinstance(v, str) for v in (question, category, theme, hint, explanation)):
            return None
        questions.append(
            {
                "question": question,
                "category": category,
                "theme": theme,
                "hint": hint,
                "explanation": explanation,
            }
        )
    return questions


async def generate_questions(
    sections: list[Section],
    mode: str,
    count: int,
    ai_client: AIProvider,
    difficulty: str = "medium",
    avoid_themes: list[str] | None = None,
    language: str = "en",
) -> list[dict[str, str]]:
    context = build_context(sections, settings.max_generation_context_chars, query=MODE_INSTRUCTIONS[mode])

    user_prompt = (
        f"Knowledge base content:\n{context}\n\n"
        f"Generate exactly {count} interview questions. {MODE_INSTRUCTIONS[mode]} "
        f"{DIFFICULTY_INSTRUCTIONS[difficulty]}\n"
        f"{_avoid_themes_line(avoid_themes)}"
        f"{_language_line(language)}"
        "Respond with a strict JSON array only, no prose, no markdown fences."
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    raw = await ai_client.complete(messages)
    questions = _parse_questions(raw)
    if questions is None:
        raw = await ai_client.complete(messages)
        questions = _parse_questions(raw)
    if questions is None:
        raise AIClientError("Could not parse AI response as JSON")
    return questions


def _parse_quiz_questions(raw: str) -> list[dict] | None:
    data = extract_json_value(raw, "[", "]")
    if not isinstance(data, list):
        return None

    questions: list[dict] = []
    for item in data:
        if not isinstance(item, dict):
            return None
        question = item.get("question")
        category = item.get("category")
        options = item.get("options")
        correct_index = item.get("correct_index")
        theme = item.get("theme")
        hint = item.get("hint")
        explanation = item.get("explanation")

        if not isinstance(question, str) or not isinstance(category, str):
            return None
        if not isinstance(options, list) or len(options) != 4:
            return None
        if not all(isinstance(opt, str) for opt in options):
            return None
        if not isinstance(correct_index, int) or isinstance(correct_index, bool):
            return None
        if not (0 <= correct_index < len(options)):
            return None
        if not all(isinstance(v, str) for v in (theme, hint, explanation)):
            return None

        questions.append(
            {
                "question": question,
                "category": category,
                "options": options,
                "correct_index": correct_index,
                "theme": theme,
                "hint": hint,
                "explanation": explanation,
            }
        )
    return questions


async def generate_quiz_questions(
    sections: list[Section],
    mode: str,
    count: int,
    ai_client: AIProvider,
    difficulty: str = "medium",
    avoid_themes: list[str] | None = None,
    language: str = "en",
) -> list[dict]:
    context = build_context(sections, settings.max_generation_context_chars, query=MODE_INSTRUCTIONS[mode])

    user_prompt = (
        f"Knowledge base content:\n{context}\n\n"
        f"Generate exactly {count} multiple-choice interview questions. {MODE_INSTRUCTIONS[mode]} "
        f"{DIFFICULTY_INSTRUCTIONS[difficulty]}\n"
        f"{_avoid_themes_line(avoid_themes)}"
        f"{_language_line(language)}"
        "Respond with a strict JSON array only, no prose, no markdown fences."
    )
    messages = [
        {"role": "system", "content": QUIZ_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    raw = await ai_client.complete(messages)
    questions = _parse_quiz_questions(raw)
    if questions is None:
        raw = await ai_client.complete(messages)
        questions = _parse_quiz_questions(raw)
    if questions is None:
        raise AIClientError("Could not parse AI response as JSON")
    return questions

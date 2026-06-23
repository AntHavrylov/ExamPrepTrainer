import re

from app.models import Document, Section

_WORD_RE = re.compile(r"[a-z0-9]+")


def _words(text: str) -> set[str]:
    return set(_WORD_RE.findall(text.lower()))


def _total_length(sections: list[Section]) -> int:
    total = 0
    for section in sections:
        total += len(f"## Section: {section.name}\n")
        for document in section.documents:
            total += len(f"### {document.title}\n{document.content}\n")
    return total


def _build_in_order(sections: list[Section], char_budget: int) -> str:
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


def _build_by_relevance(sections: list[Section], char_budget: int, query: str) -> str:
    query_words = _words(query)
    entries: list[tuple[int, Section, Document]] = [
        (
            len(_words(f"{section.name} {document.title} {document.content}") & query_words),
            section,
            document,
        )
        for section in sections
        for document in section.documents
    ]
    entries.sort(key=lambda entry: entry[0], reverse=True)

    parts: list[str] = []
    remaining = char_budget
    for _, section, document in entries:
        if remaining <= 0:
            break
        chunk = f"### [{section.name}] {document.title}\n{document.content}\n"
        appended = chunk[:remaining]
        parts.append(appended)
        remaining -= len(appended)
    return "".join(parts)


def build_context(sections: list[Section], char_budget: int, query: str = "") -> str:
    """Concatenate section/document content up to char_budget.

    If everything fits, content is emitted in stored order. Otherwise, when a
    query is given, documents are ranked by keyword overlap with it so the
    most relevant notes survive truncation instead of whatever happens to
    come first in document order.
    """
    if not query or _total_length(sections) <= char_budget:
        return _build_in_order(sections, char_budget)
    return _build_by_relevance(sections, char_budget, query)

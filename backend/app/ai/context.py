from app.models import Section


def build_context(sections: list[Section], char_budget: int) -> str:
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

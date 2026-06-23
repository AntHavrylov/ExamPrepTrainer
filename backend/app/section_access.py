from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import Section


def get_owned_sections(db: Session, section_ids: list[int], user_id: int) -> list[Section]:
    sections: list[Section] = []
    for section_id in section_ids:
        section = db.get(Section, section_id)
        if section is None or section.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Section not found")
        sections.append(section)
    return sections

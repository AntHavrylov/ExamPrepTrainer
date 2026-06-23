from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.config import settings
from app.db import get_db
from app.models import Document, Section, User
from app.schemas import (
    DocumentCreate,
    DocumentRead,
    DocumentUpdate,
    SectionCreate,
    SectionRead,
    SectionWithDocuments,
)

router = APIRouter(tags=["sections"])


def _get_owned_section(db: Session, section_id: int, user_id: int) -> Section:
    section = db.get(Section, section_id)
    if section is None or section.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Section not found")
    return section


def _get_owned_document(db: Session, document_id: int, user_id: int) -> Document:
    document = db.get(Document, document_id)
    if document is None or document.section.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return document


@router.post("/sections", response_model=SectionRead, status_code=status.HTTP_201_CREATED)
def create_section(
    payload: SectionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Section:
    section_count = db.scalar(
        select(func.count()).select_from(Section).where(Section.user_id == current_user.id)
    )
    if section_count >= settings.max_sections_per_user:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Maximum number of sections reached",
        )

    section = Section(user_id=current_user.id, name=payload.name, description=payload.description)
    db.add(section)
    db.commit()
    db.refresh(section)
    return section


@router.get("/sections", response_model=list[SectionRead])
def list_sections(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Section]:
    return list(db.scalars(select(Section).where(Section.user_id == current_user.id)))


@router.get("/sections/{section_id}", response_model=SectionWithDocuments)
def get_section(
    section_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Section:
    return _get_owned_section(db, section_id, current_user.id)


@router.post(
    "/sections/{section_id}/documents",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
)
def add_document(
    section_id: int,
    payload: DocumentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Document:
    section = _get_owned_section(db, section_id, current_user.id)
    document = Document(section_id=section.id, title=payload.title, content=payload.content)
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


@router.put("/documents/{document_id}", response_model=DocumentRead)
def update_document(
    document_id: int,
    payload: DocumentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Document:
    document = _get_owned_document(db, document_id, current_user.id)
    document.title = payload.title
    document.content = payload.content
    db.commit()
    db.refresh(document)
    return document


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    document = _get_owned_document(db, document_id, current_user.id)
    db.delete(document)
    db.commit()

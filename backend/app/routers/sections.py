from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.config import settings
from app.db import get_db
from app.models import Document, Section, User
from app.question_pool import remove_orphaned_bank_rows
from app.schemas import (
    DocumentCreate,
    DocumentRead,
    DocumentUpdate,
    SectionCreate,
    SectionRead,
    SectionWithDocuments,
)

router = APIRouter(tags=["sections"])

ALLOWED_UPLOAD_EXTENSIONS = (".md", ".txt")


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


@router.delete("/sections/{section_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_section(
    section_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    section = _get_owned_section(db, section_id, current_user.id)
    db.delete(section)
    db.commit()
    # The section's own notes are gone via cascade; any pooled questions that
    # were generated for it (alone or combined with other sections) can never
    # be matched again, so sweep those out too instead of leaving dead rows.
    remove_orphaned_bank_rows(db, current_user.id)


def _create_document(db: Session, section: Section, payload: DocumentCreate) -> Document:
    document = Document(section_id=section.id, title=payload.title, content=payload.content)
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


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
    return _create_document(db, section, payload)


@router.post(
    "/sections/{section_id}/documents/upload",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    section_id: int,
    file: UploadFile,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Document:
    section = _get_owned_section(db, section_id, current_user.id)

    filename = file.filename or ""
    if not filename.lower().endswith(ALLOWED_UPLOAD_EXTENSIONS):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Only {', '.join(ALLOWED_UPLOAD_EXTENSIONS)} files are supported",
        )

    raw = await file.read()
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="File must be UTF-8 encoded text",
        ) from exc

    title = Path(filename).stem or filename
    try:
        payload = DocumentCreate(title=title[:255], content=content)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc

    return _create_document(db, section, payload)


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

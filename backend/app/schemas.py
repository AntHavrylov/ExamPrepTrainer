from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.config import settings


class UserCreate(BaseModel):
    email: EmailStr
    password: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class SectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1000)


class SectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    created_at: datetime


class DocumentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=settings.max_document_content_length)


class DocumentUpdate(DocumentCreate):
    pass


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    section_id: int
    title: str
    content: str
    updated_at: datetime


class SectionWithDocuments(SectionRead):
    documents: list[DocumentRead] = []


class GenerateQuestionsRequest(BaseModel):
    section_ids: list[int] = Field(min_length=1)
    mode: Literal["technical", "behavioral", "mixed"] = "mixed"
    count: int = Field(default=5, ge=1, le=settings.max_questions_per_generate)


class QuestionRead(BaseModel):
    question: str
    category: str


class EvaluateAnswerRequest(BaseModel):
    question: str = Field(min_length=1)
    answer: str = Field(min_length=1)
    section_ids: list[int] = Field(default_factory=list)


class EvaluationRead(BaseModel):
    score: int
    feedback: str
    strengths: list[str]
    gaps: list[str]

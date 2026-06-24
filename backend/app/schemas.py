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
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


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


class StartSessionRequest(BaseModel):
    section_ids: list[int] = Field(min_length=1)
    mode: Literal["technical", "behavioral", "mixed"] = "mixed"
    format: Literal["open_ended", "quiz"] = "open_ended"
    difficulty: Literal["easy", "medium", "hard"] = "medium"


class SessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    mode: str
    format: str
    difficulty: str
    section_ids: list[int]
    started_at: datetime
    finished_at: datetime | None


class NextQuestionRead(BaseModel):
    attempt_id: int
    question: str
    category: str
    options: list[str] | None = None
    hint: str


class AnswerRequest(BaseModel):
    answer: str | None = Field(default=None, min_length=1)
    selected_index: int | None = Field(default=None, ge=0)


class AnswerResultRead(BaseModel):
    attempt_id: int
    format: str
    score: int
    feedback: str
    strengths: list[str] = []
    gaps: list[str] = []
    correct_index: int | None = None
    is_correct: bool | None = None
    explanation: str | None = None


class AttemptSummaryRead(BaseModel):
    id: int
    question: str
    category: str
    format: str
    options: list[str] | None = None
    selected_index: int | None = None
    correct_index: int | None = None
    answer: str | None = None
    score: int | None = None
    feedback: str | None = None
    created_at: datetime
    hint: str | None = None
    explanation: str | None = None


class SessionSummaryRead(SessionRead):
    attempts: list[AttemptSummaryRead] = []
    average_score: float | None = None


class ScorePoint(BaseModel):
    attempt_id: int
    created_at: datetime
    score: int


class TopicStat(BaseModel):
    section_id: int
    section_name: str
    average_score: float
    attempt_count: int


class StatsRead(BaseModel):
    total_attempts: int
    average_score: float | None
    score_history: list[ScorePoint]
    weakest_topics: list[TopicStat]


class ApiKeyStatusRead(BaseModel):
    has_key: bool
    model: str | None = None


class ApiKeySaveRequest(BaseModel):
    api_key: str = Field(min_length=1)
    model: str = Field(min_length=1)


class ModelOption(BaseModel):
    id: str
    name: str
    context_length: int | None = None

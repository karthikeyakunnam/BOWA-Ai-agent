"""
BOWA (Brain On World Alerts) - FastAPI Backend

REST API for priority news, student roadmaps, job recommendations, and
skill gap analysis.
"""

from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from services.brain import process_user_request
from services.conversation import handle_user_message
from services.jobs import get_job_recommendation_response
from services.news import get_priority_news
from services.scheduler import get_latest_user_result, start_scheduler
from services.student import get_student_roadmap


app = FastAPI(
    title="BOWA API",
    description="Brain On World Alerts backend APIs.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class StudentRequest(BaseModel):
    branch: str = Field(..., examples=["CSE"])


class JobsRequest(BaseModel):
    role: str = Field(..., examples=["Frontend Developer"])
    skills: list[str] = Field(default_factory=list, examples=[["HTML", "CSS"]])


class BowaRequest(BaseModel):
    user_id: str | None = Field(default=None, examples=["123"])
    user_type: str | None = Field(default=None, examples=["student"])
    branch: str | None = Field(default=None, examples=["CSE"])
    goal: str | None = Field(default=None, examples=["Data Analyst"])
    role: str | None = Field(default=None, examples=["Frontend Developer"])
    skills: list[str] = Field(default_factory=list, examples=[["Python"]])


class ChatRequest(BaseModel):
    user_id: str = Field(default="default", examples=["karthikeya"])
    message: str = Field(..., examples=["Help me plan my study"])
    mode: str = Field(default="General", examples=["Study"])


@app.on_event("startup")
def startup_event() -> None:
    """Start background automation when FastAPI starts."""
    start_scheduler()


@app.get("/")
def serve_ui() -> FileResponse:
    """Serve the BOWA web UI."""
    return FileResponse("index.html")


@app.get("/health")
def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {
        "status": "ok",
        "message": "BOWA API is running"
    }


@app.get("/news")
def news() -> list[dict[str, Any]]:
    """Fetch and return classified priority news."""
    return get_priority_news()


@app.post("/student")
def student(payload: StudentRequest) -> dict[str, Any]:
    """Return a structured learning roadmap for a student branch."""
    return get_student_roadmap(payload.branch)


@app.post("/jobs")
def jobs(payload: JobsRequest) -> dict[str, Any]:
    """Return job recommendations and skill gap analysis."""
    return get_job_recommendation_response(payload.role, payload.skills)


@app.post("/bowa")
def bowa(payload: BowaRequest) -> dict[str, Any]:
    """Run the unified BOWA brain layer."""
    return process_user_request(payload.model_dump(exclude_unset=True))


@app.post("/chat")
def chat(payload: ChatRequest) -> dict[str, Any]:
    """Conversational chat endpoint for BOWA."""
    return handle_user_message(
        payload.user_id,
        payload.message,
        payload.mode,
    )


@app.get("/results/{user_id}")
def results(user_id: str) -> dict[str, Any]:
    """Return the latest scheduled BOWA result for a user."""
    return get_latest_user_result(user_id)

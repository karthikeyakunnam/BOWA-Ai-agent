"""
BOWA (Brain On World Alerts) - FastAPI Backend

REST API for priority news, student roadmaps, job recommendations, and
skill gap analysis.
"""

import logging
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from services.brain import process_user_request
from services.conversation import handle_user_message, handle_user_message_stream
from services.jobs import get_job_recommendation_response
from services.llm import get_runtime_info
from services.news import get_priority_news
from services.proactive import get_user_notifications
from services.scheduler import get_latest_user_result, start_scheduler
from services.student import get_student_roadmap


logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:%(name)s:%(message)s",
)

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
def health_check() -> dict[str, Any]:
    """Health check endpoint."""
    return {
        "status": "ok",
        "message": "BOWA API is running",
        "llm": get_runtime_info(),
    }


@app.get("/architecture")
def architecture() -> dict[str, Any]:
    """Return the modular BOWA AI system architecture."""
    return {
        "base_model": {
            "providers": ["Groq Llama 3 or Mixtral", "Local Transformers inference"],
            "note": "BOWA does not train a foundation model from scratch.",
        },
        "fine_tuning": {
            "method": "LoRA / QLoRA adapters via PEFT + TRL",
            "entrypoints": ["training/prepare_dataset.py", "training/finetune.py"],
        },
        "memory_layer": {
            "persistent_profile": "memory.json",
            "conversation_history": "state.json",
            "semantic_recall": "ChromaDB persistent collection with JSON fallback",
        },
        "tool_system": ["job search", "news engine", "study roadmap", "planner/tracker"],
        "action_engine": "services/actions.py selects and executes deterministic actions before any LLM call.",
        "orchestrator": "services/conversation.py detects intent, decides an action, executes it, then asks the LLM only to render the structured result.",
        "response_layer": "System prompt and formatter enforce direct, practical, motivating BOWA tone.",
        "optimization": ["diskcache news cache", "streaming endpoint", "provider timeout", "offline fallback routing"],
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
    """Conversational chat endpoint for BOWA (Non-streaming)."""
    return handle_user_message(
        payload.user_id,
        payload.message,
        payload.mode,
    )

@app.post("/chat/stream")
def chat_stream(payload: ChatRequest):
    """Streaming conversational chat endpoint for BOWA."""
    return StreamingResponse(
        handle_user_message_stream(
            payload.user_id,
            payload.message,
            payload.mode,
        ),
        media_type="text/event-stream"
    )


@app.get("/results/{user_id}")
def results(user_id: str) -> dict[str, Any]:
    """Return the latest scheduled BOWA result for a user."""
    return get_latest_user_result(user_id)


@app.get("/notifications/{user_id}")
def notifications(user_id: str) -> list[dict[str, Any]]:
    """Return the latest proactive notifications for a user."""
    return get_user_notifications(user_id)

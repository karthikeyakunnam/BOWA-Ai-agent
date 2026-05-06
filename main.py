"""
BOWA (Brain On World Alerts) - FastAPI Backend

REST API for priority news, student roadmaps, job recommendations, and
skill gap analysis.
"""

import logging
import os
import threading
from typing import Any

from fastapi import Depends, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from models import User
from services.brain import process_user_request
from services.checkin import generate_checkin
from services.conversation import handle_user_message, handle_user_message_stream
from services.daily_summary import generate_daily_summary
from services.jobs import get_job_recommendation_response
from services.llm import get_runtime_info
from services.memory import calculate_habit_score, load_user_memory
from services.news import get_priority_news
from services.proactive import get_user_notifications
from services.execution import get_session_status
from services.event_bus import register_manager
from services.scheduler import get_latest_user_result, start_scheduler
from services.student import get_student_roadmap
from services.streak import get_user_streak
from services.weekly_insights import generate_weekly_insight


# Auth setup - commented out for now
# SECRET = os.getenv("SECRET", "your-secret-key")

# bearer_transport = BearerTransport(tokenUrl="auth/login")

# def get_jwt_strategy() -> JWTStrategy:
#     return JWTStrategy(secret=SECRET, lifetime_seconds=3600)

# auth_backend = AuthenticationBackend(
#     name="jwt",
#     transport=bearer_transport,
#     get_strategy=get_jwt_strategy,
# )

# database = SQLAlchemyUserDatabase(get_db, User)
# fastapi_users = FastAPIUsers(database, [auth_backend])

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:%(name)s:%(message)s",
)

app = FastAPI(
    title="BOWA API",
    description="Brain On World Alerts backend APIs.",
    version="1.0.0"
)


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: dict[str, WebSocket] = {}
        self.lock = threading.Lock()

    async def connect(self, user_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        with self.lock:
            self.active_connections[user_id] = websocket
        logging.getLogger(__name__).info("bowa_ws connected user=%s", user_id)

    async def disconnect(self, user_id: str) -> None:
        with self.lock:
            self.active_connections.pop(user_id, None)
        logging.getLogger(__name__).info("bowa_ws disconnected user=%s", user_id)

    async def send(self, user_id: str, message: Any) -> None:
        websocket = None
        with self.lock:
            websocket = self.active_connections.get(user_id)

        if not websocket:
            return

        try:
            if isinstance(message, dict):
                await websocket.send_json(message)
            else:
                await websocket.send_text(str(message))
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "bowa_ws send failed user=%s error=%s",
                user_id,
                exc,
            )


manager = ConnectionManager()
register_manager(manager)

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
async def startup_event() -> None:
    """Start background automation when FastAPI starts."""
    register_manager(manager)
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
    user_id = "guest"
    return handle_user_message(
        user_id,
        payload.message,
        payload.mode,
    )

@app.post("/chat/stream")
def chat_stream(payload: ChatRequest):
    """Streaming conversational chat endpoint for BOWA."""
    user_id = "guest"
    return StreamingResponse(
        handle_user_message_stream(
            user_id,
            payload.message,
            payload.mode,
        ),
        media_type="text/event-stream"
    )


# WebSocket for real-time updates
@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    await manager.connect(user_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(user_id)


@app.get("/results/{user_id}")
def results(user_id: str) -> dict[str, Any]:
    """Return the latest scheduled BOWA result for a user."""
    return get_latest_user_result(user_id)


@app.get("/notifications/{user_id}")
def notifications(user_id: str) -> list[dict[str, Any]]:
    """Return the latest proactive notifications for a user."""
    return get_user_notifications(user_id)


@app.get("/execution/{user_id}")
def execution_status(user_id: str) -> dict[str, Any]:
    """Return the current execution session status for a user."""
    return get_session_status(user_id)


@app.get("/habit/{user_id}")
def habit_data(user_id: str) -> dict[str, Any]:
    """Return daily habit data for UI."""
    user_state = load_user_memory(user_id) or {"user_id": user_id}
    checkin = generate_checkin(user_state)
    daily_summary = generate_daily_summary(user_id)
    habit_score = calculate_habit_score(user_id)
    streak = get_user_streak(user_id)["current_streak"]
    weekly_insight = generate_weekly_insight(user_id)

    return {
        "checkin": checkin,
        "daily_summary": daily_summary,
        "habit_score": habit_score,
        "streak": streak,
        "weekly_insight": weekly_insight,
    }

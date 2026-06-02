<div align="center">

# BOWA

**Brain On World Alerts**

An AI-powered decision intelligence system that converts goals into focused actions through planning, execution tracking, news intelligence, behavioral feedback loops, and adaptive personality.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg)](https://fastapi.tiangolo.com)
[![LLM](https://img.shields.io/badge/LLM-Groq%20Llama%203-orange.svg)](https://groq.com)
[![GitHub stars](https://img.shields.io/github/stars/karthikeyakunnam/BOWA-Ai-agent?style=social)](https://github.com/karthikeyakunnam/BOWA-Ai-agent)
[![GitHub forks](https://img.shields.io/github/forks/karthikeyakunnam/BOWA-Ai-agent?style=social)](https://github.com/karthikeyakunnam/BOWA-Ai-agent/fork)
[![GitHub issues](https://img.shields.io/github/issues/karthikeyakunnam/BOWA-Ai-agent)](https://github.com/karthikeyakunnam/BOWA-Ai-agent/issues)
[![GitHub last commit](https://img.shields.io/github/last-commit/karthikeyakunnam/BOWA-Ai-agent)](https://github.com/karthikeyakunnam/BOWA-Ai-agent/commits/main)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](https://github.com/karthikeyakunnam/BOWA-Ai-agent/blob/main/LICENSE)

</div>

---

## Why BOWA Exists

Most AI assistants answer questions. BOWA drives execution.

The problem isn't access to information — it's the gap between *knowing* and *doing*:

| Problem | How BOWA Addresses It |
|---|---|
| **Attention Fragmentation** | Mode isolation forces single-domain focus (Study, Jobs, News, Tracker) |
| **Goal Abandonment** | Trajectory engine tracks consistency over time, detects drops, and escalates |
| **Information Overload** | News intelligence scores, classifies, and filters articles by personal relevance |
| **Lack of Execution Systems** | Timed execution sessions with expiry detection, follow-through measurement, and streak tracking |
| **No Behavioral Feedback** | Reflection, strategy, and reward engines adapt difficulty and tone per user |

BOWA is not a chatbot. It is a **state-driven execution system** where the LLM never controls product logic — it only renders structured action results into human language.

---

## Core Capabilities

| Capability | Description | Module |
|---|---|---|
| **Conversation Engine** | Intent detection → state evaluation → action execution → LLM rendering pipeline | `conversation.py` |
| **Goal Management** | Centralized goal storage, progress tracking, urgency evaluation, gap analysis | `goal_engine.py` |
| **Execution Engine** | Timed sessions with running/expired/completed/failed states, duration adaptation | `execution.py` |
| **Multi-Step Planner** | Generates structured plans for complex goals, tracks step-by-step progress | `planner_engine.py` |
| **News Intelligence** | Fetch → classify → score → filter pipeline with adaptive user preferences | `news_service.py`, `news_feedback.py` |
| **Watch-to-Action** | Watched news items auto-convert to execution tasks after 24h based on confidence | `scheduler.py` |
| **Behavior Correction** | Missed high-urgency items from daily summaries inject into next-day plans | `scheduler.py` |
| **Mode Isolation** | Separate state per mode (General, Study, Jobs, News, Tracker) with independent history | `state.py` |
| **Proactive Guidance** | Consistency drop alerts, inactivity nudges, execution follow-ups, news escalation | `proactive.py` |
| **Adaptive Personality** | Detects user type (new/struggling/inconsistent/disciplined) and adapts tone | `personality.py` |
| **Event Timeline** | Chronological audit trail of all system events per user (100 events retained) | `event_timeline.py` |
| **Health Diagnostics** | Database, memory, scheduler, WebSocket, and session validation in one endpoint | `health.py` |
| **Prediction Engine** | Pattern-based proactive session triggers (active hours, consistency trends) | `predictor.py` |
| **Streak & Rewards** | Consecutive-day tracking with milestone rewards and comeback detection | `streak.py`, `reward.py` |
| **Semantic Memory** | ChromaDB vector store with JSON keyword fallback for long-term recall | `vector_memory.py` |
| **Daily Intelligence** | End-of-day summaries with news takeaways, personal impact, and recommendations | `daily_summary.py` |

---

## System Architecture

```mermaid
graph TB
    User([User / Web UI]) -->|HTTP / WebSocket| FastAPI[FastAPI Server]

    FastAPI --> ConvEngine[Conversation Engine]
    FastAPI --> BrainLayer[Brain Layer]
    FastAPI --> NewsAPI[News Endpoints]
    FastAPI --> ExecAPI[Execution Endpoints]

    ConvEngine --> IntentDetect[Intent Detection]
    IntentDetect --> StateEval[State Evaluation]
    StateEval --> ActionEngine[Action Engine]
    ActionEngine --> ExecEngine[Execution Engine]
    ActionEngine --> PlannerEngine[Planner Engine]

    ConvEngine --> Reflection[Reflection Engine]
    ConvEngine --> Strategy[Strategy Engine]
    ConvEngine --> ResponseBuilder[Response Builder]
    ResponseBuilder --> LLM[LLM Provider]
    ResponseBuilder --> Formatter[Response Formatter]

    subgraph Intelligence Layer
        NewsService[News Service]
        NewsFeedback[News Feedback & Learning]
        DailySummary[Daily Summary]
        DailyNewsSummary[Daily News Summary]
        Predictor[Prediction Engine]
    end

    subgraph Persistence Layer
        Memory[(memory.json)]
        State[(state.json)]
        ExecSessions[(execution_sessions.json)]
        Timeline[(event_timeline.json)]
        Notifications[(notifications.json)]
        Results[(results.json)]
        VectorDB[(ChromaDB / JSON Fallback)]
        PostgreSQL[(PostgreSQL)]
    end

    subgraph Background Systems
        Scheduler[Scheduler - 5min loop]
        Proactive[Proactive Engine]
        EventBus[Event Bus - WebSocket]
    end

    ActionEngine --> Memory
    ActionEngine --> State
    ExecEngine --> ExecSessions
    ExecEngine --> Timeline
    ConvEngine --> VectorDB
    NewsService --> NewsFeedback
    Scheduler --> Proactive
    Scheduler --> Predictor
    Scheduler --> NewsService
    Proactive --> EventBus
    EventBus --> User

    LLM -->|Groq API| GroqCloud[Groq Cloud - Llama 3]
    LLM -->|Local| LocalModel[Transformers - Llama 3 8B]
```

---

## Request Flow

```mermaid
sequenceDiagram
    participant U as User
    participant F as FastAPI
    participant C as Conversation Engine
    participant I as Intent Detection
    participant S as State Manager
    participant A as Action Engine
    participant E as Execution Engine
    participant R as Reflection Engine
    participant ST as Strategy Engine
    participant L as LLM Provider
    participant M as Memory Layer
    participant T as Event Timeline

    U->>F: POST /chat {message, mode, user_id}
    F->>C: handle_user_message()
    T->>T: append_event("message_received")
    C->>M: load_user_memory()
    C->>I: detect_intent(message, mode)
    I-->>C: intent (jobs/study/tracker/news/general/greeting)
    C->>S: get_user_state()
    C->>C: analyze_user_state() → {intent, mood, clarity, urgency}
    C->>R: analyze_performance(state, last_action, message)
    R-->>C: {success, adjustment, reason}
    C->>ST: choose_strategy(state, reflection, intent)
    ST-->>C: {strategy, reason}
    C->>A: decide_action() → execute_action()
    A->>S: update_user_state()
    A-->>C: action_result (structured data)
    C->>C: update_trajectory()
    C->>L: generate_response(context, structured_data)
    L-->>C: human-readable reply
    C->>C: format_response() → adapt_message()
    C->>C: _avoid_repeat() → _regenerate_reply_if_similar()
    C->>M: save_user_memory(), add_memory()
    C-->>F: {reply, action, reason, state, structured}
    F-->>U: JSON Response
```

---

## Project Structure

```
bowa/
├── main.py                          # FastAPI app, endpoints, WebSocket manager, startup
├── models.py                        # SQLAlchemy ORM models (User, Memory, Trajectory, ExecutionSession, Notification, Analytics)
├── database.py                      # PostgreSQL connection via SQLAlchemy
├── health.py                        # System health diagnostics and scheduler monitoring
├── event_timeline.py                # Centralized event timeline with dynamic interceptors
├── index.html                       # Single-page web UI (44KB)
├── requirements.txt                 # Python dependencies
├── Dockerfile                       # Container configuration
├── .env.example                     # Environment variable template
│
├── services/
│   ├── conversation.py              # Core conversation engine (950 lines) — intent → action → render
│   ├── actions.py                   # Deterministic action engine — decide and execute without LLM
│   ├── action_selector.py           # Dynamic action selection layer (advisory)
│   ├── brain.py                     # Unified decision engine for /bowa endpoint
│   ├── execution.py                 # Execution session lifecycle (create → run → expire → complete)
│   ├── planner_engine.py            # Multi-step plan generator for complex goals
│   ├── planner.py                   # Time-block plan builder for daily tracking
│   ├── scheduler.py                 # Background automation loop (5-min interval)
│   ├── proactive.py                 # Proactive notifications with adaptive cooldown
│   ├── predictor.py                 # User pattern analysis and proactive session triggers
│   │
│   ├── news_service.py              # News fetch → filter → classify → prioritize → score
│   ├── news_feedback.py             # Feedback capture, preference learning, adaptive scoring
│   ├── daily_news_summary.py        # End-of-day LLM-powered news intelligence report
│   ├── daily_summary.py             # Daily intelligence report (sessions, streak, recommendations)
│   ├── daily_plan.py                # Daily task list generator based on goal urgency
│   │
│   ├── state.py                     # JSON-backed per-mode conversation state persistence
│   ├── memory.py                    # JSON-backed user memory (profile, scores, preferences)
│   ├── vector_memory.py             # ChromaDB semantic memory with JSON keyword fallback
│   ├── trajectory.py                # Multi-session progress tracking (unclear → advanced)
│   ├── goal_engine.py               # Goal storage, progress evaluation, session recording
│   │
│   ├── personality.py               # Adaptive tone engine (supportive/firm/respectful/clear)
│   ├── reflection.py                # Post-action performance evaluation
│   ├── strategy.py                  # Adaptive strategy selection (support/simplify/challenge/push)
│   ├── response_builder.py          # Structured response composition for LLM
│   ├── reward.py                    # Streak-based reward generation (milestone/recovery/failure)
│   ├── streak.py                    # Consecutive-day streak tracking
│   │
│   ├── llm.py                       # LLM provider layer (Groq + local Transformers)
│   ├── formatter.py                 # Response control — removes fluff, enforces action language
│   ├── behavior.py                  # System prompt and deterministic action plan builder
│   ├── event_bus.py                 # Real-time WebSocket event delivery
│   ├── notifications.py             # Update detection for scheduler-generated alerts
│   ├── checkin.py                   # User check-in message generator
│   ├── insights.py                  # Readiness scoring and skill gap insights
│   ├── weekly_insights.py           # Weekly trend analysis
│   │
│   ├── student.py                   # Branch-specific learning roadmaps
│   ├── jobs.py                      # Job recommendation engine with skill gap analysis
│   ├── tools.py                     # LLM tool definitions for function calling
│   └── __init__.py
│
├── tests/
│   ├── conftest.py                  # Shared fixtures — JSON store isolation per test
│   ├── test_conversation.py         # 32 tests — intent detection, message handling, repeat prevention
│   ├── test_execution.py            # 17 tests — session lifecycle, news tasks, outcome classification
│   ├── test_health.py               # 5 tests — system health diagnostics validation
│   ├── test_memory.py               # 25 tests — memory persistence, merge, habit scoring
│   ├── test_mode_isolation.py       # 4 tests — cross-mode state separation
│   ├── test_news.py                 # 13 tests — news pipeline, feedback, adaptive scoring
│   ├── test_planner.py              # 23 tests — plan generation, step tracking, greeting skip
│   ├── test_scheduler.py            # 22 tests — scheduler loop, watch list, behavior correction
│   └── test_timeline.py             # 10 tests — event append, interceptors, timeline retrieval
│
└── training/
    ├── prepare_dataset.py           # Dataset preparation for fine-tuning
    ├── finetune.py                  # LoRA/QLoRA fine-tuning via PEFT + TRL
    └── data/                        # Training data directory
```

---

## Intelligence Pipeline

Every user message flows through a multi-stage intelligence pipeline before a response is generated. The LLM is invoked **only at the final rendering step** — all decision logic is deterministic.

```mermaid
graph LR
    A[User Message] --> B[Intent Detection]
    B --> C[State Evaluation]
    C --> D[Goal Context Injection]
    D --> E[Reflection Engine]
    E --> F[Strategy Selection]
    F --> G[Plan Generation]
    G --> H[Action Decision & Execution]
    H --> I[Trajectory Update]
    I --> J[Response Builder]
    J --> K[LLM Rendering]
    K --> L[Formatter & Personality Adaptation]
    L --> M[Repeat Prevention]
    M --> N[Memory Persistence]
    N --> O[Final Response]

    style H fill:#ff6b35,color:#fff
    style K fill:#2196f3,color:#fff
```

| Stage | Implementation | Purpose |
|---|---|---|
| **Intent Detection** | `detect_intent()` in `conversation.py` | Keyword matching against jobs/study/tracker/news/greeting patterns |
| **State Evaluation** | `analyze_user_state()` | Classifies mood (lazy/confused/focused/curious), clarity (clear/vague), urgency (high/medium/low) |
| **Goal Context** | `load_user_memory()` | Injects last goal and daily plan into message context |
| **Reflection** | `analyze_performance()` in `reflection.py` | Evaluates if previous action succeeded → suggests reduce/change/increase/continue |
| **Strategy** | `choose_strategy()` in `strategy.py` | Selects interaction strategy: support, simplify, challenge, or push |
| **Plan Generation** | `generate_plan()` in `planner_engine.py` | Creates multi-step plans for large goals (study/jobs/tracker intents) |
| **Action Decision** | `decide_action()` → `execute_action()` in `actions.py` | Deterministic action selection and execution without LLM |
| **Trajectory Update** | `update_trajectory()` in `trajectory.py` | Updates stage (unclear→planning→executing→consistent→advanced) and consistency score |
| **Response Builder** | `build_response()` in `response_builder.py` | Composes structured data with tone, pressure, plan step, strategy, reflection, reward |
| **LLM Rendering** | `generate_response()` in `llm.py` | Converts structured data to natural language via Groq Llama 3 |
| **Formatter** | `format_response()` in `formatter.py` | Strips fluff phrases, rewrites vague language, enforces action-oriented tone |
| **Personality** | `adapt_message()` in `personality.py` | Adjusts tone based on user type (struggling → supportive, disciplined → respectful) |
| **Repeat Prevention** | `_avoid_repeat()`, `_regenerate_reply_if_similar()` | Similarity detection and fallback generation |
| **Memory** | `add_memory()` in `vector_memory.py` | Persists turn to semantic vector memory for future recall |

---

## News Intelligence System

BOWA's news system goes beyond simple aggregation. It builds a **per-user preference model** that learns from engagement patterns and converts insights into execution tasks.

### Pipeline

```mermaid
graph TB
    A[NewsAPI Fetch] -->|Cached 1h| B[Deduplicate & Filter]
    B --> C[Classify Category]
    C --> D[Assign Priority]
    D --> E[Calculate Urgency]
    E --> F[Apply User Preference Weights]
    F --> G[Adaptive Relevance Scoring]
    G --> H[Confidence Score Calculation]
    H --> I[Suggest Action: act / watch / ignore]
    I --> J[Sort by Relevance + Urgency]

    subgraph User Feedback Loop
        K[User Reacts] --> L[Capture Reaction]
        L --> M[Update Topic Weights]
        M --> N[Adjust Feedback Scores]
        N --> O[Update Preference Model]
        O -->|Next Fetch| F
    end

    subgraph Action Outcomes
        P[act] --> Q[Create Execution Session]
        R[watch] --> S[Add to Watch List]
        T[ignore] --> U[Log & Skip]
        S -->|After 24h| V{Confidence ≥ 70?}
        V -->|Yes| Q
        V -->|No| W[Prompt User]
    end
```

### Scoring System

| Component | Formula | Range |
|---|---|---|
| **Base Score** | `50 + priority_boost + category_match + keyword_overlap + stage_boost` | 0–100 |
| **Adaptive Score** | `base_score × user_preference_weight` | Weight: 0.5–1.5 |
| **Confidence Score** | `(topic_feedback_score × 100) + min(20, engagements × 2)` | 0–100 |
| **Action Suggestion** | `if confidence ≥ 70 AND score ≥ 75 → act` | act / watch / ignore |

### Preference Learning

- **Positive feedback** → topic score +0.1 (cap at 0.95)
- **Negative feedback** → topic score -0.15 (floor at 0.1)
- **3+ ignores on a topic** → topic weight ×0.7
- **Any acted engagement** → topic weight ×1.2 (cap at 1.5)
- **Time decay** → `e^(-days × 0.1)` applied to impact scores

---

## Execution System

Execution sessions are BOWA's core productivity mechanism — timed, tracked, and scored.

### Session Lifecycle

```mermaid
stateDiagram-v2
    [*] --> Created: create_one_session_task()
    Created --> Running: Session active
    Running --> Expired: duration elapsed
    Running --> Completed: User confirms "yes"
    Running --> Failed: User confirms "no"
    Expired --> Completed: User confirms "yes"
    Expired --> Failed: User confirms "no"

    Completed --> [*]: handle_session_completion()
    Failed --> [*]: handle_session_completion()

    note right of Running
        Duration adaptation:
        success_rate < 40% → 10-20 min
        40-70% → 20-30 min
        > 70% → 30-45 min
    end note

    note right of Completed
        Updates:
        • consistency_score ±0.1
        • streak tracking
        • goal progress
        • reward generation
        • reflection analysis
    end note
```

### Outcome Classification (News-Triggered Tasks)

| Outcome | Condition | Impact |
|---|---|---|
| `completed` | User confirms OR time ≥ 100% | confidence +10, high impact |
| `partial` | Time ≥ 50% without confirmation | confidence +5, medium impact |
| `abandoned` | Time < 50% without confirmation | confidence -5, low impact |

### Duration Adaptation

Task duration is dynamically adjusted based on past performance:

```
success_rate < 40%  → random(10, 20) minutes
40% ≤ rate ≤ 70%    → random(20, 30) minutes
rate > 70%          → random(30, 45) minutes
```

---

## Mode Architecture

BOWA implements **full mode isolation** — each mode maintains independent conversation state, history, and plan context.

```mermaid
graph TB
    subgraph User State Store
        direction TB
        UserEntry[User Entry]
        UserEntry --> ActiveMode[active_mode: "Study"]
        UserEntry --> Modes[modes]
        Modes --> General[general: {stage, history, plan}]
        Modes --> Study[study: {stage, history, plan}]
        Modes --> Jobs[jobs: {stage, history, plan}]
        Modes --> News[news: {stage, history, plan}]
        Modes --> Tracker[tracker: {stage, history, plan}]
    end
```

| Mode | Identity | Behavior |
|---|---|---|
| **General** | Direct, practical assistant | Detects intent from message, routes to appropriate domain |
| **Study** | Structured learning tutor | Generates branch-specific roadmaps (CSE, ECE, etc.), step-by-step plans |
| **Jobs** | Action-oriented career coach | Job search, skill gap analysis, resume/portfolio focus |
| **News** | Sharp, insightful analyst | Priority news with act/watch/ignore decisions, personalized scoring |
| **Tracker** | Strict accountability coach | Time-blocked daily plans, execution sessions, progress measurement |

**Isolation guarantees:**
- Each mode has its own `stage`, `history`, `last_action`, `active_plan`
- Switching modes preserves previous mode state
- Mode routing: message intent takes priority over active mode (configurable priority weighting)

---

## Event Timeline System

BOWA records a chronological audit trail of all significant system events per user.

### Tracked Events

| Event Type | Trigger | Metadata |
|---|---|---|
| `message_received` | User sends a message | `{message, mode}` |
| `goal_updated` | User sets/changes goal | `{goal}` |
| `execution_started` | Execution session created | `{task, duration, source_type, news_id, category}` |
| `execution_completed` | Session ends (any status) | `{task, completed, status}` |
| `notification_sent` | Proactive message delivered | `{message, reason}` |
| `plan_created` | New plan generated | `{goal, source}` |
| `plan_completed` | Plan marked complete | `{goal}` |
| `news_clicked` | User clicks a news item | `{title, category}` |

### Implementation Details

- **Storage**: `event_timeline.json` — JSON-backed with thread-safe locking
- **Retention**: Latest 100 events per user
- **Interceptors**: Dynamic monkey-patching captures events from `goal_engine`, `proactive`, and `state` modules without modifying their source code
- **API**: `GET /timeline/{user_id}` returns the full event list

---

## Health Monitoring

The `/system-health` endpoint aggregates diagnostics from all subsystems into a single response.

### Checks Performed

| Check | Source | What It Validates |
|---|---|---|
| Active Execution Sessions | `execution_sessions.json` | Count of running sessions within their time window |
| Active Plans | `state.json` | Count of uncompleted plans across all users |
| Unique Users | Memory + State + Execution stores | Union of all user IDs across persistence files |
| Pending Notifications | `notifications.json` | Total stored proactive messages |
| Scheduler Status | `scheduler._scheduler_thread` | Whether the background thread is alive |
| Memory Corruption | `memory.json` | JSON validity and structure validation |
| Database Connection | SQLAlchemy engine | `SELECT 1` ping test |
| WebSocket Connections | Connection manager | Active WebSocket count |
| Last Scheduler Run | Health monitor wrapper | Timestamp of most recent automation cycle |
| Last Error | Health monitor wrapper | Most recent scheduler exception |

### Sample Response

```json
{
  "active_sessions": 1,
  "active_plans": 3,
  "users": 2,
  "notifications_pending": 7,
  "scheduler_running": true,
  "memory_corruption_detected": false,
  "db_connected": true,
  "websocket_connections": 1,
  "last_scheduler_run": "2026-06-02T15:30:00+00:00",
  "last_error": null
}
```

---

## Behavioral Intelligence

BOWA adapts its behavior based on accumulated user data. These are the key metrics tracked and their computation:

| Metric | Computation | Used By |
|---|---|---|
| **Consistency Score** | `±0.1` per session completion/failure, `−0.15` for 36h+ gaps, `+0.08` for ≤30h gaps | Trajectory, personality, proactive |
| **Success Rate** | `(completed_sessions / total_sessions) × 100` | Duration adaptation, execution |
| **Confidence Score** | `(topic_feedback × 100) + min(20, engagements × 2)` | News action suggestions |
| **Impact Score** | Weighted average: `(prev × 0.7) + (new × 0.3)`, where high=80, medium=50, low=20 | News relevance |
| **Follow-Through Rate** | `acted_items / checked_items × 100` within 24h window | News feedback |
| **Habit Score** | `(streak × 0.4) + (success_rate × 0.4) + (consistency × 20)`, cap at 100 | Dashboard |
| **Streak** | Consecutive days with ≥1 completed session, resets on miss | Rewards, proactive |

### Trajectory Stages

```mermaid
graph LR
    Unclear --> Planning
    Planning --> Executing
    Executing --> Consistent
    Consistent --> Advanced
    Executing -.->|hesitation ≥ 2| Unclear
    Consistent -.->|gap > 36h| Executing

    style Unclear fill:#ff5722,color:#fff
    style Planning fill:#ff9800,color:#fff
    style Executing fill:#2196f3,color:#fff
    style Consistent fill:#4caf50,color:#fff
    style Advanced fill:#9c27b0,color:#fff
```

| Stage | Entry Condition |
|---|---|
| `unclear` | Clarification action or hesitation_count ≥ 2 |
| `planning` | Plan/jobs/news action with 0 completed steps |
| `executing` | Tracker/continue action with ≥ 1 completed step |
| `consistent` | consistency_score ≥ 0.45 AND completed_steps ≥ 2 |
| `advanced` | consistency_score ≥ 0.70 AND completed_steps ≥ 3 |

### Reward System

| Trigger | Reward Type | Message Style |
|---|---|---|
| First completion | `small` | "Good start. That's 1 in a row." |
| Streak 3/7/14 | `milestone` | "Good. That's {n} in a row. Keep it going." |
| Streak recovery | `recovery` | "You're back. That matters more than perfection." |
| Session failure | `failure` | "You broke the streak. Restart today." |

---

## API Endpoints

All endpoints discovered from `main.py`:

| Method | Route | Purpose | Request Body |
|---|---|---|---|
| `GET` | `/` | Serve web UI | — |
| `GET` | `/health` | Basic health check + LLM info | — |
| `GET` | `/system-health` | Full system diagnostics | — |
| `GET` | `/architecture` | System architecture metadata | — |
| `GET` | `/news` | Fetch classified priority news | `?user_id=` |
| `POST` | `/news/feedback` | Capture thumbs up/down on news | `NewsFeedbackRequest` |
| `POST` | `/news/action` | Track user action on news item | `NewsActionRequest` |
| `GET` | `/news/follow-through/{user_id}` | Check 24h follow-through on recommended actions | — |
| `GET` | `/news/stats/{user_id}` | Comprehensive news engagement statistics | — |
| `POST` | `/user/settings` | Update news frequency | `SettingsRequest` |
| `POST` | `/user/active_mode` | Switch active mode | `ActiveModeRequest` |
| `POST` | `/student` | Get branch-specific learning roadmap | `StudentRequest` |
| `POST` | `/jobs` | Get job recommendations + skill gap analysis | `JobsRequest` |
| `POST` | `/bowa` | Run unified brain layer | `BowaRequest` |
| `POST` | `/chat` | Conversational chat (non-streaming) | `ChatRequest` |
| `POST` | `/chat/stream` | Streaming chat via SSE | `ChatRequest` |
| `WS` | `/ws/{user_id}` | Real-time WebSocket for push notifications | — |
| `GET` | `/results/{user_id}` | Latest scheduler automation result | — |
| `GET` | `/notifications/{user_id}` | Proactive notification history | — |
| `GET` | `/execution/{user_id}` | Current execution session status | — |
| `GET` | `/state/{user_id}` | Comprehensive user state for dashboard | — |
| `GET` | `/habit/{user_id}` | Daily habit data (check-in, summary, score, streak) | — |
| `GET` | `/timeline/{user_id}` | Latest 100 timeline events | — |

---

## Testing & Validation

### Test Suite

| Test File | Tests | Coverage Area |
|---|---|---|
| `test_conversation.py` | 32 | Intent detection, mode routing, greeting handling, repeat prevention, news explain, execution follow-up |
| `test_memory.py` | 25 | Memory persistence, merge logic, habit score calculation, isolation |
| `test_planner.py` | 23 | Plan generation, step normalization, greeting skip, large goal detection |
| `test_scheduler.py` | 22 | Scheduler loop, watch list processing, behavior correction, daily plans |
| `test_execution.py` | 17 | Session lifecycle, duration adaptation, news task classification, outcome tracking |
| `test_news.py` | 13 | News pipeline, feedback capture, adaptive scoring, preference learning |
| `test_timeline.py` | 10 | Event append, interceptors, timeline retrieval, retention limits |
| `test_health.py` | 5 | System health diagnostics, memory corruption detection |
| `test_mode_isolation.py` | 4 | Cross-mode state separation, independent histories |

**Total: 151 tests across 9 test files**

### Test Infrastructure

- **Isolation**: `conftest.py` redirects all JSON stores to `tmp_path` — tests never touch production data
- **Cache clearing**: All module-level caches (`_memory_store_cache`, `_state_store_cache`, etc.) are reset per test
- **Fixtures**: `user_id`, `clean_memory`, `clean_state` helpers for consistent seeding

### Run Tests

```bash
pytest tests/ -v
```

---

## Technical Decisions

| Decision | Rationale |
|---|---|
| **FastAPI** | Async-capable, automatic OpenAPI docs, Pydantic validation, WebSocket support, streaming responses via `StreamingResponse` |
| **LLM as renderer, not controller** | The LLM converts structured action results into human language. All product logic (intent detection, action selection, state transitions) is deterministic. This prevents hallucination-driven decision making |
| **State-driven architecture** | Every user has a persistent state machine (stage, mode, plan, history). Responses are a function of state, not isolated messages. Enables multi-turn context, plan tracking, and progress measurement |
| **Execution sessions** | Timed tasks with explicit start/complete/fail lifecycle. Solves the "I'll do it later" problem by creating accountability through expiry detection and follow-up prompts |
| **Mode isolation** | Separate state per mode prevents cross-contamination. A study plan doesn't interfere with job search state. Each mode has its own stage progression |
| **Event timeline** | Chronological audit trail enables debugging, user behavior analysis, and system observability. Dynamic interceptors capture events without modifying source modules |
| **Proactive reminders** | Background scheduler runs every 5 minutes, detecting inactivity, consistency drops, expired sessions, and stale watch list items. Adaptive cooldown prevents notification fatigue (max 2/day, 6–12h between repeats) |
| **JSON persistence with in-memory cache** | Thread-safe JSON stores with module-level caches for low-latency reads. PostgreSQL models exist for production migration. This enables zero-infrastructure local development |
| **ChromaDB with JSON fallback** | Semantic memory via ChromaDB when available, falls back to keyword-based JSON matching. The app runs locally without any vector database |
| **Groq with local fallback** | Production uses Groq-hosted Llama 3 for low-latency inference. Local Transformers backend available for teams running their own hardware. Offline mode returns deterministic responses |

---

## What Makes BOWA Different

| Dimension | Traditional Chatbot | BOWA |
|---|---|---|
| **Architecture** | Stateless request-response | State machine with persistent trajectory |
| **Decision Making** | LLM decides everything | Deterministic action engine; LLM only renders output |
| **Memory** | Per-session context window | Persistent behavioral memory + semantic vector recall |
| **Responses** | Generic answers | Adaptive tone based on user type and consistency score |
| **Goals** | No goal tracking | Goal storage, progress measurement, urgency evaluation |
| **Execution** | No accountability | Timed sessions with expiry, follow-up, and streak tracking |
| **News** | Raw feed | Classified, scored, personalized with act/watch/ignore decisions |
| **Feedback** | None | Reflection → strategy → reward loop after every action |
| **Proactivity** | Waits for input | Background scheduler nudges, predicts, and escalates |
| **Repetition** | Often repeats | Multi-layer repeat prevention with similarity detection |

---

## Current Status

### Implemented Systems ✅

- Decision-driven conversation engine with 8 action types
- Multi-provider LLM layer (Groq + local Transformers)
- Execution session lifecycle with duration adaptation
- News intelligence pipeline with adaptive preference learning
- Watch-to-action conversion with confidence-based auto-triggers
- Per-mode state isolation with independent histories
- Background scheduler (5-min loop) with user automation
- Proactive notification engine with adaptive cooldown
- Event timeline with dynamic interceptors
- Prediction engine for pattern-based session triggers
- Streak and reward system with milestone detection
- Health monitoring with 10 diagnostic checks
- Daily intelligence summaries (sessions + news)
- Behavior correction from missed high-urgency items
- Semantic vector memory (ChromaDB) with JSON fallback
- Response formatter with fluff removal and action enforcement
- Adaptive personality engine (5 user types, 4 tones)
- 151 automated tests with full store isolation
- Single-page web UI
- Docker containerization
- Fine-tuning pipeline (LoRA/QLoRA via PEFT + TRL)

### In Progress 🔄

- PostgreSQL migration (ORM models defined, JSON stores primary)
- Authentication system (JWT strategy defined, commented out)
- User registration and login flow

### Future Roadmap 🗺️

- Migrate from JSON persistence to PostgreSQL for production scalability
- Enable JWT authentication and multi-user accounts
- Add real-time WebSocket dashboard updates
- Expand fine-tuning data pipeline with production conversation logs
- Integrate calendar/scheduling APIs for time-aware planning
- Add analytics dashboard for historical progress visualization

---

## Screenshots

> **Note**: Screenshots for the following views should be captured from the running application:

| View | Description |
|---|---|
| **Dashboard** | Main chat interface with status panel |
| **News Intelligence** | Priority news with relevance scores and action suggestions |
| **Execution Tracking** | Active session timer with task details |
| **Mode Switching** | Mode selector showing isolated contexts |
| **Timeline** | Chronological event history |

---

## Installation

### Prerequisites

- Python 3.11+
- PostgreSQL (optional — defaults to JSON persistence)
- [Groq API key](https://console.groq.com/) (optional — works offline with deterministic responses)
- [NewsAPI key](https://newsapi.org/) (optional — news features disabled without it)

### Setup

```bash
# Clone the repository
git clone https://github.com/karthikeyakunnam/BOWA-Ai-agent.git
cd BOWA-Ai-agent

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # macOS/Linux
# .venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your keys
```

---

## Running Locally

```bash
# Start the server
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Open the web UI
open http://localhost:8000

# Or use Docker
docker build -t bowa .
docker run -p 8000:8000 --env-file .env bowa
```

### Verify

```bash
# Health check
curl http://localhost:8000/health

# System diagnostics
curl http://localhost:8000/system-health

# Chat
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test", "message": "I want to learn SQL", "mode": "Study"}'
```

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `GROQ_API_KEY` | No | — | Groq API key for Llama 3 inference. Without it, BOWA runs in offline mode with deterministic responses |
| `NEWS_API_KEY` | No | — | NewsAPI key for live news fetching. Without it, news endpoints return empty results |
| `DATABASE_URL` | No | `postgresql://user:password@localhost/bowa` | PostgreSQL connection string |
| `SECRET` | No | `your-secret-key` | JWT secret for authentication (not yet active) |
| `BOWA_LLM_PROVIDER` | No | `groq` | LLM provider: `groq` or `local` |
| `BOWA_MODEL` | No | `llama-3.1-8b-instant` | Groq model name |
| `BOWA_LOCAL_MODEL` | No | `meta-llama/Meta-Llama-3-8B-Instruct` | Local Transformers model |
| `BOWA_LLM_TIMEOUT` | No | `20` | LLM request timeout in seconds |
| `BOWA_USE_CHROMA` | No | `0` | Set to `1` to enable ChromaDB vector memory |

---

## Codebase Statistics

| Metric | Value |
|---|---|
| **Total Source Lines** | ~8,500 |
| **Service Modules** | 38 |
| **Test Files** | 9 |
| **Test Cases** | 151 |
| **API Endpoints** | 22 (including WebSocket) |
| **Event Types Tracked** | 8 |
| **Behavioral Metrics** | 7 |
| **Trajectory Stages** | 5 |
| **Persistence Stores** | 7 (JSON) + 1 (PostgreSQL) + 1 (ChromaDB) |

---

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/your-feature`)
3. Commit your changes (`git commit -m 'Add your feature'`)
4. Push to the branch (`git push origin feature/your-feature`)
5. Open a Pull Request

---

## Author

**Karthikeya Unnam**

- GitHub: [@karthikeyakunnam](https://github.com/karthikeyakunnam)
- Email: karthikeyaunnam1364@gmail.com
- Project: [BOWA-Ai-agent](https://github.com/karthikeyakunnam/BOWA-Ai-agent)

---

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

---

<div align="center">

**BOWA** — Stop planning. Start executing.

⭐ Star this repo if you find it useful!

</div>

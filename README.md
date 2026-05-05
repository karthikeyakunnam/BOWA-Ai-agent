# BOWA AI

BOWA is a hybrid AI assistant for study, jobs, planning, and priority updates. It uses a strong existing model, then adds BOWA-specific memory, tools, orchestration, and optional LoRA adapters.

## Architecture

1. **Base Model**
   - Default: Groq-hosted Llama 3 via `GROQ_API_KEY`.
   - Optional: local Transformers inference with `BOWA_LLM_PROVIDER=local`.
   - No foundation model is trained from scratch.

2. **Fine-Tuning**
   - `training/prepare_dataset.py` creates a BOWA-specific JSONL dataset.
   - `training/finetune.py` trains LoRA / QLoRA adapters with PEFT + TRL.
   - Override the base model with `BOWA_FINETUNE_MODEL`, for example a Llama 3 or Mixtral instruct checkpoint.

3. **Memory Layer**
   - `memory.json`: persistent user profile and preferences.
   - `state.json`: conversation history and planner state.
   - `services/vector_memory.py`: ChromaDB semantic recall with a JSON fallback.

4. **Tool System**
   - `services/jobs.py`: job matching and skill gap analysis.
   - `services/news.py`: priority news engine with hourly cache.
   - `services/student.py`: study roadmap generator.
   - `services/planner.py`: planner and task tracker.

5. **Orchestrator**
   - `services/actions.py` is the Action Engine. It decides and executes `ask_clarification`, `generate_plan`, `show_jobs`, `show_news`, `create_tracker`, or `continue_flow`.
   - `services/conversation.py` detects intent, asks the Action Engine for the next action, executes it, and sends structured data to the LLM only for response rendering.
   - If Groq/local inference is not configured, BOWA still works through deterministic local rendering.

6. **Response Layer**
   - `services/behavior.py` and `services/formatter.py` enforce the BOWA voice: direct, practical, motivating.

7. **Optimization**
   - News caching with `diskcache`.
   - `/chat/stream` endpoint for streaming responses.
   - LLM timeout via `BOWA_LLM_TIMEOUT`.
   - Offline fallback to avoid a dead app when keys or model weights are missing.

## Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Open `http://127.0.0.1:8000`.

## Environment

```bash
GROQ_API_KEY=your_key
NEWS_API_KEY=optional_newsapi_key
BOWA_MODEL=llama3-70b-8192
BOWA_LLM_PROVIDER=groq
```

For local inference:

```bash
BOWA_LLM_PROVIDER=local
BOWA_LOCAL_MODEL=meta-llama/Meta-Llama-3-8B-Instruct
```

## Fine-Tune

```bash
python training/prepare_dataset.py
BOWA_FINETUNE_MODEL=meta-llama/Meta-Llama-3-8B-Instruct python training/finetune.py
```

The adapter output is saved to `training/bowa_model_adapters`.

## Key API Endpoints

- `GET /health`
- `GET /architecture`
- `POST /chat`
- `POST /chat/stream`
- `POST /bowa`
- `POST /jobs`
- `POST /student`
- `GET /news`

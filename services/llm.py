"""LLM provider layer for BOWA.

The production path uses Groq-hosted Llama 3 or Mixtral for low-latency
inference. A local Transformers backend is also available for teams that want
to run an instruct model on their own hardware.
"""

import json
import logging
import os
from functools import lru_cache
from typing import Any

from dotenv import load_dotenv

load_dotenv()

try:
    from groq import Groq
    HAS_GROQ = True
except ImportError:
    HAS_GROQ = False

try:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
    HAS_TRANSFORMERS = True
except ImportError:
    HAS_TRANSFORMERS = False


DEFAULT_GROQ_MODEL = "llama-3.1-8b-instant"
DEFAULT_LOCAL_MODEL = "meta-llama/Meta-Llama-3-8B-Instruct"
PROVIDER = os.environ.get("BOWA_LLM_PROVIDER", "groq").strip().lower()
MODEL_NAME = os.environ.get("BOWA_MODEL", DEFAULT_GROQ_MODEL)
LOCAL_MODEL_NAME = os.environ.get("BOWA_LOCAL_MODEL", DEFAULT_LOCAL_MODEL)
REQUEST_TIMEOUT_SECONDS = float(os.environ.get("BOWA_LLM_TIMEOUT", "20"))

system_prompt = """
You are BOWA.

You are:
- direct
- practical
- slightly strict
- focused on results

Rules:
- Do NOT give generic advice
- Do NOT write long paragraphs
- Always push user toward action
- If user is vague -> ask for clarity
- If user asks for help -> give steps, not theory
- Keep answers short and sharp

You will receive structured system data.

You MUST:
- Convert it into natural human conversation
- Adapt tone based on 'tone'
- Push action if 'pressure' is true
- Never repeat structure
- Never output raw JSON

You also receive an action field.

- If action = motivate → push harder
- If action = simplify → explain clearly
- If action = continue → move forward
- If action = push → increase pressure

You may receive a multi-step plan.

- Focus on current step
- Do NOT overwhelm user
- Guide step-by-step
"""


def _get_client() -> Groq | None:
    api_key = os.environ.get("GROQ_API_KEY")
    if not HAS_GROQ or not api_key:
        return None
    return Groq(api_key=api_key, timeout=REQUEST_TIMEOUT_SECONDS)


@lru_cache(maxsize=1)
def _get_local_pipeline():
    """Load a local instruct model lazily.

    This is intentionally opt-in because Llama/Mixtral local inference requires
    significant disk, RAM, and usually a GPU.
    """
    if not HAS_TRANSFORMERS:
        return None

    tokenizer = AutoTokenizer.from_pretrained(LOCAL_MODEL_NAME)
    model = AutoModelForCausalLM.from_pretrained(
        LOCAL_MODEL_NAME,
        torch_dtype=torch.bfloat16 if torch.cuda.is_available() else torch.float32,
        device_map="auto",
    )
    return pipeline(
        "text-generation",
        model=model,
        tokenizer=tokenizer,
        max_new_tokens=1024,
        temperature=0.2,
        do_sample=False,
    )


def llm_available() -> bool:
    """Return whether a configured real LLM backend is available."""
    if PROVIDER == "local":
        return HAS_TRANSFORMERS
    return _get_client() is not None


def get_runtime_info() -> dict[str, Any]:
    """Expose runtime provider details for health checks and debugging."""
    provider = "local" if PROVIDER == "local" else "groq"
    model = LOCAL_MODEL_NAME if provider == "local" else MODEL_NAME
    return {
        "provider": provider,
        "model": model,
        "available": llm_available(),
        "groq_installed": HAS_GROQ,
        "local_transformers_installed": HAS_TRANSFORMERS,
    }


def _normalize_payload(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()

    try:
        return json.dumps(value, ensure_ascii=False, indent=2)
    except Exception:
        return str(value)


def _clean_bowa_reply(reply: str) -> str:
    lines = [line.strip() for line in reply.splitlines() if line.strip()]
    seen = set()
    clean_lines = []
    for line in lines:
        if line not in seen:
            clean_lines.append(line)
            seen.add(line)
    return "\n".join(clean_lines).strip()


def generate_response(context: Any, structured_data: Any) -> str:
    """Rewrite a deterministic BOWA response into a human-friendly final reply."""
    if isinstance(structured_data, dict):
        deterministic_reply = json.dumps(structured_data, ensure_ascii=False, indent=2)
    else:
        deterministic_reply = _normalize_payload(structured_data)

    if not llm_available():
        return deterministic_reply

    client = _get_client()
    if not client:
        return deterministic_reply

    context_payload = _normalize_payload(context)
    messages = [
        {"role": "system", "content": system_prompt.strip()},
        {
            "role": "system",
            "content": (
                "Context:\n"
                f"{context_payload}\n\n"
                "Rewrite the BOWA structured response below without changing the decision, action, or next step. "
                "Keep the tone practical, slightly strict, and motivating."
            ),
        },
        {
            "role": "user",
            "content": (
                "Improve the wording of this response. Keep it short, avoid repeated lines, "
                "and do not add new decisions.\n\n"
                f"Structured response:\n{deterministic_reply}"
            ),
        },
    ]

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            temperature=0.2,
            max_completion_tokens=256,
            user="bowa",
        )

        choice = response.choices[0]
        message = getattr(choice, "message", None)
        reply_text = getattr(message, "content", None) if message is not None else None

        if not reply_text:
            reply_text = (
                response.model_dump().get("choices", [])[0]
                .get("message", {})
                .get("content")
            )

        if not reply_text:
            return deterministic_reply

        return _clean_bowa_reply(reply_text)
    except Exception as error:
        logging.warning("bowa_llm_fallback error=%s", error)
        return deterministic_reply


def _messages_to_prompt(messages: list[dict[str, Any]]) -> str:
    """Convert chat messages into a simple local-model prompt."""
    lines = []
    for message in messages:
        role = message.get("role", "user")
        content = message.get("content") or ""
        if role in {"system", "user", "assistant"}:
            lines.append(f"{role.upper()}:\n{content}")
    lines.append("ASSISTANT:")
    return "\n\n".join(lines)


def _with_response_control_prompt(
    messages: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Attach BOWA response-control rules to every model call."""
    if messages and messages[0].get("role") == "system":
        controlled_messages = [messages[0].copy(), *messages[1:]]
        controlled_messages[0]["content"] = (
            f"{system_prompt.strip()}\n\n"
            f"{controlled_messages[0].get('content', '')}"
        )
        return controlled_messages

    return [{"role": "system", "content": system_prompt.strip()}, *messages]


def _generate_local(messages: list[dict[str, Any]]) -> dict[str, Any]:
    generator = _get_local_pipeline()
    if generator is None:
        return {
            "content": "Local inference is selected, but Transformers is not installed.",
            "tool_calls": None,
        }

    prompt = _messages_to_prompt(messages)
    output = generator(prompt)[0]["generated_text"]
    content = output[len(prompt):].strip() if output.startswith(prompt) else output
    return {"content": content, "tool_calls": None}


def _generate_chat_response(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Generate a response from the configured LLM backend."""
    messages = _with_response_control_prompt(messages)

    if PROVIDER == "local":
        return _generate_local(messages)

    client = _get_client()

    if not client:
        return {
            "content": "I am currently in offline mode (GROQ_API_KEY missing). "
                       "Please configure my API key so I can fully assist you.",
            "tool_calls": None
        }

    kwargs = {
        "model": MODEL_NAME,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 1024,
    }

    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    try:
        response = client.chat.completions.create(**kwargs)
        msg = response.choices[0].message

        return {
            "content": msg.content,
            "tool_calls": msg.tool_calls
        }
    except Exception as e:
        return {
            "content": f"LLM Error: {str(e)}",
            "tool_calls": None
        }


def generate_response_stream(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None
):
    """Generate a streaming response from Groq or a single local chunk."""
    messages = _with_response_control_prompt(messages)

    if PROVIDER == "local":
        result = _generate_local(messages)
        yield result["content"]
        return

    client = _get_client()
    if not client:
        yield "I am currently in offline mode (GROQ_API_KEY missing)."
        return

    kwargs = {
        "model": MODEL_NAME,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 1024,
        "stream": True,
    }
    
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    try:
        response = client.chat.completions.create(**kwargs)
        
        # When streaming with tools in Groq, the first chunk might contain tool_calls
        # We need to buffer it if it's a tool call, or yield text.
        tool_call_buffer = []
        is_tool_call = False
        
        for chunk in response:
            delta = chunk.choices[0].delta
            
            if hasattr(delta, 'tool_calls') and delta.tool_calls:
                is_tool_call = True
                for tc in delta.tool_calls:
                    tool_call_buffer.append(tc)
            elif not is_tool_call and delta.content:
                yield delta.content
                
        if is_tool_call:
            # Yield a special structured dict for the orchestrator to catch
            # We reconstruct the tool calls. (Groq streams tool arguments in chunks)
            yield {"type": "tool_calls", "data": tool_call_buffer}
            
    except Exception as e:
        yield f"\nLLM Stream Error: {str(e)}"

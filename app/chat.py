"""New Guy chat via xAI API."""
from __future__ import annotations

from typing import Any, AsyncIterator

import httpx
from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from .config import SYSTEM_PROMPT, XAI_CHAT_URL, get_xai_settings


async def chat_completion(messages: list[dict[str, str]], *, stream: bool = False) -> Any:
    key, model, temperature = get_xai_settings()
    if not key:
        raise HTTPException(status_code=503, detail="XAI_API_KEY not configured")

    payload_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for m in messages:
        role = m.get("role")
        content = m.get("content")
        if role in ("user", "assistant") and isinstance(content, str) and content.strip():
            payload_messages.append({"role": role, "content": content.strip()})

    if len(payload_messages) < 2:
        raise HTTPException(status_code=400, detail="At least one user message required")

    body = {
        "model": model,
        "messages": payload_messages,
        "temperature": temperature,
        "stream": stream,
    }
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }

    if not stream:
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(XAI_CHAT_URL, json=body, headers=headers)
            if r.status_code >= 400:
                raise HTTPException(
                    status_code=502,
                    detail=f"xAI error {r.status_code}",
                )
            data = r.json()
            try:
                text = data["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError):
                raise HTTPException(status_code=502, detail="Unexpected xAI response")
            return {"reply": text, "model": model}

    async def event_gen() -> AsyncIterator[bytes]:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST", XAI_CHAT_URL, json=body, headers=headers
            ) as r:
                if r.status_code >= 400:
                    yield b'data: {"error": "xAI upstream error"}\n\n'
                    return
                async for line in r.aiter_lines():
                    if not line:
                        continue
                    if line.startswith("data: "):
                        yield (line + "\n\n").encode("utf-8")

    return StreamingResponse(event_gen(), media_type="text/event-stream")

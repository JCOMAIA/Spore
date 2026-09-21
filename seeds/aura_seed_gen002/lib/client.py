# -*- coding: utf-8 -*-
"""Cliente OpenAI-compatible minimo (stdlib only) â€” roda na VPS e na maquina fraca.

Compativel com: OpenRouter (default), llama.cpp server (LOCAL_JUDGE_URL),
qualquer endpoint /v1/chat/completions."""
from __future__ import annotations

import json
import os
import urllib.request


class ChatClient:
    def __init__(self, base_url="https://openrouter.ai/api/v1", model="z-ai/glm-4.5-air",
                 api_key=None, timeout=90.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        self.timeout = timeout

    def chat(self, msgs, max_tokens=300, temperature=0.7):
        """Retorna (texto, usage_dict). usage vem do provedor (pode vir vazio)."""
        body = json.dumps({"model": self.model, "messages": msgs,
                           "max_tokens": max_tokens, "temperature": temperature}).encode("utf-8")
        req = urllib.request.Request(
            self.base_url + "/chat/completions", data=body,
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer " + self.api_key})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            out = json.loads(r.read().decode("utf-8"))
        text = out["choices"][0]["message"]["content"].strip()
        return text, (out.get("usage") or {})


def list_models(max_prompt_usd_per_1m=None, limit=30):
    """Lista modelos do OpenRouter ordenados por preco de entrada (USD/1M tokens)."""
    req = urllib.request.Request("https://openrouter.ai/api/v1/models")
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read().decode("utf-8"))["data"]
    rows = []
    for m in data:
        p = (m.get("pricing") or {})
        try:
            pin = float(p.get("prompt") or 0) * 1e6
        except (TypeError, ValueError):
            pin = None
        rows.append((m.get("id", "?"), pin))
    if max_prompt_usd_per_1m is not None:
        rows = [x for x in rows if x[1] is not None and x[1] <= max_prompt_usd_per_1m]
    rows.sort(key=lambda x: (x[1] is None, x[1] if x[1] is not None else 0))
    return rows[:limit]
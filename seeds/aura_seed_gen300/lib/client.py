# -*- coding: utf-8 -*-
"""Cliente OpenAI-compatible minimo (stdlib only) — v2 com resiliencia.

v2 (pos-artefato de throttle): 429/5xx e falha de rede -> retry com backoff,
respeitando Retry-After quando o provedor mandar. Sem isso, a bateria confundia
"provedor engasgado" com "organismo ruim" e o lineage virava cemiterio."""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

RETRYABLE = (429, 500, 502, 503, 504)
ATTEMPTS = 4
BACKOFFS = (2.0, 5.0, 12.0)


class ChatClient:
    def __init__(self, base_url="https://openrouter.ai/api/v1",
                 model="z-ai/glm-5.3-flash", api_key=None, timeout=90.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        self.timeout = timeout

    def chat(self, msgs, max_tokens=300, temperature=0.7, response_format=None):
        """(texto, usage). Retry: 429/5xx/rede com backoff; e CONTENT vazio/None
        (modelo thinking esgotou o max_tokens no raciocinio) -> repete com
        orcamento 3x maior. Outros erros HTTP sobem limpos."""
        cur = int(max_tokens)
        last_err = None
        for attempt in range(ATTEMPTS):
            body_d = {"model": self.model, "messages": msgs,
                      "max_tokens": cur, "temperature": temperature}
            if response_format:
                body_d["response_format"] = response_format
            if os.environ.get("AURA_DISABLE_REASONING") == "1":
                body_d["reasoning"] = {"enabled": False}
            body = json.dumps(body_d).encode("utf-8")
            req = urllib.request.Request(
                self.base_url + "/chat/completions", data=body,
                headers={"Content-Type": "application/json",
                         "Authorization": "Bearer " + self.api_key})
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    out = json.loads(r.read().decode("utf-8"))
                msg = (out.get("choices") or [{}])[0].get("message") or {}
                text = (msg.get("content") or "").strip()
                if text:
                    return text, (out.get("usage") or {})
                cur = cur * 3  # reasoning comeu o orcamento — 3x e de novo
                last_err = "content vazio (max_tokens agora %d)" % cur
                continue
            except urllib.error.HTTPError as e:
                payload = e.read().decode("utf-8", "ignore")[:300]
                if e.code in RETRYABLE and attempt < ATTEMPTS - 1:
                    wait = BACKOFFS[min(attempt, len(BACKOFFS) - 1)]
                    ra = (e.headers or {}).get("Retry-After") if getattr(e, "headers", None) else None
                    try:
                        wait = max(wait, float(ra))
                    except (TypeError, ValueError):
                        pass
                    time.sleep(wait)
                    last_err = "HTTP %d: %s" % (e.code, payload)
                    continue
                raise RuntimeError("HTTP %d: %s" % (e.code, payload))
            except Exception as e:
                if attempt < ATTEMPTS - 1:
                    time.sleep(BACKOFFS[min(attempt, len(BACKOFFS) - 1)])
                    last_err = str(e)
                    continue
                raise
        raise RuntimeError("esgotou retries: %s" % (last_err or "?"))


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

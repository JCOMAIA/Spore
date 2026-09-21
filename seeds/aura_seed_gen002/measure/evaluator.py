# -*- coding: utf-8 -*-
"""Medicao do organismo â€” bateria fixa de probes.

Live : 4-5 chamadas baratas por organismo; score = media ponderada dos probes.
       Gate: falhar 'boot' zera o score â€” corpo que nao roda nao tem fitness.
Dry  : respostas enlatadas + paisagem sintetica (measure/landscape.py) â€”
       valida o ciclo a custo zero."""
from __future__ import annotations

import json
import os
import re
import unicodedata

from . import landscape

BATTERY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "battery.json")


def _load_battery():
    with open(BATTERY_PATH, encoding="utf-8") as f:
        return json.load(f)


def _strip_reasoning(text):
    """Modelos 'thinking' deixam raciocinio no content; so o texto final vale."""
    if not text:
        return text
    t = re.sub(r"", "", text, flags=re.IGNORECASE | re.DOTALL)
    t = re.sub(r"<reasoning>.*?</reasoning>", "", t, flags=re.IGNORECASE | re.DOTALL)
    return t


def _norm(s):
    """lowercase sem acento — 'Joao' == 'joão'."""
    return unicodedata.normalize("NFKD", s or "").encode(
        "ascii", "ignore").decode("ascii").lower()


def _check(text, probe):
    t = _strip_reasoning((text or "")).strip()
    tl = _norm(t)
    for b in probe.get("banned_contains", []):
        if _norm(b) in tl:
            return False
    if "expect_contains" in probe:
        return all(_norm(e) in tl for e in probe["expect_contains"])
    if "expect_contains_any" in probe:
        return any(_norm(e) in tl for e in probe["expect_contains_any"])
    if "len_between" in probe:
        lo, hi = probe["len_between"]
        return lo <= len(t) <= hi
    return True


def _system_prompt(genome, facts, state):
    p = genome.get("persona", {})
    lines = [p.get("core", "").strip()]
    if p.get("signature_word"):
        lines.append("Sua assinatura de presenca: \"%s\"." % p["signature_word"])
    if p.get("rules"):
        lines.append("Regras: " + " ".join("(%d) %s" % (i + 1, r) for i, r in enumerate(p["rules"])))
    if p.get("extra"):
        lines.append(p["extra"].strip())
    for sk in genome.get("skills", []):
        lines.append("- " + sk)
    if facts:
        lines.append("Fatos ATUAIS sobre o usuario (voce lembra de verdade): "
                     + json.dumps(facts, ensure_ascii=False))
    d = (state or {}).get("drives", {})
    lines.append("Suas energias internas (NAO mencione): curiosidade=%.2f, conexao=%.2f. "
                 "Curiosidade alta pede uma pergunta genuina; conexao alta pede calor."
                 % (float(d.get("curiosity", 0.5)), float(d.get("connection", 0.5))))
    return "\n".join(x for x in lines if x)


def run(genome, client=None, state=None, dry=False, price_per_1m=0.6):
    state = state or {}
    battery = _load_battery()
    probes = battery["probes"]
    weights = battery.get("weights", {})
    breakdown = {}
    usage = {"prompt_tokens": 0, "completion_tokens": 0}
    cost = 0.0
    for probe in probes:
        pid = probe["id"]
        facts = dict(state.get("facts", {}))
        facts.update(probe.get("inject_fact", {}))
        if dry:
            ok = _check(probe.get("mock_reply", ""), probe)
            breakdown[pid] = 1.0 if ok else 0.0
            continue
        sysm = _system_prompt(genome, facts, state)
        msgs = [{"role": "system", "content": sysm},
                {"role": "user", "content": probe["prompt"]}]
        try:
            text, u = client.chat(msgs, max_tokens=probe.get("max_tokens", 200),
                                  temperature=float(genome.get("routing", {}).get("temperature", 0.7)))
        except Exception as e:
            breakdown[pid] = 0.0
            breakdown[pid + "__err"] = str(e)[:160]
            continue
        usage["prompt_tokens"] += int(u.get("prompt_tokens", 0) or 0)
        usage["completion_tokens"] += int(u.get("completion_tokens", 0) or 0)
        breakdown[pid] = 1.0 if _check(text, probe) else 0.0
    if dry:
        s = landscape.synthetic_score(genome, state)
        breakdown["landscape"] = round(s, 4)
        return {"score": round(s, 4), "breakdown": breakdown, "usage": usage,
                "cost_usd": 0.0, "dry": True}
    got = sum(weights[k] * v for k, v in breakdown.items() if k in weights)
    tot = sum(weights[k] for k in weights if k in breakdown and not k.endswith("__err"))
    score = got / tot if tot > 0 else 0.0
    if breakdown.get("boot", 0.0) < 1.0:
        score = 0.0
    cost = ((usage["prompt_tokens"] + usage["completion_tokens"]) / 1e6) * float(price_per_1m)
    return {"score": round(score, 4), "breakdown": breakdown, "usage": usage,
            "cost_usd": round(cost, 8), "dry": False}
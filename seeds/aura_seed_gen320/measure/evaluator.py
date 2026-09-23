# -*- coding: utf-8 -*-
"""Medicao do organismo — v3: probes estaticos + probes EXECUTAVEIS (plugins).

- probes comuns: credito parcial [0,1] via _check_scored;
- probes com "plugin": o codigo DA AURA roda em subprocesso com timeout
  (measure/plugins.py) — erro/timeout/fora de faixa = probe 0 + registro;
- boot continua gate binario; _check_scored nunca levanta;
- o campeao e re-medido a todo ciclo (infinite), comparacao simetrica."""
from __future__ import annotations

import json
import os
import re
import time
import unicodedata

from . import landscape
from . import plugins as _plugins

BATTERY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "battery.json")

PROBE_DELAY_S = float(os.environ.get("AURA_PROBE_DELAY_S", "1.2"))


def _load_battery():
    with open(BATTERY_PATH, encoding="utf-8") as f:
        return json.load(f)


def _strip_reasoning(text):
    if not text:
        return text
    t = re.sub(r"", "", text, flags=re.IGNORECASE | re.DOTALL)
    t = re.sub(r"<reasoning>.*?</reasoning>", "", t, flags=re.IGNORECASE | re.DOTALL)
    return t


def _norm(s):
    return unicodedata.normalize("NFKD", s or "").encode(
        "ascii", "ignore").decode("ascii").lower()


def _check_scored(text, probe):
    """Credito parcial [0,1]. Supoe entrada saneada; caller protege com try."""
    t = _strip_reasoning((text or "")).strip()
    tl = _norm(t)
    for b in probe.get("banned_contains", []):
        if _norm(b) in tl:
            return 0.0
    if "expect_contains" in probe:
        exps = [_norm(e) for e in probe["expect_contains"]]
        hits = sum(1 for e in exps if e in tl)
        if hits == len(exps):
            return 1.0
        if hits:
            return 0.5
        return 0.0
    if "expect_contains_any" in probe:
        if any(_norm(e) in tl for e in probe["expect_contains_any"]):
            return 1.0
        return 0.25 if t else 0.0
    if "len_between" in probe:
        lo, hi = probe["len_between"]
        if lo <= len(t) <= hi:
            return 1.0
        return 0.5 if t else 0.0
    return 0.5


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


def run(genome, client=None, state=None, dry=False, price_per_1m=0.6,
        latency_slow_s=0.0, latency_penalty_max=0.0):
    state = state or {}
    battery = _load_battery()
    probes = battery["probes"]
    weights = battery.get("weights", {})
    breakdown = {}
    usage = {"prompt_tokens": 0, "completion_tokens": 0}
    cost = 0.0
    lat_sum, n_lat = 0.0, 0
    for idx, probe in enumerate(probes):
        pid = str(probe.get("id") or "probe_%d" % idx)
        facts = dict(state.get("facts", {}))
        facts.update(probe.get("inject_fact", {}))
        if dry:
            text = probe.get("mock_reply", "")
        else:
            sysm = _system_prompt(genome, facts, state)
            msgs = [{"role": "system", "content": sysm},
                    {"role": "user", "content": str(probe.get("prompt", ""))}]
            _t0 = time.time()
            try:
                text, u = client.chat(msgs, max_tokens=int(probe.get("max_tokens", 200)),
                                      temperature=float(genome.get("routing", {}).get("temperature", 0.7)))
            except Exception as e:
                breakdown[pid] = 0.0
                breakdown[pid + "__err"] = str(e)[:160]
                continue
            usage["prompt_tokens"] += int(u.get("prompt_tokens", 0) or 0)
            usage["completion_tokens"] += int(u.get("completion_tokens", 0) or 0)
            lat_sum += time.time() - _t0
            n_lat += 1
        if probe.get("plugin"):
            try:
                breakdown[pid] = float(_plugins.call(probe["plugin"], text, probe))
            except Exception as e:
                breakdown[pid] = 0.0
                breakdown[pid + "__err"] = "plugin: %s" % str(e)[:120]
        else:
            try:
                breakdown[pid] = _check_scored(text, probe)
            except Exception:
                breakdown[pid] = 0.0
        if not dry and PROBE_DELAY_S > 0 and idx < len(probes) - 1:
            time.sleep(PROBE_DELAY_S)
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
    lat_media = (lat_sum / n_lat) if n_lat else 0.0
    penalty = 0.0
    if latency_penalty_max > 0 and lat_media > latency_slow_s:
        penalty = min(float(latency_penalty_max),
                      (lat_media - latency_slow_s) / max(1.0, latency_slow_s)
                      * float(latency_penalty_max))
        score = max(0.0, round(score - penalty, 4))
    breakdown["latencia_media_s"] = round(lat_media, 2)
    cost = ((usage["prompt_tokens"] + usage["completion_tokens"]) / 1e6) * float(price_per_1m)
    return {"score": round(score, 4), "breakdown": breakdown, "usage": usage,
            "latency_penalty": round(penalty, 4),
            "cost_usd": round(cost, 8), "dry": False}

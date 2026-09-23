# -*- coding: utf-8 -*-
"""Paisagem de fitness SINTETICA (modo dry).

score = f(genoma, estado), deterministica e multimodal: 2 senos + 1 termo de
assinatura. Serve para validar/demonstrar o ciclo N+1 (subida, plato, morte)
SEM gastar API â€” o que se mede aqui e a MECANICA evolutiva, nao a qualidade
real da Aura. Em live, quem manda e a bateria de probes."""
from __future__ import annotations

import hashlib
import math


def synthetic_score(genome, state=None):
    r = genome.get("routing", {})
    d = (state or {}).get("drives", {})
    x = (0.37 * float(r.get("temperature", 0.7))
         + 0.53 * float(d.get("curiosity", 0.5))
         + 0.71 * float(d.get("connection", 0.5)))
    s = 0.5 + 0.22 * math.sin(2.0 * math.pi * x) + 0.10 * math.sin(2.0 * math.pi * 3.7 * x + 1.1)
    sig = (genome.get("persona", {}).get("signature_word") or "").encode("utf-8")
    s += 0.04 * ((int(hashlib.sha256(sig).hexdigest()[:8], 16) % 1000) / 999.0 - 0.5)
    return max(0.0, min(1.0, s))
# -*- coding: utf-8 -*-
"""O menu de mutacoes â€” o '+1 = qualquer coisa', tornado legivel.

Cada mutacao e UM diff registrado: {"op", "path", "before", "after", "ts"}.
O organismo e (genoma U estado): genoma = genes constantes; estado = niveis
motivacionais + memoria, herdados entre geracoes.
Regra: mutacao que nao pode ser registrada nao entra no menu."""
from __future__ import annotations

import copy
import json
import os
import random
import time

PHRASES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            os.pardir, "genome", "phrases.json")

OPS = ["drive", "persona_extra", "signature", "temperature", "skill", "routing", "meta"]


def load_phrases():
    with open(PHRASES_PATH, encoding="utf-8") as f:
        return json.load(f)


def mutate(genome, state, rng=None, phrases=None):
    rng = rng or random.Random()
    phrases = phrases or load_phrases()
    g = copy.deepcopy(genome)
    s = copy.deepcopy(state or {})
    s.setdefault("drives", {"curiosity": 0.5, "connection": 0.5})
    weights = g.get("mutation_weights", {"drive": 3, "persona_extra": 3, "signature": 1,
                                         "temperature": 2, "skill": 3, "routing": 2, "meta": 1})
    op = rng.choices(OPS, weights=[max(0, int(weights.get(o, 1))) for o in OPS])[0]
    rec = {"op": op, "ts": time.time()}

    if op == "drive":
        k = rng.choice(["curiosity", "connection"])
        before = float(s["drives"].get(k, 0.5))
        after = round(min(1.0, max(0.0, before + rng.choice([-1, 1]) * rng.uniform(0.03, 0.15))), 4)
        s["drives"][k] = after
        rec.update(path="state.drives." + k, before=before, after=after)

    elif op == "temperature":
        before = float(g["routing"].get("temperature", 0.7))
        after = round(min(1.0, max(0.1, before + rng.choice([-1, 1]) * rng.uniform(0.03, 0.12))), 3)
        g["routing"]["temperature"] = after
        rec.update(path="routing.temperature", before=before, after=after)

    elif op == "persona_extra":
        before = g["persona"].get("extra", "")
        after = (before + " " + rng.choice(phrases["persona_extras"])).strip()
        sents = after.split(". ")
        if len(sents) > 4:
            after = ". ".join(sents[-4:])
        g["persona"]["extra"] = after
        rec.update(path="persona.extra", before=(before[-80:] or "(vazio)"), after=after[-80:])

    elif op == "signature":
        pool = [w for w in phrases["signature_words"] if w != g["persona"].get("signature_word")]
        if not pool:
            rec.update(op="noop")
        else:
            before = g["persona"].get("signature_word", "")
            after = rng.choice(pool)
            g["persona"]["signature_word"] = after
            rec.update(path="persona.signature_word", before=before, after=after)

    elif op == "skill":
        pool = phrases["skills"]
        pick = rng.choice(pool)
        g.setdefault("skills", [])
        if pick in g["skills"]:
            g["skills"].remove(pick)
            rec.update(path="skills", before=pick, after="(removida)")
        else:
            g["skills"].append(pick)
            rec.update(path="skills", before="(nada)", after=pick)

    elif op == "routing":
        alts = [m for m in g["routing"].get("decider_models", [])
                if m != g["routing"].get("active_model")]
        if not alts:
            rec.update(op="noop")
        else:
            before = g["routing"]["active_model"]
            after = rng.choice(alts)
            g["routing"]["active_model"] = after
            rec.update(path="routing.active_model", before=before, after=after)

    elif op == "meta":
        keys = [k for k in g.get("mutation_weights", {}) if k in OPS]
        if not keys:
            rec.update(op="noop")
        else:
            k = rng.choice(keys)
            before = int(g["mutation_weights"][k])
            after = max(0, before + rng.choice([-1, 1]))
            g["mutation_weights"][k] = after
            rec.update(path="mutation_weights." + k, before=before, after=after)

    return g, s, rec
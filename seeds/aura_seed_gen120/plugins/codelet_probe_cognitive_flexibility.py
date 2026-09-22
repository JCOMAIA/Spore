# -*- coding: utf-8 -*-
"""Plugin: probe_cognitive_flexibility (v0.1.1)
Mede flexibilidade cognitiva: diversidade lexical e alternancia de ideias.
Python puro: apenas re, math, unicodedata.
"""
import re
import unicodedata

PROMPT = "Liste o maximo de usos possiveis para um objeto comum (ex.: um tijolo) e justifique cada um."


def _norm(text):
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text.lower()


def probe_cognitive_flexibility(text, probe):
    """Pontua flexibilidade (0.0 a 1.0): diversidade lexical + fluencia de ideias."""
    t = _norm(text)
    words = re.findall(r"[a-z]{3,}", t)
    if not words:
        return 0.0
    unique = set(words)
    diversity = len(unique) / float(len(words))
    # fluencia: ideias delimitadas por virgulas/pontos ou conectivos de mudanca
    segments = [s for s in re.split(r"[,.!?;]|\bou\b|\be\b|\btambem\b", t) if len(s.split()) >= 2]
    fluency = min(1.0, len(segments) / 10.0)
    score = 0.5 * diversity + 0.5 * fluency
    return max(0.0, min(1.0, score))

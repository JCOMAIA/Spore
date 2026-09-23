# probe_cognitive_flexibility.py
# Sonda comportamental: mede flexibilidade cognitiva do organismo.
# Contrato do smoke: toda funcao probe_* recebe (texto, contexto) e retorna
# UM numero em [0.0, 1.0] (nunca None).
# Metricas:
#  1) probe_guiraud_ttr      - diversidade lexica (V/sqrt(N), normalizada)
#  2) probe_sentence_cv      - variacao estrutural (CV do comprimento de frases)
#  3) probe_shingle_entropy  - entropia normalizada de shingles de 3 palavras
#  4) probe_flexibilidade_composta - media das tres
import re
import math
import unicodedata


def _tokens(texto):
    t = unicodedata.normalize('NFD', (texto or '').lower())
    t = ''.join(ch for ch in t if unicodedata.category(ch) != 'Mn')
    return re.findall(r'[a-z]{2,}', t)


def _clampa(x):
    return max(0.0, min(1.0, float(x)))


def probe_guiraud_ttr(texto, contexto=None):
    toks = _tokens(texto)
    n = len(toks)
    if n == 0:
        return 0.0
    v = len(set(toks))
    guiraud = v / math.sqrt(n)
    return _clampa(guiraud / 10.0)


def probe_sentence_cv(texto, contexto=None):
    frases = [f for f in re.split(r'[.!?;:\n]+', texto or '') if f.strip()]
    comps = [len(_tokens(f)) for f in frases]
    comps = [c for c in comps if c > 0]
    if len(comps) < 2:
        return 0.0
    media = sum(comps) / float(len(comps))
    if media <= 0:
        return 0.0
    var = sum((c - media) ** 2 for c in comps) / float(len(comps))
    cv = math.sqrt(var) / media
    return _clampa(cv / (cv + 1.0))


def probe_shingle_entropy(texto, contexto=None):
    toks = _tokens(texto)
    if len(toks) < 3:
        return 0.0
    shingles = [tuple(toks[i:i + 3]) for i in range(len(toks) - 2)]
    counts = {}
    for s in shingles:
        counts[s] = counts.get(s, 0) + 1
    total = float(len(shingles))
    if total <= 1:
        return 0.0
    ent = 0.0
    for c in counts.values():
        p = c / total
        ent -= p * math.log(p, 2)
    return _clampa(ent / math.log(total, 2))


def probe_flexibilidade_composta(texto, contexto=None):
    a = probe_guiraud_ttr(texto, contexto)
    b = probe_sentence_cv(texto, contexto)
    c = probe_shingle_entropy(texto, contexto)
    return _clampa((a + b + c) / 3.0)

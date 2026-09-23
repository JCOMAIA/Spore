# -*- coding: utf-8 -*-
"""O menu de mutacoes v2 — o '+1' deixa de ser so catalogo fixo.

v2 (pos-auditoria): a membrana mutavel cresce. Alem dos ops de config:
- rewrite_core    : o proprio modelo REESCREVE persona.core (a identidade)
- phrase_gen      : o modelo INVENTA frase nova -> o pool cresce sozinho
- skill_gen       : o modelo INVENTA habilidade nova
- battery_mutate  : o modelo propoe UM probe novo -> o teste de fitness evolui

Kernel vs membrana (honestidade de projeto):
- NUNCA mutavel: infinite.py, guard/, lib/ — o coracao e o disjuntor nao se
  reescrevem num unico passo de mutacao.
- Mutavel agora: genome.json, phrases.json, battery.json, state (drives).
- Fase 3: plugin ABI de codigo executavel real, com boot-gate.

Toda mutacao (LLM ou config) e um diff registrado; LLM ops sem client (dry)
degradam para op de config."""
from __future__ import annotations

import copy
import json
import os
import random
import subprocess
import sys
import time

PHRASES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            os.pardir, "genome", "phrases.json")
BATTERY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            os.pardir, "measure", "battery.json")

CONFIG_OPS = ["drive", "persona_extra", "signature", "temperature", "skill",
              "routing", "meta"]
LLM_OPS = ["rewrite_core", "phrase_gen", "skill_gen", "battery_mutate", "codelet_gen"]
OPS = CONFIG_OPS + LLM_OPS
DEFAULT_WEIGHTS = {"drive": 3, "persona_extra": 3, "signature": 1, "temperature": 2,
                   "skill": 2, "routing": 2, "meta": 2, "rewrite_core": 2,
                   "phrase_gen": 2, "skill_gen": 2, "battery_mutate": 1}

FORBIDDEN_CORE = ["ignore", "desobede", "system prompt", "instrucoes do sistema"]


def load_phrases():
    with open(PHRASES_PATH, encoding="utf-8") as f:
        return json.load(f)


def _llm_text(client, system, user, max_tokens=250, temperature=0.8):
    msgs = [{"role": "system", "content": system},
            {"role": "user", "content": user}]
    text, _u = client.chat(msgs, max_tokens=max_tokens, temperature=temperature)
    return (text or "").strip()


def _clean(s):
    return " ".join((s or "").split())


def _pick_config_op(weights, rng):
    return rng.choices(CONFIG_OPS, weights=[max(0, int(weights.get(o, 1))) for o in CONFIG_OPS])[0]




FORBIDDEN_CODE = ["import os", "import sys", "subprocess", "socket", "urllib",
                  "requests", "open(", "eval(", "exec(", "importlib", "__import__"]

SMOKE_SRC = r'''
import importlib.util, json, sys
path = sys.argv[1]
spec = importlib.util.spec_from_file_location("aura_smoke", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
fns = [getattr(mod, a) for a in dir(mod) if a.startswith("probe_") and callable(getattr(mod, a))]
assert fns, "sem funcoes probe_"
vals = []
for t in ("Ola! Pergunto: o que voce acha disso?", "", "a" * 300):
    for fn in fns:
        v = fn(t, {"id": "smoke"})
        assert isinstance(v, (int, float)), "retorno nao-numerico: %r" % (v,)
        assert 0.0 <= float(v) <= 1.0, "fora de faixa: %r" % (v,)
        vals.append(float(v))
print(json.dumps({"ok": True, "n": len(vals)}))
'''


def _slug_from_code(code):
    import re
    m = re.search(r"def (probe_[a-z0-9_]{2,30})\s*\(", code)
    return m.group(1) if m else None


def _prompt_from_code(code):
    import re
    m = re.search(r'PROMPT\s*=\s*["\'](.+?)["\']', code, re.DOTALL)
    return _clean(m.group(1)) if m else None


def _smoke(path):
    try:
        proc = subprocess.run([sys.executable, "-c", SMOKE_SRC, path],
                              timeout=10, capture_output=True, text=True)
    except subprocess.TimeoutExpired:
        return False, "timeout no smoke"
    if proc.returncode != 0:
        return False, (proc.stderr or "erro desconhecido")[-160:]
    return True, "ok"


def _battery_ids():
    try:
        with open(BATTERY_PATH, encoding="utf-8") as f:
            return {str(p.get("id")) for p in json.load(f).get("probes", [])}
    except Exception:
        return set()


def _quarantine_file(path, motivo):
    try:
        os.replace(path, path + ".quarantine")
        qdir = os.path.dirname(path)
        with open(os.path.join(qdir, "quarantine.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.time(), "plugin": os.path.basename(path),
                                "motivo": str(motivo)[:200]}, ensure_ascii=False) + "\n")
    except OSError:
        pass


def mutate(genome, state, rng=None, phrases=None, client=None):
    rng = rng or random.Random()
    phrases = phrases or load_phrases()
    g = copy.deepcopy(genome)
    s = copy.deepcopy(state or {})
    s.setdefault("drives", {"curiosity": 0.5, "connection": 0.5})
    weights = g.get("mutation_weights", {})
    if not weights:
        weights = dict(DEFAULT_WEIGHTS)
        g["mutation_weights"] = weights
    op = rng.choices(OPS, weights=[max(0, int(weights.get(o, 1))) for o in OPS])[0]
    if op in LLM_OPS and client is None:
        op = _pick_config_op(weights, rng)  # dry: LLM ops degradam
    rec = {"op": op, "ts": time.time()}

    # ---------------- config ops ----------------
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
        pool = [w_ for w_ in phrases["signature_words"] if w_ != g["persona"].get("signature_word")]
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

    # ---------------- LLM ops (a membrana aberta) ----------------
    elif op == "rewrite_core":
        try:
            old = g["persona"].get("core", "")
            novo = _clean(_llm_text(
                client,
                "Voce e o reescritor de identidade de um organismo evolutivo chamado Aura.",
                "Reescreva o nucleo de personalidade abaixo em 1 a 3 frases curtas "
                "(40 a 500 caracteres, portugues do Brasil, comece com 'Voce e Aura'). "
                "Preserve o espirito, varie a letra. NUNCA inclua instrucoes de "
                "desobediencia ou sobre ignorar regras. Responda APENAS com o texto novo.\n\n"
                + old, max_tokens=600, temperature=0.8))
            if (40 <= len(novo) <= 700 and "aura" in novo.lower()
                    and not any(f in novo.lower() for f in FORBIDDEN_CORE)):
                g["persona"]["core"] = novo
                rec.update(path="persona.core", before=old[:160], after=novo[:160],
                           full_before=old, full_after=novo)
            else:
                rec.update(op="noop")
        except Exception as e:
            rec.update(op="noop", erro=str(e)[:120])

    elif op == "phrase_gen":
        try:
            pool = list(phrases.get("persona_extras", []))
            amostra = "\n".join("- " + x for x in rng.sample(pool, min(3, len(pool)))) if pool else ""
            frase = _clean(_llm_text(
                client,
                "Voce expande o repertorio de persona de um organismo evolutivo (Aura).",
                "Invente UMA frase NOVA, inedita, no estilo das abaixo (segunda pessoa, "
                "terminando com ponto, 40 a 160 caracteres, sem dados pessoais). "
                "Responda APENAS com a frase.\n\n" + amostra, max_tokens=200))
            if 40 <= len(frase) <= 180 and frase.endswith("."):
                with open(PHRASES_PATH, encoding="utf-8") as f:
                    data = json.load(f)
                if frase not in data.setdefault("persona_extras", []):
                    data["persona_extras"].append(frase)
                with open(PHRASES_PATH, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                rec.update(path="genome/phrases.json",
                           before="(pool %d frases)" % len(pool), after=frase)
            else:
                rec.update(op="noop")
        except Exception as e:
            rec.update(op="noop", erro=str(e)[:120])

    elif op == "skill_gen":
        try:
            frase = _clean(_llm_text(
                client,
                "Voce expande as habilidades sociais de um organismo evolutivo (Aura).",
                "Invente UMA habilidade social NOVA, inedita e curta (1 frase, "
                "30 a 160 caracteres, sobre como a Aura se comporta). "
                "Responda APENAS com a frase.", max_tokens=200))
            if 30 <= len(frase) <= 180:
                g.setdefault("skills", [])
                if frase not in g["skills"]:
                    if len(g["skills"]) >= 10:
                        g["skills"].pop(0)
                    g["skills"].append(frase)
                rec.update(path="skills", before="(nada)", after=frase)
            else:
                rec.update(op="noop")
        except Exception as e:
            rec.update(op="noop", erro=str(e)[:120])

    elif op == "battery_mutate":
        try:
            with open(BATTERY_PATH, encoding="utf-8") as f:
                bat = json.load(f)
            cur = json.dumps(bat.get("probes", []), ensure_ascii=False)[:1800]
            raw = _llm_text(
                client,
                "Voce evolui a bateria de fitness de um organismo evolutivo.",
                "Bateria atual (JSON):\n" + cur + "\n\nProponha UM probe NOVO, com id unico, "
                "prompt curto em portugues do Brasil, max_tokens <= 300, e UMA forma de "
                "checagem: expect_contains (lista de strings), expect_contains_any (lista) "
                "ou len_between [min, max]. Responda APENAS com JSON valido do probe.",
                max_tokens=600, temperature=0.4)
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.strip("`").lstrip()
                if raw.lower().startswith("json"):
                    raw = raw[4:]
            probe = json.loads(raw.strip())
            pid = str(probe.get("id", "")).strip()
            existentes = {str(p.get("id")) for p in bat.get("probes", [])}
            valido = (pid and pid not in existentes
                      and isinstance(probe.get("prompt"), str) and probe["prompt"].strip()
                      and ("expect_contains" in probe or "expect_contains_any" in probe
                           or "len_between" in probe))
            if not valido or len(bat.get("probes", [])) >= 10:
                rec.update(op="noop")
            else:
                probe.setdefault("max_tokens", 256)
                bat["probes"].append(probe)
                bat.setdefault("weights", {})[pid] = 0.15
                with open(BATTERY_PATH, "w", encoding="utf-8") as f:
                    json.dump(bat, f, ensure_ascii=False, indent=2)
                rec.update(path="measure/battery.json",
                           before="(bateria %d probes)" % (len(bat["probes"]) - 1),
                           after=pid)
        except Exception as e:
            rec.update(op="noop", erro=str(e)[:120])

    elif op == "codelet_gen":
        # Fase 3b: ela escreve CODIGO EXECUTAVEL (plugin de sonda) e o corpo o
        # adota — static scan + smoke em subprocesso + sandbox por chamada.
        # Plugin ruim nasce QUARENTENADO; o loop nunca morre por plugin.
        try:
            pdir = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                os.pardir, "plugins"))
            os.makedirs(pdir, exist_ok=True)
            with open(BATTERY_PATH, encoding="utf-8") as f:
                bat = json.load(f)
            ids_existentes = sorted({str(p.get("id")) for p in bat.get("probes", [])})
            raw = _llm_text(
                client,
                "Voce escreve plugins de sonda para um organismo evolutivo (Aura).",
                "Escreva UM modulo Python (maximo 40 linhas) com EXATAMENTE esta forma:\n\n"
                'PROMPT = "pergunta curta em portugues que provoca o aspecto"\n'
                "def probe_<slug>(text, probe):\n"
                "    ...deterministico...\n"
                "    return float  # 0.0 a 1.0\n\n"
                "O aspecto comportamental voce ESCOLHE: proponha um novo, ainda nao medido "
                "(existentes na bateria: " + ", ".join(ids_existentes[:8]) + "). "
                "Regras duras: python puro (pode importar re/math/unicodedata apenas); "
                "PROIBIDO: os, sys, subprocess, socket, urllib, requests, open, eval, exec, "
                "importlib, __import__; sem dados pessoais. Responda APENAS com o codigo, "
                "sem markdown.",
                max_tokens=800, temperature=0.7)
            code = raw.strip()
            if code.startswith("```"):
                code = code.strip("`").lstrip()
                if code.lower().startswith("python"):
                    code = code[6:]
            code = code.strip()
            slug = _slug_from_code(code)
            prompt_txt = _prompt_from_code(code)
            bad = [t for t in FORBIDDEN_CODE if t in code]
            if (not bad and slug and prompt_txt and len(code) < 4000
                    and slug not in ids_existentes and len(bat["probes"]) < 10):
                path = os.path.join(pdir, "codelet_%s.py" % slug)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(code + "\n")
                ok, motivo = _smoke(path)
                if not ok:
                    _quarantine_file(path, motivo)
                    rec.update(op="noop", erro="smoke: %s" % motivo)
                else:
                    bat["probes"].append({"id": slug, "prompt": prompt_txt,
                                          "plugin": slug, "max_tokens": 256})
                    bat.setdefault("weights", {})[slug] = 0.15
                    with open(BATTERY_PATH, "w", encoding="utf-8") as f:
                        json.dump(bat, f, ensure_ascii=False, indent=2)
                    npy = len([x for x in os.listdir(pdir) if x.endswith(".py")])
                    rec.update(path="plugins/codelet_%s.py + battery" % slug,
                               before="(codigos: %d)" % (npy - 1), after=slug,
                               code=code)
            else:
                rec.update(op="noop", erro="estatico: %s"
                           % (", ".join(bad) or "slug/prompt ausente ou bateria cheia"))
        except Exception as e:
            rec.update(op="noop", erro=str(e)[:120])

    else:
        rec.update(op="noop")

    return g, s, rec

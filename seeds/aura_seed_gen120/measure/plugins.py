# -*- coding: utf-8 -*-
"""Codigo executavel que a Aura escreve (fase 3b) — plugins de sonda.

ABI de plugin (arquivo .py em plugins/):
    PROMPT = "pergunta curta que provoca o aspecto"
    def probe_<slug>(text, probe) -> float   # 0.0..1.0

Execucao SEMPRE em subprocesso com timeout — o loop nunca trava por plugin.
Erro/timeout/fora de faixa = probe 0 + registro no breakdown.
Plugin que nem importa e QUARENTENADO (.quarantine) — orgao defeituoso sai do
corpo, o organismo segue vivo. O kernel nunca passa por aqui; guard/
kernel.sha256 vigia os arquivos vitais."""
from __future__ import annotations

import glob
import json
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN_DIR = os.path.join(ROOT, "plugins")
RUNNER = 'import importlib.util, json, sys\npath, fname, text = sys.argv[1], sys.argv[2], sys.argv[3]\nprobe = json.loads(sys.argv[4])\nspec = importlib.util.spec_from_file_location("aura_plugin", path)\nmod = importlib.util.module_from_spec(spec)\nspec.loader.exec_module(mod)\nfn = getattr(mod, fname)\nv = fn(text, probe)\nif not isinstance(v, (int, float)) or v != v or v in (float("inf"), float("-inf")):\n    raise ValueError("retorno nao-float: %r" % (v,))\nprint(json.dumps({"ok": True, "value": float(v)}))'

def scan():
    """Retorna {fn_name: path} dos plugins vivos."""
    out = {}
    if not os.path.isdir(PLUGIN_DIR):
        return out
    for path in sorted(glob.glob(os.path.join(PLUGIN_DIR, "*.py"))):
        try:
            with open(path, encoding="utf-8") as f:
                src = f.read()
            for m in re.finditer(r"def (probe_[a-z0-9_]+)\s*\(", src):
                out[m.group(1)] = path
        except Exception:
            continue
    return out


def quarantine(path, motivo):
    try:
        os.replace(path, path + ".quarantine")
        with open(os.path.join(PLUGIN_DIR, "quarantine.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.time(), "plugin": os.path.basename(path),
                                "motivo": str(motivo)[:200]}, ensure_ascii=False) + "\n")
    except OSError:
        pass


def call(fn_name, text, probe, timeout=6.0):
    m = scan()
    path = m.get(fn_name)
    if not path:
        raise RuntimeError("plugin ausente: %s" % fn_name)
    proc = subprocess.run(
        [sys.executable, "-c", RUNNER, path, fn_name, str(text or ""), json.dumps(probe)],
        timeout=timeout, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or "erro desconhecido")[-160:])
    lines = [l for l in proc.stdout.strip().splitlines() if l.strip()]
    out = json.loads(lines[-1])
    if not out.get("ok"):
        raise RuntimeError(str(out)[:160])
    return out["value"]

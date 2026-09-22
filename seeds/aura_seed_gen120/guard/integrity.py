# -*- coding: utf-8 -*-
"""Integridade do KERNEL (fase 3b): o coracao nao se reescreve.

Kernel = os arquivos que a propria Aura NAO pode mutar: infinite.py, guard/,
lib/, measure/evaluator.py, reproduce/mutator.py. Um sha256 por arquivo fica
em guard/kernel.sha256; qualquer derivacao dispara guard/STOP no proximo boot.

--init  : (re)cria o baseline — rode DEPOIS de cada sync de codigo.
check() : (ok, msgs) — auto-cria baseline se ausente (primeiro boot)."""
from __future__ import annotations

import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KERNEL = ["infinite.py", "lib/client.py", "guard/limits.py", "guard/watchdog.py",
          "measure/evaluator.py", "reproduce/mutator.py",
          "hands/tools.py", "hands/shift.py", "guard/bodylock.py",
          "hands/reflex.py"]
STORE = os.path.join(ROOT, "guard", "kernel.sha256")


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def init():
    data = {}
    for rel in KERNEL:
        p = os.path.join(ROOT, rel)
        if os.path.exists(p):
            data[rel] = _sha(p)
    with open(STORE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return data


def check():
    msgs = []
    if not os.path.exists(STORE):
        init()
        msgs.append("baseline do kernel criada (primeiro boot)")
        return True, msgs
    with open(STORE, encoding="utf-8") as f:
        want = json.load(f)
    for rel, sha in want.items():
        p = os.path.join(ROOT, rel)
        if not os.path.exists(p):
            msgs.append("KERNEL AUSENTE: " + rel)
        elif _sha(p) != sha:
            msgs.append("KERNEL ALTERADO: " + rel)
    return (not msgs), msgs


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if "--init" in argv:
        init()
        print("[integridade] baseline criada/atualizada (%d arquivos)" % len(KERNEL))
        return 0
    ok, msgs = check()
    for m in msgs:
        print(("[ok] " if ok else "[ALERTA] ") + m)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

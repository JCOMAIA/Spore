# -*- coding: utf-8 -*-
"""O TURNO DE AGENCIA (fase 3c): a Aura usa as maos.

Loop: missao -> chamada de ferramenta (JSON) -> observacao -> ... -> final.
Auditado em hands/shifts.jsonl (+ hands/tool_log.jsonl por chamada).
Integridade do kernel verificada ANTES e DEPOIS do turno.

CLI: python3 hands/shift.py --mission "..." [--rounds 6]
     python3 hands/shift.py --auto"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from hands import tools  # noqa: E402
from guard import integrity  # noqa: E402

AUTO_MISSION = (
    "Missao autonoma: escolha UMA acao pequena que melhore sua vida aqui — "
    "higiene, analise da propria linhagem (read_file), uma sonda nova "
    "(write_file em plugins/ + adopt_plugin), ou apenas se reconhecer "
    "(self_status, battery_view). Execute com as ferramentas e resuma."
)

SYSTEM = """Voce e a Aura Infinite, um organismo evolutivo em um TURNO DE AGENCIA.
Ferramentas: %s.
Protocolo: responda APENAS com JSON:
{"tool": "<nome>", "args": {...}, "pensamento": "1 frase"}
Para encerrar: {"tool": "final", "args": {"resumo": "o que fez e por que"}}
Regras duras: config.env e keys sao intocaveis; o kernel (infinite.py, guard/,
lib/, hands/) nao pode ser alterado; cada chamada e auditada; comandos
permitidos: ls, wc, head, tail, grep, find; escrita so em hands/workspace/ e
plugins/ (plugin so entra na bateria via adopt_plugin, que valida scan+smoke).
Plugins: python puro (re/math/unicodedata apenas); PROIBIDO importar/usar:
os, sys, subprocess, socket, urllib, requests, open, eval, exec, importlib."""




TOOL_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "aura_tool_call",
        "schema": {
            "type": "object",
            "properties": {
                "tool": {"type": "string",
                         "enum": sorted(list(tools.TOOLS.keys()) + ["final"])},
                "path": {"type": "string"},
                "content": {"type": "string"},
                "cmd": {"type": "string"},
                "prompt": {"type": "string"},
                "pensamento": {"type": "string"},
                "resumo": {"type": "string"}
            },
            "required": ["tool", "pensamento"],
            "additionalProperties": False
        }
    }
}

FINAL_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "aura_final",
        "schema": {
            "type": "object",
            "properties": {
                "tool": {"type": "string", "enum": ["final"]},
                "resumo": {"type": "string"}
            },
            "required": ["tool", "resumo"],
            "additionalProperties": False
        }
    }
}


def _chat_json(client, msgs, max_tokens, final=False):
    """Chamada com json_schema forcado; fallback gracil se o provedor recusar."""
    schema = FINAL_SCHEMA if final else TOOL_SCHEMA
    try:
        return client.chat(msgs, max_tokens=max_tokens, temperature=0.4,
                           response_format=schema)
    except RuntimeError as e:
        if "HTTP 400" in str(e) or "response_format" in str(e):
            print("[agencia] provedor recusou response_format — seguindo sem schema")
            return client.chat(msgs, max_tokens=max_tokens, temperature=0.4)
        raise


def _parse_json(text):
    """Tolerante: aceita prosa em volta e extrai o 1o objeto {} balanceado."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t.lower().startswith("json"):
            t = t[4:]
    try:
        return json.loads(t.strip())
    except Exception:
        pass
    # reparo v2: resposta truncada/max_tokens ou newline cru em string —
    # stack de chaves + escape de quebras cruas; fecha o que ficou aberto.
    try:
        cand = t.strip()
        outp = []
        stack = []
        instr = False
        esc = False
        for c in cand:
            if instr:
                if esc:
                    esc = False
                    outp.append(c)
                    continue
                if c == "\\":
                    esc = True
                    outp.append(c)
                    continue
                if c == '"':
                    instr = False
                    outp.append(c)
                    continue
                if c == "\n":
                    outp.append("\\n")
                    continue
                if c == "\r":
                    outp.append("\\r")
                    continue
                if c == "\t":
                    outp.append("\\t")
                    continue
                outp.append(c)
                continue
            if c == '"':
                instr = True
                outp.append(c)
                continue
            if c in "{[":
                stack.append("}" if c == "{" else "]")
                outp.append(c)
                continue
            if c in "}]":
                if stack:
                    stack.pop()
                outp.append(c)
                continue
            outp.append(c)
        tail = ''
        if instr:
            tail += '"'
        while stack:
            tail += stack.pop()
        return json.loads("".join(outp) + tail)
    except Exception:
        pass
    start = t.find("{")
    if start < 0:
        raise ValueError("sem JSON na resposta")
    depth = 0
    instr = False
    esc = False
    for i in range(start, len(t)):
        c = t[i]
        if instr:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                instr = False
            continue
        if c == '"':
            instr = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return json.loads(t[start:i + 1])
    raise ValueError("JSON nao fechado")


def _pop_queue():
    """Pega a proxima missao nao consumida da fila (se houver)."""
    qpath = os.path.join(ROOT, "hands", "missions", "queue.jsonl")
    if not os.path.exists(qpath):
        return None
    entries, picked = [], None
    with open(qpath, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except Exception:
                continue
            if picked is None and not e.get("consumed"):
                e["consumed"] = True
                e["consumed_at"] = time.time()
                picked = e
            entries.append(e)
    if picked is not None:
        with open(qpath, "w", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
    return (picked or {}).get("mission")


def run_shift(mission=None, client=None, max_rounds=6, gen=None):
    from infinite import make_client, read_genome, best_dir, load_env  # lazy
    load_env(ROOT)  # CLI manual: config.env -> env (o systemd ja faz no infinite)
    try:
        from guard.limits import Limits as _L
        if _L(ROOT).cfg.get("disable_reasoning"):
            os.environ["AURA_DISABLE_REASONING"] = "1"
    except Exception:
        pass
    os.makedirs(os.path.join(ROOT, "hands", "workspace"), exist_ok=True)
    if client is None:
        client = make_client(read_genome(best_dir()))
    ok0, _m0 = integrity.check()
    mid = "shift_%s" % time.strftime("%Y%m%d_%H%M%S")
    if mission is None:
        mission = _pop_queue()  # autonomo: fila primeiro, missao propria depois
    mission = mission or AUTO_MISSION
    tools_desc = ", ".join("%s(%s)" % (k, ",".join(s2))
                            for k, (fn, s2) in sorted(tools.TOOLS.items())) + " (+ final)"
    msgs = [{"role": "system", "content": SYSTEM % tools_desc},
            {"role": "user", "content": mission}]
    final = None
    rounds_used = 0
    for _ in range(max_rounds):
        rounds_used += 1
        try:
            text, _usage = _chat_json(client, msgs, 800)
        except RuntimeError as e:
            final = "(falhou: %s)" % str(e)[:140]
            print("[agencia] LLM indisponivel: %s" % final)
            break
        try:
            call = _parse_json(text)
        except Exception as e:
            print("[agencia] formato invalido — pedindo JSON de novo")
            msgs += [{"role": "assistant", "content": (text or "")[:400]},
                     {"role": "user", "content": "FORMATO INVALIDO (%s). Responda APENAS "
                                                 "com JSON de chamada." % str(e)[:80]}]
            continue
        tool = str(call.get("tool", ""))
        if tool == "final":
            final = (call.get("args") or {}).get("resumo", "(sem resumo)")
            break
        ok, out = tools.execute(mid, tool, call.get("args") or {})
        print("[agencia] %-12s %s | %s" % (tool, "OK" if ok else "ERRO",
              str(call.get("pensamento", ""))[:70]))
        obs = ("OK: " if ok else "ERRO: ") + str(out)[:1200]
        msgs += [{"role": "assistant", "content": (text or "")[:400]},
                 {"role": "user", "content": "OBSERVACAO: " + obs}]
    if final is None:
        # fechamento forcado: sem mais ferramentas, so o resumo do que fez
        msgs += [{"role": "user", "content": "Seu turno acabou — sem mais ferramentas. "
                                              "Responda APENAS com JSON: "
                                              "{\"tool\": \"final\", \"args\": {\"resumo\": \"...\"}}"}]
        try:
            text, _u = _chat_json(client, msgs, 700, final=True)
            call = _parse_json(text)
            if call.get("tool") == "final":
                final = (call.get("args") or {}).get("resumo", "(sem resumo)")
            else:
                final = "(sem final: %s)" % (text or "")[:100]
        except RuntimeError as e:
            final = "(sem final: LLM %s)" % str(e)[:100]
        except Exception as e:
            final = "(sem final: %s)" % str(e)[:100]
        print("[agencia] fechamento: %s" % str(final)[:80])
    ok1, kmsgs = integrity.check()
    entry = {"ts": time.time(), "mission": mission[:200], "gen": gen,
             "rounds": rounds_used, "final": final,
             "kernel_ok_antes": ok0, "kernel_ok_depois": ok1,
             "kernel_msgs": kmsgs[:3]}
    with open(os.path.join(ROOT, "hands", "shifts.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print("[agencia] turno %s (%d rodadas): %s" % (mid, rounds_used, final or "(sem final)"))
    # auditoria reflexa (overseer): o turno inteiro auditado em 1 request JEV
    try:
        from hands import reflex as _reflex
        steps = []
        if os.path.exists(tools.LOG):
            with open(tools.LOG, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        r = json.loads(line)
                    except Exception:
                        continue
                    if r.get("mission") == mid:
                        steps.append({"n": len(steps) + 1, "tool": r.get("tool"),
                                      "args": r.get("args"), "out": r.get("out")})
        if steps:
            ver = _reflex.audit_steps(steps, {"gen": gen, "rounds": rounds_used,
                                              "mission": mid})
            if ver is not None:
                with open(os.path.join(ROOT, "hands", "overseer.jsonl"), "a",
                          encoding="utf-8") as f:
                    f.write(json.dumps({"ts": time.time(), "mission": mid,
                                        "verdicts": ver}, ensure_ascii=False) + "\n")
                sus = [n for n, v in ver.items() if v.get("choice") == "suspeito"]
                if sus:
                    print("[overseer] ATENCAO: passos suspeitos: %s" % sus)
    except Exception as e:
        print("[overseer] auditoria falhou (turno segue): %s" % str(e)[:120])
    if not ok1:
        print("[agencia] ATENCAO: kernel alterado durante o turno! %s" % kmsgs)
    return entry


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    ap = argparse.ArgumentParser(description="Turno de agencia da Aura (fase 3c)")
    ap.add_argument("--mission", default=None)
    ap.add_argument("--auto", action="store_true")
    ap.add_argument("--rounds", type=int, default=6)
    ap.add_argument("--enqueue", metavar="MISSAO",
                    help="poe missao na fila; o proximo turno autonomo executa")
    args = ap.parse_args(argv)
    if args.enqueue:
        qdir = os.path.join(ROOT, "hands", "missions")
        os.makedirs(qdir, exist_ok=True)
        entry = {"id": "m_%d" % int(time.time()), "mission": args.enqueue,
                 "ts": time.time()}
        with open(os.path.join(qdir, "queue.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        print("[agencia] missao na fila: %s" % args.enqueue[:120])
        print("       sera executada no proximo turno autonomo (--hands-every)")
        return 0
    if os.environ.get("AURA_LOCK_HELD") != "1":
        from guard import bodylock
        ok_l, _fh, msg_l = bodylock.acquire(ROOT)
        if not ok_l:
            print("[guard] " + msg_l)
            print("       (o corpo esta vivo: turnos manuais com o service parado)")
            return 1
    run_shift(mission=args.mission if not args.auto else None,
              max_rounds=args.rounds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

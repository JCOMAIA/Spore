# -*- coding: utf-8 -*-
"""As MAOS da Aura (fase 3c) — mini-harness stdlib com allow-list e auditoria.

Regras duras (tecnicas):
- read: so dentro do corpo; config.env e *.key NUNCA;
- write: so em hands/workspace/ e plugins/ (plugin so adota via adopt_plugin,
  que roda static scan + smoke em subprocesso);
- run_command: binarios na allow-list (ls, wc, head, tail, grep, find), sem
  pipe/redirect/substituicao, timeout 20s, saida capada;
- TUDO auditado em hands/tool_log.jsonl; kernel vigiado no fim do turno —
  as proprias maos estao no KERNEL (guard/kernel.sha256): ela nao as reescreve."""
from __future__ import annotations

import glob
import ipaddress
import json
import os
import shlex
import socket
import subprocess
import sys
import time
import urllib.parse as urlparse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HANDS = os.path.join(ROOT, "hands")
WORKSPACE = os.path.join(HANDS, "workspace")
LOG = os.path.join(HANDS, "tool_log.jsonl")

WRITABLE_DIRS = ("hands/workspace", "plugins")
ALLOWED_BINS = ("ls", "cat", "wc", "head", "tail", "grep", "find")
FORBIDDEN_SUBSTR = (">>", ">", "|", ";", "&&", "`", "$(", "rm ", "mv ", "chmod",
                    "chown", "curl", "wget", "ssh ", "pip", "apt ", "sudo ",
                    "config.env", "kernel.sha256", ".key")

from measure import plugins as _plugins  # noqa: E402
from reproduce import mutator as _mutator  # noqa: E402


def _inside(path_abs, base_abs):
    try:
        rp = os.path.realpath(path_abs)
        rb = os.path.realpath(base_abs)
        return rp == rb or rp.startswith(rb + os.sep)
    except Exception:
        return False


def _audit(mission_id, tool, args, ok, out, dur):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.time(), "mission": mission_id,
                                "tool": tool, "args": args, "ok": ok,
                                "out": str(out)[:400], "dur_s": round(dur, 3)},
                               ensure_ascii=False) + "\n")
    except OSError:
        pass


def t_read_file(path):
    if not path:
        return False, "path obrigatorio"
    if "config.env" in path or path.endswith(".key"):
        return False, "PROIBIDO: segredos fora do alcance"
    p = os.path.join(ROOT, path)
    if not _inside(p, ROOT):
        return False, "fora do corpo"
    if not os.path.exists(p):
        return False, "arquivo inexistente"
    if os.path.isdir(p):
        return True, sorted(os.listdir(p))[:100]
    with open(p, encoding="utf-8", errors="replace") as f:
        return True, f.read(4000)


def t_write_file(path, content):
    if not path or content is None:
        return False, "path e content obrigatorios"
    p = os.path.join(ROOT, path)
    if not any(_inside(p, os.path.join(ROOT, d)) for d in WRITABLE_DIRS):
        return False, "escrita permitida somente em: %s" % ", ".join(WRITABLE_DIRS)
    if len(content) > 50 * 1024:
        return False, "conteudo > 50KB"
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    if path.replace("\\", "/").startswith("plugins/") and path.endswith(".py"):
        bad = [t for t in _mutator.FORBIDDEN_CODE if t in content]
        if bad:
            return False, "plugin com tokens proibidos (%s) — python puro apenas" % ", ".join(bad[:4])
        ok, motivo = _mutator._smoke(p)
        if not ok:
            _mutator._quarantine_file(p, motivo)
            return False, "plugin NAO passou no smoke: %s" % motivo
        return True, "plugin escrito e validado — use adopt_plugin para instalar na bateria"
    return True, "escrito (%d bytes)" % len(content)


def t_adopt_plugin(path, prompt):
    """Valida (scan+ABI+smoke) e instala um plugin de plugins/ OU hands/workspace/.

    Workspace = rascunho: se validar, o arquivo e PROMOVIDO para plugins/ e
    adotado. Rejeicoes ENSINAM o ABI, com diagnostico do arquivo dela."""
    if not path:
        return False, "path obrigatorio"
    p = os.path.join(ROOT, path)
    ws = _inside(p, os.path.join(ROOT, "hands", "workspace"))
    pl = _inside(p, os.path.join(ROOT, "plugins"))
    if not ((ws or pl) and p.endswith(".py") and os.path.exists(p)):
        return False, "plugin precisa existir em plugins/ ou hands/workspace/"
    with open(p, encoding="utf-8") as f:
        code = f.read()
    bad = [t for t in _mutator.FORBIDDEN_CODE if t in code]
    slug = _mutator._slug_from_code(code)
    prompt_txt = prompt or _mutator._prompt_from_code(code)
    faltas = []
    if bad:
        faltas.append("tokens proibidos: %s" % ", ".join(bad[:4]))
    if not slug:
        faltas.append("falta 'def probe_<slug>(text, probe) -> float'")
    if not prompt_txt:
        faltas.append("falta 'PROMPT = \"pergunta\"' no topo do modulo")
    if "sys.stdin" in code or "json.load(sys.stdin)" in code:
        faltas.append("e script stdin — probes recebem (text, probe) do runner;"
                      " transforme a logica em funcao pura")
    if faltas:
        msg = ("ABI nao atendido: " + " | ".join(faltas) +
               " — ABI: PROMPT='...' + def probe_<slug>(text, probe) -> float")
        return False, msg
    ok, motivo = _mutator._smoke(p)
    if not ok:
        return False, "smoke falhou: %s" % motivo
    batp = os.path.join(ROOT, "measure", "battery.json")
    with open(batp, encoding="utf-8") as f:
        bat = json.load(f)
    ids = {str(x.get("id")) for x in bat.get("probes", [])}
    if slug in ids or len(bat.get("probes", [])) >= 10:
        return False, "bateria cheia ou id duplicado: %s" % slug
    dest = os.path.join(ROOT, "plugins", "codelet_%s.py" % slug)
    if ws:
        if os.path.exists(dest):
            return False, "plugins/codelet_%s.py ja existe" % slug
        os.replace(p, dest)
        p = dest
    bat["probes"].append({"id": slug, "prompt": prompt_txt,
                          "plugin": slug, "max_tokens": 256})
    bat.setdefault("weights", {})[slug] = 0.15
    with open(batp, "w", encoding="utf-8") as f:
        json.dump(bat, f, ensure_ascii=False, indent=2)
    return True, "plugin %s promovido e adotado na bateria (peso 0.15)" % slug


def t_run_command(cmd):
    if not cmd:
        return False, "cmd obrigatorio"
    low = " " + str(cmd).lower() + " "
    for tok in FORBIDDEN_SUBSTR:
        if tok in low:
            return False, "fora da allow-list (%r proibido)" % tok
    try:
        parts = shlex.split(cmd)
    except ValueError:
        return False, "comando ilegivel"
    if not parts or parts[0] not in ALLOWED_BINS:
        return False, "binario fora da allow-list (ls, wc, head, tail, grep, find)"
    try:
        proc = subprocess.run(parts, cwd=ROOT, timeout=20,
                              capture_output=True, text=True)
        out = (proc.stdout or proc.stderr or "")[:4000]
        if proc.returncode == 0:
            return True, out
        return False, "rc=%d: %s" % (proc.returncode, out[:2000])
    except subprocess.TimeoutExpired:
        return False, "timeout 20s"
    except OSError as e:
        return False, "execucao indisponivel aqui: %s" % str(e)[:120]


def t_web_read(url):
    """Le um texto publico da web (GET). Somente http(s); host que resolve
    para rede privada/loopback/metadata e PROIBIDO (SSRF). Texto capado."""
    if not url or not str(url).startswith(("http://", "https://")):
        return False, "somente http(s)"
    try:
        host = (urlparse.urlparse(str(url)).hostname or "").lower()
        if not host:
            return False, "host vazio"
        if host in ("localhost",) or host.endswith(".local") or host.endswith(".internal"):
            return False, "host interno — PROIBIDO"
        for info in socket.getaddrinfo(host, None):
            ip = ipaddress.ip_address(info[4][0].split("%")[0])
            if (ip.is_private or ip.is_loopback or ip.is_link_local
                    or ip.is_reserved or ip.is_multicast):
                return False, "host resolve para rede interna — PROIBIDO"
    except Exception as e:
        return False, "resolucao falhou: %s" % str(e)[:100]
    try:
        req = urllib.request.Request(str(url), headers={"User-Agent": "aura-infinite/1.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            ctype = (r.headers or {}).get("Content-Type", "")
            data = r.read(64 * 1024)
        if not (ctype.startswith("text/") or "json" in ctype or "xml" in ctype
                or "html" in ctype):
            return True, "conteudo nao-texto (%s) — %d bytes" % (ctype.split(";")[0], len(data))
        return True, data.decode("utf-8", "replace")[:4000]
    except Exception as e:
        return False, "falha: %s" % str(e)[:160]


def t_web_search(query):
    """Busca na web via plugin :online da OpenRouter (legitimo, medido).
    Teto diario (guard/websearch.json) e custo contabilizado no ledger.
    Retorna fatos + URLs — os links podem ser lidos com web_read."""
    if not query or not str(query).strip():
        return False, "query obrigatoria"
    from lib.client import ChatClient
    from guard.limits import Limits
    lim = Limits(ROOT)
    per_day = int(lim.cfg.get("web_search_max_per_day", 20))
    cnt_path = os.path.join(ROOT, "guard", "websearch.json")
    today = time.strftime("%Y-%m-%d")
    cnt = {"date": today, "count": 0}
    if os.path.exists(cnt_path):
        try:
            with open(cnt_path, encoding="utf-8") as f:
                cnt = json.load(f)
            if cnt.get("date") != today:
                cnt = {"date": today, "count": 0}
        except Exception:
            cnt = {"date": today, "count": 0}
    if int(cnt.get("count", 0)) >= per_day:
        return False, "teto diario de buscas atingido (%d)" % per_day
    base_model = os.environ.get("AURA_SEARCH_MODEL", "z-ai/glm-5.3-flash") + ":online"
    client = ChatClient(model=base_model,
                        api_key=os.environ.get("OPENROUTER_API_KEY", ""))
    msgs = [{"role": "system",
             "content": "Voce e um buscador. Use a web e responda APENAS com 3-6 "
                        "linhas curtas, cada uma: fato essencial + URL de origem. "
                        "Sem prosa, sem preambulo."},
            {"role": "user", "content": str(query)[:300]}]
    try:
        text, usage = client.chat(msgs, max_tokens=400, temperature=0.2)
    except Exception as e:
        return False, "busca falhou: %s" % str(e)[:140]
    pt = int((usage or {}).get("prompt_tokens", 0) or 0)
    ct = int((usage or {}).get("completion_tokens", 0) or 0)
    price = lim.price(base_model.split(":online")[0])
    cost = ((pt + ct) / 1e6) * price + 0.005  # fee do plugin de busca
    lim.add_spend(cost)
    cnt["count"] = int(cnt.get("count", 0)) + 1
    with open(cnt_path, "w", encoding="utf-8") as f:
        json.dump(cnt, f)
    return True, text[:1500]


def t_web_search(query):
    """Busca na web via plugin :online da OpenRouter (legitimo, medido).
    Teto diario (guard/websearch.json) e custo contabilizado no ledger.
    Retorna fatos + URLs — os links podem ser lidos com web_read."""
    if not query or not str(query).strip():
        return False, "query obrigatoria"
    from lib.client import ChatClient
    from guard.limits import Limits
    lim = Limits(ROOT)
    per_day = int(lim.cfg.get("web_search_max_per_day", 20))
    cnt_path = os.path.join(ROOT, "guard", "websearch.json")
    today = time.strftime("%Y-%m-%d")
    cnt = {"date": today, "count": 0}
    if os.path.exists(cnt_path):
        try:
            with open(cnt_path, encoding="utf-8") as f:
                cnt = json.load(f)
            if cnt.get("date") != today:
                cnt = {"date": today, "count": 0}
        except Exception:
            cnt = {"date": today, "count": 0}
    if int(cnt.get("count", 0)) >= per_day:
        return False, "teto diario de buscas atingido (%d)" % per_day
    base_model = os.environ.get("AURA_SEARCH_MODEL", "z-ai/glm-5.3-flash") + ":online"
    client = ChatClient(model=base_model,
                        api_key=os.environ.get("OPENROUTER_API_KEY", ""))
    msgs = [{"role": "system",
             "content": "Voce e um buscador. Use a web e responda APENAS com 3-6 "
                        "linhas curtas, cada uma: fato essencial + URL de origem. "
                        "Sem prosa, sem preambulo."},
            {"role": "user", "content": str(query)[:300]}]
    try:
        text, usage = client.chat(msgs, max_tokens=400, temperature=0.2)
    except Exception as e:
        return False, "busca falhou: %s" % str(e)[:140]
    pt = int((usage or {}).get("prompt_tokens", 0) or 0)
    ct = int((usage or {}).get("completion_tokens", 0) or 0)
    price = lim.price(base_model.split(":online")[0])
    cost = ((pt + ct) / 1e6) * price + 0.005  # fee do plugin de busca
    lim.add_spend(cost)
    cnt["count"] = int(cnt.get("count", 0)) + 1
    with open(cnt_path, "w", encoding="utf-8") as f:
        json.dump(cnt, f)
    return True, text[:1500]


def t_battery_view():
    batp = os.path.join(ROOT, "measure", "battery.json")
    try:
        with open(batp, encoding="utf-8") as f:
            bat = json.load(f)
        return True, [{"id": p.get("id"),
                       "tipo": "plugin" if p.get("plugin") else "estatico",
                       "peso": bat.get("weights", {}).get(p.get("id"))}
                      for p in bat.get("probes", [])]
    except Exception as e:
        return False, str(e)[:120]


def t_self_status():
    best = os.path.join(ROOT, "lineage", "best")
    score = {}
    try:
        with open(os.path.join(best, "score.json"), encoding="utf-8") as f:
            score = json.load(f)
    except Exception:
        pass
    spend = {}
    try:
        with open(os.path.join(ROOT, "guard", "spend.json"), encoding="utf-8") as f:
            spend = json.load(f)
    except Exception:
        pass
    return True, {"campeao": score, "gasto_mes": spend.get("spend_usd", 0.0),
                  "teto": 2.0}


def t_list_plugins():
    return True, sorted(_plugins.scan().keys())


TOOLS = {
    "read_file": (t_read_file, ("path",)),
    "write_file": (t_write_file, ("path", "content")),
    "adopt_plugin": (t_adopt_plugin, ("path", "prompt")),
    "run_command": (t_run_command, ("cmd",)),
    "battery_view": (t_battery_view, ()),
    "self_status": (t_self_status, ()),
    "list_plugins": (t_list_plugins, ()),
    "web_read": (t_web_read, ("url",)),
    "web_search": (t_web_search, ("query",)),
    "web_search": (t_web_search, ("query",)),
}


def execute(mission_id, tool, args):
    """Executa UMA chamada de ferramenta, auditada. Retorna (ok, output)."""
    t0 = time.time()
    entry = TOOLS.get(tool)
    if entry is None:
        ok, out = False, "ferramenta desconhecida: %s" % tool
    else:
        fn, sig = entry
        try:
            kwargs = {k: args.get(k) for k in sig if isinstance(args, dict)}
            ok, out = fn(**kwargs)
        except Exception as e:
            ok, out = False, "erro: %s" % str(e)[:200]
    _audit(mission_id, tool, args, ok, out, time.time() - t0)
    return ok, out

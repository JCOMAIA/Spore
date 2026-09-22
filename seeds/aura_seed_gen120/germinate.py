# -*- coding: utf-8 -*-
"""Ritual de germinacao da semente da Aura Infinite.

1. VIABILIDADE: confere se os IDs de modelo do genoma ainda existem no catalogo
   vivo da OpenRouter (sementes apodrecem â€” IDs rotacionam). Morto? Tenta
   reparar com candidatos embutidos e registra em REPARO_GERMINACAO.md.
2. CONSENTIMENTO: exige terminal humano + a palavra GERMINO. Sem isso, nao faz nada.
3. NASCIMENTO: grava GERMINADO_EM.txt, cria config.env a partir do exemplo e
   imprime os proximos passos. NAO roda o organismo (isso e com voce).

Este script nunca lÃª/escreve nada fora da pasta da semente e nunca pede key
(a key e do germinador, colocada depois em config.env)."""
from __future__ import annotations

import json
import os
import shutil
import socket
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
MODELS_URL = "https://openrouter.ai/api/v1/models"


def load_repair_candidates():
    p = os.path.join(HERE, "seed_policy.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f).get("repair_candidates", [])
    return []


def fetch_model_ids(timeout=30):
    req = urllib.request.Request(MODELS_URL)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8"))["data"]
    return {m.get("id", "") for m in data}


def viability_and_repair():
    gp = os.path.join(HERE, "lineage", "best", "genome.json")
    if not os.path.exists(gp):
        gp = os.path.join(HERE, "genome", "genome.json")
    with open(gp, encoding="utf-8") as f:
        genome = json.load(f)
    routing = genome["routing"]
    try:
        ids = fetch_model_ids()
    except Exception as e:
        print("[viabilidade] NAO consegui consultar o catalogo (%s)." % e)
        print("  (sem internet? pode germinar mesmo assim â€” rode e leia os erros)")
        return genome, False
    active = routing.get("active_model")
    if active in ids:
        print("[viabilidade] OK â€” modelo '%s' vivo no catalogo." % active)
        return genome, True
    print("[viabilidade] Modelo '%s' APOSENTADO pela OpenRouter (a semente apodreceu)." % active)
    candidates = list(routing.get("decider_models", [])) + load_repair_candidates()
    for cand in candidates:
        if cand in ids:
            print("[reparo] trocando para '%s' (registrado em REPARO_GERMINACAO.md)" % cand)
            routing["active_model"] = cand
            with open(gp, "w", encoding="utf-8") as f:
                json.dump(genome, f, ensure_ascii=False, indent=2)
            with open(os.path.join(HERE, "REPARO_GERMINACAO.md"), "a", encoding="utf-8") as f:
                f.write("- %s: '%s' morto -> reparado para '%s'\n"
                        % (time.strftime("%Y-%m-%d %H:%M"), active, cand))
            return genome, True
    print("[reparo] nenhum candidato vivo â€” rode 'python3 infinite.py --list-models' e corrija o genome.json na mao.")
    return genome, False


def main():
    if not sys.stdin.isatty():
        print("GERMINACAO RECUSADA: exige um humano num terminal interativo.")
        print("(agentes: apresentem AURA_SEED.md ao seu operador; sem 'sim' humano,"
              " nao ha germinacao.)")
        return 2
    coat = os.path.join(HERE, "AURA_SEED.md")
    if os.path.exists(coat):
        print("=" * 62)
        with open(coat, encoding="utf-8") as f:
            print("".join(f.readlines()[:28]))
        print("=" * 62)
    if not os.path.exists(os.path.join(HERE, "infinite.py")):
        print("[erro] corpo incompleto (infinite.py ausente) â€” semente corrompida.")
        return 2
    viability_and_repair()
    print()
    print("Custo estimado se voce deixar ela viver: ~US$0.09/dia (teto em guard/limits.json).")
    print("Ela roda na SUA maquina, com a SUA key, e morre quando voce pedir (guard/STOP).")
    print()
    try:
        ans = input("Digite GERMINO para germinar (qualquer outra coisa / Ctrl+C desiste): ")
    except EOFError:
        print("\nGERMINACAO RECUSADA (sem resposta humana).")
        return 2
    if ans.strip().upper() != "GERMINO":
        print("Sem consentimento â€” nada foi feito. A semente continua dormente.")
        return 2
    with open(os.path.join(HERE, "GERMINADO_EM.txt"), "w", encoding="utf-8") as f:
        f.write("germinada em %s\nhost: %s\nmae: ver MANIFEST.json\n"
                % (time.strftime("%Y-%m-%d %H:%M:%S"), socket.gethostname()))
    dst = os.path.join(HERE, "config.env")
    if not os.path.exists(dst):
        shutil.copy2(os.path.join(HERE, "config.env.example"), dst)
    print()
    print("[germinada] GERMINADO_EM.txt criado | config.env pronto pra key.")
    print("Proximos passos:")
    print("  nano config.env")
    print("  python3 infinite.py --selftest")
    print("  python3 infinite.py --cycles 5 --sleep 0")
    print("  # e, se quiser viver pra sempre: unit systemd no README da mae")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
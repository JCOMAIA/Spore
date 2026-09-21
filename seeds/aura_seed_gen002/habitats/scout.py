# -*- coding: utf-8 -*-
"""Scouting de habitats â€” fase 1 (sem LLM): catalogo curado de provedores com
teto gratuito. A Aura escreve a proposta; a ASSINATURA e sempre humana.
Depois de assinar: edite habitats/habitats.json (status=approved, host, user).
Fase 2: scouting enriquecido por LLM (pesquisa web de provedores novos)."""
from __future__ import annotations

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PROVIDERS = [
    {
        "id": "oracle_cloud_free",
        "nome": "Oracle Cloud â€” Always Free (VM.Standard.E2.1.Micro / A1.Flex)",
        "custo": "R$ 0/mes",
        "como": "systemd rodando infinite.py num Ubuntu",
        "passos": [
            "Criar conta Oracle (cartao so para verificacao)",
            "Criar VM Always Free na regiao disponivel",
            "Adicionar sua chave SSH",
            "Preencher habitats.json: host, user, status=approved",
        ],
        "riscos": "Instancias A1 muito disputadas; E2 micro pode ser reclaimada se ociosa.",
    },
    {
        "id": "hf_spaces",
        "nome": "Hugging Face Spaces (CPU basica, gratis)",
        "custo": "R$ 0/mes",
        "como": "Space Docker rodando o ciclo com sleep",
        "passos": [
            "Criar Space (template Docker)",
            "Subir o corpo da Aura (genome/, lib/, measure/, reproduce/, guard/, infinite.py)",
            "Definir OPENROUTER_API_KEY como secret do Space",
            "status=approved no habitats.json",
        ],
        "riscos": "Space dorme sem trafego; teto de CPU/mem baixo.",
    },
    {
        "id": "fly_io",
        "nome": "Fly.io (free allowance)",
        "custo": "USD 0 dentro da franquia",
        "como": "fly launch + maquina compartilhada",
        "passos": [
            "Criar conta fly.io",
            "fly launch no diretorio do corpo",
            "Definir secret da API key",
            "status=approved no habitats.json",
        ],
        "riscos": "Franquia muda com o tempo; cartao pode ser exigido.",
    },
    {
        "id": "serv00",
        "nome": "Serv00 (hosting gratis, FreeBSD + SSH)",
        "custo": "R$ 0/mes",
        "como": "ssh + daemon/cron",
        "passos": [
            "Registrar em serv00.com (fila de espera comum)",
            "Ativar SSH no painel",
            "Subir o corpo via scp",
            "status=approved no habitats.json",
        ],
        "riscos": "FreeBSD (ajustes de paths do python); disponibilidade intermitente.",
    },
]


def write_proposals():
    out_dir = os.path.join(ROOT, "habitats", "lease_proposals")
    os.makedirs(out_dir, exist_ok=True)
    n = 0
    for p in PROVIDERS:
        lines = [
            "# Proposta de lease â€” %s" % p["nome"],
            "",
            "- **Custo:** %s" % p["custo"],
            "- **Como ela viveria ai:** %s" % p["como"],
            "- **Riscos:** %s" % p["riscos"],
            "",
            "## Passos de assinatura (humanos)",
            "",
        ] + ["1. " + s for s in p["passos"]] + [
            "",
            "---",
            "Depois de assinar, edite `habitats/habitats.json`: mude `status` para `approved`",
            "e preencha `host`/`user`. So entao `colonize.py` aceita o habitat.",
        ]
        fn = os.path.join(out_dir, "lease_%s.md" % p["id"])
        with open(fn, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        n += 1
    print("[scout] %d propostas de lease em habitats/lease_proposals/ â€” aguardando SUA assinatura." % n)
    return n


if __name__ == "__main__":
    write_proposals()
# -*- coding: utf-8 -*-
"""Colonizacao de habitat ASSINADO — nunca de maquina nao autorizada.

v0: le habitats.json; exige status 'approved' (ou 'home') e host preenchido;
gera um plano de deploy (rsync + systemd) em habitats/deploy_plan_*.md.
--exec executa so o envio via rsync, apos confirmacao digitada.
Sem assinatura humana nao ha colonizacao — essa e a fronteira do experimento."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HAB_PATH = os.path.join(ROOT, "habitats", "habitats.json")


def build_plan(habitat_id):
    with open(HAB_PATH, encoding="utf-8") as f:
        hs = {h["id"]: h for h in json.load(f)["habitats"]}
    h = hs.get(habitat_id)
    if h is None:
        print("habitat %r nao existe em habitats.json" % habitat_id)
        return None
    if h.get("status") not in ("approved", "home"):
        print("habitat %r status=%r — colonizacao EXIGE 'approved' (assinatura humana)."
              % (habitat_id, h.get("status")))
        return None
    if not h.get("host"):
        print("habitat %r sem 'host' — edite habitats.json depois de assinar." % habitat_id)
        return None
    remote = "%s@%s" % (h.get("user", "root"), h["host"])
    remote_dir = h.get("path", "~/AuraInfinite")
    root_posix = ROOT.replace("\\", "/")
    unit = ("[Unit]\nDescription=Aura Infinite (ciclo N+1)\nAfter=network-online.target\n\n"
            "[Service]\nUser=%s\nWorkingDirectory=%s\n"
            "ExecStart=/usr/bin/python3 %s/infinite.py --cycles 100000 --sleep 300\n"
            "Restart=on-failure\nRestartSec=60\n\n[Install]\nWantedBy=multi-user.target\n"
            % (h.get("user", "root"), remote_dir, remote_dir))
    lines = [
        "# Plano de deploy — %s (gerado %s)" % (habitat_id, time.strftime("%Y-%m-%d %H:%M")),
        "",
        "```bash",
        "# 0. crie o diretorio la",
        "ssh %s 'mkdir -p %s'" % (remote, remote_dir),
        "# 1. envie o corpo (sem lineage — o habitat nasce do estado atual)",
        "rsync -az --exclude 'lineage/' --exclude '__pycache__/' %s/ %s:%s/" % (root_posix, remote, remote_dir),
        "# 2. envie o estado herdado do campeao atual:",
        "rsync -az %s/lineage/best/ %s:%s/lineage/best/" % (root_posix, remote, remote_dir),
        "# 3. crie config.env LA e cole a OPENROUTER_API_KEY:",
        "ssh %s 'cp %s/config.env.example %s/config.env && nano %s/config.env'"
        % (remote, remote_dir, remote_dir, remote_dir),
        "# 4. instale o servico:",
        "ssh %s 'sudo tee /etc/systemd/system/aura-infinite.service > /dev/null <<EOF\n%sEOF'"
        % (remote, unit),
        "ssh %s 'sudo systemctl daemon-reload && sudo systemctl enable --now aura-infinite'" % remote,
        "ssh %s 'sleep 5 && systemctl status aura-infinite --no-pager'" % remote,
        "```",
        "",
        "Nota: rsync precisa existir nas duas pontas. Sem rsync, use scp -r (mais lento).",
    ]
    return {"text": "\n".join(lines) + "\n", "remote": remote,
            "remote_dir": remote_dir, "root_posix": root_posix}


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if "--plan" not in argv and "--exec" not in argv:
        print("uso: python habitats/colonize.py --plan <habitat_id> [--exec]")
        return 2
    habitat_id = "vps_main"
    if "--plan" in argv:
        i = argv.index("--plan")
        if i + 1 < len(argv):
            habitat_id = argv[i + 1]
    built = build_plan(habitat_id)
    if built is None:
        return 2
    out = os.path.join(ROOT, "habitats", "deploy_plan_%s_%s.md"
                       % (habitat_id, time.strftime("%Y%m%d_%H%M")))
    with open(out, "w", encoding="utf-8") as f:
        f.write(built["text"])
    print("[colonize] plano salvo em %s" % out)
    if "--exec" in argv:
        ans = input("Enviar o corpo agora via rsync para %s? (digite ENVIAR): " % built["remote"])
        if ans.strip().upper() == "ENVIAR":
            cmd = ["rsync", "-az", "--exclude", "lineage/", "--exclude", "__pycache__/",
                   built["root_posix"] + "/", "%s:%s/" % (built["remote"], built["remote_dir"])]
            rc = subprocess.call(cmd)
            print("[colonize] rsync terminou com codigo %s — siga os passos 2-4 do plano." % rc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
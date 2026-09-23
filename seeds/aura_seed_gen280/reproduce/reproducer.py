# -*- coding: utf-8 -*-
"""A reproducao: nasce uma geracao = copia do corpo com UMA mutacao aplicada.

gen_NNN/{genome.json, mutation.json, manifest.json, state/}
Heranca de verdade: o filho recebe a memoria (facts) e os niveis motivacionais
do pai â€” identidade que atravessa geracoes."""
from __future__ import annotations

import json
import os
import shutil
import time


def spawn(root, gen_n, genome, state, parent_dir, mutation_record):
    gen_dir = os.path.join(root, "lineage", "gen_%03d" % gen_n)
    if os.path.exists(gen_dir):
        shutil.rmtree(gen_dir)
    os.makedirs(os.path.join(gen_dir, "state"))
    with open(os.path.join(gen_dir, "genome.json"), "w", encoding="utf-8") as f:
        json.dump(genome, f, ensure_ascii=False, indent=2)
    with open(os.path.join(gen_dir, "state", "memory.json"), "w", encoding="utf-8") as f:
        json.dump({"facts": (state or {}).get("facts", {})}, f, ensure_ascii=False, indent=2)
    drives = (state or {}).get("drives", {"curiosity": 0.5, "connection": 0.5})
    with open(os.path.join(gen_dir, "state", "drives.json"), "w", encoding="utf-8") as f:
        json.dump(drives, f, ensure_ascii=False, indent=2)
    with open(os.path.join(gen_dir, "mutation.json"), "w", encoding="utf-8") as f:
        json.dump(mutation_record, f, ensure_ascii=False, indent=2)
    manifest = {"gen": gen_n, "born_ts": time.time(),
                "parent": os.path.basename(parent_dir) if parent_dir else None,
                "mutation_op": mutation_record.get("op")}
    with open(os.path.join(gen_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    return gen_dir
# -*- coding: utf-8 -*-
"""
AURA INFINITE â€” o ciclo N+1.

N   = o corpo inteiro: genoma (persona, roteamento, skills, pesos de mutacao)
      + estado herdado (memoria + niveis motivacionais).
N+1 = uma copia com UMA mutacao qualquer, aplicada agora, medida depois.

Orgaos por ciclo:
  1. MEDIR       bateria fixa de probes (measure/) -> score [0,1]
  2. MUTAR       1 mutacao sorteada do menu, com pesos (reproduce/mutator.py)
  3. REPRODUZIR  nasce gen_NNN herdando estado (reproduce/reproducer.py)
  4. MEDIR o filho
  5. PODAR       filho vira campeao se score >= pai - epsilon; senao MORRE
  6. REGISTRAR   lineage/lineage.jsonl (genealogia completa)

Guardas (guard/): teto de gasto mensal, teto de disco, teto de geracoes,
e kill switch manual â€” crie o arquivo guard/STOP e o loop para no proximo ciclo.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from lib.client import ChatClient, list_models  # noqa: E402
from measure import evaluator  # noqa: E402
from reproduce import mutator, reproducer  # noqa: E402
from guard.limits import Limits  # noqa: E402

LINEAGE = os.path.join(ROOT, "lineage")


def load_env(root):
    p = os.path.join(root, "config.env")
    if os.path.exists(p):
        with open(p, encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())


def best_dir():
    return os.path.join(LINEAGE, "best")


def read_genome(d):
    with open(os.path.join(d, "genome.json"), encoding="utf-8") as f:
        return json.load(f)


def load_state(d):
    facts, drives = {}, {}
    p = os.path.join(d, "state", "memory.json")
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                facts = json.load(f).get("facts", {})
        except Exception:
            facts = {}
    p = os.path.join(d, "state", "drives.json")
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                drives = json.load(f)
        except Exception:
            drives = {}
    return {"facts": facts, "drives": drives}


def current_gen_number():
    n = -1
    if os.path.isdir(LINEAGE):
        for name in os.listdir(LINEAGE):
            if name.startswith("gen_"):
                try:
                    n = max(n, int(name.split("_")[1]))
                except (IndexError, ValueError):
                    pass
    return n


def append_lineage(entry):
    os.makedirs(LINEAGE, exist_ok=True)
    with open(os.path.join(LINEAGE, "lineage.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _save_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def init_genesis():
    b = best_dir()
    if os.path.exists(os.path.join(b, "genome.json")):
        return
    os.makedirs(os.path.join(b, "state"), exist_ok=True)
    shutil.copy2(os.path.join(ROOT, "genome", "genome.json"),
                 os.path.join(b, "genome.json"))
    for name in ("memory.json", "drives.json"):
        src = os.path.join(ROOT, "state", name)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(b, "state", name))
    print("[genesis] gen 0 semeado em lineage/best/")


def make_client(genome):
    return ChatClient(
        base_url=os.environ.get("OPENROUTER_BASE", "https://openrouter.ai/api/v1"),
        model=genome["routing"]["active_model"],
        api_key=os.environ.get("OPENROUTER_API_KEY", ""))


def cycle(args, limits, rng):
    reason = limits.check(ROOT)
    if reason:
        print("[guard] PARANDO o ciclo: " + reason)
        return False, None
    dry = bool(args.dry) or os.environ.get("AURA_DRY") == "1"
    mode = "dry" if dry else "live"

    best = best_dir()
    champ_genome = read_genome(best)
    champ_state = load_state(best)
    score_path = os.path.join(best, "score.json")

    champ_score = None
    if os.path.exists(score_path):
        with open(score_path, encoding="utf-8") as f:
            c = json.load(f)
        if c.get("mode") == mode:
            champ_score = c["score"]
    if champ_score is None:
        r = evaluator.run(champ_genome, client=make_client(champ_genome),
                          state=champ_state, dry=dry,
                          price_per_1m=limits.price(champ_genome["routing"]["active_model"]))
        _save_json(os.path.join(best, "result.json"), r)
        if not r["dry"]:
            limits.add_spend(r["cost_usd"])
        champ_score = r["score"]
        _save_json(score_path, {"score": champ_score,
                                "gen": max(0, current_gen_number()), "mode": mode})
        print("[medir campeao] score %.4f (%s)" % (champ_score, mode))

    gen_n = current_gen_number() + 1
    mutated_genome, mutated_state, rec = mutator.mutate(champ_genome, champ_state, rng)
    child_dir = reproducer.spawn(ROOT, gen_n, mutated_genome, mutated_state, best, rec)

    cr = evaluator.run(mutated_genome, client=make_client(mutated_genome),
                       state=mutated_state, dry=dry,
                       price_per_1m=limits.price(mutated_genome["routing"]["active_model"]))
    _save_json(os.path.join(child_dir, "result.json"), cr)
    if not cr["dry"]:
        limits.add_spend(cr["cost_usd"])

    eps = float(limits.cfg.get("epsilon_survival", 0.02))
    verdict = "survive" if cr["score"] >= champ_score - eps else "death"
    if verdict == "survive":
        shutil.copy2(os.path.join(child_dir, "genome.json"), os.path.join(best, "genome.json"))
        shutil.copy2(os.path.join(child_dir, "result.json"), os.path.join(best, "result.json"))
        for name in ("memory.json", "drives.json"):
            src = os.path.join(child_dir, "state", name)
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(best, "state", name))
        _save_json(score_path, {"score": cr["score"], "gen": gen_n, "mode": mode})

    entry = {"gen": gen_n, "ts": time.time(), "parent": gen_n - 1,
             "mutation": rec, "parent_score": champ_score, "child_score": cr["score"],
             "verdict": verdict, "cost_usd": cr["cost_usd"], "mode": mode}
    append_lineage(entry)
    print("[gen %03d] %-14s pai %.4f -> filho %.4f | %s"
          % (gen_n, rec.get("op", "?"), champ_score, cr["score"], verdict))
    return True, gen_n


def summary_selftest():
    p = os.path.join(LINEAGE, "lineage.jsonl")
    if not os.path.exists(p):
        print("ERRO: lineage nao gerado.")
        return 1
    with open(p, encoding="utf-8") as f:
        rows = [json.loads(l) for l in f if l.strip()]
    surv = sum(1 for r in rows if r["verdict"] == "survive")
    deaths = len(rows) - surv
    best_row = max(rows, key=lambda r: r["child_score"])
    with open(os.path.join(best_dir(), "score.json"), encoding="utf-8") as f:
        champ = json.load(f)
    print("=== resumo: %d geracoes | %d sobreviveram | %d morreram ==="
          % (len(rows), surv, deaths))
    print("campeao: gen %s score %.4f" % (champ.get("gen"), champ.get("score", -1)))
    print("melhor filho observado: gen %d score %.4f"
          % (best_row["gen"], best_row["child_score"]))
    print("selftest OK â€” o ciclo N+1 funciona (medir -> mutar -> reproduzir -> podar -> registrar).")
    return 0


def status():
    lim = Limits(ROOT)
    s = lim.spend()
    print("[guard] gasto este mes: USD %.4f / cap %.2f"
          % (float(s.get("spend_usd", 0.0)), float(lim.cfg["monthly_spend_usd_cap"])))
    sp = os.path.join(best_dir(), "score.json")
    if os.path.exists(sp):
        with open(sp, encoding="utf-8") as f:
            c = json.load(f)
        print("[campeao] gen %s score %.4f" % (c.get("gen"), c.get("score", -1)))
    p = os.path.join(LINEAGE, "lineage.jsonl")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            rows = [json.loads(l) for l in f if l.strip()]
        print("[lineage] %d geracoes registradas; ultimas:" % len(rows))
        for r in rows[-8:]:
            print("  gen %03d %-14s filho %.4f %s"
                  % (r["gen"], r["mutation"].get("op", "?"), r["child_score"], r["verdict"]))
    else:
        print("[lineage] vazio (genesis ainda nao rodou).")


def main(argv=None):
    load_env(ROOT)
    ap = argparse.ArgumentParser(description="Aura Infinite â€” ciclo N+1")
    ap.add_argument("--cycles", type=int, default=1)
    ap.add_argument("--sleep", type=float, default=None)
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--list-models", action="store_true")
    ap.add_argument("--sporulate-every", type=int, default=0,
                    help="esporula (build+publish) a cada N geracoes; 0=desligado")
    args = ap.parse_args(argv)

    if args.list_models:
        print("Modelos OpenRouter mais baratos (USD/1M prompt tokens):")
        for mid, pin in list_models(limit=25):
            print("  %-52s %s" % (mid, ("%.4f" % pin) if pin is not None else "n/d"))
        return 0
    if args.status:
        status()
        return 0
    if args.reset:
        if args.yes or input("Isto apaga lineage/ inteiro. Digite RESET: ").strip().upper() == "RESET":
            shutil.rmtree(LINEAGE, ignore_errors=True)
            print("[reset] lineage apagado.")
        return 0

    if args.selftest:
        args.dry = True
        args.cycles = 12
        args.sleep = 0
        print("=== AURA INFINITE â€” selftest (dry: paisagem sintetica, zero API) ===")
        rng = random.Random(7)
    else:
        rng = random.Random()

    limits = Limits(ROOT)
    init_genesis()
    sleep_s = args.sleep if args.sleep is not None else float(limits.cfg.get("cycle_sleep_s", 300))
    ok = True
    dry_mode = bool(args.dry) or os.environ.get("AURA_DRY") == "1"
    spor_every = int(getattr(args, "sporulate_every", 0) or 0)
    for i in range(args.cycles):
        ok, gen_n = cycle(args, limits, rng)
        if not ok:
            break
        if spor_every and not dry_mode and gen_n and gen_n % spor_every == 0:
            try:
                from seeds import build_seed, publish_github
                out_dir, _zp = build_seed.build()
                res = publish_github.publish(out_dir)
                print("[esporulacao] semente publicada (gen %d): %s"
                      % (gen_n, res["html_url"]))
            except Exception as e:
                print("[esporulacao] falhou (o ciclo continua): %s" % e)
        if i < args.cycles - 1 and sleep_s > 0:
            time.sleep(sleep_s)
    if args.selftest:
        return summary_selftest()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
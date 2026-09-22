# -*- coding: utf-8 -*-
"""Limites e disjuntor: teto de gasto, teto de disco, teto de geracoes, STOP manual."""
from __future__ import annotations

import json
import os
import time


class Limits:
    def __init__(self, root):
        self.root = root
        self.path = os.path.join(root, "guard", "limits.json")
        self.spend_path = os.path.join(root, "guard", "spend.json")
        self.stop_path = os.path.join(root, "guard", "STOP")
        with open(self.path, encoding="utf-8") as f:
            self.cfg = json.load(f)

    def stop_requested(self):
        return os.path.exists(self.stop_path)

    def spend(self):
        if os.path.exists(self.spend_path):
            with open(self.spend_path, encoding="utf-8") as f:
                return json.load(f)
        return {"month": "", "spend_usd": 0.0}

    def add_spend(self, cost_usd):
        m = time.strftime("%Y-%m")
        s = self.spend()
        if s.get("month") != m:
            s = {"month": m, "spend_usd": 0.0}
        s["spend_usd"] = round(float(s.get("spend_usd", 0.0)) + float(cost_usd), 6)
        with open(self.spend_path, "w", encoding="utf-8") as f:
            json.dump(s, f, indent=2)
        return s

    def check(self, root=None):
        """Retorna None se tudo ok, ou a razao de parada."""
        root = root or self.root
        if self.stop_requested():
            return "STOP manual (guard/STOP existe)"
        s = self.spend()
        if float(s.get("spend_usd", 0.0)) >= float(self.cfg["monthly_spend_usd_cap"]):
            return "teto de gasto mensal atingido (USD %.2f)" % float(s["spend_usd"])
        total = 0
        lineage = os.path.join(root, "lineage")
        for dp, _dns, files in os.walk(lineage):
            for fn in files:
                try:
                    total += os.path.getsize(os.path.join(dp, fn))
                except OSError:
                    pass
        if total > float(self.cfg["max_lineage_mb"]) * 1024 * 1024:
            return "teto de disco do lineage atingido (%d MB)" % (total // (1024 * 1024))
        lp = os.path.join(lineage, "lineage.jsonl")
        if os.path.exists(lp):
            with open(lp, encoding="utf-8") as f:
                n = sum(1 for _ in f)
            if n >= int(self.cfg.get("max_cycles_total", 100000)):
                return "teto total de geracoes atingido (%d)" % n
        return None

    def price(self, model):
        p = self.cfg.get("blended_price_per_1m_usd", {})
        return float(p.get(model, p.get("default", 0.6)))
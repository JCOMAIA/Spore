# -*- coding: utf-8 -*-
"""Watchdog standalone (cron-friendly): impoe os tetos do guard/limits.json.
O loop principal tambem se auto-verifica a cada ciclo; isto e a segunda linha."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from guard.limits import Limits  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    lim = Limits(ROOT)
    reason = lim.check(ROOT)
    if reason:
        with open(lim.stop_path, "w", encoding="utf-8") as f:
            f.write(reason)
        print("[watchdog] STOP gravado:", reason)
        return 1
    print("[watchdog] ok â€” gasto USD %.4f este mes; sem STOP."
          % float(lim.spend().get("spend_usd", 0.0)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
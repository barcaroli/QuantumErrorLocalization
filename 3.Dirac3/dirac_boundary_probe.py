"""
Dirac-3 boundary probe (follow-up to dirac_scaling_probe.py).

The scaling probe found that, for a free-tier account, the practical
ceiling is a HARD API limit of 100 variables for degree-2 problems --
not a time/budget limit (cost stayed flat at 1-2s per job from n=10 to
n=80, using only 5 of 453 available seconds).

This script stays AT that ceiling (n=100, the maximum allowed) and
instead varies the other three knobs that could plausibly affect job
cost, one at a time from a baseline, to see which of them actually
matters:
  - density: sparse (m=150, same ratio as the scaling probe) vs dense
    (m=4950, a complete graph on 100 variables)
  - num_samples: 1 (baseline) vs 20
  - relaxation_schedule: 1 (baseline) vs 10

Same safety-checked pattern as dirac_scaling_probe.py: balance is
checked before every job, and the script stops rather than risk
overspending.

Usage:
    python dirac_boundary_probe.py
"""

import argparse
import csv
import time

from dirac_scaling_probe import (
    random_qubo_polynomial, run_one_probe, get_balance,
)
from dirac_solver import ensure_env_from_config

N = 100  # the free-tier ceiling found by dirac_scaling_probe.py

CONFIGS = [
    {"label": "sparse, 1 sample, schedule=4 (max valid)",
     "m": 150, "num_samples": 1, "relaxation_schedule": 4},
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--safety-margin-seconds", type=float, default=60.0)
    parser.add_argument("--safety-factor", type=float, default=3.0)
    parser.add_argument("--out", default="dirac_boundary_probe_2.csv")
    args = parser.parse_args()

    ensure_env_from_config()
    from qci_client import QciClient
    client = QciClient()

    start_balance = get_balance(client)
    print(f"Starting Dirac allocation balance: {start_balance:.1f} s\n")

    rows = []
    max_job_cost_seen = 54.0  # informed by the first boundary-probe run (20 samples: 54s)

    for cfg in CONFIGS:
        required = args.safety_factor * max_job_cost_seen
        current_balance = get_balance(client)
        print(f"{cfg['label']:45s}  balance={current_balance:.1f}s  "
              f"need>={required:.1f}s  ", end="")

        if current_balance - args.safety_margin_seconds < required:
            print("STOP (insufficient safety margin).")
            rows.append({**cfg, "attempted": False, "cost_s": None})
            break

        print("attempting...")
        balance_before = current_balance
        try:
            elapsed_wall, status = run_one_probe(
                client, N, cfg["m"], seed=42,
                num_samples=cfg["num_samples"],
                relaxation_schedule=cfg["relaxation_schedule"],
            )
        except Exception as e:
            print(f"  ERROR: {e}")
            rows.append({**cfg, "attempted": True, "cost_s": None,
                         "status": f"error: {e}"})
            break

        balance_after = get_balance(client)
        real_cost = balance_before - balance_after
        max_job_cost_seen = max(max_job_cost_seen, real_cost)

        print(f"  done: status={status}  real_cost={real_cost:.2f}s  "
              f"wall_clock={elapsed_wall:.2f}s  new_balance={balance_after:.1f}s")
        rows.append({**cfg, "attempted": True, "cost_s": round(real_cost, 2),
                      "wall_clock_s": round(elapsed_wall, 2), "status": status})

    with open(args.out, "w", newline="") as f:
        fieldnames = sorted({k for r in rows for k in r})
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    final_balance = get_balance(client)
    print(f"\nFinished. Balance: {start_balance:.1f}s -> {final_balance:.1f}s "
          f"(spent {start_balance - final_balance:.1f}s). Log written to {args.out}")


if __name__ == "__main__":
    main()

"""
Adaptive Dirac-3 scaling probe.

Goal: find out how far Dirac-3 can practically scale (in number of
binary variables, degree-2 QUBO -- same structural shape as the Tunisia
Fellegi-Holt problem), while staying safely within a real, LIMITED time
allocation budget (e.g. a 10-minute free-tier trial).

Why adaptive, not a fixed list of sizes
------------------------------------------
We have exactly one real data point (from the Tunisia case study run):
~3-5 seconds per job at <=6 variables. We do NOT know how run time
scales with problem size on Dirac-3 -- it could stay roughly flat
(if network/preprocessing overhead dominates) or grow noticeably (if
photonic readout/iteration time scales with n). Committing to a fixed
list of sizes in advance risks either wasting the whole budget on a
handful of large jobs, or being overly conservative and never finding
the real ceiling.

Instead, this script:
  1. Tries increasing sizes on a log-ish schedule (10, 20, 40, 80, 160,
     320, 640 -- degree-2, moderate density m=1.5n, matching the
     "sparse" density already used in the IBM/D-Wave synthetic
     experiments for comparability).
  2. Before EVERY job, checks the REAL remaining allocation balance via
     client.get_allocations() and only proceeds if there is enough
     margin left (a safety factor over the largest job cost observed
     so far, or a conservative default guess before any data exists).
  3. Uses minimal settings per job (num_samples=1, relaxation_schedule=1)
     to spend as little as possible while still getting one solve --
     this explores SIZE, not solution quality.
  4. Logs actual consumed time (balance before/after) for every
     attempted size to a CSV, so even a partial run leaves real,
     reusable scaling data.
  5. Stops immediately, without spending anything further, the moment
     the safety check fails -- leaving unused budget on the table is
     the intended, safe failure mode.

Requires: qci-client (real credentials -- see dirac_save_account.py)
Usage:    python dirac_scaling_probe.py [--budget-seconds 600]
                                         [--safety-margin-seconds 60]
                                         [--safety-factor 3]
"""

import argparse
import csv
import random
import time

import numpy as np

from dirac_solver import ensure_env_from_config, polynomial_to_qci_file_data
import ibm_qaoa_solver as solver


CANDIDATE_SIZES = [10, 20, 40, 80, 160, 320, 640]
DENSITY_FACTOR = 1.5  # m = 1.5*n, matching the "sparse" synthetic density
                        # already used in the IBM/D-Wave scaling experiments


def random_qubo_polynomial(n, m, seed):
    """Same structural shape as the Fellegi-Holt hitting-set QUBO:
    linear terms (per-variable cost) + quadratic penalty terms on m
    random pairs. Returns (poly, variables) in the same {frozenset: coeff}
    format used everywhere else in this project."""
    rng = random.Random(seed)
    variables = [f"x{i}" for i in range(n)]
    cost = {v: rng.randint(1, 5) for v in variables}
    pairs = set()
    attempts = 0
    while len(pairs) < m and attempts < m * 20:
        i, j = rng.sample(range(n), 2)
        pairs.add((min(i, j), max(i, j)))
        attempts += 1
    rule_groups = [[variables[i], variables[j]] for i, j in pairs]
    penalty = sum(cost.values()) + 3
    poly = solver.build_polynomial(variables, cost, rule_groups, penalty)
    return poly, variables


def run_one_probe(client, n, m, seed, num_samples=1, relaxation_schedule=1):
    """Submit exactly one job at size n. Returns (elapsed_wall_s,
    job_status) -- does NOT read allocation balance itself (the caller
    does, before and after, for the authoritative cost figure)."""
    from qci_client import JobStatus

    poly, variables = random_qubo_polynomial(n, m, seed)
    data, max_degree = polynomial_to_qci_file_data(poly, variables)
    min_degree = min(len(mono) for mono in poly if len(mono) > 0)

    poly_file = {
        "file_name": f"scaling_probe_n{n}",
        "file_config": {
            "polynomial": {
                "data": data,
                "num_variables": n,
                "min_degree": min_degree,
                "max_degree": max_degree,
            }
        },
    }
    file_response = client.upload_file(file=poly_file)
    polynomial_file_id = file_response["file_id"]

    job_body = client.build_job_body(
        job_type="sample-hamiltonian-integer",
        job_params={
            "device_type": "dirac-3",
            "num_samples": num_samples,
            "num_levels": [2] * n,      # binary
            "relaxation_schedule": relaxation_schedule,
        },
        polynomial_file_id=polynomial_file_id,
        job_name=f"scaling-probe-n{n}",
    )

    t0 = time.time()
    job_response = client.process_job(job_body=job_body)
    elapsed = time.time() - t0
    status = job_response.get("status", "UNKNOWN")
    return elapsed, status


def get_balance(client):
    return client.get_allocations()["allocations"]["dirac"]["seconds"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--budget-seconds", type=float, default=420.0,
                         help="total real allocation budget available for this "
                              "run (default: 420s, leaving margin under the "
                              "~453s currently on the account)")
    parser.add_argument("--safety-margin-seconds", type=float, default=60.0,
                         help="always keep at least this much balance untouched (default: 60s)")
    parser.add_argument("--safety-factor", type=float, default=3.0,
                         help="require remaining budget >= safety_factor * "
                              "(largest cost observed so far, or a 15s default "
                              "guess before any data exists) before attempting "
                              "the next size (default: 3x)")
    parser.add_argument("--out", default="dirac_scaling_probe.csv")
    args = parser.parse_args()

    ensure_env_from_config()
    from qci_client import QciClient
    client = QciClient()

    start_balance = get_balance(client)
    print(f"Starting Dirac allocation balance: {start_balance:.1f} s")
    print(f"Configured budget for this run: {args.budget_seconds:.0f} s "
          f"(safety margin: {args.safety_margin_seconds:.0f} s, "
          f"safety factor: {args.safety_factor}x)\n")

    rows = []
    max_job_cost_seen = None
    default_guess = 15.0  # conservative guess before any real data point exists
    spent_this_run = 0.0

    for n in CANDIDATE_SIZES:
        m = max(1, round(DENSITY_FACTOR * n))

        estimate = max_job_cost_seen if max_job_cost_seen is not None else default_guess
        required = args.safety_factor * estimate

        current_balance = get_balance(client)
        remaining_for_this_run = args.budget_seconds - spent_this_run
        available = min(current_balance - args.safety_margin_seconds,
                         remaining_for_this_run)

        print(f"n={n:4d}  balance={current_balance:.1f}s  "
              f"budget_left_this_run={remaining_for_this_run:.1f}s  "
              f"need>={required:.1f}s  ", end="")

        if available < required:
            print("STOP (insufficient safety margin) -- not attempting this size.")
            rows.append({"n": n, "attempted": False, "cost_s": None,
                         "status": "skipped_safety_stop"})
            break

        print("attempting...")
        balance_before = current_balance
        try:
            elapsed_wall, status = run_one_probe(client, n, m, seed=42)
        except Exception as e:
            print(f"  ERROR: {e}")
            rows.append({"n": n, "attempted": True, "cost_s": None,
                         "status": f"error: {e}"})
            break

        balance_after = get_balance(client)
        real_cost = balance_before - balance_after
        spent_this_run += real_cost
        max_job_cost_seen = max(max_job_cost_seen or 0, real_cost)

        print(f"  done: status={status}  real_cost={real_cost:.2f}s  "
              f"wall_clock={elapsed_wall:.2f}s  new_balance={balance_after:.1f}s")
        rows.append({"n": n, "attempted": True, "cost_s": round(real_cost, 2),
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

"""
Dirac-3 (QCi Entropy Quantum Computing) solver for the Fellegi-Holt
error-localization benchmark. Tunisia census, education-chain subset
(ENROLL, EDULEV, DEGREE, DEGLEV, DEGCTY, FIELD).

Pipeline
--------
1. Load the problem definition and a specific test record from
   testdata.csv (shared with ibm_qaoa_solver.py / dwave_solver.py).
2. Compute the Fellegi-Holt edit closure and evaluate which edits fire
   on the record (identical logic to the other two solvers -- see
   generate_implied_edits.py).
3. Build the penalized pseudo-Boolean cost function as a SYMMETRIC QUBO
   matrix (numpy array) -- Dirac-3's native "sample-qubo" job format.
   No quadratization needed for this dataset (verified: all closure
   edits stay pairwise); Dirac-3 could in principle also accept
   higher-degree polynomials directly (up to degree 5, via a
   "sample-hamiltonian" job) if a future rule set required it.
4. Solve with one of two modes:
     - "cloud" : submit to QCi's real Dirac-3 device over the network
                 (requires an account -- see dirac_save_account.py).
     - "local-test" (default): NOT Dirac-3. Solves the identical QUBO
       with a classical simulated-annealing reference solver, purely
       to validate the problem construction before spending real QCi
       time allocation. Unlike IBM (Aer) and D-Wave (dwave.samplers),
       QCi provides no official local/offline simulator for Dirac-3,
       so this fallback is our own, clearly labelled as such in every
       output line.
5. Cross-check against brute-force enumeration.

Requires: qci-client (cloud mode), dwave-ocean-sdk (local-test mode
           only, reused as a classical stand-in solver), numpy

Usage
-----
    python dirac_solver.py                        # local-test (no account needed)
    python dirac_solver.py --record R4             # local-test, record R4
    python dirac_solver.py --mode cloud            # real Dirac-3, record R6
    python dirac_solver.py --mode cloud --num-samples 20

Authentication for --mode cloud
---------------------------------
Run dirac_save_account.py ONCE beforehand, or set the QCI_TOKEN (and
optionally QCI_API_URL) environment variables for the current terminal
session. This script never asks for or reads the token directly.
"""

import argparse
import itertools
import os
import json
from pathlib import Path

import numpy as np

import ibm_qaoa_solver as solver  # reuse: CSV loaders, closure, violated_rules

CONFIG_PATH = Path.home() / ".qci" / "config.json"
DEFAULT_URL = "https://api.qci-prod.com"


# ---------------------------------------------------------------------
# 1. Authentication (QCi has no built-in persistent config file, unlike
#    IBM/D-Wave -- this mirrors the UX of ibm_save_account.py /
#    dwave_save_account.py with our own small JSON file).
# ---------------------------------------------------------------------

def ensure_env_from_config():
    if os.environ.get("QCI_TOKEN"):
        return
    if CONFIG_PATH.exists():
        cfg = json.loads(CONFIG_PATH.read_text())
        os.environ.setdefault("QCI_TOKEN", cfg.get("token", ""))
        os.environ.setdefault("QCI_API_URL", cfg.get("url", DEFAULT_URL))


# ---------------------------------------------------------------------
# 2. Pseudo-Boolean polynomial -> symmetric QUBO matrix (Dirac-3's
#    native "sample-qubo" format: minimize x^T Q x over x in {0,1}^n)
# ---------------------------------------------------------------------

def polynomial_to_qci_file_data(poly, variables):
    """Convert our x-basis pseudo-Boolean polynomial into QCi's
    'polynomial' file format.

    Two conventions, confirmed against QCi's own multibody-formulation
    example (an initial guess without them produced a 400 Bad Request):
      1. Variables are indexed FROM 1, not from 0.
      2. Every monomial's 'idx' list must have the SAME length, equal
         to max_degree -- lower-degree terms are left-padded with 0
         entries (index 0 is reserved as a "no variable here" filler,
         not an actual variable), e.g. a linear term on variable i in a
         degree-2 problem is idx=[0, i], not idx=[i].
    """
    max_degree = max((len(m) for m in poly if len(m) > 0), default=0)
    data = []
    for monomial, coeff in poly.items():
        if len(monomial) == 0:
            continue  # constant offset, irrelevant for argmin, dropped
        idx_1based = sorted(i + 1 for i in monomial)
        padded = [0] * (max_degree - len(idx_1based)) + idx_1based
        data.append({"idx": padded, "val": coeff})
    return data, max_degree


def polynomial_to_qubo_matrix(poly, variables):
    """Same polynomial, as a symmetric QUBO matrix -- used only by the
    local-test classical stand-in solver (dimod expects this form)."""
    n = len(variables)
    Q = np.zeros((n, n))
    offset = 0.0
    for monomial, coeff in poly.items():
        if len(monomial) == 0:
            offset += coeff
        elif len(monomial) == 1:
            (i,) = tuple(monomial)
            Q[i, i] += coeff
        elif len(monomial) == 2:
            i, j = tuple(monomial)
            Q[i, j] += coeff / 2
            Q[j, i] += coeff / 2
        else:
            raise ValueError(
                f"This QUBO path requires degree <= 2; got a degree-"
                f"{len(monomial)} term {monomial}. Dirac-3 itself supports "
                f"degree up to 5 natively via a 'sample-hamiltonian' job "
                f"(not implemented here since the Tunisia dataset never "
                f"needs it -- verified all closure edits stay pairwise).")
    return Q, offset


# ---------------------------------------------------------------------
# 3. Solvers
# ---------------------------------------------------------------------

def solve_local_test(poly, variables, num_samples, seed=42):
    """NOT Dirac-3 -- classical simulated annealing on the identical
    problem, used only to validate the problem construction offline.
    Automatically quadratizes (via dimod.make_quadratic) if poly has any
    term of degree > 2 -- dimod's BQM, like D-Wave's own native format,
    is strictly degree-2, unlike Dirac-3's real cloud path which accepts
    the polynomial natively up to degree 5 (see solve_cloud)."""
    import dimod
    from dwave.samplers import SimulatedAnnealingSampler
    from domain_utils import polynomial_to_bqm

    bqm = polynomial_to_bqm(poly, variables)
    sampleset = SimulatedAnnealingSampler().sample(
        bqm, num_reads=num_samples, seed=seed)
    best = sampleset.first.sample
    sample = np.array([best[v] for v in variables])
    return sample, float(sampleset.first.energy)


def solve_cloud(poly, variables, num_samples, device_type="dirac-3",
                 relaxation_schedule=1):
    """Real Dirac-3 over QCi's cloud API. Uses the 'sample-hamiltonian-
    integer' job type (Qudit Hamiltonian Optimization with discrete
    levels), NOT 'sample-hamiltonian' (continuous/normalized qudits) --
    an initial attempt used the continuous version and returned
    meaningless large-magnitude results (energies like -479474), because
    our binary {0,1} variables were left unconstrained over a continuous
    domain. Setting num_levels=2 per variable restricts each qudit to
    exactly two discrete levels (0 and 1), matching our problem."""
    from qci_client import QciClient, JobStatus

    ensure_env_from_config()
    client = QciClient()

    data, max_degree = polynomial_to_qci_file_data(poly, variables)
    min_degree = min(len(m) for m in poly if len(m) > 0)
    poly_file = {
        "file_name": "tunisia_polynomial",
        "file_config": {
            "polynomial": {
                "data": data,
                "num_variables": len(variables),
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
            "device_type": device_type,
            "num_samples": num_samples,
            "num_levels": [2] * len(variables),  # binary: 2 discrete levels each
            "relaxation_schedule": relaxation_schedule,
        },
        polynomial_file_id=polynomial_file_id,
        job_name="tunisia-fellegi-holt",
    )
    job_response = client.process_job(job_body=job_body)
    if job_response["status"] != JobStatus.COMPLETED.value:
        raise RuntimeError(f"Dirac job did not complete: {job_response['status']}")

    solutions = job_response["results"]["solutions"]
    energies = job_response["results"]["energies"]
    best_idx = int(np.argmin(energies))
    # Dirac-3's qudit solver returns continuous-relaxed values; round to
    # the nearest binary value for a 0/1-domain problem like ours.
    return np.array(solutions[best_idx]), float(energies[best_idx])


# ---------------------------------------------------------------------
# 4. Reusable localization routine (mirrors the IBM/D-Wave solvers)
# ---------------------------------------------------------------------

def localize_record(record, all_variables, cost, rules_logic, closure=None,
                     mode="local-test", device_type="dirac-3",
                     num_samples=20, verbose=True):
    if closure is None:
        closure = solver.get_closure(rules_logic, all_variables)
    active = solver.violated_rules(record, rules_logic, all_variables, closure)
    if not active:
        if verbose:
            print(f"Record {record['record_id']}: no rule violated.")
        return None

    rule_groups = [a["variables"] for a in active]
    variables = [v for v in all_variables if any(v in g for g in rule_groups)]
    n = len(variables)
    penalty = sum(cost.values()) + 3

    def C_tot(assignment):
        val = sum(cost[v] * assignment[v] for v in variables)
        for g in rule_groups:
            prod = 1
            for v in g:
                prod *= (1 - assignment[v])
            val += penalty * prod
        return val

    poly = solver.build_polynomial(variables, cost, rule_groups, penalty)

    best_cost = min(
        C_tot(dict(zip(variables, bits)))
        for bits in itertools.product([0, 1], repeat=n)
    )
    best_bits_set = {
        bits for bits in itertools.product([0, 1], repeat=n)
        if C_tot(dict(zip(variables, bits))) == best_cost
    }

    if verbose and mode == "cloud":
        print(f"  Submitting to Dirac-3 (device_type={device_type})...")
    if mode == "cloud":
        sample, _energy = solve_cloud(poly, variables, num_samples, device_type)
    else:
        sample, _energy = solve_local_test(poly, variables, num_samples)

    sampled_bits = tuple(int(round(b)) for b in sample)
    sampled_cost = C_tot(dict(zip(variables, sampled_bits)))
    corrections = [v for v, b in zip(variables, sampled_bits) if b == 1]

    label = "Dirac-3 (cloud)" if mode == "cloud" else "LOCAL TEST, not Dirac-3"
    if verbose:
        print(f"Record {record['record_id']}: violated rules = "
              f"{[a['rule_id'] for a in active]}, "
              f"correction = {corrections} (cost {sampled_cost}, {label})")
        if len(best_bits_set) > 1:
            alt = [[v for v, b in zip(variables, bits) if b == 1]
                   for bits in best_bits_set]
            print(f"  Note: {len(best_bits_set)} equally minimal corrections "
                  f"exist for this record (cost {best_cost}): {alt}")

    return {
        "violated": active,
        "variables": variables,
        "corrections": corrections,
        "cost": sampled_cost,
        "optimal": sampled_bits in best_bits_set,
        "n_tied_optima": len(best_bits_set),
        "mode": mode,
    }


# ---------------------------------------------------------------------
# 5. Command-line entry point
# ---------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", default="R6",
                         help="record_id from testdata.csv (default: R6)")
    parser.add_argument("--mode", choices=["local-test", "cloud"],
                         default="local-test",
                         help="local-test = classical stand-in solver, no "
                              "account needed (default, NOT Dirac-3); "
                              "cloud = real QCi Dirac-3 device")
    parser.add_argument("--device", default="dirac-3",
                         help="QCi device_type for --mode cloud "
                              "(default: dirac-3)")
    parser.add_argument("--num-samples", type=int, default=20)
    args = parser.parse_args()

    if args.mode == "local-test":
        print("NOTE: --mode local-test uses a classical simulated-annealing "
              "stand-in solver, NOT the real Dirac-3 device. Use --mode "
              "cloud (after running dirac_save_account.py once) to run on "
              "actual QCi hardware.\n")

    all_variables, cost = solver.load_variables()
    rules_logic = solver.load_rules_logic()
    record = solver.load_record(args.record)

    print(f"Record {args.record}: "
          f"{ {v: record[v] for v in all_variables} }")

    result = localize_record(record, all_variables, cost, rules_logic,
                              mode=args.mode, device_type=args.device,
                              num_samples=args.num_samples, verbose=False)
    if result is None:
        print(f"\nRecord {args.record} violates no rule -- nothing to localize.")
        return

    print(f"\nViolated rules for record {args.record}:")
    for a in result["violated"]:
        print(f"  {a['rule_id']}: {a['variables']}")

    print(f"\nActive variables ({len(result['variables'])}): {result['variables']}")
    if result["n_tied_optima"] > 1:
        print(f"({result['n_tied_optima']} equally minimal corrections exist "
              f"for this record -- any of them is a valid answer)")
    label = "Dirac-3 (cloud)" if result["mode"] == "cloud" else "LOCAL TEST, not Dirac-3"
    print(f"\nFinal correction ({label}): "
          f"{result['corrections']}, cost = {result['cost']}")
    print(f"Matches brute-force optimum: {result['optimal']}")


if __name__ == "__main__":
    main()

"""
D-Wave quantum annealing solver for the Fellegi-Holt error-localization
benchmark. Tunisia census, education-chain subset (ENROLL, EDULEV,
DEGREE, DEGLEV, DEGCTY, FIELD).

Pipeline
--------
1. Load the problem definition and a specific test record from
   testdata.csv (shared with ibm_qaoa_solver.py -- same variables.csv,
   rules_logic.csv, testdata.csv).
2. Compute the Fellegi-Holt edit closure (explicit + implied edits --
   see generate_implied_edits.py) and evaluate which edits fire on the
   record. Using the closure (not just the 10 explicit REGOLE.txt
   lines) is what makes the minimum hitting-set answer correct --
   verified against LISTAIMP.Example_Tunisia.
3. Build the penalized pseudo-Boolean cost function directly as a QUBO
   dict (D-Wave's native input format -- no Ising conversion needed,
   unlike the IBM/gate-model path).
4. Solve with one of three samplers:
     - "sim"    (default): SimulatedAnnealingSampler, local, no D-Wave
                 account needed. Fast, useful for development.
     - "hybrid": LeapHybridSampler, D-Wave's cloud hybrid solver.
                 Handles larger problems, still counts against your
                 Leap quota but far less than direct QPU access.
     - "qpu":    DWaveSampler + EmbeddingComposite, direct quantum
                 annealing on real D-Wave hardware (e.g. Advantage2).
5. Cross-check against brute-force enumeration.

Unlike QAOA, D-Wave's quantum annealing needs no classical variational
parameter loop: the anneal directly minimizes the QUBO's energy in one
physical operation. There is no COBYLA-style optimization step to run
on a simulator first -- the "sim"/"hybrid"/"qpu" choice is simply which
sampler evaluates the SAME QUBO.

Requires: dwave-ocean-sdk (dimod, dwave-samplers, dwave-system)

Usage
-----
    python dwave_solver.py                       # simulated annealing, record R6
    python dwave_solver.py --record R4            # simulated annealing, record R4
    python dwave_solver.py --sampler hybrid        # D-Wave Leap hybrid solver
    python dwave_solver.py --sampler qpu           # real D-Wave QPU

Authentication for --sampler hybrid / qpu
-------------------------------------------
Run dwave_save_account.py ONCE beforehand (wraps the standard `dwave
config create` wizard), or set the DWAVE_API_TOKEN environment variable
for the current terminal session. This script never asks for or reads
the token directly.
"""

import argparse
import itertools

import dimod

import ibm_qaoa_solver as solver  # reuse: CSV loaders, closure, violated_rules


# ---------------------------------------------------------------------
# 1. Pseudo-Boolean polynomial -> native QUBO dict (D-Wave's own format,
#    no Ising conversion needed -- this is the practical advantage over
#    the gate-model path).
# ---------------------------------------------------------------------

from domain_utils import polynomial_to_qubo, polynomial_to_bqm


# ---------------------------------------------------------------------
# 2. Sampler selection
# ---------------------------------------------------------------------

def get_sampler(kind, backend_name=None, num_reads=200, seed=42):
    if kind == "sim":
        from dwave.samplers import SimulatedAnnealingSampler
        sampler = SimulatedAnnealingSampler()
        return sampler, {"num_reads": num_reads, "seed": seed}
    elif kind == "hybrid":
        from dwave.system import LeapHybridSampler
        sampler = LeapHybridSampler()  # loads credentials automatically
        return sampler, {}
    elif kind == "qpu":
        from dwave.system import DWaveSampler, EmbeddingComposite
        qpu = DWaveSampler(solver=backend_name) if backend_name else DWaveSampler()
        sampler = EmbeddingComposite(qpu)
        return sampler, {"num_reads": num_reads}
    else:
        raise ValueError(f"Unknown sampler kind: {kind}")


# ---------------------------------------------------------------------
# 3. Reusable localization routine (mirrors ibm_qaoa_solver.localize_record)
# ---------------------------------------------------------------------

def localize_record(record, all_variables, cost, rules_logic, closure=None,
                     sampler_kind="sim", backend_name=None, num_reads=200,
                     verbose=True):
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
    bqm = polynomial_to_bqm(poly, variables)

    # brute-force ground truth (with tie-awareness, same as IBM path)
    best_cost = min(
        C_tot(dict(zip(variables, bits)))
        for bits in itertools.product([0, 1], repeat=n)
    )
    best_bits_set = {
        bits for bits in itertools.product([0, 1], repeat=n)
        if C_tot(dict(zip(variables, bits))) == best_cost
    }

    sampler, sampler_kwargs = get_sampler(sampler_kind, backend_name, num_reads)
    if verbose and sampler_kind != "sim":
        print(f"  Submitting to D-Wave ({sampler_kind})...")
    sampleset = sampler.sample(bqm, **sampler_kwargs)
    best_sample = sampleset.first.sample
    sampled_bits = tuple(best_sample[v] for v in variables)
    sampled_cost = C_tot(dict(zip(variables, sampled_bits)))
    corrections = [v for v, b in zip(variables, sampled_bits) if b == 1]

    if verbose:
        print(f"Record {record['record_id']}: violated rules = "
              f"{[a['rule_id'] for a in active]}, "
              f"correction = {corrections} (cost {sampled_cost}, "
              f"sampler={sampler_kind})")
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
        "sampler_kind": sampler_kind,
    }


# ---------------------------------------------------------------------
# 4. Command-line entry point
# ---------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", default="R6",
                         help="record_id from testdata.csv (default: R6)")
    parser.add_argument("--sampler", choices=["sim", "hybrid", "qpu"],
                         default="sim",
                         help="sim = local simulated annealing (default, "
                              "no account needed); hybrid = D-Wave Leap "
                              "hybrid solver; qpu = real D-Wave quantum "
                              "annealer")
    parser.add_argument("--backend", default=None,
                         help="specific QPU solver name (only used with "
                              "--sampler qpu); default: D-Wave's own choice")
    parser.add_argument("--num-reads", type=int, default=200)
    args = parser.parse_args()

    all_variables, cost = solver.load_variables()
    rules_logic = solver.load_rules_logic()
    record = solver.load_record(args.record)

    print(f"Record {args.record}: "
          f"{ {v: record[v] for v in all_variables} }")

    result = localize_record(record, all_variables, cost, rules_logic,
                              sampler_kind=args.sampler,
                              backend_name=args.backend,
                              num_reads=args.num_reads, verbose=False)
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
    print(f"\nFinal correction ({result['sampler_kind']}): "
          f"{result['corrections']}, cost = {result['cost']}")
    print(f"Matches brute-force optimum: {result['optimal']}")


if __name__ == "__main__":
    main()

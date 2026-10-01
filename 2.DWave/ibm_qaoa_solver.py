"""
IBM Quantum (QAOA) solver for the Fellegi-Holt error-localization benchmark.
Tunisia census, education-chain subset (ENROLL, EDULEV, DEGREE, DEGLEV,
DEGCTY, FIELD).

Pipeline
--------
1. Load the problem definition (variables.csv, rules_logic.csv) and a
   specific test record from testdata.csv.
2. Evaluate rules_logic.csv against that record to determine which rules
   are ACTUALLY violated (both directions: "must be blank" and "must not
   be blank") -- only violated rules enter the penalty function.
3. Build the penalized pseudo-Boolean cost function C_tot(x) over the
   fields involved in the violated rules only.
4. Expand C_tot(x) into a general polynomial in x (works for rules of any
   size, not just the pairwise rules used here).
5. Convert the polynomial to an Ising Hamiltonian (SparsePauliOp) via
   x_j = (I - Z_j)/2. No quadratization is needed on IBM hardware even if
   a rule involved 3+ fields; only circuit depth would grow.
6. Run QAOA's classical parameter optimization (COBYLA) ALWAYS on the
   local Aer simulator -- see note below.
7. If --hardware is passed, submit exactly ONE job to a real IBM backend,
   using the parameters already optimized in step 6, to sample the final
   result. Otherwise the final sampling also happens on Aer.
8. Cross-check against brute-force enumeration over the active variables.

Why parameter optimization never runs on real hardware
--------------------------------------------------------
COBYLA (like any classical optimizer driving QAOA) proposes each new set
of angles based on the previous job's result -- it is inherently
sequential, one job per iteration. On the IBM Quantum Open Plan, Session
mode (which would let sequential jobs skip re-queueing) is NOT available
(Premium/Flex only), and Batch mode does not help either, since Batch
requires all jobs to be known in advance, which sequential optimization
cannot provide. Running 50+ sequential iterations in job mode means 50+
separate trips through the queue -- slow and wasteful of the Open Plan's
limited monthly QPU time. Since this problem is small (<=6 qubits) and
the simulator has already been verified to reliably reach the exact
optimum, the practical and scientifically sound approach is: optimize
angles classically on the noiseless simulator, then spend real QPU time
on a single confirmatory run with those angles -- this is also a more
meaningful benchmark question ("does real hardware noise still recover
the right answer given good parameters?") than re-deriving the angles at
great expense on noisy hardware.

Requires: qiskit, qiskit-aer, qiskit-ibm-runtime, scipy, numpy

Usage
-----
    python ibm_qaoa_solver.py                     # simulator only, record R6
    python ibm_qaoa_solver.py --record R4          # simulator only, record R4
    python ibm_qaoa_solver.py --hardware           # simulator optimization +
                                                    # ONE confirmatory job on
                                                    # real IBM hardware, record R6
    python ibm_qaoa_solver.py --hardware --backend ibm_torino

Authentication for --hardware
------------------------------
Run ibm_save_account.py ONCE beforehand to store your IBM Quantum API key
on disk (~/.qiskit/qiskit-ibm.json), or set the QISKIT_IBM_TOKEN
environment variable for the current terminal session. This script never
asks for or reads the token directly -- it only calls
QiskitRuntimeService(), which discovers credentials automatically.

To cancel jobs that are queued or running on IBM's side, use
cancel_jobs.py (stopping this script locally does NOT cancel jobs
already submitted).
"""

import argparse
import csv
import itertools
from collections import defaultdict

import numpy as np
# NOTE: scipy and qiskit are imported LAZILY (inside the functions that
# actually need them), not here at module level. This file is imported
# as a shared utility module by dwave_solver.py and dirac_solver.py
# too, which do not need QAOA/qiskit at all -- a top-level import here
# would force qiskit to be installed even in venv_dwave/venv_dirac,
# which don't (and shouldn't) have it.

# ---------------------------------------------------------------------
# 1. Load problem definition
# ---------------------------------------------------------------------

def load_variables(path="variables.csv"):
    cost = {}
    order = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            order.append(row["name"])
            cost[row["name"]] = int(row["cost"])
    return order, cost


def load_rules_logic(path="rules_logic.csv"):
    """Generalized N-ary rule format: 'variables', 'operators', and
    'conditions' are semicolon-separated, positionally aligned lists,
    supporting any number of variables per rule (not just 2)."""
    rules = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            rules.append({
                "rule_id": row["rule_id"],
                "variables": row["variables"].split(";"),
                "operators": row["operators"].split(";"),
                "conditions": row["conditions"].split(";"),
                "form": row["form"],
                "regole_line": row["regole_line"],
            })
    return rules


def load_all_records(path="testdata.csv"):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def load_record(record_id, path="testdata.csv"):
    for row in load_all_records(path):
        if row["record_id"] == record_id:
            return row
    raise ValueError(f"Record '{record_id}' not found in {path}")


def is_blank(value):
    return value is None or value.strip() == ""


def violated_rules(record, rules_logic, all_variables, closure):
    """Return the list of dicts (rule_id, variables) for every edit that
    fires on this record -- using the FULL Fellegi-Holt closure
    (explicit + implied edits generated by resolution), not just the
    explicit REGOLE.txt lines. This is what makes plain minimum
    hitting-set search (what the QUBO below actually minimizes) agree
    with CONCORD/SCIA's true minimum-change answer -- verified directly
    against LISTAIMP.Example_Tunisia (see generate_implied_edits.py).
    Uses LITERAL integer domains (via domain_utils), not the coarse
    blank/filled symbolic abstraction -- necessary for N-ary rules,
    where a coarser abstraction can silently merge distinct values that
    a rule needs to tell apart (this caused real, found-and-fixed bugs
    earlier in this project). Call get_closure() once per process and
    pass its result in here.
    """
    from generate_implied_edits import edit_fires
    from domain_utils import encode_record_state

    state = encode_record_state(record, all_variables)
    active = []
    for i, e in enumerate(closure["edits"]):
        if edit_fires(e, state):
            active.append({
                "rule_id": closure["labels"][i],
                "regole_line": closure["labels"][i],
                "variables": sorted(e.keys()),
            })
    return active


_CLOSURE_CACHE = {}


def get_closure(rules_logic, all_variables):
    """Compute (and cache) the Fellegi-Holt edit closure once per
    process, from the generalized N-ary rule format (any number of
    variables per rule) using literal integer domains."""
    if "closure" in _CLOSURE_CACHE:
        return _CLOSURE_CACHE["closure"]

    from generate_implied_edits import generate_closure
    from domain_utils import load_domains, variable_full_domain, parse_spec

    domains = load_domains("variables.csv")
    states_by_var = {v: variable_full_domain(v, domains) for v in all_variables}

    explicit = []
    for r in rules_logic:
        edit = {}
        for var, op, spec in zip(r["variables"], r["operators"], r["conditions"]):
            full = variable_full_domain(var, domains)
            named = parse_spec(spec)
            if op == "(":
                edit[var] = frozenset(named & full)
            else:
                edit[var] = frozenset(full - named)
        explicit.append(edit)

    all_edits = generate_closure(explicit, states_by_var, verbose=False)

    # Label explicit edits by their REGOLE.txt line number; implied edits
    # get labels "I1", "I2", ... in generation order.
    labels = [r["regole_line"] for r in rules_logic] + \
             [f"I{i+1}" for i in range(len(all_edits) - len(rules_logic))]

    result = {"edits": all_edits, "labels": labels,
              "domains": domains, "states_by_var": states_by_var}
    _CLOSURE_CACHE["closure"] = result
    return result


# ---------------------------------------------------------------------
# 2. Pseudo-Boolean polynomial -> Ising Hamiltonian (generic, any degree)
# ---------------------------------------------------------------------

def build_polynomial(variables, cost, rule_groups, penalty):
    idx = {v: i for i, v in enumerate(variables)}
    poly = defaultdict(float)
    for v in variables:
        poly[frozenset([idx[v]])] += cost[v]
    for group in rule_groups:
        idxs = [idx[v] for v in group]
        for r in range(len(idxs) + 1):
            for subset in itertools.combinations(idxs, r):
                poly[frozenset(subset)] += penalty * ((-1) ** r)
    return poly


def polynomial_to_ising(poly):
    ising = defaultdict(float)
    for monomial, coeff in poly.items():
        m = list(monomial)
        k = len(m)
        for r in range(k + 1):
            for subset in itertools.combinations(m, r):
                ising[frozenset(subset)] += coeff * ((-1) ** r) / (2 ** k)
    return ising


def ising_to_sparse_pauli_op(ising, n):
    from qiskit.quantum_info import SparsePauliOp
    labels, coeffs = [], []
    for term, coeff in ising.items():
        if len(term) == 0:
            continue
        chars = ["I"] * n
        for i in term:
            chars[n - 1 - i] = "Z"
        labels.append("".join(chars))
        coeffs.append(coeff)
    return SparsePauliOp(labels, coeffs=np.array(coeffs, dtype=complex)).simplify()


# ---------------------------------------------------------------------
# 3. Reusable localization routine (one record in, corrections out)
# ---------------------------------------------------------------------

def localize_record(record, all_variables, cost, rules_logic,
                     reps=3, hardware=False, backend_name=None,
                     sim_shots=4096, hardware_shots=8192, verbose=True,
                     seed=42, closure=None):
    """Run the full QUBO-build + QAOA pipeline for one record (a dict as
    returned by csv.DictReader on testdata.csv). Returns a dict with:
        violated   -- list of active-rule dicts (rule_id, regole_line, variables)
        variables  -- active variable list (qubits used)
        corrections-- QAOA-selected fields to correct
        cost       -- cost of the QAOA solution
        optimal    -- True if the QAOA solution matches brute force
        ran_on_hardware -- whether the final sample came from real hardware
    Returns None if the record violates no rule.
    """
    from scipy.optimize import minimize
    from qiskit.circuit.library import QAOAAnsatz

    if closure is None:
        closure = get_closure(rules_logic, all_variables)
    active = violated_rules(record, rules_logic, all_variables, closure)
    if not active:
        if verbose:
            print(f"Record {record['record_id']}: no rule violated.")
        return None

    rule_groups = [a["variables"] for a in active]
    variables = [v for v in all_variables
                 if any(v in g for g in rule_groups)]
    n = len(variables)
    penalty = sum(cost.values()) + 3

    def C_tot(bits):
        x = dict(zip(variables, bits))
        val = sum(cost[v] * x[v] for v in variables)
        for g in rule_groups:
            prod = 1
            for v in g:
                prod *= (1 - x[v])
            val += penalty * prod
        return val

    poly = build_polynomial(variables, cost, rule_groups, penalty)
    ising = polynomial_to_ising(poly)
    cost_hamiltonian = ising_to_sparse_pauli_op(ising, n)

    # brute force (ground truth, always computed -- trivial at this size)
    # With uniform or near-uniform costs, MULTIPLE bitstrings can share the
    # same minimum cost (genuine ties in Fellegi-Holt minimum-change
    # localization). Collect the full set of optimal solutions, not just
    # one, so that "matches brute force" correctly accepts any of them.
    best_cost = min(C_tot(b) for b in itertools.product([0, 1], repeat=n))
    best_bits_set = {b for b in itertools.product([0, 1], repeat=n)
                      if C_tot(b) == best_cost}

    qaoa_circuit = QAOAAnsatz(cost_operator=cost_hamiltonian, reps=reps)
    qaoa_circuit.measure_all()

    # --- Step A: ALWAYS optimize parameters on the local Aer simulator ---
    from qiskit_aer.primitives import SamplerV2 as AerSampler
    sim_circuit = qaoa_circuit.decompose(reps=6)
    sim_sampler = AerSampler(seed=seed)

    def sim_sample_counts(params, shots):
        bound = sim_circuit.assign_parameters(params)
        result = sim_sampler.run([bound], shots=shots).result()
        return result[0].data.meas.get_counts()

    def objective(params):
        counts = sim_sample_counts(params, sim_shots)
        total, weighted = 0, 0.0
        for bitstring, freq in counts.items():
            bits = tuple(int(bitstring[n - 1 - i]) for i in range(n))
            weighted += C_tot(bits) * freq
            total += freq
        return weighted / total

    rng = np.random.default_rng(seed)
    best_opt_x, best_opt_cost = None, None
    n_restarts = 5
    for restart in range(n_restarts):
        init_params = rng.uniform(0, np.pi, size=qaoa_circuit.num_parameters)
        opt_result = minimize(objective, init_params, method="COBYLA",
                               options={"maxiter": 150})
        # Evaluate the TRUE classical cost of this restart's best sample
        # (not the noisy COBYLA objective value) to pick the winner.
        counts = sim_sample_counts(opt_result.x, sim_shots)
        restart_best = min(C_tot(tuple(int(bs[n - 1 - i]) for i in range(n)))
                            for bs in counts)
        if best_opt_cost is None or restart_best < best_opt_cost:
            best_opt_cost, best_opt_x = restart_best, opt_result.x
    opt_result_x = best_opt_x
    if verbose:
        print(f"  Simulator optimization done over {n_restarts} restarts "
              f"(best sampled cost={best_opt_cost}).")

    # --- Step B: sample the final result, either on Aer or on ONE real job ---
    ran_on_hardware = False
    if hardware:
        from qiskit_ibm_runtime import QiskitRuntimeService
        from qiskit_ibm_runtime import SamplerV2 as RuntimeSampler
        from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager

        service = QiskitRuntimeService()
        backend = (service.backend(backend_name) if backend_name else
                   service.least_busy(operational=True, simulator=False,
                                       min_num_qubits=n))
        if verbose:
            print(f"  Submitting ONE confirmatory job to IBM backend: "
                  f"{backend.name}")
        pm = generate_preset_pass_manager(backend=backend, optimization_level=1)
        run_circuit = pm.run(qaoa_circuit)
        bound = run_circuit.assign_parameters(opt_result_x)
        result = RuntimeSampler(mode=backend).run(
            [bound], shots=hardware_shots).result()
        final_counts = result[0].data.meas.get_counts()
        ran_on_hardware = True
    else:
        final_counts = sim_sample_counts(opt_result_x, max(sim_shots, 8192))

    best_sampled = min(final_counts.items(), key=lambda kv: C_tot(
        tuple(int(kv[0][n - 1 - i]) for i in range(n))))
    sampled_bits = tuple(int(best_sampled[0][n - 1 - i]) for i in range(n))
    sampled_cost = C_tot(sampled_bits)
    corrections = [v for v, b in zip(variables, sampled_bits) if b == 1]

    if verbose:
        print(f"Record {record['record_id']}: violated rules = "
              f"{[a['rule_id'] for a in active]}, "
              f"correction = {corrections} (cost {sampled_cost}, "
              f"{'real hardware' if ran_on_hardware else 'simulator'})")
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
        "ran_on_hardware": ran_on_hardware,
    }


# ---------------------------------------------------------------------
# 4. Command-line entry point (single record, verbose)
# ---------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", default="R6",
                         help="record_id from testdata.csv (default: R6)")
    parser.add_argument("--reps", type=int, default=3, help="QAOA depth p")
    parser.add_argument("--hardware", action="store_true",
                         help="after simulator optimization, submit ONE "
                              "confirmatory job to real IBM Quantum hardware")
    parser.add_argument("--backend", default=None,
                         help="specific IBM backend name; default: least busy")
    parser.add_argument("--sim-shots", type=int, default=4096,
                         help="shots per simulator evaluation during "
                              "COBYLA optimization")
    parser.add_argument("--hardware-shots", type=int, default=8192,
                         help="shots for the single hardware job")
    args = parser.parse_args()

    all_variables, cost = load_variables()
    rules_logic = load_rules_logic()
    record = load_record(args.record)

    print(f"Record {args.record}: "
          f"{ {v: record[v] for v in all_variables} }")

    result = localize_record(record, all_variables, cost, rules_logic,
                              reps=args.reps, hardware=args.hardware,
                              backend_name=args.backend,
                              sim_shots=args.sim_shots,
                              hardware_shots=args.hardware_shots,
                              verbose=False)
    if result is None:
        print(f"\nRecord {args.record} violates no rule -- nothing to localize.")
        return

    print(f"\nViolated rules for record {args.record}:")
    for a in result["violated"]:
        print(f"  {a['rule_id']} (REGOLE line {a['regole_line']}): {a['variables']}")

    print(f"\nActive variables ({len(result['variables'])}): {result['variables']}")
    if result["n_tied_optima"] > 1:
        print(f"({result['n_tied_optima']} equally minimal corrections exist "
              f"for this record -- any of them is a valid answer)")
    print(f"\nFinal correction ({'IBM hardware' if result['ran_on_hardware'] else 'Aer simulator'}): "
          f"{result['corrections']}, cost = {result['cost']}")
    print(f"Matches brute-force optimum: {result['optimal']}")


if __name__ == "__main__":
    main()

"""
Fellegi-Holt implicit edit generation (the "resolution" / edit-generation
algorithm that CONCORD's contreg/genreg step performs internally).

Motivation
----------
check_generalized_localization.py finds the true minimum-change set by
existential search: does SOME value assignment to a candidate field
subset satisfy every edit? That is correct but not directly portable to
a QUBO (which needs a fixed penalty polynomial over "touch/don't touch"
flags, not an existential search over field values).

The classical Fellegi-Holt theorem gives a way around this: generate the
CLOSURE of the edit set under resolution. Two edits that share a
variable v, whose failure-conditions on v jointly cover v's entire
domain, can be "resolved" by eliminating v and combining their
conditions on the other variables into a new (implied) edit. Once the
closure is complete (fixed point -- no more new edits can be generated),
a PLAIN minimum hitting set over the fields appearing in the CURRENTLY
FAILING edits (explicit + implied) is guaranteed to be the true minimum
change set -- no existential search needed. This means the existing
QUBO/QAOA pipeline (which already does plain hitting-set minimization)
becomes correct again, as long as it is fed the closure instead of just
the 10 explicit edits.

Representation
---------------
Each edit is a dict {variable: frozenset(failure_states)} using the same
small symbolic state alphabet as check_generalized_localization.py
(e.g. DEGREE in {"blank", "2", "other"}). An edit "fires" on a record
when, for every variable it mentions, the record's (symbolic) value for
that variable lies in the edit's failure set for that variable.

Usage:
    python generate_implied_edits.py
"""

import csv
import itertools

import ibm_qaoa_solver as solver
from check_generalized_localization import (
    variable_states, encode_state, minimum_change_set,
)


def explicit_edits_as_conditions(rules_logic, all_variables, states_by_var):
    """Convert rules_logic.csv rows into the {var: failure_set} form."""
    edits = []
    for r in rules_logic:
        pv, tv = r["premise_var"], r["target_var"]
        if r["form"] == "blank":
            premise_fail = frozenset([r["premise_val"]])
            target_fail = frozenset(s for s in states_by_var[tv] if s != "blank")
        else:
            premise_fail = frozenset(s for s in states_by_var[pv]
                                       if s != r["premise_val"])
            target_fail = frozenset(["blank"])
        edits.append({pv: premise_fail, tv: target_fail})
    return edits


def try_resolve(e1, e2, states_by_var):
    """Try to resolve e1 and e2 on every variable they share. Returns a
    list of newly generated edits (usually 0 or 1)."""
    shared = set(e1) & set(e2)
    generated = []
    for v in shared:
        full_domain = frozenset(states_by_var[v])
        if e1[v] | e2[v] != full_domain:
            continue  # generating condition not met on this variable
        new_edit = {}
        for w in set(e1) | set(e2):
            if w == v:
                continue
            if w in e1 and w in e2:
                new_edit[w] = e1[w] & e2[w]  # "C1 AND C2": intersection
            elif w in e1:
                new_edit[w] = e1[w]
            else:
                new_edit[w] = e2[w]
        # Simplification: drop any variable whose failure-set is the
        # entire domain (it adds no real constraint); if that leaves any
        # OTHER variable with an empty failure-set, the edit can never
        # fire -- discard it as vacuous.
        simplified = {}
        vacuous = False
        for w, fail in new_edit.items():
            if fail == frozenset(states_by_var[w]):
                continue  # drop: no constraint
            if len(fail) == 0:
                vacuous = True
                break
            simplified[w] = fail
        if vacuous:
            continue
        if len(simplified) < 2:
            # A generated edit must constrain at least two fields to be a
            # genuine cross-field consistency rule. A single-field (or
            # empty) result here means the two input edits were logically
            # contradictory (resolution can derive anything from a
            # contradiction) -- this is a modelling error upstream, not a
            # legitimate implied edit, and must never be silently kept.
            raise RuntimeError(
                f"Degenerate edit generated while resolving on '{v}': "
                f"{simplified or '(empty)'} -- this means edits "
                f"{edit_key(e1)} and {edit_key(e2)} are contradictory. "
                f"Check rules_logic.csv for an inconsistency.")
        generated.append(simplified)
    return generated


def edit_key(edit):
    return tuple(sorted((k, tuple(sorted(v, key=str))) for k, v in edit.items()))


def generate_closure(explicit_edits, states_by_var, verbose=True):
    all_edits = list(explicit_edits)
    seen = {edit_key(e) for e in all_edits}
    frontier = list(all_edits)
    n_rounds = 0
    while frontier:
        n_rounds += 1
        new_this_round = []
        for e1, e2 in itertools.combinations(all_edits, 2):
            for cand in try_resolve(e1, e2, states_by_var):
                k = edit_key(cand)
                if k not in seen:
                    seen.add(k)
                    new_this_round.append(cand)
        if verbose:
            print(f"  Resolution round {n_rounds}: {len(new_this_round)} "
                  f"new edit(s) (total so far: {len(all_edits) + len(new_this_round)})")
        all_edits.extend(new_this_round)
        frontier = new_this_round
        if n_rounds > 20:
            raise RuntimeError("Closure did not converge in 20 rounds -- "
                                "check for a modelling error.")
    return all_edits


def edit_fires(edit, state):
    return all(state[v] in fail for v, fail in edit.items())


def hitting_set_minimum(record_state, edits):
    """Plain minimum hitting set over the fields appearing in currently
    FAILING edits (explicit + implied). No existential value search."""
    failing = [e for e in edits if edit_fires(e, record_state)]
    if not failing:
        return None, []
    fields_per_edit = [set(e.keys()) for e in failing]
    all_fields = sorted(set().union(*fields_per_edit))
    for k in range(1, len(all_fields) + 1):
        solutions = []
        for subset in itertools.combinations(all_fields, k):
            if all(set(subset) & fe for fe in fields_per_edit):
                solutions.append(subset)
        if solutions:
            uniq = sorted({tuple(sorted(s)) for s in solutions})
            return list(uniq[0]), uniq
    raise RuntimeError("No hitting set found even using all fields.")


def main():
    all_variables, cost = solver.load_variables()
    rules_logic = list(csv.DictReader(open("rules_logic.csv")))
    blank_allowed = {}
    with open("variables.csv", newline="") as f:
        for row in csv.DictReader(f):
            blank_allowed[row["name"]] = row["blank_allowed"] == "1"
    states_by_var = {v: variable_states(v, rules_logic, blank_allowed)
                      for v in all_variables}

    explicit = explicit_edits_as_conditions(rules_logic, all_variables, states_by_var)
    print(f"Explicit edits: {len(explicit)}")
    closure = generate_closure(explicit, states_by_var)
    print(f"Closure size (explicit + implied): {len(closure)}\n")

    implied = closure[len(explicit):]
    if implied:
        print("Implied edits generated:")
        for e in implied:
            desc = " AND ".join(f"{v} in {sorted(fail)}" for v, fail in e.items())
            print(f"  {desc}  -> conflict")
        print()

    records = solver.load_all_records()
    print(f"{'record':<8}{'hitting-set (closure)':<40}{'existential (ground truth)':<40}{'match'}")
    for record in records:
        state = {v: encode_state(record[v], v, rules_logic, blank_allowed)
                  for v in all_variables}
        hs_best, hs_ties = hitting_set_minimum(state, closure)
        ex_best, ex_ties = minimum_change_set(record, all_variables, rules_logic, blank_allowed)
        hs_set = set(tuple(sorted(t)) for t in hs_ties) if hs_ties else set()
        ex_set = set(tuple(sorted(t)) for t in ex_ties) if ex_ties else set()
        match = "OK" if hs_set == ex_set else "MISMATCH"
        print(f"{record['record_id']:<8}{str(hs_best):<40}{str(ex_best):<40}{match}")


if __name__ == "__main__":
    main()

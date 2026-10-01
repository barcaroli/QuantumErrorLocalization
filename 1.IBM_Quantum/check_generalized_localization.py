"""
Exact generalized Fellegi-Holt minimum-change search.

The QAOA/QUBO pipeline in ibm_qaoa_solver.py builds its penalty function
only from the edits that are violated by the ORIGINAL record. That is an
approximation: correcting one field can change whether OTHER edits fire
(e.g. filling DEGREE to satisfy edits 8/9/10 can newly violate edit 2,
which requires DEGREE blank when ENROLL=4). The true Fellegi-Holt
guarantee is the minimum set of fields S such that THERE EXISTS some
value assignment to S making the WHOLE record satisfy every edit at
once -- a genuinely different (existential) problem.

This module implements that exact check classically. Since every edit in
rules_logic.csv only ever tests a variable against blank / a single
named value / "not that value", each variable's relevant behaviour is
captured by a small set of symbolic states:
    - "blank"                      (only if the variable allows blank)
    - the specific value used as premise_val for that variable, if any
    - "other"                      (any other filled value)
This keeps the search space tiny (<= 3 states per variable) even though
the real domains are larger.

Usage:
    python check_generalized_localization.py
"""

import csv
import itertools

import ibm_qaoa_solver as solver


def variable_states(var, rules_logic, blank_allowed):
    """Possible symbolic states for a variable, given the rules that
    reference it as a premise (equality-tested against a fixed value).
    A premise_val of "blank" (used when a rule's condition is on the
    variable itself being blank, not on a named value) is treated as
    the existing "blank" state, not as an extra named value."""
    premise_vals = {r["premise_val"] for r in rules_logic
                     if r["premise_var"] == var and r["premise_val"] != "blank"}
    states = []
    if blank_allowed[var]:
        states.append("blank")
    if premise_vals:
        assert len(premise_vals) == 1, (
            f"{var} used with inconsistent premise values: {premise_vals}")
        states.append(next(iter(premise_vals)))
        states.append("other")  # filled, but not equal to premise_val
    else:
        if blank_allowed[var]:
            states.append("filled")
        else:
            states.append("filled")  # var always filled, single generic state
    # dedupe while preserving order
    seen, out = set(), []
    for s in states:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def encode_state(value, var, rules_logic, blank_allowed):
    premise_vals = {r["premise_val"] for r in rules_logic
                     if r["premise_var"] == var}
    if value.strip() == "":
        return "blank"
    if premise_vals and value == next(iter(premise_vals)):
        return next(iter(premise_vals))
    if premise_vals:
        return "other"
    return "filled"


def rule_fires(rule, state):
    premise_state = state[rule["premise_var"]]
    target_state = state[rule["target_var"]]
    if rule["form"] == "blank":
        return premise_state == rule["premise_val"] and target_state != "blank"
    else:
        return premise_state != rule["premise_val"] and target_state == "blank"


def is_consistent(state, rules_logic):
    return not any(rule_fires(r, state) for r in rules_logic)


def minimum_change_set(record, all_variables, rules_logic, blank_allowed):
    """Return (variables_to_change, all_tied_solutions) for the smallest
    k such that some assignment to k variables makes the record fully
    consistent with every edit. Returns (None, []) if the record is
    already consistent (k=0)."""
    orig_state = {v: encode_state(record[v], v, rules_logic, blank_allowed)
                  for v in all_variables}
    states_by_var = {v: variable_states(v, rules_logic, blank_allowed)
                      for v in all_variables}

    if is_consistent(orig_state, rules_logic):
        return None, []

    for k in range(1, len(all_variables) + 1):
        solutions = []
        for subset in itertools.combinations(all_variables, k):
            option_lists = [states_by_var[v] for v in subset]
            for combo in itertools.product(*option_lists):
                trial = dict(orig_state)
                for v, s in zip(subset, combo):
                    trial[v] = s
                if is_consistent(trial, rules_logic):
                    solutions.append(subset)
                    break  # one satisfying assignment is enough for this subset
        if solutions:
            # dedupe subsets (order-independent)
            uniq = sorted({tuple(sorted(s)) for s in solutions})
            return list(uniq[0]), uniq
    raise RuntimeError("No consistent assignment found even changing all "
                        "fields -- check rules_logic.csv for a contradiction "
                        "that no assignment can resolve.")


def main():
    all_variables, cost = solver.load_variables()
    rules_logic = list(csv.DictReader(open("rules_logic.csv")))
    blank_allowed = {}
    with open("variables.csv", newline="") as f:
        for row in csv.DictReader(f):
            blank_allowed[row["name"]] = row["blank_allowed"] == "1"
    records = solver.load_all_records()

    print(f"{'record':<8}{'k':>3}  variables")
    for record in records:
        best, all_ties = minimum_change_set(
            record, all_variables, rules_logic, blank_allowed)
        if best is None:
            print(f"{record['record_id']:<8}{'0':>3}  (already consistent)")
        else:
            tie_note = f"  ({len(all_ties)} tied minimal sets)" if len(all_ties) > 1 else ""
            print(f"{record['record_id']:<8}{len(best):>3}  {best}{tie_note}")
            if len(all_ties) > 1:
                for t in all_ties:
                    print(f"           alt: {list(t)}")


if __name__ == "__main__":
    main()

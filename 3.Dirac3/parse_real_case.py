"""
Extends the Fellegi-Holt closure machinery (generate_implied_edits.py) to
real-world VARDOM/REGOLE files, where premises use value LISTS
("01,98") and numeric RANGES ("02-98"), not just the single named value
+ blank abstraction used for the simplified Tunisia education-chain toy
example.

Key simplification that makes this tractable without new resolution
logic: rather than inventing a coarser symbolic-state alphabet, each
variable's full declared domain (FFFF..TTTT, plus "blank" if allowed)
is used LITERALLY as its state space -- domains here are small enough
(<=98 codes) that no abstraction is needed. Every rule's condition on a
variable becomes a concrete frozenset of the actual codes it refers to.
generate_closure()/try_resolve() from generate_implied_edits.py already
operate generically on {var: frozenset(states)} dicts, so they are
reused UNCHANGED -- only the parsing/loading layer is new.

Usage:
    python parse_real_case.py VARDOM.individuals REGOLE.individuals
"""

import re
import sys
import time

from generate_implied_edits import generate_closure, edit_fires


VARDOM_LINE_RE = re.compile(r"^(.{6})(\d{4})(\d)(\d{4})(\d{4})(B   B   )?$")
REGOLE_TOKEN_RE = re.compile(r"(\w+)\s*([(<])\s*([^)]+)\)")


def parse_regole_line(line):
    """Generic N-ary parser: splits a REGOLE line into as many
    (var, operator, spec) tokens as it contains -- not limited to 2."""
    tokens = REGOLE_TOKEN_RE.findall(line)
    # sanity check: re-join should reproduce the line modulo whitespace
    rebuilt = " ".join(f"{v}{op}{spec})" for v, op, spec in tokens)
    if rebuilt.replace(" ", "") != line.replace(" ", ""):
        return None  # did not fully match -- let caller treat as skipped
    return tokens


def load_vardom(path):
    """Returns {var_name: {"frm": int, "to": int, "blank": bool}}."""
    domains = {}
    with open(path) as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.rstrip("\n")
            if not line.strip():
                continue
            m = VARDOM_LINE_RE.match(line)
            if not m:
                raise ValueError(f"VARDOM line {lineno} did not match expected "
                                  f"format: {line!r}")
            name = m.group(1).strip()
            frm = int(m.group(4))
            to = int(m.group(5))
            blank = m.group(6) is not None
            domains[name] = {"frm": frm, "to": to, "blank": blank}
    return domains


def variable_full_domain(var, vardom):
    d = vardom[var]
    states = set(range(d["frm"], d["to"] + 1))
    if d["blank"]:
        states.add("blank")
    return states


def parse_spec(spec):
    """Parses a comma-separated list of tokens, where each token is
    either a single value ('01') or a range ('03-98'). Handles mixed
    forms like '01,03-98' (seen in real REGOLE files), not just a pure
    list or a pure range."""
    spec = spec.strip()
    values = set()
    for token in spec.split(","):
        token = token.strip()
        if "-" in token:
            frm_s, to_s = token.split("-")
            values.update(range(int(frm_s), int(to_s) + 1))
        else:
            values.add(int(token))
    return values


def parse_regole(path, vardom):
    """Returns a list of explicit edits, each {var: frozenset(failure_states)},
    in the SAME representation generate_implied_edits.py's resolution
    engine already works with. Handles lines with ANY number of
    variable conditions (not just 2)."""
    edits = []
    skipped = []
    with open(path) as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.strip()
            if not line or line.startswith("*"):
                continue
            tokens = parse_regole_line(line)
            if not tokens or len(tokens) < 2:
                skipped.append((lineno, line))
                continue
            for v, _op, _spec in tokens:
                if v not in vardom:
                    raise ValueError(
                        f"REGOLE line {lineno} references undeclared "
                        f"variable {v!r}: {line!r}")

            def failure_set(var, op, spec):
                full = variable_full_domain(var, vardom)
                named = parse_spec(spec)
                if op == "(":
                    return frozenset(named & full)
                else:
                    return frozenset(full - named)

            edit = {v: failure_set(v, op, spec) for v, op, spec in tokens}
            edits.append(edit)
    return edits, skipped


def encode_record_state(record, vardom):
    """record: {var: raw string value, possibly blank}. Returns
    {var: int-or-"blank"} matching the literal-domain representation."""
    state = {}
    for var, d in vardom.items():
        raw = record.get(var, "").strip()
        state[var] = "blank" if raw == "" else int(raw)
    return state


def main():
    if len(sys.argv) != 3:
        print("Usage: python parse_real_case.py VARDOM.individuals REGOLE.individuals")
        sys.exit(1)
    vardom_path, regole_path = sys.argv[1], sys.argv[2]

    vardom = load_vardom(vardom_path)
    print(f"Loaded {len(vardom)} variables from {vardom_path}")

    explicit, skipped = parse_regole(regole_path, vardom)
    print(f"Parsed {len(explicit)} explicit edits from {regole_path}")
    if skipped:
        print(f"WARNING: {len(skipped)} lines did not match the expected "
              f"pattern and were skipped:")
        for lineno, line in skipped:
            print(f"  line {lineno}: {line!r}")

    # degree check
    degrees = {len(e) for e in explicit}
    print(f"Explicit-edit degrees present: {sorted(degrees)}")

    # variables actually referenced
    referenced = set()
    for e in explicit:
        referenced |= set(e.keys())
    print(f"Distinct variables referenced by REGOLE: {len(referenced)} "
          f"(of {len(vardom)} declared)")

    states_by_var = {v: variable_full_domain(v, vardom) for v in vardom}

    print("\nGenerating closure (this is the real, non-extrapolated measurement)...")
    t0 = time.time()
    closure = generate_closure(explicit, states_by_var, verbose=True)
    elapsed = time.time() - t0

    closure_degrees = {len(e) for e in closure}
    closure_vars = set()
    for e in closure:
        closure_vars |= set(e.keys())

    print(f"\n=== RESULTS ===")
    print(f"Explicit edits:            {len(explicit)}")
    print(f"Total closure size:        {len(closure)}")
    print(f"Implied edits generated:   {len(closure) - len(explicit)}")
    print(f"Closure degrees present:   {sorted(closure_degrees)}")
    print(f"Variables touched by closure: {len(closure_vars)} (of {len(vardom)} declared)")
    print(f"Generation time:           {elapsed:.3f} s")


if __name__ == "__main__":
    main()
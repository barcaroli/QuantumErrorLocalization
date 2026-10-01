"""
Shared literal-domain utilities: parsing value specs ("01,03-98" etc.)
and computing a variable's full domain as a concrete set of integer
values (plus "blank" if allowed).

Used by both the production pipeline (ibm_qaoa_solver.py, and via it
dwave_solver.py / dirac_solver.py) and the real-VARDOM/REGOLE parser
(parse_real_case.py) for the 4 real census files -- kept in its own
module specifically to avoid a circular import: parse_real_case.py
already imports ibm_qaoa_solver.py for the CSV loaders, so
ibm_qaoa_solver.py cannot import back from parse_real_case.py.
"""
import csv


def parse_spec(spec):
    """Parses a comma-separated list of tokens, where each token is
    either a single value ('01') or a range ('03-98'). Handles mixed
    forms like '01,03-98'."""
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


def load_domains(path="variables.csv"):
    """{var: {"frm": int, "to": int, "blank": bool}} from variables.csv's
    domain_min / domain_max / blank_allowed columns."""
    domains = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            domains[row["name"]] = {
                "frm": int(row["domain_min"]),
                "to": int(row["domain_max"]),
                "blank": row["blank_allowed"] == "1",
            }
    return domains


def variable_full_domain(var, domains):
    d = domains[var]
    s = set(range(d["frm"], d["to"] + 1))
    if d["blank"]:
        s.add("blank")
    return s


def encode_record_state(record, all_variables):
    """record: {var: raw string value, possibly blank}. Returns
    {var: int-or-"blank"}."""
    state = {}
    for var in all_variables:
        raw = record.get(var, "")
        raw = raw.strip() if raw is not None else ""
        state[var] = "blank" if raw == "" else int(raw)
    return state


def polynomial_to_qubo(poly, variables):
    """poly: {frozenset(variable indices): coeff}, x-basis (0/1), as
    produced by ibm_qaoa_solver.build_polynomial(). Returns (Q, offset)
    where Q is a dict {(var_i, var_j): coeff} keyed by VARIABLE NAMES
    (dimod.BQM.from_qubo accepts arbitrary hashable labels directly).
    Shared by dwave_solver.py and dirac_solver.py's local-test path --
    kept here (not in either solver module) so neither has to import
    from the other."""
    idx_to_var = {i: v for i, v in enumerate(variables)}
    Q = {}
    offset = 0.0
    for monomial, coeff in poly.items():
        if len(monomial) == 0:
            offset += coeff
        elif len(monomial) == 1:
            (i,) = tuple(monomial)
            v = idx_to_var[i]
            Q[(v, v)] = Q.get((v, v), 0.0) + coeff
        elif len(monomial) == 2:
            i, j = tuple(monomial)
            vi, vj = idx_to_var[i], idx_to_var[j]
            Q[(vi, vj)] = Q.get((vi, vj), 0.0) + coeff
        else:
            raise ValueError(
                f"QUBO requires degree <= 2; got a degree-{len(monomial)} "
                f"term {monomial}. Needs quadratization (see "
                f"polynomial_to_bqm below, which handles this "
                f"automatically).")
    return Q, offset


def polynomial_to_bqm(poly, variables, strength=None):
    """Converts poly into a dimod BinaryQuadraticModel, automatically
    quadratizing (via dimod.make_quadratic, D-Wave's own reduction
    utility -- not a hand-rolled Rosenberg substitution) any term of
    degree > 2. dimod's native BQM format is strictly degree-2; this is
    what makes higher-degree closures (e.g. the degree-3 rule in the
    extended Tunisia example) runnable at all on both D-Wave and on
    Dirac-3's local-test stand-in solver (which is itself dimod-based --
    Dirac-3's real cloud path does not need this, it accepts higher
    degree natively). Verified: introduces exactly d-2 auxiliary
    variables per degree-d term, matching the general
    Rosenberg-reduction bound (checked directly against
    dimod.make_quadratic's own output during this project's degree-3/4
    impact testing)."""
    import dimod
    idx_to_var = {i: v for i, v in enumerate(variables)}
    max_degree = max((len(m) for m in poly if len(m) > 0), default=0)

    if max_degree <= 2:
        Q, offset = polynomial_to_qubo(poly, variables)
        return dimod.BinaryQuadraticModel.from_qubo(Q, offset=offset)

    dpoly = {}
    for monomial, coeff in poly.items():
        key = tuple(idx_to_var[i] for i in monomial)  # () for the constant term
        dpoly[key] = dpoly.get(key, 0.0) + coeff

    if strength is None:
        strength = 10 * max(abs(c) for c in dpoly.values())
    return dimod.make_quadratic(dpoly, strength=strength, vartype=dimod.BINARY)

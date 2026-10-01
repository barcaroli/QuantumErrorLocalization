"""
Run the Dirac-3 error-localization pipeline over every record in
testdata.csv and produce the same two summary tables as the IBM/D-Wave
report generators, for direct comparison.

Defaults to --mode local-test (classical stand-in solver, NOT Dirac-3)
so the report structure can be validated without spending QCi time
allocation; pass --mode cloud to run on the real device.

Requires: qci-client (cloud mode), dwave-ocean-sdk (local-test mode)
Usage:    python generate_dirac_report.py [--mode local-test|cloud]
"""

import argparse
from collections import defaultdict, Counter

import dirac_solver as dc
import ibm_qaoa_solver as solver


def run_report(mode="local-test", device_type="dirac-3", num_samples=20):
    all_variables, cost = solver.load_variables()
    rules_logic = solver.load_rules_logic()
    records = solver.load_all_records()
    closure = solver.get_closure(rules_logic, all_variables)

    per_var_times = defaultdict(int)
    per_var_edits = defaultdict(Counter)
    per_record = []
    n_processed = len(records)
    n_with_errors = 0

    for record in records:
        result = dc.localize_record(
            record, all_variables, cost, rules_logic, closure=closure,
            mode=mode, device_type=device_type, num_samples=num_samples,
            verbose=True,
        )
        if result is None:
            continue
        n_with_errors += 1
        per_record.append({
            "record_id": record["record_id"],
            "corrections": result["corrections"],
        })
        for v in result["corrections"]:
            per_var_times[v] += 1
            for a in result["violated"]:
                if v in a["variables"]:
                    per_var_edits[v][a["rule_id"]] += 1

    return (all_variables, per_var_times, per_var_edits, per_record,
            n_processed, n_with_errors)


def format_stats_table(all_variables, per_var_times, per_var_edits,
                        n_with_errors, label):
    lines = []
    lines.append(f"STATISTICS OF IMPUTED VARIABLES WITH VIOLATED EDITS ({label})")
    header = f"{'name':<8}{'times':>7}{'%':>8}  " + "  ".join(
        f"{'edit':>4}{'times':>7}" for _ in range(4))
    lines.append(header)
    for v in all_variables:
        times = per_var_times.get(v, 0)
        if times == 0:
            continue
        pct = 100.0 * times / n_with_errors
        edits = sorted(per_var_edits[v].items(), key=lambda kv: str(kv[0]))
        cells = []
        for i in range(4):
            edit_num, edit_count = edits[i] if i < len(edits) else (0, 0)
            cells.append(f"{edit_num:>4}{edit_count:>7}")
        lines.append(f"{v:<8}{times:>7}{pct:>8.2f}  " + "  ".join(cells))
    lines.append("edit 0 = padding (fewer than 4 distinct edits for this variable)")
    return "\n".join(lines)


def format_listaimp_table(per_record, label):
    lines = []
    lines.append(f"LIST OF IMPUTATIONS PER RECORD ({label})")
    lines.append(f"{'N_ERRATO':<10}{'IMPUTAZIONE':<13}{'N_VARIABILI':<13}VARIABILI")
    for i, r in enumerate(per_record, 1):
        n = len(r["corrections"])
        vars_str = " ".join(r["corrections"])
        lines.append(f"{i:<10}{'R':<13}{n:<13}{vars_str}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["local-test", "cloud"], default="local-test")
    parser.add_argument("--device", default="dirac-3")
    parser.add_argument("--num-samples", type=int, default=20)
    parser.add_argument("--out", default="dirac_statis_report.txt")
    parser.add_argument("--out-listaimp", default="dirac_listaimp_report.txt")
    args = parser.parse_args()

    label = "DIRAC-3 CLOUD" if args.mode == "cloud" else "LOCAL TEST, NOT DIRAC-3"
    if args.mode == "local-test":
        print(f"NOTE: running in {label} mode -- classical stand-in solver, "
              f"not the real device. Use --mode cloud for actual QCi hardware.\n")

    (all_variables, per_var_times, per_var_edits, per_record,
     n_processed, n_with_errors) = run_report(
        mode=args.mode, device_type=args.device, num_samples=args.num_samples)

    stats_report = format_stats_table(all_variables, per_var_times,
                                       per_var_edits, n_with_errors, label)
    listaimp_report = format_listaimp_table(per_record, label)
    header = (f"Processed {n_processed} records, {n_with_errors} needed at "
              f"least one correction (percentages relative to {n_with_errors}). "
              f"Mode: {label}.")

    print(f"\n{header}\n")
    print(stats_report)
    print()
    print(listaimp_report)

    with open(args.out, "w") as f:
        f.write(header + "\n\n" + stats_report + "\n")
    with open(args.out_listaimp, "w") as f:
        f.write(header + "\n\n" + listaimp_report + "\n")

    print(f"\nReports written to {args.out} and {args.out_listaimp}")


if __name__ == "__main__":
    main()

"""Post-run check, pre-registered in pre-registration.md.

Compares raw band-edges.csv values at P=2*pi (x=0.5) and P=6*pi (x=4/3)
against an independent mpmath 60-digit solution of the paper's Eq. (6).
"""
import csv
import json
import math
from pathlib import Path
import sys

import mpmath as mp

mp.mp.dps = 60
PI = mp.pi
TOL_Y = mp.mpf("1e-10")
TOL_X = mp.mpf("1e-12")
TOL_P_REL = mp.mpf("1e-12")

RUN = Path(sys.argv[1])
OUT = Path(sys.argv[2])


def lower_z(n, P):
    """Solve P = z tan((z-(n-1)pi)/2) on ((n-1)pi, n pi) at 60 dps."""
    a = mp.mpf(n - 1) * PI
    lo = mp.mpf("1e-50")
    hi = PI - mp.mpf("1e-50")
    for _ in range(400):
        mid = (lo + hi) / 2
        z = a + mid
        if z * mp.tan(mid / 2) - P < 0:
            lo = mid
        else:
            hi = mid
    t = (lo + hi) / 2
    z = a + t
    f = mp.cos(z) + P * mp.sin(z) / z
    target = mp.mpf((-1) ** (n - 1))
    return z, (z / PI) ** 2, f - target


def main():
    rows = list(csv.DictReader((RUN / "band-edges.csv").open(encoding="utf-8")))
    report = {"run": str(RUN), "tolerance": {"y_abs": str(TOL_Y), "x_abs": str(TOL_X),
                                             "p_rel": str(TOL_P_REL)},
              "targets": [], "all_pass": True}
    for P_num, P in (("2*pi", 2 * PI), ("6*pi", 6 * PI)):
        if P_num == "2*pi":
            x_expected = mp.mpf("0.5")
        else:
            x_expected = 2 - 4 * PI / P
        target_rows = [r for r in rows if abs(mp.mpf(r["x_plot"]) - x_expected) < mp.mpf("1e-12")]
        entry = {"P_label": P_num, "P_expected": mp.nstr(P, 30),
                 "x_expected": mp.nstr(x_expected, 30), "bands": [],
                 "row_count": len(target_rows)}
        if len(target_rows) != 3:
            entry["error"] = f"expected 3 band rows, found {len(target_rows)}"
            report["all_pass"] = False
            report["targets"].append(entry)
            continue
        for r in sorted(target_rows, key=lambda r: int(r["band"])):
            n = int(r["band"])
            z_exp, y_exp, residual = lower_z(n, P)
            y_csv = mp.mpf(r["y_lower"])
            z_csv = mp.mpf(r["beta_a_lower"])
            p_csv = mp.mpf(r["P"])
            y_up = mp.mpf(r["y_upper"])
            dy = y_csv - y_exp
            dz = z_csv - z_exp
            dx = mp.mpf(r["x_plot"]) - x_expected
            dp_rel = abs(p_csv - P) / P
            entry["bands"].append({
                "band": n,
                "x_csv": r["x_plot"],
                "P_csv": r["P"],
                "z_expected": mp.nstr(z_exp, 30),
                "z_csv": mp.nstr(z_csv, 30),
                "dz": mp.nstr(dz, 5),
                "y_expected": mp.nstr(y_exp, 30),
                "y_csv": mp.nstr(y_csv, 30),
                "dy": mp.nstr(dy, 5),
                "abs_dy": mp.nstr(abs(dy), 5),
                "y_upper_csv": mp.nstr(y_up, 10),
                "upper_error": mp.nstr(abs(y_up - mp.mpf(n * n)), 5),
                "dx": mp.nstr(dx, 5),
                "dp_rel": mp.nstr(dp_rel, 5),
                "pass": bool(abs(dy) <= TOL_Y and abs(dx) <= TOL_X and dp_rel <= TOL_P_REL
                             and abs(y_up - mp.mpf(n * n)) <= TOL_Y),
                "f_residual_expected": mp.nstr(residual, 5),
            })
            if not entry["bands"][-1]["pass"]:
                report["all_pass"] = False
        report["targets"].append(entry)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

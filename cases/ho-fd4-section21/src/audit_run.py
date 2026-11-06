"""Read archived arrays, verify hashes, and reconstruct H independently.
Never scans outside the explicitly selected case and its run directory.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
from scipy.sparse import diags

CASE = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--run", type=Path)
    p.add_argument("--write", action="store_true")
    args = p.parse_args()
    out = args.run.resolve() if args.run else CASE/"outputs"/(CASE/"latest_run.txt").read_text().strip()
    if not out.is_relative_to(CASE/"outputs"):
        raise ValueError("Run must belong to this case")
    checks = []
    def record(name, passed, value):
        checks.append(dict(name=name, passed=bool(passed), value=value))
    manifest = json.loads((out/"manifest.json").read_text(encoding="utf8"))
    bad = [r["path"] for r in manifest if hashlib.sha256((out/r["path"]).read_bytes()).hexdigest() != r["sha256"]]
    record("archive_hashes", not bad, bad)
    inputs = json.loads((out/"inputs.json").read_text(encoding="utf8"))
    changed = [r["path"] for r in inputs if hashlib.sha256(Path(r["path"]).read_bytes()).hexdigest() != r["sha256"]]
    record("current_inputs_match", not changed, changed)
    cfg = json.loads((out/"snapshot/config.json").read_text(encoding="utf8"))
    data = np.load(out/"eigenpairs.npz", allow_pickle=False)
    rows = list(csv.DictReader((out/"metrics.csv").open(encoding="utf8")))
    max_residual = max_orth = max_energy_csv = max_wave_csv = max_parity = 0.
    for tag in [k[:-2] for k in data.files if k.endswith("_e")]:
        order = int(tag[1])
        h = float(tag.split("_h")[1])
        x, e, psi, ref = (data[tag+"_"+s] for s in ("x","e","psi","analytic"))
        diag = (1 if order == 2 else 1.25)/h**2+x*x/2
        offsets = [-1, 0, 1] if order == 2 else [-2,-1,0,1,2]
        nearest = (-.5 if order == 2 else -2/3)/h**2
        bands = [nearest*np.ones(len(x)-1), diag, nearest*np.ones(len(x)-1)]
        if order == 4:
            bands = [np.ones(len(x)-2)/(24*h*h)]+bands+[np.ones(len(x)-2)/(24*h*h)]
        H = diags(bands, offsets, format="csr")
        denom = np.max(np.asarray(abs(H).sum(axis=1)))+max(abs(e))
        max_residual = max(max_residual, float(np.max(np.linalg.norm(H@psi-psi*e, axis=0)*np.sqrt(h)/denom)))
        max_orth = max(max_orth, float(np.max(abs(h*psi.T@psi-np.eye(len(e))))))
        max_parity = max(max_parity, float(np.max(np.sqrt(h*np.sum((psi[::-1]-psi*((-1.)**np.arange(len(e))))**2, axis=0)))))
        for row in [r for r in rows if int(r["order"])==order and float(r["h"])==h]:
            n = int(row["n"])
            max_energy_csv = max(max_energy_csv, abs(float(row["energy"])-e[n]))
            max_wave_csv = max(max_wave_csv, abs(float(row["wave_L2"])-np.sqrt(h*np.sum((psi[:,n]-ref[:,n])**2))))
    for name,value,limit in [("saved_eigenpair_residual",max_residual,1e-12),("saved_orthogonality",max_orth,1e-10),
                             ("saved_parity",max_parity,1e-8),("energy_csv",max_energy_csv,1e-14),("wave_csv",max_wave_csv,1e-14)]:
        record(name, value<=limit, float(value))
    table = list(csv.DictReader((out/"table1_comparison.csv").open(encoding="utf8")))
    reference = list(csv.DictReader((out/"snapshot/table1.csv").open(encoding="utf8")))
    matches = sum(f"{data['o'+r['order']+'_h'+r['h']+'_e'][int(r['n'])]:.6f}" == f"{float(reference[int(r['n'])]['order'+r['order']+'_h'+r['h']]):.6f}" for r in table)
    record("saved_table1", matches==40, matches)
    status = json.loads((out/"status.json").read_text(encoding="utf8"))
    record("successful_run", status["exit_code"]==0, status["exit_code"])
    original = json.loads((out/"checks.json").read_text(encoding="utf8"))
    record("original_checks", all(c["passed"] for c in original), len(original))
    result = dict(run=str(out), checks=checks, passed=all(c["passed"] for c in checks),
                  note="Archive integrity and saved-state checks; not another independent physics algorithm.")
    if args.write:
        (out/"archive_audit.json").write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding="utf8")
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    sys.exit(main())

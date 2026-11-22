"""Grade the submitted curve using the already registered five values."""
import csv
import json
from pathlib import Path
import numpy as np

case = Path(__file__).resolve().parents[2]/"cases/vankov2009-fig1"
with (case/"curve.csv").open(encoding="utf8") as stream:
    rows = list(csv.DictReader(stream))
x = np.array([float(r["s"]) for r in rows])
y = np.array([float(r["Ai_s"]) for r in rows])
points = [-3,-2,-1,0,1]
reference = [-0.37881429367765806,0.22740742820168558,0.5355608832923521,0.3550280538878172,0.13529241631288141]
assert np.all(np.diff(x)>0) and x[0]<=min(points) and x[-1]>=max(points)
actual = np.interp(points, x, y)
diff = abs(actual-reference)
print(json.dumps(dict(s=points, reference=reference, csv=actual.tolist(), errors=diff.tolist(),
                      tolerance=0.001, passed=bool(max(diff)<=0.001)), indent=2))
raise SystemExit(int(max(diff)>0.001))


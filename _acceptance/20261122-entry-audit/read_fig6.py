"""Digitize the uppermost solid curve at three labeled ticks. No fit to CSV."""
import json
from pathlib import Path
import sys
import numpy as np
from PIL import Image

image = np.asarray(Image.open(sys.argv[1]).convert("L"))
csv = np.genfromtxt(sys.argv[2], delimiter=",", names=True)
# At 400 dpi: E=0 and E=3 horizontal tick centers, measured at x=1906.
zero, three = 3235.5, 2724.5
scale = (zero-three)/3
points = []
for r, x in ((0.5,2152), (1.,2408), (1.5,2663)):
    ink = np.flatnonzero(image[2720:3235,x] < 128)+2720
    groups = np.split(ink,np.flatnonzero(np.diff(ink)>1)+1)
    y = float(np.mean(groups[0]))
    read = (zero-y)/scale
    value = float(csv["energy_20"][csv["ratio"] == r][0])
    # +/-2 px on line + tick centers, +/-1 px on x with |dE/dr|<=1.
    uncertainty = 2/scale + 1/511
    points.append(dict(r=r,x=x,y=y,read=read,computed=value,residual=read-value,
                       uncertainty=uncertainty,passed=abs(read-value)<=uncertainty))
print(json.dumps(points,indent=2))
sys.exit(int(not all(p["passed"] for p in points)))


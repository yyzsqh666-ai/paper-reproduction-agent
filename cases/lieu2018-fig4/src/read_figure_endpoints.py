"""Limited pixel reading of Fig.4 endpoints, not full curve digitization.
Requires Pillow; source is the preserved 1800-high Poppler render.
"""
from pathlib import Path
import json
import hashlib
from PIL import Image

case=Path(__file__).resolve().parents[1]
path=case/'source/page04.png'
im=Image.open(path).convert('RGB')
assert im.size==(1391,1800), 'Pixel calibration applies only to the preserved rendering'
# Calibrated visually using the y=0 and y=+/-1 tick positions on p.4.
y0=215.5
pixels_per_energy=64.5
rows=[]
for panel,xs in [('real',range(971,974)),('imag',range(1219,1222))]:
    ys=[]
    for x in xs:
        for y in range(125,215):
            r,g,b=im.getpixel((x,y))
            if b>130 and r<100 and g<140:
                ys.append(y)
    assert ys, panel
    ys.sort(); median=ys[len(ys)//2]
    rows.append(dict(panel=panel,x_columns=list(xs),blue_y_min=min(ys),blue_y_max=max(ys),
                     blue_y_median=median,estimated_positive_E=(y0-median)/pixels_per_energy,
                     conservative_absolute_uncertainty=.03))
result=dict(source='source/page04.png',source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            render='pdftoppm -f 4 -l 4 -scale-to 1800 -png -singlefile source/1709.03788v2.pdf source/page04',
            y_zero=y0,pixels_per_energy=pixels_per_energy,
            method='Blue pixels in three columns just inside right frame; positive branch median. Visual tick calibration; +/-0.03 includes finite x offset, thickness and pixel placement. Not author data.',
            readings=rows)
(case/'source/endpoint_readings.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))

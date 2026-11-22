"""Recreate Vankov Fig. 1. Run: python reproduce.py path/to/paper.pdf"""
import argparse
import csv
import hashlib
import json
import math
import platform
import sys
from datetime import datetime, timezone
from decimal import Decimal, localcontext
from pathlib import Path

import numpy as np
import PIL
import pypdf
from PIL import Image, ImageDraw, ImageFont


OUT = Path(__file__).resolve().parent


def airy(s, end=10, step=0.01):
    # t = 1 + iu in (2 pi i)^(-1) integral exp(t^3/3 - s*t) dt.
    u = np.linspace(0, end, round(end / step) + 1)
    weights = np.exp(-u*u)
    weights[[0, -1]] *= 0.5
    phase = (1 - s[:, None]) * u - u**3 / 3
    return (np.cos(phase) @ weights) * (step / math.pi) * np.exp(1/3 - s)


def series(x):
    # y'' = x y; coefficients from the canonical Ai values at zero.
    with localcontext() as ctx:
        ctx.prec = 60
        coeff = [Decimal('0.35502805388781723926006318600418317639797917419918'),
                 Decimal('-0.25881940379280679840518356018920396347909113835493'),
                 Decimal(0)]
        for n in range(3, 301):
            coeff.append(coeff[n-3] / (n*(n-1)))
        total = Decimal(0)
        for c in reversed(coeff):
            total = total * Decimal(str(x)) + c
        return float(total)


def draw(s, values):
    # Scale the original plot geometry uniformly, leaving room for axis names.
    scale = 3
    im = Image.new('RGB', (1080*scale, 672*scale), 'white')
    pen = ImageDraw.Draw(im)
    def xy(x, y):
        return ((543 + 44.1*x)*scale, (348 - 574*y)*scale)
    def line(x1, y1, x2, y2, width=2):
        pen.line([xy(x1,y1), xy(x2,y2)], fill='black', width=width*scale)
    try:
        font = ImageFont.truetype('times.ttf', 22*scale)
    except OSError:
        font = ImageFont.load_default(size=22*scale)
    def label(x,y,txt,anchor):
        pen.text(xy(x,y),txt,font=font,fill='black',anchor=anchor)
    line(-10.6,0,10.6,0)
    line(0,-0.45,0,0.56)
    for x in range(-10,11):
        line(x,0,x,0.009 if x%5==0 else 0.005,1)
        if x and x%5==0:
            label(x,-0.022,str(x).replace('-','−'),'mt')
    for i in range(-8,12):
        y=i*0.05
        line(0,y,0.14 if i%4==0 else 0.08,y,1)
        if i and i%4==0:
            label(-0.25,y,f'{y:.1f}'.replace('-','−'),'rm')
    pen.line([xy(x,y) for x,y in zip(s,values)],fill='black',width=2*scale)
    label(10.95,0,'s','lm')
    label(0.2,0.555,'Ai(s)','lm')
    im.resize((1080,672),Image.Resampling.LANCZOS).save(OUT/'figure1.png')


def compare_source(pdf, s, values):
    expected = '7157926aa09f2f6a5a496036e41bfeb201178a03e47dba61b78bb72e6722ee9b'
    assert hashlib.sha256(pdf.read_bytes()).hexdigest() == expected
    ref = pypdf.PdfReader(pdf).pages[1].images[0].image.convert('L')
    assert ref.size == (312,192)
    yy,xx = np.where(np.asarray(ref)<128)
    px,py = 156 + 14.7*s,106 - 191.25*values
    mask = (abs(px-156)>2) & (abs(py-106)>2)
    distances = [np.min(np.hypot(xx-a, yy-b)) for a,b in zip(px[mask],py[mask])]
    # Independently read peak/trough centers on the native bitmap (left to right).
    landmarks = [(16,45),(31,169),(48,41),(65,175),(85,34),(108,186),(141,4)]
    ix = np.where(np.diff(np.sign(np.diff(values))) != 0)[0]+1
    rows = [dict(s=float(s[i]), Ai=float(values[i]), ref_px=x, ref_py=y,
                 dx=float(px[i]-x),dy=float(py[i]-y)) for i,(x,y) in zip(ix,landmarks)]
    assert len(ix)==len(landmarks)
    return dict(sha256=expected, landmarks=rows, n_visible=len(distances),
                p95_px=float(np.percentile(distances,95)), max_px=float(max(distances)))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pdf',type=Path)
    args=parser.parse_args()
    s=np.linspace(-10,10,2001)
    values=airy(s)
    with (OUT/'curve.csv').open('w',newline='',encoding='ascii') as f:
        writer=csv.writer(f)
        writer.writerow(['s','Ai_s'])
        writer.writerows(zip(s,values))
    draw(s,values)
    table=np.loadtxt(OUT/'curve.csv',delimiter=',',skiprows=1)
    coarse=s[::50]
    alt_error=float(np.max(abs(values[::50]-[series(x) for x in coarse])))
    mesh_error=float(np.max(abs(values-airy(s,12,0.005))))
    ref=compare_source(args.pdf,s,values)
    roots=int(np.count_nonzero(values[:-1]*values[1:]<0))
    checks=dict(csv=bool(table.shape==(2001,2) and np.isfinite(table).all()
                         and np.array_equal(table,np.column_stack((s,values)))),
                series=alt_error<=1e-10, refinement=mesh_error<=1e-10,
                roots=roots==6, tail=bool(np.all(values[s>=0]>0) and
                                          np.all(np.diff(values[s>=0])<0)),
                landmarks=all(max(abs(r['dx']),abs(r['dy']))<=2 for r in ref['landmarks']),
                geometry=ref['p95_px']<=2)
    evidence=dict(utc=datetime.now(timezone.utc).isoformat(),python=sys.version,
                  platform=platform.platform(),numpy=np.__version__,pillow=PIL.__version__,
                  pypdf=pypdf.__version__,argv=[sys.executable,*sys.argv],checks=checks,
                  max_series_error=alt_error,max_refinement_error=mesh_error,
                  sign_changes=roots,Ai_at_minus10_zero_plus10=values[[0,1000,2000]].tolist(),
                  reference=ref)
    for name in ['plan.md','reproduce.py','figure1.png','curve.csv']:
        evidence.setdefault('sha256',{})[name]=hashlib.sha256((OUT/name).read_bytes()).hexdigest()
    (OUT/'run.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
    print(json.dumps(checks),flush=True)
    return 0 if all(checks.values()) else 1


if __name__=='__main__':
    raise SystemExit(main())

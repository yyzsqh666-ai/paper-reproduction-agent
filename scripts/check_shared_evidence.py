"""Check the deliberately shared subset; no PDF, private paths or full rerun.

Scientific assumptions and thresholds are in each case's extraction/plan/config.
This is an archive and saved-equation check, not independent human validation.
"""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import sys
import time

import numpy as np
from scipy.sparse import diags
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
RUNS = {'lieu2018-fig4':'20261102T144055_167379Z', 'ho-fd4-section21':'20261102T151707_448706Z'}

def read(path):
    return json.loads(path.read_text(encoding='utf8'))

def run_checks():
    checks=[]
    def record(name, ok, value):
        checks.append({'name':name,'passed':bool(ok),'value':value})
    for case,run in RUNS.items():
        base=ROOT/'cases'/case
        out=base/'evidence'/run
        manifest=read(out/'share-manifest.json')
        bad=[]
        for row in manifest['files']:
            p=(out/row['path']).resolve()
            if not p.is_relative_to(out.resolve()) or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=row['sha256']:
                bad.append(row['path'])
        record(case+':share_hashes',not bad,bad)
        snapshot=out/('run_source.py' if case.startswith('lieu') else 'snapshot/run.py')
        record(case+':current_solver_matches',snapshot.read_bytes()==(base/'src/run.py').read_bytes(),None)
        cfg=read(out/('config.json' if case.startswith('lieu') else 'snapshot/config.json'))
        record(case+':current_config_matches',cfg==read(base/'config.json'),None)
        original=read(out/'checks.json')
        flags=list(original['passed'].values()) if isinstance(original,dict) else [r['passed'] for r in original]
        record(case+':recorded_checks',all(flags),{'passed':sum(flags),'total':len(flags)})
        record(case+':recorded_exit',read(out/'status.json')['exit_code']==0,read(out/'status.json')['exit_code'])
        if case.startswith('lieu'):
            maximum=0.
            profiles=sorted(out.glob('profile_*.npz'))
            record(case+':profile_count', len(profiles)==len(cfg['profile_t_over_pi']),len(profiles))
            for p in profiles:
                t=float(p.stem.split('_')[1])*np.pi
                n=cfg['N']; H=np.zeros((2*n,2*n),complex)
                v=np.exp(1j*cfg['phase_over_pi']*np.pi)*np.sin(t); w=np.cos(t)
                for j in range(n):
                    H[2*j,2*j+1]=H[2*j+1,2*j]=v
                    H[2*j,2*j]=1j*cfg['u']; H[2*j+1,2*j+1]=-1j*cfg['u']
                    if j<n-1: H[2*j+1,2*j+2]=H[2*j+2,2*j+1]=w
                with np.load(p,allow_pickle=False) as d:
                    e,V=d['E'],d['V']
                    residual=float(np.max(np.linalg.norm(H@V-V*e,axis=0)/(np.linalg.norm(H,'fro')+np.abs(e))))
                    record(case+':'+p.stem, np.isfinite(residual) and residual<=cfg['tolerances']['residual'],residual)
                    maximum=max(maximum,residual)
            with np.load(out/'refined.npz',allow_pickle=False) as d:
                record(case+':refined_shape',d['E'].shape==(cfg['refined_samples'],2*cfg['N']) and np.isfinite(d['E']).all(),list(d['E'].shape))
        else:
            table=list(csv.DictReader((base/'source/table1.csv').open(encoding='utf8')))
            record(case+':reference_copy', (base/'source/table1.csv').read_bytes()==(out/'snapshot/table1.csv').read_bytes(),None)
            max_res=max_orth=0.
            with np.load(out/'eigenpairs.npz',allow_pickle=False) as d:
                tags=[k[:-2] for k in d.files if k.endswith('_e')]
                for tag in tags:
                    order=int(tag[1]); h=float(tag.split('_h')[1])
                    x,e,psi=(d[tag+'_'+k] for k in ['x','e','psi'])
                    diag=(1 if order==2 else 1.25)/h**2+x*x/2
                    nearest=(-.5 if order==2 else -2/3)/h**2
                    bands=[nearest*np.ones(len(x)-1),diag,nearest*np.ones(len(x)-1)]
                    offsets=[-1,0,1]
                    if order==4:
                        bands=[np.ones(len(x)-2)/(24*h*h)]+bands+[np.ones(len(x)-2)/(24*h*h)]
                        offsets=[-2,-1,0,1,2]
                    H=diags(bands,offsets,format='csr')
                    denom=np.max(np.asarray(abs(H).sum(axis=1)))+max(abs(e))
                    max_res=max(max_res,float(np.max(np.linalg.norm(H@psi-psi*e,axis=0)*np.sqrt(h)/denom)))
                    max_orth=max(max_orth,float(np.max(abs(h*psi.T@psi-np.eye(len(e))))))
                matches=sum(f"{d[f'o{order}_h{h}_e'][n]:.6f}"==f"{float(table[n][f'order{order}_h{h}']):.6f}" for order in [2,4] for h in ['0.1','0.01'] for n in range(10))
            record(case+':saved_equation_residual',np.isfinite(max_res) and max_res<=cfg['thresholds']['relative_residual'],max_res)
            record(case+':saved_orthogonality',np.isfinite(max_orth) and max_orth<=cfg['thresholds']['orthogonality'],max_orth)
            record(case+':published_rounded_values',matches==40,{'matches':matches,'total':40})
    return checks

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write',action='store_true',help='Write a new UTC-stamped result under records/')
    args=parser.parse_args()
    start=time.perf_counter(); now=datetime.now(timezone.utc)
    with threadpool_limits(limits=1):
        checks=run_checks()
    result={'evidence_label':'[推导]','utc':now.isoformat(),'cwd':'<PROJECT_ROOT>',
        'command':['<PYTHON>','scripts/check_shared_evidence.py']+(['--write'] if args.write else []),
        'path_policy':'Portable command; local absolute paths intentionally omitted.',
        'python':sys.version,'platform':platform.platform(),
        'versions':{m:importlib.metadata.version(m) for m in ['numpy','scipy','threadpoolctl']},
        'seed':None,'threading':'one BLAS thread','checks':checks,
        'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'elapsed_seconds':time.perf_counter()-start,'exit_code':0 if all(c['passed'] for c in checks) else 1,
        'scope':'Selected saved data only; no full rerun, no claim of independent user verification.'}
    output=json.dumps(result,indent=2,ensure_ascii=False)+'\n'
    if args.write:
        folder=ROOT/'records';folder.mkdir(exist_ok=True)
        (folder/('shared-check-'+now.strftime('%Y%m%dT%H%M%S_%fZ')+'.json')).write_text(output,encoding='utf8')
    print(output)
    return result['exit_code']

if __name__=='__main__':
    raise SystemExit(main())

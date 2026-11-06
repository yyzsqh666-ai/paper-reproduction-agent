"""Read back one archived Figure-4 run without rerunning the eigenvalue solver."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np
from run import model


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', type=Path, help='Explicit output directory; defaults to latest_run.txt')
    parser.add_argument('--write', action='store_true', help='Save archive_audit.json in that run')
    args = parser.parse_args()
    case = Path(__file__).resolve().parents[1]
    out = args.run.resolve() if args.run else case/(case/'latest_run.txt').read_text().strip()
    start = time.perf_counter()
    read = lambda name: json.loads((out/name).read_text(encoding='utf-8'))
    sha = lambda p: hashlib.file_digest(p.open('rb'), 'sha256').hexdigest()
    cfg, env, checks = read('config.json'), read('environment.json'), read('checks.json')
    tests = {'completed': read('status.json') == {'status':'completed','exit_code':0},
             'declared_checks': all(checks['passed'].values()),
             'archived_code_hash': sha(out/'run_source.py') == env['code_sha256'],
             'current_code_matches_archive': sha(case/'src/run.py') == env['code_sha256'],
             'current_config_matches_archive': json.loads((case/'config.json').read_text()) == cfg,
             'paper_hash': sha(case/'source/1709.03788v2.pdf') == env['source_pdf_sha256']}
    manifest = read('manifest.json')
    tests['manifest_hashes'] = all((out/name).is_file() and sha(out/name)==h for name,h in manifest.items())
    with np.load(out/'spectrum.npz') as data, np.load(out/'refined.npz') as fine:
        E, V, weights = data['E'], data['V'], data['weights']
        tests['shapes'] = E.shape==(cfg['samples'],2*cfg['N']) and V.shape==(cfg['samples'],2*cfg['N'],2*cfg['N']) and fine['E'].shape==(cfg['refined_samples'],2*cfg['N'])
        normalization = float(np.max(np.abs(weights.sum(axis=1)-1)))
        weight_error = float(np.max(np.abs(weights-np.abs(V)**2)))
        tests['saved_weights'] = max(normalization,weight_error)<1e-12
        tests['finite_spectrum_vectors'] = bool(np.isfinite(E).all() and np.isfinite(V).all())
        tests['resolved_edge_scores'] = bool(np.isfinite(fine['edge_score']).all())
        tests['nested_grid'] = bool(np.array_equal(E, fine['E'][::2]))
        # This checks serialized eigenvectors against H, without a new eigensolve.
        residuals=[]
        for i in [0,len(E)//2,len(E)-1]:
            H=model(cfg['N'],data['t'][i],cfg['phase_over_pi']*np.pi,cfg['u'])
            residuals.append(float(np.max(np.linalg.norm(H@V[i]-V[i]*E[i],axis=0)/(np.linalg.norm(H,'fro')+np.abs(E[i])))))
        tests['saved_eigenpair_residual'] = max(residuals)<=cfg['tolerances']['residual']
    result={'run':str(out),'cwd':str(Path.cwd()),'command':[sys.executable,*sys.argv],
            'script_sha256':sha(Path(__file__)),'checks':tests,'normalization_error':normalization,
            'weights_error':weight_error,'saved_residual_max':max(residuals),
            'elapsed_seconds':time.perf_counter()-start,'exit_code':0 if all(tests.values()) else 1,
            'scope':'Archive integrity and saved-array checks, not agreement with paper image.'}
    if args.write:
        (out/'archive_audit.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))
    raise SystemExit(result['exit_code'])


if __name__=='__main__':
    main()

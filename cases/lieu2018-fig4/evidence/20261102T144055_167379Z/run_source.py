"""Caption-faithful finite OBC spectrum; no Bloch replacement or level tracking."""
import argparse
import contextlib
import csv
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import sys
import time
import traceback

import numpy as np
import scipy
from scipy.linalg import eig, eigvals, svd, svdvals
from scipy.optimize import linear_sum_assignment
from scipy.sparse.csgraph import connected_components
os.environ.setdefault('MPLCONFIGDIR', str(Path(__file__).resolve().parents[1]/'.mplconfig'))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from threadpoolctl import threadpool_limits, threadpool_info


def hamiltonian(N, v1, v2, w1, w2, u=0):
    H = np.zeros((2*N, 2*N), dtype=np.complex128)
    a = 2*np.arange(N)
    b = a+1
    H[b, a], H[a, b] = v1, v2
    H[a, a], H[b, b] = 1j*u, -1j*u
    H[a[1:], b[:-1]], H[b[:-1], a[1:]] = w1, w2
    return H


def model(N, t, phase, u=0):
    v, w = np.exp(1j*phase)*np.sin(t), np.cos(t)
    return hamiltonian(N, v, v, w, w, u)


def match_error(a, b):
    cost = np.abs(a[:, None]-b[None, :])
    rows, cols = linear_sum_assignment(cost)
    return float(cost[rows, cols].max())


def solve(H, edge_cells, cluster_tol):
    E, V = eig(H, check_finite=True)
    V /= np.linalg.norm(V, axis=0)
    P = np.abs(V)**2
    m = 2*edge_cells
    ends = np.r_[np.arange(m), np.arange(len(H)-m, len(H))]
    W = P[ends].sum(axis=0)
    score = W.copy()
    # Connected components avoid arbitrary eigenvector choices in degenerate spaces.
    adjacency = np.abs(E[:, None]-E[None, :]) < cluster_tol
    count, labels = connected_components(adjacency, directed=False)
    cluster_size = np.ones(len(E), dtype=int)
    subspace_min = np.full(len(E), np.nan)
    subspace_max = np.full(len(E), np.nan)
    for label in range(count):
        ix = np.flatnonzero(labels == label)
        if len(ix) > 1:
            U, s, _ = svd(V[:, ix], full_matrices=False)
            rank = np.count_nonzero(s > s[0]*1e-12)
            if rank != len(ix):
                score[ix] = np.nan  # defective/unresolved subspace, never silently color red
                continue
            endpoint_s = svdvals(U[ends])
            lo = float(endpoint_s[-1]**2) if len(endpoint_s) == rank else 0.0
            hi = float(endpoint_s[0]**2)
            score[ix] = lo
            cluster_size[ix] = len(ix)
            subspace_min[ix], subspace_max[ix] = lo, hi
    normH = np.linalg.norm(H, 'fro')
    residual = np.linalg.norm(H@V-V*E, axis=0)/(normH+np.abs(E))
    gamma = np.tile([1, -1], len(H)//2)
    chiral = np.linalg.norm(gamma[:, None]*H*gamma[None, :]+H, 'fro')/max(normH, 1)
    pairing = match_error(E, -E)/max(1, np.max(np.abs(E)))
    return dict(E=E, V=V, weights=P, end_weight=W, ipr=(P**2).sum(axis=0),
                edge_score=score, residual=residual, chiral=float(chiral), pairing=pairing,
                cluster_size=cluster_size, subspace_min=subspace_min, subspace_max=subspace_max)


def csv_write(path, rows):
    with path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def dump(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')


def validate_config(cfg):
    """This entry point validates the u=0 Figure-4 family, not arbitrary SSH models."""
    if cfg['u'] != 0:
        raise ValueError('Only u=0 is supported: chiral and dimer checks assume u=0.')
    for key in ['N', 'edge_cells', 'samples', 'refined_samples']:
        if type(cfg[key]) is not int or cfg[key] < 1:
            raise ValueError(f'{key} must be a positive integer')
    if cfg['samples'] < 3 or cfg['refined_samples'] != 2*cfg['samples']-1:
        raise ValueError('Require samples>=3 and refined_samples=2*samples-1')
    if not cfg['sizes'] or any(type(n) is not int or n <= 2*cfg['edge_cells'] for n in [cfg['N'], *cfg['sizes']]):
        raise ValueError('Every chain size must exceed 2*edge_cells')
    if not 0 <= cfg['t_min_over_pi'] < cfg['t_max_over_pi'] <= .5:
        raise ValueError('Require 0<=t_min/pi<t_max/pi<=0.5')
    if len(cfg['profile_t_over_pi']) != 6 or len(set(cfg['profile_t_over_pi'])) != 6:
        raise ValueError('The profile figure requires six distinct parameter points')
    if len({f'{t:.3f}' for t in cfg['profile_t_over_pi']}) != 6:
        raise ValueError('Profile filenames must be distinct at three decimal places')
    for key in ['size_t_over_pi', 'profile_t_over_pi']:
        if not cfg[key] or any(not 0 <= t <= .5 for t in cfg[key]):
            raise ValueError(f'{key} requires points in [0,0.5]')
    if 0 not in cfg['phase_regression_over_pi']:
        raise ValueError('phase_regression_over_pi must include zero for Hermitian regression')
    if not np.isfinite(cfg['phase_over_pi']):
        raise ValueError('phase_over_pi must be finite')
    if not cfg['thresholds'] or any(not 0 < x < 1 for x in [cfg['edge_threshold'], *cfg['thresholds']]):
        raise ValueError('Endpoint thresholds must be strictly between 0 and 1')
    if not np.isfinite(cfg['cluster_tolerance']) or cfg['cluster_tolerance'] <= 0:
        raise ValueError('cluster_tolerance must be finite and positive')
    for key in ['residual', 'chiral', 'pairing', 'limit', 'shared_grid']:
        if not np.isfinite(cfg['tolerances'][key]) or cfg['tolerances'][key] <= 0:
            raise ValueError(f'Tolerance {key} must be finite and positive')


def small_check(out):
    v1, v2, w1, w2 = 1+2j, 3+4j, 5+6j, 7+8j
    expected = np.array([[0,v2,0,0,0,0], [v1,0,w2,0,0,0],
                         [0,w1,0,v2,0,0], [0,0,v1,0,w2,0],
                         [0,0,0,w1,0,v2], [0,0,0,0,v1,0]], complex)
    H = hamiltonian(3, v1, v2, w1, w2)
    np.savetxt(out/'small_chain_matrix.txt', H, fmt='%.1f')
    assert np.array_equal(H, expected)
    assert np.count_nonzero(H) == 10
    assert H[0,-1] == H[-1,0] == 0
    assert np.array_equal(np.diag(hamiltonian(3,v1,v2,w1,w2,.3)), np.tile([.3j,-.3j],3))
    return dict(max_matrix_error=float(np.max(np.abs(H-expected))), dimension=6, nonzero=10, passed=True)


def scan(ts, cfg, save_vectors):
    keys = ['E','end_weight','ipr','edge_score','residual','cluster_size','subspace_min','subspace_max']
    if save_vectors:
        keys += ['V','weights']
    collected = {k: [] for k in keys}
    chiral, pairing = [], []
    start = time.perf_counter()
    for i,t in enumerate(ts):
        d = solve(model(cfg['N'],t,cfg['phase_over_pi']*np.pi,cfg['u']), cfg['edge_cells'],cfg['cluster_tolerance'])
        for k in keys:
            collected[k].append(d[k])
        chiral.append(d['chiral']); pairing.append(d['pairing'])
        if i == 4:
            print(f'Pilot: 5 points {time.perf_counter()-start:.3f}s; extrapolated scan {(time.perf_counter()-start)*len(ts)/5:.1f}s', flush=True)
        if i % 100 == 0:
            print(f'Scan {len(ts)}: {i+1}/{len(ts)}', flush=True)
    result = {k: np.array(v) for k,v in collected.items()}
    result.update(t=ts, chiral=np.array(chiral), pairing=np.array(pairing))
    print(f'Scan finished: {len(ts)} points in {time.perf_counter()-start:.3f}s', flush=True)
    return result


def spectrum_plot(data, cfg, path):
    E, ts = data['E'], data['t']
    red = data['edge_score'] > cfg['edge_threshold']
    X = np.broadcast_to(ts[:,None], E.shape)
    fig, axes = plt.subplots(1,2,figsize=(10,4),layout='constrained')
    for ax,Y,label in zip(axes,[E.real,E.imag],[r'Re $E$',r'Im $E$']):
        ax.scatter(X[~red],Y[~red],s=.15,c='#225dcc',rasterized=True,label='Other states (includes weak edge states)')
        ax.scatter(X[red],Y[red],s=2,c='#d32f2f',rasterized=True,label=f'Endpoint-localized: score > {cfg["edge_threshold"]}')
        ax.set(xlim=(ts[0],ts[-1]),ylim=(-1.5,1.5),xlabel=r'$t$',ylabel=label)
        ax.set_xticks([0,np.pi/4,np.pi/2],['0',r'$\pi/4$',r'$\pi/2$'])
        ax.set_yticks([-1,0,1]); ax.grid(alpha=.12)
    axes[1].legend(loc='upper left',fontsize=7,markerscale=3)
    fig.suptitle(r'Caption parameters: $N=100$, $v=e^{i\pi/5}\sin t$, $w=\cos t$ (OBC)'
                 if cfg['N']==100 and cfg['phase_over_pi']==.2 else f'OBC: N={cfg["N"]}, phase/pi={cfg["phase_over_pi"]}')
    fig.savefig(path,dpi=200); plt.close(fig)


def execute(cfg, out):
    start = time.perf_counter()
    checks = {'small_chain': small_check(out)}
    print('Small chain exact connection check passed.',flush=True)
    phase = cfg['phase_over_pi']*np.pi
    ts = np.linspace(cfg['t_min_over_pi']*np.pi,cfg['t_max_over_pi']*np.pi,cfg['samples'])
    data = scan(ts,cfg,True)
    np.savez_compressed(out/'spectrum.npz', **data)
    spectrum_plot(data,cfg,out/'spectrum.png')
    checks['residual_max'] = float(data['residual'].max())
    checks['chiral_max'] = float(data['chiral'].max())
    checks['pairing_max'] = float(data['pairing'].max())
    N = cfg['N']
    expected0 = np.r_[np.ones(N-1),-np.ones(N-1),0,0].astype(complex)
    expected1 = np.r_[np.ones(N),-np.ones(N)]*np.exp(1j*phase)
    checks['dimer_t0_error'] = match_error(eigvals(model(N,0,phase)),expected0)
    checks['dimer_tpi2_error'] = match_error(eigvals(model(N,np.pi/2,phase)),expected1)
    checks['tpi2_positive_energy'] = {'real':float(np.cos(phase)), 'imag':float(np.sin(phase))}

    fine_ts = np.linspace(ts[0],ts[-1],cfg['refined_samples'])
    # Only additional grid points are solved; common points are reused, not independent verification.
    assert len(fine_ts)==2*len(ts)-1
    midpoint = scan(fine_ts[1::2],cfg,False)
    fine = {}
    for k in midpoint:
        a = np.empty((len(fine_ts),)+midpoint[k].shape[1:],dtype=midpoint[k].dtype)
        a[::2],a[1::2] = data[k],midpoint[k]
        fine[k] = a
    np.savez_compressed(out/'refined.npz',**fine)
    spectrum_plot(fine,cfg,out/'spectrum_refined.png')
    # Independent re-solves at three common points test repeatability.
    repeated = []
    for i in [len(ts)//4,len(ts)//2,3*len(ts)//4]:
        repeated.append(match_error(eigvals(model(N,ts[i],phase,cfg['u'])),data['E'][i]))
    checks['repeated_common_point_error'] = max(repeated)
    checks['refined_residual_max'] = float(fine['residual'].max())
    checks['refined_pairing_max'] = float(fine['pairing'].max())
    coarse_steps = [match_error(a,b) for a,b in zip(data['E'][:-1],data['E'][1:])]
    fine_steps = [match_error(a,b) for a,b in zip(fine['E'][:-1],fine['E'][1:])]
    checks['sampling'] = {'coarse_step_t':float(ts[1]-ts[0]),'fine_step_t':float(fine_ts[1]-fine_ts[0]),
                          'coarse_max_adjacent_spectral_change':max(coarse_steps),
                          'fine_max_adjacent_spectral_change':max(fine_steps)}
    rows=[]
    for i,t in enumerate(fine_ts):
        r={'t_over_pi':float(t/np.pi)}
        for threshold in cfg['thresholds']:
            r[f'count_Wgt{threshold}']=int(np.sum(fine['edge_score'][i]>threshold))
        rows.append(r)
    csv_write(out/'threshold_scan.csv',rows)
    intervals=[]
    for threshold in cfg['thresholds']:
        for name,d in [('coarse',data),('refined',fine)]:
            selected = np.sum(d['edge_score']>threshold,axis=1)==2
            ix=np.flatnonzero(selected)
            intervals.append({'grid':name,'threshold':threshold,'two_edge_points':len(ix),
                              'last_t_over_pi':float(d['t'][ix[-1]]/np.pi) if len(ix) else None})
    checks['threshold_intervals']=intervals

    size_rows=[]
    for n in cfg['sizes']:
        for tpi in cfg['size_t_over_pi']:
            d=solve(model(n,tpi*np.pi,phase),cfg['edge_cells'],cfg['cluster_tolerance'])
            ix=np.argsort(np.abs(d['E']))[:2]
            size_rows.append(dict(N=n,t_over_pi=tpi, splitting_abs=float(abs(d['E'][ix[0]]-d['E'][ix[1]])),
                                  max_abs_E=float(np.max(abs(d['E'][ix]))), end_weight_min=float(min(d['end_weight'][ix])),
                                  ipr_min=float(min(d['ipr'][ix])),edge_score_min=float(min(d['edge_score'][ix])),
                                  residual_max=float(max(d['residual']))))
    csv_write(out/'finite_size.csv',size_rows)
    phase_rows=[]
    for tpi in [.15,.24,.30]:
        for phi in cfg['phase_regression_over_pi']:
            H=model(N,tpi*np.pi,phi*np.pi)
            E=eigvals(H)
            phase_rows.append(dict(t_over_pi=tpi,phase_over_pi=phi,max_abs_imag=float(max(abs(E.imag)))))
    csv_write(out/'phase_regression.csv',phase_rows)
    regression_errors=[]
    for tpi in [.15,.24,.30]:
        H=model(N,tpi*np.pi,0)
        Q=H[::2,1::2]
        s=svdvals(Q)
        regression_errors.append(match_error(eigvals(H),np.r_[s,-s].astype(complex)))
    checks['hermitian_svd_error']=max(regression_errors)
    checks['hermitian_max_imag']=max(r['max_abs_imag'] for r in phase_rows if r['phase_over_pi']==0)

    fig,axes=plt.subplots(2,3,figsize=(12,6),layout='constrained')
    profile_metrics=[]
    for ax,tpi in zip(axes.flat,cfg['profile_t_over_pi']):
        d=solve(model(N,tpi*np.pi,phase),cfg['edge_cells'],cfg['cluster_tolerance'])
        ix=np.argsort(np.abs(d['E']))[:2]
        U,s,_=svd(d['V'][:,ix],full_matrices=False)
        projector_weight=(np.abs(U[:,:2])**2).sum(axis=1)/2
        m=2*cfg['edge_cells']; ends=np.r_[np.arange(m),np.arange(2*N-m,2*N)]
        endpoint_eigenvalues=svdvals(U[ends,:2])**2
        other=np.flatnonzero(d['edge_score']<=cfg['edge_threshold'])
        bulk_index=int(other[np.argmin(d['ipr'][other])]) if len(other) else -1
        np.savez_compressed(out/f'profile_{tpi:.3f}.npz',**d,selected=ix,subspace_weight=projector_weight,
                            subspace_endpoint_eigenvalues=endpoint_eigenvalues,bulk_index=bulk_index)
        ax.plot(np.arange(1,2*N+1),d['weights'][:,ix[0]],label='right eigenvector 1',lw=1)
        ax.plot(np.arange(1,2*N+1),projector_weight,label='two-state subspace / 2',lw=1,ls='--')
        if bulk_index>=0:
            ax.plot(np.arange(1,2*N+1),d['weights'][:,bulk_index],label='other state (min IPR)',lw=.8,color='gray')
        ax.set(title=f't/pi = {tpi:g}',xlabel='site',ylabel='spatial weight')
        ax.set_ylim(bottom=0)
        profile_metrics.append({'t_over_pi':tpi,'selected_abs_E':abs(d['E'][ix]).tolist(),
                                'end_weights':d['end_weight'][ix].tolist(),
                                'subspace_endpoint_eigenvalues':endpoint_eigenvalues.tolist()})
    axes.flat[0].legend(fontsize=7)
    fig.savefig(out/'profiles.png',dpi=180);plt.close(fig)
    dump(out/'profile_metrics.json',profile_metrics)
    # Analytic semi-infinite trial states tested against finite matrix, not fitted.
    t=.15*np.pi; r=-np.exp(1j*phase)*np.tan(t)
    trial=np.zeros(2*N,complex);trial[::2]=r**np.arange(N);trial/=np.linalg.norm(trial)
    checks['semi_infinite_trial']={'t_over_pi':.15,'weight_ratio':float(abs(r)**2),
                                  'finite_chain_residual':float(np.linalg.norm(model(N,t,phase)@trial)),
                                  'predicted_end_weight':float(1-abs(r)**(2*cfg['edge_cells']))}
    tol=cfg['tolerances']
    checks['passed']={
        'small_chain':checks['small_chain']['passed'],
        'residual':max(checks['residual_max'],checks['refined_residual_max'])<=tol['residual'],
        'chiral':checks['chiral_max']<=tol['chiral'],
        'pairing':max(checks['pairing_max'],checks['refined_pairing_max'])<=tol['pairing'],
        'dimer_limits':max(checks['dimer_t0_error'],checks['dimer_tpi2_error'])<=tol['limit'],
        'hermitian':max(checks['hermitian_svd_error'],checks['hermitian_max_imag'])<=tol['limit'],
        'repeated_points':checks['repeated_common_point_error']<=tol['shared_grid']}
    checks['elapsed_seconds']=time.perf_counter()-start
    dump(out/'checks.json',checks)
    print(json.dumps(checks,indent=2),flush=True)
    lines=['# 自动数值验证记录','', '这些通过项只验证所实现的图注模型，不能证明原图一致。','',
           '| 检查 | 通过 |','| --- | --- |']
    lines += [f'| {k} | {v} |' for k,v in checks['passed'].items()]
    lines += ['', '实际数值、预设容差、环境分别见 checks.json、config.json、environment.json。',
              '阈值敏感性与有限尺寸效应见 threshold_scan.csv、finite_size.csv；它们不被包装为求解器通过项。']
    (out/'verification_auto.md').write_text('\n'.join(lines),encoding='utf-8')
    if not all(checks['passed'].values()):
        raise RuntimeError('One or more predeclared numerical checks failed; see checks.json')


def main():
    p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True);args=p.parse_args()
    cfg=json.loads(args.config.read_text(encoding='utf-8'))
    case=args.config.resolve().parent
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    out=case/cfg['output_root']/stamp;out.mkdir(parents=True,exist_ok=False)
    dump(out/'config.json',cfg)
    (out/'run_source.py').write_bytes(Path(__file__).read_bytes())
    env={'python':sys.version,'executable':sys.executable,'platform':platform.platform(),
         'machine':platform.machine(),'processor':platform.processor(),'cwd':str(Path.cwd()),
         'command':[sys.executable,*sys.argv],'timestamp_utc':stamp,'randomness':'none',
         'packages':{k:importlib.metadata.version(k) for k in ['numpy','scipy','matplotlib','threadpoolctl']},
         'code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
         'config_sha256':hashlib.sha256(args.config.read_bytes()).hexdigest(),
         'config_input_path':str(args.config.resolve()),
         'source_pdf_sha256':hashlib.sha256((case/'source/1709.03788v2.pdf').read_bytes()).hexdigest()}
    print(f'Output: {out}',flush=True)
    status={'status':'running','exit_code':None}
    dump(out/'status.json',status)
    try:
        with (out/'run.log').open('w',encoding='utf-8',buffering=1) as log:
            with contextlib.redirect_stdout(log),contextlib.redirect_stderr(log),threadpool_limits(limits=1):
                env['threadpools']=threadpool_info();dump(out/'environment.json',env)
                try:
                    validate_config(cfg)
                    execute(cfg,out)
                except BaseException:
                    traceback.print_exc();raise
        manifest={p.name:hashlib.file_digest(p.open('rb'),'sha256').hexdigest()
                  for p in sorted(out.iterdir()) if p.is_file() and p.name != 'status.json'}
        dump(out/'manifest.json',manifest)
        status={'status':'completed','exit_code':0}
        (case/'latest_run.txt').write_text(out.relative_to(case).as_posix(),encoding='utf-8')
    except BaseException:
        status={'status':'failed','exit_code':1};raise
    finally:
        dump(out/'status.json',status)
    print(f'Completed; see {out / "checks.json"}',flush=True)


if __name__=='__main__':
    main()

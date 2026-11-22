"""Shared preflight and process-local evidence for the two formal case entries."""
import hashlib
from importlib.metadata import version
import json
import math
from datetime import datetime, timezone
from pathlib import Path
import sys
import platform
import subprocess
import time
import traceback
import uuid


def utc():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf8")


def inventory(root):
    return {p.relative_to(root).as_posix(): {"bytes": p.stat().st_size, "sha256": sha(p)}
            for p in sorted(root.rglob("*")) if p.is_file() and ".mpl-cache" not in p.parts}


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def load(path):
    def invalid(value):
        raise ValueError(f"Invalid JSON number {value}")
    return json.loads(path.read_text(encoding="utf8"), parse_constant=invalid)


def positive(config, keys, integer=False):
    for key in keys.split():
        x = config[key]
        require(type(x) in ((int,) if integer else (float, int)) and math.isfinite(x) and x > 0,
                f"Invalid positive parameter {key}: {x}")


def preflight(case, out, ssh):
    repo = case.parents[1]
    baseline = case / "records/baseline"
    record = load(baseline / "record.json")
    pdf = case / "source/paper.pdf" if ssh else case / record["source"]["path"]
    expected = ("f5ce343dfa033606e488a12e62d31ee7ac6e019b0142ea439da27b49acc16759"
                if ssh else record["source"]["sha256"])
    actual = sha(pdf)
    require(actual == expected, f"PDF SHA256 mismatch: {pdf}, expected {expected}, observed {actual}")
    hashes = record["sha256" if ssh else "snapshots_sha256"]
    frozen = {Path(k).name: v for k, v in hashes.items()}
    for name in ("AGENTS.md", "plan.md", "extraction.md", "transfer-test.md", "reproduce.md"):
        require(sha(baseline / name) == frozen[name], f"Baseline SHA256 mismatch: {name}")
    lock = repo / "cases/ho-fd4-section21/requirements-lock.txt" if ssh else case / "requirements-lock.txt"
    packages = {}
    for line in lock.read_text(encoding="utf8").splitlines():
        if line.strip():
            package, declared = line.split("==")
            packages[package] = version(package)
            require(packages[package] == declared, f"Environment mismatch: {package} {packages[package]} != {declared}")
    require(packages.keys() >= ({"scipy", "numpy", "matplotlib", "threadpoolctl"} if ssh else {"numpy", "matplotlib"}),
            "Incomplete requirements lock")
    config = load(case / "config.json")
    if ssh:
        positive(config, "cells coarse_intervals", True)
        require(config["cells"] == 10, "Fig. 6 requires ten cells")
        positive(config, "ratio_max")
        require(config["edge_profile_ratios"] and all(0 < x < 10/11 for x in config["edge_profile_ratios"]),
                "Invalid edge_profile_ratios")
        positive(config["thresholds"], "residual orthogonality energy_pairing analytic_energy edge_density midpoint_interpolation")
    else:
        positive(config, "band_count bisection_steps", True)
        require(config["band_count"] == 3 and config["switch_P_over_pi"] == 4, "Invalid Fig. 3 bands or axis")
        positive(config["plot_subdivisions"], "smoke full", True)
        positive(config["limits"], "wall_seconds memory_bytes")
        positive(config["tolerances"], "coordinate dispersion strong_barrier_strength_over_switch strong_barrier_max_width")
        positive(config["fd"], "max_refinement_ratio")
        for mode in ("smoke", "full"):
            fd = config["fd"][mode]
            positive(fd, "max_error")
            nodes = fd["nodes"]
            require(len(nodes) >= 2 and nodes == sorted(set(nodes)) and all(type(n) is int and n > 3 for n in nodes),
                    f"Invalid fd.{mode}.nodes")
            require(fd["strength_over_switch"] and all(type(x) in (float,int) and math.isfinite(x) and x >= 0
                                                       for x in fd["strength_over_switch"]), "Invalid FD strengths")
    files = [case / n for n in ("run.py", "config.json", "plan.md", "extraction.md")]
    files += [lock, Path(__file__), baseline / "record.json"] + [baseline / n for n in frozen]
    if not ssh:
        files.append(case / "run.ps1")
    save(out / "preflight.json", {"pdf_sha256": actual, "pdf": str(pdf), "packages": packages,
                                 "sha256": {str(p.relative_to(repo)): sha(p) for p in files}})
    return config


def run(case, out, ssh, calculate, *, reserved=False):
    started = utc()
    clock = time.perf_counter()
    status = {"started_utc": started, "cwd": str(Path.cwd()), "executable": sys.executable,
              "argv": sys.orig_argv, "command": subprocess.list2cmdline(sys.orig_argv),
              "platform": platform.platform(), "python": sys.version, "ancestor_argv": None, "seed": None,
              "stdout": "inherited", "stderr": "inherited", "success": False, "stage": "allocate"}
    code = 1
    try:
        # Exclusive ownership precedes any write, including diagnostics.
        if reserved:
            if not out.is_dir() or any(out.iterdir()):
                raise FileExistsError(str(out))
        else:
            out.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        requested = out
        out = out.with_name(out.name + "-conflict-" + uuid.uuid4().hex)
        out.mkdir()
        status["error"] = f"Output already exists: {requested}"
    try:
        if "error" in status:
            raise FileExistsError(status["error"])
        status["stage"] = "preflight"
        config = preflight(case, out, ssh)
        status["stage"] = "calculation"
        code = calculate(out, config)
        status["success"] = code == 0
        if code:
            status["error"] = "Numerical checks failed"
    except Exception as exc:
        status["error"] = str(exc)
        (out / "failure.log").write_text(traceback.format_exc(), encoding="utf8")
        print(status["error"], file=sys.stderr)
    status.update(exit_code=code, ended_utc=utc(), elapsed_seconds=time.perf_counter()-clock)
    save(out / "status.json", status)
    save(out / "manifest.json", inventory(out))
    print(f"{out} (exit {code})")
    return code


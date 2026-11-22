"""Run the two official entries in disposable copies, archive and verify evidence."""
import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

from run_evidence import inventory, load, require, save, sha, utc
from verify_bloch import check as check_bloch
from verify_ssh import check as check_ssh

ROOT = Path(__file__).resolve().parents[1]
SSH = "delplace2011-fig6"
KP = "kronig-penney1931-fig3"
LOCK = Path("cases/ho-fd4-section21/requirements-lock.txt")
QUANT = ROOT / "_acceptance/20261122-kronig-penney/checks/quant_check.py"


def execute(cmd, cwd, dest):
    start = utc()
    dest.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
    with (dest/"stdout.txt").open("wb") as stdout, (dest/"stderr.txt").open("wb") as stderr:
        process = subprocess.run(cmd, cwd=cwd, env=env, stdout=stdout, stderr=stderr)
    record = dict(executable=cmd[0], argv=cmd, cwd=str(cwd), start_utc=start, end_utc=utc(),
                  exit_code=process.returncode, stdout="stdout.txt", stderr="stderr.txt")
    save(dest/"process.json", record)
    return process.returncode


def check_json_logs(out):
    for f in out.iterdir():
        if f.suffix in {".json", ".txt", ".csv", ".log"}:
            data = f.read_bytes()
            require(not data.startswith(b"\xef\xbb\xbf") and b"\0" not in data, f"Unexpected encoding {f}")
            data.decode("utf8")
            if f.suffix == ".json":
                load(f)


def verify_manifest(folder):
    for name, record in load(folder/"manifest.json").items():
        p = folder/name
        require(record == {"sha256": sha(p), "bytes": p.stat().st_size}, f"Manifest mismatch: {p}")


def run_test(tmp, dest, name, scenario, kp_python, shell):
    case = tmp/"cases"/name
    ssh = name == SSH
    shutil.copytree(ROOT/"cases"/name, case, ignore=shutil.ignore_patterns(
        "outputs", "evidence", "__pycache__", "latest-success.json"))
    (tmp/"scripts").mkdir()
    shutil.copy2(ROOT/"scripts/run_evidence.py", tmp/"scripts")
    (tmp/LOCK).parent.mkdir(parents=True)
    shutil.copy2(ROOT/LOCK, tmp/LOCK)
    record = case/"records/baseline/record.json"
    baseline = load(record)
    if ssh:
        pdf = case/"source/paper.pdf"
        lock = tmp/LOCK
    else:
        pdf = tmp/"paper.pdf"
        shutil.copyfile(case / baseline["source"]["path"], pdf)
        baseline["source"]["path"] = str(pdf)
        save(record, baseline)
        lock = case/"requirements-lock.txt"
    config = case/"config.json"
    expected = None
    if scenario == "missing-pdf":
        pdf.unlink()
        expected = "paper.pdf"
    elif scenario == "bad-pdf":
        pdf.write_bytes(b"altered isolated PDF")
        expected = "PDF SHA256 mismatch"
    elif scenario == "missing-config":
        config.unlink()
        expected = "config.json"
    elif scenario == "invalid-json":
        config.write_text("{", encoding="utf8")
        expected = "Expecting"
    elif scenario == "missing-field":
        data = load(config)
        key = "thresholds" if ssh else "tolerances"
        del data[key]
        save(config, data)
        expected = key
    elif scenario == "missing-baseline":
        record.unlink()
        expected = "record.json"
    elif scenario == "lock":
        lock.write_text(lock.read_text(encoding="utf8").replace("numpy==", "numpy==0."), encoding="utf8")
        expected = "Environment mismatch"
    elif scenario == "exception":
        # Inject a fault in the disposable computation only.
        entry = case/"run.py"
        marker = "    cells = config" if ssh else "    switch = config"
        original = entry.read_text(encoding="utf8")
        require(marker in original, "Fault injection marker missing")
        entry.write_text(original.replace(marker, '    raise RuntimeError("injected calculation fault")\n'+marker, 1),
                         encoding="utf8")
        expected = "injected calculation fault"
    outputs = case/("outputs" if ssh else "evidence")
    outputs.mkdir()
    normal = scenario in ("A", "B", "shell-smoke")
    marker_file = outputs/"previous"/"checks.json"
    if scenario == "conflict":
        marker_file.parent.mkdir()
        marker_file.write_text("old evidence", encoding="utf8")
    if ssh:
        cmd = [sys.executable, "-X", "utf8", str(case/"run.py")]
    else:
        cmd = [shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(case/"run.ps1"),
               "-Mode", "full" if scenario in ("A","B") else "smoke", "-PythonExecutable", kp_python]
    if not ssh and scenario == "conflict":
        cmd = [kp_python, "-B", "-u", str(case/"run.py"), "--mode", "smoke", "--output", str(marker_file.parent)]
        expected = "Output already exists"
    code = execute(cmd, tmp, dest)
    folders = [p for p in outputs.iterdir() if p.name != "previous"]
    require(len(folders) == 1, f"Unexpected output directories: {folders}")
    out = folders[0]
    for p in out.iterdir():
        if p.is_file() and p.suffix not in {".png",".pdf",".npz"}:
            shutil.copyfile(p, dest/("case-"+p.name))
    save(dest/"product-index.json", inventory(out))
    status = load(out/"status.json")
    if (out/"launcher.json").exists():
        launch = load(out/"launcher.json")
        require(launch["launcher"]["exit_code"] == launch["child"]["exit_code"] == code, "Launcher exit mismatch")
        require(Path(launch["launcher"]["executable"]).samefile(sys.executable if ssh else shell), "Wrong PowerShell executable")
        require(launch["child"]["argv"][1:] == status["argv"][1:], "Child argv mismatch")
    if ssh:
        require(launch["launcher"]["argv"][1:] == cmd[1:] and status["argv"][1:3] == ["-X","utf8"],
                "Python flags mismatch")
    check_json_logs(out)
    verify_manifest(out)
    if scenario == "conflict":
        require(marker_file.read_bytes() == b"old evidence", "Prior output overwritten")
    require(code == status["exit_code"] and status["success"] == (code == 0), "Inconsistent status")
    if expected:
        require(code != 0 and expected in status["error"], f"Expected {expected}: {status}")
        require(expected in (dest/"stderr.txt").read_text(encoding="utf8"), "Missing error in stderr")
        require(status["stage"] == ("calculation" if scenario == "exception" else
                "allocate" if scenario == "conflict" else "preflight"), "Wrong failure stage")
        require(not (out/"checks.json").exists() and not list(out.glob("*.csv")), "False science products")
    else:
        require(code == 0, f"Failed normal entry {status}")
    if normal and ssh:
        physics = check_ssh(out/"spectrum.csv")
        save(dest/"independent-ssh.json", physics)
        require(physics["passed"], "SSH independent check")
    if normal and not ssh and scenario != "shell-smoke":
        code = execute([kp_python, str(QUANT), str(out), str(dest/"eq6.json")], tmp, dest/"eq6-command")
        require(code == 0 and load(dest/"eq6.json")["all_pass"], "Eq. (6) check")
        fem = check_bloch(out/"band-edges.csv")
        save(dest/"bloch-fem.json", fem)
        require(fem["passed"], "Bloch finite-element check")
        checks = load(out/"checks.json")
        require(checks["A4_independent_fd"]["pass"], "Independent real-space Bloch check")
    return {"exit_code":status["exit_code"], "stage":status["stage"], "reason":status.get("error")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--kp-python", default="python")
    args = parser.parse_args()
    dest = (args.archive or (ROOT/"_acceptance"/datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))).resolve()
    dest.mkdir(parents=True)
    verifiers = [Path(__file__), QUANT, ROOT/"scripts/verify_bloch.py", ROOT/"scripts/verify_ssh.py"]
    verifier_hashes = {x.name:sha(x) for x in verifiers}
    save(dest/"verifier-before.json", verifier_hashes)
    before = {n:inventory(ROOT/"cases"/n) for n in (SSH,KP)}
    save(dest/"before.json", before)
    summary = {}
    scratch = ROOT/".local"
    scratch.mkdir(exist_ok=True)
    ps = shutil.which("powershell.exe")
    for name in (SSH,KP):
        for scenario in ["A","B","missing-pdf","bad-pdf","missing-config","invalid-json","missing-field",
                         "missing-baseline","lock","conflict","exception"] + (["shell-smoke"] if name == KP else []):
            key = name+"/"+scenario
            shell = shutil.which("pwsh") if scenario == "shell-smoke" else ps
            try:
                with TemporaryDirectory(prefix="test-", dir=scratch) as tmp:
                    summary[key] = run_test(Path(tmp), dest/key, name, scenario, args.kp_python, shell)
                summary[key]["passed"] = True
            except Exception as exc:
                summary[key] = {"passed":False, "error":repr(exc)}
            print(key, summary[key], flush=True)
            save(dest/"results.json", summary)
        files = (["spectrum.csv","eigenpairs.npz","checks.json","spectrum.png"] if name == SSH else
                 ["band-edges.csv","fd-verification.csv","fig3.png","fig3.pdf"])
        try:
            a,b = [load(dest/name/tag/"product-index.json") for tag in ("A","B")]
            same = {f:a[f] == b[f] for f in files}
            summary[name+"/determinism"] = {"files":same, "passed":all(same.values())}
        except (OSError,KeyError) as exc:
            summary[name+"/determinism"] = {"passed":False, "error":str(exc)}
    audit = ROOT/"_acceptance/20261122-entry-audit"
    # Re-grade the frozen submission. A repeat run is not a second blind trial.
    try:
        grade = execute([sys.executable, str(audit/"grade_blind.py")], ROOT, dest/"blind-score")
        summary["blind-submission"] = {"passed":grade == 0 and load(dest/"blind-score/stdout.txt")["passed"]}
    except Exception as exc:
        summary["blind-submission"] = {"passed":False, "error":str(exc)}
    try:
        with TemporaryDirectory(dir=scratch) as tmp:
            raster = Path(tmp)/"page"
            code = execute([shutil.which("pdftoppm"), "-f", "4", "-l", "4", "-r", "400", "-singlefile",
                            "-png", str(ROOT/"cases"/SSH/"source/paper.pdf"), str(raster)], ROOT, dest/"render")
            require(code == 0, "Fig. 6 render failed")
            code = execute([sys.executable, str(audit/"read_fig6.py"), str(raster.with_suffix(".png")),
                            str(dest/SSH/"A/case-spectrum.csv")], ROOT, dest/"fig6-read")
            summary["figure6"] = {"passed":code == 0}
    except Exception as exc:
        summary["figure6"] = {"passed":False, "error":str(exc)}
    after = {n:inventory(ROOT/"cases"/n) for n in (SSH,KP)}
    save(dest/"after.json", after)
    check_hashes = {x.name:sha(x) for x in verifiers}
    save(dest/"verifier-after.json", check_hashes)
    summary["verification-code"] = {"passed":verifier_hashes == check_hashes}
    summary["originals"] = {"passed":before==after}
    save(dest/"results.json",summary)
    save(dest/"launcher.json",dict(argv=sys.orig_argv,executable=sys.executable,cwd=str(Path.cwd()),
                                   ancestor_argv=None, end_utc=utc(), start_utc=START, stdout="inherited", stderr="inherited",
                                   exit_code=int(not all(v["passed"] for v in summary.values()))))
    save(dest/"manifest.json", inventory(dest))
    verify_manifest(dest)
    return int(not all(v["passed"] for v in summary.values()))


if __name__ == "__main__":
    START=utc()
    sys.exit(main())


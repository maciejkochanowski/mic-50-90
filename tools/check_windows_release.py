"""Run a packaged Windows application outside the checkout and compare it to CLI."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from urllib.request import Request, urlopen


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--application", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    executable = args.application.resolve()
    receipt_path = args.receipt.resolve()
    if receipt_path.exists():
        parser.error("Use a new receipt path")
    config = {"n": 20, "unit": "mg/L", "panel": {"levels": [1, 2, 4]},
              "additional_counts": [{"threshold": 1, "count": 8, "n": 20, "unit": "mg/L"},
                                    {"threshold": 2, "count": 2, "n": 20, "unit": "mg/L"}],
              "targets": [{"start_category": "2", "end_category": "2", "unit": "mg/L",
                           "decision_operator": "<=", "decision_fraction": ".3"}]}
    env = dict(os.environ)
    for key in ("PYTHONPATH", "PYTHONHOME"):
        env.pop(key, None)
    env["PYTHONNOUSERSITE"] = "1"
    with tempfile.TemporaryDirectory(prefix="MIC Windows release check ") as temporary:
        root = Path(temporary)
        source = root / "input.json"
        source.write_text(json.dumps(config), encoding="utf-8")
        subprocess.run([sys.executable, "-I", "-m", "mic_50_90.cli", "distribution", str(source),
                        "--output-dir", str(root / "cli")], cwd=root, env=env, check=True,
                       capture_output=True, timeout=120)
        ready = root / "session.json"
        process = subprocess.Popen([str(executable), "--no-browser", "--ready-file", str(ready),
                                    "--output-root", str(root / "jobs")], cwd=root, env=env,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        session = None
        try:
            deadline = time.monotonic() + 60
            while not ready.is_file():
                if process.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError("Packaged Windows application did not become ready")
                time.sleep(.1)
            session = json.loads(ready.read_text(encoding="utf-8"))
            origin = "http://127.0.0.1:" + str(session["port"])

            def request(path, payload=None):
                headers = {"Authorization": "Bearer " + session["token"], "Origin": origin}
                if payload is not None:
                    headers["Content-Type"] = "application/json"
                with urlopen(Request(origin + path, data=None if payload is None else json.dumps(payload).encode(),
                                     headers=headers), timeout=30) as response:
                    return response.read()

            info = json.loads(request("/api/session"))
            if info["version"] != "1.0.0":
                raise AssertionError("Unexpected application version")
            page = request("/").decode("utf-8")
            if "MIC-50-90" not in page:
                raise AssertionError("The application HTML was not served")
            payload = {"mode": "distribution", "config": config, "options": {}}
            validation = json.loads(request("/api/validate", payload))
            if not validation["valid"]:
                raise AssertionError(validation)
            status = json.loads(request("/api/jobs", payload))
            deadline = time.monotonic() + 120
            while status["status"] == "running" and time.monotonic() < deadline:
                time.sleep(.2)
                status = json.loads(request("/api/jobs/" + status["job_id"]))
            if status["status"] != "completed":
                raise AssertionError(status["status"])
            output = Path(status["output_directory"])
            windows = json.loads((output / "results.json").read_text(encoding="utf-8"))["cohorts"][0]
            cli = json.loads((root / "cli/results.json").read_text(encoding="utf-8"))["cohorts"][0]
            for key in ("sample", "population", "calibration", "resolution", "decisions"):
                if windows[key] != cli[key]:
                    raise AssertionError("Windows and CLI differ: " + key)
            if windows["decisions"][0]["sample"]["count_components"] != [[6, 6]]:
                raise AssertionError("Independent count reference (8 - 2 = 6) did not match")
            report = request("/api/jobs/" + status["job_id"] + "/files/report.html")
            if b"recorded MIC category 2 mg/L" not in report:
                raise AssertionError("The report did not describe the analysed category")
            result = {"status": "passed", "software_version": info["version"], "platform": sys.platform,
                      "application_sha256": sha256(executable.read_bytes()).hexdigest(),
                      "expected_category_count": 6, "windows_cli_fields_equal":
                      ["sample", "population", "calibration", "resolution", "decisions"],
                      "application_started_outside_checkout": True, "multiprocess_analysis_completed": True,
                      "report_download_checked": True, "report_sha256": sha256(report).hexdigest()}
        finally:
            if session and process.poll() is None:
                try:
                    request("/api/shutdown", {})
                    process.wait(timeout=15)
                finally:
                    if process.poll() is None:
                        process.terminate()
                        process.wait(timeout=15)
            elif process.poll() is None:
                process.terminate()
                process.wait(timeout=15)
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result))


if __name__ == "__main__":
    main()

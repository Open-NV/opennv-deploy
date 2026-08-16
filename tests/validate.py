#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    result = subprocess.run(
        ["docker", "compose", "config", "--format", "json"],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    config = json.loads(result.stdout)
    required = {"mongo", "clisynth", "executor", "api", "console"}
    assert required == set(config["services"]), config["services"].keys()
    assert "mongo-data" in config["volumes"]
    api_environment = config["services"]["api"]["environment"]
    assert api_environment["MONGODB_URI"].startswith("mongodb://mongo:")
    assert api_environment["CLISYNTH_URL"].startswith("http://clisynth:")
    assert api_environment["NORNIR_EXECUTOR_URL"].startswith("http://executor:")
    assert api_environment["EXECUTOR_TOKEN"] == config["services"]["executor"]["environment"]["EXECUTOR_TOKEN"]

    generated = ROOT / ".generated" / "railway"
    subprocess.run(["python3", "scripts/build_railway_contexts.py"], cwd=ROOT, check=True)
    app_config = json.loads((generated / "app" / "railway.json").read_text())
    clisynth_config = json.loads((generated / "clisynth" / "railway.json").read_text())
    assert app_config["build"]["builder"] == "DOCKERFILE"
    assert app_config["deploy"]["healthcheckPath"] == "/readyz"
    assert clisynth_config["deploy"]["healthcheckPath"] == "/readyz"
    app_dockerfile = (generated / "app" / "Dockerfile").read_text()
    assert "VITE_API_URL=/v1" in app_dockerfile
    assert "VALIDATION_PACK_ROOT=/app/validation-packs" in app_dockerfile
    assert "OUTPUTFSM_PACK_ROOT=/app/outputfsm-packs" in app_dockerfile
    assert "executor" not in app_dockerfile.lower()
    assert (generated / "app" / "licenses" / "opennv-validation.LICENSE").is_file()
    assert (generated / "clisynth" / "licenses" / "clisynth.LICENSE").is_file()
    assert not (generated / "app" / "web" / "node_modules").exists()
    assert not (generated / "app" / "web" / "dist").exists()
    print("deploy config: 5 services, persistent Mongo volume, explicit service links")
    print("Railway config: public app + private CliSynth contexts, bundled 160x8 packs, no executor")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid


def request(url: str, method: str = "GET", body: dict | None = None, headers: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    request_headers = {"Accept": "application/json", **(headers or {})}
    if body is not None:
        request_headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=request_headers)
    with urllib.request.urlopen(req, timeout=30) as response:
        raw = response.read()
        return response.status, json.loads(raw) if raw else None


def expect_http_error(
    url: str,
    expected_status: int,
    method: str = "GET",
    body: dict | None = None,
    headers: dict | None = None,
) -> dict:
    try:
        request(url, method, body, headers)
    except urllib.error.HTTPError as error:
        payload = json.loads(error.read())
        assert error.code == expected_status, payload
        return payload
    raise AssertionError(f"expected HTTP {expected_status}: {url}")


def wait_healthy(url: str, attempts: int = 60) -> None:
    for _ in range(attempts):
        try:
            status, body = request(url)
            if status == 200 and body["status"] in {"ok", "ready"}:
                return
        except (OSError, urllib.error.HTTPError):
            pass
        time.sleep(1)
    raise RuntimeError(f"health check did not pass: {url}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--console-url", help="defaults to --base-url for the combined Railway image")
    parser.add_argument("--clisynth-url", help="optional direct CliSynth health check for local deployments")
    parser.add_argument(
        "--validation-matrix",
        action="store_true",
        help="also execute all 20 validation checks for each of the 8 platforms",
    )
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    console = (args.console_url or base).rstrip("/")
    wait_healthy(base + "/healthz")
    wait_healthy(base + "/readyz")
    if args.clisynth_url:
        wait_healthy(args.clisynth_url.rstrip("/") + "/healthz")
        wait_healthy(args.clisynth_url.rstrip("/") + "/readyz")
    health_status, health = request(base + "/healthz")
    assert health_status == 200 and health["demoMode"] is True, health
    with urllib.request.urlopen(console, timeout=30) as response:
        html = response.read().decode()
        assert response.status == 200 and "OpenNV" in html
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert "default-src 'self'" in response.headers["Content-Security-Policy"]
    blocked_admin = expect_http_error(
        base + "/v1/repositories",
        403,
        "POST",
        {"kind": "outputfsm", "name": "must-not-create", "url": "https://github.com/example/example.git"},
    )
    assert blocked_admin["code"] == "demo_admin_disabled", blocked_admin
    blocked_real = expect_http_error(
        base + "/v1/runs",
        400,
        "POST",
        {
            "kind": "commands",
            "mode": "real",
            "selector": {"field": "platform", "op": "eq", "value": "cisco_iosxe"},
            "commands": ["show version"],
            "credentialRef": "must-not-resolve",
        },
        {"Idempotency-Key": "blocked-real-" + uuid.uuid4().hex},
    )
    assert "not configured" in blocked_real["detail"], blocked_real
    status, platforms = request(base + "/v1/platforms")
    assert status == 200 and platforms["total"] == 8
    completed_runs: list[str] = []
    result_count = 0

    def wait_run(run_id: str) -> dict:
        run: dict = {}
        for _ in range(120):
            _, run = request(base + "/v1/runs/" + run_id)
            if run["state"] in {"completed", "failed"}:
                return run
            time.sleep(0.25)
        raise RuntimeError(f"run did not finish: {run_id}")

    for platform in platforms["items"]:
        platform_id = platform["id"]
        query = urllib.parse.urlencode({"platform": platform_id})
        command_status, commands = request(base + "/v1/commands?" + query)
        assert command_status == 200 and commands["total"] == 20, commands
        status, created = request(
            base + "/v1/runs",
            "POST",
            {
                "kind": "commands",
                "mode": "emulated",
                "name": f"deployment smoke test: {platform_id}",
                "selector": {"field": "platform", "op": "eq", "value": platform_id},
                "commands": [commands["items"][0]],
            },
            {"Idempotency-Key": "smoke-" + uuid.uuid4().hex},
        )
        assert status == 202
        run = wait_run(created["id"])
        assert run["state"] == "completed", run
        _, results = request(base + "/v1/runs/" + created["id"] + "/results")
        assert results["total"] == 4
        assert all(item["state"] == "succeeded" for item in results["items"])
        assert all(item["platform"] == platform_id for item in results["items"]), results
        assert all(item["backend"] == "clisynth" for item in results["items"]), results
        assert all(item["synthetic"] is True for item in results["items"]), results
        assert all(item.get("output") and item.get("parsed") for item in results["items"]), results
        completed_runs.append(created["id"])
        result_count += results["total"]
    print(
        f"smoke: security boundary + console + {len(completed_runs)} platform runs + "
        f"{result_count} persisted CliSynth results"
    )
    if args.validation_matrix:
        suite_status, suites = request(base + "/v1/validation-suites")
        assert suite_status == 200 and len(suites["items"]) == 8, suites
        validation_runs: list[str] = []
        validation_results = 0
        validation_passed = 0
        validation_unknown = 0
        for suite in suites["items"]:
            assert len(suite["platforms"]) == 1 and len(suite["checks"]) == 20, suite
            platform_id = suite["platforms"][0]
            status, created = request(
                base + "/v1/runs",
                "POST",
                {
                    "kind": "validation",
                    "mode": "emulated",
                    "name": f"deployment validation matrix: {platform_id}",
                    "selector": {"field": "platform", "op": "eq", "value": platform_id},
                    "suite": suite["name"],
                },
                {"Idempotency-Key": "validation-smoke-" + uuid.uuid4().hex},
            )
            assert status == 202
            run = wait_run(created["id"])
            assert run["state"] == "completed", run
            assert run["failedCount"] == 0 and run.get("errorCount", 0) == 0, run
            assert run["passedCount"] + run["unknownCount"] == 80, run
            _, results = request(base + "/v1/runs/" + created["id"] + "/results?limit=100")
            assert results["total"] == 80, results["total"]
            assert all(item["state"] == "succeeded" for item in results["items"]), results
            assert all(item["platform"] == platform_id for item in results["items"]), results
            assert all(item["backend"] == "clisynth" and item["synthetic"] is True for item in results["items"])
            assert all(item.get("validation") for item in results["items"]), results
            assert all(item["validation"]["state"] in {"passed", "unknown"} for item in results["items"]), results
            validation_runs.append(created["id"])
            validation_results += results["total"]
            validation_passed += run["passedCount"]
            validation_unknown += run["unknownCount"]
        print(
            f"validation matrix: {len(validation_runs)} suites x 20 checks x 4 devices = "
            f"{validation_results} persisted outcomes ({validation_passed} passed, "
            f"{validation_unknown} baseline-dependent unknown, 0 failed/error)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

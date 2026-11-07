"""Bounded GitHub-native successor dispatch. No copied user token or Worker secret.

The environment protection timer provides the delay without an idle runner.
Fail closed if the timer is missing: never start an accidental rapid dispatch loop.
"""
import datetime as dt
import json
import os
import urllib.error
import urllib.request

REPO = "jwavez/moneyhunter"
API = "https://api.github.com"


def request(path, token, data=None, opener=None):
    opener = opener or urllib.request.urlopen
    req = urllib.request.Request(API + path, data=None if data is None else json.dumps(data).encode(),
        headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28", "Content-Type": "application/json"})
    try:
        with opener(req, timeout=30) as response:
            body = response.read()
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        # Never print a response body, request headers or credential.
        raise RuntimeError(f"GitHub cadence request failed (HTTP {exc.code}); successor not confirmed") from None


def dispatch(env=None, when=None, opener=None):
    env = os.environ if env is None else env
    when = when or dt.datetime.now(dt.timezone.utc)
    if env.get("GITHUB_REPOSITORY") != REPO or env.get("GITHUB_REF") != "refs/heads/main":
        raise ValueError("Cadence is restricted to this repository's main branch")
    run_id = env.get("GITHUB_RUN_ID", "")
    if not run_id.isdigit() or not env.get("GH_TOKEN"):
        raise ValueError("Native workflow run and ephemeral repository token required")
    token = env["GH_TOKEN"]
    current = request(f"/repos/{REPO}/actions/runs/{run_id}", token, opener=opener)
    if current.get("head_branch") != "main" or current.get("path") != ".github/workflows/scan.yml":
        raise ValueError("Unexpected parent workflow or branch; refusing dispatch")
    created = dt.datetime.fromisoformat(current["created_at"].replace("Z", "+00:00"))
    probe = env.get("MH_CADENCE_PROBE") == "1"
    delay = 60 if probe else 30 * 60
    if (when-created).total_seconds() < delay:
        raise ValueError("Server-side wait timer absent or too short; refusing rapid dispatch")
    # One request only. Retrying an ambiguous POST can create duplicate live scans.
    inputs = {"dry_run": probe, "publish_state": probe, "keep_running": not probe,
              "cadence_probe": False, "parent_run_id": run_id}
    result = request(f"/repos/{REPO}/actions/workflows/scan.yml/dispatches", token,
                     {"ref": "main", "inputs": inputs}, opener=opener)
    return {"parent_run_id": run_id, "mode": "one_no_send_probe" if probe else "autonomous",
            "requested_at": when.isoformat(timespec="seconds"),
            "successor_run_id": result.get("workflow_run_id"), "successor_url": result.get("html_url")}


def main():
    result = dispatch()
    print(json.dumps(result, sort_keys=True))
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as out:
            out.write("## Native cadence dispatch\n" + json.dumps(result) + "\n")


if __name__ == "__main__":
    main()

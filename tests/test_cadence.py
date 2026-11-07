"""Offline cadence policy, provenance and genuine no-send publication acceptance."""
import datetime as dt
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError
from moneyhunter import cadence, cli, hub, config

NOW = dt.datetime(2026, 11, 7, 12, tzinfo=dt.timezone.utc)
ENV = {"GITHUB_REPOSITORY": "jwavez/moneyhunter", "GITHUB_REF": "refs/heads/main",
       "GITHUB_RUN_ID": "1234", "GH_TOKEN": "synthetic-not-a-credential"}


class Cadence(unittest.TestCase):
    def opener(self, created="2026-11-07T11:29:00Z", **changes):
        run = {"created_at": created, "head_branch": "main", "path": ".github/workflows/scan.yml", **changes}
        calls = []
        def open(req, timeout):
            calls.append(req)
            return io.BytesIO(json.dumps(run).encode() if req.data is None else b"")
        return open, calls

    def test_production_rearms_with_native_token_main_and_parent_audit(self):
        opener, calls = self.opener()
        out = cadence.dispatch(ENV, NOW, opener)
        self.assertEqual(len(calls), 2)
        body = json.loads(calls[1].data)
        self.assertEqual(body, {"ref": "main", "inputs": {"dry_run": False, "publish_state": False,
            "keep_running": True, "cadence_probe": False, "parent_run_id": "1234"}})
        self.assertEqual(out["mode"], "autonomous")
        self.assertNotIn(ENV["GH_TOKEN"], json.dumps(out))

    def test_one_minute_probe_is_no_send_publishes_real_state_and_cannot_chain(self):
        opener, calls = self.opener("2026-11-07T11:58:59Z")
        cadence.dispatch({**ENV, "MH_CADENCE_PROBE": "1"}, NOW, opener)
        inputs = json.loads(calls[1].data)["inputs"]
        self.assertTrue(inputs["dry_run"] and inputs["publish_state"])
        self.assertFalse(inputs["keep_running"] or inputs["cadence_probe"])

    def test_missing_timer_fail_closed_not_a_busy_loop(self):
        for seconds, probe in ((10, "1"), (1799, "0"), (-60, "0")):
            opener, calls = self.opener((NOW-dt.timedelta(seconds=seconds)).isoformat())
            with self.assertRaisesRegex(ValueError, "wait timer"):
                cadence.dispatch({**ENV, "MH_CADENCE_PROBE": probe}, NOW, opener)
            self.assertEqual(len(calls), 1)

    def test_forks_branches_missing_credentials_rejected_before_request(self):
        for changes in ({"GITHUB_REPOSITORY": "someone/fork"}, {"GITHUB_REF": "refs/heads/fix"},
                        {"GH_TOKEN": ""}, {"GITHUB_RUN_ID": "bad"}):
            opener, calls = self.opener()
            with self.assertRaises(ValueError): cadence.dispatch({**ENV, **changes}, NOW, opener)
            self.assertEqual(calls, [])

    def test_wrong_parent_workflow_or_branch_rejected(self):
        for changes in ({"head_branch": "fix"}, {"path": ".github/workflows/unrelated.yml"}):
            opener, calls = self.opener(**changes)
            with self.assertRaises(ValueError): cadence.dispatch(ENV, NOW, opener)
            self.assertEqual(len(calls), 1)

    def test_ambiguous_failed_post_is_not_retried_or_secret_logged(self):
        opener, calls = self.opener()
        def failing(req, timeout):
            if req.data:
                calls.append(req)
                raise HTTPError(req.full_url, 403, "synthetic", {}, io.BytesIO(b"do not log body"))
            return opener(req, timeout)
        with self.assertRaisesRegex(RuntimeError, "HTTP 403") as caught:
            cadence.dispatch(ENV, NOW, failing)
        self.assertEqual(len(calls), 2)
        self.assertNotIn("do not log body", str(caught.exception))
        self.assertNotIn(ENV["GH_TOKEN"], str(caught.exception))

    def test_workflow_delay_and_scoped_permissions_have_kill_switch(self):
        text = (Path(__file__).resolve().parents[1]/".github/workflows/scan.yml").read_text()
        self.assertIn("environment: ${{ inputs.cadence_probe", text)
        self.assertIn("permissions: { contents: read, actions: write }", text)
        self.assertIn("GH_TOKEN: ${{ github.token }}", text)
        self.assertIn("vars.MH_SCANNER_PAUSED != '1'", text)
        self.assertNotIn("sleep ", text)
        self.assertIn("scan --no-send --max-posts 0", text)
        self.assertIn('concurrency: { group: "${{ inputs.cadence_probe', text)


class NoSend(unittest.TestCase):
    def test_persisted_observations_never_route_or_acknowledge_alerts(self):
        import contextlib
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); seen = root/"seen.json"; prices = root/"prices.json"
            seen.write_text('["previous-real-delivery"]')
            with patch.object(cli, "STATE", str(seen)), patch.object(cli, "OPERATIONAL", str(root/"state.json")), \
                 patch.object(cli, "REVIEW_PATH", str(root/"review.json")), patch.object(hub, "PRICES", str(prices)), \
                 patch.object(cli, "LAST_OPERATIONAL", {"schema_version": 1, "items": {}, "ask_cache": {}}), \
                 patch.object(cli, "LAST_REVIEW", []), patch.object(cli, "LAST_RAWS", []), \
                 patch.object(cli, "run_scan", return_value=(200, config.tier_for(200), [], [], [], {"scanned": 0, "priced": 0, "affordable": 0, "A": 0, "B": 0, "R": 0, "unpriced": 0})), \
                 patch.object(cli, "ebay_status", return_value="synthetic offline"), patch.object(hub, "route") as route, \
                 patch.dict(os.environ, {"MONEYHUNTER_DISABLE_SEND": "0"}), contextlib.redirect_stdout(io.StringIO()):
                cli.cmd_scan(SimpleNamespace(no_send=True, dry_run=False, show_all=False, max_posts=0, export=None))
                self.assertEqual(os.environ["MONEYHUNTER_DISABLE_SEND"], "1")
                route.assert_not_called()
                self.assertEqual(json.loads(seen.read_text()), ["previous-real-delivery"])
                self.assertTrue((root/"state.json").exists() and (root/"review.json").exists() and prices.exists())

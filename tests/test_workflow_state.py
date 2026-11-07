"""Run proposed publication shell only against temporary local Git repositories."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

class Publication(unittest.TestCase):
    def test_manual_diagnostic_has_hard_no_send_and_no_publication(self):
        workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/scan.yml").read_text()
        self.assertIn("default: true", workflow)
        self.assertIn("MONEYHUNTER_DISABLE_SEND:", workflow)
        self.assertIn("scan --dry-run --max-posts 0", workflow)
        self.assertIn("github.event_name != 'workflow_dispatch' || !inputs.dry_run", workflow)
        self.assertIn("name: moneyhunter-no-send-research", workflow)

    def test_new_and_existing_state_use_fast_forward_history(self):
        workflow = Path(__file__).resolve().parents[1] / ".github/workflows/scan.yml"
        lines = workflow.read_text().splitlines()
        start = next(i for i, line in enumerate(lines) if "mkdir /tmp/mh-state" in line)
        script = "\n".join(line[10:] for line in lines[start:])
        with tempfile.TemporaryDirectory(prefix="state-fixture-") as td:
            root = Path(td); remote = root/"remote.git"; repo = root/"repo"
            remote.mkdir(); repo.mkdir()
            env = {**os.environ, "GITHUB_WORKSPACE": str(repo), "GIT_TERMINAL_PROMPT": "0",
                   "GIT_AUTHOR_NAME": "synthetic fixture", "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
                   "GIT_COMMITTER_NAME": "synthetic fixture", "GIT_COMMITTER_EMAIL": "fixture@example.invalid"}
            def run(args, cwd):
                p = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True)
                self.assertEqual(p.returncode, 0, p.stderr)
                return p.stdout
            run(["git", "init", "--bare", str(remote)], root)
            run(["git", "init"], repo); run(["git", "remote", "add", "origin", str(remote)], repo)
            (repo/"data").mkdir(); (repo/"public").mkdir()
            for name in ("seen.json", "prices.json", "scan_state.json", "review_queue.json", "comps.csv", "evidence.json"):
                (repo/"data"/name).write_text("synthetic fixture")
            (repo/"public"/"deals.json").write_text("synthetic fixture")
            for stage in range(2):
                state = root/f"state-{stage}"; ref = root/"state-ref"
                ref.write_text("" if stage == 0 else "existing")
                if stage: run(["git", "fetch", "origin", "state", "--depth", "1"], repo)
                adjusted = script.replace("/tmp/mh-state-ref", "@@REF@@").replace("/tmp/mh-state", str(state)).replace("@@REF@@", str(ref))
                (repo/"data"/"seen.json").write_text(f"synthetic-{stage}")
                run(["bash", "-euo", "pipefail", "-c", adjusted], repo)
            self.assertEqual(run(["git", "rev-list", "--count", "refs/heads/state"], remote).strip(), "2")

if __name__ == "__main__": unittest.main()

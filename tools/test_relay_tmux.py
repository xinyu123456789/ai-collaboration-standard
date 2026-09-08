"""Real tmux smoke test for Relay; run explicitly, not as a routine unit test."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

import relay


def _run(argv: list[str], cwd: Path | None = None) -> str:
    result = subprocess.run(
        argv,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


class RealTmuxSmokeTest(unittest.TestCase):
    @unittest.skipUnless(
        os.environ.get("RELAY_RUN_TMUX_SMOKE") == "1",
        "set RELAY_RUN_TMUX_SMOKE=1 to run the real tmux smoke test",
    )
    def test_start_review_claim_and_idle_across_real_panes(self) -> None:
        session = f"relay-smoke-{uuid4().hex[:10]}"
        _run(["tmux", "new-session", "-d", "-s", session, "-n", "agents"])
        try:
            _run(["tmux", "split-window", "-h", "-t", f"{session}:agents"])
            engineer_target = f"{session}:agents.0"
            checker_target = f"{session}:agents.1"
            engineer_pane = _run(
                [
                    "tmux",
                    "display-message",
                    "-p",
                    "-t",
                    engineer_target,
                    "#{pane_id}",
                ]
            )
            checker_pane = _run(
                [
                    "tmux",
                    "display-message",
                    "-p",
                    "-t",
                    checker_target,
                    "#{pane_id}",
                ]
            )

            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                _run(["git", "init", "-b", "work"], root)
                _run(["git", "config", "user.name", "Relay Smoke"], root)
                _run(
                    ["git", "config", "user.email", "relay@example.invalid"],
                    root,
                )
                (root / ".gitignore").write_text(
                    "/docs/ai-collaboration/relay.toml\n"
                    "/docs/ai-collaboration/WORK_PLAN.local.md\n"
                    "/.relay/\n",
                    encoding="utf-8",
                )
                (root / "app.txt").write_text("base\n", encoding="utf-8")
                _run(["git", "add", ".gitignore", "app.txt"], root)
                _run(["git", "commit", "-m", "base"], root)
                config = root / "docs" / "ai-collaboration" / "relay.toml"
                config.parent.mkdir(parents=True)
                config.write_text(
                    'schema_version = "relay-config/v2"\n'
                    'branch = "work"\n'
                    "[agents.engineer]\n"
                    f'target = "{engineer_target}"\n'
                    'transport = "tmux_keys"\n'
                    "[agents.checker]\n"
                    f'target = "{checker_target}"\n'
                    'transport = "tmux_keys"\n',
                    encoding="utf-8",
                )

                relay.initialize(root)
                os.environ["TMUX_PANE"] = checker_pane
                work_message = relay.start_round(root, "SMOKE-01")
                engineer_output = _run(
                    [
                        "tmux",
                        "capture-pane",
                        "-pJ",
                        "-t",
                        engineer_target,
                        "-S",
                        "-20",
                    ]
                )
                self.assertIn(work_message, engineer_output)

                os.environ["TMUX_PANE"] = engineer_pane
                relay.claim_event(root, work_message.split()[-1])
                (root / "app.txt").write_text("implemented\n", encoding="utf-8")
                _run(["git", "add", "app.txt"], root)
                _run(["git", "commit", "-m", "implementation"], root)
                review_message = relay.handoff_review(root)
                checker_output = _run(
                    [
                        "tmux",
                        "capture-pane",
                        "-pJ",
                        "-t",
                        checker_target,
                        "-S",
                        "-20",
                    ]
                )
                self.assertIn(review_message, checker_output)

                os.environ["TMUX_PANE"] = checker_pane
                relay.claim_event(root, review_message.split()[-1])
                self.assertEqual(
                    relay.accept_checkpoint(root, next_round=None, idle=True),
                    "ACCEPT CP001 IDLE",
                )
                self.assertIn("status=idle", relay.show_status(root))
                self.assertEqual(_run(["git", "status", "--porcelain=v1"], root), "")
        finally:
            _run(["tmux", "kill-session", "-t", session])


if __name__ == "__main__":
    unittest.main()

"""Focused tests for the local Relay state machine."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import relay


class RelayTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self._git("init", "-b", "work")
        self._git("config", "user.name", "Relay Test")
        self._git("config", "user.email", "relay@example.invalid")
        (self.root / ".gitignore").write_text(
            "/docs/ai-collaboration/relay.toml\n"
            "/docs/ai-collaboration/WORK_PLAN.local.md\n"
            "/.relay/\n",
            encoding="utf-8",
        )
        (self.root / "app.txt").write_text("base\n", encoding="utf-8")
        self._git("add", ".gitignore", "app.txt")
        self._git("commit", "-m", "base")
        self._write_owner_config()

        self.tmux_calls: list[tuple[tuple[str, ...], str | None]] = []
        self.fail_next_paste = False
        self.tmux_patch = mock.patch.object(relay, "_tmux", side_effect=self._fake_tmux)
        self.tmux_patch.start()
        self.addCleanup(self.tmux_patch.stop)
        self.codex_calls: list[tuple[str, str]] = []
        self.codex_patch = mock.patch.object(
            relay,
            "_codex_queue",
            side_effect=lambda thread, message: self.codex_calls.append((thread, message)),
        )
        self.codex_patch.start()
        self.addCleanup(self.codex_patch.stop)
        self.environment = mock.patch.dict(os.environ, {"TMUX_PANE": "%2"})
        self.environment.start()
        self.addCleanup(self.environment.stop)

        relay.initialize(self.root)

    def _git(self, *args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=self.root,
            text=True,
            capture_output=True,
            check=True,
        )
        return result.stdout.strip()

    def _fake_tmux(self, *args: str, input_text: str | None = None) -> str:
        self.tmux_calls.append((args, input_text))
        if args[0] == "display-message":
            target = args[args.index("-t") + 1]
            panes = {
                "relay:0.0": "%1",
                "relay:0.1": "%2",
                "%1": "%1",
                "%2": "%2",
            }
            if target not in panes:
                raise relay.RelayError("missing pane")
            return panes[target]
        if args[0] == "paste-buffer" and self.fail_next_paste:
            self.fail_next_paste = False
            raise relay.RelayError("simulated paste failure")
        return ""

    def _write_owner_config(
        self,
        engineer: str = "relay:0.0",
        checker: str = "relay:0.1",
        checker_transport: str = "tmux_keys",
        checker_thread: str | None = None,
    ) -> None:
        path = self.root / "docs" / "ai-collaboration" / "relay.toml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join(
                (
                    'schema_version = "relay-config/v2"',
                    'branch = "work"',
                    "",
                    "[agents.engineer]",
                    f'target = "{engineer}"',
                    'transport = "tmux_keys"',
                    "",
                    "[agents.checker]",
                    f'target = "{checker}"',
                    f'transport = "{checker_transport}"',
                    *((f'thread = "{checker_thread}"',) if checker_thread is not None else ()),
                    "",
                )
            ),
            encoding="utf-8",
        )

    def _role(self, role: str) -> None:
        os.environ["TMUX_PANE"] = "%1" if role == "engineer" else "%2"

    def _delivery_call_count(self) -> int:
        return sum(args[0] == "load-buffer" for args, _input in self.tmux_calls)

    def _commit(self, text: str, message: str, path: str = "app.txt") -> str:
        destination = self.root / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text, encoding="utf-8")
        self._git("add", path)
        self._git("commit", "-m", message)
        return self._git("rev-parse", "HEAD")

    def _start_and_claim(self, work_round: str = "EXAMPLE-R130A") -> str:
        self._role("checker")
        message = relay.start_round(self.root, work_round)
        event_id = message.split()[-1]
        self._role("engineer")
        self.assertEqual(relay.claim_event(self.root, event_id), f"CLAIMED {event_id}")
        return event_id

    def _review_and_claim(self, text: str, message: str) -> str:
        self._role("engineer")
        self._commit(text, message)
        handoff = relay.handoff_review(self.root)
        event_id = handoff.split()[-1]
        self._role("checker")
        relay.claim_event(self.root, event_id)
        return event_id

    def _checkpoint(self, checkpoint_id: str = "CP001") -> dict[str, object]:
        return relay._load_checkpoint(self.root, checkpoint_id)

    def test_initial_state_is_idle_and_local_files_are_ignored(self) -> None:
        status = relay.show_status(self.root)
        self.assertIn("status=idle", status)
        self.assertEqual(self._git("status", "--porcelain=v1"), "")
        self.assertTrue((self.root / ".relay" / "state.json").exists())

    def test_checker_updates_ignored_plan_and_scans_gate_before_accept(self) -> None:
        plan = self.root / "docs" / "ai-collaboration" / "WORK_PLAN.local.md"
        plan.write_text(
            "## Phase 1\n- [ ] **WORK-001** — pending\n- [ ] **PHASE-GATE-01** — gate\n",
            encoding="utf-8",
        )
        self._start_and_claim("WORK-001")
        self._review_and_claim("complete\n", "complete implementation")
        plan.write_text(
            "## Phase 1\n- [x] **WORK-001** — complete\n- [ ] **PHASE-GATE-01** — gate\n",
            encoding="utf-8",
        )

        self.assertIn("status=review", relay.show_status(self.root))
        self.assertEqual(self._git("status", "--porcelain=v1"), "")
        self.assertEqual(
            relay.scan_unfinished_work(self.root, plan, "PHASE-GATE-01"),
            "WORK_SCAN_PASS gate=PHASE-GATE-01 checked=1 "
            "plan=docs/ai-collaboration/WORK_PLAN.local.md",
        )
        plan.write_text(
            "## Phase 1\n- [x] **WORK-001** — complete\n- [x] **PHASE-GATE-01** — passed\n",
            encoding="utf-8",
        )

        self.assertEqual(
            relay.accept_checkpoint(self.root, next_round=None, idle=True),
            "ACCEPT CP001 IDLE",
        )
        self.assertIn("status=idle", relay.show_status(self.root))

    def test_codex_delivery_uses_session_queue_instead_of_tmux_keys(self) -> None:
        self._write_owner_config(
            checker_transport="codex_queue",
            checker_thread="checker-session",
        )
        config = relay._load_config(self.root)

        relay._deliver(config, "checker", "REVIEW CP001 EV0002")

        self.assertEqual(
            self.codex_calls,
            [("checker-session", "REVIEW CP001 EV0002")],
        )
        self.assertFalse(any(args[0] == "load-buffer" for args, _input in self.tmux_calls))

    def test_owner_config_rejects_unknown_agent_roles(self) -> None:
        path = self.root / "docs" / "ai-collaboration" / "relay.toml"
        path.write_text(
            path.read_text(encoding="utf-8")
            + "[agents.observer]\n"
            + 'target = "relay:0.2"\n'
            + 'transport = "tmux_keys"\n',
            encoding="utf-8",
        )

        with self.assertRaisesRegex(relay.RelayError, "unknown agent roles: observer"):
            relay._load_config(self.root)

    def test_owner_config_rejects_unknown_top_level_fields(self) -> None:
        path = self.root / "docs" / "ai-collaboration" / "relay.toml"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                'branch = "work"\n',
                'branch = "work"\nproject = "not-a-supported-field"\n',
                1,
            ),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(relay.RelayError, "unknown top-level fields: project"):
            relay._load_config(self.root)

    def test_complete_review_revision_and_next_round_flow(self) -> None:
        self._start_and_claim()
        self._review_and_claim("first\n", "first implementation")

        finding = relay.add_finding(
            self.root,
            location="src/auth/token.py:84",
            problem="concurrent requests can validate the same token",
            finding_id=None,
        )
        self.assertEqual(finding, "F001")
        revise_message = relay.request_revision(self.root)
        self._role("engineer")
        relay.claim_event(self.root, revise_message.split()[-1])
        with self.assertRaisesRegex(relay.RelayError, "checker owns"):
            relay.complete_findings(self.root, ["F001"])

        self._review_and_claim("second\n", "first revision")
        self.assertEqual(self._checkpoint()["open_findings"], ["F001"])
        repeated = relay.add_finding(
            self.root,
            location="src/auth/token.py:91",
            problem="replacement remains outside the critical section",
            finding_id="F001",
        )
        self.assertEqual(repeated, "F001")
        revise_message = relay.request_revision(self.root)
        self._role("engineer")
        relay.claim_event(self.root, revise_message.split()[-1])

        self._role("engineer")
        self._commit("third\n", "second revision")
        self._commit("proof\n", "revision proof", "proof.txt")
        review_message = relay.handoff_review(self.root)
        self._role("checker")
        relay.claim_event(self.root, review_message.split()[-1])
        with self.assertRaisesRegex(relay.RelayError, "must be completed"):
            relay.accept_checkpoint(self.root, next_round="EXAMPLE-R130C", idle=False)
        self.assertEqual(
            relay.complete_findings(self.root, ["F001"]),
            "COMPLETED F001",
        )
        accepted = relay.accept_checkpoint(
            self.root,
            next_round="EXAMPLE-R130C",
            idle=False,
        )

        self.assertIn("ACCEPT CP001 WORK EXAMPLE-R130C CP002", accepted)
        checkpoint = self._checkpoint()
        self.assertEqual(checkpoint["status"], "accepted")
        self.assertEqual(len(checkpoint["reviews"]), 3)
        self.assertEqual(len(checkpoint["revises"]), 2)
        self.assertEqual(
            checkpoint["reviews"][0]["findings"][0]["id"],
            checkpoint["reviews"][1]["findings"][0]["id"],
        )
        self.assertEqual(
            checkpoint["reviews"][0]["findings"][0]["status"],
            "completed",
        )
        self.assertEqual(
            checkpoint["reviews"][1]["findings"][0]["status"],
            "completed",
        )
        self.assertEqual(checkpoint["open_findings"], [])
        self.assertEqual(len(checkpoint["revises"][1]["commits"]), 2)
        next_checkpoint = self._checkpoint("CP002")
        self.assertEqual(next_checkpoint["work_round"], "EXAMPLE-R130C")
        self.assertEqual(next_checkpoint["status"], "engineering")

    def test_accept_idle_does_not_send_new_work(self) -> None:
        self._start_and_claim()
        self._review_and_claim("done\n", "implementation")
        calls_before = self._delivery_call_count()
        result = relay.accept_checkpoint(self.root, next_round=None, idle=True)
        self.assertEqual(result, "ACCEPT CP001 IDLE")
        self.assertEqual(self._delivery_call_count(), calls_before)
        self.assertIn("status=idle", relay.show_status(self.root))

    def test_owner_hold_from_revision_restores_revision_state(self) -> None:
        self._start_and_claim()
        self._review_and_claim("first\n", "implementation")
        relay.add_finding(
            self.root,
            location="app.txt:1",
            problem="the result is incomplete",
            finding_id=None,
        )
        revise_message = relay.request_revision(self.root)
        self._role("engineer")
        relay.claim_event(self.root, revise_message.split()[-1])

        private_reason = "the specification has two valid readings"
        hold_message = relay.owner_hold(self.root, private_reason)
        pasted_messages = [
            input_text for args, input_text in self.tmux_calls if args[0] == "load-buffer"
        ]
        self.assertFalse(any(private_reason in (message or "") for message in pasted_messages))
        self._role("checker")
        relay.claim_event(self.root, hold_message.split()[-1])
        resume_message = relay.resume_from_hold(
            self.root,
            "use the existing public contract",
            "engineer",
        )
        self._role("engineer")
        relay.claim_event(self.root, resume_message.split()[-1])

        checkpoint = self._checkpoint()
        self.assertEqual(checkpoint["status"], "revise")
        self.assertEqual(checkpoint["holds"][0]["decision"], "use the existing public contract")

    def test_checker_hold_can_resume_to_same_review_without_delivery(self) -> None:
        self._start_and_claim()
        self._review_and_claim("first\n", "implementation")
        calls_before = self._delivery_call_count()
        self.assertEqual(
            relay.owner_hold(self.root, "acceptance is ambiguous"),
            "OWNER_HOLD CP001",
        )
        self.assertEqual(self._delivery_call_count(), calls_before)
        self.assertEqual(
            relay.resume_from_hold(self.root, "apply the stricter reading", "checker"),
            "RESUME CP001 CHECKER",
        )
        self.assertEqual(self._checkpoint()["status"], "review")

    def test_engineering_hold_cannot_resume_directly_to_checker(self) -> None:
        self._start_and_claim()
        hold_message = relay.owner_hold(self.root, "implementation needs an Owner decision")
        self._role("checker")
        relay.claim_event(self.root, hold_message.split()[-1])

        with self.assertRaisesRegex(relay.RelayError, "must resume to the Engineer"):
            relay.resume_from_hold(self.root, "continue implementation", "checker")

        checkpoint = self._checkpoint()
        self.assertEqual(checkpoint["status"], "owner_hold")
        self.assertIsNone(checkpoint["holds"][-1]["decision"])

    def test_checker_hold_with_findings_can_resume_to_engineer(self) -> None:
        """The Owner decision must not orphan findings drafted before the hold."""
        self._start_and_claim()
        self._review_and_claim("first\n", "implementation")
        self.assertEqual(
            relay.add_finding(
                self.root,
                location="app.txt:1",
                problem="the approved contract still needs implementation",
                finding_id=None,
            ),
            "F001",
        )
        self.assertEqual(
            relay.owner_hold(self.root, "the public path needs Owner approval"),
            "OWNER_HOLD CP001",
        )

        resume_message = relay.resume_from_hold(
            self.root,
            "approve the proposed public path",
            "engineer",
        )
        checkpoint = self._checkpoint()
        self.assertEqual(checkpoint["status"], "revise")
        self.assertEqual(checkpoint["draft_findings"], [])
        self.assertEqual(checkpoint["reviews"][0]["result"], "revise")
        self.assertEqual(checkpoint["reviews"][0]["findings"][0]["id"], "F001")

        self._role("engineer")
        relay.claim_event(self.root, resume_message.split()[-1])
        self._commit("second\n", "owner-approved revision")
        review_message = relay.handoff_review(self.root)
        self._role("checker")
        relay.claim_event(self.root, review_message.split()[-1])
        self.assertEqual(relay.complete_findings(self.root, ["F001"]), "COMPLETED F001")

    def test_owner_can_cancel_untouched_assignment_and_select_next_round(self) -> None:
        self._start_and_claim("EXAMPLE-R147A")
        self._role("engineer")
        hold_message = relay.owner_hold(self.root, "the wrong round was assigned")
        self._role("checker")
        relay.claim_event(self.root, hold_message.split()[-1])

        private_decision = "cancel the mistaken assignment and return to the incomplete phase"
        cancellation = relay.cancel_checkpoint(
            self.root,
            decision=private_decision,
            next_round="EXAMPLE-R132A2",
            idle=False,
        )

        self.assertIn("CANCEL CP001 WORK EXAMPLE-R132A2 CP002", cancellation)
        cancelled = self._checkpoint("CP001")
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertEqual(cancelled["holds"][0]["decision"], private_decision)
        self.assertEqual(cancelled["holds"][0]["resolved_as"], "cancelled")
        self.assertEqual(cancelled["holds"][0]["next_round"], "EXAMPLE-R132A2")
        replacement = self._checkpoint("CP002")
        self.assertEqual(replacement["work_round"], "EXAMPLE-R132A2")
        self.assertEqual(replacement["status"], "engineering")
        self.assertEqual(replacement["base"], cancelled["base"])
        pasted_messages = [
            input_text for args, input_text in self.tmux_calls if args[0] == "load-buffer"
        ]
        self.assertFalse(any(private_decision in (message or "") for message in pasted_messages))

    def test_owner_can_defer_reviewed_dependency_and_select_next_round(self) -> None:
        self._start_and_claim("EXAMPLE-R213")
        self._review_and_claim("partial evidence\n", "partial acceptance evidence")
        relay.add_finding(
            self.root,
            location="tests/acceptance.py:50",
            problem="the production dependency is unavailable",
            finding_id=None,
        )
        revise_message = relay.request_revision(self.root)
        self._role("engineer")
        relay.claim_event(self.root, revise_message.split()[-1])
        hold_message = relay.owner_hold(self.root, "the production adapter belongs to another team")
        self._role("checker")
        relay.claim_event(self.root, hold_message.split()[-1])

        private_decision = "defer the round and keep its work-plan item unchecked"
        deferred_message = relay.defer_checkpoint(
            self.root,
            decision=private_decision,
            next_round="EXAMPLE-R214A",
        )

        self.assertIn("DEFER CP001 WORK EXAMPLE-R214A CP002", deferred_message)
        deferred = self._checkpoint("CP001")
        self.assertEqual(deferred["status"], "deferred")
        self.assertEqual(deferred["open_findings"], ["F001"])
        self.assertEqual(deferred["holds"][0]["decision"], private_decision)
        self.assertEqual(deferred["holds"][0]["resolved_as"], "deferred")
        replacement = self._checkpoint("CP002")
        self.assertEqual(replacement["work_round"], "EXAMPLE-R214A")
        self.assertEqual(replacement["base"], deferred["head"])
        state = relay._load_json(relay._state_path(self.root), "state")
        self.assertEqual(state["last_accepted"], deferred["head"])
        pasted_messages = [
            input_text for args, input_text in self.tmux_calls if args[0] == "load-buffer"
        ]
        self.assertFalse(any(private_decision in (message or "") for message in pasted_messages))

    def test_checker_can_resume_and_accept_a_deferred_checkpoint(self) -> None:
        self._start_and_claim("WORK-BLOCKED")
        self._review_and_claim("partial evidence\n", "partial implementation")
        relay.add_finding(
            self.root,
            location="app.txt:1",
            problem="the external dependency is unavailable",
            finding_id=None,
        )
        self.assertEqual(relay.owner_hold(self.root, "dependency unavailable"), "OWNER_HOLD CP001")
        next_message = relay.defer_checkpoint(
            self.root,
            decision="continue independent work first",
            next_round="WORK-INDEPENDENT",
        )
        self._role("engineer")
        relay.claim_event(self.root, next_message.split()[-1])
        self._commit("independent\n", "independent implementation")
        review_message = relay.handoff_review(self.root)
        self._role("checker")
        relay.claim_event(self.root, review_message.split()[-1])
        self.assertEqual(
            relay.accept_checkpoint(self.root, next_round=None, idle=True),
            "ACCEPT CP002 IDLE",
        )

        resume_message = relay.resume_deferred_checkpoint(
            self.root,
            "CP001",
            "the dependency is now available",
        )
        self.assertIn("RESUME_DEFERRED CP001 WORK WORK-BLOCKED", resume_message)
        resumed = self._checkpoint("CP001")
        self.assertEqual(resumed["status"], "revise")
        self.assertEqual(len(resumed["deferred_resumptions"]), 1)

        self._role("engineer")
        relay.claim_event(self.root, resume_message.split()[-1])
        self._commit("complete\n", "complete deferred implementation")
        review_message = relay.handoff_review(self.root)
        self._role("checker")
        relay.claim_event(self.root, review_message.split()[-1])
        self.assertEqual(relay.complete_findings(self.root, ["F001"]), "COMPLETED F001")
        self.assertEqual(
            relay.accept_checkpoint(self.root, next_round=None, idle=True),
            "ACCEPT CP001 IDLE",
        )
        self.assertEqual(self._checkpoint("CP001")["status"], "accepted")

    def test_deferred_checkpoint_requires_idle_and_owner_decision(self) -> None:
        self._start_and_claim("WORK-ACTIVE")
        self._role("checker")
        with self.assertRaisesRegex(relay.RelayError, "only while Relay is idle"):
            relay.resume_deferred_checkpoint(self.root, "CP001", "dependency ready")

    def test_defer_requires_an_open_finding(self) -> None:
        self._start_and_claim("EXAMPLE-R213")
        self._review_and_claim("complete evidence\n", "complete acceptance evidence")
        self.assertEqual(
            relay.owner_hold(self.root, "the Owner requested a scheduling change"),
            "OWNER_HOLD CP001",
        )

        with self.assertRaisesRegex(relay.RelayError, "open finding"):
            relay.defer_checkpoint(
                self.root,
                decision="defer it",
                next_round="EXAMPLE-R214A",
            )

    def test_cancel_refuses_dirty_or_already_reviewed_work(self) -> None:
        self._start_and_claim()
        self._role("engineer")
        hold_message = relay.owner_hold(self.root, "the wrong round was assigned")
        self._role("checker")
        relay.claim_event(self.root, hold_message.split()[-1])
        (self.root / "draft.txt").write_text("not accepted\n", encoding="utf-8")

        with self.assertRaisesRegex(relay.RelayError, "not clean"):
            relay.cancel_checkpoint(
                self.root,
                decision="cancel it",
                next_round=None,
                idle=True,
            )

        (self.root / "draft.txt").unlink()
        checkpoint = self._checkpoint()
        checkpoint["reviews"].append(
            {
                "head": checkpoint["head"],
                "result": "revise",
                "findings": [],
                "created_at": relay._now(),
            }
        )
        relay._save_checkpoint(self.root, checkpoint)
        with self.assertRaisesRegex(relay.RelayError, "review history"):
            relay.cancel_checkpoint(
                self.root,
                decision="cancel it",
                next_round=None,
                idle=True,
            )

    def test_only_checker_can_cancel_and_only_during_owner_hold(self) -> None:
        self._start_and_claim()
        self._role("engineer")
        with self.assertRaisesRegex(relay.RelayError, "checker owns"):
            relay.cancel_checkpoint(
                self.root,
                decision="cancel it",
                next_round=None,
                idle=True,
            )

        self._role("checker")
        checkpoint = self._checkpoint()
        checkpoint["status"] = "review"
        relay._save_checkpoint(self.root, checkpoint)
        with self.assertRaisesRegex(relay.RelayError, "active owner hold"):
            relay.cancel_checkpoint(
                self.root,
                decision="cancel it",
                next_round=None,
                idle=True,
            )

    def test_failed_delivery_can_be_retried_and_claimed_once(self) -> None:
        self._role("checker")
        self.fail_next_paste = True
        with self.assertRaisesRegex(relay.RelayError, "pending delivery"):
            relay.start_round(self.root, "EXAMPLE-R130A")
        state = relay._load_json(relay._state_path(self.root), "state")
        event_id = state["pending_delivery"]["id"]
        with self.assertRaisesRegex(relay.RelayError, "claimed or retried"):
            relay.owner_hold(self.root, "delivery target is unavailable")
        retried = relay.retry_delivery(self.root)
        self.assertTrue(retried.endswith(event_id))

        self._role("engineer")
        self.assertEqual(relay.claim_event(self.root, event_id), f"CLAIMED {event_id}")
        self.assertEqual(
            relay.claim_event(self.root, event_id),
            f"ALREADY_CLAIMED {event_id}",
        )

    def test_wrong_role_cannot_start_or_claim(self) -> None:
        self._role("engineer")
        with self.assertRaisesRegex(relay.RelayError, "checker owns"):
            relay.start_round(self.root, "EXAMPLE-R130A")
        self._role("checker")
        message = relay.start_round(self.root, "EXAMPLE-R130A")
        with self.assertRaisesRegex(relay.RelayError, "other role"):
            relay.claim_event(self.root, message.split()[-1])

    def test_missing_other_pane_does_not_hide_current_role(self) -> None:
        config_path = self.root / "docs" / "ai-collaboration" / "relay.toml"
        config_path.write_text(
            config_path.read_text(encoding="utf-8").replace(
                'target = "relay:0.0"',
                'target = "missing:9.9"',
                1,
            ),
            encoding="utf-8",
        )
        self._role("checker")

        role = relay._current_role(relay._load_config(self.root))

        self.assertEqual(role, "checker")

    def test_review_rejects_dirty_worktree_and_missing_commit(self) -> None:
        self._start_and_claim()
        with self.assertRaisesRegex(relay.RelayError, "new commit"):
            relay.handoff_review(self.root)
        (self.root / "app.txt").write_text("dirty\n", encoding="utf-8")
        with self.assertRaisesRegex(relay.RelayError, "not clean"):
            relay.handoff_review(self.root)

    def test_unclaimed_event_blocks_the_next_transition(self) -> None:
        self._role("checker")
        message = relay.start_round(self.root, "EXAMPLE-R130A")
        self._role("engineer")
        with self.assertRaisesRegex(relay.RelayError, "must be claimed"):
            relay.handoff_review(self.root)
        relay.claim_event(self.root, message.split()[-1])

    def test_finding_text_is_never_pasted_into_tmux(self) -> None:
        self._start_and_claim()
        self._review_and_claim("first\n", "implementation")
        private_problem = "a sensitive implementation detail remains incorrect"
        relay.add_finding(
            self.root,
            location="app.txt:1",
            problem=private_problem,
            finding_id=None,
        )
        message = relay.request_revision(self.root)
        self.assertTrue(message.startswith("REVISE CP001 EV"))
        pasted_messages = [
            input_text for args, input_text in self.tmux_calls if args[0] == "load-buffer"
        ]
        self.assertFalse(any(private_problem in (pasted or "") for pasted in pasted_messages))

    def test_checker_rejects_head_changed_after_handoff(self) -> None:
        self._start_and_claim()
        self._review_and_claim("first\n", "implementation")
        self._commit("changed\n", "unexpected checker-side commit")
        with self.assertRaisesRegex(relay.RelayError, "HEAD changed"):
            relay.accept_checkpoint(self.root, next_round=None, idle=True)

    def test_interrupted_acceptance_replays_to_a_consistent_idle_state(self) -> None:
        self._start_and_claim()
        self._review_and_claim("complete\n", "complete implementation")

        with (
            mock.patch.object(relay, "_save_state", side_effect=OSError("interrupted write")),
            self.assertRaisesRegex(OSError, "interrupted write"),
        ):
            relay.accept_checkpoint(self.root, next_round=None, idle=True)

        self.assertTrue(relay._transition_path(self.root).exists())
        self.assertIn("status=idle", relay.show_status(self.root))
        self.assertFalse(relay._transition_path(self.root).exists())
        self.assertEqual(self._checkpoint("CP001")["status"], "accepted")

    def test_interrupted_review_handoff_recovers_the_pending_event(self) -> None:
        self._start_and_claim()
        self._commit("ready\n", "implementation")
        self._role("engineer")

        with (
            mock.patch.object(relay, "_save_state", side_effect=OSError("interrupted write")),
            self.assertRaisesRegex(OSError, "interrupted write"),
        ):
            relay.handoff_review(self.root)

        status = relay.show_status(self.root)
        self.assertIn("status=review", status)
        self.assertIn("pending=EV0002", status)
        self.assertEqual(relay.retry_delivery(self.root), "REVIEW CP001 EV0002")

    def test_checker_recovers_owner_approved_descendant_while_idle(self) -> None:
        self._role("checker")
        state = relay._load_json(relay._state_path(self.root), "state")
        previous_head = state["last_accepted"]
        adopted_head = self._commit("owner integration\n", "owner-approved integration")

        result = relay.adopt_idle_head(self.root, "owner approved integration between rounds")

        self.assertEqual(result, f"ADOPT_IDLE_HEAD {adopted_head}")
        state = relay._load_json(relay._state_path(self.root), "state")
        self.assertEqual(state["last_accepted"], adopted_head)
        self.assertEqual(
            state["idle_head_adoptions"],
            [
                {
                    "previous_head": previous_head,
                    "head": adopted_head,
                    "decision": "owner approved integration between rounds",
                    "created_at": state["idle_head_adoptions"][0]["created_at"],
                }
            ],
        )
        message = relay.start_round(self.root, "EXAMPLE-FIX-109")
        self.assertIn("WORK EXAMPLE-FIX-109 CP001", message)
        self.assertEqual(self._checkpoint()["base"], adopted_head)

    def test_idle_head_recovery_requires_checker_idle_and_new_head(self) -> None:
        self._role("checker")
        with self.assertRaisesRegex(relay.RelayError, "already matches"):
            relay.adopt_idle_head(self.root, "owner approved")

        self._commit("owner integration\n", "owner-approved integration")
        self._role("engineer")
        with self.assertRaisesRegex(relay.RelayError, "checker owns this command"):
            relay.adopt_idle_head(self.root, "owner approved")

        self._role("checker")
        relay.adopt_idle_head(self.root, "owner approved")
        message = relay.start_round(self.root, "EXAMPLE-FIX-109")
        self._role("engineer")
        relay.claim_event(self.root, message.split()[-1])
        self._role("checker")
        with self.assertRaisesRegex(relay.RelayError, "requires Relay to be idle"):
            relay.adopt_idle_head(self.root, "owner approved again")

    def test_idle_head_recovery_rejects_dirty_or_divergent_git(self) -> None:
        self._role("checker")
        self._commit("owner integration\n", "owner-approved integration")
        (self.root / "app.txt").write_text("dirty\n", encoding="utf-8")
        with self.assertRaisesRegex(relay.RelayError, "worktree is not clean"):
            relay.adopt_idle_head(self.root, "owner approved")

        self._git("restore", "app.txt")
        tree = self._git("rev-parse", "HEAD^{tree}")
        unrelated = self._git("commit-tree", tree, "-m", "unrelated history")
        self._git("reset", "--hard", unrelated)
        with self.assertRaisesRegex(relay.RelayError, "must descend"):
            relay.adopt_idle_head(self.root, "owner approved")

    def test_review_rejects_detached_head(self) -> None:
        self._start_and_claim()
        self._git("switch", "--detach")
        with self.assertRaisesRegex(relay.RelayError, "detached HEAD"):
            relay.handoff_review(self.root)

    def test_review_rejects_merge_commit(self) -> None:
        self._start_and_claim()
        base = self._git("rev-parse", "HEAD")
        self._git("switch", "-c", "feature")
        self._commit("feature\n", "feature", "feature.txt")
        self._git("switch", "work")
        self._commit("main\n", "main", "main.txt")
        self._git("merge", "--no-ff", "feature", "-m", "merge feature")
        self.assertNotEqual(self._git("rev-parse", "HEAD"), base)
        with self.assertRaisesRegex(relay.RelayError, "merge commits"):
            relay.handoff_review(self.root)

    def test_review_rejects_divergent_history_on_the_same_branch(self) -> None:
        self._start_and_claim()
        tree = self._git("write-tree")
        replacement = self._git("commit-tree", tree, "-m", "replacement root")
        self._git("update-ref", "refs/heads/work", replacement)
        self.assertEqual(self._git("status", "--porcelain=v1"), "")
        with self.assertRaisesRegex(relay.RelayError, "not a descendant"):
            relay.handoff_review(self.root)

    def test_unknown_or_duplicate_finding_is_rejected(self) -> None:
        self._start_and_claim()
        self._review_and_claim("first\n", "implementation")
        with self.assertRaisesRegex(relay.RelayError, "does not exist"):
            relay.add_finding(
                self.root,
                location="app.txt:1",
                problem="unknown issue",
                finding_id="F999",
            )
        relay.add_finding(
            self.root,
            location="app.txt:1",
            problem="known issue",
            finding_id=None,
        )
        with self.assertRaisesRegex(relay.RelayError, "already present"):
            relay.add_finding(
                self.root,
                location="app.txt:2",
                problem="duplicate entry",
                finding_id="F001",
            )

    def test_legacy_review_keeps_latest_revision_finding_open(self) -> None:
        """Old Relay cleared open_findings before Checker verification."""
        self._start_and_claim()
        self._review_and_claim("first\n", "implementation")
        relay.add_finding(
            self.root,
            location="app.txt:1",
            problem="known issue",
            finding_id=None,
        )
        revise_message = relay.request_revision(self.root)
        self._role("engineer")
        relay.claim_event(self.root, revise_message.split()[-1])
        self._commit("fixed\n", "revision")

        checkpoint = self._checkpoint()
        checkpoint["status"] = "review"
        checkpoint["head"] = self._git("rev-parse", "HEAD")
        checkpoint["revises"].append({"findings": ["F001"], "commits": [checkpoint["head"]]})
        checkpoint["open_findings"] = []
        checkpoint["reviews"][0]["findings"][0].pop("status")
        relay._save_checkpoint(self.root, checkpoint)

        migrated = self._checkpoint()
        self.assertEqual(migrated["reviews"][0]["findings"][0]["status"], "open")

    def test_invalid_work_round_is_rejected(self) -> None:
        self._role("checker")
        with self.assertRaisesRegex(relay.RelayError, "work-round ID"):
            relay.start_round(self.root, "bad round")

    def test_phase_gate_cannot_be_dispatched_to_engineer(self) -> None:
        self._role("checker")
        with self.assertRaisesRegex(relay.RelayError, "checker-owned"):
            relay.start_round(self.root, "PHASE-GATE-009")
        self.assertIn("status=idle", relay.show_status(self.root))

        self._start_and_claim("EXAMPLE-R168B")
        self._review_and_claim("ready\n", "last engineering round")
        with self.assertRaisesRegex(relay.RelayError, "checker-owned"):
            relay.accept_checkpoint(
                self.root,
                next_round="PHASE-GATE-009",
                idle=False,
            )

        checkpoint = self._checkpoint()
        self.assertEqual(checkpoint["status"], "review")
        self.assertEqual(checkpoint["work_round"], "EXAMPLE-R168B")

    def test_corrupt_state_fails_closed(self) -> None:
        state = relay._load_json(relay._state_path(self.root), "state")
        state["next_event"] = "four"
        relay._atomic_write_json(relay._state_path(self.root), state)
        with self.assertRaisesRegex(relay.RelayError, "invalid next_event"):
            relay.show_status(self.root)

    def test_corrupt_transition_fails_closed(self) -> None:
        relay._atomic_write_json(
            relay._transition_path(self.root),
            {"schema_version": relay.TRANSITION_SCHEMA_VERSION, "state": "invalid"},
        )

        with self.assertRaisesRegex(relay.RelayError, "transition is invalid"):
            relay.show_status(self.root)

    def test_corrupt_checkpoint_fails_closed(self) -> None:
        self._role("checker")
        relay.start_round(self.root, "EXAMPLE-R130A")
        checkpoint = relay._load_json(
            relay._checkpoint_path(self.root, "CP001"),
            "checkpoint",
        )
        checkpoint["status"] = "surprise"
        relay._atomic_write_json(
            relay._checkpoint_path(self.root, "CP001"),
            checkpoint,
        )
        with self.assertRaisesRegex(relay.RelayError, "invalid status"):
            relay.show_checkpoint(self.root, "CP001")


class InitializationTestCase(unittest.TestCase):
    def test_init_requires_relay_to_be_git_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(
                ["git", "init", "-b", "work"],
                cwd=root,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Relay Test"],
                cwd=root,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.email", "relay@example.invalid"],
                cwd=root,
                check=True,
            )
            (root / ".gitignore").write_text(
                "/docs/ai-collaboration/relay.toml\n",
                encoding="utf-8",
            )
            (root / "app.txt").write_text("base\n", encoding="utf-8")
            config = root / "docs" / "ai-collaboration" / "relay.toml"
            config.parent.mkdir(parents=True)
            config.write_text(
                'schema_version = "relay-config/v2"\n'
                'branch = "work"\n'
                "[agents.engineer]\n"
                'target = "relay:0.0"\n'
                'transport = "tmux_keys"\n'
                "[agents.checker]\n"
                'target = "relay:0.1"\n'
                'transport = "tmux_keys"\n',
                encoding="utf-8",
            )
            subprocess.run(["git", "add", ".gitignore", "app.txt"], cwd=root, check=True)
            subprocess.run(
                ["git", "commit", "-m", "base"],
                cwd=root,
                check=True,
                capture_output=True,
            )
            with (
                mock.patch.object(
                    relay,
                    "_tmux",
                    side_effect=("%1", "%2"),
                ),
                self.assertRaisesRegex(relay.RelayError, "must be ignored"),
            ):
                relay.initialize(root)

    def test_init_requires_real_owner_config_to_be_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(
                ["git", "init", "-b", "work"],
                cwd=root,
                check=True,
                capture_output=True,
            )
            subprocess.run(["git", "config", "user.name", "Relay Test"], cwd=root, check=True)
            subprocess.run(
                ["git", "config", "user.email", "relay@example.invalid"],
                cwd=root,
                check=True,
            )
            (root / ".gitignore").write_text("/.relay/\n", encoding="utf-8")
            (root / "app.txt").write_text("base\n", encoding="utf-8")
            config = root / "docs" / "ai-collaboration" / "relay.toml"
            config.parent.mkdir(parents=True)
            config.write_text(
                'schema_version = "relay-config/v2"\n'
                'branch = "work"\n'
                "[agents.engineer]\n"
                'target = "relay:0.0"\n'
                'transport = "tmux_keys"\n'
                "[agents.checker]\n"
                'target = "relay:0.1"\n'
                'transport = "tmux_keys"\n',
                encoding="utf-8",
            )
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(
                ["git", "commit", "-m", "base"],
                cwd=root,
                check=True,
                capture_output=True,
            )

            with (
                mock.patch.object(relay, "_tmux", side_effect=("%1", "%2")),
                self.assertRaisesRegex(relay.RelayError, "real relay.toml must be ignored"),
            ):
                relay.initialize(root)

    def test_init_requires_owner_to_fill_both_targets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(
                ["git", "init", "-b", "work"],
                cwd=root,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Relay Test"],
                cwd=root,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.email", "relay@example.invalid"],
                cwd=root,
                check=True,
            )
            (root / ".gitignore").write_text(
                "/docs/ai-collaboration/relay.toml\n/.relay/\n",
                encoding="utf-8",
            )
            (root / "app.txt").write_text("base\n", encoding="utf-8")
            subprocess.run(["git", "add", ".gitignore", "app.txt"], cwd=root, check=True)
            subprocess.run(
                ["git", "commit", "-m", "base"],
                cwd=root,
                check=True,
                capture_output=True,
            )
            config = root / "docs" / "ai-collaboration" / "relay.toml"
            config.parent.mkdir(parents=True)
            config.write_text(
                'schema_version = "relay-config/v2"\n'
                'branch = "work"\n'
                "[agents.engineer]\n"
                'target = ""\n'
                'transport = "tmux_keys"\n'
                "[agents.checker]\n"
                'target = "relay:0.1"\n'
                'transport = "tmux_keys"\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(relay.RelayError, "configure the engineer"):
                relay.initialize(root)


if __name__ == "__main__":
    unittest.main()

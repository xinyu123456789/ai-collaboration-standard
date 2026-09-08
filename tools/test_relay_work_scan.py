"""Work-plan scanner tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import relay


class WorkScanTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()

    def _write_plan(self, text: str, name: str = "docs/work.md") -> Path:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_scan_passes_only_current_phase_before_unchecked_gate(self) -> None:
        plan = self._write_plan(
            """# Plan
## Phase 1
- [ ] **OLD-OPEN** — intentionally outside this phase
- [x] **PHASE-GATE-001** — previous gate
## Phase 2
- [x] **EXAMPLE-R002A** — done
- [X] `EXAMPLE-R002B` — done
- [ ] **PHASE-GATE-002** — target gate
## Phase 3
- [ ] **FUTURE-OPEN** — not started
"""
        )

        result = relay.scan_unfinished_work(self.root, plan, "PHASE-GATE-002")

        self.assertEqual(
            result,
            "WORK_SCAN_PASS gate=PHASE-GATE-002 checked=2 plan=docs/work.md",
        )

    def test_scan_reports_only_unfinished_items_in_current_phase(self) -> None:
        plan = self._write_plan(
            """# Plan
## Phase 1
- [ ] **OLD-OPEN** — intentionally outside this phase
- [x] **PHASE-GATE-001** — previous gate
## Phase 2
- [x] **EXAMPLE-R002A** — done
- [ ] **EXAMPLE-R002B** — missed
- [ ] **PHASE-GATE-002** — target gate
## Phase 3
- [ ] **FUTURE-OPEN** — not started
"""
        )

        with self.assertRaises(relay.RelayError) as caught:
            relay.scan_unfinished_work(self.root, plan, "PHASE-GATE-002")

        message = str(caught.exception)
        self.assertIn("unfinished current-phase items", message)
        self.assertIn("docs/work.md:7: **EXAMPLE-R002B** — missed", message)
        self.assertNotIn("OLD-OPEN", message)
        self.assertNotIn("FUTURE-OPEN", message)

    def test_gate_reference_in_description_is_not_a_boundary(self) -> None:
        plan = self._write_plan(
            """## Phase 1
- [x] **PHASE-GATE-001** — previous gate
## Phase 2
- [x] **EXAMPLE-R002A** — must be done before PHASE-GATE-002
- [x] **WORK-NOGATE-NOTE** — ordinary work, not a gate boundary
- [ ] **PHASE-GATE-002** — target gate
"""
        )

        result = relay.scan_unfinished_work(self.root, plan, "PHASE-GATE-002")

        self.assertIn("checked=2", result)

    def test_first_gate_starts_at_nearest_level_two_heading(self) -> None:
        plan = self._write_plan(
            """# Plan
- [ ] **UNRELATED** — document-level checklist
## Phase 1
- [x] **EXAMPLE-R001** — done
- [ ] **PHASE-GATE-001** — first gate
"""
        )

        result = relay.scan_unfinished_work(self.root, plan, "PHASE-GATE-001")

        self.assertIn("checked=1", result)

    def test_first_gate_does_not_lose_work_before_a_nested_heading(self) -> None:
        plan = self._write_plan(
            """## Phase 1
- [ ] **EXAMPLE-R001** — unfinished before subsection
### Verification notes
- [x] **EXAMPLE-R002** — done
- [ ] **PHASE-GATE-001** — first gate
"""
        )

        with self.assertRaises(relay.RelayError) as caught:
            relay.scan_unfinished_work(self.root, plan, "PHASE-GATE-001")

        self.assertIn("EXAMPLE-R001", str(caught.exception))

    def test_first_gate_requires_a_level_two_phase_heading(self) -> None:
        plan = self._write_plan(
            """# Phase 1
- [x] **EXAMPLE-R001** — done
- [ ] **PHASE-GATE-001** — first gate
"""
        )

        with self.assertRaisesRegex(relay.RelayError, "level-two phase heading"):
            relay.scan_unfinished_work(self.root, plan, "PHASE-GATE-001")

    def test_missing_and_duplicate_gate_are_rejected(self) -> None:
        missing = self._write_plan(
            "## Phase 1\n- [x] **EXAMPLE-R001** — done\n",
            "docs/missing.md",
        )
        duplicate = self._write_plan(
            """## Phase 1
- [ ] **PHASE-GATE-001** — first copy
- [ ] **PHASE-GATE-001** — second copy
""",
            "docs/duplicate.md",
        )

        with self.assertRaisesRegex(relay.RelayError, "is not a checklist item"):
            relay.scan_unfinished_work(self.root, missing, "PHASE-GATE-001")
        with self.assertRaisesRegex(relay.RelayError, "appears more than once"):
            relay.scan_unfinished_work(self.root, duplicate, "PHASE-GATE-001")

    def test_scan_rejects_an_ordinary_work_id_as_the_gate(self) -> None:
        plan = self._write_plan("## Phase 1\n- [ ] **WORK-001** — ordinary work\n")

        with self.assertRaisesRegex(relay.RelayError, "gate ID must contain GATE"):
            relay.scan_unfinished_work(self.root, plan, "WORK-001")

    def test_scan_rejects_paths_outside_repository(self) -> None:
        repository = self.root / "repository"
        repository.mkdir()
        outside = self._write_plan(
            "## Phase 1\n- [ ] **PHASE-GATE-001** — gate\n",
            "outside.md",
        )

        with self.assertRaisesRegex(relay.RelayError, "inside the project repository"):
            relay.scan_unfinished_work(repository, outside, "PHASE-GATE-001")

    def test_scan_all_reports_unfinished_items_across_every_phase(self) -> None:
        plan = self._write_plan(
            """# Plan
## Phase 1
- [ ] **OLD-OPEN** — unfinished work
- [x] **EXAMPLE-R001** — done
- [ ] **PHASE-GATE-001** — unfinished gate
## Phase 2
- [X] `EXAMPLE-R002A` — done
- [ ] **FUTURE-OPEN** — unfinished work
- [x] **PHASE-GATE-002** — done gate
"""
        )

        result = relay.scan_all_unfinished_work(self.root, plan)

        self.assertEqual(
            result,
            "WORK_SCAN_ALL unfinished=3 plan=docs/work.md\n"
            "docs/work.md:3: **OLD-OPEN** — unfinished work\n"
            "docs/work.md:5: **PHASE-GATE-001** — unfinished gate\n"
            "docs/work.md:8: **FUTURE-OPEN** — unfinished work",
        )

    def test_scan_all_reports_zero_when_plan_is_complete(self) -> None:
        plan = self._write_plan(
            "## Phase 1\n- [x] **EXAMPLE-R001** — done\n- [X] **PHASE-GATE-001** — done\n"
        )

        result = relay.scan_all_unfinished_work(self.root, plan)

        self.assertEqual(
            result,
            "WORK_SCAN_ALL unfinished=0 plan=docs/work.md",
        )

    def test_scan_all_rejects_paths_outside_repository(self) -> None:
        repository = self.root / "repository"
        repository.mkdir()
        outside = self._write_plan(
            "## Phase 1\n- [ ] **EXAMPLE-R001** — unfinished\n",
            "outside.md",
        )

        with self.assertRaisesRegex(relay.RelayError, "inside the project repository"):
            relay.scan_all_unfinished_work(repository, outside)


if __name__ == "__main__":
    unittest.main()

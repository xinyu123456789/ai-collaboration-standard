# Example Work Plan

Gate IDs must contain `GATE` as a dot, underscore, or hyphen-delimited token. Checklist labels begin
with a unique work ID in plain text, bold, or backticks.

## Phase 1: Foundation

- [ ] **WORK-001** — Add the smallest executable project skeleton; acceptance: the documented smoke command exits successfully.
- [ ] **WORK-002** — Add one focused automated test for the skeleton.
- [ ] **PHASE-GATE-01** — Checker verifies every Phase 1 item, required project checks, and the phase-specific adversarial cases.

## Phase 2: First capability

- [ ] **WORK-003** — Define one public contract and its positive and negative tests.
- [ ] **WORK-004** — Implement one adapter without expanding the public contract.
- [ ] **PHASE-GATE-02** — Checker scans unfinished work, reruns the project baseline, and records the gate result.

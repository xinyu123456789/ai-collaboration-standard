# Project Work Plan

> Owner-approved local planning record for Relay. Copy it to the Git-ignored path defined in
> `PROJECT_PROFILE.md`, replace the example phase and rounds before activation, and share it through
> the agents' common filesystem. Keep checklist items on one physical line so scanner output includes
> the full acceptance description.

## Planning rules

- Each engineering round has one unique ID, one objective, and one observable acceptance condition.
- Keep a round within the maximum size defined in `PROJECT_PROFILE.md`.
- Record dependencies on the same checklist line. Use `depends on: none` when it is ready.
- The Engineer does not check off its own work.
- The Checker changes `[ ]` to `[x]` after the committed implementation passes review and before
  the terminal `accept` transition.
- A blocked or deferred round remains `[ ]` and names the exact missing dependency.
- The Checker may insert focused repair rounds after the affected item.
- Every phase ends with a Checker-owned Gate whose ID contains `GATE` as a delimited token.
- Use level-two headings (`##`) for phases. Nested headings do not start a new phase.
- Keep the phase's final engineering Checkpoint in review while running its Gate; `accept` is the
  Checker's final workflow action.
- Before a Gate, run `relay scan-work`; before a final project Gate, also run `relay scan-all-work`.

## Phase 1: Replace with phase name

- [ ] **WORK-001** — Objective: deliver one independently testable result; acceptance: name the exact observable result or command; scope: name the relevant paths or component; depends on: none.
- [ ] **WORK-002** — Objective: deliver the next independent result; acceptance: name the exact positive and negative evidence; scope: name one component; depends on: WORK-001.
- [ ] **PHASE-GATE-01** — Checker verifies every Phase 1 item, required project checks, phase-specific adversarial cases, and retained evidence.

## Phase 2: Replace with phase name

- [ ] **WORK-003** — Objective: deliver one independently testable result; acceptance: name the exact observable result or command; scope: name the relevant paths or component; depends on: PHASE-GATE-01.
- [ ] **PHASE-GATE-02** — Checker scans unfinished work, verifies every Phase 2 item, reruns the required project baseline, and records retained evidence.

## Deferred dependencies

Do not duplicate checklist items here. Summarize external dependencies and point back to their
unchecked round IDs.

| Blocked round | Dependency owner | Exact missing input | Evidence or coordination reference | Resume condition |
|---|---|---|---|---|
| `WORK-XXX` | `{{OWNER_OR_TEAM}}` | `{{MISSING_CONTRACT_DATA_OR_DECISION}}` | `{{PATH_ISSUE_OR_DECISION}}` | `{{OBJECTIVE_RESUME_CONDITION}}` |

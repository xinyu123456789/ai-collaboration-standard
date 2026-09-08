# AI Collaboration Standard

AI Collaboration Standard is a local, turn-based workflow for one Owner, one Engineer agent, and
one Checker agent working in the same Git repository. Its Relay CLI coordinates handoffs, preserves
review history, enforces Git boundaries, and delivers short control events between two tmux-hosted
agents.

The project is model- and vendor-neutral. Relay runs locally, uses only the Python standard library,
and never calls an AI API.

## Core principles

- One role owns the turn at a time.
- One work round has one independently verifiable objective.
- Every engineering handoff is bound to an exact Git commit.
- The Checker owns findings, acceptance, and next-round selection.
- Missing authority or ambiguous requirements stop at an Owner decision.
- Runtime state stays local and separate from product history.
- Control events contain identifiers only; detailed evidence remains in Git and Checkpoints.

Relay coordinates the workflow. It does not interpret requirements, judge implementation quality,
run tests, edit product files, commit changes, or grant permissions.

## Requirements

- Git
- Python 3.11 or newer
- tmux
- Optional: a Codex CLI that supports `codex queue --help` when using the `codex_queue` transport

There are no third-party Python dependencies.

## Repository contents

```text
ai-collaboration-standard/
├── README.md
├── AI_COLLABORATION_PROTOCOL.md
├── PROJECT_PROFILE_TEMPLATE.md
├── WORK_PLAN_TEMPLATE.md
├── relay.example.toml
├── pyproject.toml
├── examples/
│   └── WORK_PLAN.md
└── tools/
    ├── relay.py
    ├── test_relay.py
    ├── test_relay_tmux.py
    └── test_relay_work_scan.py
```

The files have distinct responsibilities:

- `AI_COLLABORATION_PROTOCOL.md` defines the workflow, authority model, and invariants.
- `PROJECT_PROFILE_TEMPLATE.md` defines project-specific scope, ownership, validation, and
  permissions.
- `WORK_PLAN_TEMPLATE.md` defines small work rounds, dependencies, acceptance criteria, and phase
  Gates.
- `relay.example.toml` maps roles to a branch, tmux panes, and delivery transports.
- `tools/relay.py` implements the state machine and command-line interface.
- `tools/test_relay*.py` cover state transitions, Git guards, recovery paths, work-plan scans, and
  real tmux delivery.

## Install in a project

From this repository, copy the protocol and Relay CLI into the target project:

```text
AI_COLLABORATION_PROTOCOL.md -> <project>/docs/ai-collaboration/PROTOCOL.md
tools/relay.py                -> <project>/docs/ai-collaboration/tools/relay.py
```

Create the project-specific files from the supplied templates:

```text
PROJECT_PROFILE_TEMPLATE.md -> <project>/docs/ai-collaboration/PROJECT_PROFILE.md
WORK_PLAN_TEMPLATE.md        -> <project>/docs/ai-collaboration/WORK_PLAN.local.md
relay.example.toml           -> <project>/docs/ai-collaboration/relay.toml
```

Add local operational files to the target project's `.gitignore`:

```gitignore
/.relay/
/docs/ai-collaboration/relay.toml
/docs/ai-collaboration/WORK_PLAN.local.md
```

The protocol, completed project profile, Relay source, and sanitized templates may be committed.
The active work plan, runtime configuration, and `.relay/` state must remain local so Relay can
require a clean worktree at every handoff.

## Configure the roles

Create or select the shared working branch, then identify both agent panes:

```bash
tmux list-panes -a \
  -F '#{session_name}:#{window_index}.#{pane_index} #{pane_id} #{pane_current_command}'
```

Fill `docs/ai-collaboration/relay.toml`:

```toml
schema_version = "relay-config/v2"
branch = "feature/shared-work"

[agents.engineer]
target = "project:0.0"
transport = "tmux_keys"

[agents.checker]
target = "project:0.1"
transport = "codex_queue"
thread = "<codex-session-uuid-or-name>"
```

Available transports:

- `tmux_keys` pastes the event into the target pane and submits it with Enter.
- `codex_queue` sends the event through a named Codex session queue.

Every role requires a distinct, resolvable tmux target because Relay uses the current pane as role
identity. A `codex_queue` recipient also requires a distinct Codex session identifier.

## Activate Relay

Before activation:

1. Replace every placeholder in `PROJECT_PROFILE.md`.
2. Define the initial rounds and acceptance criteria in `WORK_PLAN.local.md`.
3. Confirm the branch, panes, transports, and optional Codex sessions in `relay.toml`.
4. Run the unit suite and the required smoke tests.
5. Review the activation checklist in the protocol.
6. Obtain explicit Owner approval for the first work round.

Initialize from the target project root:

```bash
python3 docs/ai-collaboration/tools/relay.py init
```

Relay verifies the repository, branch, clean worktree, ignored runtime paths, and distinct tmux
panes. It then records the current Git HEAD as the initial accepted boundary.

The documentation below uses `relay` as shorthand for:

```bash
python3 docs/ai-collaboration/tools/relay.py
```

## Workflow

### 1. Assign a round

The Checker selects one ready, non-Gate work item and starts it:

```bash
relay start --round WORK-001
```

Relay creates a Checkpoint and sends an event such as:

```text
WORK WORK-001 CP001 EV0001
```

### 2. Claim the event

The Engineer claims the exact event before working:

```bash
relay claim EV0001
relay show CP001
```

Claims are idempotent. A pending, unclaimed event blocks further state transitions.

### 3. Implement and request review

The Engineer implements only the assigned round, runs the project-required checks, and commits the
result. The worktree must be clean before handoff:

```bash
relay review
```

Relay requires at least one new non-merge commit descending from the previous Checkpoint head. It
records the new head and sends:

```text
REVIEW CP001 EV0002
```

### 4. Review the exact head

The Checker claims the event, reads the Checkpoint, inspects the actual Git diff, and runs checks
appropriate to the risk:

```bash
relay claim EV0002
relay show CP001
```

Relay rejects review decisions if Git HEAD changes after the engineering handoff.

### 5. Record findings and request revision

The Checker records each actionable issue:

```bash
relay finding --location src/auth/token.py:84 \
  "refresh rotation is not atomic"
relay revise
```

Relay assigns stable IDs such as `F001` and sends every open finding back to the Engineer. If the
same underlying issue remains, reuse its ID:

```bash
relay finding --id F001 --location src/auth/token.py:91 \
  "replacement creation remains outside the critical section"
```

After the Engineer submits another committed head, the Checker verifies the repair and completes
the relevant findings:

```bash
relay complete F001 F002
```

Acceptance remains blocked while any finding is open.

### 6. Accept and select the next state

To accept the reviewed head and immediately assign another round:

```bash
relay accept --next WORK-002
```

To accept the reviewed head without assigning more work:

```bash
relay accept --idle
```

Only the Checker accepts work. When a next round is selected, Relay accepts the current Checkpoint,
creates the next one at the accepted head, and sends a single combined event.

## Owner decisions

The active role stops when requirements, authority, dependencies, Git state, or material design
choices cannot be resolved from the project profile and sources of truth:

```bash
relay hold --owner "the public response contract has two valid interpretations"
```

The Checker presents the evidence, options, impact, recommendation, and one precise question to the
Owner. After an explicit decision, the Checker resumes the appropriate role:

```bash
relay resume --decision "use the documented response shape" --to engineer
```

Two narrower Owner-authorized outcomes are available:

- `relay cancel` cancels an untouched mistaken assignment.
- `relay defer` retains reviewed partial work with open findings when an external dependency is
  unavailable.

Deferred work can be resumed only while Relay is idle:

```bash
relay resume-deferred --checkpoint CP018 \
  --decision "the required upstream contract is now available"
```

The original Checkpoint and Finding IDs remain intact.

## Work plans and phase Gates

The default planning backend is a local Markdown checklist. Every engineering item contains:

- a unique opaque round ID;
- one independently verifiable objective;
- an observable acceptance condition;
- explicit dependencies;
- enough scope detail to prevent unrelated changes.

Only the Checker marks engineering items complete. A blocked or deferred item remains unchecked and
names its exact dependency.

Every configured phase ends with a Checker-owned Gate whose ID contains `GATE` as a dot-,
underscore-, or hyphen-delimited token, such as `PHASE-GATE-01`. Gate IDs cannot be dispatched as
engineering rounds.

Before a phase Gate, scan the current phase:

```bash
relay scan-work \
  --plan docs/ai-collaboration/WORK_PLAN.local.md \
  --gate PHASE-GATE-01
```

The Gate may proceed only after `WORK_SCAN_PASS`. To list every unchecked item across the complete
plan:

```bash
relay scan-all-work \
  --plan docs/ai-collaboration/WORK_PLAN.local.md
```

The scanners are read-only. Projects using another planning system must define equivalent ID,
ownership, dependency, acceptance, and Gate behavior in `PROJECT_PROFILE.md`.

## Git and delivery guarantees

State-changing handoffs enforce:

- the configured repository and branch;
- a non-detached HEAD;
- no unresolved merge entries;
- a clean worktree;
- descendant-only engineering history;
- at least one new engineering commit;
- no merge commits introduced inside a round;
- an unchanged head throughout Checker review.

Relay stores local state in:

```text
.relay/
├── state.json
├── transition.json
└── checkpoints/
    ├── CP001.json
    └── CP002.json
```

`transition.json` exists only while a multi-file update is pending. Relay writes each JSON file
through a same-directory temporary file and atomic replacement. A later command replays an
interrupted transition before reading state.

If event delivery fails, the pending Event ID blocks the workflow. After repairing the target or
session, the original sender retries the same event:

```bash
relay retry
```

If an Owner-approved integration advances Git while Relay is idle, the Checker may record the new
descendant boundary without changing Git:

```bash
relay adopt-idle-head --decision "approved integration commit"
```

## Command reference

```text
relay init
relay start --round <work-round>
relay claim <event-id>
relay review
relay finding [--id <finding-id>] --location <path[:line]> <problem>
relay complete <finding-id> [<finding-id> ...]
relay revise
relay accept (--next <work-round> | --idle)
relay hold --owner <reason>
relay cancel --decision <owner-decision> (--next <work-round> | --idle)
relay defer --decision <owner-decision> --next <work-round>
relay resume --decision <owner-decision> --to <engineer|checker>
relay resume-deferred --checkpoint <checkpoint-id> --decision <owner-decision>
relay adopt-idle-head --decision <owner-decision>
relay retry
relay show [checkpoint-id]
relay status
relay scan-work --plan <work-plan.md> --gate <gate-id>
relay scan-all-work --plan <work-plan.md>
```

`show`, `status`, `scan-work`, and `scan-all-work` are read-only. State-changing commands
verify role ownership and reject an unclaimed incoming event.

## Test the standard

Run the portable suite:

```bash
python3 -m unittest discover -s tools -p 'test_relay*.py' -v
```

Run the real tmux smoke test explicitly:

```bash
RELAY_RUN_TMUX_SMOKE=1 python3 -m unittest discover \
  -s tools -p 'test_relay_tmux.py' -v
```

The tests create isolated temporary repositories and do not modify the repository under test.

## Operational boundaries

- Relay supports one local worktree and two configured tmux-hosted agents.
- Concurrent state-changing commands are unsupported.
- Runtime JSON and pane identity are cooperative controls, not a security boundary against a local
  user who deliberately changes state or environment variables.
- Relay passes Git, tmux, and Codex arguments directly to subprocesses without constructing a shell
  command.
- Findings, source content, secrets, and Owner decisions are never placed in transport events.
- The Owner remains responsible for project scope, credentials, external services, costs,
  destructive actions, push, merge, deployment, and exceptional recovery.

For normative behavior and authority rules, read
[`AI_COLLABORATION_PROTOCOL.md`](AI_COLLABORATION_PROTOCOL.md) before activation.

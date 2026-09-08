# Two-Agent Relay Collaboration Protocol

> Version 3.1.0 | Local Relay | Git-backed engineering | Silent handoff

## 0. Adoption and compatibility

This protocol is a reusable baseline for one Owner, one Engineer agent, and one Checker agent
working on the same local Git worktree. A project adopts it only after the Owner completes the
project profile, Relay configuration, and activation checks.

Relay v3 replaces report files, completion-signal JSON, polling watchers, and background detector
processes. A project migrating from an older workflow may retain those artifacts as read-only audit
history, but they are not part of this standard and must not be used for new handoffs after cutover.

### 0.1 Baseline invariants and project policy

An unmodified Relay workflow keeps one active role, claimed event delivery, review of the exact Git
head, Checker-controlled findings and acceptance, terminal `accept`, and explicit Owner authority.
These are operational invariants, not project preferences.

The project profile may adapt the planning backend, ID convention, round size, Gate use and scope,
verification commands, path ownership, permissions, and Owner-facing report format. The Markdown
work plan and phase-Gate workflow are supported defaults. A project that changes Relay's state
machine, Git-boundary rules, or delivery guarantees must version and test that variant separately.

## 1. Purpose and limits

Relay coordinates one Engineer and one Checker running in separate tmux panes. It provides a small,
strict state machine and reliable short handoffs without depending on a model vendor or AI API.

Relay does:

- record the active work round and Checkpoint;
- enforce turn ownership;
- verify mechanical Git boundaries;
- store concise review findings and revision commits;
- send fixed events through an Owner-selected local transport;
- stop for an owner decision when existing authority is insufficient.

Relay does not:

- interpret requirements or decide whether code is correct;
- select work without the Checker's judgment;
- run tests automatically;
- modify product code;
- commit, push, merge, deploy, delete, or rewrite Git history;
- grant authority that the owner did not provide;
- run a watcher, polling loop, daemon, network service, or background agent.

## 2. Sources of truth

The sources of truth have separate responsibilities:

```text
requirements documents   required behavior and constraints
design documents         implementation contracts and boundaries
project work plan         planned rounds and acceptance details
Git                       product changes and commit history
Relay Checkpoints         local turn, review, and revision history
Owner decisions           scope and exceptional authorization
```

The project profile must list the exact documents in priority order. A Checkpoint may narrow one
round but cannot override a higher-priority source.

Work-round IDs are opaque project-defined strings. Relay accepts existing IDs such as
`EXAMPLE-R130A3B2B1C2` and does not renumber or parse the project work plan.

## 3. Local files

The recommended project integration is:

```text
docs/ai-collaboration/
├── PROTOCOL.md
├── PROJECT_PROFILE.md
├── relay.toml
└── tools/
    ├── relay.py
    └── ...

.relay/
├── state.json
├── transition.json        # exists only while a multi-file transition is pending
└── checkpoints/
    ├── CP001.json
    └── CP002.json
```

The project decides whether the protocol, profile, and tool source are tracked. `.relay/` is always
local operational state and must be ignored by Git. The real `relay.toml` and the active Markdown
work plan are also local files because Relay's Git guards require an unchanged worktree at every
handoff. Commit only sanitized configuration and work-plan templates.

The Owner writes `relay.toml`; Relay never creates or edits it. Every agent has a tmux target for
role identity and an explicit delivery transport. Codex uses its session-aware queue because
programmatically pasting text followed immediately by Enter is not a reliable Codex submission.
The Owner obtains tmux targets with `tmux list-panes`. For Codex, the Owner also supplies the
session UUID or exact session name accepted by the installed `codex queue` command:

```toml
schema_version = "relay-config/v2"
branch = "work"

[agents.engineer]
target = "project:0.1"
transport = "tmux_keys"

[agents.checker]
target = "project:0.0"
transport = "codex_queue"
thread = "<codex-session-uuid-or-name>"
```

Blank, equal, or unresolvable targets, an unknown transport, or a missing Codex thread fail
initialization. Relay does not guess terminal names, client types, or session identities. Agents
never edit Relay state or Checkpoint JSON directly; the Relay CLI owns those files.

`codex_queue` is optional. Before selecting it, the Owner must confirm that the installed Codex CLI
exposes `codex queue --help`; otherwise use `tmux_keys` with a compatible recipient.

## 4. Project authority

### 4.1 Owner

The Owner decides requirements, priority, public contracts, architecture, technology choices,
costs, credentials, external services, destructive actions, push, main merge, deployment, pause,
cancel, and exceptional recovery.

Project-specific permissions belong in `PROJECT_PROFILE.md`. Silence never grants commit, push,
merge, deployment, destructive-action, external-service, or spending authority.

### 4.2 Engineer

The Engineer:

- implements only the assigned work round;
- stays inside its allowed paths and acceptance conditions;
- self-tests and fixes obvious failures;
- commits completed work when the project rules permit it;
- hands the committed head to the Checker with `relay review`;
- stops after the handoff.

The Engineer does not select a next round, modify Checkpoints directly, push, merge, deploy, delete,
or guess an owner decision.

### 4.3 Checker

The Checker:

- independently inspects the actual diff and relevant source;
- runs tests appropriate to the risk;
- records concise, actionable findings;
- accepts only a head it actually reviewed;
- selects one executable next round;
- reports progress to the Owner when asked;
- asks the Owner whenever existing rules do not determine a safe answer.

The Checker does not change product code to make a review pass.

## 5. Project profile and boundaries

Before activation, the Owner copies `PROJECT_PROFILE_TEMPLATE.md` to
`docs/ai-collaboration/PROJECT_PROFILE.md` and replaces every placeholder. The profile defines:

- project objective, non-goals, and completion criteria;
- source-of-truth order and work-plan path;
- Engineer and Checker responsibilities;
- allowed, shared, protected, and excluded paths;
- maximum round size;
- required validation commands;
- commit, push, merge, deployment, and external-service authority;
- Owner decision channel and stop conditions.

Each round contains one independently verifiable objective within the configured size limit. A
second objective, unrelated subsystem, or repeated review churn means the Checker splits the work
before assignment.

Required verification is project-defined. An unavailable command is reported honestly; it is never
claimed as executed. Neither agent expands permissions because a path or command is absent from the
profile; uncertainty enters an Owner hold.

### 5.1 Work-plan contract

The standard planning backend is one local, Git-ignored Markdown work plan created from
`WORK_PLAN_TEMPLATE.md`. Both agents share it through the common filesystem. Each engineering
checklist item contains:

- one unique opaque work-round ID;
- one independently verifiable objective;
- an observable acceptance condition;
- explicit dependencies or `none`;
- enough scope information to prevent unrelated work from entering the round.

The Owner approves the initial scope and material scope changes. Within that approved scope, the
Checker may split oversized work, add focused repair rounds from findings, reorder ready rounds, and
select the next executable round. Only the Checker changes a work item from `[ ]` to `[x]`, after its
committed implementation passes review and before the terminal `accept` transition. The Engineer
never marks its own round complete in the work plan.

A blocked or deferred item remains unchecked and records its exact dependency. Explanatory prose
does not waive it. When the project uses phase Gates, each configured phase ends with a Checker-owned
Gate item whose ID contains the delimited `GATE` token required by the built-in scanner.

### 5.2 Alternative planning systems

Relay state transitions require only an opaque work-round ID, so a project may use GitHub Issues,
Jira, or another planning system. The project profile must name that system and define equivalent
rules for unique IDs, objective size, acceptance criteria, dependencies, status ownership, and any
configured phase Gates.

The built-in `scan-work` and `scan-all-work` commands read Markdown checklists only. A project using
another planning system and the phase-Gate preflight must either maintain a local, Git-ignored
generated Markdown mirror or provide a reviewed replacement scan command with the same blocking
behavior. Without one of those two mechanisms, it cannot claim compatibility with this preflight.

## 6. Turn model

Only one role owns the turn:

```text
engineering -> review -> revise -> review -> accepted
```

Additional states:

- `owner_hold`: no agent may continue until the Owner decides and explicitly authorizes resume.
- `idle`: the previous Checkpoint is accepted and no next round is assigned.
- `cancelled`: an explicitly cancelled untouched assignment; records are retained.
- `deferred`: reviewed partial work is retained, but its open finding and unchecked plan item remain
  blocking obligations until the dependency becomes available.

The Checker may reorder ready work before assigning it. Once a round starts, neither agent silently
parks it and changes the same branch with another round. An unexpected dependency or decision enters
`owner_hold`; only an explicit Owner-approved `defer` transition may then retain reviewed partial work
and assign a different ready round.

## 7. Checkpoint lifecycle

The Checker creates a Checkpoint when assigning the round:

```bash
relay start --round EXAMPLE-R130A3B2B1C2
```

Checkpoint numbering is independent from work-round numbering. One round uses one Checkpoint for
all review and revision passes.

```json
{
  "id": "CP018",
  "work_round": "EXAMPLE-R130A3B2B1C2",
  "base": "72ed191",
  "head": "72ed191",
  "status": "engineering",
  "reviews": [],
  "revises": [],
  "holds": []
}
```

Rules:

- `base` is the last accepted commit at assignment and remains fixed.
- `head` is the latest commit handed to the Checker.
- Review, revision, and hold entries are append-only in meaning.
- Finding location and problem text remain historical review content. A finding's live `status`
  is the sole mutable field and only the Checker may change it.
- Relay may atomically rewrite the JSON file, but never rewrites prior work evidence.
- The active Checkpoint remains assigned until accepted, held, explicitly cancelled, or explicitly
  deferred by the Owner.

## 8. Git guards

Git guards are mandatory and run before state-changing handoffs.

Relay reads the configured branch and agent targets, then records the initial accepted HEAD during
`relay init`. It rejects:

- the wrong repository or branch;
- detached HEAD;
- unresolved merges;
- a dirty worktree, excluding ignored local artifacts;
- an engineering head with no new commit;
- a new head that is not a descendant of the previous head;
- merge commits introduced inside the round or revision;
- `accept` or `revise` after the reviewed HEAD changes.

These checks protect the handoff boundary. They do not replace scope review or behavioral tests.
Relay never runs a Git mutation command.

If an Owner-approved descendant integration advances Git while Relay is idle between accepted
rounds, the Checker records the new boundary with:

```bash
relay adopt-idle-head --decision <owner-decision>
```

The command requires `idle`, no pending delivery, the configured branch, a clean worktree, an
explicit one-line Owner decision, and a current HEAD that strictly descends from `last_accepted`.
It records an append-only state-level adoption, advances `last_accepted`, sends no event, and never
mutates Git. It is not a general synchronization command and cannot run during an active round.

## 9. Engineering handoff

After implementation, self-testing, fixes, and commits, the Engineer runs:

```bash
relay review
```

Relay verifies Git, updates the Checkpoint head, and sends the Checker:

```text
REVIEW CP018 EV0042
```

**HARD RULE — NO EXPLANATORY COMPLETION REPORT:** after successful `relay review`, the Engineer's
entire final assistant message is the exact single Relay event line returned by the command. The
Engineer must not send a prose completion message before or after it, and must not summarize work,
files, commits, tests, findings, or next steps. A routine handoff containing any additional
explanatory text violates this protocol even when Relay itself succeeded.

The Engineer ends the turn immediately after that single-line handoff. Routine completion
summaries and Markdown reports are not produced.

## 10. Review and revision

The Checker first claims the event:

```bash
relay claim EV0042
relay show CP018
```

A new finding:

```bash
relay finding --location src/auth/token.py:84 \
  "refresh rotation is not atomic"
```

If the same underlying issue remains on a later pass, the same Finding ID is reused:

```bash
relay finding --id F001 --location src/auth/token.py:91 \
  "replacement creation remains outside the critical section"
```

A Finding ID identifies one underlying issue. Its current location and description may change. A
different issue receives a new ID.

Every finding has one live status:

- `open`: the finding still blocks acceptance;
- `completed`: the Checker verified the repair.

The Engineer cannot modify finding status. `relay review` records revision commits but leaves every
finding `open`. After verifying one or more repairs, the Checker completes them in one command:

```bash
relay complete F001 F002
```

Repeating `relay finding --id F001 ...` keeps or returns that finding to `open`. A finding that is
still accurate does not need to be rewritten merely to request another revision. `relay revise`
always sends every finding that remains open.

When the pass requires changes:

```bash
relay revise
```

Relay appends the review and sends:

```text
REVISE CP018 EV0043
```

The Engineer claims the event, reads the Checkpoint, fixes the current findings, tests, commits,
and runs `relay review`. Relay records every commit added after the previous reviewed head in one
revision entry without changing finding status.

## 11. Acceptance

When the current head passes review, the Checker selects one ready round:

```bash
relay accept --next EXAMPLE-R130A3B2B2
```

Acceptance is rejected while any finding remains `open`; the Checker must verify and complete each
one first. This prevents an Engineer handoff from self-certifying its own repair.

Relay accepts the current Checkpoint, updates `last_accepted`, creates the next Checkpoint, and sends
one event:

```text
ACCEPT CP018 WORK EXAMPLE-R130A3B2B2 CP019 EV0044
```

If no round is ready:

```bash
relay accept --idle
```

Relay accepts the current Checkpoint and enters `idle` without inventing new work.

`accept` is always the Checker's final workflow action in the turn. With `--next`, the Engineer may
begin as soon as it receives the event. The Checker therefore completes every required work-plan
update, phase Gate, and next-round selection before running `accept`; it performs no further work
after a successful acceptance.

### Phase-gate preflight (when configured)

Phase Gates are Checker actions, not engineering work rounds. Never pass a Gate ID to
`relay start`, `relay accept --next`, or `relay cancel --next`; Relay rejects that dispatch. The
work plan must give every Gate an ID containing `GATE` as a dot, underscore, or hyphen-delimited
token, such as `PHASE-GATE-01`.

After the phase's final engineering head passes its focused review, the Checker marks that work item
complete and performs the Gate while the Checkpoint remains in `review`; the Engineer continues to
wait. If the Gate passes, the Checker marks the Gate complete, selects the next ready round, and uses
`relay accept --next <round>` as the turn's final action. If the project has no ready next round, the
final action is `relay accept --idle`.

If the Gate invalidates the active round's own acceptance, the Checker returns that item to
unchecked and uses the normal finding and revision flow. For a separate defect, the Checker adds one
focused repair item, leaves the Gate unchecked, and selects that repair with the terminal
`accept --next`; the Gate is run again after the repair passes review. A Gate is never dispatched as
an engineering round, and the Checker performs no Gate work after `accept`.

Before every configured phase-ending Gate, the Checker must run the read-only work-plan scan:

```bash
relay scan-work --plan <work-plan.md> --gate <gate-id>
```

The scan covers only checklist items in the current phase: after the preceding Gate and before the
named Gate. It excludes the named Gate itself, earlier phases, and future phases. The first phase
must begin at a level-two Markdown heading (`##`); lower-level headings do not reset its boundary.
An earlier Gate's checkbox does not become a global blocker; projects that require global closure
may additionally use `scan-all-work` or a project-defined replacement.

An unchecked item in that range blocks the phase Gate. Prose such as `deferred`, `skipped`, or
`covered elsewhere` does not waive an unchecked item. The Checker must first resolve and update the
project plan under its existing rules, or enter an Owner hold when authority is insufficient. Only a
`WORK_SCAN_PASS` result permits the Checker to continue to that phase's red-team and full-project
Gate checks.

For a whole-project inventory, the Checker may also run:

```bash
relay scan-all-work --plan <work-plan.md>
```

This read-only command lists every unchecked checklist item across all phases, including Gates. It
does not infer why an item is open and does not authorize a phase Gate; only the phase-scoped
`scan-work` command can return `WORK_SCAN_PASS`.

Any project-specific progress file remains governed by that project's rules. The Relay state machine
never rewrites a Markdown work plan; both scan commands only read it.

## 12. Owner decision hold

Uncertainty always stops the workflow. Either role must request an Owner decision for:

- conflicting or ambiguous requirements;
- multiple reasonable acceptance interpretations;
- public contract, data model, architecture, dependency, service, cost, or credential decisions;
- push, merge, deployment, deletion, or another action lacking specific authorization;
- unexplained worktree or Relay state;
- a choice that could materially change behavior, scope, quality, or schedule.

The active role runs:

```bash
relay hold --owner "short reason"
```

Relay records the previous state and enters `owner_hold`. It assigns no other work. If the Engineer
raises the hold, Relay notifies the Checker.

**HARD RULE — THE ENGINEER DOES NOT EXPLAIN A HOLD TO THE OWNER:** after a successful
Engineer-raised hold, the Engineer outputs only the exact `OWNER_HOLD ...` event line. It does not
send the Owner a reason, options, impact analysis, recommendation, or proposed implementation. The
hold record is the handoff to the Checker; the Checker alone turns it into an Owner-facing decision
request. The Engineer cannot resume its own hold.

The Checker asks the Owner with:

1. current work and evidence;
2. why existing authority is insufficient;
3. viable options and impact;
4. the Checker's recommendation;
5. one exact question.

Only after the Owner decides and explicitly says work may continue does the Checker run:

```bash
relay resume --decision "owner decision" --to engineer
```

The decision is appended to the hold record. It grants no unrelated authority.

If the Owner instead cancels a mistakenly assigned round before it has produced any commit or
review, the Checker may atomically retain that Checkpoint as `cancelled` and select the correct
next round:

```bash
relay cancel --decision "owner decision" --next EXAMPLE-R132A2
```

Use `--idle` when no round is ready. Cancellation is deliberately narrow: the hold must have been
raised from `engineering`, Git must still equal the accepted base, the worktree must be clean, and
the Checkpoint must have no review, revision, or finding history. Relay never discards or silently
accepts product work. The fixed handoff is `CANCEL <old> WORK <round> <new> <event>`.

If a reviewed round has an open finding that cannot be completed until an external dependency is
available, the Owner may instead approve deferral. The Checker leaves the work-plan item unchecked,
records the dependency in that item, and runs:

```bash
relay defer --decision "owner decision" --next EXAMPLE-R214A
```

Deferral is Checker-only, requires an active Owner hold and at least one open finding, retains the
reviewed HEAD as the next Checkpoint baseline, and never completes the finding or the work round.
Any configured phase Gate therefore continues to block until the deferred round is resumed and
accepted. Its fixed handoff is `DEFER <old> WORK <round> <new> <event>`.

After the dependency becomes available, the Checker first completes the active round and leaves
Relay idle. With explicit Owner approval, the Checker resumes the original Checkpoint:

```bash
relay resume-deferred --checkpoint CP018 --decision "dependency is available"
```

Relay keeps the same Checkpoint and Finding IDs, advances its revision baseline to the current
accepted HEAD, records the decision, and sends the Engineer
`RESUME_DEFERRED <checkpoint> WORK <round> <event>`. The normal revision, review, finding-completion,
and acceptance flow then continues.

The Checker is the only role that explains an active hold to the Owner and the only role authorized
to run `relay resume`. If the Owner addresses the Engineer while a hold is active, the Engineer does
not duplicate or replace the Checker's decision analysis.

## 13. Event delivery

Relay resolves Engineer and Checker targets to pane IDs during initialization. It sends only fixed,
short control messages through the configured transport:

- `tmux_keys` uses a project-specific named tmux buffer followed by the Enter key;
- `codex_queue` invokes `codex queue --thread <thread> --message <event>` and does not simulate
  keyboard input.

Arguments are passed directly to `subprocess`; no shell command is constructed. A Codex recipient
must use `codex_queue`; `tmux_keys` is not considered a reliable Codex activation path.

Every delivery has an Event ID. The receiver must claim it before acting:

```bash
relay claim EV0042
```

Duplicate claims are harmless. A failed send remains in `pending_delivery`, which already blocks
every other state transition. After the Owner repairs the configured target or session, the original
sender runs:

```bash
relay retry
```

Relay does not create an Owner hold while a delivery is pending. The necessary delivery error may be
reported to the Owner; an unexplained mismatch is inspected with `relay status`, then retried or
claimed using the recorded Event ID. Finding text, source content, and Owner decisions are never
placed in transport messages.

## 14. Atomic state without locks

Relay uses no watcher, daemon, server, polling process, or lock file. The protocol permits only one
state-changing command after the active role finishes its work. Concurrent invocation is explicitly
unsupported.

Each JSON file is written to a temporary file in the same directory, flushed, and atomically moved
into place with `os.replace`. A transition that changes both Checkpoints and `state.json` first writes
a replayable `.relay/transition.json` intent. Every later command that reads Relay state completes
that intent first. If interruption happens after an event is delivered but before delivery state is
saved, retrying may deliver the same Event ID again; duplicate claims remain harmless.

The intent journal protects sequential commands from interrupted writes. It is not a lock and does
not make concurrent invocation safe. Supporting multiple processes or remote agents would require a
new concurrency-control design.

## 15. Commands

From the project root, the entry point is:

```bash
python3 docs/ai-collaboration/tools/relay.py
```

The documentation uses `relay` as shorthand for that command.

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
relay resume --decision <decision> --to <engineer|checker>
relay resume-deferred --checkpoint <checkpoint-id> --decision <owner-decision>
relay adopt-idle-head --decision <owner-decision>
relay retry
relay show [checkpoint-id]
relay status
relay scan-work --plan <work-plan.md> --gate <gate-id>
relay scan-all-work --plan <work-plan.md>
```

Read-only `show`, `status`, `scan-work`, and `scan-all-work` do not change turn ownership. Other
commands enforce the current tmux pane role and reject an unclaimed incoming event.

## 16. Silent handoff and owner reports

Normal agent-to-agent turns end with a Relay command. No routine prose handoff report is written or
printed. Git and the Checkpoint contain the durable details.

**HARD RULE — NO EXPLANATORY HANDOFF REPORT:** for `review`, `revise`, `accept`, and an
Engineer-raised `hold`, the role that
just completed its work must output only the exact Relay event line. It must not add acknowledgments,
headings, explanations, summaries, test results, file lists, commit details, status prose, or next
steps anywhere in the completion handoff. It also must not send a prose "work completed" message
immediately before running Relay. Relay success is the completion notice.

After a successful routine handoff, the final assistant message must contain exactly the single
Relay event line returned by the command and nothing else. It must not summarize scope, files,
commits, tests, findings, or next steps. This rule applies even when the host normally expects a
final response. An Owner message that asks a question or requires a decision remains an explicit
exception and receives a concise answer.

Agent-authored Checkpoint text is concise English written directly for agent use. Dynamic product
or user content is never translated or rewritten. Owner-facing conversation may use the Owner's
preferred language; any decision summary stored in Relay is written as concise English.

The Checker provides a concise human-readable report when the Owner requests progress or must make a
decision. A larger report may be created at a major milestone. It does not duplicate complete diffs
or routine test output.

Necessary errors and blockers may be printed when Git, tmux, Relay, or a required test fails.

## 17. Initialization and activation checks

Before activation:

- [ ] The Owner completes `PROJECT_PROFILE.md` without placeholders.
- [ ] Relay unit and adversarial tests pass.
- [ ] A temporary Git repository dry run covers start, review, revise, repeat finding, accept, idle,
      hold, resume, deferral recovery, interrupted-write replay, failed delivery, retry, and duplicate
      claim.
- [ ] Engineer and Checker pane IDs resolve correctly in a disposable real-tmux smoke test.
- [ ] `.relay/`, the real `relay.toml`, and any active local Markdown work plan are ignored by Git.
- [ ] Git guards reject dirty, detached, divergent, merged, and changed-during-review states.
- [ ] The Owner fills both real tmux targets, transports, and any Codex thread in `relay.toml`;
      Relay validates them without guessing.
- [ ] The Owner reviews the dry-run result and explicitly activates Relay for the project.

After activation:

- no new routine reports or completion signals are published;
- no watcher is started;
- the first real work round begins only through `relay start`.

## 18. Version history

| Version | Date | Change |
|---|---|---|
| 3.1.0 | 2026-09-03 | Extracts Relay into a project-agnostic standard, adds project and work-plan templates plus whole-plan unfinished-work inventory, defines alternative-planner compatibility, adds deferred-work resumption and interrupted-transition replay, and removes legacy report publishers from the distributable package. |
| 3.0.9 candidate | 2026-08-31 | Adds an Owner-authorized, Checker-only deferral path for reviewed work blocked by an unavailable dependency; partial commits remain while findings and plan items stay open. |
| 3.0.8 candidate | 2026-08-30 | Adds a narrow, audited Checker recovery for an Owner-approved descendant HEAD while Relay is idle between rounds. |
| 3.0.6 candidate | 2026-08-25 | Adds a mandatory phase-scoped unfinished-work scan before every configured phase Gate. |
| 3.0.5 candidate | 2026-08-25 | Adds Checker-owned `open`/`completed` finding status and bulk `relay complete`; Engineer review handoffs cannot alter status, and acceptance rejects any open finding. |
| 3.0.4 candidate | 2026-08-25 | Adds an Owner-authorized, Checker-only cancellation path for a mistaken untouched assignment; it preserves the cancelled Checkpoint and never discards committed or reviewed work. |
| 3.0.3 candidate | 2026-08-24 | Makes Owner-hold authority one-way: the Engineer emits only the hold event; the Checker alone explains options and recommendations to the Owner and alone resumes the Checkpoint. |
| 3.0.2 candidate | 2026-08-24 | Makes the ban on explanatory completion reports a hard rule: routine review, revise, and accept handoffs contain only the exact Relay event line, with no prose completion message before or after it. |
| 3.0.1 candidate | 2026-08-23 | Adds explicit per-agent transports, uses the Codex session queue instead of simulated Enter for Codex activation, and makes the single-line final response mandatory. |
| 3.0.0 candidate | 2026-08-23 | Replaces report/signal polling with local tmux Relay, Owner-written TOML agent mapping, one Checkpoint per round, Git guards, silent handoff, Event claim/retry, and mandatory Owner hold. |
| 2.2.5 | 2026-08-17 | Last report-and-signal protocol. Retained only as legacy history during transition. |

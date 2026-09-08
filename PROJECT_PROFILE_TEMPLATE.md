# Project Collaboration Profile

> Owner-maintained policy file. Copy this file to
> `docs/ai-collaboration/PROJECT_PROFILE.md`, replace every `{{...}}` placeholder, and keep it
> consistent with the work plan and Relay configuration. Relay does not parse this file.

## 1. Project identity

| Item | Project value |
|---|---|
| Project name | `{{PROJECT_NAME}}` |
| Owner | `{{OWNER_NAME_OR_ROLE}}` |
| Objective | `{{ONE_SENTENCE_OBJECTIVE}}` |
| Explicit non-goals | `{{NON_GOALS}}` |
| Completion criteria | `{{DONE_CRITERIA}}` |

## 2. Sources of truth

List exact repository paths or named Owner decisions from highest to lowest priority.

1. `{{HIGHEST_PRIORITY_REQUIREMENTS}}`
2. `{{DESIGN_OR_CONTRACT_DOCUMENT}}`
3. `{{WORK_PLAN_PATH}}`
4. `{{OTHER_SOURCE_OR_NONE}}`

When sources conflict, both agents stop and request an Owner decision. A Relay Checkpoint cannot
override these sources.

## 3. Roles and path ownership

### Engineer

- Responsibility: `{{ENGINEER_RESPONSIBILITY}}`
- Allowed paths: `{{ENGINEER_ALLOWED_PATHS}}`
- Shared paths requiring coordination: `{{SHARED_PATHS}}`

### Checker

- Responsibility: independent review, risk-based verification, findings, gates, and next-round
  selection.
- Product-code write policy: `{{CHECKER_PRODUCT_WRITE_POLICY}}`
- Progress-file write policy: only the Checker changes active work-plan checkbox status; define any
  additional progress-file authority separately without weakening that rule.

### Protected and excluded paths

- `{{PROTECTED_OR_OUT_OF_SCOPE_PATHS}}`
- Secrets and local credentials are always excluded unless the Owner explicitly defines a safe,
  narrower operation.

## 4. Round policy

| Item | Project value |
|---|---|
| Work-round ID convention | `{{WORK_ROUND_ID_CONVENTION}}` |
| Phase-gate ID convention | `{{MUST_CONTAIN_DELIMITED_GATE_TOKEN_OR_NOT_APPLICABLE}}` |
| Maximum round size | `{{TIME_OR_SCOPE_LIMIT}}` |
| Planning backend | `{{MARKDOWN_OR_EXTERNAL_SYSTEM}}` |
| Work-plan path | `{{WORK_PLAN_PATH}}` |
| Gate scan command | `{{BUILT_IN_EQUIVALENT_OR_NOT_APPLICABLE}}` |
| Gate acceptance evidence | `{{GATE_EVIDENCE_OR_NOT_APPLICABLE}}` |

Every round has one independently verifiable objective. The Checker splits work before assignment
when the objective exceeds this limit.

## 5. Required verification

Record exact commands. Use `not applicable` with a reason instead of leaving a row blank.

| Scope | Required commands or checks |
|---|---|
| Focused tests | `{{FOCUSED_TEST_COMMANDS}}` |
| Full tests | `{{FULL_TEST_COMMANDS}}` |
| Static analysis | `{{STATIC_ANALYSIS_COMMANDS}}` |
| Formatting | `{{FORMAT_COMMANDS}}` |
| Build or packaging | `{{BUILD_COMMANDS}}` |
| Security or adversarial checks | `{{SECURITY_COMMANDS}}` |
| Gate-only checks | `{{GATE_COMMANDS_OR_NOT_APPLICABLE}}` |

## 6. Authority matrix

Use `Owner only`, `allowed when assigned`, or another explicit rule. Silence means not authorized.

| Action | Authority |
|---|---|
| Create or edit product files | `{{PRODUCT_WRITE_AUTHORITY}}` |
| Update active work-plan checkbox status | `Checker only` |
| Commit | `{{COMMIT_AUTHORITY}}` |
| Pull, fetch, or rebase | `{{SYNC_AUTHORITY}}` |
| Push | `{{PUSH_AUTHORITY}}` |
| Merge | `{{MERGE_AUTHORITY}}` |
| Deploy or publish | `{{DEPLOY_AUTHORITY}}` |
| Destructive actions | `{{DESTRUCTIVE_AUTHORITY}}` |
| External services or spending | `{{EXTERNAL_SERVICE_AUTHORITY}}` |

## 7. Owner decisions and stop conditions

| Item | Project value |
|---|---|
| Owner decision channel | `{{OWNER_CHANNEL}}` |
| Required decision format | `{{DECISION_FORMAT_OR_FREE_TEXT}}` |
| Pause conditions | `{{PAUSE_CONDITIONS}}` |
| Cancellation conditions | `{{CANCEL_CONDITIONS}}` |
| Maximum wait policy | `{{WAIT_POLICY}}` |

Unclear requirements, conflicting authority, unexplained Git state, unavailable dependencies, and
material design choices enter `owner_hold`. Only the Checker explains the decision to the Owner and
resumes the workflow after explicit approval.

## 8. Activation approval

- [ ] Every placeholder in this profile has been resolved.
- [ ] The work plan follows `WORK_PLAN_TEMPLATE.md` or documents an equivalent planning backend.
- [ ] `relay.toml` contains the correct branch, panes, transports, and optional Codex sessions.
- [ ] `.relay/`, the real `relay.toml`, and any active local Markdown work plan are ignored.
- [ ] Unit and required smoke tests pass.
- [ ] Both agents have read the protocol and this profile.
- [ ] Owner explicitly authorizes the first Relay round.

Owner activation decision: `{{OWNER_ACTIVATION_DECISION}}`

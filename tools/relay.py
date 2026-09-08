"""Local turn-based collaboration relay for two tmux-hosted CLI agents."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "relay/v1"
CONFIG_SCHEMA_VERSION = "relay-config/v2"
TRANSITION_SCHEMA_VERSION = "relay-transition/v1"
DELIVERY_TRANSPORTS = {"tmux_keys", "codex_queue"}
WORK_ROUND_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
CHECKPOINT_RE = re.compile(r"CP[0-9]{3,}\Z")
EVENT_RE = re.compile(r"EV[0-9]{4,}\Z")
FINDING_RE = re.compile(r"F[0-9]{3,}\Z")
CHECKLIST_RE = re.compile(r"^\s*[-*+]\s+\[(?P<mark>[ xX])\]\s+(?P<label>\S.*)\s*$")
CHECKLIST_ID_RE = re.compile(r"^(?:\*\*|`)?(?P<id>[A-Za-z0-9][A-Za-z0-9._-]{0,127})")
PHASE_HEADING_RE = re.compile(r"^##\s+\S")
GATE_ID_RE = re.compile(r"(?:^|[._-])GATE(?:[._-]|$)", re.IGNORECASE)
FINDING_STATUSES = {"open", "completed"}
CHECKPOINT_STATUSES = {
    "engineering",
    "review",
    "revise",
    "owner_hold",
    "accepted",
    "cancelled",
    "deferred",
}


class RelayError(RuntimeError):
    """A safe, user-facing Relay failure."""


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _run(
    argv: list[str],
    *,
    cwd: Path | None = None,
    input_text: str | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        argv,
        cwd=cwd,
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "command failed"
        raise RelayError(f"{argv[0]} failed: {detail}")
    return result


def _git(root: Path, *args: str, check: bool = True) -> str:
    result = _run(["git", *args], cwd=root, check=check)
    return result.stdout.strip()


def _tmux(*args: str, input_text: str | None = None) -> str:
    return _run(["tmux", *args], input_text=input_text).stdout.strip()


def _codex_queue(thread: str, message: str) -> str:
    """Queue one event through Codex's session-aware transport."""
    return _run(["codex", "queue", "--thread", thread, "--message", message]).stdout.strip()


def _repository_root(path: Path) -> Path:
    candidate = path.resolve()
    result = _run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=candidate,
        check=False,
    )
    if result.returncode != 0:
        raise RelayError("project root is not inside a Git repository")
    return Path(result.stdout.strip()).resolve()


def _relay_dir(root: Path) -> Path:
    return root / ".relay"


def _config_path(root: Path) -> Path:
    return root / "docs" / "ai-collaboration" / "relay.toml"


def _state_path(root: Path) -> Path:
    return _relay_dir(root) / "state.json"


def _transition_path(root: Path) -> Path:
    return _relay_dir(root) / "transition.json"


def _checkpoint_path(root: Path, checkpoint_id: str) -> Path:
    if not CHECKPOINT_RE.fullmatch(checkpoint_id):
        raise RelayError(f"invalid checkpoint ID: {checkpoint_id}")
    return _relay_dir(root) / "checkpoints" / f"{checkpoint_id}.json"


def _atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, indent=2, ensure_ascii=False) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RelayError(f"{label} does not exist: {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise RelayError(f"{label} is unreadable: {path}") from exc
    if not isinstance(value, dict):
        raise RelayError(f"{label} must contain a JSON object")
    return value


def _load_config(root: Path) -> dict[str, Any]:
    path = _config_path(root)
    try:
        value = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RelayError(f"Owner configuration does not exist: {path}") from exc
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise RelayError(f"Owner configuration is unreadable: {path}") from exc
    if not isinstance(value, dict) or value.get("schema_version") != CONFIG_SCHEMA_VERSION:
        raise RelayError("unsupported Relay owner-configuration schema")
    unknown_fields = set(value) - {"schema_version", "branch", "agents"}
    if unknown_fields:
        names = ", ".join(sorted(unknown_fields))
        raise RelayError(f"Owner configuration has unknown top-level fields: {names}")
    branch = value.get("branch")
    agents = value.get("agents")
    if not isinstance(branch, str) or not branch.strip():
        raise RelayError("Owner configuration must name a Git branch")
    if not isinstance(agents, dict):
        raise RelayError("Owner configuration must contain an agents table")
    unknown_roles = set(agents) - {"engineer", "checker"}
    if unknown_roles:
        names = ", ".join(sorted(unknown_roles))
        raise RelayError(f"Owner configuration has unknown agent roles: {names}")
    parsed_agents: dict[str, dict[str, str]] = {}
    for role in ("engineer", "checker"):
        entry = agents.get(role)
        if not isinstance(entry, dict):
            raise RelayError(f"Owner must configure the {role} agent table")
        unknown = set(entry) - {"target", "transport", "thread"}
        if unknown:
            raise RelayError(f"Owner configuration has unknown {role} agent fields")
        target = entry.get("target")
        if not isinstance(target, str) or not target.strip():
            raise RelayError(f"Owner must configure the {role} tmux target")
        transport = entry.get("transport")
        if transport not in DELIVERY_TRANSPORTS:
            raise RelayError(f"Owner must configure the {role} delivery transport")
        parsed = {
            "target": _validate_one_line(target, f"{role} tmux target", 200),
            "transport": str(transport),
        }
        thread = entry.get("thread")
        if transport == "codex_queue":
            if not isinstance(thread, str) or not thread.strip():
                raise RelayError(f"Owner must configure the {role} Codex thread")
            parsed["thread"] = _validate_one_line(
                thread,
                f"{role} Codex thread",
                200,
            )
        elif thread is not None:
            raise RelayError(f"{role} thread is only valid with codex_queue")
        parsed_agents[role] = parsed
    if parsed_agents["engineer"]["target"] == parsed_agents["checker"]["target"]:
        raise RelayError("Engineer and Checker must use different tmux targets")
    if parsed_agents["engineer"].get("thread") is not None and parsed_agents["engineer"].get(
        "thread"
    ) == parsed_agents["checker"].get("thread"):
        raise RelayError("Engineer and Checker must use different Codex threads")
    digest = hashlib.sha256(str(root).encode()).hexdigest()[:12]
    return {
        "repository": str(root),
        "branch": _validate_one_line(branch, "Git branch", 255),
        "buffer": f"relay-{digest}",
        "agents": parsed_agents,
    }


def _load_context(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    _recover_transition(root)
    config = _load_config(root)
    state = _load_json(_state_path(root), "Relay state")
    if state.get("schema_version") != SCHEMA_VERSION:
        raise RelayError("unsupported Relay state schema")
    for counter in ("next_checkpoint", "next_event"):
        if not isinstance(state.get(counter), int) or int(state[counter]) < 1:
            raise RelayError(f"Relay state has an invalid {counter}")
    current = state.get("current_checkpoint")
    if current is not None and (
        not isinstance(current, str) or not CHECKPOINT_RE.fullmatch(current)
    ):
        raise RelayError("Relay state has an invalid current Checkpoint")
    idle_head_adoptions = state.get("idle_head_adoptions", [])
    if not isinstance(idle_head_adoptions, list) or any(
        not isinstance(item, dict)
        or not all(
            isinstance(item.get(field), str)
            for field in ("previous_head", "head", "decision", "created_at")
        )
        for item in idle_head_adoptions
    ):
        raise RelayError("Relay state has invalid idle-head adoption history")
    pending = state.get("pending_delivery")
    if pending is not None:
        if not isinstance(pending, dict):
            raise RelayError("Relay state has an invalid pending delivery")
        if (
            not EVENT_RE.fullmatch(str(pending.get("id", "")))
            or pending.get("source") not in {"engineer", "checker"}
            or pending.get("target") not in {"engineer", "checker"}
            or not isinstance(pending.get("message"), str)
        ):
            raise RelayError("Relay state has an invalid pending delivery")
    return config, state


def _save_state(root: Path, state: dict[str, Any]) -> None:
    _atomic_write_json(_state_path(root), state)


def _recover_transition(root: Path) -> None:
    """Finish an interrupted multi-file state transition before reading Relay state."""
    path = _transition_path(root)
    if not path.exists():
        return
    intent = _load_json(path, "Relay transition")
    if intent.get("schema_version") != TRANSITION_SCHEMA_VERSION:
        raise RelayError("unsupported Relay transition schema")
    state = intent.get("state")
    checkpoints = intent.get("checkpoints")
    if not isinstance(state, dict) or not isinstance(checkpoints, list):
        raise RelayError("Relay transition is invalid")
    if state.get("schema_version") != SCHEMA_VERSION:
        raise RelayError("Relay transition contains an invalid state")
    for checkpoint in checkpoints:
        if not isinstance(checkpoint, dict):
            raise RelayError("Relay transition contains an invalid Checkpoint")
        checkpoint_id = checkpoint.get("id")
        if not isinstance(checkpoint_id, str) or not CHECKPOINT_RE.fullmatch(checkpoint_id):
            raise RelayError("Relay transition contains an invalid Checkpoint")
        _save_checkpoint(root, checkpoint)
    _save_state(root, state)
    path.unlink(missing_ok=True)


def _commit_transition(
    root: Path,
    state: dict[str, Any],
    checkpoints: list[dict[str, Any]],
) -> None:
    """Persist related Checkpoint and state updates through a replayable intent."""
    intent = {
        "schema_version": TRANSITION_SCHEMA_VERSION,
        "state": state,
        "checkpoints": checkpoints,
        "created_at": _now(),
    }
    _atomic_write_json(_transition_path(root), intent)
    for checkpoint in checkpoints:
        _save_checkpoint(root, checkpoint)
    _save_state(root, state)
    _transition_path(root).unlink(missing_ok=True)


def _finding_items(checkpoint: dict[str, Any]) -> list[dict[str, Any]]:
    """Return every live finding object stored in review history or the draft."""
    items: list[dict[str, Any]] = []
    for review in checkpoint.get("reviews", []):
        if isinstance(review, dict):
            items.extend(item for item in review.get("findings", []) if isinstance(item, dict))
    items.extend(item for item in checkpoint.get("draft_findings", []) if isinstance(item, dict))
    return items


def _set_finding_status(checkpoint: dict[str, Any], finding_id: str, status: str) -> bool:
    """Update all appearances of one finding and report whether it exists."""
    found = False
    for item in _finding_items(checkpoint):
        if item.get("id") == finding_id:
            item["status"] = status
            found = True
    return found


def _migrate_finding_statuses(checkpoint: dict[str, Any]) -> None:
    """Add live statuses to Checkpoints created before finding status existed.

    Old Relay cleared ``open_findings`` when the Engineer handed a revision back. If such a
    Checkpoint is currently under review, the latest revision's IDs are still awaiting Checker
    verification and therefore remain open. All other historical findings were already passed
    over by a later Checker decision and migrate to completed.
    """
    open_ids = {item for item in checkpoint.get("open_findings", []) if isinstance(item, str)}
    open_ids.update(
        str(item.get("id"))
        for item in checkpoint.get("draft_findings", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    )
    if checkpoint.get("status") == "review" and checkpoint.get("revises"):
        latest = checkpoint["revises"][-1]
        if isinstance(latest, dict):
            open_ids.update(item for item in latest.get("findings", []) if isinstance(item, str))

    for item in _finding_items(checkpoint):
        if "status" not in item:
            item["status"] = "open" if item.get("id") in open_ids else "completed"


def _load_checkpoint(root: Path, checkpoint_id: str) -> dict[str, Any]:
    checkpoint = _load_json(
        _checkpoint_path(root, checkpoint_id),
        f"Checkpoint {checkpoint_id}",
    )
    if checkpoint.get("schema_version") != SCHEMA_VERSION:
        raise RelayError(f"unsupported schema in {checkpoint_id}")
    if checkpoint.get("id") != checkpoint_id:
        raise RelayError(f"Checkpoint identity mismatch in {checkpoint_id}")
    if not WORK_ROUND_RE.fullmatch(str(checkpoint.get("work_round", ""))):
        raise RelayError(f"invalid work-round ID in {checkpoint_id}")
    if checkpoint.get("status") not in CHECKPOINT_STATUSES:
        raise RelayError(f"invalid status in {checkpoint_id}")
    if not isinstance(checkpoint.get("base"), str) or not isinstance(checkpoint.get("head"), str):
        raise RelayError(f"invalid Git boundary in {checkpoint_id}")
    for field in (
        "reviews",
        "revises",
        "holds",
        "head_adoptions",
        "deferred_resumptions",
        "draft_findings",
        "open_findings",
    ):
        if field in {"head_adoptions", "deferred_resumptions"} and field not in checkpoint:
            checkpoint[field] = []
        if not isinstance(checkpoint.get(field), list):
            raise RelayError(f"invalid {field} in {checkpoint_id}")
    _migrate_finding_statuses(checkpoint)
    for item in _finding_items(checkpoint):
        if item.get("status") not in FINDING_STATUSES:
            raise RelayError(f"invalid finding status in {checkpoint_id}")
    if not isinstance(checkpoint.get("next_finding"), int):
        raise RelayError(f"invalid finding counter in {checkpoint_id}")
    return checkpoint


def _save_checkpoint(root: Path, checkpoint: dict[str, Any]) -> None:
    checkpoint_id = str(checkpoint.get("id", ""))
    _atomic_write_json(_checkpoint_path(root, checkpoint_id), checkpoint)


def _active_checkpoint(root: Path, state: dict[str, Any]) -> dict[str, Any]:
    checkpoint_id = state.get("current_checkpoint")
    if not isinstance(checkpoint_id, str):
        raise RelayError("there is no active Checkpoint")
    return _load_checkpoint(root, checkpoint_id)


def _current_role(config: dict[str, Any]) -> str:
    pane = os.environ.get("TMUX_PANE")
    if not pane:
        raise RelayError("state-changing commands must run inside a configured tmux pane")
    agents = config.get("agents")
    if not isinstance(agents, dict):
        raise RelayError("Relay config has no agent mapping")
    for role in ("engineer", "checker"):
        entry = agents.get(role)
        if not isinstance(entry, dict) or not isinstance(entry.get("target"), str):
            continue
        try:
            resolved = _resolve_pane(entry["target"])
        except RelayError:
            continue
        if resolved == pane:
            return role
    raise RelayError(f"tmux pane {pane} is not configured as an agent")


def _require_role(actual: str, expected: str) -> None:
    if actual != expected:
        raise RelayError(f"{expected} owns this command; current role is {actual}")


def _require_no_pending(state: dict[str, Any]) -> None:
    pending = state.get("pending_delivery")
    if pending is not None:
        event_id = pending.get("id", "unknown") if isinstance(pending, dict) else "unknown"
        raise RelayError(f"event {event_id} must be claimed or retried first")


def _validate_one_line(value: str, label: str, maximum: int) -> str:
    normalized = value.strip()
    if not normalized or "\n" in normalized or "\r" in normalized:
        raise RelayError(f"{label} must be one non-empty line")
    if len(normalized) > maximum:
        raise RelayError(f"{label} exceeds {maximum} characters")
    return normalized


def _validate_work_round(value: str) -> str:
    if not WORK_ROUND_RE.fullmatch(value):
        raise RelayError("work-round ID must use letters, digits, dot, underscore, or hyphen")
    return value


def _work_plan_path(root: Path, value: Path) -> Path:
    """Resolve a work plan without allowing a scan outside the repository."""
    root = root.resolve()
    candidate = value if value.is_absolute() else root / value
    candidate = candidate.resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise RelayError("work plan must be inside the project repository") from exc
    return candidate


def _checklist_id(label: str) -> str | None:
    """Read the leading work ID without matching references later in its description."""
    match = CHECKLIST_ID_RE.match(label)
    return match.group("id") if match is not None else None


def _is_gate_id(identifier: str | None) -> bool:
    return identifier is not None and GATE_ID_RE.search(identifier) is not None


def _validate_engineering_round(value: str) -> str:
    """Reject phase Gates before Relay can deliver them to the Engineer."""
    work_round = _validate_work_round(value)
    if _is_gate_id(work_round):
        raise RelayError("phase Gate is checker-owned and cannot be dispatched as engineering work")
    return work_round


def scan_unfinished_work(root: Path, plan: Path, gate: str) -> str:
    """Fail when the phase ending at ``gate`` still has unchecked items.

    A phase begins after the preceding gate checklist item and ends before the named gate. The first
    phase begins at its nearest preceding level-two heading; nested headings do not reset it.
    Earlier and later phases are excluded. Prose such as "deferred" does not silently waive an open
    checkbox inside the phase; the Owner must resolve that item in the project plan.
    """
    gate = _validate_work_round(gate)
    if not _is_gate_id(gate):
        raise RelayError("gate ID must contain GATE as a dot, underscore, or hyphen token")
    path = _work_plan_path(root, plan)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise RelayError(f"work plan does not exist: {path}") from exc
    except (OSError, UnicodeError) as exc:
        raise RelayError(f"work plan is unreadable: {path}") from exc

    checklist: list[tuple[int, str, str, str | None]] = []
    gates: list[int] = []
    for line_number, line in enumerate(lines, start=1):
        match = CHECKLIST_RE.fullmatch(line)
        if match is None:
            continue
        mark = match.group("mark")
        label = match.group("label")
        identifier = _checklist_id(label)
        checklist.append((line_number, mark, label, identifier))
        if identifier == gate:
            gates.append(line_number)

    if not gates:
        raise RelayError(f"gate {gate} is not a checklist item in {path}")
    if len(gates) != 1:
        locations = ", ".join(str(item) for item in gates)
        raise RelayError(f"gate {gate} appears more than once in {path}: {locations}")

    gate_line = gates[0]
    previous_gates = [
        line_number
        for line_number, _mark, _label, identifier in checklist
        if line_number < gate_line and _is_gate_id(identifier)
    ]
    if previous_gates:
        phase_start = max(previous_gates)
    else:
        headings = [
            line_number
            for line_number, line in enumerate(lines[: gate_line - 1], start=1)
            if PHASE_HEADING_RE.match(line)
        ]
        if not headings:
            raise RelayError("the first Gate must follow a level-two phase heading")
        phase_start = max(headings)

    earlier = [item for item in checklist if phase_start < item[0] < gate_line]
    unfinished = [item for item in earlier if item[1] == " "]
    relative = path.relative_to(root)
    if unfinished:
        details = "\n".join(
            f"{relative}:{line_number}: {label}"
            for line_number, _mark, label, _identifier in unfinished
        )
        raise RelayError(
            f"unfinished current-phase items exist before {gate} ({len(unfinished)}):\n{details}"
        )

    return f"WORK_SCAN_PASS gate={gate} checked={len(earlier)} plan={relative.as_posix()}"


def scan_all_unfinished_work(root: Path, plan: Path) -> str:
    """List every unchecked checklist item in a work plan without changing state."""
    path = _work_plan_path(root, plan)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise RelayError(f"work plan does not exist: {path}") from exc
    except (OSError, UnicodeError) as exc:
        raise RelayError(f"work plan is unreadable: {path}") from exc

    unfinished: list[tuple[int, str]] = []
    for line_number, line in enumerate(lines, start=1):
        match = CHECKLIST_RE.fullmatch(line)
        if match is not None and match.group("mark") == " ":
            unfinished.append((line_number, match.group("label")))

    relative = path.relative_to(root)
    summary = f"WORK_SCAN_ALL unfinished={len(unfinished)} plan={relative.as_posix()}"
    if not unfinished:
        return summary
    details = "\n".join(f"{relative}:{line_number}: {label}" for line_number, label in unfinished)
    return f"{summary}\n{details}"


def _resolve_pane(target: str) -> str:
    pane = _tmux("display-message", "-p", "-t", target, "#{pane_id}")
    if not pane.startswith("%"):
        raise RelayError(f"tmux target did not resolve to a pane: {target}")
    return pane


def _deliver(config: dict[str, Any], target_role: str, message: str) -> None:
    agents = config["agents"]
    agent = agents[target_role]
    if agent["transport"] == "codex_queue":
        _codex_queue(agent["thread"], message)
        return
    pane = _resolve_pane(agent["target"])
    buffer_name = str(config["buffer"])
    _tmux("load-buffer", "-b", buffer_name, "-", input_text=message)
    _tmux("paste-buffer", "-b", buffer_name, "-t", pane, "-d")
    _tmux("send-keys", "-t", pane, "Enter")


def _prepare_delivery(
    state: dict[str, Any],
    *,
    source_role: str,
    target_role: str,
    message_prefix: str,
) -> str:
    _require_no_pending(state)
    event_id = f"EV{int(state['next_event']):04d}"
    state["next_event"] = int(state["next_event"]) + 1
    message = f"{message_prefix} {event_id}"
    state["pending_delivery"] = {
        "id": event_id,
        "source": source_role,
        "target": target_role,
        "message": message,
        "created_at": _now(),
        "delivered_at": None,
    }
    return message


def _send_pending(root: Path, config: dict[str, Any], state: dict[str, Any]) -> str:
    pending = state.get("pending_delivery")
    if not isinstance(pending, dict):
        raise RelayError("there is no pending delivery")
    event_id = str(pending["id"])
    target_role = str(pending["target"])
    message = str(pending["message"])
    try:
        _deliver(config, target_role, message)
    except RelayError as exc:
        raise RelayError(f"event {event_id} is pending delivery: {exc}") from exc
    pending["delivered_at"] = _now()
    _save_state(root, state)
    return message


def _commit_and_deliver(
    root: Path,
    config: dict[str, Any],
    state: dict[str, Any],
    checkpoints: list[dict[str, Any]],
    *,
    source_role: str,
    target_role: str,
    message_prefix: str,
) -> str:
    _prepare_delivery(
        state,
        source_role=source_role,
        target_role=target_role,
        message_prefix=message_prefix,
    )
    _commit_transition(root, state, checkpoints)
    return _send_pending(root, config, state)


def _assert_git_common(root: Path, config: dict[str, Any]) -> str:
    actual_root = _repository_root(root)
    if actual_root != root:
        raise RelayError("command is not running from the configured repository")
    branch = _git(root, "symbolic-ref", "--quiet", "--short", "HEAD", check=False)
    if not branch:
        raise RelayError("detached HEAD is not allowed")
    if branch != config.get("branch"):
        raise RelayError(f"expected branch {config.get('branch')}, found {branch}")
    if _git(root, "diff", "--name-only", "--diff-filter=U"):
        raise RelayError("unresolved merge entries are not allowed")
    dirty = _git(root, "status", "--porcelain=v1", "--untracked-files=all")
    if dirty:
        first = dirty.splitlines()[0]
        raise RelayError(f"worktree is not clean: {first}")
    return _git(root, "rev-parse", "HEAD")


def _commits_between(root: Path, previous: str, current: str) -> list[str]:
    ancestry = _run(
        ["git", "merge-base", "--is-ancestor", previous, current],
        cwd=root,
        check=False,
    )
    if ancestry.returncode != 0:
        raise RelayError("new HEAD is not a descendant of the previous head")
    if previous == current:
        raise RelayError("engineering handoff requires at least one new commit")
    merges = _git(root, "rev-list", "--merges", f"{previous}..{current}")
    if merges:
        raise RelayError("merge commits are not allowed inside a work round")
    output = _git(root, "rev-list", "--reverse", f"{previous}..{current}")
    commits = output.splitlines() if output else []
    if not commits:
        raise RelayError("no revision commits were found")
    return commits


def _assert_reviewed_head(
    root: Path,
    config: dict[str, Any],
    checkpoint: dict[str, Any],
) -> None:
    current = _assert_git_common(root, config)
    if current != checkpoint.get("head"):
        raise RelayError("Git HEAD changed after the review handoff")


def adopt_idle_head(root: Path, decision: str) -> str:
    """Recover an idle Relay after an explicitly Owner-approved descendant integration."""
    config, state = _load_context(root)
    role = _current_role(config)
    _require_role(role, "checker")
    _require_no_pending(state)
    if state.get("current_checkpoint") is not None:
        raise RelayError("idle-head adoption requires Relay to be idle")

    current = _assert_git_common(root, config)
    previous = str(state.get("last_accepted"))
    if current == previous:
        raise RelayError("Git HEAD already matches the last accepted commit")
    ancestry = _run(
        ["git", "merge-base", "--is-ancestor", previous, current],
        cwd=root,
        check=False,
    )
    if ancestry.returncode != 0:
        raise RelayError("adopted idle HEAD must descend from the last accepted commit")

    adoption = {
        "previous_head": previous,
        "head": current,
        "decision": _validate_one_line(decision, "owner adoption decision", 1000),
        "created_at": _now(),
    }
    history = state.setdefault("idle_head_adoptions", [])
    if not isinstance(history, list):
        raise RelayError("Relay state has invalid idle-head adoption history")
    history.append(adoption)
    state["last_accepted"] = current
    _save_state(root, state)
    return f"ADOPT_IDLE_HEAD {current}"


def initialize(root: Path) -> None:
    root = _repository_root(root)
    if _state_path(root).exists():
        raise RelayError("Relay is already initialized")
    config = _load_config(root)
    branch = str(config["branch"])
    actual_branch = _git(root, "symbolic-ref", "--quiet", "--short", "HEAD", check=False)
    if not actual_branch:
        raise RelayError("detached HEAD is not allowed")
    if actual_branch != branch:
        raise RelayError(f"expected branch {branch}, found {actual_branch}")
    if _git(root, "status", "--porcelain=v1", "--untracked-files=all"):
        raise RelayError("initialize Relay only from a clean worktree")
    ignored = _run(
        ["git", "check-ignore", "-q", ".relay/state.json"],
        cwd=root,
        check=False,
    )
    if ignored.returncode != 0:
        raise RelayError(".relay/ must be ignored by Git before initialization")
    config_relative = _config_path(root).relative_to(root).as_posix()
    config_ignored = _run(
        ["git", "check-ignore", "-q", "--", config_relative],
        cwd=root,
        check=False,
    )
    if config_ignored.returncode != 0:
        raise RelayError("the real relay.toml must be ignored by Git before initialization")
    engineer_target = config["agents"]["engineer"]["target"]
    checker_target = config["agents"]["checker"]["target"]
    engineer_pane = _resolve_pane(engineer_target)
    checker_pane = _resolve_pane(checker_target)
    if engineer_pane == checker_pane:
        raise RelayError("Engineer and Checker must use different tmux panes")
    state = {
        "schema_version": SCHEMA_VERSION,
        "last_accepted": _git(root, "rev-parse", "HEAD"),
        "current_checkpoint": None,
        "next_checkpoint": 1,
        "next_event": 1,
        "pending_delivery": None,
        "last_delivery": None,
        "idle_head_adoptions": [],
    }
    _save_state(root, state)


def start_round(root: Path, work_round: str) -> str:
    config, state = _load_context(root)
    role = _current_role(config)
    _require_role(role, "checker")
    _require_no_pending(state)
    if state.get("current_checkpoint") is not None:
        raise RelayError("a Checkpoint is already active")
    current = _assert_git_common(root, config)
    if current != state.get("last_accepted"):
        raise RelayError("HEAD differs from the last accepted commit")
    work_round = _validate_engineering_round(work_round)
    checkpoint_id = f"CP{int(state['next_checkpoint']):03d}"
    state["next_checkpoint"] = int(state["next_checkpoint"]) + 1
    checkpoint = {
        "schema_version": SCHEMA_VERSION,
        "id": checkpoint_id,
        "work_round": work_round,
        "base": current,
        "head": current,
        "status": "engineering",
        "reviews": [],
        "revises": [],
        "holds": [],
        "head_adoptions": [],
        "deferred_resumptions": [],
        "draft_findings": [],
        "open_findings": [],
        "next_finding": 1,
        "created_at": _now(),
    }
    state["current_checkpoint"] = checkpoint_id
    return _commit_and_deliver(
        root,
        config,
        state,
        [checkpoint],
        source_role="checker",
        target_role="engineer",
        message_prefix=f"WORK {work_round} {checkpoint_id}",
    )


def claim_event(root: Path, event_id: str) -> str:
    if not EVENT_RE.fullmatch(event_id):
        raise RelayError(f"invalid event ID: {event_id}")
    config, state = _load_context(root)
    role = _current_role(config)
    pending = state.get("pending_delivery")
    if pending is None:
        previous = state.get("last_delivery")
        if isinstance(previous, dict) and previous.get("id") == event_id:
            if previous.get("target") != role:
                raise RelayError("event belongs to the other role")
            return f"ALREADY_CLAIMED {event_id}"
        raise RelayError(f"event is not pending: {event_id}")
    if not isinstance(pending, dict) or pending.get("id") != event_id:
        expected = pending.get("id", "unknown") if isinstance(pending, dict) else "unknown"
        raise RelayError(f"expected event {expected}, not {event_id}")
    if pending.get("target") != role:
        raise RelayError("event belongs to the other role")
    pending["claimed_at"] = _now()
    state["last_delivery"] = pending
    state["pending_delivery"] = None
    _save_state(root, state)
    return f"CLAIMED {event_id}"


def handoff_review(root: Path) -> str:
    config, state = _load_context(root)
    role = _current_role(config)
    _require_role(role, "engineer")
    _require_no_pending(state)
    checkpoint = _active_checkpoint(root, state)
    previous_status = checkpoint.get("status")
    if previous_status not in {"engineering", "revise"}:
        raise RelayError(f"cannot request review from state {previous_status}")
    current = _assert_git_common(root, config)
    previous_head = str(checkpoint["head"])
    commits = _commits_between(root, previous_head, current)
    if previous_status == "revise":
        findings = checkpoint.get("open_findings")
        if not isinstance(findings, list) or not findings:
            raise RelayError("revision state has no open findings")
        checkpoint["revises"].append(
            {
                "findings": list(findings),
                "commits": commits,
                "created_at": _now(),
            }
        )
    checkpoint["head"] = current
    checkpoint["status"] = "review"
    checkpoint["draft_findings"] = []
    return _commit_and_deliver(
        root,
        config,
        state,
        [checkpoint],
        source_role="engineer",
        target_role="checker",
        message_prefix=f"REVIEW {checkpoint['id']}",
    )


def add_finding(
    root: Path,
    *,
    location: str,
    problem: str,
    finding_id: str | None,
) -> str:
    config, state = _load_context(root)
    role = _current_role(config)
    _require_role(role, "checker")
    _require_no_pending(state)
    checkpoint = _active_checkpoint(root, state)
    if checkpoint.get("status") != "review":
        raise RelayError("findings may be added only during review")
    _assert_reviewed_head(root, config, checkpoint)
    location = _validate_one_line(location, "location", 300)
    problem = _validate_one_line(problem, "problem", 500)
    draft = checkpoint.get("draft_findings")
    if not isinstance(draft, list):
        raise RelayError("Checkpoint draft findings are invalid")
    if finding_id is None:
        finding_id = f"F{int(checkpoint['next_finding']):03d}"
        checkpoint["next_finding"] = int(checkpoint["next_finding"]) + 1
    else:
        if not FINDING_RE.fullmatch(finding_id):
            raise RelayError(f"invalid finding ID: {finding_id}")
        if any(item.get("id") == finding_id for item in draft if isinstance(item, dict)):
            raise RelayError(f"finding is already present in this review: {finding_id}")
        known: set[object] = set()
        for review in checkpoint.get("reviews", []):
            if not isinstance(review, dict):
                continue
            for item in review.get("findings", []):
                if isinstance(item, dict):
                    known.add(item.get("id"))
        if finding_id not in known:
            raise RelayError(f"finding does not exist in an earlier review: {finding_id}")
        _set_finding_status(checkpoint, finding_id, "open")
    draft.append(
        {
            "id": finding_id,
            "location": location,
            "problem": problem,
            "status": "open",
        }
    )
    open_findings = checkpoint.get("open_findings")
    if not isinstance(open_findings, list):
        raise RelayError("Checkpoint open findings are invalid")
    if finding_id not in open_findings:
        open_findings.append(finding_id)
    _save_checkpoint(root, checkpoint)
    return finding_id


def complete_findings(root: Path, finding_ids: list[str]) -> str:
    """Mark verified findings completed; this command belongs only to the Checker."""
    config, state = _load_context(root)
    role = _current_role(config)
    _require_role(role, "checker")
    _require_no_pending(state)
    checkpoint = _active_checkpoint(root, state)
    if checkpoint.get("status") != "review":
        raise RelayError("findings may be completed only during review")
    _assert_reviewed_head(root, config, checkpoint)
    if not finding_ids:
        raise RelayError("name at least one finding to complete")
    if len(set(finding_ids)) != len(finding_ids):
        raise RelayError("finding IDs to complete must be unique")

    draft_ids = {
        item.get("id") for item in checkpoint.get("draft_findings", []) if isinstance(item, dict)
    }
    open_findings = checkpoint.get("open_findings")
    if not isinstance(open_findings, list):
        raise RelayError("Checkpoint open findings are invalid")

    for finding_id in finding_ids:
        if not FINDING_RE.fullmatch(finding_id):
            raise RelayError(f"invalid finding ID: {finding_id}")
        if finding_id in draft_ids:
            raise RelayError(f"draft finding cannot be completed: {finding_id}")
        if finding_id not in open_findings:
            raise RelayError(f"finding is not open: {finding_id}")
        if not _set_finding_status(checkpoint, finding_id, "completed"):
            raise RelayError(f"finding does not exist: {finding_id}")

    completed = set(finding_ids)
    checkpoint["open_findings"] = [item for item in open_findings if item not in completed]
    _save_checkpoint(root, checkpoint)
    return "COMPLETED " + " ".join(finding_ids)


def request_revision(root: Path) -> str:
    config, state = _load_context(root)
    role = _current_role(config)
    _require_role(role, "checker")
    _require_no_pending(state)
    checkpoint = _active_checkpoint(root, state)
    if checkpoint.get("status") != "review":
        raise RelayError("revision may be requested only during review")
    _assert_reviewed_head(root, config, checkpoint)
    findings = checkpoint.get("draft_findings")
    open_findings = checkpoint.get("open_findings")
    if not isinstance(findings, list) or not isinstance(open_findings, list):
        raise RelayError("Checkpoint findings are invalid")
    if not open_findings:
        raise RelayError("at least one open finding is required for revision")
    checkpoint["reviews"].append(
        {
            "head": checkpoint["head"],
            "result": "revise",
            "findings": findings,
            "created_at": _now(),
        }
    )
    checkpoint["draft_findings"] = []
    checkpoint["status"] = "revise"
    return _commit_and_deliver(
        root,
        config,
        state,
        [checkpoint],
        source_role="checker",
        target_role="engineer",
        message_prefix=f"REVISE {checkpoint['id']}",
    )


def accept_checkpoint(root: Path, *, next_round: str | None, idle: bool) -> str:
    config, state = _load_context(root)
    role = _current_role(config)
    _require_role(role, "checker")
    _require_no_pending(state)
    checkpoint = _active_checkpoint(root, state)
    if checkpoint.get("status") != "review":
        raise RelayError("acceptance may occur only during review")
    _assert_reviewed_head(root, config, checkpoint)
    if checkpoint.get("draft_findings"):
        raise RelayError("current findings must be revised before acceptance")
    if checkpoint.get("open_findings"):
        raise RelayError("all open findings must be completed before acceptance")
    if idle == (next_round is not None):
        raise RelayError("choose exactly one of --next or --idle")
    if next_round is not None:
        next_round = _validate_engineering_round(next_round)
    checkpoint["reviews"].append(
        {
            "head": checkpoint["head"],
            "result": "accept",
            "findings": [],
            "created_at": _now(),
        }
    )
    checkpoint["status"] = "accepted"
    checkpoint["accepted_at"] = _now()
    old_checkpoint_id = str(checkpoint["id"])
    state["last_accepted"] = checkpoint["head"]
    if idle:
        state["current_checkpoint"] = None
        _commit_transition(root, state, [checkpoint])
        return f"ACCEPT {old_checkpoint_id} IDLE"
    new_checkpoint_id = f"CP{int(state['next_checkpoint']):03d}"
    state["next_checkpoint"] = int(state["next_checkpoint"]) + 1
    new_checkpoint = {
        "schema_version": SCHEMA_VERSION,
        "id": new_checkpoint_id,
        "work_round": next_round,
        "base": checkpoint["head"],
        "head": checkpoint["head"],
        "status": "engineering",
        "reviews": [],
        "revises": [],
        "holds": [],
        "head_adoptions": [],
        "deferred_resumptions": [],
        "draft_findings": [],
        "open_findings": [],
        "next_finding": 1,
        "created_at": _now(),
    }
    state["current_checkpoint"] = new_checkpoint_id
    return _commit_and_deliver(
        root,
        config,
        state,
        [checkpoint, new_checkpoint],
        source_role="checker",
        target_role="engineer",
        message_prefix=(f"ACCEPT {old_checkpoint_id} WORK {next_round} {new_checkpoint_id}"),
    )


def owner_hold(root: Path, reason: str) -> str:
    config, state = _load_context(root)
    role = _current_role(config)
    _require_no_pending(state)
    checkpoint = _active_checkpoint(root, state)
    status = str(checkpoint.get("status"))
    owner = "engineer" if status in {"engineering", "revise"} else "checker"
    if status not in {"engineering", "revise", "review"}:
        raise RelayError(f"owner hold is not valid from state {status}")
    _require_role(role, owner)
    reason = _validate_one_line(reason, "owner-hold reason", 500)
    hold_id = f"H{len(checkpoint['holds']) + 1:03d}"
    checkpoint["holds"].append(
        {
            "id": hold_id,
            "raised_by": role,
            "reason": reason,
            "previous_status": status,
            "created_at": _now(),
            "decision": None,
        }
    )
    checkpoint["status"] = "owner_hold"
    if role == "checker":
        _save_checkpoint(root, checkpoint)
        return f"OWNER_HOLD {checkpoint['id']}"
    return _commit_and_deliver(
        root,
        config,
        state,
        [checkpoint],
        source_role="engineer",
        target_role="checker",
        message_prefix=f"OWNER_HOLD {checkpoint['id']}",
    )


def cancel_checkpoint(
    root: Path,
    *,
    decision: str,
    next_round: str | None,
    idle: bool,
) -> str:
    """Cancel a mistaken, untouched engineering assignment by explicit Owner decision.

    This is intentionally narrower than a general rollback.  It is valid only while an
    engineering-originated Owner hold is active, before the Checkpoint has produced a commit,
    review, revision, or finding.  Product work is never discarded or accepted implicitly.
    """
    config, state = _load_context(root)
    role = _current_role(config)
    _require_role(role, "checker")
    _require_no_pending(state)
    checkpoint = _active_checkpoint(root, state)
    if checkpoint.get("status") != "owner_hold":
        raise RelayError("cancellation requires an active owner hold")
    holds = checkpoint.get("holds")
    if not isinstance(holds, list) or not holds:
        raise RelayError("Checkpoint owner-hold history is invalid")
    hold = holds[-1]
    if hold.get("decision") is not None:
        raise RelayError("the current owner hold already has a decision")
    if hold.get("previous_status") != "engineering":
        raise RelayError("only an untouched engineering assignment may be cancelled")
    if checkpoint.get("head") != checkpoint.get("base"):
        raise RelayError("a Checkpoint with a handed-off head cannot be cancelled")
    if any(
        checkpoint.get(field) for field in ("reviews", "revises", "draft_findings", "open_findings")
    ):
        raise RelayError("a Checkpoint with review history cannot be cancelled")
    if idle == (next_round is not None):
        raise RelayError("choose exactly one of --next or --idle")
    if next_round is not None:
        next_round = _validate_engineering_round(next_round)
    decision = _validate_one_line(decision, "owner cancellation decision", 1000)

    current = _assert_git_common(root, config)
    if current != checkpoint.get("base") or current != state.get("last_accepted"):
        raise RelayError("Git HEAD differs from the untouched Checkpoint base")

    decided_at = _now()
    hold["decision"] = decision
    hold["decided_at"] = decided_at
    hold["resolved_as"] = "cancelled"
    hold["next_round"] = next_round
    checkpoint["status"] = "cancelled"
    checkpoint["cancelled_at"] = decided_at
    old_checkpoint_id = str(checkpoint["id"])

    if idle:
        state["current_checkpoint"] = None
        _commit_transition(root, state, [checkpoint])
        return f"CANCEL {old_checkpoint_id} IDLE"

    new_checkpoint_id = f"CP{int(state['next_checkpoint']):03d}"
    state["next_checkpoint"] = int(state["next_checkpoint"]) + 1
    new_checkpoint = {
        "schema_version": SCHEMA_VERSION,
        "id": new_checkpoint_id,
        "work_round": next_round,
        "base": current,
        "head": current,
        "status": "engineering",
        "reviews": [],
        "revises": [],
        "holds": [],
        "head_adoptions": [],
        "deferred_resumptions": [],
        "draft_findings": [],
        "open_findings": [],
        "next_finding": 1,
        "created_at": _now(),
    }
    state["current_checkpoint"] = new_checkpoint_id
    return _commit_and_deliver(
        root,
        config,
        state,
        [checkpoint, new_checkpoint],
        source_role="checker",
        target_role="engineer",
        message_prefix=(f"CANCEL {old_checkpoint_id} WORK {next_round} {new_checkpoint_id}"),
    )


def defer_checkpoint(root: Path, *, decision: str, next_round: str) -> str:
    """Defer reviewed work on an unavailable dependency by explicit Owner decision.

    Unlike cancellation, deferral retains the reviewed HEAD as the next Checkpoint base and
    deliberately leaves findings open. The unchecked work-plan item still blocks the phase Gate.
    """
    config, state = _load_context(root)
    role = _current_role(config)
    _require_role(role, "checker")
    _require_no_pending(state)
    checkpoint = _active_checkpoint(root, state)
    if checkpoint.get("status") != "owner_hold":
        raise RelayError("deferral requires an active owner hold")
    holds = checkpoint.get("holds")
    if not isinstance(holds, list) or not holds:
        raise RelayError("Checkpoint owner-hold history is invalid")
    hold = holds[-1]
    if hold.get("decision") is not None:
        raise RelayError("the current owner hold already has a decision")
    if not checkpoint.get("open_findings"):
        raise RelayError("deferral requires at least one open finding")
    draft = checkpoint.get("draft_findings")
    reviews = checkpoint.get("reviews")
    if not isinstance(draft, list) or not isinstance(reviews, list):
        raise RelayError("Checkpoint findings are invalid")
    if draft:
        reviews.append(
            {
                "head": checkpoint["head"],
                "result": "revise",
                "findings": draft,
                "created_at": _now(),
            }
        )
        checkpoint["draft_findings"] = []

    decision = _validate_one_line(decision, "owner deferral decision", 1000)
    next_round = _validate_engineering_round(next_round)
    current = _assert_git_common(root, config)
    if current != checkpoint.get("head"):
        raise RelayError("Git HEAD changed after the review handoff")

    decided_at = _now()
    hold["decision"] = decision
    hold["decided_at"] = decided_at
    hold["resolved_as"] = "deferred"
    hold["next_round"] = next_round
    checkpoint["status"] = "deferred"
    checkpoint["deferred_at"] = decided_at
    old_checkpoint_id = str(checkpoint["id"])

    # The partial commit is retained as a reviewed baseline. The open finding and unchecked
    # work-plan item preserve the obligation; neither is converted into acceptance.
    state["last_accepted"] = current
    new_checkpoint_id = f"CP{int(state['next_checkpoint']):03d}"
    state["next_checkpoint"] = int(state["next_checkpoint"]) + 1
    new_checkpoint = {
        "schema_version": SCHEMA_VERSION,
        "id": new_checkpoint_id,
        "work_round": next_round,
        "base": current,
        "head": current,
        "status": "engineering",
        "reviews": [],
        "revises": [],
        "holds": [],
        "head_adoptions": [],
        "deferred_resumptions": [],
        "draft_findings": [],
        "open_findings": [],
        "next_finding": 1,
        "created_at": _now(),
    }
    state["current_checkpoint"] = new_checkpoint_id
    return _commit_and_deliver(
        root,
        config,
        state,
        [checkpoint, new_checkpoint],
        source_role="checker",
        target_role="engineer",
        message_prefix=(f"DEFER {old_checkpoint_id} WORK {next_round} {new_checkpoint_id}"),
    )


def resume_from_hold(root: Path, decision: str, target: str) -> str:
    if target not in {"engineer", "checker"}:
        raise RelayError("resume target must be engineer or checker")
    config, state = _load_context(root)
    role = _current_role(config)
    _require_role(role, "checker")
    _require_no_pending(state)
    checkpoint = _active_checkpoint(root, state)
    if checkpoint.get("status") != "owner_hold":
        raise RelayError("there is no active owner hold")
    decision = _validate_one_line(decision, "owner decision", 1000)
    holds = checkpoint.get("holds")
    if not isinstance(holds, list) or not holds:
        raise RelayError("Checkpoint owner-hold history is invalid")
    hold = holds[-1]
    if hold.get("decision") is not None:
        raise RelayError("the current owner hold already has a decision")
    previous_status = hold.get("previous_status")
    if previous_status in {"engineering", "revise"} and target != "engineer":
        raise RelayError(f"a hold from {previous_status} must resume to the Engineer")
    if previous_status not in {"engineering", "revise", "review"}:
        raise RelayError("the current owner hold has an invalid previous state")
    hold["decision"] = decision
    hold["decided_at"] = _now()
    hold["resume_to"] = target
    if target == "engineer" and previous_status in {"engineering", "revise"}:
        checkpoint["status"] = previous_status
    elif target == "engineer" and previous_status == "review":
        # A Checker may discover both implementation findings and an Owner decision in the
        # same review.  The findings are still drafts while the hold is active.  Sending the
        # decision straight to the Engineer must first persist that review exactly as
        # `request_revision` would; otherwise `handoff_review` clears the drafts on the next
        # handoff and leaves only orphan IDs in `open_findings`.
        draft = checkpoint.get("draft_findings")
        open_findings = checkpoint.get("open_findings")
        reviews = checkpoint.get("reviews")
        if not isinstance(draft, list) or not isinstance(open_findings, list):
            raise RelayError("Checkpoint findings are invalid")
        if not isinstance(reviews, list):
            raise RelayError("Checkpoint reviews are invalid")
        if draft:
            reviews.append(
                {
                    "head": checkpoint["head"],
                    "result": "revise",
                    "findings": draft,
                    "created_at": _now(),
                }
            )
            checkpoint["draft_findings"] = []
        checkpoint["status"] = "revise" if open_findings else "engineering"
    else:
        checkpoint["status"] = "review"
    if target == "checker":
        _save_checkpoint(root, checkpoint)
        return f"RESUME {checkpoint['id']} CHECKER"
    return _commit_and_deliver(
        root,
        config,
        state,
        [checkpoint],
        source_role="checker",
        target_role="engineer",
        message_prefix=f"RESUME {checkpoint['id']} ENGINEER",
    )


def resume_deferred_checkpoint(root: Path, checkpoint_id: str, decision: str) -> str:
    """Resume one deferred Checkpoint after its dependency becomes available."""
    config, state = _load_context(root)
    role = _current_role(config)
    _require_role(role, "checker")
    _require_no_pending(state)
    if state.get("current_checkpoint") is not None:
        raise RelayError("deferred work may resume only while Relay is idle")

    checkpoint = _load_checkpoint(root, checkpoint_id)
    if checkpoint.get("status") != "deferred":
        raise RelayError(f"Checkpoint {checkpoint_id} is not deferred")
    if not checkpoint.get("open_findings"):
        raise RelayError("deferred Checkpoint has no open finding to resume")

    current = _assert_git_common(root, config)
    if current != state.get("last_accepted"):
        raise RelayError("HEAD differs from the last accepted commit")
    previous = str(checkpoint["head"])
    ancestry = _run(
        ["git", "merge-base", "--is-ancestor", previous, current],
        cwd=root,
        check=False,
    )
    if ancestry.returncode != 0:
        raise RelayError("current HEAD does not descend from the deferred Checkpoint")

    resumed_at = _now()
    checkpoint["deferred_resumptions"].append(
        {
            "previous_head": previous,
            "head": current,
            "decision": _validate_one_line(decision, "owner resume decision", 1000),
            "created_at": resumed_at,
        }
    )
    checkpoint["head"] = current
    checkpoint["status"] = "revise"
    checkpoint["resumed_at"] = resumed_at
    state["current_checkpoint"] = checkpoint_id
    return _commit_and_deliver(
        root,
        config,
        state,
        [checkpoint],
        source_role="checker",
        target_role="engineer",
        message_prefix=f"RESUME_DEFERRED {checkpoint_id} WORK {checkpoint['work_round']}",
    )


def retry_delivery(root: Path) -> str:
    config, state = _load_context(root)
    role = _current_role(config)
    pending = state.get("pending_delivery")
    if not isinstance(pending, dict):
        raise RelayError("there is no pending delivery")
    if pending.get("source") != role:
        raise RelayError("only the event sender may retry delivery")
    message = str(pending.get("message", ""))
    target = str(pending.get("target", ""))
    _deliver(config, target, message)
    pending["delivered_at"] = _now()
    _save_state(root, state)
    return message


def show_checkpoint(root: Path, checkpoint_id: str | None) -> str:
    _config, state = _load_context(root)
    if checkpoint_id is None:
        current = state.get("current_checkpoint")
        if not isinstance(current, str):
            raise RelayError("there is no active Checkpoint")
        checkpoint_id = current
    checkpoint = _load_checkpoint(root, checkpoint_id)
    return json.dumps(checkpoint, indent=2, ensure_ascii=False)


def show_status(root: Path) -> str:
    _config, state = _load_context(root)
    checkpoint_id = state.get("current_checkpoint")
    if isinstance(checkpoint_id, str):
        checkpoint = _load_checkpoint(root, checkpoint_id)
        phase = checkpoint.get("status")
        work_round = checkpoint.get("work_round")
        head = checkpoint.get("head")
    else:
        phase = "idle"
        work_round = "-"
        head = state.get("last_accepted")
    pending = state.get("pending_delivery")
    pending_id = pending.get("id") if isinstance(pending, dict) else "-"
    return (
        f"status={phase} checkpoint={checkpoint_id or '-'} round={work_round} "
        f"head={head} pending={pending_id}"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="relay")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("init")

    start_parser = commands.add_parser("start")
    start_parser.add_argument("--round", dest="work_round", required=True)

    claim_parser = commands.add_parser("claim")
    claim_parser.add_argument("event_id")

    commands.add_parser("review")

    finding_parser = commands.add_parser("finding")
    finding_parser.add_argument("problem")
    finding_parser.add_argument("--id", dest="finding_id")
    finding_parser.add_argument("--location", required=True)

    complete_parser = commands.add_parser("complete")
    complete_parser.add_argument("finding_ids", nargs="+")

    commands.add_parser("revise")

    accept_parser = commands.add_parser("accept")
    accept_choice = accept_parser.add_mutually_exclusive_group(required=True)
    accept_choice.add_argument("--next", dest="next_round")
    accept_choice.add_argument("--idle", action="store_true")

    hold_parser = commands.add_parser("hold")
    hold_parser.add_argument("--owner", dest="reason", required=True)

    cancel_parser = commands.add_parser("cancel")
    cancel_parser.add_argument("--decision", required=True)
    cancel_choice = cancel_parser.add_mutually_exclusive_group(required=True)
    cancel_choice.add_argument("--next", dest="next_round")
    cancel_choice.add_argument("--idle", action="store_true")

    defer_parser = commands.add_parser("defer")
    defer_parser.add_argument("--decision", required=True)
    defer_parser.add_argument("--next", dest="next_round", required=True)

    resume_parser = commands.add_parser("resume")
    resume_parser.add_argument("--decision", required=True)
    resume_parser.add_argument("--to", choices=("engineer", "checker"), required=True)

    resume_deferred_parser = commands.add_parser("resume-deferred")
    resume_deferred_parser.add_argument("--checkpoint", required=True)
    resume_deferred_parser.add_argument("--decision", required=True)

    adopt_idle_parser = commands.add_parser("adopt-idle-head")
    adopt_idle_parser.add_argument("--decision", required=True)

    commands.add_parser("retry")

    show_parser = commands.add_parser("show")
    show_parser.add_argument("checkpoint_id", nargs="?")

    commands.add_parser("status")

    scan_parser = commands.add_parser("scan-work")
    scan_parser.add_argument("--plan", type=Path, required=True)
    scan_parser.add_argument("--gate", required=True)

    scan_all_parser = commands.add_parser("scan-all-work")
    scan_all_parser.add_argument("--plan", type=Path, required=True)
    return parser


def _dispatch(args: argparse.Namespace) -> str:
    root = _repository_root(args.project_root)
    if args.command == "init":
        initialize(root)
        return "INITIALIZED"
    if args.command == "start":
        return start_round(root, args.work_round)
    if args.command == "claim":
        return claim_event(root, args.event_id)
    if args.command == "review":
        return handoff_review(root)
    if args.command == "finding":
        return add_finding(
            root,
            location=args.location,
            problem=args.problem,
            finding_id=args.finding_id,
        )
    if args.command == "complete":
        return complete_findings(root, args.finding_ids)
    if args.command == "revise":
        return request_revision(root)
    if args.command == "accept":
        return accept_checkpoint(root, next_round=args.next_round, idle=args.idle)
    if args.command == "hold":
        return owner_hold(root, args.reason)
    if args.command == "cancel":
        return cancel_checkpoint(
            root,
            decision=args.decision,
            next_round=args.next_round,
            idle=args.idle,
        )
    if args.command == "defer":
        return defer_checkpoint(
            root,
            decision=args.decision,
            next_round=args.next_round,
        )
    if args.command == "resume":
        return resume_from_hold(root, args.decision, args.to)
    if args.command == "resume-deferred":
        return resume_deferred_checkpoint(root, args.checkpoint, args.decision)
    if args.command == "adopt-idle-head":
        return adopt_idle_head(root, args.decision)
    if args.command == "retry":
        return retry_delivery(root)
    if args.command == "show":
        return show_checkpoint(root, args.checkpoint_id)
    if args.command == "status":
        return show_status(root)
    if args.command == "scan-work":
        return scan_unfinished_work(root, args.plan, args.gate)
    if args.command == "scan-all-work":
        return scan_all_unfinished_work(root, args.plan)
    raise RelayError(f"unsupported command: {args.command}")


def main(argv: list[str] | None = None) -> int:
    try:
        result = _dispatch(_parser().parse_args(argv))
    except RelayError as exc:
        print(f"RELAY_ERROR: {exc}", file=sys.stderr)
        return 2
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Publish one reviewer completion JSON. This program never reads signals."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


ROLE = "reviewer"
REPORT_DIRECTORY = Path("docs/ai-collaboration/reports/reviewer")
SIGNAL_DIRECTORY = Path("docs/ai-collaboration/signals")


class PublishError(RuntimeError):
    """The completion signal cannot be published safely."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PublishError(message)


def publish(project_root: Path, report_argument: Path) -> Path:
    root = project_root.resolve(strict=True)
    expected_directory = (root / REPORT_DIRECTORY).resolve(strict=True)
    signal_directory = (root / SIGNAL_DIRECTORY).resolve(strict=True)
    require(expected_directory.is_dir(), f"missing report directory: {expected_directory}")
    require(signal_directory.is_dir(), f"missing signal directory: {signal_directory}")

    supplied_report = report_argument if report_argument.is_absolute() else root / report_argument
    report = supplied_report.resolve(strict=True)
    require(report.is_file(), f"report is not a regular file: {report}")
    require(report.is_relative_to(expected_directory), f"report must be inside {expected_directory}")
    require(report.suffix.lower() == ".md", "report filename must end with .md")
    require(not report.name.endswith(".draft.md"), "a .draft.md report cannot be published")

    relative_report = report.relative_to(root).as_posix()
    signal_path = signal_directory / f"{report.stem}.{ROLE}.complete.json"
    require(not signal_path.exists(), f"signal already exists: {signal_path}")

    report_bytes = report.read_bytes()
    require(bool(report_bytes), "report cannot be empty")
    report_hash = hashlib.sha256(report_bytes).hexdigest()
    payload = {
        "schema_version": "ai-collaboration-completion/v1",
        "source": ROLE,
        "report_path": relative_report,
        "report_sha256": report_hash,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "complete": True,
    }
    signal_bytes = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")

    original_mode = stat.S_IMODE(report.stat().st_mode)
    locked_mode = original_mode & ~(
        stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH
    )
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{signal_path.name}.",
        suffix=".pending",
        dir=signal_directory,
    )
    temporary_path = Path(temporary_name)
    report_locked = False
    try:
        with os.fdopen(descriptor, "wb") as temporary_file:
            temporary_file.write(signal_bytes)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.chmod(temporary_path, 0o444)

        os.chmod(report, locked_mode)
        report_locked = True
        require(report.read_bytes() == report_bytes, "report changed while the signal was being prepared")
        require(not signal_path.exists(), f"signal already exists: {signal_path}")

        # Publishing the final JSON path is the last filesystem mutation.
        os.replace(temporary_path, signal_path)
    except Exception:
        if temporary_path.exists():
            temporary_path.unlink()
        if report_locked:
            os.chmod(report, original_mode)
        raise

    return signal_path.relative_to(root)


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish a reviewer completion JSON as the final action.")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--report", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        signal_path = publish(arguments.project_root, arguments.report)
    except (OSError, PublishError, ValueError) as error:
        print(f"COMPLETION-NOT-PUBLISHED: {error}", file=sys.stderr)
        return 2
    print(signal_path.as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

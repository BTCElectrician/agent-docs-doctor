"""Console entry point for Agent Docs Doctor."""

from __future__ import annotations

import argparse
import hashlib
import os
import platform
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any

from .core import (
    INVENTORY_VERSION,
    SCHEMA_VERSION,
    build_audit,
    build_inventory,
    dump_json,
    validate_audit,
)
from .installer import (
    CLIENT_PATHS,
    apply_install,
    apply_uninstall,
    bundled_skill_root,
    plan_as_dict,
    plan_install,
    plan_uninstall,
)
from .presentation import audit_text
from .report_validation import (
    decode_report,
    read_report_file,
    read_report_stdin,
)
from .version import __version__

sys.dont_write_bytecode = True


def _configure_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="agent-docs-doctor",
        description="Audit agent-facing repository documentation without changing it.",
    )
    result.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = result.add_subparsers(dest="command", required=True)

    inventory = sub.add_parser("inventory", help="emit the deterministic inventory")
    inventory.add_argument("root", nargs="?", default=".", help="repository root (default: .)")
    inventory.add_argument("--pretty", action="store_true", help="pretty-print JSON")

    audit = sub.add_parser("audit", help="audit a repository without changing it")
    audit.add_argument("root", nargs="?", default=".", help="repository root (default: .)")
    audit.add_argument(
        "--format",
        choices=("json", "text"),
        default="json",
        help="output format (default: json)",
    )
    audit.add_argument("--pretty", action="store_true", help="pretty-print JSON")

    validate = sub.add_parser("validate-report", help="validate an audit JSON report")
    validate.add_argument("report", help="path to report JSON, or - for stdin")

    doctor = sub.add_parser("doctor", help="check this installation and its read-only contract")
    doctor.add_argument("--format", choices=("text", "json"), default="text")

    install = sub.add_parser("install-skill", help="preview or install the user-level Agent Skill")
    install.add_argument("--client", choices=tuple(CLIENT_PATHS), required=True)
    install.add_argument("--update", action="store_true", help="preview an update with backup")
    install.add_argument(
        "--apply",
        metavar="PLAN_TOKEN",
        help="apply only the operation matching this previewed current-plan fingerprint",
    )
    install.add_argument("--format", choices=("text", "json"), default="text")

    uninstall = sub.add_parser(
        "uninstall-skill",
        help="preview or move a managed skill to a reversible backup",
    )
    uninstall.add_argument("--client", choices=tuple(CLIENT_PATHS), required=True)
    uninstall.add_argument(
        "--apply",
        metavar="PLAN_TOKEN",
        help="apply only the operation matching this previewed current-plan fingerprint",
    )
    uninstall.add_argument("--format", choices=("text", "json"), default="text")
    return result


def _doctor_report() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    try:
        skill_root = bundled_skill_root()
    except OSError:
        checks.append(
            {
                "name": "bundled-skill",
                "status": "error",
                "detail": "bundled skill files could not be verified",
            }
        )
    else:
        checks.append(
            {
                "name": "bundled-skill",
                "status": "ok",
                "detail": f"SKILL.md available at {skill_root.name}",
            }
        )
    checks.append(
        {
            "name": "python",
            "status": "ok" if sys.version_info >= (3, 10) else "error",
            "detail": platform.python_version(),
        }
    )
    try:
        with tempfile.TemporaryDirectory(prefix="agent-docs-doctor-probe-") as value:
            probe = Path(value)
            authority = probe / "AGENTS.md"
            authority.write_text("# Disposable read-only audit probe\n", encoding="utf-8")
            before = _probe_snapshot(probe)
            report = build_audit(probe)
            errors = validate_audit(report)
            after = _probe_snapshot(probe)
            if errors:
                raise ValueError(f"generated probe report was invalid: {errors[0]}")
            if before != after:
                raise OSError("the disposable audit probe changed its repository")
    except (OSError, ValueError):
        checks.append(
            {
                "name": "audit-mode",
                "status": "error",
                "detail": "the disposable audit probe failed",
            }
        )
    else:
        checks.append(
            {
                "name": "audit-mode",
                "status": "ok",
                "detail": "disposable audit left its captured filesystem snapshot unchanged",
            }
        )
    try:
        with tempfile.TemporaryDirectory(prefix="agent-docs-doctor-install-preview-") as value:
            home = Path(value)
            before = _probe_snapshot(home)
            install_plan = plan_install("codex", home=home)
            after = _probe_snapshot(home)
            if install_plan.state != "ready" or not install_plan.plan_token:
                raise ValueError("installer preview did not produce a bound ready plan")
            if before != after:
                raise OSError("the disposable installer preview changed its home")
    except (OSError, ValueError):
        checks.append(
            {
                "name": "installer-preview",
                "status": "error",
                "detail": "the disposable installer preview failed",
            }
        )
    else:
        checks.append(
            {
                "name": "installer-preview",
                "status": "ok",
                "detail": "disposable preview produced a state-bound plan without applying it",
            }
        )
    return {
        "status": "ok" if all(check["status"] == "ok" for check in checks) else "error",
        "version": __version__,
        "audit_schema": SCHEMA_VERSION,
        "inventory_schema": INVENTORY_VERSION,
        "platform": platform.system().lower(),
        "checks": checks,
    }


def _doctor_text(report: dict[str, Any]) -> str:
    lines = [f"Agent Docs Doctor {report['version']}", f"Status: {report['status'].upper()}"]
    for check in report["checks"]:
        marker = "OK" if check["status"] == "ok" else "ERROR"
        lines.append(f"- {marker} {check['name']}: {check['detail']}")
    lines.append("No repository files were changed. The audit-mode check used only a disposable probe.")
    return "\n".join(lines) + "\n"


def _probe_snapshot(root: Path) -> tuple[tuple[Any, ...], ...]:
    entries: list[tuple[Any, ...]] = []
    paths = [root, *root.rglob("*")]
    for path in sorted(paths, key=lambda item: item.as_posix()):
        relative = "." if path == root else path.relative_to(root).as_posix()
        value = path.lstat()
        kind = stat.S_IFMT(value.st_mode)
        digest = ""
        link_target = ""
        if stat.S_ISREG(value.st_mode):
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        elif stat.S_ISLNK(value.st_mode):
            link_target = os.readlink(path)
        entries.append(
            (
                relative,
                kind,
                stat.S_IMODE(value.st_mode),
                value.st_size,
                value.st_mtime_ns,
                value.st_ctime_ns,
                getattr(value, "st_uid", None),
                getattr(value, "st_gid", None),
                getattr(value, "st_flags", None),
                getattr(value, "st_file_attributes", None),
                digest,
                link_target,
            )
        )
    return tuple(entries)


def _plan_text(plan: dict[str, Any], applied: bool) -> str:
    verb = plan["action"].capitalize()
    lines = [
        f"Agent Docs Doctor skill {verb.lower()}",
        f"Client: {plan['client']}",
        f"Target: {plan['target']}",
        f"State: {plan['state']}",
    ]
    if plan["files"]:
        lines.append(f"Managed files: {len(plan['files'])}")
    if plan["backup"]:
        lines.append(f"Reversible backup: {plan['backup']}")
    if plan["message"]:
        lines.append(plan["message"])
    if not applied:
        lines.append("Nothing was changed.")
        if plan["state"] == "ready":
            lines.append(f"Current-plan fingerprint: {plan['plan_token']}")
            lines.append(
                f"After reviewing this preview, run the same command with --apply {plan['plan_token']}."
            )
    return "\n".join(lines) + "\n"


def _emit_plan(plan: Any, output_format: str, applied: bool) -> None:
    value = plan_as_dict(plan)
    if output_format == "json":
        sys.stdout.write(dump_json(value, pretty=True))
    else:
        sys.stdout.write(_plan_text(value, applied))


def main(argv: list[str] | None = None) -> int:
    _configure_utf8()
    args = parser().parse_args(argv)
    try:
        if args.command == "inventory":
            sys.stdout.write(dump_json(build_inventory(args.root), args.pretty))
            return 0
        if args.command == "audit":
            report = build_audit(args.root)
            report_errors = validate_audit(report)
            if report_errors:
                raise ValueError(
                    "generated report failed internal validation: " + "; ".join(report_errors[:3])
                )
            if args.format == "text":
                sys.stdout.write(audit_text(report))
            else:
                sys.stdout.write(dump_json(report, args.pretty))
            return 0
        if args.command == "validate-report":
            raw = (
                read_report_stdin(sys.stdin.buffer)
                if args.report == "-"
                else read_report_file(Path(args.report))
            )
            errors = validate_audit(decode_report(raw))
            if errors:
                for error in errors:
                    print(f"error: {error}", file=sys.stderr)
                return 1
            print("valid")
            return 0
        if args.command == "doctor":
            report = _doctor_report()
            if args.format == "json":
                sys.stdout.write(dump_json(report, pretty=True))
            else:
                sys.stdout.write(_doctor_text(report))
            return 0 if report["status"] == "ok" else 1
        if args.command == "install-skill":
            plan = plan_install(args.client, update=args.update)
            if args.apply and plan.state == "ready":
                plan = apply_install(plan, args.apply)
            _emit_plan(
                plan,
                args.format,
                bool(args.apply and plan.state.startswith("applied")),
            )
            return 0 if plan.state in {"ready", "applied", "already-installed"} else 1
        plan = plan_uninstall(args.client)
        if args.apply and plan.state == "ready":
            plan = apply_uninstall(plan, args.apply)
        _emit_plan(
            plan,
            args.format,
            bool(args.apply and plan.state.startswith("applied")),
        )
        return 0 if plan.state in {"ready", "applied", "not-installed"} else 1
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

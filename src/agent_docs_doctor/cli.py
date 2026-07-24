"""Console entry point for Agent Docs Doctor."""

from __future__ import annotations

import argparse
import json
import platform
import sys
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
    install.add_argument("--apply", action="store_true", help="apply the displayed operation")
    install.add_argument("--format", choices=("text", "json"), default="text")

    uninstall = sub.add_parser(
        "uninstall-skill",
        help="preview or move a managed skill to a reversible backup",
    )
    uninstall.add_argument("--client", choices=tuple(CLIENT_PATHS), required=True)
    uninstall.add_argument("--apply", action="store_true", help="apply the displayed operation")
    uninstall.add_argument("--format", choices=("text", "json"), default="text")
    return result


def _doctor_report() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    try:
        skill_root = bundled_skill_root()
    except OSError as exc:
        checks.append({"name": "bundled-skill", "status": "error", "detail": str(exc)})
    else:
        checks.append(
            {
                "name": "bundled-skill",
                "status": "ok",
                "detail": f"SKILL.md available at {skill_root.name}",
            }
        )
    checks.extend(
        [
            {
                "name": "python",
                "status": "ok" if sys.version_info >= (3, 10) else "error",
                "detail": platform.python_version(),
            },
            {
                "name": "audit-mode",
                "status": "ok",
                "detail": "read-only; writes only occur in explicit skill install operations",
            },
        ]
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
    lines.append("No repository files were changed.")
    return "\n".join(lines) + "\n"


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
            lines.append("Run the same command with --apply to perform exactly this operation.")
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
            raw = sys.stdin.read() if args.report == "-" else Path(args.report).read_text(encoding="utf-8")
            errors = validate_audit(json.JSONDecoder().decode(raw))
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
                plan = apply_install(plan)
            _emit_plan(plan, args.format, args.apply and plan.state == "applied")
            return 0 if plan.state in {"ready", "applied", "already-installed"} else 1
        plan = plan_uninstall(args.client)
        if args.apply and plan.state == "ready":
            plan = apply_uninstall(plan)
        _emit_plan(plan, args.format, args.apply and plan.state == "applied")
        return 0 if plan.state in {"ready", "applied", "not-installed"} else 1
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

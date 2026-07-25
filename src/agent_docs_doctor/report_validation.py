"""Bounded, non-blocking input handling for audit report validation."""

from __future__ import annotations

import json
import math
import os
import stat
from pathlib import Path
from typing import Any, BinaryIO

from .core import MAX_REPORT_BYTES

MAX_JSON_DEPTH = 128
MAX_JSON_NUMBER_CHARS = 256
_READ_CHUNK_BYTES = 64 * 1024


class ReportInputError(ValueError):
    """A privacy-safe report input or decoding failure."""


def _same_file_snapshot(before: os.stat_result, after: os.stat_result) -> bool:
    before_inode = getattr(before, "st_ino", 0)
    after_inode = getattr(after, "st_ino", 0)
    before_device = getattr(before, "st_dev", 0)
    after_device = getattr(after, "st_dev", 0)
    identity_matches = (
        before_inode == after_inode and before_device == after_device
        if before_inode and after_inode
        else stat.S_IFMT(before.st_mode) == stat.S_IFMT(after.st_mode)
    )
    return (
        identity_matches
        and before.st_size == after.st_size
        and getattr(before, "st_mtime_ns", None) == getattr(after, "st_mtime_ns", None)
        and getattr(before, "st_ctime_ns", None) == getattr(after, "st_ctime_ns", None)
    )


def _read_fd(fd: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while total <= MAX_REPORT_BYTES:
        try:
            chunk = os.read(fd, min(_READ_CHUNK_BYTES, MAX_REPORT_BYTES + 1 - total))
        except BlockingIOError as exc:
            raise ReportInputError("report input is not a readable regular file") from exc
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
    if total > MAX_REPORT_BYTES:
        raise ReportInputError(f"report exceeds the {MAX_REPORT_BYTES} byte validation limit")
    return b"".join(chunks)


def read_report_file(path: Path) -> bytes:
    """Read one regular report file through one bounded, non-blocking descriptor."""

    try:
        before = path.lstat()
    except OSError as exc:
        detail = exc.strerror or type(exc).__name__
        raise ReportInputError(f"unable to inspect report file: {detail}") from exc
    if not stat.S_ISREG(before.st_mode):
        raise ReportInputError("report input must be a regular file, not a link or special file")
    if before.st_nlink != 1:
        raise ReportInputError("report input must not be multiply linked")
    if before.st_size > MAX_REPORT_BYTES:
        raise ReportInputError(f"report exceeds the {MAX_REPORT_BYTES} byte validation limit")

    flags = os.O_RDONLY
    for name in ("O_BINARY", "O_CLOEXEC", "O_NONBLOCK", "O_NOFOLLOW"):
        flags |= int(getattr(os, name, 0))
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        detail = exc.strerror or type(exc).__name__
        raise ReportInputError(f"unable to open report file: {detail}") from exc
    try:
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode):
            raise ReportInputError("report input must be a regular file")
        if opened.st_nlink != 1:
            raise ReportInputError("report input must not be multiply linked")
        if not _same_file_snapshot(before, opened):
            raise ReportInputError("report file changed while it was being opened; try again")
        if opened.st_size > MAX_REPORT_BYTES:
            raise ReportInputError(f"report exceeds the {MAX_REPORT_BYTES} byte validation limit")
        raw = _read_fd(fd)
        after = os.fstat(fd)
        if not _same_file_snapshot(opened, after):
            raise ReportInputError("report file changed while it was being read; try again")
        return raw
    finally:
        os.close(fd)


def read_report_stdin(stream: BinaryIO) -> bytes:
    """Read a bounded report from the caller-selected standard input stream."""

    raw = stream.read(MAX_REPORT_BYTES + 1)
    if len(raw) > MAX_REPORT_BYTES:
        raise ReportInputError(f"report exceeds the {MAX_REPORT_BYTES} byte validation limit")
    return raw


def _check_json_depth(text: str) -> None:
    depth = 0
    in_string = False
    escaped = False
    for character in text:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character in "[{":
            depth += 1
            if depth > MAX_JSON_DEPTH:
                raise ReportInputError(f"report JSON exceeds the maximum nesting depth of {MAX_JSON_DEPTH}")
        elif character in "]}":
            depth = max(0, depth - 1)


def _reject_json_constant(_value: str) -> Any:
    raise ReportInputError("report JSON contains an unsupported numeric constant")


def _bounded_json_int(value: str) -> int:
    if len(value) > MAX_JSON_NUMBER_CHARS:
        raise ReportInputError("report JSON numeric token exceeds the validation limit")
    try:
        return int(value)
    except (ValueError, OverflowError) as exc:
        raise ReportInputError("report JSON contains an unsupported integer") from exc


def _bounded_json_float(value: str) -> float:
    if len(value) > MAX_JSON_NUMBER_CHARS:
        raise ReportInputError("report JSON numeric token exceeds the validation limit")
    try:
        result = float(value)
    except (ValueError, OverflowError) as exc:
        raise ReportInputError("report JSON contains an unsupported number") from exc
    if not math.isfinite(result):
        raise ReportInputError("report JSON contains a non-finite numeric value")
    if result == 0.0:
        mantissa = value.lower().split("e", 1)[0]
        if any(character in "123456789" for character in mantissa):
            raise ReportInputError("report JSON numeric magnitude exceeds the validation limit")
    return result


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ReportInputError("report JSON contains duplicate object keys")
        result[key] = value
    return result


def decode_report(raw: bytes) -> Any:
    """Decode bounded UTF-8 JSON without exposing input contents in errors."""

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ReportInputError("report is not valid UTF-8") from exc
    _check_json_depth(text)
    try:
        return json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_json_constant,
            parse_int=_bounded_json_int,
            parse_float=_bounded_json_float,
        )
    except json.JSONDecodeError as exc:
        raise ReportInputError(f"invalid report JSON at line {exc.lineno} column {exc.colno}") from exc
    except (RecursionError, MemoryError) as exc:
        raise ReportInputError("report JSON exceeds safe validation complexity") from exc
    except ValueError as exc:
        if isinstance(exc, ReportInputError):
            raise
        raise ReportInputError("report JSON exceeds safe validation complexity") from exc

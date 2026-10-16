"""Opt-in, numeric-only local usage aggregates. No network or request objects."""

import json
import os
import tempfile
from datetime import date, timedelta
from pathlib import Path

from . import __version__

OPS = (
    "search_code",
    "read_code",
    "get_system_overview",
    "find_related",
    "navigate_structure",
    "resolve_instructions",
)
OUTCOMES = ("success", "empty", "stale", "unavailable", "cancelled", "internal_error")

BINS = ("le_100", "101_500", "501_2000", "gt_2000")
MAX = 10**12
RELEASE = __version__


def decode(text):
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise ValueError("Duplicate report field")
            result[key] = value
        return result

    if len(text.encode()) > 65536:
        raise ValueError("Report exceeds 64 KB")
    return json.loads(text, object_pairs_hook=pairs)


def integer(value):
    if type(value) is not int or not 0 <= value <= MAX:
        raise ValueError("Invalid metric integer")


def validate(report):
    if not isinstance(report, dict) or set(report) != {
        "schema_version",
        "engine_release",
        "report_kind",
        "period_days_bucket",
        "operations",
        "token_usage",
    }:
        raise ValueError("Unexpected report fields")
    if (
        type(report["schema_version"]) is not int
        or report["schema_version"] != 1
        or report["engine_release"] != RELEASE
        or report["report_kind"] != "product_usage_aggregate"
    ):
        raise ValueError("Unsupported report version or kind")
    if report["period_days_bucket"] not in ("0", "1-7", "8-30") or report["token_usage"] != {
        "availability": "unavailable"
    }:
        raise ValueError("Invalid report metadata")
    operations = report["operations"]
    if not isinstance(operations, dict) or set(operations) - set(OPS):
        raise ValueError("Unknown operation")
    for row in operations.values():
        if not isinstance(row, dict) or set(row) != {
            "calls",
            "outcomes",
            "duration_ms_bins",
            "emitted_payload_bytes",
            "duplicate_candidates_suppressed",
        }:
            raise ValueError("Invalid metric fields")
        for key in ("calls", "emitted_payload_bytes", "duplicate_candidates_suppressed"):
            integer(row[key])
        for key, allowed in (("outcomes", OUTCOMES), ("duration_ms_bins", BINS)):
            if not isinstance(row[key], dict) or set(row[key]) != set(allowed):
                raise ValueError("Invalid metric labels")
            for value in row[key].values():
                integer(value)
            if sum(row[key].values()) != row["calls"]:
                raise ValueError("Inconsistent metric totals")
    return report


def blank():
    return {
        "calls": 0,
        "outcomes": dict.fromkeys(OUTCOMES, 0),
        "duration_ms_bins": dict.fromkeys(BINS, 0),
        "emitted_payload_bytes": 0,
        "duplicate_candidates_suppressed": 0,
    }


class Usage:
    def __init__(self, root):
        self.root = Path(root)

    def _directory(self):
        if self.root.is_symlink():
            raise ValueError("Refusing symlink usage directory")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root.chmod(0o700)

    def _read(self):
        path = self.root / "aggregates.json"
        if path.is_symlink():
            raise ValueError("Refusing symlink usage data")
        if not path.exists():
            return {"enabled": False, "days": {}}
        data = decode(path.read_text())
        if (
            not isinstance(data, dict)
            or set(data) != {"enabled", "days"}
            or type(data["enabled"]) is not bool
            or not isinstance(data["days"], dict)
            or len(data["days"]) > 31
        ):
            raise ValueError("Invalid local usage state")
        cutoff = date.today() - timedelta(days=29)
        data["days"] = {
            day: rows
            for day, rows in data["days"].items()
            if cutoff <= date.fromisoformat(day) <= date.today()
        }
        for rows in data["days"].values():
            validate(self._report(rows, "1-7"))
        return data

    def _write(self, data):
        descriptor, name = tempfile.mkstemp(prefix="aggregate-", dir=self.root)
        try:
            with os.fdopen(descriptor, "w") as handle:
                json.dump(data, handle, separators=(",", ":"))
            os.replace(name, self.root / "aggregates.json")
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def _locked(self):
        import fcntl
        from contextlib import contextmanager

        @contextmanager
        def lock():
            self._directory()
            fd = os.open(self.root / "usage.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
                for orphan in self.root.glob("aggregate-*"):
                    if orphan.is_file() and not orphan.is_symlink():
                        orphan.unlink()
                yield
            finally:
                os.close(fd)

        return lock()

    def configure(self, enabled):
        if type(enabled) is not bool:
            raise ValueError("enabled must be boolean")
        with self._locked():
            data = self._read()
            data["enabled"] = enabled
            self._write(data)

    def clear(self):
        with self._locked():
            self._write({"enabled": False, "days": {}})

    def record(self, operation, outcome, duration_ms, payload_bytes, reused=0):
        if operation not in OPS or outcome not in OUTCOMES:
            raise ValueError("Unknown metric enum")
        for value in (duration_ms, payload_bytes, reused):
            integer(value)
        # No file writes at all until explicitly configured.
        if not (self.root / "aggregates.json").exists():
            return
        with self._locked():
            data = self._read()
            if not data["enabled"]:
                self._write(data)
                return
            rows = data["days"].setdefault(date.today().isoformat(), {})
            row = rows.setdefault(operation, blank())
            bucket = BINS[
                0
                if duration_ms <= 100
                else 1
                if duration_ms <= 500
                else 2
                if duration_ms <= 2000
                else 3
            ]
            row["calls"] += 1
            row["outcomes"][outcome] += 1
            row["duration_ms_bins"][bucket] += 1
            row["emitted_payload_bytes"] += payload_bytes
            row["duplicate_candidates_suppressed"] += reused
            validate(self._report(rows, "1-7"))
            self._write(data)

    @staticmethod
    def _report(rows, period):
        return {
            "schema_version": 1,
            "engine_release": RELEASE,
            "report_kind": "product_usage_aggregate",
            "period_days_bucket": period,
            "operations": rows,
            "token_usage": {"availability": "unavailable"},
        }

    def report(self):
        with self._locked():
            data = self._read()
            self._write(data)
            total = {}
            for rows in data["days"].values():
                for op, row in rows.items():
                    target = total.setdefault(op, blank())
                    for key in (
                        "calls",
                        "emitted_payload_bytes",
                        "duplicate_candidates_suppressed",
                    ):
                        target[key] += row[key]
                    for key in ("outcomes", "duration_ms_bins"):
                        for label, count in row[key].items():
                            target[key][label] += count
            days = (
                (date.today() - date.fromisoformat(min(data["days"]))).days + 1
                if data["days"]
                else 0
            )
            return validate(
                self._report(total, "0" if not days else "1-7" if days <= 7 else "8-30")
            )

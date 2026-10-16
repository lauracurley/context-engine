"""Restartable periodic refresh of code, architecture, vectors and history."""

import json
import math
import time
from datetime import datetime, timezone

from .locking import WriterBusy, exclusive, writer_lock


def now():
    return datetime.now(timezone.utc).timestamp()


class Crawler:
    def __init__(self, engine):
        self.engine = engine

    def config(self, interval=None, history_interval=None, history=None):
        raw = self.engine.config.get("crawler", {})
        if not isinstance(raw, dict) or set(raw) - {
            "interval",
            "history_interval",
            "history",
            "history_provider",
            "history_months",
            "max_pages",
        }:
            raise ValueError("Invalid crawler configuration")
        c = dict(
            interval=300,
            history_interval=21600,
            history=True,
            history_provider="auto",
            history_months=6,
            max_pages=100,
        )
        c.update(raw)
        saved = self.engine.db.execute(
            "SELECT value FROM meta WHERE key='schedule_preferences'"
        ).fetchone()
        if saved:
            c.update(json.loads(saved[0]))
        for key, value in (
            ("interval", interval),
            ("history_interval", history_interval),
            ("history", history),
        ):
            if value is not None:
                c[key] = value
        for key in ("interval", "history_interval"):
            if (
                type(c[key]) not in (float, int)
                or not math.isfinite(c[key])
                or not 1 <= c[key] <= 31536000
            ):
                raise ValueError("crawler " + key + " must be 1..31536000 seconds")
        if type(c["history"]) is not bool or c["history_provider"] not in (
            "auto",
            "git",
            "github",
            "gateway",
        ):
            raise ValueError("Invalid crawler history/provider setting")
        if type(c["history_months"]) is not int or not 1 <= c["history_months"] <= 120:
            raise ValueError("crawler history_months must be 1..120")
        if type(c["max_pages"]) is not int or not 1 <= c["max_pages"] <= 1000:
            raise ValueError("crawler max_pages must be 1..1000")
        if self.engine.policy and not self.engine.policy["allow_history"]:
            c["history"] = False
        return c

    @exclusive
    def configure(self, values):
        """Persist timing preferences without changing the manifest/index identity."""
        if not isinstance(values, dict) or set(values) - {
            "interval",
            "history_interval",
            "history_months",
        }:
            raise ValueError("Only refresh timing preferences may be changed")
        for key, value in values.items():
            if type(value) is not int or not 1 <= value <= (
                120 if key == "history_months" else 31536000
            ):
                raise ValueError("Invalid refresh timing preference")
        current = self.config()
        selected = {key: current[key] for key in ("interval", "history_interval", "history_months")}
        selected.update(values)
        with self.engine.db:
            self.engine.db.execute(
                "INSERT OR REPLACE INTO meta VALUES('schedule_preferences',?)",
                (json.dumps(selected),),
            )
            # Apply changed timing on the next cycle rather than retaining the old deadline.
            self.engine.db.execute("DELETE FROM meta WHERE key='crawler'")
        return {"config": self.config(), "state": "saved", "knowledge_preserved": True}

    def status(self):
        row = self.engine.db.execute("SELECT value FROM meta WHERE key='crawler'").fetchone()
        report = json.loads(row[0]) if row else {"state": "never_run", "jobs": {}}
        # Stored timestamps report the last cycle, not whether a daemon is alive.
        return dict(
            report,
            liveness="Not inferred from stored state; process supervision belongs to the launcher",
        )

    def save(self, report):
        with self.engine.db:
            self.engine.db.execute(
                "INSERT OR REPLACE INTO meta VALUES('crawler',?)", (json.dumps(report),)
            )

    def cycle(self, force=False, interval=None, history_interval=None, history=None, clock=None):
        if type(force) is not bool:
            raise ValueError("force must be a boolean")
        c = self.config(interval, history_interval, history)
        instant = now() if clock is None else clock
        try:
            with writer_lock(self.engine):
                report = self.status()
                report.pop("liveness", None)
                report.update(state="running", started_at=instant, config=c)
                self.save(report)
                for job, cadence in (("code", c["interval"]), ("history", c["history_interval"])):
                    previous = report["jobs"].get(job, {})
                    if job == "history" and not c["history"]:
                        report["jobs"][job] = dict(previous, state="disabled")
                        continue
                    if (
                        not force
                        and previous.get("state") != "running"
                        and instant < previous.get("next_due", 0)
                    ):
                        continue
                    report["jobs"][job] = dict(previous, state="running", started_at=instant)
                    self.save(report)
                    try:
                        if job == "code":
                            from .managed import sync

                            sync(self.engine)
                            result = self.engine.index()
                            errors = sum(len(s["errors"]) for s in result["coverage"].values())
                            degraded = (
                                bool(errors) or result.get("semantic", {}).get("state") == "error"
                            )
                            summary = {
                                "generation": result["generation"],
                                "changed": result["changed"],
                                "deleted": result["deleted"],
                                "unchanged": result["unchanged"],
                                "architecture": result.get("architecture"),
                                "semantic": result.get("semantic", {}).get("state", "disabled"),
                                "source_errors": errors,
                            }
                        else:
                            result = self.engine.history.ingest(
                                provider=c["history_provider"],
                                months=c["history_months"],
                                max_pages=c["max_pages"],
                            )
                            degraded = result["state"] != "ready"
                            summary = {
                                k: result[k]
                                for k in (
                                    "accepted",
                                    "inserted",
                                    "updated",
                                    "unchanged",
                                    "rejected",
                                    "state",
                                )
                            }
                        failures = 0
                        state = "partial" if degraded else "ready"
                    except Exception as exc:
                        failures = previous.get("failures", 0) + 1
                        state = "error"
                        summary = {
                            "error": type(exc).__name__,
                            "message": "Refresh failed; inspect source/provider configuration and retry",
                        }
                    finished = now() if clock is None else instant
                    # A thrown error retries with bounded backoff; partial scans use their normal cadence.
                    delay = min(cadence, 30 * 2 ** min(failures - 1, 10)) if failures else cadence
                    report["jobs"][job] = {
                        "state": state,
                        "started_at": instant,
                        "finished_at": finished,
                        "next_due": finished + delay,
                        "failures": failures,
                        "result": summary,
                    }
                    self.save(report)
                report["state"] = (
                    "degraded"
                    if any(j["state"] in ("error", "partial") for j in report["jobs"].values())
                    else "ready"
                )
                report["finished_at"] = now() if clock is None else instant
                self.save(report)
                return report
        except WriterBusy:
            return {
                "state": "busy",
                "gaps": ["Another refresh owns this store; this cycle was skipped"],
            }

    def run(self, once=False, **kwargs):
        self.config(kwargs.get("interval"), kwargs.get("history_interval"), kwargs.get("history"))
        while True:
            report = self.cycle(**kwargs)
            print(json.dumps(report, ensure_ascii=False), flush=True)
            if once:
                return report
            due = [
                job["next_due"]
                for job in report.get("jobs", {}).values()
                if job.get("state") != "disabled" and "next_due" in job
            ]
            delay = max(1, min(due) - now()) if due else 5
            # Keep process shutdown responsive and avoid a long uninterruptible wait.
            deadline = time.monotonic() + delay
            while time.monotonic() < deadline:
                time.sleep(max(0, min(1, deadline - time.monotonic())))

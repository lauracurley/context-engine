"""In-memory, server-scoped retrieval accounting; not a model billing meter."""

import re

from .budget import size


class RetrievalTasks:
    def __init__(self):
        self.tasks = {}

    def prepare(self, name, arguments):
        args = dict(arguments)
        task_id = args.pop("task_id", None)
        limit = args.pop("task_byte_budget", None)
        end = args.pop("task_end", False)
        if type(end) is not bool:
            raise ValueError("task_end must be a boolean")
        if task_id is None:
            if limit is not None or end:
                raise ValueError("Task options require task_id")
            return args, None
        if not isinstance(task_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", task_id):
            raise ValueError("task_id must be 1..64 letters, digits, underscores or hyphens")
        if limit is not None and (type(limit) is not int or not 1280 <= limit <= 1_000_000):
            raise ValueError("task_byte_budget must be 1280..1000000")
        state = self.tasks.get(task_id)
        if state is None:
            if limit is None:
                raise ValueError(
                    "Unknown task; supply task_byte_budget to start (tasks reset on server restart)"
                )
            if len(self.tasks) >= 128:
                raise ValueError("Task capacity reached; finish an existing task with task_end")
            state = {"limit": limit, "used": 0, "seen": set()}
            self.tasks[task_id] = state
        elif limit is not None and limit != state["limit"]:
            raise ValueError("An active task's budget cannot be reset")
        default = (
            4000 if name in ("read_code", "navigate_structure", "resolve_instructions") else 2000
        )
        requested = args.get("token_budget", default)
        if type(requested) is not int or not 1024 <= requested <= 32000:
            raise ValueError("Response byte budget must be 1024..32000")
        ceiling = min(requested, state["limit"] - state["used"])
        if ceiling < 1280:
            if end:
                del self.tasks[task_id]
            raise ValueError("Task budget exhausted for retrieval; no evidence returned")
        # Reserve space for accounting, itself charged to the task and response.
        args["token_budget"] = ceiling - 256
        if name == "search_code":
            excluded = args.get("exclude_evidence_ids", [])
            if not isinstance(excluded, list) or any(not isinstance(i, str) for i in excluded):
                raise ValueError("exclude_evidence_ids must be a list of strings")
            args["exclude_evidence_ids"] = list(state["seen"] | set(excluded))
        return args, (task_id, name, state, ceiling, end)

    def finish(self, ticket, result):
        if ticket is None:
            return result
        task_id, name, state, ceiling, end = ticket
        result["task_budget"] = {"id": task_id, "limit": state["limit"], "remaining_bytes": 0}
        result["budget"]["limit"] = ceiling
        for _ in range(12):
            measured = size(result)
            remaining = state["limit"] - state["used"] - measured
            if (
                result["budget"]["used_bytes"] == measured
                and result["task_budget"]["remaining_bytes"] == remaining
            ):
                break
            result["budget"]["used_bytes"] = measured
            result["task_budget"]["remaining_bytes"] = remaining
        measured = size(result)
        if measured > ceiling:
            raise ValueError("Task accounting exceeded the reserved response space")
        state["used"] += measured
        if name == "search_code" and result["state"] == "ready":
            state["seen"].update(i["evidence_id"] for i in result["items"] if "evidence_id" in i)
        if end:
            del self.tasks[task_id]
        return result

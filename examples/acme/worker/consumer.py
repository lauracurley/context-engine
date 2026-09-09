"""Worker side of the task.requested contract."""


def consume_task(message):
    """Consume task.requested; preserve priority and report completion."""
    if message["event"] != "task.requested":
        raise ValueError("UNKNOWN_EVENT")
    return {"template_id": message["template_id"],
            "priority": message["priority"], "status": "COMPLETED"}

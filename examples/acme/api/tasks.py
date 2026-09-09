"""Task creation API; queue is supplied by the caller."""


def create_task(template_id, priority, queue):
    """Validate template selection and publish a task.requested message."""
    if template_id not in {"invoice", "receipt"}:
        raise ValueError("UNKNOWN_TEMPLATE")
    message = {"event": "task.requested", "template_id": template_id,
               "priority": priority, "status": "QUEUED"}
    queue.append(message)
    return message

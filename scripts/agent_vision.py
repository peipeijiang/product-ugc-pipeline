"""Agent-native vision handoff.

Image understanding is done by the multimodal model already running the agent.
Scripts never call an external vision API: they write a task file that lists the
exact local images and the required JSON fields, the agent looks at every image
and writes an answer file, and the script validates coverage before finalizing.

Every answer must echo the task's task_sha256. A changed image, brief or target
produces a new task hash, so a stale answer can never pass.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from common import load_json, write_json

PENDING_EXIT_CODE = 3


class AgentReviewPending(RuntimeError):
    """Raised when the agent still has to look at the images and write the answer."""

    def __init__(self, task_path: Path, answer_path: Path, reason: str):
        self.task_path = task_path
        self.answer_path = answer_path
        super().__init__(
            f"{reason}. Open every image listed in {task_path}, then write {answer_path} "
            "with the task's task_sha256 and the required fields. Rerun this command to finalize."
        )


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_task(task_path: Path, task: dict[str, Any]) -> str:
    """Write the task and return its content hash (excluding the hash field itself)."""
    body = {key: value for key, value in task.items() if key != "task_sha256"}
    task_hash = hashlib.sha256(
        json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    write_json(task_path, {**body, "task_sha256": task_hash})
    return task_hash


def load_answer(task_path: Path, answer_path: Path, task_hash: str) -> dict[str, Any]:
    answer = load_json(answer_path, None)
    if not isinstance(answer, dict):
        raise AgentReviewPending(task_path, answer_path, "Agent vision answer is missing")
    if answer.get("task_sha256") != task_hash:
        raise AgentReviewPending(
            task_path, answer_path,
            "Agent vision answer is stale or unbound (task_sha256 does not match the current task)",
        )
    return answer

"""
Safe command execution layer.

Only commands that pass the allowlist validator are ever executed.
shell=False is non-negotiable — args are always passed as a list.
"""

import logging
import subprocess
import time

from security.allowlist import AllowlistValidator, CommandRequest, ValidationError
from security.audit_log import audit_logger


logger = logging.getLogger(__name__)


def run_command(request_id: str, command: str, args: list[str] | None = None) -> str:
    args = args or []

    try:
        AllowlistValidator.validate(CommandRequest(command=command, args=args))
    except ValidationError as exc:
        audit_logger.log_command(
            request_id=request_id,
            command=command,
            args=args,
            outcome="rejected",
            reason=str(exc),
        )
        return f"Command rejected: {exc}"

    start = time.monotonic()
    try:
        result = subprocess.run(
            [command, *args],
            capture_output=True,
            text=True,
            timeout=10,
            shell=False,
        )
        output = result.stdout.strip() or result.stderr.strip()
        duration_ms = int((time.monotonic() - start) * 1000)

        audit_logger.log_command(
            request_id=request_id,
            command=command,
            args=args,
            outcome="allowed",
            duration_ms=duration_ms,
        )
        return output

    except subprocess.TimeoutExpired:
        audit_logger.log_command(
            request_id=request_id,
            command=command,
            args=args,
            outcome="error",
            reason="timeout",
        )
        return "Command timed out."

    except FileNotFoundError:
        audit_logger.log_command(
            request_id=request_id,
            command=command,
            args=args,
            outcome="error",
            reason="command not found",
        )
        return f"Command not found: {command}"

"""
Command allowlist.

Default deny — if a command is not in ALLOWED_COMMANDS, it is rejected.
Each entry declares the maximum number of arguments and optional allowed
argument values. This keeps the surface area explicit and auditable.
"""

from dataclasses import dataclass, field


class ValidationError(ValueError):
    pass


@dataclass
class CommandSpec:
    max_args: int = 0
    allowed_args: list[str] | None = None  # None = any value permitted (within max_args)


@dataclass
class CommandRequest:
    command: str
    args: list[str] = field(default_factory=list)


# The complete list of commands RasaPi may execute.
# Extend this list deliberately — never add a wildcard or shell builtin.
ALLOWED_COMMANDS: dict[str, CommandSpec] = {
    "uptime": CommandSpec(max_args=0),
    "date": CommandSpec(max_args=0),
    "hostname": CommandSpec(max_args=0),
    "uname": CommandSpec(max_args=1, allowed_args=["-a", "-r", "-m", "-s"]),
    "df": CommandSpec(max_args=1, allowed_args=["-h"]),
    "free": CommandSpec(max_args=1, allowed_args=["-h", "-m"]),
    "vcgencmd": CommandSpec(
        max_args=1,
        allowed_args=["measure_temp", "get_throttled", "measure_clock arm"],
    ),
    "ip": CommandSpec(max_args=1, allowed_args=["addr"]),
}


class AllowlistValidator:
    @staticmethod
    def validate(request: CommandRequest) -> None:
        spec = ALLOWED_COMMANDS.get(request.command)

        if spec is None:
            raise ValidationError(f"Command not allowed: {request.command!r}")

        if len(request.args) > spec.max_args:
            raise ValidationError(
                f"{request.command!r} accepts at most {spec.max_args} argument(s), "
                f"got {len(request.args)}"
            )

        if spec.allowed_args is not None:
            for arg in request.args:
                if arg not in spec.allowed_args:
                    raise ValidationError(
                        f"Argument {arg!r} not permitted for {request.command!r}"
                    )

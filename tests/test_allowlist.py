import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest

from security.allowlist import AllowlistValidator, CommandRequest, ValidationError


def test_allowed_command_no_args():
    AllowlistValidator.validate(CommandRequest(command="uptime"))


def test_allowed_command_with_valid_arg():
    AllowlistValidator.validate(CommandRequest(command="uname", args=["-a"]))


def test_allowed_command_with_valid_df_flag():
    AllowlistValidator.validate(CommandRequest(command="df", args=["-h"]))


def test_rejected_unknown_command():
    with pytest.raises(ValidationError, match="not allowed"):
        AllowlistValidator.validate(CommandRequest(command="rm"))


def test_rejected_shell_builtin():
    with pytest.raises(ValidationError):
        AllowlistValidator.validate(CommandRequest(command="bash"))


def test_rejected_sudo():
    with pytest.raises(ValidationError):
        AllowlistValidator.validate(CommandRequest(command="sudo"))


def test_rejected_too_many_args():
    with pytest.raises(ValidationError, match="at most"):
        AllowlistValidator.validate(CommandRequest(command="uptime", args=["extra"]))


def test_rejected_disallowed_arg_value():
    with pytest.raises(ValidationError, match="not permitted"):
        AllowlistValidator.validate(CommandRequest(command="uname", args=["--all"]))


def test_vcgencmd_allowed():
    AllowlistValidator.validate(CommandRequest(command="vcgencmd", args=["measure_temp"]))


def test_vcgencmd_rejected_arbitrary_arg():
    with pytest.raises(ValidationError):
        AllowlistValidator.validate(CommandRequest(command="vcgencmd", args=["get_mem gpu"]))

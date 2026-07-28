"""
Loads config.py, with a message that explains itself when it is missing.

config.py is gitignored (it holds your device names), so a fresh clone does
not have one until setup.ps1 copies the example across. Importing it
directly would fail with a bare ModuleNotFoundError, which tells a new user
nothing -- everything imports through here instead.
"""


class ConfigMissing(Exception):
    """config.py has not been created yet."""


MESSAGE = (
    "config.py not found.\n\n"
    "Copy config.example.py to config.py, then edit it so the device names "
    "match your own speakers:\n\n"
    "    copy config.example.py config.py\n\n"
    "Running setup.ps1 does this for you."
)

try:
    from config import OUTPUTS, VIRTUAL_SINK_NAME
except ImportError:  # pragma: no cover - depends on the user's setup
    raise ConfigMissing(MESSAGE) from None

__all__ = ["OUTPUTS", "VIRTUAL_SINK_NAME", "ConfigMissing", "MESSAGE"]

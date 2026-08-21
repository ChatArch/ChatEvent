"""ChatEnv configuration contract for ChatEvent."""

from __future__ import annotations

from chatenv import BaseEnvConfig, EnvField


class ChatEventConfig(BaseEnvConfig):
    """Typed ChatEnv profile for ChatEvent runtime and API credentials."""

    _title = "ChatEvent Configuration"
    _aliases = ["chatevent", "event"]
    _storage_dir = "ChatEvent"

    @classmethod
    def test(cls) -> None:
        """Validate schema registration without contacting a live Event Hub."""

        print(f"Testing {cls._title}...")
        print("Schema loaded; no network test is required.")

    CHATARCH_HOME = EnvField(
        "CHATARCH_HOME",
        desc="ChatArch runtime home resolved through ChatEnv; falls back to ~/.chatarch.",
        is_sensitive=False,
    )
    CHATEVENT_DB = EnvField(
        "CHATEVENT_DB",
        desc="Optional explicit SQLite database path for ChatEvent.",
        is_sensitive=False,
    )
    CHATEVENT_API_URL = EnvField(
        "CHATEVENT_API_URL",
        desc="Base URL used by `chatevent api ...` when --base-url is omitted.",
        is_sensitive=False,
    )
    CHATEVENT_ADMIN_TOKEN = EnvField(
        "CHATEVENT_ADMIN_TOKEN",
        desc="Account-scoped API token for CLI/model/programmatic access.",
        is_sensitive=True,
    )
    CHATEVENT_ADMIN_TOKEN_FILE = EnvField(
        "CHATEVENT_ADMIN_TOKEN_FILE",
        desc="File containing an account-scoped API token.",
        is_sensitive=False,
    )
    CHATEVENT_API_USERNAME = EnvField(
        "CHATEVENT_API_USERNAME",
        desc="Username for CLI password-login fallback.",
        is_sensitive=False,
    )
    CHATEVENT_API_PASSWORD_FILE = EnvField(
        "CHATEVENT_API_PASSWORD_FILE",
        desc="File containing the CLI login password; the file contents are sensitive.",
        is_sensitive=False,
    )
    CHATEVENT_BOOTSTRAP_USERNAME = EnvField(
        "CHATEVENT_BOOTSTRAP_USERNAME",
        desc="Initial administrator username for first-run bootstrap.",
        is_sensitive=False,
    )
    CHATEVENT_BOOTSTRAP_PASSWORD_FILE = EnvField(
        "CHATEVENT_BOOTSTRAP_PASSWORD_FILE",
        desc="File containing the first-run bootstrap administrator password.",
        is_sensitive=False,
    )


__all__ = ["ChatEventConfig"]

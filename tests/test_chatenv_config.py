from importlib import metadata
from pathlib import Path
from unittest.mock import Mock, patch

from chatevent.config import ChatEventConfig
from chatevent.state import state_paths


def test_chatevent_config_declares_sensitive_api_token() -> None:
    assert ChatEventConfig._title == "ChatEvent Configuration"
    assert "chatevent" in ChatEventConfig._aliases
    assert ChatEventConfig.CHATEVENT_ADMIN_TOKEN.is_sensitive
    assert not ChatEventConfig.CHATEVENT_API_URL.is_sensitive


def test_chatenv_entry_point_registers_chatevent_config() -> None:
    entry_points = metadata.entry_points(group="chatenv.configs")
    matches = [entry for entry in entry_points if entry.name == "chatevent"]

    assert matches
    assert matches[0].value == "chatevent.config:ChatEventConfig"


def test_state_paths_prefers_chatenv_home_dir(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("CHATARCH_HOME", raising=False)
    fake_paths = Mock(home_dir=tmp_path / "chatarch-home")

    with patch("chatenv.get_paths", return_value=fake_paths):
        paths = state_paths(create=False)

    assert paths.chatarch_home == tmp_path / "chatarch-home"
    assert paths.database == tmp_path / "chatarch-home" / "chatevent" / "events.db"

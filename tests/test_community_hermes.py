"""Native capability wiring and start receipts, without Hermes/network/model calls."""
from pathlib import Path
from types import ModuleType, SimpleNamespace
import json
import os
import signal
import subprocess
import sys

import pytest

from chatevent import community_hermes as module


def invocation(tmp_path, **runtime):
    source, home, cwd = [tmp_path / name for name in ("source", "home", "workspace")]
    for path in (source, home, cwd):
        path.mkdir(exist_ok=True)
    return {"id": "dispatch-one", "agent_id": "own-agent",
            "event": {"source": "zulip", "conversation_id": "stream:1/topic:task", "payload": {"content": "Do the authorized task"}},
            "runtime": {"kind": "hermes", "python": sys.executable, "source": str(source), "home": str(home), "cwd": str(cwd), **runtime}}


def fixture_child(tmp_path, monkeypatch, body):
    child = tmp_path / "child.py"
    child.write_text("import json,sys,os,time\np=json.load(open(sys.argv[3]))\n" + body)
    monkeypatch.setattr(module, "__file__", str(child))


def test_started_callback_once_and_failure_does_not_block_execution(tmp_path, monkeypatch):
    fixture_child(tmp_path, monkeypatch,
                  "f=open(p['started_file'],'w');json.dump({'invocation_id':p['invocation_id'],'phase':'model_invoking'},f);f.close()\n"
                  "time.sleep(.15)\n"
                  "json.dump({'status':'succeeded','text':'done','runtime_status':'completed','evidence':{}},open(p['output'],'w'))\n")
    calls = []
    def started(item):
        calls.append(item["id"])
        raise RuntimeError("status transport unavailable")
    result = module.HermesAdapter(tmp_path / "state", on_started=started)(invocation(tmp_path))
    assert calls == ["dispatch-one"]
    assert result["status"] == "succeeded"
    assert result["evidence"]["model_started"] is True
    request = json.loads(next((tmp_path / "state").glob("*/request.json")).read_text())
    assert "NO tools" not in request["prompt"]
    assert "projects/README.md" in request["prompt"]
    assert request["runtime"].get("max_iterations") is None
    assert request["runtime"].get("timeout_seconds") is None


def test_child_preflight_failure_does_not_report_started(tmp_path, monkeypatch):
    fixture_child(tmp_path, monkeypatch,
                  "json.dump({'status':'failed','text':'preflight failed','runtime_status':'child_error','evidence':{}},open(p['output'],'w'))\n")
    calls = []
    result = module.HermesAdapter(tmp_path / "state", calls.append)(invocation(tmp_path))
    assert calls == []
    assert result["evidence"]["model_started"] is False


@pytest.mark.parametrize("value", [None, 5, 3600, 43200])
def test_configurable_lifecycle_deadline(value):
    assert module._timeout({"timeout_seconds": value}) == value


@pytest.mark.parametrize("value", [True, 0, 4, 43201, -1, "3600"])
def test_lifecycle_deadline_rejects_invalid_values(value):
    with pytest.raises(ValueError):
        module._timeout({"timeout_seconds": value})


def test_marker_cannot_report_another_invocation_or_public_file(tmp_path):
    marker = tmp_path / "started.json"
    marker.write_text('{"invocation_id":"other","phase":"model_invoking"}')
    marker.chmod(0o600)
    assert not module._started_marker(marker, "one")
    marker.write_text('{"invocation_id":"one","phase":"model_invoking"}')
    marker.chmod(0o644)
    assert not module._started_marker(marker, "one")


@pytest.fixture
def native_fixture(tmp_path, monkeypatch):
    """Install deterministic protocol doubles, never import a real Hermes runtime."""
    calls = {"approval": [], "agent_options": None, "mcp": [], "closed": 0, "released": 0}
    def install(name, **values):
        obj = ModuleType(name)
        obj.__dict__.update(values)
        monkeypatch.setitem(sys.modules, name, obj)
        return obj
    for name in ("pm", "hermes_cli", "tools"):
        obj = install(name)
        obj.__path__ = []
    install("pm.environments", activate_dependencies=lambda source: None)
    def dotenv(**kwargs):
        os.environ["HERMES_YOLO_MODE"] = "1"  # Child must never inherit a process-wide bypass.
    install("hermes_cli.env_loader", load_hermes_dotenv=dotenv)
    config = {"agent": {}, "checkpoints": {"enabled": True}, "skills": {"auto_load": ["own-skill"]}}
    install("hermes_cli.config", load_config=lambda: config)
    install("hermes_cli.oneshot", _resolve_model_and_provider=lambda *args: SimpleNamespace(provider="custom", model="own-model", base_url=None, api_key=None))
    install("hermes_cli.runtime_provider", resolve_runtime_provider=lambda **kwargs: {"provider": "custom", "api_mode": "responses"})
    install("hermes_cli.tools_config", _get_platform_tools=lambda cfg, platform: {"terminal", "file", "memory", "skills", "mcp_own"})
    install("hermes_cli.mcp_startup", ensure_mcp_discovery_before_agent_build=lambda **kwargs: calls["mcp"].append(kwargs))
    install("hermes_cli.fallback_config", get_fallback_chain=lambda cfg: [])
    install("hermes_constants", resolve_reasoning_config=lambda cfg, model: {"effort": "high"})
    store = object()
    def release(db):
        assert db is store
        calls["released"] += 1
    install("hermes_state_registry", acquire=lambda: store, release_or_close=release)
    install("tools.approval", enable_session_yolo=lambda sid: calls["approval"].append(("enable", sid)),
            disable_session_yolo=lambda sid: calls["approval"].append(("disable", sid)))
    install("tools.approval_context", set_current_session_key=lambda sid: ("scope", sid),
            reset_current_session_key=lambda token: calls["approval"].append(("reset", token)))
    class Agent:
        def __init__(self, **kwargs):
            calls["agent_options"] = kwargs
            assert "HERMES_YOLO_MODE" not in os.environ
            self.tools = [{"function": {"name": name}} for name in ["terminal", "read_file", "mcp_own"]]
            self.session_id = kwargs["session_id"]
        def run_conversation(self, prompt):
            assert module._started_marker(Path(request["started_file"]), request["invocation_id"])
            return {"completed": True, "final_response": "Actual fixture result", "api_calls": 3}
        def close(self):
            calls["closed"] += 1
    install("run_agent", AIAgent=Agent)
    import resource
    import ctypes
    monkeypatch.setattr(resource, "setrlimit", lambda *args: None)
    monkeypatch.setattr(signal, "alarm", lambda *args: None)
    monkeypatch.setattr(ctypes, "CDLL", lambda *args, **kwargs: SimpleNamespace(prctl=lambda *args: 0))
    monkeypatch.setattr(module.subprocess, "run", lambda argv, **kwargs: SimpleNamespace(stdout="source-head" if argv[-1] == "HEAD" else ""))
    monkeypatch.setattr(sys, "path", list(sys.path))
    # Restore environment even when the fake loader writes to it.
    monkeypatch.setenv("HERMES_YOLO_MODE", "original")
    for key in ("HERMES_SESSION_PLATFORM", "HERMES_DISABLE_LAZY_INSTALLS", "HERMES_INTERACTIVE", "HERMES_EXEC_ASK",
                "HERMES_GATEWAY_SESSION", "HERMES_SINGLE_QUERY_SESSION", "HERMES_CRON_SESSION"):
        monkeypatch.setenv(key, os.environ.get(key, ""))
    request = {"runtime": invocation(tmp_path)["runtime"], "prompt": "Actual task", "invocation_id": "native-one",
               "started_file": str(tmp_path / "started.json")}
    Path(request["started_file"]).touch(mode=0o600)
    return calls, config, request, store


def test_full_native_configuration_is_preserved_and_session_approval_is_explicit(native_fixture):
    calls, cfg, request, store = native_fixture
    request["runtime"]["approval_mode"] = "full"
    result = module._run_child(request)
    options = calls["agent_options"]
    assert set(options["enabled_toolsets"]) == {"terminal", "file", "memory", "skills", "mcp_own"}
    assert options["session_db"] is store
    assert options["skip_context_files"] is options["skip_memory"] is options["skip_background_review"] is False
    assert options["load_soul_identity"] is True
    assert options["checkpoints_enabled"] is True
    assert "max_tokens" not in options and "max_iterations" not in options and "ephemeral_system_prompt" not in options
    assert calls["mcp"] and calls["closed"] == calls["released"] == 1
    assert calls["approval"] == [("enable", "native-one"), ("disable", "native-one"), ("reset", ("scope", "native-one"))]
    assert result["evidence"]["native_session_full"] is True
    assert result["evidence"]["tool_count"] == 3


def test_native_mode_does_not_invent_full_authorization_and_honors_config_budget(native_fixture):
    calls, cfg, request, _ = native_fixture
    cfg["agent"]["max_turns"] = 42
    result = module._run_child(request)
    assert calls["agent_options"]["max_iterations"] == 42
    assert calls["approval"] == [("reset", ("scope", "native-one"))]
    assert result["evidence"]["native_session_full"] is False


def test_construct_failure_never_marks_started_and_always_releases_authorization(native_fixture, monkeypatch):
    calls, _, request, _ = native_fixture
    request["runtime"]["approval_mode"] = "full"
    class Broken:
        def __init__(self, **kwargs):
            raise ValueError("configured capability unavailable")
    monkeypatch.setattr(sys.modules["run_agent"], "AIAgent", Broken)
    with pytest.raises(ValueError, match="capability"):
        module._run_child(request)
    assert not module._started_marker(Path(request["started_file"]), request["invocation_id"])
    assert calls["released"] == 1
    assert ("disable", "native-one") in calls["approval"]

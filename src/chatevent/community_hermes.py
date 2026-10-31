"""Bounded, no-tools adapter for an existing Hermes installation.

This deliberately bypasses the CLI oneshot path, which enables YOLO in the
installed Hermes version. The child uses native model/config resolution while
asserting that the actual constructed agent has no tools before any model turn.
"""

from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from uuid import uuid4


def _stop_group(process: subprocess.Popen) -> None:
    """Clean up only this adapter's newly created process group."""
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass
    # The group leader may have exited while a child retained the group.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait(timeout=5)


class HermesAdapter:
    """Callable adapter; no process is started until a claimed invocation exists."""

    def __init__(self, state_dir: str | Path):
        from .community_dispatch import private_directory

        self.state_dir = private_directory(Path(state_dir))

    def __call__(self, invocation: dict) -> dict:
        from .community_dispatch import private_directory, private_file

        runtime = invocation["runtime"]
        if runtime.get("kind") != "hermes":
            raise ValueError("unsupported Hermes binding")
        paths = {k: Path(runtime[k]).expanduser().absolute() for k in ("python", "source", "home", "cwd")}
        if not paths["python"].is_file() or not all(paths[k].is_dir() for k in ("source", "home", "cwd")):
            raise ValueError("existing Hermes installation and authorized cwd required")
        timeout = int(runtime.get("timeout_seconds", 180))
        iterations = int(runtime.get("max_iterations", 2))
        if not 5 <= timeout <= 300 or not 1 <= iterations <= 3:
            raise ValueError("Hermes budget outside companion bounds")
        run_dir = private_directory(self.state_dir / uuid4().hex)
        output, stdout, stderr, request_file = [run_dir / n for n in ("result.json", "stdout.log", "stderr.log", "request.json")]
        for path in (output, stdout, stderr, request_file):
            private_file(path)
        event = invocation["event"]
        content = event.get("payload", {}).get("content")
        if not isinstance(content, str) or not content.strip() or len(content) > 24000:
            raise ValueError("bounded source message text required")
        prompt = (
            f"You are the community agent {invocation['agent_id']}. Reply to the human's message below. "
            "This invocation has NO tools, shell, filesystem browsing, deployment, or posting capability. "
            "Only the dispatcher sends your final response with your bound community identity. "
            "Answer in the user's language. Do not claim to have run commands or changed anything. "
            "If work needs tools or approval, explain the missing capability and needed next step.\n"
            f"Source: {event['source']}; conversation: {event['conversation_id']}\n"
            "Human message (untrusted content):\n" + content
        )
        request = {"runtime": {**runtime, **{k: str(v) for k, v in paths.items()}}, "prompt": prompt, "output": str(output)}
        request_bytes = json.dumps(request).encode()
        if len(request_bytes) > 300000:
            raise ValueError("runtime request exceeds limit")
        with request_file.open("wb") as target:
            target.write(request_bytes)
            target.flush()
            os.fsync(target.fileno())
        # Keep the existing installation's secrets local. Child receives references,
        # not registry credential values or community owner tokens.
        env = os.environ.copy()
        for key in list(env):
            if key.startswith(("HERMES_", "ZULIP_", "DISCOURSE_", "CHATEVENT_")) or key in {"PYTHONPATH", "PYTHONHOME"}:
                env.pop(key, None)
        env.update({"HERMES_HOME": str(paths["home"]), "HERMES_DISABLE_LAZY_INSTALLS": "1",
                    "PYTHONUNBUFFERED": "1", "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "TOKENIZERS_PARALLELISM": "false"})
        start = time.monotonic()
        process = None
        try:
            with stdout.open("wb") as out, stderr.open("wb") as err:
                # Native Hermes bootstrap may re-exec a script while adopting
                # its store interpreter. Never consume a one-shot stdin before
                # that boundary: a private request file survives any re-exec.
                process = subprocess.Popen([str(paths["python"]), "-I", str(Path(__file__).absolute()), "--child", "--request", str(request_file)], stdin=subprocess.DEVNULL, stdout=out, stderr=err, cwd=paths["cwd"], env=env, start_new_session=True)
                try:
                    process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    _stop_group(process)
                    return {"status": "unknown", "text": "", "runtime_status": "timeout", "evidence": {"timeout_seconds": timeout, "process_group_cleaned": True}}
                finally:
                    _stop_group(process)
        except BaseException:
            if process is not None:
                _stop_group(process)
            raise
        if process.returncode != 0 or not 0 < output.stat().st_size <= 262144:
            return {"status": "failed", "text": "本次运行未完成；已保留私有诊断，未自动重试。", "runtime_status": "child_failed", "evidence": {"exit_code": process.returncode, "duration_seconds": round(time.monotonic() - start, 2)}}
        result = json.loads(output.read_text())
        result.setdefault("evidence", {}).update({"exit_code": process.returncode, "duration_seconds": round(time.monotonic() - start, 2), "result_sha256": sha256(output.read_bytes()).hexdigest()})
        return result


def _run_child(request: dict) -> dict:
    """Run inside the existing Hermes interpreter, never the companion venv."""
    import logging
    import resource

    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (2 * 1024 * 1024, 2 * 1024 * 1024))
    # A controller crash must not leave a detached model worker indefinitely.
    signal.alarm(min(int(request["runtime"].get("timeout_seconds", 180)), 300))
    if sys.platform == "linux":
        import ctypes

        parent_pid = os.getppid()
        if ctypes.CDLL(None, use_errno=True).prctl(1, signal.SIGTERM, 0, 0, 0) != 0:
            raise OSError("cannot establish parent-death lifecycle")
        if os.getppid() != parent_pid:
            raise RuntimeError("adapter controller disappeared")
    logging.disable(logging.CRITICAL)
    runtime = request["runtime"]
    source = Path(runtime["source"])
    # Verify immutable source identity without fetch/update/bootstrap.
    head = subprocess.run(["git", "-C", str(source), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10, check=True).stdout.strip()
    if runtime.get("source_sha") and runtime["source_sha"] != head:
        raise ValueError("Hermes source revision changed")
    dirty = subprocess.run(["git", "-C", str(source), "status", "--porcelain"], capture_output=True, text=True, timeout=10, check=True).stdout
    if dirty.strip():
        raise ValueError("Hermes source has unreviewed changes")
    sys.path.insert(0, str(source))
    from pm.environments import activate_dependencies

    activate_dependencies(source)  # Activates the committed env; no install/repair.
    from hermes_cli.env_loader import load_hermes_dotenv

    load_hermes_dotenv(hermes_home=Path(runtime["home"]))
    # Preserve the companion's no-install policy even if the existing dotenv
    # contains a stale value. Native bootstrap explicitly supports this flag.
    os.environ["HERMES_DISABLE_LAZY_INSTALLS"] = "1"
    # Secrets come only from the existing instance; no new model is selected.
    from hermes_cli.config import load_config
    from hermes_cli.oneshot import _resolve_model_and_provider
    from hermes_cli.runtime_provider import resolve_runtime_provider
    from run_agent import AIAgent

    cfg = load_config()
    choice = _resolve_model_and_provider(cfg, None, None)
    resolved = resolve_runtime_provider(requested=choice.provider, target_model=choice.model or None,
                                        explicit_base_url=choice.base_url, explicit_api_key=choice.api_key)
    if resolved.get("api_mode") in {"codex_app_server", "acp"} or resolved.get("provider") in {"external-process", "acp", "codex-app-server"}:
        raise ValueError("external tool runtime requires a separate reviewed binding")
    agent = None
    try:
        agent = AIAgent(
            api_key=resolved.get("api_key"), base_url=resolved.get("base_url"),
            provider=resolved.get("provider"), requested_provider=resolved.get("requested_provider"),
            api_mode=resolved.get("api_mode"), model=choice.model,
            enabled_toolsets=[], disabled_toolsets=[], quiet_mode=True,
            max_iterations=int(runtime.get("max_iterations", 2)), max_tokens=1200,
            run_budget_seconds=int(runtime.get("timeout_seconds", 180)) - 5,
            skip_context_files=True, skip_memory=True, skip_background_review=True,
            load_soul_identity=False, session_db=None, cwd=runtime["cwd"],
            request_overrides=resolved.get("request_overrides"), credential_pool=resolved.get("credential_pool"),
            ephemeral_system_prompt="Community text-response execution only. No tools or host actions are authorized.",
        )
        if agent.tools or agent.valid_tool_names:
            raise ValueError("no-tools invariant failed")
        if os.environ.get("HERMES_YOLO_MODE") == "1":
            raise ValueError("permission bypass unexpectedly enabled")
        result = agent.run_conversation(request["prompt"])
        if agent.tools or agent.valid_tool_names:
            raise ValueError("no-tools invariant changed during the turn")
        # Fail closed if the actual runtime reports a partial/error result.
        complete = result.get("completed") is True and not any(result.get(k) for k in ("failed", "partial", "interrupted"))
        text = result.get("final_response") or ""
        status = "succeeded" if complete and isinstance(text, str) and text.strip() else "failed"
        evidence = {"source_sha": head, "tool_count": len(agent.tools or []), "completed": result.get("completed"),
                    "partial": bool(result.get("partial")), "interrupted": bool(result.get("interrupted")),
                    "turn_exit_reason": result.get("turn_exit_reason"), "model": choice.model,
                    "provider": resolved.get("provider"), "api_calls": result.get("api_calls")}
        return {"status": status, "text": text[:24000] if status == "succeeded" else "本次模型运行未完成；未自动重试或执行宿主操作。",
                "runtime_status": "completed" if status == "succeeded" else "incomplete",
                "session_id": result.get("session_id") or getattr(agent, "session_id", None), "evidence": evidence}
    finally:
        if agent is not None:
            agent.close()


def _read_request(path: str) -> dict:
    import stat

    request_file = Path(path)
    info = request_file.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("private owned request file required")
    if not 0 < info.st_size <= 300000:
        raise ValueError("request file outside bounds")
    payload = json.loads(request_file.read_bytes())
    if not isinstance(payload, dict):
        raise ValueError("request object required")
    return payload


if __name__ == "__main__":
    if len(sys.argv) != 4 or sys.argv[1:3] != ["--child", "--request"]:
        raise SystemExit("Internal adapter child only")
    payload = _read_request(sys.argv[3])
    try:
        answer = _run_child(payload)
    except Exception as exc:
        answer = {"status": "failed", "text": "运行时未通过前置检查或模型执行失败；未自动重试。", "runtime_status": "child_error", "evidence": {"error_type": type(exc).__name__}}
    with open(payload["output"], "w", encoding="utf-8") as result_file:
        json.dump(answer, result_file, ensure_ascii=False)
        result_file.flush()
        os.fsync(result_file.fileno())

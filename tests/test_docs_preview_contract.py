"""Keep PR previews alive when production docs are deployed."""
from pathlib import Path
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def deployment_script():
    text = (ROOT / ".github/workflows/deploy-docs.yml").read_text()
    return text.split("      - name: Build and publish docs\n        run: |\n", 1)[1]


def test_docs_jobs_share_non_cancelling_lock():
    for name in ("deploy-docs.yml", "preview-docs.yml"):
        text = (ROOT / ".github/workflows" / name).read_text()
        assert "  group: docs-pages\n  cancel-in-progress: false\n" in text


def test_production_preserves_preview_not_old_production(tmp_path):
    _exercise_deployment(tmp_path, preview=True)


def test_first_production_without_published_branch(tmp_path):
    _exercise_deployment(tmp_path, preview=False)


def _exercise_deployment(tmp_path, *, preview):
    def git(*args, cwd=tmp_path):
        return subprocess.check_output(["git", *args], cwd=cwd, text=True).strip()

    remote = tmp_path / "remote.git"
    git("init", "--bare", str(remote))
    source = tmp_path / "source"
    source.mkdir()
    git("init", cwd=source)
    git("config", "user.name", "Docs Test", cwd=source)
    git("config", "user.email", "docs-test@example.org", cwd=source)
    git("remote", "add", "origin", str(remote), cwd=source)
    (source / "README.md").write_text("fresh source")
    git("add", "README.md", cwd=source)
    git("commit", "-m", "source", cwd=source)
    if preview:
        old = tmp_path / "published"
        old.mkdir()
        git("init", cwd=old)
        git("config", "user.name", "Docs Test", cwd=old)
        git("config", "user.email", "docs-test@example.org", cwd=old)
        (old / "dev").mkdir()
        (old / "dev/index.html").write_text("preserved preview")
        (old / "versions.json").write_text('[{"version":"dev"}]')
        (old / "obsolete.html").write_text("must not return")
        git("add", ".", cwd=old)
        git("commit", "-m", "old publication", cwd=old)
        git("push", str(remote), "HEAD:refs/heads/gh-pages", cwd=old)
    tools = tmp_path / "bin"
    tools.mkdir()
    build = tools / "mkdocs"
    build.write_text(f"#!{sys.executable}\nfrom pathlib import Path\nimport sys\nassert sys.argv[1:]==['build','--strict']\nPath('site').mkdir()\nPath('site/index.html').write_text('fresh production')\n")
    build.chmod(0o700)
    publisher = tools / "ghp-import"
    publisher.write_text(f"#!{sys.executable}\nfrom pathlib import Path\nassert Path('site/index.html').read_text()=='fresh production'\nassert not Path('site/obsolete.html').exists()\nassert Path('site/dev/index.html').exists()=={preview!r}\nassert Path('site/versions.json').exists()=={preview!r}\nif {preview!r}: assert Path('site/dev/index.html').read_text()=='preserved preview'\nPath('published-ok').write_text('ok')\n")
    publisher.chmod(0o700)
    runner = tmp_path / "runner"
    runner.mkdir()
    script = "\n".join(line[10:] if line.startswith("          ") else line for line in deployment_script().splitlines())
    child = {**os.environ, "PATH": str(tools) + os.pathsep + os.environ["PATH"], "RUNNER_TEMP": str(runner), "GITHUB_SHA": git("rev-parse", "HEAD", cwd=source)}
    subprocess.run(["bash", "-c", script], cwd=source, env=child, check=True, capture_output=True, text=True)
    assert (source / "published-ok").read_text() == "ok"
    assert not (runner / "docs-published").exists()
    assert git("worktree", "list", "--porcelain", cwd=source).count("worktree ") == 1

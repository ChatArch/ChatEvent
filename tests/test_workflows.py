from pathlib import Path


def test_publish_workflow_is_tag_only_trusted_publisher() -> None:
    workflow = Path(".github/workflows/publish.yml").read_text(encoding="utf-8")

    assert "tags:" in workflow
    assert '"v*"' in workflow
    assert "id-token: write" in workflow
    assert "pypa/gh-action-pypi-publish@release/v1" in workflow
    assert "Validate tag matches package version" in workflow
    assert "python -m build" in workflow
    assert "python -m twine check dist/*" in workflow


def test_ci_workflow_checks_both_cli_tree_modes() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "chatevent --tree" in workflow
    assert "chatevent --tree-brief" in workflow

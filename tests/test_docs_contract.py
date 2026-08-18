from pathlib import Path


DOC_PATHS = [
    Path("README.md"),
    Path("README.en.md"),
    Path("docs/index.md"),
    Path("docs/index.en.md"),
    Path("docs/quickstart.md"),
    Path("docs/quickstart.en.md"),
    Path("docs/reference.md"),
    Path("docs/reference.en.md"),
]


def test_docs_use_chatarch_internal_defaults() -> None:
    combined = "\n".join(path.read_text(encoding="utf-8") for path in DOC_PATHS)

    assert "0.1.0.dev0" not in combined
    assert "--db ./events.db" not in combined
    assert "/home/zhihong/Playground/projects/08-18-chatevent/playground" not in combined
    assert "$CHATARCH_HOME/chatevent/events.db" in combined
    assert "~/.chatarch/chatevent/events.db" in combined
    assert "chatevent paths --json" in combined

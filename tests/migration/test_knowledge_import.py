"""RED-first vectors for historical knowledge-document imports."""

from __future__ import annotations

from pathlib import Path

from tools.migration.operator_knowledge.main import (
    _parse_knowledge_files,
    analyze_knowledge_import,
)

__all__: tuple[str, ...] = ()


def test_parse_knowledge_files_excludes_agreed_decisions(tmp_path: Path) -> None:
    (tmp_path / "policy.md").write_text("# Policy\n\nKeep the record spine.")
    (tmp_path / "agreed-decision.md").write_text("# Decision\n\nUse the ruling tier.")

    rows = _parse_knowledge_files(tmp_path)

    assert [row["source_ref"] for row in rows] == ["policy.md"]


def test_analyze_knowledge_import_preserves_file_timestamp_and_source_ref(tmp_path: Path) -> None:
    source = tmp_path / "reference.md"
    source.write_text("# Reference\n\nExact bytes.\n")

    report = analyze_knowledge_import(tmp_path)

    assert report["eligible"] is True
    assert report["document_count"] == 1
    row = report["rows"][0]
    assert row["source_ref"] == "reference.md"
    assert row["body"] == "# Reference\n\nExact bytes.\n"
    assert row["recorded_at"].endswith("+00:00")
    assert report["estate_manifest"]["tier"] == "knowledge_documents"


def test_analyze_knowledge_import_empty_source_is_ineligible(tmp_path: Path) -> None:
    report = analyze_knowledge_import(tmp_path)

    assert report["eligible"] is False
    assert report["document_count"] == 0

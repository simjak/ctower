"""RED-first vectors for historical knowledge-document imports."""

from __future__ import annotations

from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from tools.migration.ctower_project.ctower_project_source.signing import ArtifactSigner
from tools.migration.operator_knowledge.main import (
    _parse_knowledge_files,
    analyze_knowledge_import,
    execute_knowledge_import,
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


def test_execute_posts_batch_index_and_idempotency_key(tmp_path: Path) -> None:
    source = tmp_path / "reference.md"
    source.write_text("# Reference\n\nExact bytes.\n", encoding="utf-8")
    signer = ArtifactSigner("signing-key-ref:test-knowledge", 1, Ed25519PrivateKey.generate())
    report = analyze_knowledge_import(tmp_path, signer=signer)
    client = _RecordingClient()

    result = execute_knowledge_import(
        client,
        root=tmp_path,
        manifest=report["estate_manifest"],
        base_url="https://ctower.test",
    )

    assert result["imported_count"] == 1
    assert client.url == "https://ctower.test/v1/migrations/estate/knowledge"
    assert client.payload["batch_index"] == 0
    assert client.payload["rows"][0]["source_ref"] == "reference.md"
    assert client.headers["Idempotency-Key"]


class _Response:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return {"imported_count": 1}


class _RecordingClient:
    def __init__(self) -> None:
        self.url = ""
        self.payload: dict[str, object] = {}
        self.headers: dict[str, str] = {}

    def post(
        self,
        url: str,
        *,
        json: dict[str, object],
        headers: dict[str, str],
        timeout: int,
    ) -> _Response:
        self.url = url
        self.payload = json
        self.headers = headers
        assert timeout == 60
        return _Response()

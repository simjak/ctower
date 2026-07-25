from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tools.migration.ctower_project.ctower_project_source.canonical import (
    canonical_bytes,
    sha256_digest,
)
from tools.migration.ctower_project.ctower_project_source.exporter import freeze_export
from tools.migration.ctower_project.ctower_project_source.refusal import (
    MigrationRefusal,
    RefusalCode,
)
from tools.migration.ctower_project.ctower_project_source.source import ReadOnlySourceRoot

from .fixtures import CUTOVER_ID, SyntheticFixture, make_fixture

__all__: tuple[str, ...] = ()


def _rewrite_first_request(
    fixture: SyntheticFixture,
    updates: dict[str, Any],
    *,
    reseal: bool = True,
) -> None:
    path = fixture.root / "requests.jsonl"
    rows = path.read_bytes().splitlines()
    first = json.loads(rows[0])
    _deep_update(first, updates)
    rows[0] = canonical_bytes(first)
    data = b"\n".join(rows) + b"\n"
    path.write_bytes(data)
    inventory = fixture.selection["source_inventories"][0]
    inventory["whole_source_digest"] = sha256_digest(data)
    inventory["whole_source_bytes"] = len(data)
    if reseal:
        sealed = fixture.signer.seal(fixture.selection, "manifest_digest")
        fixture.selection.clear()
        fixture.selection.update(sealed)


def _deep_update(value: dict[str, Any], updates: dict[str, Any]) -> None:
    for key, item in updates.items():
        if isinstance(item, dict) and isinstance(value.get(key), dict):
            _deep_update(value[key], item)
        else:
            value[key] = item


def _freeze(fixture: SyntheticFixture) -> None:
    freeze_export(
        fixture.selection,
        ReadOnlySourceRoot(fixture.root),
        fixture.target_inventory,
        cutover_id=CUTOVER_ID,
        export_stage="export_a",
        verifier=fixture.verifier,
    )


@pytest.mark.parametrize(
    ("updates", "code"),
    [
        ({"review_decision": None}, RefusalCode.UNREVIEWED_CANDIDATE),
        ({"data_classes": ["pii_or_client_data"]}, RefusalCode.FORBIDDEN_DATA_CLASS),
        (
            {"identity": {"immutable_source_id": "R999"}},
            RefusalCode.OUTSIDE_REVIEWED_CLOSURE,
        ),
    ],
)
def test_unreviewed_forbidden_and_outside_closure_refuse(
    tmp_path: Path,
    updates: dict[str, Any],
    code: RefusalCode,
) -> None:
    fixture = make_fixture(tmp_path)
    _rewrite_first_request(fixture, updates)
    with pytest.raises(MigrationRefusal) as caught:
        _freeze(fixture)
    assert caught.value.code == code


def test_digest_or_signature_rebinding_refuses(tmp_path: Path) -> None:
    fixture = make_fixture(tmp_path)
    _rewrite_first_request(
        fixture,
        {"title": "reviewed but unsigned mutation"},
        reseal=False,
    )
    with pytest.raises(MigrationRefusal) as caught:
        _freeze(fixture)
    assert caught.value.code == RefusalCode.SIGNATURE_REBOUND

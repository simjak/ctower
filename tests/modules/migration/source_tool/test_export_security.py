from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import replace
from multiprocessing import get_context
from multiprocessing.connection import Connection
from pathlib import Path
from typing import Any, Literal, cast

import pytest

from tools.migration.ctower_project.ctower_project_source.canonical import (
    canonical_bytes,
    sha256_digest,
    strict_json,
)
from tools.migration.ctower_project.ctower_project_source.exporter import (
    EXPORT_A,
    EXPORT_B,
    FrozenExport,
    compare_exports,
    equality_manifest_bytes,
    freeze_export,
)
from tools.migration.ctower_project.ctower_project_source.import_plan import (
    build_import_plan,
)
from tools.migration.ctower_project.ctower_project_source.refusal import (
    MigrationRefusal,
    RefusalCode,
)
from tools.migration.ctower_project.ctower_project_source.signing import ArtifactVerifier
from tools.migration.ctower_project.ctower_project_source.source import (
    PositionedRecord,
    ReadOnlySourceRoot,
    SourceIdentity,
    SourceRecord,
    validate_position_chain,
)

from .fixtures import (
    COMMANDER_ID,
    CUTOVER_ID,
    REVIEW,
    RUN_ID,
    SyntheticFixture,
    make_fixture,
)

__all__: tuple[str, ...] = ()

EXPECTED_DIMENSIONS = 13


def _freeze(
    fixture: SyntheticFixture,
    export_stage: Literal["export_a", "export_b"] = EXPORT_A,
) -> FrozenExport:
    return freeze_export(
        fixture.selection,
        ReadOnlySourceRoot(fixture.root),
        fixture.target_inventory,
        cutover_id=CUTOVER_ID,
        export_stage=export_stage,
        verifier=fixture.verifier,
    )


def _process_export(
    root_path: str,
    public_key_path: str,
    export_stage: Literal["export_a", "export_b"],
    equality: dict[str, Any],
    alias_map: dict[str, Any],
    connection: Connection,
) -> None:
    root = ReadOnlySourceRoot(Path(root_path))
    selection = strict_json(root.read("selection.json").data, context="selection")
    target = strict_json(root.read("target.json").data, context="target")
    assert isinstance(selection, dict)
    assert isinstance(target, dict)
    verifier = ArtifactVerifier.from_path(Path(public_key_path))
    frozen = freeze_export(
        cast(dict[str, object], selection),
        root,
        cast(dict[str, object], target),
        cutover_id=CUTOVER_ID,
        export_stage=export_stage,
        verifier=verifier,
    )
    plan = build_import_plan(
        frozen,
        equality,
        alias_map,
        run_id=RUN_ID,
        cutover_id=CUTOVER_ID,
        commander_custodian_id=COMMANDER_ID,
        verifier=verifier,
    )
    proof = canonical_bytes(
        {
            "selection": selection,
            "manifest": strict_json(
                equality_manifest_bytes(frozen.manifest),
                context="manifest projection",
            ),
            "semantic_export": strict_json(
                frozen.semantic_bytes,
                context="semantic export",
            ),
            "batches": [batch.model_dump(mode="json", by_alias=True) for batch in plan.batches],
        }
    )
    connection.send_bytes(proof)
    connection.close()


def test_two_independent_processes_emit_identical_semantic_export(tmp_path: Path) -> None:
    fixture = make_fixture(tmp_path)
    first_wrapper = _freeze(fixture, EXPORT_A)
    second_wrapper = _freeze(fixture, EXPORT_B)
    equality = compare_exports(
        first_wrapper,
        second_wrapper,
        review=REVIEW,
        signer=fixture.signer,
    )
    alias_map = fixture.alias_map(equality)
    context = get_context("spawn")
    parent_a, child_a = context.Pipe(duplex=False)
    parent_b, child_b = context.Pipe(duplex=False)
    process_a = context.Process(
        target=_process_export,
        args=(
            str(tmp_path),
            str(fixture.public_key_path),
            EXPORT_A,
            equality,
            alias_map,
            child_a,
        ),
    )
    process_b = context.Process(
        target=_process_export,
        args=(
            str(tmp_path),
            str(fixture.public_key_path),
            EXPORT_B,
            equality,
            alias_map,
            child_b,
        ),
    )
    process_a.start()
    process_b.start()
    first = parent_a.recv_bytes()
    second = parent_b.recv_bytes()
    process_a.join()
    process_b.join()
    assert process_a.exitcode == process_b.exitcode == 0
    assert first == second
    assert first_wrapper.manifest["artifact_digest"] != second_wrapper.manifest["artifact_digest"]


def test_signed_exports_compare_across_all_frozen_dimensions(tmp_path: Path) -> None:
    fixture = make_fixture(tmp_path)
    first = _freeze(fixture)
    second = _freeze(fixture, EXPORT_B)
    equality = compare_exports(
        first,
        second,
        review=REVIEW,
        signer=fixture.signer,
    )
    assert equality["result"] == "equal"
    assert len(equality["compared_dimensions"]) == EXPECTED_DIMENSIONS
    assert first.semantic_bytes == second.semantic_bytes
    assert first.manifest["semantic_export_digest"] == second.manifest["semantic_export_digest"]


@pytest.mark.parametrize(
    ("mutator", "code"),
    [
        (
            lambda selection: selection["source_inventories"][0].update(path="../requests.jsonl"),
            RefusalCode.PATH_OUTSIDE_ALLOWLIST,
        ),
        (
            lambda selection: selection.update(
                selected_request_ids=[
                    *selection["selected_request_ids"][:-1],
                    "R999",
                ]
            ),
            RefusalCode.SIGNATURE_REBOUND,
        ),
    ],
)
def test_selection_path_and_signature_rebinding_refuse(
    tmp_path: Path,
    mutator: Callable[[dict[str, Any]], None],
    code: RefusalCode,
) -> None:
    fixture = make_fixture(tmp_path)
    mutator(fixture.selection)
    with pytest.raises(MigrationRefusal) as caught:
        _freeze(fixture)
    assert caught.value.code == code


def test_symlink_and_fifo_are_never_opened_as_sources(tmp_path: Path) -> None:
    fixture = make_fixture(tmp_path)
    requests = tmp_path / "requests.jsonl"
    moved = tmp_path / "requests.real"
    requests.rename(moved)
    requests.symlink_to(moved)
    with pytest.raises(MigrationRefusal) as caught:
        _freeze(fixture)
    assert caught.value.code == RefusalCode.SOURCE_SYMLINK
    requests.unlink()
    os.mkfifo(requests)
    with pytest.raises(MigrationRefusal) as caught:
        _freeze(fixture)
    assert caught.value.code == RefusalCode.SOURCE_NOT_REGULAR


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        (b'{"schema":"ctower.synthetic-migration-source/v1"', RefusalCode.TRUNCATED_JSONL),
        (b'{"schema":"x","schema":"y"}\n', RefusalCode.DUPLICATE_JSON_KEY),
        (b"not-json\n", RefusalCode.MALFORMED_JSON),
    ],
)
def test_malformed_truncated_and_duplicate_key_jsonl_refuse_before_drift(
    tmp_path: Path, payload: bytes, code: RefusalCode
) -> None:
    fixture = make_fixture(tmp_path)
    (tmp_path / "requests.jsonl").write_bytes(payload)
    with pytest.raises(MigrationRefusal) as caught:
        _freeze(fixture)
    assert caught.value.code == code


def test_source_drift_refuses_and_emits_no_source_bytes(tmp_path: Path) -> None:
    fixture = make_fixture(tmp_path)
    source_path = tmp_path / "requests.jsonl"
    source_path.write_bytes(source_path.read_bytes() + b"{}\n")
    with pytest.raises(MigrationRefusal) as caught:
        _freeze(fixture)
    assert caught.value.code in {RefusalCode.MALFORMED_JSON, RefusalCode.SOURCE_DRIFT}
    assert "Reviewed migration request" not in str(caught.value)


def test_noncontiguous_position_chain_refuses() -> None:
    identity = SourceIdentity(
        namespace="mission-control:request",
        immutable_source_id="R325",
        source_version="reviewed-v1",
        source_digest=sha256_digest(b"R325"),
    )
    record = SourceRecord.model_validate(
        {
            "schema": "ctower.synthetic-migration-source/v1",
            "identity": identity.model_dump(),
            "candidate": True,
            "review_decision": "included",
            "data_classes": [],
            "title": "R325",
            "operation_hint": None,
        }
    )
    positioned = PositionedRecord(record, "requests.jsonl", 1, 1, 3, sha256_digest(b"{}\n"))
    with pytest.raises(MigrationRefusal) as caught:
        validate_position_chain([positioned], 3, "requests")
    assert caught.value.code == RefusalCode.NONCONTIGUOUS_POSITION


def test_compare_refuses_watermark_or_semantic_drift(tmp_path: Path) -> None:
    fixture = make_fixture(tmp_path)
    first = _freeze(fixture)
    second = _freeze(fixture, EXPORT_B)
    drifted_manifest = json.loads(canonical_bytes(second.manifest))
    drifted_manifest["sources"][0]["watermark"] = "bytes:999999"
    drifted = replace(second, manifest=drifted_manifest)
    with pytest.raises(MigrationRefusal) as caught:
        compare_exports(first, drifted, review=REVIEW, signer=fixture.signer)
    assert caught.value.code == RefusalCode.EXPORT_NONDETERMINISM

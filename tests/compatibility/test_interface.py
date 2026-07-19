from __future__ import annotations

import copy
import importlib
import json
import os
import tempfile
import unittest
from collections.abc import Callable
from contextlib import chdir
from importlib.util import find_spec
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from pydantic import ValidationError

if TYPE_CHECKING:
    from compatibility.support import MATRIX_PATH, report_payload
else:
    try:
        from .support import MATRIX_PATH, report_payload
    except ImportError:
        from support import MATRIX_PATH, report_payload

from tools.compatibility import (
    CompatibilityError,
    CompatibilityReport,
    load_matrix,
    validate_report,
    write_report,
)
from tools.compatibility.schema import JsonObject

__all__ = ()

CONTRACT_ROOT = MATRIX_PATH.parent


class InputBoundaryTests(unittest.TestCase):
    def test_fixed_matrix_crosses_schema_then_frozen_model(self) -> None:
        matrix = load_matrix(MATRIX_PATH)
        self.assertEqual(matrix.matrix_id, "ct-l0-007-python-2026-07-19")
        self.assertEqual(
            [item.version for item in matrix.candidates], ["3.12.13", "3.13.14", "3.14.6"]
        )
        self.assertTrue(matrix.digest.startswith("sha256:"))
        attribute = "matrix_id"
        with self.assertRaises(ValidationError):
            setattr(matrix.source, attribute, "changed")

    def test_every_meaningful_input_scalar_is_fixed_before_execution(self) -> None:
        source = _read_matrix()
        mutations: tuple[Callable[[JsonObject], None], ...] = (
            _set(("schema",), "ctower.compatibility-input/v2"),
            _set(("matrix_id",), "arbitrary-matrix"),
            _set(("uv_version",), "0.11.30"),
            _set(("requirements", 0), "build>=1"),
            _set(("requirements", 0), "--index-url=https://evil.invalid"),
            _set(("requirements", 0), "evil-package==1.0"),
            _set(("required_observations", 0), "arbitrary_probe"),
            _set(("product_artifacts", 0), "arbitrary_artifact"),
            _set(("candidates", 0, "version"), "3.12.12"),
            _set(("candidates", 0, "gil"), "optional"),
            _set(("candidates", 0, "release_date"), "2026-99-99"),
            _set(("candidates", 0, "release_url"), "https://evil.invalid/release"),
            _set(("candidates", 0, "source_url"), "file:///private/source.tgz"),
            _set(("candidates", 0, "source_sha256"), "z" * 64),
            _set(("candidates", 0, "linux_image"), "evil.invalid/python@sha256:" + "a" * 64),
            _set(("candidates", 0, "linux_image"), "docker.io/library/python@sha256:nothex"),
            _add(("candidates", 0), "registry", value="evil.invalid"),
            _add((), "unknown", value=True),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "matrix.json"
            for index, mutation in enumerate(mutations):
                candidate = copy.deepcopy(source)
                mutation(candidate)
                path.write_text(json.dumps(candidate), encoding="utf-8")
                with self.subTest(index=index), self.assertRaises(CompatibilityError):
                    load_matrix(path)

    def test_invalid_json_nonobject_and_format_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "matrix.json"
            for value in ("{", "[]"):
                path.write_text(value, encoding="utf-8")
                with self.subTest(value=value), self.assertRaises(CompatibilityError):
                    load_matrix(path)


class ResultBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.matrix = load_matrix(MATRIX_PATH)
        self.report = validate_report(self.matrix, report_payload(self.matrix))

    def test_report_is_exact_six_leg_frozen_evidence(self) -> None:
        accepted = validate_report(self.matrix, _raw(self.report))
        self.assertEqual(len(accepted.runs), 6)
        self.assertEqual(accepted.evidence_scope, "external-runner-noncanonical")
        attribute = "matrix_id"
        with self.assertRaises(ValidationError):
            setattr(accepted, attribute, "changed")

    def test_missing_duplicate_and_reordered_topology_are_rejected(self) -> None:
        cases: list[JsonObject] = []
        missing = _raw(self.report)
        _runs(missing).pop()
        cases.append(missing)
        duplicate = _raw(self.report)
        _runs(duplicate)[1] = copy.deepcopy(_runs(duplicate)[0])
        cases.append(duplicate)
        reordered = _raw(self.report)
        _runs(reordered)[0], _runs(reordered)[2] = _runs(reordered)[2], _runs(reordered)[0]
        cases.append(reordered)
        for raw in cases:
            with self.subTest(runs=len(_runs(raw))), self.assertRaises(CompatibilityError):
                validate_report(self.matrix, raw)

    def test_result_extras_and_malformed_observation_fields_fail_schema(self) -> None:
        cases: list[JsonObject] = []
        root_extra = _raw(self.report)
        root_extra["surprise"] = True
        cases.append(root_extra)
        run_extra = _raw(self.report)
        _runs(run_extra)[0]["surprise"] = True
        cases.append(run_extra)
        details_extra = _raw(self.report)
        _observations(details_extra)[0]["details"]["secret"] = True
        cases.append(details_extra)
        bad_status = _raw(self.report)
        _observations(bad_status)[0]["status"] = "skipped"
        cases.append(bad_status)
        missing_details = _raw(self.report)
        del _observations(missing_details)[0]["details"]
        cases.append(missing_details)
        for raw in cases:
            with self.subTest(case=len(cases)), self.assertRaises(CompatibilityError):
                validate_report(self.matrix, raw)

    def test_result_must_bind_digest_telemetry_host_candidate_and_image(self) -> None:
        cases: list[JsonObject] = []
        digest = _raw(self.report)
        digest["input_digest"] = "sha256:" + ("0" * 64)
        cases.append(digest)
        telemetry = _raw(self.report)
        cast(dict[str, object], telemetry["telemetry"])["trace_id"] = "0" * 32
        cases.append(telemetry)
        intake_telemetry = _raw(self.report)
        cast(dict[str, object], intake_telemetry["telemetry"])["trace_id"] = "1" * 32
        for run in _runs(intake_telemetry):
            run["telemetry"]["trace_id"] = "1" * 32
        cases.append(intake_telemetry)
        host = _raw(self.report)
        _runs(host)[0]["host_identity"]["system"] = "Linux"
        cases.append(host)
        interpreter_system = _raw(self.report)
        _runs(interpreter_system)[0]["interpreter"]["system"] = "Linux"
        _runs(interpreter_system)[0]["observations"][0]["details"]["system"] = "Linux"
        cases.append(interpreter_system)
        machine = _raw(self.report)
        _runs(machine)[1]["host_identity"]["machine"] = "amd64"
        cases.append(machine)
        image = _raw(self.report)
        _runs(image)[1]["image_identity"]["requested"] = _runs(image)[3]["image_identity"][
            "requested"
        ]
        cases.append(image)
        image_id = _raw(self.report)
        _runs(image_id)[1]["image_identity"]["image_id"] = "sha256:" + "f" * 64
        cases.append(image_id)
        resolution = _raw(self.report)
        _runs(resolution)[0]["resolution"]["lock_sha256"] = "0" * 64
        cases.append(resolution)
        for raw in cases:
            with self.subTest(index=cases.index(raw)), self.assertRaises(CompatibilityError):
                validate_report(self.matrix, raw)

    def test_public_interface_has_no_native_execution_seam(self) -> None:
        compatibility = importlib.import_module("tools.compatibility")
        self.assertFalse(hasattr(compatibility, "execute_matrix"))
        self.assertFalse(hasattr(compatibility, "ExecutionPort"))
        self.assertFalse(hasattr(compatibility, "LocalExecutionPort"))
        for module in ("environment", "execution", "probe", "process", "resolution"):
            self.assertIsNone(find_spec(f"tools.compatibility.{module}"))


class PublicReportWriteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.matrix = load_matrix(MATRIX_PATH)
        self.report = validate_report(self.matrix, report_payload(self.matrix))

    def test_atomic_report_write_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "report.json"
            write_report(destination, self.matrix, self.report)
            self.assertEqual(json.loads(destination.read_text()), _raw(self.report))

    def test_publication_revalidates_matrix_binding(self) -> None:
        unbound = self.report.model_copy(update={"input_digest": "sha256:" + ("0" * 64)})
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "unbound.json"
            with self.assertRaisesRegex(CompatibilityError, "input digest"):
                write_report(destination, self.matrix, unbound)
            self.assertFalse(destination.exists())

    def test_private_paths_symlink_destinations_and_parent_escape_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "real.json"
            destination.write_text("old", encoding="utf-8")
            symlink = root / "link.json"
            symlink.symlink_to(destination)
            with self.assertRaisesRegex(CompatibilityError, "symlink"):
                write_report(symlink, self.matrix, self.report)

            real_parent = root / "real-parent"
            real_parent.mkdir()
            linked_parent = root / "linked-parent"
            linked_parent.symlink_to(real_parent, target_is_directory=True)
            with self.assertRaisesRegex(CompatibilityError, "safe existing directory"):
                write_report(linked_parent / "report.json", self.matrix, self.report)

            sub = root / "sub"
            sub.mkdir()
            with self.assertRaisesRegex(CompatibilityError, "parent-path escape"):
                write_report(sub / ".." / "escaped.json", self.matrix, self.report)

    def test_public_write_rejects_hostile_lock_and_formerly_free_runtime_fields(self) -> None:
        raw = _raw(self.report)
        _runs(raw)[0]["resolution"]["lock"] = [
            "package @ https://user:secret@example.invalid/private.whl"
        ]
        with self.assertRaises(ValidationError):
            CompatibilityReport.model_validate_json(json.dumps(raw))

        for field, value in (
            ("platform", "Darwin-alice@example.invalid"),
            ("machine", "/Users/alice/private"),
            ("soabi", "TOKEN=synthetic-secret"),
            ("cache_tag", "https://example.invalid/private"),
        ):
            raw = _raw(self.report)
            _runs(raw)[0]["interpreter"][field] = value
            _observations(raw)[0]["details"][field] = value
            with self.subTest(field=field), self.assertRaises(ValidationError):
                CompatibilityReport.model_validate_json(json.dumps(raw))

    def test_missing_parent_is_rejected_without_creating_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory) / "missing"
            with self.assertRaisesRegex(CompatibilityError, "safe existing directory"):
                write_report(parent / "report.json", self.matrix, self.report)
            self.assertFalse(parent.exists())

    def test_publish_os_error_is_typed_and_relative_output_is_supported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            destination_directory = root / "occupied"
            destination_directory.mkdir()
            with self.assertRaisesRegex(CompatibilityError, "unable to publish"):
                write_report(destination_directory, self.matrix, self.report)

            with chdir(root):
                write_report(Path("relative.json"), self.matrix, self.report)
            self.assertTrue((root / "relative.json").is_file())

    def test_macos_tmp_alias_is_opened_without_following_arbitrary_parents(self) -> None:
        system_tmp = Path(os.sep) / "tmp"
        with tempfile.TemporaryDirectory(dir=system_tmp) as directory:
            destination = system_tmp / Path(directory).name / "report.json"
            write_report(destination, self.matrix, self.report)
            self.assertTrue(destination.is_file())


def _raw(report: CompatibilityReport) -> JsonObject:
    return cast("JsonObject", report.model_dump(mode="json", by_alias=True))


def _read_matrix() -> JsonObject:
    value: object = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    return cast("JsonObject", value)


def _runs(report: JsonObject) -> list[dict[str, Any]]:
    return cast("list[dict[str, Any]]", report["runs"])


def _observations(report: JsonObject) -> list[dict[str, Any]]:
    return cast("list[dict[str, Any]]", _runs(report)[0]["observations"])


def _set(path: tuple[str | int, ...], value: object) -> Callable[[JsonObject], None]:
    def mutate(document: JsonObject) -> None:
        target: Any = document
        for part in path[:-1]:
            target = target[part]
        target[path[-1]] = value

    return mutate


def _add(path: tuple[str | int, ...], key: str, *, value: object) -> Callable[[JsonObject], None]:
    def mutate(document: JsonObject) -> None:
        target: Any = document
        for part in path:
            target = target[part]
        target[key] = value

    return mutate

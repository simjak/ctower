from __future__ import annotations

import copy
import json
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from typing import cast

from tools.compatibility import CompatibilityError, load_matrix, validate_report, write_report

ROOT = Path(__file__).resolve().parents[2]
CONTRACT_ROOT = ROOT / "contracts" / "compatibility"


class CompatibilityContractTests(unittest.TestCase):
    def test_authored_contracts_are_strict_and_self_validating(self) -> None:
        matrix = json.loads((CONTRACT_ROOT / "ct-l0-007-matrix.json").read_text())
        schema = json.loads((CONTRACT_ROOT / "matrix-input.schema.json").read_text())

        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(
            schema["$id"], "https://ctower.dev/contracts/compatibility/matrix-input/v1"
        )
        self.assertEqual(matrix["schema"], schema["properties"]["schema"]["const"])
        self.assertFalse(schema["additionalProperties"])

    def test_matrix_names_every_required_standard_gil_candidate(self) -> None:
        matrix = load_matrix(CONTRACT_ROOT / "ct-l0-007-matrix.json")

        self.assertEqual(
            [candidate.version for candidate in matrix.candidates],
            ["3.12.13", "3.13.14", "3.14.6"],
        )
        self.assertTrue(all(candidate.gil == "required" for candidate in matrix.candidates))
        self.assertTrue(all("@sha256:" in candidate.linux_image for candidate in matrix.candidates))
        self.assertTrue(all(candidate.source_sha256 for candidate in matrix.candidates))

    def test_changed_input_is_rejected_by_report_validation(self) -> None:
        matrix_path = CONTRACT_ROOT / "ct-l0-007-matrix.json"
        matrix = load_matrix(matrix_path)
        report = _minimal_report(matrix_path, matrix.digest)
        report["input_digest"] = "sha256:" + ("0" * 64)

        with self.assertRaisesRegex(CompatibilityError, "input digest"):
            validate_report(matrix, report)

    def test_missing_candidate_is_rejected(self) -> None:
        matrix_path = CONTRACT_ROOT / "ct-l0-007-matrix.json"
        matrix = load_matrix(matrix_path)
        report = _minimal_report(matrix_path, matrix.digest)
        _runs(report).pop()

        with self.assertRaisesRegex(CompatibilityError, "candidate runs"):
            validate_report(matrix, report)

    def test_free_threaded_observation_is_rejected(self) -> None:
        matrix_path = CONTRACT_ROOT / "ct-l0-007-matrix.json"
        matrix = load_matrix(matrix_path)
        report = _minimal_report(matrix_path, matrix.digest)
        runtime = _observations(report)[0]
        details = cast(dict[str, object], runtime["details"])
        details["gil_enabled"] = False

        with self.assertRaisesRegex(CompatibilityError, "standard GIL"):
            validate_report(matrix, report)

    def test_skipped_current_check_is_rejected(self) -> None:
        matrix_path = CONTRACT_ROOT / "ct-l0-007-matrix.json"
        matrix = load_matrix(matrix_path)
        report = _minimal_report(matrix_path, matrix.digest)
        dependency = _observations(report)[1]
        dependency["status"] = "not_exercised"
        dependency["reason"] = "pretend skip"

        with self.assertRaisesRegex(CompatibilityError, "required observation"):
            validate_report(matrix, report)

    def test_absent_product_artifacts_are_explicit_not_exercised(self) -> None:
        matrix_path = CONTRACT_ROOT / "ct-l0-007-matrix.json"
        matrix = load_matrix(matrix_path)
        report = _minimal_report(matrix_path, matrix.digest)

        validate_report(matrix, report)
        product = cast(dict[str, dict[str, str]], _runs(report)[0]["product_artifacts"])
        self.assertEqual(product["release_helper_wheel"]["status"], "not_exercised")
        self.assertEqual(product["generated_clients"]["status"], "not_exercised")

    def test_malformed_json_and_unknown_input_fields_fail_closed(self) -> None:
        source = json.loads((CONTRACT_ROOT / "ct-l0-007-matrix.json").read_text())
        source["surprise"] = True
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "matrix.json"
            path.write_text(json.dumps(source))
            with self.assertRaises(CompatibilityError):
                load_matrix(path)

            path.write_text("{")
            with self.assertRaises(CompatibilityError):
                load_matrix(path)


class CompatibilityFailureBoundaryTests(unittest.TestCase):
    def test_public_report_rejects_private_host_and_temporary_paths(self) -> None:
        matrix_path = CONTRACT_ROOT / "ct-l0-007-matrix.json"
        matrix = load_matrix(matrix_path)
        self._assert_private_path_rejected(matrix_path, matrix.digest, "/Users/alice/bin/uv")
        self._assert_private_path_rejected(matrix_path, matrix.digest, "/home/alice/bin/uv")

    def _assert_private_path_rejected(
        self, matrix_path: Path, digest: str, private_path: str
    ) -> None:
        report = _minimal_report(matrix_path, digest)
        details = cast(dict[str, object], _observations(report)[1]["details"])
        details["commands"] = [[private_path]]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            with self.assertRaisesRegex(CompatibilityError, "private host"):
                write_report(path, report)
            self.assertFalse(path.exists())

    def test_public_report_write_is_atomic_and_rejects_symlink_destination(self) -> None:
        matrix_path = CONTRACT_ROOT / "ct-l0-007-matrix.json"
        matrix = load_matrix(matrix_path)
        report = _minimal_report(matrix_path, matrix.digest)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "nested" / "report.json"
            write_report(destination, report)
            self.assertEqual(json.loads(destination.read_text()), report)

            symlink = root / "report-link.json"
            symlink.symlink_to(destination)
            with self.assertRaisesRegex(CompatibilityError, "symlink"):
                write_report(symlink, report)

    def test_matrix_validation_failure_boundaries(self) -> None:
        source = json.loads((CONTRACT_ROOT / "ct-l0-007-matrix.json").read_text())
        cases: tuple[tuple[str, Callable[[dict[str, object]], None]], ...] = (
            ("schema", _set_value(("schema",), "wrong")),
            ("pinned", _set_value(("requirements", 0), "build>=1")),
            ("candidates", _set_value(("candidates",), {})),
            ("versions", _set_value(("candidates", 0, "version"), "3.11.0")),
            ("candidate", _set_value(("candidates", 0), "wrong")),
            ("GIL", _set_value(("candidates", 0, "gil"), "optional")),
            ("immutable", _set_value(("candidates", 0, "linux_image"), "python:3.12")),
            ("64 hexadecimal", _set_value(("candidates", 0, "source_sha256"), "bad")),
            ("non-empty string array", _set_value(("required_observations",), [])),
            ("non-empty string array", _set_value(("required_observations",), [1])),
            ("duplicates", _set_value(("required_observations",), ["runtime", "runtime"])),
            ("non-empty string", _set_value(("matrix_id",), "")),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "matrix.json"
            for message, mutate in cases:
                self._assert_invalid_matrix(path, source, message, mutate)
            path.write_text("[]", encoding="utf-8")
            with self.assertRaisesRegex(CompatibilityError, "root must be an object"):
                load_matrix(path)

    def _assert_invalid_matrix(
        self,
        path: Path,
        source: dict[str, object],
        message: str,
        mutate: Callable[[dict[str, object]], None],
    ) -> None:
        candidate = copy.deepcopy(source)
        mutate(candidate)
        path.write_text(json.dumps(candidate), encoding="utf-8")
        with (
            self.subTest(message=message),
            self.assertRaisesRegex(CompatibilityError, message),
        ):
            load_matrix(path)

    def test_report_validation_failure_boundaries(self) -> None:
        matrix_path = CONTRACT_ROOT / "ct-l0-007-matrix.json"
        matrix = load_matrix(matrix_path)

        def assert_invalid(report: dict[str, object], message: str) -> None:
            with (
                self.subTest(message=message),
                self.assertRaisesRegex(CompatibilityError, message),
            ):
                validate_report(matrix, report)

        report = _minimal_report(matrix_path, matrix.digest)
        report["runs"] = {}
        assert_invalid(report, "runs must be an array")

        report = _minimal_report(matrix_path, matrix.digest)
        report["schema"] = "wrong"
        assert_invalid(report, "result schema")

        report = _minimal_report(matrix_path, matrix.digest)
        report["matrix_id"] = "wrong"
        assert_invalid(report, "matrix ID")

        report = _minimal_report(matrix_path, matrix.digest)
        _runs(report).append(cast(dict[str, object], 1))
        assert_invalid(report, "every run")

        for key, value, message in (
            ("unknown", True, "malformed run fields"),
            ("status", "failed", "did not pass"),
            ("interpreter", [], "interpreter version"),
            (
                "interpreter",
                {"version": "3.12.13", "free_threaded": True},
                "standard GIL evidence",
            ),
            ("observations", {}, "observations must be an array"),
            ("observations", [], "observation set"),
            ("product_artifacts", {}, "artifact evidence"),
        ):
            report = _minimal_report(matrix_path, matrix.digest)
            _runs(report)[0][key] = value
            assert_invalid(report, message)

        report = _minimal_report(matrix_path, matrix.digest)
        product = cast(dict[str, dict[str, str]], _runs(report)[0]["product_artifacts"])
        product["generated_clients"]["reason_code"] = "skipped"
        assert_invalid(report, "explicitly not_exercised")

    def test_environment_validation_rejects_empty_unknown_and_duplicate_values(self) -> None:
        matrix_path = CONTRACT_ROOT / "ct-l0-007-matrix.json"
        matrix = load_matrix(matrix_path)
        report = _minimal_report(matrix_path, matrix.digest)
        for environments in ((), ("unknown",), ("macos-host", "macos-host")):
            with (
                self.subTest(environments=environments),
                self.assertRaisesRegex(CompatibilityError, "unsupported environments"),
            ):
                validate_report(matrix, report, environments=environments)


def _set_value(path: tuple[str | int, ...], value: object) -> Callable[[dict[str, object]], None]:
    def mutate(document: dict[str, object]) -> None:
        target: object = document
        for key in path[:-1]:
            target = _descend(target, key)
        _assign(target, path[-1], value)

    return mutate


def _descend(target: object, key: str | int) -> object:
    if isinstance(target, dict) and isinstance(key, str):
        return target[key]
    if isinstance(target, list) and isinstance(key, int):
        return target[key]
    raise TypeError("test mutation path does not match fixture shape")


def _assign(target: object, key: str | int, value: object) -> None:
    if isinstance(target, dict) and isinstance(key, str):
        target[key] = value
        return
    if isinstance(target, list) and isinstance(key, int):
        target[key] = value
        return
    raise TypeError("test mutation target does not match fixture shape")


def _minimal_report(matrix_path: Path, digest: str) -> dict[str, object]:
    source = json.loads(matrix_path.read_text())
    required = source["required_observations"]
    runs: list[dict[str, object]] = []
    for candidate in source["candidates"]:
        observations = [
            {
                "id": observation,
                "status": "passed",
                "duration_ms": 1,
                "details": {"gil_enabled": True} if observation == "runtime" else {},
            }
            for observation in required
        ]
        runs.append(
            {
                "version": candidate["version"],
                "environment": "macos-host",
                "status": "passed",
                "interpreter": {"version": candidate["version"], "free_threaded": False},
                "observations": observations,
                "product_artifacts": {
                    "release_helper_wheel": {
                        "status": "not_exercised",
                        "reason_code": "artifact_absent",
                    },
                    "generated_clients": {
                        "status": "not_exercised",
                        "reason_code": "artifact_absent",
                    },
                },
            }
        )
    report = {
        "schema": "ctower.compatibility-result/v1",
        "input_digest": digest,
        "matrix_id": source["matrix_id"],
        "runs": runs,
    }
    return copy.deepcopy(report)


def _runs(report: dict[str, object]) -> list[dict[str, object]]:
    return cast(list[dict[str, object]], report["runs"])


def _observations(report: dict[str, object]) -> list[dict[str, object]]:
    return cast(list[dict[str, object]], _runs(report)[0]["observations"])

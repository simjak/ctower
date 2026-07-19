"""Deterministic authored-contract traceability index vectors."""

from __future__ import annotations

import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from typing import cast

from jsonschema import Draft202012Validator

from tools.checks.traceability import main as traceability_main

_GENERATED_NOTICE = "DO NOT EDIT: generated file; regenerate from declared inputs."


class TraceabilityTests(unittest.TestCase):
    root = Path(__file__).parents[3]

    def test_authored_source_map_validates_against_its_schema(self) -> None:
        schema = json.loads(
            (self.root / "contracts/traceability/traceability-sources.schema.json").read_text(
                encoding="utf-8"
            )
        )
        source_map = json.loads(
            (self.root / "contracts/traceability/sources.json").read_text(encoding="utf-8")
        )

        Draft202012Validator(schema).validate(source_map)

    def test_committed_index_is_deterministic_and_maps_stable_ids(self) -> None:
        index = json.loads(
            (self.root / "generated/traceability-index.json").read_text(encoding="utf-8")
        )
        references = cast(dict[str, list[str]], index["references"])

        self.assertEqual(traceability_main(["--root", str(self.root), "--check"]), 0)
        self.assertEqual(index["_notice"], _GENERATED_NOTICE)
        self.assertIn("INV-43", references)
        self.assertIn("AC-WF-22", references)
        self.assertIn(
            "contracts/workflow/review-plan.schema.json",
            references["INV-43"],
        )

    def test_generated_manifest_owns_the_committed_index(self) -> None:
        manifest = json.loads(
            (self.root / "generated/.generated-manifest.json").read_text(encoding="utf-8")
        )
        entries = [
            artifact
            for artifact in manifest["artifacts"]
            if artifact["id"] == "contract-traceability-index"
        ]

        self.assertEqual(manifest["_notice"], _GENERATED_NOTICE)
        self.assertEqual(len(entries), 1)
        expected_digest = hashlib.sha256(
            (self.root / "generated/traceability-index.json").read_bytes()
        ).hexdigest()
        self.assertEqual(
            entries[0]["outputs"],
            [
                {
                    "path": "generated/traceability-index.json",
                    "sha256": f"sha256:{expected_digest}",
                }
            ],
        )

    def test_invalid_reference_duplicate_source_and_missing_artifact_fail(self) -> None:
        cases: dict[str, tuple[list[dict[str, object]], str]] = {
            "invalid reference": (
                [{"path": "contracts/example.json", "references": ["NOT-A-STABLE-ID"]}],
                "invalid stable ID",
            ),
            "duplicate source": (
                [
                    {"path": "contracts/example.json", "references": ["INV-43"]},
                    {"path": "contracts/example.json", "references": ["AC-WF-22"]},
                ],
                "path duplicates",
            ),
            "missing artifact": (
                [{"path": "contracts/missing.json", "references": ["INV-43"]}],
                "does not exist",
            ),
        }
        for label, (artifacts, expected_error) in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as name:
                root = Path(name)
                self._write_fixture(root, artifacts)
                errors = io.StringIO()
                with redirect_stderr(errors):
                    exit_code = traceability_main(["--root", str(root), "--check"])

                self.assertEqual(exit_code, 1)
                self.assertIn(expected_error, errors.getvalue())

    def test_unowned_normative_contract_or_package_fails_closed(self) -> None:
        for relative in (
            "contracts/unowned.schema.json",
            "packs/unowned.yaml",
        ):
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as name:
                root = Path(name)
                self._write_fixture(
                    root,
                    [{"path": "contracts/example.json", "references": ["INV-43"]}],
                )
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("{}\n", encoding="utf-8")

                errors = io.StringIO()
                with redirect_stderr(errors):
                    exit_code = traceability_main(["--root", str(root), "--check"])

                self.assertEqual(exit_code, 1)
                self.assertIn(f"unowned normative artifact: {relative}", errors.getvalue())

    def _write_fixture(self, root: Path, artifacts: list[dict[str, object]]) -> None:
        (root / "contracts/traceability").mkdir(parents=True)
        (root / "contracts/example.json").write_text("{}\n", encoding="utf-8")
        (root / "SPEC.md").write_text(
            "## Review rounds\n\n1. **INV-43 — Plan.**\n\n"
            '| <a id="ac-wf-22"></a>AC-WF-22 | condition | evidence |\n',
            encoding="utf-8",
        )
        payload = {"schema": "ctower.traceability-sources/v1", "artifacts": artifacts}
        (root / "contracts/traceability/sources.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )


if __name__ == "__main__":
    unittest.main()

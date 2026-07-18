"""Validate every authored L0 JSON Schema through its public artifact."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


class AuthoredContractTests(unittest.TestCase):
    root = Path(__file__).parents[3]

    def test_every_authored_json_schema_is_valid_draft_2020_12(self) -> None:
        schemas = tuple(sorted((self.root / "contracts").rglob("*.schema.json")))
        self.assertGreaterEqual(len(schemas), 4)
        for path in schemas:
            with self.subTest(path=path.relative_to(self.root)):
                schema = json.loads(path.read_text(encoding="utf-8"))
                Draft202012Validator.check_schema(schema)


if __name__ == "__main__":
    unittest.main()

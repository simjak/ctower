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

    def test_contract_readmes_do_not_regress_to_pre_runtime_claims(self) -> None:
        contracts = (self.root / "contracts/README.md").read_text(encoding="utf-8")
        bootstrap = (self.root / "contracts/bootstrap/README.md").read_text(encoding="utf-8")

        self.assertNotIn("not an active runtime API", contracts)
        self.assertNotIn("capability issuer and route do not exist yet", contracts)
        self.assertIn("contracts exercised by the current development walking slice", contracts)
        self.assertNotIn(
            "no route, token issuer, database mutation, or runtime authority", bootstrap
        )
        self.assertNotIn("When implemented, the handler", bootstrap)
        self.assertIn("kernel-owned Postgres Record implementation", bootstrap)
        self.assertIn("The handler uses one serializable transaction", bootstrap)


if __name__ == "__main__":
    unittest.main()

"""Positive and negative first-tenant request contract vectors."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from typing import Any, ClassVar

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError


class FirstTenantContractTests(unittest.TestCase):
    root = Path(__file__).parents[3]
    schema: ClassVar[dict[str, Any]]
    example: ClassVar[dict[str, Any]]
    validator: ClassVar[Draft202012Validator]

    @classmethod
    def setUpClass(cls) -> None:
        schema_path = cls.root / "contracts/bootstrap/first-tenant-request.schema.json"
        example_path = cls.root / "examples/first-tenant/bootstrap-request.example.json"
        cls.schema = json.loads(schema_path.read_text(encoding="utf-8"))
        cls.example = json.loads(example_path.read_text(encoding="utf-8"))
        cls.validator = Draft202012Validator(cls.schema)

    def test_secret_free_example_is_valid(self) -> None:
        self.validator.validate(self.example)

    def test_transport_authority_cannot_enter_the_body(self) -> None:
        for forbidden in ("bootstrap_token", "idempotency_key", "authorization"):
            with self.subTest(field=forbidden):
                candidate = copy.deepcopy(self.example)
                candidate[forbidden] = "must-not-be-here"
                with self.assertRaises(ValidationError):
                    self.validator.validate(candidate)

    def test_vault_reference_cannot_carry_a_secret_value(self) -> None:
        candidate = copy.deepcopy(self.example)
        candidate["vault_binding_refs"][0]["value"] = "plaintext-secret"
        with self.assertRaises(ValidationError):
            self.validator.validate(candidate)

    def test_runtime_or_catalog_authority_cannot_enter_the_body(self) -> None:
        for forbidden in ("workflow", "skills", "ticket", "session", "verdict"):
            with self.subTest(field=forbidden):
                candidate = copy.deepcopy(self.example)
                candidate[forbidden] = {}
                with self.assertRaises(ValidationError):
                    self.validator.validate(candidate)

    def test_at_least_one_vault_binding_reference_is_required(self) -> None:
        candidate = copy.deepcopy(self.example)
        candidate["vault_binding_refs"] = []
        with self.assertRaises(ValidationError):
            self.validator.validate(candidate)


if __name__ == "__main__":
    unittest.main()

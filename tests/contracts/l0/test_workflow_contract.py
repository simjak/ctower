"""Domain-neutral workflow stage metadata vectors."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from typing import Any, ClassVar

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError


class WorkflowContractTests(unittest.TestCase):
    root = Path(__file__).parents[3]
    schema: ClassVar[dict[str, Any]]
    example: ClassVar[dict[str, Any]]
    validator: ClassVar[Draft202012Validator]

    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = json.loads(
            (cls.root / "contracts/workflow/workflow.schema.json").read_text(encoding="utf-8")
        )
        cls.example = json.loads(
            (cls.root / "packs/workflows/engineering.software-factory/v1.yaml").read_text(
                encoding="utf-8"
            )
        )
        cls.validator = Draft202012Validator(cls.schema)

    def test_software_factory_pack_declares_activity_for_every_stage(self) -> None:
        self.validator.validate(self.example)
        stages = self.example["stages"]
        self.assertEqual(len(stages), 16)
        self.assertTrue(all("activity_class" in stage for stage in stages))
        self.assertEqual(
            next(stage for stage in stages if stage["key"] == "risk-derived-review")[
                "activity_class"
            ],
            "verification",
        )

    def test_activity_class_is_fixed_and_domain_neutral(self) -> None:
        allowed = set(self.schema["$defs"]["activityClass"]["enum"])
        self.assertEqual(allowed, {"work", "verification"})
        self.assertTrue(
            allowed.isdisjoint(
                {"think", "plan", "design", "implement", "qa", "review", "docs", "release"}
            )
        )

    def test_unknown_or_missing_activity_class_is_rejected(self) -> None:
        for replacement in (None, "software-engineering-review"):
            with self.subTest(replacement=replacement):
                candidate = copy.deepcopy(self.example)
                if replacement is None:
                    del candidate["stages"][0]["activity_class"]
                else:
                    candidate["stages"][0]["activity_class"] = replacement
                with self.assertRaises(ValidationError):
                    self.validator.validate(candidate)


if __name__ == "__main__":
    unittest.main()

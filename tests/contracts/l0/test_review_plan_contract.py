"""Generic ReviewPlan contract and software-factory example vectors."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from typing import Any, ClassVar

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError


class ReviewPlanContractTests(unittest.TestCase):
    root = Path(__file__).parents[3]
    schema: ClassVar[dict[str, Any]]
    gate_policy: ClassVar[dict[str, Any]]
    plans: ClassVar[dict[str, dict[str, Any]]]
    execution_policy: ClassVar[dict[str, Any]]
    risk_selectors: ClassVar[dict[str, dict[str, Any]]]
    validator: ClassVar[Draft202012Validator]

    @classmethod
    def setUpClass(cls) -> None:
        schema_path = cls.root / "contracts/workflow/review-plan.schema.json"
        pack_path = cls.root / "packs/policies/gates/software-factory-v1.yaml"
        cls.schema = json.loads(schema_path.read_text(encoding="utf-8"))
        pack = json.loads(pack_path.read_text(encoding="utf-8"))
        cls.gate_policy = pack
        cls.plans = pack["review_plans"]
        cls.execution_policy = json.loads(
            (cls.root / "packs/policies/execution/software-factory-v1.yaml").read_text(
                encoding="utf-8"
            )
        )
        cls.risk_selectors = cls.execution_policy["risk_defaults"]
        cls.validator = Draft202012Validator(cls.schema)

    def test_every_software_factory_child_plan_uses_the_generic_schema(self) -> None:
        self.assertEqual(set(self.plans), {"low", "standard", "elevated", "critical"})
        for risk, plan in self.plans.items():
            with self.subTest(risk=risk):
                self.validator.validate(plan)
                self.assertGreater(plan["limits"]["max_nonpassing_rounds"], 0)
                self.assertNotIn("required_passing_rounds", plan)
                self.assertNotIn("total_executions", plan)
                self.assertNotIn("total_executions", plan["limits"])

    def test_child_identity_is_owned_only_by_the_parent_gate_policy(self) -> None:
        gate_policy_ref = f"{self.gate_policy['key']}@{self.gate_policy['revision']}"
        for risk, plan in self.plans.items():
            with self.subTest(risk=risk):
                self.assertTrue({"key", "revision", "status"}.isdisjoint(plan))
                self.assertEqual(plan["policy_ref"], gate_policy_ref)
                self.assertEqual(
                    self.risk_selectors[risk]["review_plan_ref"],
                    f"{gate_policy_ref}#review-plans.{risk}",
                )

    def test_risk_selector_uses_only_the_canonical_parent_child_reference(self) -> None:
        self.assertNotIn("hard_automatic_ceiling", self.execution_policy)
        self.assertEqual(set(self.risk_selectors), set(self.plans))
        gate_policy_ref = f"{self.gate_policy['key']}@{self.gate_policy['revision']}"
        for risk, selector in self.risk_selectors.items():
            with self.subTest(risk=risk):
                self.assertEqual(set(selector), {"review_plan_ref"})
                plan = self.plans[risk]
                self.assertEqual(plan["policy_ref"], gate_policy_ref)
                self.assertEqual(
                    selector["review_plan_ref"],
                    f"{gate_policy_ref}#review-plans.{risk}",
                )

    def test_repeated_passing_round_scalar_is_forbidden(self) -> None:
        invalid = copy.deepcopy(self.plans["standard"])
        invalid["required_passing_rounds"] = 2
        with self.assertRaises(ValidationError):
            self.validator.validate(invalid)

    def test_software_factory_review_plans_use_only_v1_limits(self) -> None:
        expected_limit_keys = {
            "max_nonpassing_rounds",
            "max_repairs_per_lineage",
            "max_candidate_generations",
        }
        for risk, plan in self.plans.items():
            with self.subTest(risk=risk):
                self.assertEqual(set(plan["limits"]), expected_limit_keys)

    def test_software_factory_example_plan_topologies_and_limits_are_exact(self) -> None:
        expected = {
            "low": ({"code-review"}, set(), (1, 1, 2)),
            "standard": ({"code-review"}, set(), (2, 2, 4)),
            "elevated": (
                {"code-review"},
                {"security", "rendered-design"},
                (2, 2, 4),
            ),
            "critical": (
                {"code-review", "security"},
                {"rendered-design"},
                (1, 1, 3),
            ),
        }
        for risk, plan in self.plans.items():
            with self.subTest(risk=risk):
                required, additional, limits = expected[risk]
                self.assertEqual({item["name"] for item in plan["required_perspectives"]}, required)
                self.assertEqual(
                    {item["perspective"]["name"] for item in plan["additional_perspectives"]},
                    additional,
                )
                observed_limits = plan["limits"]
                self.assertEqual(
                    (
                        observed_limits["max_nonpassing_rounds"],
                        observed_limits["max_repairs_per_lineage"],
                        observed_limits["max_candidate_generations"],
                    ),
                    limits,
                )

    def test_observed_execution_fields_are_forbidden(self) -> None:
        plan = copy.deepcopy(self.plans["standard"])
        plan["limits"]["total_executions"] = 1
        with self.assertRaises(ValidationError):
            self.validator.validate(plan)

        plan = copy.deepcopy(self.plans["standard"])
        plan["total_executions"] = 1
        with self.assertRaises(ValidationError):
            self.validator.validate(plan)

    def test_schema_is_domain_neutral_and_accepts_non_engineering_references(self) -> None:
        plan = copy.deepcopy(self.plans["low"])
        plan["workflow_ref"] = "accounting.monthly-close@4"
        plan["policy_ref"] = "accounting.separation-of-duties@2"
        plan["required_perspectives"] = [
            {
                "name": "ledger-integrity",
                "workflow_ref": "accounting.monthly-close@4#reconcile",
                "policy_ref": "accounting.review.ledger-integrity@2",
            }
        ]
        self.validator.validate(plan)

        enum_values = {
            item
            for node in self._nodes(self.schema)
            if isinstance(node, dict)
            for item in node.get("enum", [])
            if isinstance(item, str)
        }
        self.assertTrue(enum_values.isdisjoint({"engineer", "designer", "qa", "cso", "reviewer"}))

    def test_required_and_conditional_perspectives_fail_closed(self) -> None:
        plan = copy.deepcopy(self.plans["elevated"])
        plan["required_perspectives"] = []
        with self.assertRaises(ValidationError):
            self.validator.validate(plan)

        plan = copy.deepcopy(self.plans["elevated"])
        del plan["additional_perspectives"][0]["applicability"]["predicate_ref"]
        with self.assertRaises(ValidationError):
            self.validator.validate(plan)

    def _nodes(self, value: object) -> list[object]:
        nodes = [value]
        if isinstance(value, dict):
            for item in value.values():
                nodes.extend(self._nodes(item))
        elif isinstance(value, list):
            for item in value:
                nodes.extend(self._nodes(item))
        return nodes


if __name__ == "__main__":
    unittest.main()

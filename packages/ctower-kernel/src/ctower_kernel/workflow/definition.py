"""Workflow Definition source Interface: the authored S7/S8 configuration source.

One strict `workflows/<name>.yaml` resource is the fifth configuration layer. S7's
visual stage editor and S8's YAML view are two projections of that one resource, and
this Interface is the only path from it into the kernel. Validation has three named
gates and calling all three merely "valid" is forbidden: `load_workflow_definition`
decides source-schema validity, `resolve_workflow_definition` decides the resolved
plan, and `normalized_workflow_payload` renders the publishable payload.
"""

from ctower_kernel.workflow._definition_export import canonical_yaml
from ctower_kernel.workflow._definition_model import (
    EvidenceSlot,
    ProjectOverlay,
    SkipSet,
    StageDefinition,
    TransitionDefinition,
    WorkflowDefinition,
    WorkflowDefinitionRefusedError,
)
from ctower_kernel.workflow._definition_plan import (
    ResolvedStage,
    ResolvedWorkflow,
    WorkflowResolution,
)
from ctower_kernel.workflow._definition_plan import (
    normalized_payload as normalized_workflow_payload,
)
from ctower_kernel.workflow._definition_plan import (
    resolve_definition as resolve_workflow_definition,
)
from ctower_kernel.workflow._definition_source import (
    SOURCE_SCHEMA_ID,
)
from ctower_kernel.workflow._definition_source import (
    load_definition as load_workflow_definition,
)

__all__ = [
    "SOURCE_SCHEMA_ID",
    "EvidenceSlot",
    "ProjectOverlay",
    "ResolvedStage",
    "ResolvedWorkflow",
    "SkipSet",
    "StageDefinition",
    "TransitionDefinition",
    "WorkflowDefinition",
    "WorkflowDefinitionRefusedError",
    "WorkflowResolution",
    "canonical_yaml",
    "load_workflow_definition",
    "normalized_workflow_payload",
    "resolve_workflow_definition",
]

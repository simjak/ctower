"""Public Interface for versioned runtime compatibility evidence."""

from tools.compatibility.interface import execute_matrix, load_matrix, validate_report, write_report
from tools.compatibility.models_core import (
    CompatibilityError,
    CompatibilityMatrix,
)
from tools.compatibility.models_report import CompatibilityReport
from tools.compatibility.process import ExecutionPort, LocalExecutionPort, ProbePort

__all__ = [
    "CompatibilityError",
    "CompatibilityMatrix",
    "CompatibilityReport",
    "ExecutionPort",
    "LocalExecutionPort",
    "ProbePort",
    "execute_matrix",
    "load_matrix",
    "validate_report",
    "write_report",
]

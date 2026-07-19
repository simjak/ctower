"""Public Interface for versioned runtime compatibility evidence."""

from tools.compatibility.contract import CompatibilityError, CompatibilityMatrix
from tools.compatibility.interface import execute_matrix, load_matrix, validate_report, write_report

__all__ = [
    "CompatibilityError",
    "CompatibilityMatrix",
    "execute_matrix",
    "load_matrix",
    "validate_report",
    "write_report",
]

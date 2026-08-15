"""Thin online ctower command-line Adapter."""

from ctowerctl._parser import parse_arguments
from ctowerctl.interface import main

__all__ = ["main", "parse_arguments"]

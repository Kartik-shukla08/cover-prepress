"""Calculation engine package for Markee Books."""

from .base import BasePublisherCalculator
from .kdp import KDPCalculator
from .ingram import IngramSparkCalculator
from .lulu import LuluCalculator
from .universal import UniversalCalculator
from .orchestrator import (
    get_calculator,
    calculate_specifications,
    calculate_spine,
    calculate_cover,
    calculate_interior,
    calculate_economics,
)

__all__ = [
    "BasePublisherCalculator",
    "KDPCalculator",
    "IngramSparkCalculator",
    "LuluCalculator",
    "UniversalCalculator",
    "get_calculator",
    "calculate_specifications",
    "calculate_spine",
    "calculate_cover",
    "calculate_interior",
    "calculate_economics",
]

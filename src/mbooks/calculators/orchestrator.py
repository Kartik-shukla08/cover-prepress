"""Orchestration dispatcher for publisher physical and economic calculations."""

from __future__ import annotations
from typing import Optional

from mbooks.domain.book import BookConfiguration
from mbooks.domain.enums import Publisher
from mbooks.domain.geometry import (
    SpineSpecification,
    CoverDimensions,
    InteriorDimensions,
    CalculatedSpecification,
)
from mbooks.domain.economics import PrintEconomics
from .base import BasePublisherCalculator
from .kdp import KDPCalculator
from .ingram import IngramSparkCalculator
from .lulu import LuluCalculator
from .universal import UniversalCalculator

# Cached singleton calculator instances
_CALCULATORS: dict[str, BasePublisherCalculator] = {
    "KDP": KDPCalculator(),
    "INGRAMSPARK": IngramSparkCalculator(),
    "LULU": LuluCalculator(),
    "UNIVERSAL": UniversalCalculator(),
}


def get_calculator(publisher: Publisher | str | None) -> BasePublisherCalculator:
    """Retrieve the appropriate publisher calculator or the universal fallback."""
    if publisher is None:
        return _CALCULATORS["UNIVERSAL"]

    pub_key = publisher.value.upper() if isinstance(publisher, Publisher) else str(publisher).upper()
    return _CALCULATORS.get(pub_key, _CALCULATORS["UNIVERSAL"])


def calculate_specifications(
    config: BookConfiguration, list_price: float | None = None
) -> CalculatedSpecification:
    """Calculate the complete physical specifications and economics for a book configuration.

    Answers: "Given this configuration, what are the exact dimensions, spine width,
    bleed canvas, gutter margins, and print specifications?"
    """
    calculator = get_calculator(config.publisher)
    return calculator.calculate(config, list_price=list_price)


def calculate_spine(config: BookConfiguration) -> SpineSpecification:
    """Calculate only spine dimensions and text eligibility for a book configuration."""
    calculator = get_calculator(config.publisher)
    return calculator.calculate_spine(config)


def calculate_cover(config: BookConfiguration) -> CoverDimensions:
    """Calculate only cover canvas layout dimensions and guides for a book configuration."""
    calculator = get_calculator(config.publisher)
    return calculator.calculate_cover(config)


def calculate_interior(config: BookConfiguration) -> InteriorDimensions:
    """Calculate only interior page bounding box and margins for a book configuration."""
    calculator = get_calculator(config.publisher)
    return calculator.calculate_interior(config)


def calculate_economics(
    config: BookConfiguration, list_price: float | None = None
) -> PrintEconomics | None:
    """Calculate only print economics and royalty projections for a book configuration."""
    calculator = get_calculator(config.publisher)
    return calculator.calculate_economics(config, list_price=list_price)

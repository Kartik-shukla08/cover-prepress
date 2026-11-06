"""Base abstract calculator interface for publisher physical and economic calculations."""

from __future__ import annotations
from abc import ABC, abstractmethod

from mbooks.domain.book import BookConfiguration
from mbooks.domain.geometry import (
    SpineSpecification,
    CoverDimensions,
    InteriorDimensions,
    CalculatedSpecification,
)
from mbooks.domain.economics import PrintEconomics


class BasePublisherCalculator(ABC):
    """Abstract base class for publisher-specific calculation engines."""

    @property
    @abstractmethod
    def publisher_name(self) -> str:
        """Publisher identifier e.g. 'KDP', 'IngramSpark', 'Lulu'."""
        pass

    @abstractmethod
    def calculate_spine(self, config: BookConfiguration) -> SpineSpecification:
        """Calculate spine width, spine text allowance, and safety boundaries."""
        pass

    @abstractmethod
    def calculate_cover(
        self, config: BookConfiguration, spine: SpineSpecification | None = None
    ) -> CoverDimensions:
        """Calculate complete cover layout dimensions, bleed, wrap, and fold points."""
        pass

    @abstractmethod
    def calculate_interior(self, config: BookConfiguration) -> InteriorDimensions:
        """Calculate interior page bounding box, bleed, and stepped margin requirements."""
        pass

    @abstractmethod
    def calculate_economics(
        self, config: BookConfiguration, list_price: float | None = None
    ) -> PrintEconomics | None:
        """Calculate estimated printing costs, minimum retail price, and royalties."""
        pass

    def calculate(
        self, config: BookConfiguration, list_price: float | None = None
    ) -> CalculatedSpecification:
        """Orchestrate complete physical specification calculation."""
        spine = self.calculate_spine(config)
        cover = self.calculate_cover(config, spine=spine)
        interior = self.calculate_interior(config)
        economics = self.calculate_economics(config, list_price=list_price)

        return CalculatedSpecification(
            publisher=self.publisher_name,
            spine=spine,
            cover=cover,
            interior=interior,
            spine_width=spine.width,
            spine_text_allowed=spine.spine_text_allowed,
            weight_lb=spine.weight_lb,
            weight_g=spine.weight_g,
            economics=economics,
            unit="in",
        )

"""Typed calculator errors.

All are ``ValueError`` subclasses so existing ``except ValueError`` callers keep working.

* ``EconomicsUnavailableError`` (and subclasses) — the engine refuses to price a
  configuration rather than return a figure it can't stand behind (unsupported
  currency, no published rate row, a product the vendor doesn't sell). Geometry is
  still computed; ``BasePublisherCalculator.calculate`` records the refusal in
  ``CalculatedSpecification.notes`` and leaves ``economics=None``.
* ``PageCountOutOfRangeError`` — the page count is outside the vendor's absolute
  manufacturable range. Raised by geometry, so it propagates.
"""

from __future__ import annotations


class EconomicsUnavailableError(ValueError):
    """The engine cannot produce trustworthy print economics for this configuration."""


class UnsupportedCurrencyError(EconomicsUnavailableError):
    """Requested currency has no published vendor rate / royalty terms in the engine."""


class UnsupportedEconomicsConfigurationError(EconomicsUnavailableError):
    """Vendor does not sell / publish a rate for this product configuration."""


class PageCountOutOfRangeError(ValueError):
    """Page count is outside the vendor's absolute manufacturable range."""

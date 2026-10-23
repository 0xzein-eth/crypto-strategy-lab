"""Prospective research gates and independent, read-only diagnostics.

Keep the original public API available when Python resolves this package
instead of the older top-level research_quality.py module.
"""
from research_quality.legacy_quality import *  # noqa: F401,F403
from research_quality.legacy_quality import _day, _holdout

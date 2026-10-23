"""Legacy public quality API and new research-quality submodules.

A Python package takes precedence over a same-named top-level .py module;
re-export the original functions/constants so engine and older tests remain valid.
"""
from .legacy_quality import *  # noqa: F401,F403
from .legacy_quality import _day, _holdout

"""Compatibility interface for original v8 research_quality.py and new read-only modules.

Keep research_quality.evaluate callable by legacy engine and v2 review code.
"""
from .legacy_quality import evaluate

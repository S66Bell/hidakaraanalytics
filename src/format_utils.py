"""Shared formatting helpers for views (NaN-safe)."""
from __future__ import annotations

import math


def format_yen(value) -> str:
    if value is None:
        return "—"
    try:
        if isinstance(value, float) and math.isnan(value):
            return "—"
    except Exception:
        pass
    return f"¥{int(value):,}"


def format_count(value) -> str:
    if value is None:
        return "—"
    try:
        if isinstance(value, float) and math.isnan(value):
            return "—"
    except Exception:
        pass
    return f"{int(value):,} 件"


def format_pct(value) -> str:
    if value is None:
        return "—"
    try:
        if isinstance(value, float) and math.isnan(value):
            return "—"
    except Exception:
        pass
    return f"{float(value) * 100:.1f}%"


def format_int(value) -> str:
    if value is None:
        return "—"
    try:
        if isinstance(value, float) and math.isnan(value):
            return "—"
    except Exception:
        pass
    return f"{int(value):,}"


def format_yen_round(value) -> str:
    """For averaged yen values where the source may be a float."""
    if value is None:
        return "—"
    try:
        if isinstance(value, float) and math.isnan(value):
            return "—"
    except Exception:
        pass
    return f"¥{int(round(float(value))):,}"


def format_yoy(value) -> str:
    """Signed year-over-year ratio. 0.123 -> '+12.3%', -0.05 -> '-5.0%', None/NaN -> '—'."""
    if value is None:
        return "—"
    try:
        if isinstance(value, float) and math.isnan(value):
            return "—"
    except Exception:
        pass
    return f"{float(value) * 100:+.1f}%"

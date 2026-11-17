"""
PACE - Proactive Audit and Cognitive Evaluation
UI Package: design system, CSS styling, and reusable Streamlit components.
"""

from .styles import apply_styles
from .components import (
    NEAR_MARGIN,
    LEVELS,
    risk_level,
    page_header,
    card_title,
    kpi_figma,
    render_custom_table,
    toast_new,
    idle_expired,
    spacer,
    telemetry_panel,
    play_alert_sound,
)

__all__ = [
    "apply_styles",
    "NEAR_MARGIN",
    "LEVELS",
    "risk_level",
    "page_header",
    "card_title",
    "kpi_figma",
    "render_custom_table",
    "toast_new",
    "idle_expired",
    "spacer",
    "telemetry_panel",
    "play_alert_sound",
]

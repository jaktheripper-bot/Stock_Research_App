"""
UI Views Package for Equity Research App.

Modularized view controllers for public interface:
- state: Session state synchronization, deep linking restoration, and execution pipeline.
- sidebar: Stock lookup search, archive selection, and revision timeline.
- alerts_view: Surveillance alert feed, unread triage, and watchlist preferences.
- dossier_view: Research report input, synthesis execution, metrics, and scorecard rendering.
"""

from ui.views.state import (
    sanitize_ticker_input,
    set_active_dossier_state,
    execute_stock_research,
    restore_dossier_from_url,
)
from ui.views.alerts_view import render_alert_hub
from ui.views.sidebar import render_sidebar
from ui.views.dossier_view import render_dossier_view
from ui.views.policies_view import render_policies_view

__all__ = [
    "sanitize_ticker_input",
    "set_active_dossier_state",
    "execute_stock_research",
    "restore_dossier_from_url",
    "render_alert_hub",
    "render_sidebar",
    "render_dossier_view",
    "render_policies_view",
]

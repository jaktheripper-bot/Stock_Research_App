"""Sitewide Autonomous Multi-Agent Network powered by Google Antigravity SDK.

Exposes domain research squads across Equities, Funds, Debt, Real Assets, and Macro.
"""

from core.agents.equity.forensic_squad import audit_equity_ticker, run_deterministic_equity_audit
from core.agents.funds.lookthrough_squad import audit_fund_lookthrough
from core.agents.debt.credit_squad import audit_credit_offering
from core.agents.reits.real_assets_squad import audit_real_asset, scan_sgb_parity_discounts
from core.agents.macro.macro_squad import audit_macro_yield_environment

__all__ = [
    "audit_equity_ticker",
    "run_deterministic_equity_audit",
    "audit_fund_lookthrough",
    "audit_credit_offering",
    "audit_real_asset",
    "scan_sgb_parity_discounts",
    "audit_macro_yield_environment"
]

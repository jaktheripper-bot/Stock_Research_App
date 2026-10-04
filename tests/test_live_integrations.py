"""Live Provider Integration Smoke Test Suite.

Probes external market data feeds (Yahoo Finance, BSE India) over live network sockets
to verify third-party data structures and API contracts haven't changed upstream.

Run on-demand or before major deployments:
    pytest -m integration
"""

import pytest
import pandas as pd
from core.analysis.fundamentals import get_stock_fundamentals, get_historical_prices
from bse_master import resolve_canonical_symbol, resolve_bse_scrip_code

@pytest.mark.integration
class TestLiveExternalProviders:
    def test_live_yahoo_finance_fundamentals(self):
        """Verifies Yahoo Finance returns valid fundamental data for benchmark ticker INFY."""
        fund = get_stock_fundamentals("INFY")
        assert fund is not None, "Failed to retrieve live fundamentals for INFY"
        assert isinstance(fund, dict), "Fundamentals payload must be a dict"
        assert "current_price" in fund or "market_cap" in fund, "Fundamentals payload missing core valuation fields"
        if fund.get("current_price"):
            assert fund["current_price"] > 100.0, "Current price for INFY out of reasonable historical bounds"

    def test_live_yahoo_finance_historical_prices(self):
        """Verifies Yahoo Finance historical price dataframe schema."""
        df = get_historical_prices("INFY", period="1mo")
        assert df is not None and not df.empty, "Historical dataframe for INFY is empty or None"
        assert "Close" in df.columns, "Historical prices missing 'Close' column"
        assert len(df) >= 15, "1-month historical dataframe returned fewer trading days than expected"

    def test_live_bse_scrip_resolution(self):
        """Verifies BSE Scrip Master resolves canonical symbols and scrip codes."""
        scrip = resolve_bse_scrip_code("INFY")
        assert scrip == "500209", f"Expected BSE scrip code 500209 for INFY, got {scrip}"
        canonical = resolve_canonical_symbol("INFY")
        assert canonical == "INFY", f"Expected canonical INFY, got {canonical}"

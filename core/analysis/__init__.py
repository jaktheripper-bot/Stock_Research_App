"""
Core Analysis Package for Equity Research App.

Modularized institutional equity analysis architecture divided into specialized submodules:
- exceptions: Strict pipeline error hierarchy for diagnostics.
- parser: Health matrix parsing, citations formatting, regulatory sanitization, and differential drift.
- fundamentals: Primary BSE exchange fetching, yfinance fallback, and mathematical indicators.
- engine: Dynamic Gemini Flash cascade, Perplexity failover, and streaming generation.
- delta: Material change gating (>=5% price move, BSE announcements, >14 days) and surgical refresh.
- comparator: Cross-company institutional peer comparison and 3-axis disparity diagnostics.
"""

from core.analysis.exceptions import (
    PipelineError,
    TickerResolutionError,
    ExchangeDataFetchError,
)

from core.analysis.parser import (
    extract_health_matrix,
    remove_health_matrix_text,
    strip_conclusion_sections,
    format_citations_section,
    compare_revisions,
)

from core.analysis.fundamentals import (
    enrich_fundamentals,
    resolve_pe_with_failsafes,
    fetch_latest_bse_announcement,
    fetch_bse_exchange_data,
    get_stock_fundamentals,
    get_historical_prices,
    compute_deterministic_technical_context,
)

from core.analysis.engine import (
    get_system_prompt,
    get_latest_flash_models,
    get_surgical_flash_model,
    stream_genai_with_fallback,
    stream_perplexity_fallback,
    stream_gemini_ungrounded_bypass,
    stream_stock_report,
    generate_stock_report,
    _DISCOVERED_MODELS_CACHE,
)

from core.analysis.delta import (
    evaluate_material_change,
    splice_report_pillars,
    execute_surgical_pillar_update,
)

from core.analysis.comparator import (
    evaluate_company_disparity,
    compare_two_companies,
)

__all__ = [
    # exceptions
    "PipelineError",
    "TickerResolutionError",
    "ExchangeDataFetchError",
    # parser
    "extract_health_matrix",
    "remove_health_matrix_text",
    "strip_conclusion_sections",
    "format_citations_section",
    "compare_revisions",
    # fundamentals
    "enrich_fundamentals",
    "resolve_pe_with_failsafes",
    "fetch_latest_bse_announcement",
    "fetch_bse_exchange_data",
    "get_stock_fundamentals",
    "get_historical_prices",
    "compute_deterministic_technical_context",
    # engine
    "get_system_prompt",
    "get_latest_flash_models",
    "get_surgical_flash_model",
    "stream_genai_with_fallback",
    "stream_perplexity_fallback",
    "stream_gemini_ungrounded_bypass",
    "stream_stock_report",
    "generate_stock_report",
    "_DISCOVERED_MODELS_CACHE",
    # delta
    "evaluate_material_change",
    "splice_report_pillars",
    "execute_surgical_pillar_update",
    # comparator
    "evaluate_company_disparity",
    "compare_two_companies",
]

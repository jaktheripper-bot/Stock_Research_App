"""
Institutional Analysis Facade for Equity Research App.

This module provides a backward-compatible facade for the modularized equity analysis
engine in `core.analysis`. All pipelines, fundamentals fetchers, AI generation routers,
delta triggers, and peer comparison tools are implemented in `core.analysis.*` and
re-exported here to ensure 100% compatibility across all existing imports.
"""

from core.analysis import (
    PipelineError,
    TickerResolutionError,
    ExchangeDataFetchError,
    extract_health_matrix,
    remove_health_matrix_text,
    strip_conclusion_sections,
    format_citations_section,
    compare_revisions,
    enrich_fundamentals,
    resolve_pe_with_failsafes,
    fetch_latest_bse_announcement,
    fetch_bse_exchange_data,
    get_stock_fundamentals,
    get_historical_prices,
    compute_deterministic_technical_context,
    get_system_prompt,
    get_latest_flash_models,
    get_surgical_flash_model,
    stream_genai_with_fallback,
    stream_perplexity_fallback,
    stream_gemini_ungrounded_bypass,
    stream_stock_report,
    generate_stock_report,
    _DISCOVERED_MODELS_CACHE,
    evaluate_material_change,
    splice_report_pillars,
    execute_surgical_pillar_update,
    evaluate_company_disparity,
    compare_two_companies,
    __all__ as _core_analysis_all,
)

__all__ = list(_core_analysis_all)

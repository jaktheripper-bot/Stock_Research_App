"""Moatnomics Visual Identity & Motion Design Tokens (v2.0).

Codifies the canonical visual design system defined in
`docs/VISUAL_IDENTITY_AND_MOTION_GUIDE.md` for use across web templates,
chart renderers, PDF compilers, and automated verification suites.
"""

from __future__ import annotations

from typing import Any, Dict


BRAND_PALETTE_V2: Dict[str, Dict[str, str]] = {
    "forest": {
        "name": "Moatnomics Forest",
        "hex": "#0E3D32",
        "rgb": "14, 61, 50",
        "role": "Primary brand anchor, mastheads, primary actions, active analytical states",
    },
    "ink_navy": {
        "name": "Deep Ink Navy",
        "hex": "#0B2337",
        "rgb": "11, 35, 55",
        "role": "Primary dark canvas, executive headers, high-authority typography",
    },
    "warm_ivory": {
        "name": "Warm Ivory",
        "hex": "#F7F5EE",
        "rgb": "247, 245, 238",
        "role": "Editorial paper reading surface, primary text on dark canvas, PDF print canvas",
    },
    "sage": {
        "name": "Sage Green",
        "hex": "#7DA77A",
        "rgb": "125, 167, 122",
        "role": "Secondary brand accent, Perspective Portal inner arch, secondary chart series",
    },
    "botanical_lime": {
        "name": "Botanical Lime",
        "hex": "#C7E268",
        "rgb": "199, 226, 104",
        "role": "Focal highlight, active tab indicator, key chart callout marker",
    },
    "mist_slate": {
        "name": "Mist Slate",
        "hex": "#D9E3E8",
        "rgb": "217, 227, 232",
        "role": "Secondary text on dark canvas, structural hairlines, chart gridlines",
    },
    "charcoal_slate": {
        "name": "Charcoal Slate",
        "hex": "#282F33",
        "rgb": "40, 47, 51",
        "role": "Body copy on Warm Ivory reading surfaces and exported PDFs",
    },
}


ASSET_CLASS_ACCENTS_V2: Dict[str, Dict[str, str]] = {
    "equities": {
        "label": "Listed Equities",
        "name": "Botanical Sage",
        "hex_dark": "#7DA77A",
        "hex_light": "#1F6F54",
        "subtle_bg": "rgba(125, 167, 122, 0.14)",
        "border": "rgba(125, 167, 122, 0.42)",
    },
    "funds": {
        "label": "Mutual Funds",
        "name": "Deep Cerulean",
        "hex_dark": "#3B7A9E",
        "hex_light": "#2B6282",
        "subtle_bg": "rgba(59, 122, 158, 0.15)",
        "border": "rgba(59, 122, 158, 0.42)",
    },
    "etfs": {
        "label": "National ETFs",
        "name": "Slate Cyan",
        "hex_dark": "#2E8B88",
        "hex_light": "#216E6B",
        "subtle_bg": "rgba(46, 139, 136, 0.15)",
        "border": "rgba(46, 139, 136, 0.42)",
    },
    "debt": {
        "label": "Corporate Debt & NCDs",
        "name": "Warm Ochre",
        "hex_dark": "#C88A32",
        "hex_light": "#A66E1E",
        "subtle_bg": "rgba(200, 138, 50, 0.15)",
        "border": "rgba(200, 138, 50, 0.42)",
    },
    "sovereign": {
        "label": "Sovereign Curve & T-Bills",
        "name": "Imperial Indigo",
        "hex_dark": "#5B5F97",
        "hex_light": "#45497A",
        "subtle_bg": "rgba(91, 95, 151, 0.16)",
        "border": "rgba(91, 95, 151, 0.44)",
    },
    "reits": {
        "label": "REITs, InvITs & SGBs",
        "name": "Terracotta Copper",
        "hex_dark": "#B86545",
        "hex_light": "#964E32",
        "subtle_bg": "rgba(184, 101, 69, 0.15)",
        "border": "rgba(184, 101, 69, 0.42)",
    },
    "msme": {
        "label": "Unlisted MSMEs",
        "name": "Steel Bronze",
        "hex_dark": "#8C7355",
        "hex_light": "#6E583F",
        "subtle_bg": "rgba(140, 115, 85, 0.16)",
        "border": "rgba(140, 115, 85, 0.42)",
    },
}


CANONICAL_ICONS_V2: Dict[str, Dict[str, str]] = {
    "research": {"symbol_id": "icon-research", "label": "Research & Dossiers", "viewbox": "0 0 24 24"},
    "markets": {"symbol_id": "icon-markets", "label": "Markets & Curves", "viewbox": "0 0 24 24"},
    "compare": {"symbol_id": "icon-compare", "label": "Peer & Asset Comparison", "viewbox": "0 0 24 24"},
    "watchlist": {"symbol_id": "icon-watchlist", "label": "Watchlist & Monitoring", "viewbox": "0 0 24 24"},
    "insights": {"symbol_id": "icon-insights", "label": "Nuance & Key Insights", "viewbox": "0 0 24 24"},
    "portfolio": {"symbol_id": "icon-portfolio", "label": "Portfolio Look-Through", "viewbox": "0 0 24 24"},
    "risk": {"symbol_id": "icon-risk", "label": "Risk & Fragility", "viewbox": "0 0 24 24"},
    "valuation": {"symbol_id": "icon-valuation", "label": "Valuation & Cash Flows", "viewbox": "0 0 24 24"},
    "multi-asset": {"symbol_id": "icon-multi-asset", "label": "Multi-Asset Allocation", "viewbox": "0 0 24 24"},
    "screen": {"symbol_id": "icon-screen", "label": "Screener & Filters", "viewbox": "0 0 24 24"},
    "alerts": {"symbol_id": "icon-alerts", "label": "Monitoring & Alerts", "viewbox": "0 0 24 24"},
    "download": {"symbol_id": "icon-download", "label": "Export PDF Dossier", "viewbox": "0 0 24 24"},
}


MOATNOMICS_VISUAL_IDENTITY_V2: Dict[str, Any] = {
    "version": "2.0",
    "logo_system": {
        "name": "The Perspective Portal",
        "primary_symbol": "/static/img/brand/logo-mark.svg",
        "flat_small_symbol": "/static/img/brand/logo-mark-flat.svg",
        "horizontal_wordmark": "/static/img/brand/logo-wordmark.svg",
        "stacked_lockup": "/static/img/brand/logo-stacked.svg",
        "favicon": "/static/img/brand/favicon.svg",
        "flat_threshold_px": 24,
    },
    "palette": BRAND_PALETTE_V2,
    "asset_class_accents": ASSET_CLASS_ACCENTS_V2,
    "typography": {
        "font_serif": "'Playfair Display', 'Tiempos Headline', Georgia, serif",
        "font_sans": "'IBM Plex Sans', 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif",
        "font_mono": "'IBM Plex Mono', 'JetBrains Mono', monospace",
        "tabular_numerals_required": True,
    },
    "canonical_icons": CANONICAL_ICONS_V2,
    "motion_tokens": {
        "micro_ms": 140,
        "state_ms": 200,
        "panel_ms": 280,
        "chart_ms": 500,
        "portal_reveal_ms": 950,
    },
}


def get_asset_class_accent(asset_class: str, theme: str = "dark") -> Dict[str, str]:
    """Return the canonical v2.0 accent metadata for one of the 7 asset classes."""
    key = (asset_class or "equities").strip().lower()
    alias_map = {
        "equity": "equities",
        "stocks": "equities",
        "stock": "equities",
        "fund": "funds",
        "mutual_funds": "funds",
        "etf": "etfs",
        "bond": "debt",
        "bonds": "debt",
        "ncd": "debt",
        "gsec": "sovereign",
        "tbill": "sovereign",
        "reit": "reits",
        "invit": "reits",
        "sgb": "reits",
        "sme": "msme",
    }
    resolved = alias_map.get(key, key)
    entry = ASSET_CLASS_ACCENTS_V2.get(resolved, ASSET_CLASS_ACCENTS_V2["equities"]).copy()
    entry["active_hex"] = entry["hex_light"] if theme == "light" else entry["hex_dark"]
    entry["asset_key"] = resolved
    return entry


def format_visual_asset_filename(
    asset_type: str,
    context: str,
    variant: str,
    theme: str = "dark",
    size: str = "24",
    version: str = "v2",
    ext: str = "svg",
) -> str:
    """Format an asset filename adhering to Section 12 naming convention."""
    clean = lambda s: str(s).strip().lower().replace(" ", "-")
    return (
        f"moatnomics_{clean(asset_type)}_{clean(context)}_{clean(variant)}_"
        f"{clean(theme)}_{clean(size)}_{clean(version)}.{clean(ext).lstrip('.')}"
    )

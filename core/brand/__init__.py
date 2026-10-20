"""Moatnomics Brand Architecture & Identity Package."""

from core.brand.moatnomics_house import (
    MOATNOMICS_BRAND_HOUSE,
    MASTER_AI_PROMPT,
    get_system_prompt_context,
    get_content_framework_brief,
)
from core.brand.visual_identity import (
    BRAND_PALETTE_V2,
    ASSET_CLASS_ACCENTS_V2,
    CANONICAL_ICONS_V2,
    MOATNOMICS_VISUAL_IDENTITY_V2,
    get_asset_class_accent,
    format_visual_asset_filename,
)

__all__ = [
    "MOATNOMICS_BRAND_HOUSE",
    "MASTER_AI_PROMPT",
    "get_system_prompt_context",
    "get_content_framework_brief",
    "BRAND_PALETTE_V2",
    "ASSET_CLASS_ACCENTS_V2",
    "CANONICAL_ICONS_V2",
    "MOATNOMICS_VISUAL_IDENTITY_V2",
    "get_asset_class_accent",
    "format_visual_asset_filename",
]

"""
Moatnomics SEO & Generative Engine Optimization (GEO) Module
============================================================
Provides unified Schema.org JSON-LD generation, /llms.txt protocols, and crawler management.
"""

from core.seo.indexnow import ping_indexnow_urls, get_indexnow_key

__all__ = ["ping_indexnow_urls", "get_indexnow_key"]

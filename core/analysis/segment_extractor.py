"""
Ind AS 108 Statutory Segment, Geography & Order-Book Extractor
==============================================================
Extracts source-attributed operating segment revenue splits, domestic/export mix,
and order-book backlog from archived statutory Pillar 01/02 disclosures or structured
BSE Regulation 33 segment notes. Fails closed for single-segment entities.
"""

import re
from typing import Any, Dict, List, Optional


_NOISE_WORD_RE = re.compile(
    r"(?i)\b(?:"
    r"roce|roe|roa|roi|ebitda|ebit|pbit|opm|npm|pat|pbt|eps|"
    r"margin|margins|cagr|yoy|qoq|mom|growth|decline|contraction|erosion|"
    r"promoter|pledge|pledged|shareholding|stake|holding|holdings|fii|fpi|dii|"
    r"tax|taxation|gst|excise|duty|tariff|subsidy|"
    r"market\s+share|volume\s+share|value\s+share|wallet\s+share|"
    r"ratio|ratios|tier\s*1|cet[\s\-]*1|deposit|lcr|nsfr|"
    r"yield|nim|casa|gnpa|nnpa|npa|crar|car|pcr|credit\s+cost|cost\s+of\s+funds|opex|cost[\s\-]+to[\s\-]+income|spread|"
    r"capex|utilization|utilisation|capacity|occupancy|penetration|localisation|localization|"
    r"churn|attrition|retention|collection|payout|dividend|buyback|"
    r"multiple|pe|ev|beta|volatility|inflation|discount|upside|downside|target|score|weight"
    r")\b"
)

_GEO_WORD_RE = re.compile(
    r"(?i)^(?:domestic|india|exports?|international|overseas|global|rest\s+of\s+(?:the\s+)?world|row|"
    r"north\s+america|americas?|united\s+states|us|usa|europe|uk|emea|apac|asia[\s\-]*pacific|middle\s+east|mena|latam)"
    r"(?:\s+(?:market|markets|business|operations|sales|revenue|revenues))?$"
)

_PCT_ROW_RE = re.compile(
    r"(?m)^[\-\*\•\s]*\**([A-Za-z][A-Za-z0-9\s\&\/\(\)\-]{2,48}?)\**\s*[:—\-]\s*"
    r"(?:(?:₹|INR|Rs\.?)\s*[\d,\.]+\s*(?:Cr|Crore|Crores|Lakh\s*Cr)\s*\()?\s*~?\s*(\d{1,3}(?:\.\d+)?)\s*%"
)

_PIPE_CELL_PCT_RE = re.compile(
    r"\**([A-Za-z][A-Za-z0-9\s\&\/\-]{2,40}?)\**\s*\(\s*~?\s*(\d{1,3}(?:\.\d+)?)(?:\s*[–\-]\s*(\d{1,3}(?:\.\d+)?))?\s*%(?:\s*(?:of\s+)?(?:rev(?:enue)?s?|sales|turnover))?\s*\)",
    re.I,
)

_PROSE_SEG_FROM_RE = re.compile(
    r"(?i)(?:~|approx(?:imately)?\.?\s*|roughly\s*)?(\d{1,2}(?:\.\d+)?)(?:\s*[–\-]\s*(\d{1,2}(?:\.\d+)?))?\s*%\s+(?:of\s+(?:consolidated\s+|total\s+)?(?:revenues?|sales|turnover)\s+)?from\s+([A-Za-z][A-Za-z0-9\s\&\-]{2,36}?)(?=[,\.;\)]|\s+and\s+|\Z)"
)

_PROSE_PAREN_SEG_RE = re.compile(
    r"([A-Z][A-Za-z0-9\s\&\/\-]{2,38}?)\s*\(\s*(?:accounting\s+for\s+|representing\s+|contributing\s+)?(?:~|roughly\s+|approx\.?\s+)?(\d{1,2}(?:\.\d+)?)(?:\s*[–\-]\s*(\d{1,2}(?:\.\d+)?))?\s*%\s+of\s+(?:consolidated\s+|total\s+)?(?:revenues?|sales|turnover)\s*\)"
)

_ORDER_BOOK_RE = re.compile(
    r"(?i)(?<!export\s)(?<!bid-ask\s)(?<!limit\s)\border[\s\-]*(?:books?|backlogs?)\b([^\n]{0,65}?)(?:₹|INR|Rs\.?)\s*([\d,]+(?:\.\d+)?)\+?\s*(Lakh\s*Cr(?:ores?)?|Cr(?:ores?)?)\b"
)

_DOWNSIDE_TRIGGER_WORDS_RE = re.compile(
    r"(?i)\b(?:below|under|less\s+than|fall(?:ing|s)?|drop(?:ping|s)?|contract(?:ing|s|ion)?|deplet(?:ion|ing)|erosion|erod(?:ing|es)|slip(?:ping|s)?|shrink(?:ing|s)?)\b"
)

_FILING_PERIOD_RE = re.compile(
    r"\[VERIFIED\s+FACT[^\]]*?\b((?:Q[1-4]\s+)?(?:FY|CY)\s*20\d{2}(?:\s*[\-–]\s*\d{2,4})?|(?:Q[1-4]\s+)?(?:FY|CY)\d{2})\b[^\]]*\]",
    re.I,
)


def _strip_revision_triggers(text: str) -> str:
    cleaned = re.sub(
        r"(?ims)^#{3,4}\s*What\s+Would\s+Change\s+This\s+View.*?(?=^#{1,3}\s+[^#]|\Z)",
        "\n",
        text,
    )
    cleaned = re.sub(
        r"(?im)^[\-\*\•\s]*\**(?:Evidence\s+That\s+Forces\s+a\s+Revision|What\s+Contradicts\s+This\s+Conclusion)\**[^\n]*$",
        "",
        cleaned,
    )
    return cleaned


def _clean_segment_label(raw: str) -> str:
    lbl = re.sub(r"\(\s*revenue\s+share\s*\)", "", raw, flags=re.I)
    lbl = re.sub(r"\s+", " ", lbl).strip(" -*:|•~")
    lbl = re.sub(r"^(?:the|its|core)\s+", "", lbl, flags=re.I).strip()
    if lbl and lbl[0].islower():
        lbl = lbl[0].upper() + lbl[1:]
    return lbl


def _is_valid_segment_label(label: str, pct: float) -> bool:
    if not label or len(label) < 2 or len(label) > 48:
        return False
    if pct <= 0 or pct > 100:
        return False
    if _NOISE_WORD_RE.search(label):
        return False
    if re.match(r"^(?:fy|cy|q[1-4]|h[12]|pillar|step|tier|phase|note|source|table|total)\b", label, re.I):
        return False
    return True


def _verify_entity_match(clean_ticker: str, report_text: str, company_name: Optional[str] = None) -> bool:
    """Rejects cross-company text leaks when an explicit exchange symbol or corporate name contradicts ticker."""
    head = report_text[:600]
    m_ex = re.search(r"\(\s*(?:NSE|BSE)\s*:\s*([A-Z0-9&\-]{2,15})\s*\)", head)
    if m_ex and m_ex.group(1).upper() != clean_ticker:
        return False
    if company_name and company_name.strip().upper() != clean_ticker and " " in company_name.strip():
        stop_words = {
            "india", "indian", "limited", "ltd", "industries", "industry",
            "company", "corporation", "corp", "enterprises", "holdings",
            "private", "public", "group", "global", "international", "services",
            "solutions", "technologies", "systems", "products", "bank", "finance",
            "financial", "pharma", "pharmaceuticals", "healthcare", "lifesciences",
        }
        tokens = [
            t.lower()
            for t in re.split(r"[^A-Za-z0-9]+", company_name)
            if len(t) >= 4 and t.lower() not in stop_words
        ]
        probe_window = report_text[:3000].lower()
        if tokens and not any(tok in probe_window for tok in tokens) and clean_ticker.lower() not in probe_window:
            return False
    return True


def _parse_revenue_markdown_tables(scope: str, resolved_period: str) -> List[Dict[str, Any]]:
    """Extracts segments from Markdown tables ONLY when column headers denote Revenue Share/Mix (never Market Share)."""
    lines = scope.splitlines()
    results: List[Dict[str, Any]] = []
    seen = set()
    in_rev_table = False

    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("|") or stripped.count("|") < 3:
            in_rev_table = False
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if all(re.match(r"^[:\-\s]+$", c) for c in cells if c):
            continue
        header_join = " | ".join(cells).lower()
        if any(h in header_join for h in ("segment", "vertical", "division", "business", "geography")):
            if "market share" in header_join:
                in_rev_table = False
            elif any(r in header_join for r in ("revenue", "sales", "turnover", "mix", "split", "contribution", "share")):
                in_rev_table = True
            else:
                in_rev_table = False
            continue
        if in_rev_table and len(cells) >= 2:
            lbl = _clean_segment_label(re.sub(r"\*+", "", cells[0]))
            pct_m = None
            for cell in cells[1:]:
                pct_m = re.search(r"~?\s*(\d{1,3}(?:\.\d+)?)\s*%", cell)
                if pct_m:
                    break
            if pct_m:
                pct = float(pct_m.group(1))
                if _is_valid_segment_label(lbl, pct) and lbl.upper() not in seen:
                    seen.add(lbl.upper())
                    results.append({
                        "segment_name": lbl,
                        "revenue_share_pct": round(pct, 1),
                        "epistemic_tier": "VERIFIED_FACT",
                        "source_period": resolved_period,
                    })
    return results


def extract_ind_as_108_segments(
    ticker: str,
    report_text: str,
    filing_period: str = "Latest Audited Filing",
    company_name: Optional[str] = None,
) -> Dict[str, Any]:
    clean_sym = (ticker or "").upper().strip()
    if not report_text or len(report_text.strip()) < 300:
        return {
            "ticker": clean_sym,
            "status": "PENDING_FILING",
            "filing_period": filing_period,
            "segments": [],
            "order_book_cr": None,
        }

    if not _verify_entity_match(clean_sym, report_text, company_name=company_name):
        return {
            "ticker": clean_sym,
            "status": "ENTITY_MISMATCH",
            "filing_period": filing_period,
            "segments": [],
            "order_book_cr": None,
        }

    resolved_period = filing_period
    if filing_period == "Latest Audited Filing":
        fp_m = _FILING_PERIOD_RE.search(report_text[:6000])
        if fp_m:
            norm_fp = re.sub(r"\s+", " ", fp_m.group(1)).strip().upper()
            resolved_period = f"{norm_fp} Statutory Filing"

    # Restrict scan to Pillar 01 & Pillar 02 to prevent shareholding/tax percentages from polluting segments
    p12_match = re.search(
        r"(?ims)^##+\s*(?:Pillar\s*)?0?[12]\b.*?(?=^##+\s*(?:Pillar\s*)?0?[3-7]\b|\Z)",
        report_text,
    )
    raw_scope = p12_match.group(0) if p12_match else report_text[:3500]
    scope = _strip_revision_triggers(raw_scope)

    def _select_valid_split(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        op_group = [c for c in candidates if not _GEO_WORD_RE.match(c["segment_name"])]
        geo_group = [c for c in candidates if _GEO_WORD_RE.match(c["segment_name"])]
        for grp in (op_group, geo_group, candidates):
            tot = sum(s["revenue_share_pct"] for s in grp)
            if len(grp) >= 2 and 65.0 <= tot <= 115.0:
                return grp[:6]
        return []

    # Pass 1: Structured BSE Regulation 33 / Pillar 01-02 bullet & key-value rows
    bullet_candidates: List[Dict[str, Any]] = []
    seen = set()
    for m in _PCT_ROW_RE.finditer(scope):
        label = _clean_segment_label(m.group(1))
        pct = float(m.group(2))
        if not _is_valid_segment_label(label, pct):
            continue
        if label.upper() not in seen:
            seen.add(label.upper())
            bullet_candidates.append({
                "segment_name": label,
                "revenue_share_pct": round(pct, 1),
                "epistemic_tier": "VERIFIED_FACT",
                "source_period": resolved_period,
            })
    segments = _select_valid_split(bullet_candidates)

    # Pass 2: Revenue-tagged Markdown tables (explicitly excluding Market Share tables)
    if not segments:
        segments = _select_valid_split(_parse_revenue_markdown_tables(scope, resolved_period))

    # Pass 3: Horizontal pipe-delimited segment architecture rows (e.g. "| Seg A (~45% Revs) | Seg B (~33% Revs) |")
    if not segments:
        for line in scope.splitlines():
            if "|" not in line or not re.search(r"(?i)%\s*(?:of\s+)?(?:rev(?:enue)?s?|sales|turnover)", line):
                continue
            row_cands: List[Dict[str, Any]] = []
            row_seen = set()
            for m in _PIPE_CELL_PCT_RE.finditer(line):
                lbl = _clean_segment_label(m.group(1))
                p1 = float(m.group(2))
                p2 = float(m.group(3)) if m.group(3) else p1
                pct = (p1 + p2) / 2.0
                if _is_valid_segment_label(lbl, pct) and lbl.upper() not in row_seen:
                    row_seen.add(lbl.upper())
                    row_cands.append({
                        "segment_name": lbl,
                        "revenue_share_pct": round(pct, 1),
                        "epistemic_tier": "VERIFIED_FACT",
                        "source_period": resolved_period,
                    })
            segments = _select_valid_split(row_cands)
            if segments:
                break

    # Pass 4: Explicit prose revenue breakdown sentences ("derives ~48% of revenue from X, ~40% from Y...")
    if not segments:
        for sentence in re.split(r"(?<=[a-zA-Z0-9%\)\]])[.!?]\s+|\n+", scope):
            if not re.search(r"(?i)\b(?:revenues?|sales|turnover)\b", sentence):
                continue
            sent_cands: List[Dict[str, Any]] = []
            sent_seen = set()
            for m in _PROSE_SEG_FROM_RE.finditer(sentence):
                p1 = float(m.group(1))
                p2 = float(m.group(2)) if m.group(2) else p1
                pct = (p1 + p2) / 2.0
                lbl = _clean_segment_label(m.group(3))
                if _is_valid_segment_label(lbl, pct) and lbl.upper() not in sent_seen:
                    sent_seen.add(lbl.upper())
                    sent_cands.append({
                        "segment_name": lbl,
                        "revenue_share_pct": round(pct, 1),
                        "epistemic_tier": "VERIFIED_FACT",
                        "source_period": resolved_period,
                    })
            for m in _PROSE_PAREN_SEG_RE.finditer(sentence):
                lbl = _clean_segment_label(m.group(1))
                p1 = float(m.group(2))
                p2 = float(m.group(3)) if m.group(3) else p1
                pct = (p1 + p2) / 2.0
                if _is_valid_segment_label(lbl, pct) and lbl.upper() not in sent_seen:
                    sent_seen.add(lbl.upper())
                    sent_cands.append({
                        "segment_name": lbl,
                        "revenue_share_pct": round(pct, 1),
                        "epistemic_tier": "VERIFIED_FACT",
                        "source_period": resolved_period,
                    })
            segments = _select_valid_split(sent_cands)
            if segments:
                break

    order_book_cr: Optional[float] = None
    for ob_scope in (scope, _strip_revision_triggers(report_text)):
        for ob_match in _ORDER_BOOK_RE.finditer(ob_scope):
            intervening = ob_match.group(1) or ""
            if _DOWNSIDE_TRIGGER_WORDS_RE.search(intervening):
                continue
            try:
                val = float(ob_match.group(2).replace(",", ""))
                unit = ob_match.group(3).lower()
                if "lakh" in unit:
                    val *= 100000.0
                if val > 0:
                    order_book_cr = round(val, 2)
                    break
            except ValueError:
                order_book_cr = None
        if order_book_cr is not None:
            break

    return {
        "ticker": clean_sym,
        "status": "DISCLOSED" if (segments or order_book_cr) else "SINGLE_SEGMENT_OR_UNDISCLOSED",
        "filing_period": resolved_period,
        "segments": segments[:6],
        "order_book_cr": order_book_cr,
    }

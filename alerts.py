import os
import re
import logging
from datetime import datetime, timezone, timedelta
import requests
import streamlit as st

logger = logging.getLogger("equity_research.alerts")

from db import (
    IST,
    get_watchlist,
    update_watchlist_scan_state,
    record_alert_event,
    get_alert_events,
    get_unread_alert_count,
    mark_alert_as_read,
    mark_all_alerts_as_read,
    add_to_watchlist,
    remove_from_watchlist,
    is_ticker_in_watchlist
)
from bse_master import resolve_bse_scrip_code

# Regulatory & Educational Notice:
# All alerts generated are descriptive diagnostic notices of publicly disseminated exchange data.
# They do not constitute investment advice or buy/sell recommendations per SEBI safe harbor standards.

def fetch_bse_announcements(scrip_code: str, days: int = 45) -> list:
    """
    Fetches official BSE corporate announcements for a given scrip code over a date range.
    Uses BSE India's official public API endpoint.
    """
    if not scrip_code or not str(scrip_code).isdigit():
        return []
    
    try:
        now_dt = datetime.now()
        str_to_date = now_dt.strftime("%Y%m%d")
        str_prev_date = (now_dt - timedelta(days=days)).strftime("%Y%m%d")
        
        url = (
            f"https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w?"
            f"pageno=1&strCat=-1&strPrevDate={str_prev_date}&strScrip={scrip_code}&strSearch=P&strToDate={str_to_date}&strType=C"
        )
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.bseindia.com/",
            "Accept": "application/json, text/plain, */*"
        }
        res = requests.get(url, headers=headers, timeout=6)
        if res.status_code == 200:
            data = res.json()
            table = data.get("Table", [])
            results = []
            for row in table:
                headline = (row.get("HEADLINE") or "").strip()
                news_sub = (row.get("NEWSSUB") or "").strip()
                cat_name = (row.get("CATEGORYNAME") or "").strip()
                dt_tm = (row.get("DT_TM") or "").strip()
                
                # Filter out pure boilerplate empty notices
                if headline or news_sub:
                    results.append({
                        "headline": headline,
                        "news_sub": news_sub,
                        "category_name": cat_name,
                        "dt_tm": dt_tm,
                        "scrip_code": scrip_code
                    })
            return results
    except Exception as e:
        logger.error(f"BSE announcements fetch error for scrip {scrip_code}: {e}")
    return []

def classify_announcement(item: dict) -> tuple:
    """
    Classifies a raw BSE filing into an analytical alert category and urgency tier.
    Returns: (category, severity, alert_title, alert_summary)
    Categories: 'material', 'fundamental', 'valuation', 'routine'
    Severities: 'high', 'medium', 'info'
    """
    headline = item.get("headline", "")
    news_sub = item.get("news_sub", "")
    cat_name = item.get("category_name", "")
    combined = f"{headline} {news_sub} {cat_name}".lower()

    # 1. Fundamental Shifts: Financial Results, Earnings, Guidance
    if any(k in combined for k in ["financial result", "financial statements", "unaudited financial", "audited financial", "quarterly result", "earnings call", "investor presentation"]):
        if any(k in combined for k in ["outcome of board meeting", "approval of financial", "audited"]):
            return "fundamental", "high", "Quarterly Financial Results Released", news_sub or headline
        return "fundamental", "medium", "Financial Results Intimation / Disclosure", news_sub or headline

    # 2. Material Corporate Events: Board meetings, Governance, M&A, Dividends, Capital Allocation
    if any(k in combined for k in ["board meeting intimation", "notice of board meeting"]):
        if "financial result" in combined or "dividend" in combined:
            return "material", "high", "Board Meeting: Financials / Dividend Consideration", news_sub or headline
        return "material", "medium", "Board of Directors Meeting Intimated", news_sub or headline

    if any(k in combined for k in ["resignation", "cessation", "appointment of auditor", "resignation of director", "resignation of auditor", "key managerial"]):
        return "material", "high", "Governance & C-Suite Transition", news_sub or headline

    if any(k in combined for k in ["dividend", "bonus", "stock split", "sub-division", "buyback"]):
        return "material", "high", "Corporate Action: Capital Allocation Event", news_sub or headline

    if any(k in combined for k in ["acquisition", "merger", "amalgamation", "joint venture", "slump sale"]):
        return "material", "high", "Strategic M&A / Corporate Reorganization", news_sub or headline

    if any(k in combined for k in ["credit rating", "rating downgrade", "rating upgrade"]):
        return "material", "high", "Credit Rating Action Disclosed", news_sub or headline

    if any(k in combined for k in ["order received", "contract win", "expansion", "commercial production", "launch"]):
        return "material", "medium", "Commercial Operation / Contract Announcement", news_sub or headline

    if any(k in combined for k in ["insider", "sast", "regulation 29", "regulation 7(2)", "pledge"]):
        return "material", "medium", "Insider / Promoters Shareholding Disclosure", news_sub or headline

    if any(k in combined for k in ["newspaper", "advertisement", "loss of share", "duplicate", "investor meet", "analyst meet"]):
        return "routine", "info", "Routine Regulatory / Administrative Publication", news_sub or headline

    return "material", "medium", "Corporate Disclosure / Regulation 30 Filing", news_sub or headline

def poll_single_stock(item: dict, live_fund: dict = None) -> list:
    """
    Executes surveillance sweep for a single watchlisted stock.
    Checks:
    1. Valuation Shock: Price jump or compression >= 5% vs last scanned price
    2. Material & Fundamental Filings: Ingests new BSE corporate filings
    """
    ticker = item.get("ticker", "").strip().upper()
    scrip_code = item.get("scrip_code") or resolve_bse_scrip_code(ticker)
    short_name = item.get("short_name", ticker)
    last_price = item.get("last_scanned_price")
    last_ann = (item.get("last_scanned_announcement") or "").strip()
    
    new_alerts = []
    current_price = None

    # 1. Price Valuation Volatility Check (±5% Threshold)
    if live_fund:
        p = live_fund.get("current_price") or live_fund.get("currentValue")
        try:
            current_price = float(str(p).replace(",", "").strip())
        except Exception:
            current_price = None

    if current_price and last_price and last_price > 0:
        price_diff = current_price - last_price
        pct_change = (price_diff / last_price) * 100.0
        if abs(pct_change) >= 5.0 and item.get("alert_valuation", True):
            direction = "surged" if pct_change > 0 else "compressed"
            sign = "+" if pct_change > 0 else ""
            severity = "high" if abs(pct_change) >= 7.5 else "medium"
            title = f"Valuation Volatility Alert: {ticker} {direction} {sign}{pct_change:.1f}%"
            details = (
                f"Surveillance quote shift: ₹{last_price:,.2f} → ₹{current_price:,.2f} "
                f"({sign}{pct_change:.1f}% move), crossing the ±5% surveillance sensitivity gate."
            )
            aid = record_alert_event(
                ticker=ticker,
                category="valuation",
                severity=severity,
                title=title,
                details=details,
                source="BSE Exchange Live Feed"
            )
            new_alerts.append({
                "id": aid,
                "ticker": ticker,
                "category": "valuation",
                "severity": severity,
                "title": title,
                "details": details,
                "timestamp": datetime.now(IST).strftime("%d-%b-%Y %H:%M IST")
            })

    # 2. BSE Corporate Announcements Surveillance
    latest_seen_headline = last_ann
    if scrip_code:
        filings = fetch_bse_announcements(scrip_code, days=30)
        for filing in filings:
            f_head = (filing.get("headline") or "").strip()
            f_sub = (filing.get("news_sub") or "").strip()
            filing_id = f"{f_head} | {f_sub}".strip()

            # If we reached the already recorded announcement, stop processing older records
            if last_ann and (last_ann in filing_id or filing_id in last_ann):
                break

            category, severity, alert_title, alert_summary = classify_announcement(filing)

            # Skip routine administrative publications to prevent notification fatigue
            if category == "routine" and not item.get("digest_mode") == "all":
                continue

            # Check user subscription filter
            if category == "material" and not item.get("alert_material", True):
                continue
            if category == "fundamental" and not item.get("alert_fundamental", True):
                continue

            full_title = f"{alert_title}: {ticker}"
            full_details = f"{f_sub or f_head}\n\nCategory: {filing.get('category_name', 'Corporate Filing')} | Filing Time: {filing.get('dt_tm', 'N/A')}"
            
            aid = record_alert_event(
                ticker=ticker,
                category=category,
                severity=severity,
                title=full_title,
                details=full_details,
                source="BSE Corporate Disclosures"
            )
            new_alerts.append({
                "id": aid,
                "ticker": ticker,
                "category": category,
                "severity": severity,
                "title": full_title,
                "details": full_details,
                "timestamp": datetime.now(IST).strftime("%d-%b-%Y %H:%M IST")
            })

        if filings:
            top_filing = filings[0]
            latest_seen_headline = f"{top_filing.get('headline', '')} | {top_filing.get('news_sub', '')}".strip()

    # Update state in watchlist
    update_watchlist_scan_state(
        ticker=ticker,
        price=current_price if current_price else last_price,
        announcement=latest_seen_headline if latest_seen_headline else last_ann
    )

    try:
        if st.session_state.get("notifications_opted_out", False):
            return []
    except Exception:
        pass

    return new_alerts

def run_surveillance_scan(progress_callback=None) -> dict:
    """
    Runs a complete surveillance sweep across all stocks on the user's watchlist.
    Polls live BSE exchange quotes and regulatory filings.
    """
    watchlist = get_watchlist()
    if not watchlist:
        return {"stocks_scanned": 0, "new_alerts_count": 0, "alerts": []}

    total = len(watchlist)
    all_new_alerts = []

    for idx, item in enumerate(watchlist):
        ticker = item.get("ticker", "")
        if progress_callback:
            progress_callback(idx + 1, total, ticker)

        try:
            # Poll fundamentals/quotes for live price
            from analyzer import fetch_bse_exchange_data
            fund = None
            try:
                fund = fetch_bse_exchange_data(ticker)
            except Exception:
                pass

            alerts = poll_single_stock(item, live_fund=fund)
            all_new_alerts.extend(alerts)
        except Exception as e:
            logger.error(f"Error scanning {ticker}: {e}")

    return {
        "stocks_scanned": total,
        "new_alerts_count": len(all_new_alerts),
        "alerts": all_new_alerts
    }

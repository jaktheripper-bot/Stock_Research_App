#!/usr/bin/env python3
"""
Read-only Corpus Substance, Parity & Taxonomy Distribution Probe.
Executes against a sandbox clone of reports.db (or workspace reports.db in read-only mode)
to catch deterministic boilerplate, header-vs-prose numerical drift, cloned fund holdings,
and skewed category/benchmark distributions BEFORE committing code.

Usage:
  python3 .agents/skills/consequence-sandbox-testing/scripts/corpus_substance_probe.py --db reports.db
  python3 .agents/skills/consequence-sandbox-testing/scripts/corpus_substance_probe.py --db reports.db --strict
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Set, Tuple


BANNED_PROSE_SIGNATURES = (
    "operating franchise benefits from steady sponsorship",
    "commands strong institutional backing",
    "current market price of ₹500.00",
    "current market price of ₹100.00",
)


def _shingles(text: str, k: int = 8) -> Set[str]:
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    if len(words) < k:
        return set()
    return {" ".join(words[i : i + k]) for i in range(len(words) - k + 1)}


def _extract_prose_price(text: str) -> float | None:
    m = re.search(r"current market price of\s*₹\s*([0-9,]+(?:\.[0-9]+)?)", text or "", re.IGNORECASE)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def run_probe(db_path: Path, strict: bool = False) -> int:
    if not db_path.exists():
        print(f"[ERROR] Database not found: {db_path}", file=sys.stderr)
        return 2

    uri = f"file:{db_path.resolve()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    cur = conn.cursor()

    issues: List[str] = []

    # 1. Equity Dossier Boilerplate & Header-vs-Prose Parity
    cur.execute(
        """
        SELECT r.ticker, r.report_text, r.baseline_price, c.current_price
        FROM reports r
        LEFT JOIN cached_fundamentals c ON c.ticker = r.ticker
        """
    )
    rep_rows = cur.fetchall()
    boilerplate_tickers: List[str] = []
    price_drift_tickers: List[Tuple[str, float, float]] = []
    shingle_map: Dict[str, Set[str]] = {}

    for ticker, text, base_px, cached_px in rep_rows:
        body = text or ""
        if any(sig in body for sig in BANNED_PROSE_SIGNATURES):
            boilerplate_tickers.append(ticker)
        prose_px = _extract_prose_price(body)
        ref_px = float(cached_px or base_px or 0.0)
        if prose_px is not None and ref_px > 0:
            rel_diff = abs(prose_px - ref_px) / ref_px
            if rel_diff > 0.35:
                price_drift_tickers.append((ticker, ref_px, prose_px))
        shingle_map[ticker] = _shingles(body)

    # Exhaustive pairwise Jaccard check using inverted 8-gram postings to stay fast across entire table
    from collections import defaultdict

    inverted: Dict[str, List[str]] = defaultdict(list)
    for t_sym, s_set in shingle_map.items():
        for sh in s_set:
            inverted[sh].append(t_sym)

    candidate_pairs: Counter[Tuple[str, str]] = Counter()
    for tickers_sharing in inverted.values():
        if len(tickers_sharing) < 2 or len(tickers_sharing) > 250:
            # Note: if >250 dossiers share the exact same 8-gram, record pairs among first 20 representatives too
            subset = tickers_sharing[:20] if len(tickers_sharing) > 250 else tickers_sharing
        else:
            subset = tickers_sharing
        for i in range(len(subset)):
            for j in range(i + 1, len(subset)):
                a, b = (subset[i], subset[j]) if subset[i] < subset[j] else (subset[j], subset[i])
                candidate_pairs[(a, b)] += 1

    high_overlap_pairs: List[Tuple[str, str, float]] = []
    for (t1, t2), shared_cnt in candidate_pairs.items():
        if shared_cnt < 10:
            continue
        s1, s2 = shingle_map[t1], shingle_map[t2]
        union_len = len(s1 | s2)
        if union_len > 0:
            jaccard = shared_cnt / union_len
            if jaccard > 0.25:
                high_overlap_pairs.append((t1, t2, round(jaccard * 100, 1)))

    print(f"[1/4] Equity Dossiers Checked: {len(rep_rows)}")
    print(f"      - Banned boilerplate signatures: {len(boilerplate_tickers)}")
    print(f"      - Header-vs-Prose price drift (>35%): {len(price_drift_tickers)}")
    print(f"      - High 8-gram overlap pairs (>25% across corpus): {len(high_overlap_pairs)}")
    if boilerplate_tickers:
        issues.append(f"{len(boilerplate_tickers)} equity dossiers contain static boilerplate")
    if price_drift_tickers:
        issues.append(f"{len(price_drift_tickers)} equity dossiers contradict header price in prose")
    if high_overlap_pairs:
        issues.append(f"{len(high_overlap_pairs)} equity dossier pairs exceed 25% 8-gram similarity")

    # 2. Mutual Fund Cloned Portfolios & Template Dossiers (group by distinct canonical scheme stem so AMFI/slug twins are not misflagged)
    def _mf_stem(nm: str) -> str:
        s = re.sub(
            r"(?i)\b(direct|regular|plan|growth|option|idcw|dividend(?!\s+yield\b)|payout|reinvestment)\b",
            " ",
            nm or "",
        )
        s = re.sub(r"[^a-zA-Z0-9]+", " ", s).strip().upper()
        s = re.sub(r"\s+", " ", s)
        return re.sub(r"\b(FLEXI|LARGE|MID|SMALL|MULTI)\s+CAP\b", r"\1CAP", s)

    cur.execute("SELECT scheme_code, scheme_name FROM mutual_fund_schemes")
    mf_names = {str(sc): str(sn or sc) for sc, sn in cur.fetchall()}
    cur.execute(
        """
        SELECT scheme_code, GROUP_CONCAT(identifier || ':' || ROUND(weight_pct, 2), ',') as sig
        FROM (SELECT DISTINCT scheme_code, holding_type, identifier, weight_pct FROM mutual_fund_holdings ORDER BY scheme_code, identifier)
        GROUP BY scheme_code
        """
    )
    sig_stems: Dict[str, set] = defaultdict(set)
    for sc, sig in cur.fetchall():
        if sig:
            sig_stems[sig].add(_mf_stem(mf_names.get(str(sc), str(sc))) or str(sc))
    cloned_mf_groups = [(len(stems), sig) for sig, stems in sig_stems.items() if len(stems) > 1]
    cur.execute("SELECT COUNT(*), SUM(CASE WHEN dossier_text LIKE '%With an Active Share of%' THEN 1 ELSE 0 END) FROM fund_forensic_dossiers")
    tot_ffd, det_ffd = cur.fetchone()
    tot_ffd = tot_ffd or 0
    det_ffd = det_ffd or 0
    print(f"[2/4] Mutual Funds Checked: {tot_ffd} forensic dossiers")
    print(f"      - Deterministic template narratives: {det_ffd}")
    print(f"      - Cloned portfolio vectors shared across multiple schemes: {len(cloned_mf_groups)}")
    if cloned_mf_groups:
        issues.append(f"{len(cloned_mf_groups)} cloned holdings vectors shared across distinct MF schemes")
    if det_ffd > 0:
        issues.append(f"{det_ffd} mutual fund forensic dossiers use static template narrative")

    # 3. ETF Category & Benchmark Distribution Check
    cur.execute("SELECT category, underlying_index, scheme_name FROM etf_matrix")
    etf_rows = cur.fetchall()
    cat_counts = Counter(r[0] for r in etf_rows)
    aditya_it_mismatches = [
        r[2]
        for r in etf_rows
        if "ADITYA" in (r[2] or "").upper()
        and "IT" not in (r[2] or "").upper().replace("ADITYA", "")
        and r[1] == "Nifty IT TRI"
    ]
    print(f"[3/4] ETF Matrix Checked: {len(etf_rows)} ETFs | Top categories: {cat_counts.most_common(3)}")
    print(f"      - Substring 'ADITYA' -> 'Nifty IT TRI' collisions: {len(aditya_it_mismatches)}")
    if aditya_it_mismatches:
        issues.append(f"{len(aditya_it_mismatches)} ETFs misclassified as Nifty IT TRI due to substring collision")

    # 4. Sector Scoring Corpus Distribution Check
    try:
        root_dir = Path(__file__).resolve().parents[4]
        if str(root_dir) not in sys.path:
            sys.path.insert(0, str(root_dir))
        from core.analysis.sector_scoring import detect_sector

        cur.execute("SELECT ticker, short_name FROM reports")
        sec_counts: Counter[str] = Counter()
        for sym, sname in cur.fetchall():
            sec_counts[detect_sector(sym, "", sname or "")] += 1
        top_sec, top_cnt = sec_counts.most_common(1)[0] if sec_counts else ("NONE", 0)
        share_pct = (top_cnt / len(rep_rows) * 100.0) if rep_rows else 0.0
        print(f"[4/4] Equity Sector Classifier Distribution: top={top_sec} ({top_cnt}/{len(rep_rows)} = {share_pct:.1f}%)")
        if share_pct > 40.0:
            issues.append(f"Skewed sector classifier: {top_sec} captures {share_pct:.1f}% of corpus (>40% ceiling)")
    except Exception as sec_err:
        print(f"[4/4] Sector distribution check notice: {sec_err}", file=sys.stderr)

    conn.close()

    if issues:
        print("\n[SUMMARY] Substance & Consequence Probe surfaced findings:")
        for item in issues:
            print(f"  - {item}")
        return 1 if strict else 0

    print("\n[SUMMARY] All corpus substance, parity, and taxonomy checks passed.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Corpus Substance & Consequence Sandbox Probe")
    parser.add_argument("--db", default="reports.db", help="Path to SQLite database (sandbox clone or reports.db)")
    parser.add_argument("--strict", action="store_true", help="Exit with code 1 when substance issues are present")
    args = parser.parse_args()
    sys.exit(run_probe(Path(args.db), strict=args.strict))


if __name__ == "__main__":
    main()

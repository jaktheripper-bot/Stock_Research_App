# Permutation Archetypes (pick dynamically via SQL; tickers are illustrative only)

## Equities
| Archetype | Typical selector | Why it breaks things |
|---|---|---|
| Hyper-growth / extreme P/E | `pe_ratio > 120` | DCF/EPV sandboxes vanish; implied growth explodes |
| Deep value / very low P/E | `pe_ratio < 4` | Cyclical-peak earnings; valuation looks "cheap" falsely |
| Loss-making | `eps <= 0` | P/E-based models undefined; needs EV/Sales route |
| Negative net worth | `book_value <= 0` | D/E and ROE invert; "stability" claims become false |
| Banks / NBFCs / Insurers (BFSI) | sector match (word-boundary regex) | Deposits ≠ debt; OPM NULL; EV/EBIT invalid; Dechow false positives |
| Cash-rich IT with liquid-fund treasury | high current investments, low debt | Ind AS puts treasury in Investments, not Cash → soft-asset inflation |
| Pending balance sheet | `debt_to_equity IS NULL` or CFO missing | Bull/solvency claims must be suppressed |
| Recent split / bonus | corporate action within window | Unadjusted candles fake -50%/-80% crashes; beta/alpha garbage |
| Short history / fresh listing | < 3 FY periods | Multi-period scores (Beneish, ROIIC) need t and t-1 |
| Q1/Q3 vs H1/FY filing | period month Jun/Dec vs Sep/Mar | LODR Reg 33: Q1/Q3 have P&L only |
| Gross-loss swing | GM_t ≤ 0 < GM_{t-1} | Ratio sign flips reward deterioration |

## Other asset classes
- **Mutual funds:** portfolio-backed vs NAV-only; index / FoF / debt / hybrid; overlapping holdings; stale AMFI date.
- **Debt (NCD/bonds/SDI):** unrated or downgraded, near maturity, illiquid EOD prints.
- **Sovereign:** inverted vs normal curve, missing tenor, stale macro rates.
- **REIT/InvIT/SGB/alt-yield:** past 90-day TTL, distribution mix changes.
- **ETF:** thin liquidity, large NAV premium/discount, high tracking error.
- **MSME:** sparse or self-reported data, past 30-day TTL.

## User & system states
- Guest vs logged-in vs pro vs admin; zero credits; locked vs unlocked dossier.
- `GEMINI_API_KEY=""`, empty quote dict, upstream 429/503, cache past TTL.
- SQLite local vs Supabase Postgres; scheduler disabled (`ENABLE_BACKGROUND_SCHEDULERS` unset).
- Light / dark / ivory themes; mobile viewport.

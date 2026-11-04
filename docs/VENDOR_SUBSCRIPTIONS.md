# External Vendor Subscriptions, Itemized Services & Optimization Ledger

**Document Identifier:** [VENDOR_SUBSCRIPTIONS.md](file:///Users/lyndonpinto/Documents/Stock_Research_App/docs/VENDOR_SUBSCRIPTIONS.md)  
**Target Production Domain:** https://moatnomics.com  
**Live Runtime Quota Monitor:** `/admin?tab=ai-spends` (powered by [`get_all_provider_constraints`](file:///Users/lyndonpinto/Documents/Stock_Research_App/core/analytics/provider_quotas.py#L105-L343))  
**Last Updated:** 2026-11-04 IST  

---

## 1. Master Subscription & Renewal Schedule

> [!IMPORTANT]
> **Due-Date Pattern Tracking:** Subscriptions marked **`UNCONFIRMED`** still need one invoice/receipt verified so their exact billing cycle, charge day, payment card, and itemized line-items are locked in. Once all active paid vendors reach `CONFIRMED`, the daily reminder automation can switch to a pre-renewal alert cadence.

| Vendor & Account | Pattern Status | Billing Period & Charge Pattern | Last Paid & Amount | Next Expected Charge | Payment Method | Itemized Billable Line-Items & Project Workloads Covered | Billing Portal |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Render**<br>*(Team: `Moatnomics`)* | `CONFIRMED` | **Calendar-Month Arrears** (`1st–end of month`), auto-charged on **`3rd` (US) / `3rd–4th` (IST)** of the following month | **`2026-11-03`** (`\$25.93` for `Oct 1–31, 2026`, Inv `BWIGQNGT-0001`) | **`2026-12-03` / `2026-12-04` IST**<br>*(Covers `Nov 1–30, 2026`; est. `~\$44–\$50/mo` unless Workspace is downgraded to Hobby `\$0`)* | `Visa •••• 3275` | **Billed Line-Items:**<br>1. `Workspace Subscription` (`Qty 1`: `\$14.57` Oct prorated; `\$19–\$25/mo` full rate)<br>2. `Servers - 1 instance` (`699h 11m` Oct: `\$11.36`; now `Standard 2 GB RAM / 1 vCPU` @ `\$25.00/mo`)<br>**Project Workloads:**<br>• `stock-research-app` FastAPI/Uvicorn web server<br>• Failover background schedulers (`ENABLE_BACKGROUND_SCHEDULERS=1`)<br>• Git-push CI build (`verify_reality_audit.py` + `pytest`) & `moatnomics.com` TLS | https://dashboard.render.com/billing |
| **AWS**<br>*(Region: `ap-southeast-2` Sydney)* | `UNCONFIRMED` | **Calendar-Month Arrears** (`1st–end of month`), typically charged **`2nd–5th`** of the following month *(provisioned `2026-10-10`)* | *Drop Oct receipt or check portal (likely billed `Nov 2–5`)* | *Verify Oct charge first → then `~2026-12-03`* | *TBD* | **Expected Billed Line-Items:**<br>1. `Amazon Lightsail` Linux IPv4 bundle (`\$5.00/mo` full-month rate)<br>2. Dedicated Static IPv4 (`13.54.76.134`, `\$0` while attached to running instance; `\$3.65/mo` if detached!)<br>**Project Workloads:**<br>• HTTP forward proxy (`:8888`) providing SEBI-compliant static IP egress (`SMARTAPI_PROXY_URL`) for Angel One SmartAPI | https://console.aws.amazon.com/billing/home |
| **Google Cloud Platform** | `UNCONFIRMED` | **Calendar-Month Postpay** (`1st–end of month`), typically charged **`1st–3rd`** of the following month *(Vertex live `2026-10-28`)* | *Drop Oct receipt or check portal (likely billed `Nov 1–3`)* | *Verify Oct charge first → then `~2026-12-02`* | *TBD* | **Expected Billed Line-Items:**<br>1. `Vertex AI` (`gemini-3.8-flash` & `gemini-3.5-flash-lite` tokens + Google Search Grounding)<br>2. `Generative Language API` (AI Studio Batch/Flex 50%-discount fallback, if invoked)<br>3. `Google Identity / OAuth 2.0` (`\$0` — `/auth/google` sign-in)<br>**Project Workloads:**<br>• Daily 15-stock cohort synthesis, MF look-through audits, on-demand `/api/generate`, & Research Desk Copilot (soft cap `GEMINI_MONTHLY_BUDGET_USD=20.0`) | https://console.cloud.google.com/billing |
| **Supabase**<br>*(Project: `omswdxrtzrvlszkidssh`)* | `UNCONFIRMED` | **Monthly** *(Confirm org billing anchor day & Free `\$0` vs. Pro `\$25/mo` tier; repo init `2026-09-01`)* | *Pending check* | *Verify in portal* | *TBD* | **Subscribed Services under Project:**<br>1. Managed PostgreSQL (`18` production tables, `ap-southeast-1` Singapore; current corpus size `~83 MB`)<br>2. Supavisor Connection Pooler (`:5432` session mode)<br>3. PostgREST HTTPS API (cloud-to-local audit sync & RLS `system_settings`)<br>4. GoTrue Auth (Email Magic Link / 6-digit OTP + Google OAuth PKCE callback) | https://supabase.com/dashboard/org/_/billing |
| **Perplexity API** | `UNCONFIRMED` | **Prepaid Credit Balance** *(Check whether Auto-Top-Up is on or manual)* | *Pending check* | *Balance-triggered (`< \$5`)* | *TBD* | **Subscribed Services under Account:**<br>1. Perplexity Sonar / Agent API (`/v1/responses`) — standby grounded-search failover circuit (zero daily burn while Vertex AI succeeds) | https://www.perplexity.ai/settings/api |
| **Cloudflare Registrar** | `CONFIRMED` | **Annual on `Oct 13`** *(Auto-renew triggers 30 days prior on `Sep 13`)* | **`2026-10-13`** | **`2027-10-13`** *(Auto-renew `2027-09-13`)* | *On file in Cloudflare* | **Billed Line-Items:**<br>1. `.com` Domain Registration (`moatnomics.com`, wholesale at-cost annual renewal ~`\$10.44/yr`) | https://dash.cloudflare.com/?to=/:account/domains |

---

## 2. Active Zero-Cost, Free-Tier & Per-Transaction Accounts (`₹0` / `\$0` Recurring)

These accounts run active production services ([render.yaml](file:///Users/lyndonpinto/Documents/Stock_Research_App/render.yaml), [scheduled_pipeline.yml](file:///Users/lyndonpinto/Documents/Stock_Research_App/.github/workflows/scheduled_pipeline.yml)) at **zero monthly subscription cost**, tracked here so you know every service under each login and when a free quota would require upgrading:

| Vendor / Account | Billing Model | Quota Ceiling to Watch | Sub-Services Running Under This Account | Portal URL |
| :--- | :--- | :--- | :--- | :--- |
| **Cloudflare Edge** | **Free Website Plan** (`\$0/mo`) | Standard CDN/WAF & Cache Rules | • Authoritative DNS (`magnolia.ns.cloudflare.com`, `troy.ns.cloudflare.com`)<br>• Reverse proxy, CDN edge caching & DDoS/bot WAF<br>• Email tracking CNAME (`links.moatnomics.com` → Resend) | https://dash.cloudflare.com |
| **Razorpay** | **Per-Transaction TDR (`2.0%`)** (`₹0/mo` fixed) | `25 req/s` API limit; ~`3.0–3.5%` FX fee on international cards | • Live Checkout orders (`/api/create-order`, `/api/verify-payment`)<br>• Live payment webhooks (`/api/razorpay-webhook`)<br>• Multi-currency pricing, Pro pass & credit fulfillment, and `process_refund()` | https://dashboard.razorpay.com |
| **Angel One** | **Free Broker API** (`₹0/mo`) | `10 req/s` quotes, `3 req/s` EOD candles; keep demat MPIN/TOTP active | • Primary BSE/NSE live quotes & 5-level L2 order depth<br>• 1-year `ONE_DAY` historical EOD candles (`get_eod_summary` for 52W range, 50-DMA, 200-DMA)<br>• Dynamic NSE/BSE scrip token resolver (`search_scrip_token`) | https://smartapi.angelbroking.com |
| **Resend** | **Free Tier** (`\$0/mo`) | **`100 emails/day`** (`3,000/mo`) — Pro is `\$20/mo` if exceeded | • 7-Asset Day-End Market Wrap subscriber newsletter<br>• Two-way customer support ticket replies (`/admin?tab=tickets`)<br>• Custom SMTP fallback (primary OTPs route via Supabase GoTrue first) | https://resend.com/settings/billing |
| **Better Stack** | **Free / Starter Tier** (`\$0/mo`) | Monthly log retention & ingestion cap (`is_test_environment()` blocks test logs) | • Logtail centralized container & pipeline IST logs (`s2808842.us-west-2a.betterstackdata.com`)<br>• Production `/health` HTTP uptime monitor (`uptime.betterstack.com`)<br>• Scheduled pipeline cron heartbeat & incident alerts (`BETTER_STACK_HEARTBEAT_URL`) | https://telemetry.betterstack.com |
| **GitHub** | **Free / Included Actions** (`\$0/mo`) | Monthly Actions runner minutes (`timeout-minutes: 45` per cron run) | • Git repository hosting (`main` & `dev` branches)<br>• GitHub Actions scheduled pipeline (`19:30`, `23:15`, and `08:00` IST crons)<br>• Encrypted Actions Secrets store (`15` cloud secrets) | https://github.com/settings/billing |

---

## 3. Cost vs. Performance Optimization Playbook

Ranked by **net monthly savings vs. latency/reliability impact** across the current Moatnomics stack:

| Priority | Target Service | Current State | Recommended Optimization | Cost Impact | Performance / Risk Tradeoff |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **P1 (Immediate Savings)** | **Render Workspace Plan** | **Pro / Paid Workspace** (`\$14.57` prorated in Oct → `\$19–\$25/mo` full month) + **Standard 2 GB Server** (`\$25/mo`) = **`~\$44–\$50/mo`** | **Downgrade Workspace to `Hobby (\$0/mo)` while keeping the `Standard 2 GB` instance (`\$25/mo`).** Render Hobby supports 1 user + paid always-on `Standard` compute (`2 GB` RAM / `1` vCPU) + custom TLS domains. | **Saves `\$19–\$25/mo` (`\$228–\$300/yr`)** — cuts upcoming Dec Render bill by ~45–50%. | **Zero CPU/RAM loss.** Only loses multi-seat access, autoscaling (`>1` instance), and Render native HTTP log retention (already covered by Better Stack Logtail). Can re-upgrade in 15s during a traffic surge per [BREAK_GLASS_IN_CASE_OF_EMERGENCY.md](file:///Users/lyndonpinto/Documents/Stock_Research_App/docs/BREAK_GLASS_IN_CASE_OF_EMERGENCY.md). |
| **P2 (Free Speed + Egress Shield)** | **Cloudflare Edge Cache** | Free plan active; anonymous HTML hits origin unless Cache Rule is enabled | **Keep a permanent `30s–60s` Anonymous SSR Cache Rule active** (cookie-free `GET` requests excluding `/api/`, `/auth/`, `/admin`, `/contact`). | **`\$0/mo`** (Protects Render Hobby `5–100 GB` bandwidth cap & prevents overages). | **~5–8× faster page loads in India** (`< 50ms` from Cloudflare Mumbai/Chennai POPs vs. `~400ms` origin RTT) + cuts Render CPU & Supabase read load by ~80%. Logged-in users remain 100% live via `user_session_token` bypass. |
| **P3 (3× Faster Quotes at Same Cost)** | **AWS Lightsail Static IP Proxy** | `13.54.76.134:8888` is in **AWS `ap-southeast-2` (Sydney)** (`\$5/mo`), hairpinning traffic to Mumbai NSE/BSE | **Re-create the `\$5/mo` Lightsail proxy in `ap-south-1` (Mumbai)**, whitelist the new static IP in Angel One SmartAPI, update `SMARTAPI_PROXY_URL`, then delete the Sydney instance **and** release its static IP. | **`\$0` change** (Still `\$5/mo`; avoids accidental `\$3.65/mo` unattached-IP fee). *(Optional: Oracle Cloud Always Free Mumbai VM = `\$0/mo`, saves `\$5/mo`, slightly higher ops setup.)* | **~3× lower quote/candle latency** (`< 10ms` Mumbai-to-Angel-One vs. `~150ms+` Sydney hairpin). |
| **P4 (Build Minute Protection)** | **Render Build Pipeline** | [render.yaml](file:///Users/lyndonpinto/Documents/Stock_Research_App/render.yaml#L5) runs full `pytest -q` (`960+` tests, ~3 min) on every `git push` | **Use `[skip render]` on docs-only commits** and consider offloading full `pytest` to GitHub Actions (`2,000` free min/mo) while keeping fast `verify_reality_audit.py` (`~12s`) on Render builds. | **Avoids `\$` build-minute overages** if Render Workspace moves to Hobby (`500` build min/mo cap). | **~4× faster production deploys** (`~45s` vs. `~3.5 min`) while maintaining full CI test gating in GitHub. |
| **P5 (Check If Over-Provisioned)** | **Supabase Tier** | Total corpus (`18` tables, `392` equities, `2,059` MF schemes) is only **`~83 MB`** (`reports.db`) | **Verify whether org is on Free (`\$0/mo`, `500 MB` limit) or Pro (`\$25/mo`, `8 GB` limit).** 3× daily GitHub crons prevent Free-tier 7-day inactivity pausing, and `./run.sh sync-down` + `backup` already maintain full local backups. | **Saves `\$25/mo` (`\$300/yr`)** if currently paying for Pro before crossing `~350–400 MB` or high concurrent load. | **Tradeoff:** Free tier caps direct connections at `60` (`200` via Supavisor Pooler, which is already active on `:5432`) and omits cloud PITR backups (mitigated by local `sync-down` backups). Upgrade to Pro once traffic or DB size warrants it. |
| **P6 (LLM Grounding Guardrail)** | **Google Cloud Vertex AI** | `gemini-3.8-flash` token spend is pennies, **but** Vertex **Google Search Grounding** bills `~\$35 / 1,000` grounded prompts once outside free credits | **Keep Search Grounding strictly limited to 14-day/material Equity Dossier syntheses**; ensure MF look-through narratives, surgical valuation refreshes, and Research Desk Copilot rely on DB-grounded context without Search Grounding tools attached. | **Caps monthly AI spend well inside `\$5–\$20/mo`** instead of `\$15–\$30/day` grounding creep. | **Zero quality loss:** MF holdings, BSE headers, and DCF/DuPont math are already deterministically pre-computed before LLM synthesis. |

---

## 4. Verified Receipt & Payment History Log

| Date Paid | Vendor | Invoice / Receipt # | Billing Period Covered | Itemized Breakdown | Total Paid | Payment Method |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `2026-10-13` | **Cloudflare Registrar** | *Initial Registration* | `2026-10-13` → `2027-10-13` | • `moatnomics.com` (`.com` 1-year registration) | *At-cost annual* | *Cloudflare card on file* |
| `2026-11-03` | **Render** (`Moatnomics`) | Inv `BWIGQNGT-0001` / Rcpt `2479-3933` | `2026-10-01` → `2026-10-31` | • `Workspace Subscription` (Qty 1): `\$14.57`<br>• `Servers - 699h 11m 11s - 1 instance`: `\$11.36` | **`\$25.93`** | `Visa •••• 3275` |

---

## 5. Decommissioned / Inactive Vendors (Confirmed Not Active — Do Not Pay)

Per [source_evaluation.md](file:///Users/lyndonpinto/Documents/Stock_Research_App/source_evaluation.md#L147-L152):
* **EODHD (`\$49.99–\$79.99/mo`):** Decommissioned and purged from the codebase. Cancel immediately if seen on any card statement.
* **FMP, Twelve Data, Zerodha Kite Connect, NSE DotEx, Accord Fintech:** Evaluated only; never activated.

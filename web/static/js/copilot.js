/**
 * Research Desk Frontend Controller (v2.0).
 * Supports Multi-Asset Dispatch across Fundamental Equities, Mutual Funds, and Corporate Debt,
 * with Deep Section Contextual Awareness, Smooth Slide-In Transitions, and SEBI Safe Harbor Guardrails.
 */

let activeConversationId = null;
let activeTicker = "";
let activeAssetType = "equity";
let activeSection = null;
let activeSectionLabel = "";

/**
 * Brand-approved icon renderer: draws a monochrome sprite symbol defined in base.html
 * (Visual Identity v2.0, Section 7) instead of a raw OS emoji. Unknown ids fall back to the Insights icon.
 */
function brandGlyph(iconId) {
    const id = /^icon-[a-z0-9-]+$/.test(iconId || "") ? iconId : "icon-insights";
    return `<svg class="glyph" aria-hidden="true" focusable="false" style="width:1em;height:1em;vertical-align:-0.125em;"><use href="#${id}"></use></svg>`;
}

const COPILOT_CONFIGS = {
    equity: {
        headerTitle: "Research Desk",
        assetBadge: "Fundamental Equity Intelligence",
        introText: (ticker) => `Welcome to the <strong>Research Desk</strong>. I can assist in stress-testing your investment thesis on <strong>${ticker || 'the selected equity'}</strong>, deriving implied growth rates via Reverse DCF, or running a <strong>countercase analysis</strong>.`,
        features: [
            { icon: "icon-compare", title: "Countercase", desc: "Find failure modes and thesis risks", prompt: "Run a countercase analysis on this stock: what failure modes could destroy shareholder value?" },
            { icon: "icon-valuation", title: "Reverse DCF Growth", desc: "See the growth implied by the current price", prompt: "What implied growth rate is priced into current CMP based on Reverse DCF?" },
            { icon: "icon-doc", title: "Governance Check", desc: "Audit promoter pledging & related-party transactions", prompt: "Are there any promoter pledging or corporate governance red flags in recent disclosures?" }
        ],
        chips: [
            { icon: "icon-compare", label: "Countercase", prompt: "Run a countercase analysis on this stock: what failure modes could destroy shareholder value?" },
            { icon: "icon-valuation", label: "Reverse DCF Implied Growth", prompt: "What implied growth rate is priced into current CMP based on Reverse DCF?" },
            { icon: "icon-doc", label: "Governance & Pledging Check", prompt: "Are there any promoter pledging or corporate governance red flags in recent disclosures?" },
            { icon: "icon-risk", label: "Balance Sheet Solvency", prompt: "Evaluate balance sheet solvency and leverage ratios for this company." }
        ]
    },
    mutual_fund: {
        headerTitle: "Fund Look-Through Intelligence Desk",
        assetBadge: "Mutual Fund Intelligence",
        introText: (ticker) => `Welcome to the <strong>Fund Look-Through Intelligence Desk</strong>. I evaluate underlying constituent quality, weighted moat endurance, look-through ASRI accounting stress, active share vs benchmark, and <strong>direct vs regular intermediary fee drag</strong> for <strong>${ticker || 'this scheme'}</strong>.`,
        features: [
            { icon: "icon-pillar-01", title: "Weighted Moat Index", desc: "Constituent economic moat distribution & quality", prompt: "Evaluate the constituent moat distribution and overall portfolio quality for this fund." },
            { icon: "icon-valuation", title: "Intermediary Fee Drag", desc: "20-yr compounded cost of distributor commissions", prompt: "What is the 20-year compounded fee drag and cost of distributor commissions for this fund?" },
            { icon: "icon-portfolio", title: "Active Share & Style Drift", desc: "Audit closet indexing and benchmark hugging", prompt: "Audit the active share and check if this fund is exhibiting benchmark hugging or style drift." }
        ],
        chips: [
            { icon: "icon-risk", label: "Moat & Quality Score", prompt: "Evaluate the constituent moat distribution and overall portfolio quality for this fund." },
            { icon: "icon-alerts", label: "High-Risk Holdings", prompt: "Which underlying constituent holdings carry the highest accounting risk or lowest health score?" },
            { icon: "icon-portfolio", label: "Style Drift & Active Share", prompt: "Audit the active share and check if this fund is exhibiting benchmark hugging or style drift." },
            { icon: "icon-valuation", label: "Intermediary Fee Drag", prompt: "What is the 20-year compounded fee drag and cost of distributor commissions for this fund?" }
        ]
    },
    debt: {
        headerTitle: "Credit & Solvency Intelligence Desk",
        assetBadge: "Fixed Income & SDI Solvency",
        introText: (ticker) => `Welcome to the <strong>Credit & Solvency Intelligence Desk</strong>. I can stress-test Asset Coverage Ratios (ACR), recovery seniority in liquidation, DSCR covenant headroom, and <strong>credit contagion risk</strong> for <strong>${ticker || 'this security'}</strong>.`,
        features: [
            { icon: "icon-risk", title: "Asset Coverage & Covenants", desc: "Stress-test ACR and DSCR covenant headroom", prompt: "Stress-test the Asset Coverage Ratio (ACR) and DSCR covenant headroom for this instrument." },
            { icon: "icon-valuation", title: "Recovery Seniority Tier", desc: "Evaluate recovery seniority & liquidation hierarchy", prompt: "Evaluate recovery seniority and investor recourse in a stressed debt restructuring or liquidation." },
            { icon: "icon-radar", title: "Credit Contagion Radar", desc: "Analyze parent group linkages and contagion risk", prompt: "What does the Credit Contagion Radar say about the parent group and systemic risks for this issuer?" }
        ],
        chips: [
            { icon: "icon-risk", label: "Asset Coverage & Covenants", prompt: "Stress-test the Asset Coverage Ratio (ACR) and DSCR covenant headroom for this instrument." },
            { icon: "icon-valuation", label: "Recovery Seniority Tier", prompt: "Evaluate recovery seniority and investor recourse in a stressed debt restructuring or liquidation." },
            { icon: "icon-radar", label: "Credit Contagion Radar", prompt: "What does the Credit Contagion Radar say about the parent group and systemic risks for this issuer?" }
        ]
    },
    etf: {
        headerTitle: "ETF & Arbitrage Intelligence Desk",
        assetBadge: "ETF Arbitrage & Tracking Intelligence",
        introText: (ticker) => `Welcome to the <strong>ETF & Arbitrage Intelligence Desk</strong>. I evaluate secondary market pricing vs Fair NAV, 1-year tracking error fidelity, expense ratio drag, and <strong>Authorized Participant creation/redemption arbitrage</strong> for <strong>${ticker || 'this ETF'}</strong>.`,
        features: [
            { icon: "icon-valuation", title: "Arbitrage & Fair Value", desc: "Audit CMP vs statutory Fair NAV premium/discount", prompt: "Evaluate the secondary market premium/discount spread and arbitrage corridor for this ETF." },
            { icon: "icon-screen", title: "Tracking Error Fidelity", desc: "1Y annualized deviation vs benchmark index TRI", prompt: "Audit the 1-year annualized tracking error and replication fidelity for this ETF." },
            { icon: "icon-markets", title: "Liquidity Depth & Impact", desc: "Analyze daily volume, turnover, and bid-ask spread proxy", prompt: "What is the secondary market liquidity depth, average daily volume, and impact cost for this ETF?" }
        ],
        chips: [
            { icon: "icon-valuation", label: "Arbitrage & Premium Spread", prompt: "Evaluate the secondary market premium/discount spread and arbitrage corridor for this ETF." },
            { icon: "icon-screen", label: "1Y Tracking Error", prompt: "Audit the 1-year annualized tracking error and replication fidelity for this ETF." },
            { icon: "icon-valuation", label: "TER Fee Drag vs Peers", prompt: "Compare the expense ratio (TER) and 10-year fee drag of this ETF against category peers." },
            { icon: "icon-markets", label: "Liquidity Depth", prompt: "What is the secondary market liquidity depth, average daily volume, and impact cost for this ETF?" },
            { icon: "icon-compare", label: "Countercase & AP Risk", prompt: "Summarize the bear thesis and Authorized Participant withdrawal risks during high market volatility." }
        ]
    },
    reit: {
        headerTitle: "REIT & InvIT Cash Flow Desk",
        assetBadge: "REIT & InvIT Cash Flow",
        introText: (ticker) => `Welcome to the <strong>REIT & InvIT Cash Flow Desk</strong>. I evaluate Section 115UA tax waterfalls (Interest, Dividend, Return of Capital, Rental), statutory <strong>NDCF payout purity</strong> (≥90% Mainboard, ≥95% SM REIT), WALE & tenant concentration, and <strong>Countercase risk</strong> for <strong>${ticker || 'this Trust'}</strong>.`,
        features: [
            { icon: "icon-multi-asset", title: "Sec 115UA Tax Waterfall", desc: "Audit distribution components & net post-tax yield", prompt: "Evaluate the Section 115UA tax distribution waterfall and net post-tax yield across tax slabs for this REIT/InvIT." },
            { icon: "icon-markets", title: "NDCF Payout Purity", desc: "Audit statutory distribution vs SEBI 15% penal threshold", prompt: "Analyze the NDCF payout purity, cash conversion, and SEBI compliance for this trust." },
            { icon: "icon-multi-asset", title: "Portfolio Scale & WALE", desc: "Evaluate portfolio occupancy, lease expiry, and tenant risk", prompt: "Evaluate the portfolio scale, Weighted Average Lease Expiry (WALE), and top tenant concentration." }
        ],
        chips: [
            { icon: "icon-multi-asset", label: "Sec 115UA Tax Waterfall", prompt: "Evaluate the Section 115UA tax distribution waterfall and net post-tax yield across tax slabs for this REIT/InvIT." },
            { icon: "icon-markets", label: "NDCF Payout Purity", prompt: "Analyze the NDCF payout purity, cash conversion, and SEBI compliance for this trust." },
            { icon: "icon-multi-asset", label: "Portfolio WALE & Tenants", prompt: "Evaluate the portfolio scale, Weighted Average Lease Expiry (WALE), and top tenant concentration." },
            { icon: "icon-insights", label: "Leverage & LTV Headroom", prompt: "What is the leverage LTV vs SEBI 49% statutory cap and interest coverage headroom?" },
            { icon: "icon-compare", label: "Countercase & Refinancing Risk", prompt: "Summarize the bear thesis, refinancing risks, and tenant vacancy shocks under Countercase." }
        ]
    }
};

const SECTION_CHIPS = {
    reit: {
        tax_waterfall: [
            { icon: "icon-multi-asset", label: "Sec 115UA Post-Tax Yield", prompt: "Break down the post-tax yield across the 0%, 10%, 20%, 30%, and 39% tax slabs for this REIT/InvIT." },
            { icon: "icon-valuation", label: "ROC Tax Treatment", prompt: "Explain the tax treatment of Return of Capital (Amortization) and Section 56(2)(xii) specified sum threshold." },
            { icon: "icon-valuation", label: "Dividend SPV Tax Exemption", prompt: "Is the dividend component exempt or taxable in unitholder hands based on SPV Sec 115BAA status?" }
        ],
        ndcf_purity: [
            { icon: "icon-markets", label: "NDCF Distribution Purity", prompt: "Audit the NDCF payout purity against SEBI's statutory mandate (≥90% for Mainboard, ≥95% for SM REIT)." },
            { icon: "icon-alerts", label: "SEBI 15% Penal Clause", prompt: "Does this trust risk the SEBI 15% penal interest rate for delayed distributions?" },
            { icon: "icon-valuation", label: "Free Cash Flow vs NDCF", prompt: "Analyze the spread between accounting Net Distributable Cash Flow and true operating free cash flow." }
        ],
        portfolio_wale: [
            { icon: "icon-multi-asset", label: "Lease Expiry Schedule", prompt: "Analyze the lease expiry concentration and renewal risk over the next 3 years." },
            { icon: "icon-screen", label: "Top 3 Tenant Concentration", prompt: "How vulnerable is distribution cash flow if the top 3 tenants vacate or downsize?" },
            { icon: "icon-valuation", label: "Occupancy & Mark-to-Market", prompt: "Evaluate current physical occupancy and mark-to-market rental escalation headroom." }
        ],
        inversion: [
            { icon: "icon-compare", label: "Inversion Failure Modes", prompt: "What structural failure modes or macro shocks could permanently impair distributions for this REIT/InvIT?" },
            { icon: "icon-insights", label: "Interest Rate Sensitivity", prompt: "How does a 150 bps rise in benchmark bond yields impact the unit price and NAV cap rate?" }
        ]
    },
    mutual_fund: {
        fee_drag: [
            { icon: "icon-valuation", label: "20-Yr Compounded Drag", prompt: "What is the 20-year compounded fee drag and total cost difference between Direct and Regular plans for this fund?" },
            { icon: "icon-valuation", label: "TER Spread Analysis", prompt: "Analyze the distributor commission spread (bps/year) and why direct plans protect compounding." },
            { icon: "icon-valuation", label: "Key Takeaway", prompt: "What is the key takeaway regarding the expense ratio and distributor commissions?" }
        ],
        active_share: [
            { icon: "icon-portfolio", label: "Closet Indexing Check", prompt: "Is this fund exhibiting benchmark hugging or closet indexing based on its Active Share?" },
            { icon: "icon-portfolio", label: "Active Share vs Benchmark", prompt: "Evaluate the Active Share score and concentration vs benchmark index." },
            { icon: "icon-alerts", label: "Style Drift Diagnostic", prompt: "Check if this fund is drifting away from its stated mandate or category style." }
        ],
        asri_solvency: [
            { icon: "icon-alerts", label: "High-Risk Constituents", prompt: "Which underlying constituent holdings carry the highest accounting risk or lowest health score?" },
            { icon: "icon-doc", label: "Promoter Pledging Check", prompt: "Are any constituent companies flagged for elevated promoter pledging or governance risks?" },
            { icon: "icon-risk", label: "Look-Through ASRI", prompt: "Evaluate the portfolio-wide Accounting Stress & Risk Index (ASRI)." }
        ],
        moat_index: [
            { icon: "icon-pillar-01", label: "Weighted Moat Breakdown", prompt: "Break down the fund's Weighted Moat Index and proportion of Wide vs Narrow Moat businesses." },
            { icon: "icon-insights", label: "Core Compounders", prompt: "Which top holdings contribute the strongest structural economic moats?" },
            { icon: "icon-risk", label: "Pricing Power Endurance", prompt: "Evaluate the pricing power and return on capital endurance of the underlying portfolio." }
        ],
        margin_of_safety: [
            { icon: "icon-valuation", label: "Weighted MoS (DCF)", prompt: "What is the weighted Margin of Safety across the portfolio based on DCF models?" },
            { icon: "icon-valuation", label: "Intrinsic Valuation Gap", prompt: "Are the top constituent holdings trading at a discount or premium to intrinsic value?" }
        ],
        promoter_pledge: [
            { icon: "icon-doc", label: "Promoter Pledge Exposure", prompt: "What percentage of fund capital is allocated to companies with elevated promoter pledge levels?" },
            { icon: "icon-research", label: "Governance Watchlist", prompt: "Identify any holdings with related-party transactions or accounting friction." }
        ],
        holdings: [
            { icon: "icon-portfolio", label: "Dual-Sleeve Allocation", prompt: "Analyze the equity vs debt vs cash allocation and portfolio concentration." },
            { icon: "icon-screen", label: "Top 10 Concentration", prompt: "Evaluate the concentration risk of the top 10 constituent holdings." },
            { icon: "icon-multi-asset", label: "Sector & Asset Distribution", prompt: "Break down the sector allocation and asset weights across the fund." }
        ],
        downside_capture: [
            { icon: "icon-risk", label: "Bear Market Resilience", prompt: "How does this fund perform during market drawdowns based on its Downside Capture ratio?" },
            { icon: "icon-markets", label: "Capture Spread & Alpha", prompt: "Explain the spread between Upside Capture and Downside Capture ratios." },
            { icon: "icon-valuation", label: "Sortino & Momentum", prompt: "Interpret the Sortino ratio and Hurst exponent momentum metric for this fund." }
        ],
        dossier_narrative: [
            { icon: "icon-doc", label: "Summarize AI Audit", prompt: "Summarize the key findings, strengths, and vulnerabilities from the accounting check narrative." },
            { icon: "icon-alerts", label: "Critical Red Flags", prompt: "Highlight any governance concerns or governance warnings identified in the qualitative audit." }
        ],
        lookthrough_metrics: [
            { icon: "icon-research", label: "7-Pillar Overview", prompt: "Provide an overview of the fund's 7-pillar look-through metrics." },
            { icon: "icon-risk", label: "Moat vs Solvency Spread", prompt: "Compare the fund's Weighted Moat Index against its Look-Through ASRI accounting risk." }
        ]
    },
    equity: {
        reverse_dcf: [
            { icon: "icon-valuation", label: "Implied Growth Priced In", prompt: "What implied growth rate is priced into current CMP based on Reverse DCF?" },
            { icon: "icon-screen", label: "Hurdle Rate Sensitivity", prompt: "How sensitive is the Reverse DCF valuation to hurdle rate assumptions?" }
        ],
        solvency: [
            { icon: "icon-risk", label: "Balance Sheet Solvency", prompt: "Evaluate balance sheet solvency and leverage ratios." },
            { icon: "icon-doc", label: "Accrual & Earnings Check", prompt: "Are there any forensic accounting or earnings manipulation red flags?" }
        ],
        countercase: [
            { icon: "icon-compare", label: "Thesis Failure Modes", prompt: "Run a countercase analysis on this stock: what failure modes could destroy shareholder value?" },
            { icon: "icon-alerts", label: "Structural Vulnerabilities", prompt: "Identify the top 3 structural risks that could permanently impair business earnings." }
        ]
    },
    debt: {
        covenants: [
            { icon: "icon-risk", label: "Asset Coverage (ACR)", prompt: "Stress-test the Asset Coverage Ratio (ACR) and DSCR covenant headroom for this instrument." },
            { icon: "icon-valuation", label: "Recovery Seniority Tier", prompt: "Evaluate recovery seniority and investor recourse in a stressed debt restructuring or liquidation." }
        ],
        contagion: [
            { icon: "icon-radar", label: "Credit Contagion Radar", prompt: "What does the Credit Contagion Radar say about the parent group and systemic risks for this issuer?" },
            { icon: "icon-alerts", label: "Cross-Default Risks", prompt: "Are there any cross-default triggers or related-party exposure in the group structure?" }
        ]
    },
    etf: {
        arbitrage: [
            { icon: "icon-valuation", label: "Fair NAV Spread", prompt: "What is the current premium or discount percentage over Fair NAV and is retail paying an impact surcharge?" },
            { icon: "icon-multi-asset", label: "AP Creation Incentives", prompt: "How do Authorized Participants arbitrage this spread via creation/redemption baskets?" },
            { icon: "icon-screen", label: "Retail Limit Order Strategy", prompt: "What execution strategy should retail investors use to minimize slippage on this ETF?" }
        ],
        tracking_error: [
            { icon: "icon-screen", label: "1Y Tracking Error", prompt: "How does the 1-year tracking error compare to the benchmark standard?" },
            { icon: "icon-valuation", label: "Drag Sources", prompt: "What portion of tracking error comes from TER, cash drag, and dividend reinvestment latency?" }
        ],
        peers: [
            { icon: "icon-portfolio", label: "Compare with Peers", prompt: "Compare this ETF against its category peers on TER, tracking error, and liquidity depth." },
            { icon: "icon-insights", label: "Cheapest in Category", prompt: "Is this ETF the most cost-efficient vehicle in its category?" }
        ],
    }
};

const SECTION_METADATA = {
    reit: {
        tax_waterfall: {
            headerTitle: "Sec 115UA Tax Waterfall Desk",
            introHeadline: "Sec 115UA Tax Waterfall Workspace",
            introText: (ticker) => `Auditing composite cash distribution streams for <strong>${ticker || 'this Trust'}</strong> across Section 115UA components (Interest, Dividend, Return of Capital, and Rental). Post-tax yield simulations calculate exact in-hand realizations across marginal personal tax slabs (0% to 39%).`,
            features: [
                { icon: "icon-multi-asset", title: "5-Slab Post-Tax Yield Simulation", desc: "Comparative yield table across 0%, 10%, 20%, 30%, and 39% tax slabs with tax drag (bps)", prompt: "Break down the post-tax yield across the 0%, 10%, 20%, 30%, and 39% tax slabs for this REIT/InvIT." },
                { icon: "icon-valuation", title: "Return of Capital & Sec 56(2)(xii)", desc: "Tax-free amortization rules, acquisition cost reduction & specified sum threshold", prompt: "Explain the tax treatment of Return of Capital (Amortization) and Section 56(2)(xii) specified sum threshold." },
                { icon: "icon-valuation", title: "SPV Dividend Pass-Through Status", desc: "Section 10(23FD) tax-free dividend status vs Section 115BAA corporate tax regime", prompt: "Is the dividend component exempt or taxable in unitholder hands based on SPV Sec 115BAA status?" }
            ]
        },
        ndcf_purity: {
            headerTitle: "NDCF Payout Purity & Capital Discipline Desk",
            introHeadline: "NDCF Payout Purity Workspace",
            introText: (ticker) => `Auditing statutory upstreaming discipline and cash conversion for <strong>${ticker || 'this Trust'}</strong> against SEBI mandates (≥90% Mainboard, ≥95% SM REIT). Cross-checking free operating cash flow vs accounting NDCF and verifying the <strong>SEBI 15% p.a. penal interest clause</strong> for delayed distributions.`,
            features: [
                { icon: "icon-markets", title: "Statutory NDCF Payout Purity", desc: "Audit distribution purity against SEBI mandate (≥90% Mainboard, ≥95% SM REIT)", prompt: "Audit the NDCF payout purity against SEBI's statutory mandate (≥90% for Mainboard, ≥95% for SM REIT)." },
                { icon: "icon-alerts", title: "SEBI 15% Penal Clause Audit", desc: "Manager personal liability & statutory compliance track record", prompt: "Does this trust risk the SEBI 15% penal interest rate for delayed distributions?" },
                { icon: "icon-valuation", title: "Operating FCF vs Accounting NDCF", desc: "Audit capex reserves, debt servicing deductions & cash conversion", prompt: "Analyze the spread between accounting Net Distributable Cash Flow and true operating free cash flow." }
            ]
        },
        portfolio_wale: {
            headerTitle: "Portfolio WALE & Tenant Concentration Desk",
            introHeadline: "Portfolio Scale, WALE & Solvency Workspace",
            introText: (ticker) => `Auditing physical occupancy, Weighted Average Lease Expiry (WALE), and anchor counterparty concentration for <strong>${ticker || 'this Trust'}</strong>. Evaluating debt maturity profiles, cost of debt, and statutory borrowing headroom under the SEBI 49% LTV ceiling.`,
            features: [
                { icon: "icon-multi-asset", title: "Lease Expiry & Renewals Pipeline", desc: "Next 3-year expiry concentration, WALE & contractual rental escalations", prompt: "Analyze the lease expiry concentration and renewal risk over the next 3 years." },
                { icon: "icon-screen", title: "Top Tenant Counterparty Concentration", desc: "Fortune 500 / GCC exposure, fit-out switching costs & vacancy resilience", prompt: "How vulnerable is distribution cash flow if the top 3 tenants vacate or downsize?" },
                { icon: "icon-insights", title: "LTV Borrowing Headroom & Debt Mix", desc: "Net LTV vs SEBI 49% cap, cost of debt & fixed vs floating maturity mix", prompt: "What is the leverage LTV vs SEBI 49% statutory cap and interest coverage headroom?" }
            ]
        },
        inversion: {
            headerTitle: "Countercase & Stress Desk",
            introHeadline: "Countercase & Risk Ledger",
            introText: (ticker) => `Conducting adversarial Countercase on <strong>${ticker || 'this Trust'}</strong>. Stress-testing distribution resilience against +150 bps interest rate hikes, tenant vacancy bunching, cap rate expansion NAV shocks, and sponsor pipeline conflicts.`,
            features: [
                { icon: "icon-compare", title: "Structural Failure Modes Ledger", desc: "Countercase analysis of macro, operational, and regulatory disruption vectors", prompt: "What structural failure modes or macro shocks could permanently impair distributions for this REIT/InvIT?" },
                { icon: "icon-insights", title: "+150 bps Interest Rate Shock", desc: "Stress-testing floating debt servicing, cap-rate expansion & NAV sensitivity", prompt: "How does a 150 bps rise in benchmark bond yields impact the unit price and NAV cap rate?" },
                { icon: "icon-compare", title: "Sponsor ROFO Pipeline Governance", desc: "Skin-in-the-game percentage, RPT unitholder voting & independent valuations", prompt: "Audit the sponsor governance, skin-in-the-game, and ROFO asset acquisition pipeline." }
            ]
        }
    },
    mutual_fund: {
        fee_drag: {
            headerTitle: "Intermediary Fee Drag Desk",
            introHeadline: "Intermediary Fee Drag Workspace",
            introText: (ticker) => `Auditing the 20-year compounded fee drag and distributor commission spread between Direct and Regular plans for <strong>${ticker || 'this Fund'}</strong>.`,
            features: [
                { icon: "icon-valuation", title: "20-Yr Compounded Fee Drag", desc: "Calculate the cumulative cost of distributor commissions over 20 years", prompt: "What is the 20-year compounded fee drag and total cost difference between Direct and Regular plans for this fund?" },
                { icon: "icon-valuation", title: "Distributor Commission Spread", desc: "Analyze the bps/year expense ratio difference between Direct and Regular plans", prompt: "Analyze the distributor commission spread (bps/year) and why direct plans protect compounding." },
                { icon: "icon-valuation", title: "Long-Term Compounding Takeaway", desc: "Long-term compounding preservation via commission-free investing", prompt: "What is the key takeaway regarding the expense ratio and distributor commissions?" }
            ]
        },
        active_share: {
            headerTitle: "Active Share & Closet Indexing Desk",
            introHeadline: "Active Share & Style Drift Workspace",
            introText: (ticker) => `Auditing portfolio non-overlap against the benchmark index to expose closet indexing and style drift for <strong>${ticker || 'this Fund'}</strong>.`,
            features: [
                { icon: "icon-portfolio", title: "Closet Indexing Check", desc: "Audit whether active fees are charged for benchmark hugging", prompt: "Is this fund exhibiting benchmark hugging or closet indexing based on its Active Share?" },
                { icon: "icon-portfolio", title: "Active Share vs Benchmark", desc: "Quantitative non-overlap percentage against benchmark index", prompt: "Evaluate the Active Share score and concentration vs benchmark index." },
                { icon: "icon-alerts", title: "Style Drift Diagnostic", desc: "Check for market-cap drift or divergence from stated mandate", prompt: "Check if this fund is drifting away from its stated mandate or category style." }
            ]
        },
        asri_solvency: {
            headerTitle: "Accounting Risk (ASRI) Desk",
            introHeadline: "Look-Through Accounting Stress Workspace",
            introText: (ticker) => `Evaluating capital-weighted accounting stress, aggressive revenue recognition, and promoter pledging across underlying holdings of <strong>${ticker || 'this Fund'}</strong>.`,
            features: [
                { icon: "icon-alerts", title: "High-Risk Constituents Watchlist", desc: "Constituent holdings carrying elevated accounting or leverage stress", prompt: "Which underlying constituent holdings carry the highest accounting risk or lowest health score?" },
                { icon: "icon-doc", title: "Promoter Pledging Exposure", desc: "Audit promoter pledge encumbrances across constituent portfolio companies", prompt: "Are any constituent companies flagged for elevated promoter pledging or governance risks?" },
                { icon: "icon-risk", title: "Portfolio-Wide ASRI Metric", desc: "Aggregated Accounting Stress & Risk Index across all underlying holdings", prompt: "Evaluate the portfolio-wide Accounting Stress & Risk Index (ASRI)." }
            ]
        },
        moat_index: {
            headerTitle: "Weighted Moat & Quality Endurance Desk",
            introHeadline: "Weighted Moat Quality Workspace",
            introText: (ticker) => `Auditing structural competitive advantages, pricing power, and return on capital persistence across constituent holdings for <strong>${ticker || 'this Fund'}</strong>.`,
            features: [
                { icon: "icon-pillar-01", title: "Weighted Moat Breakdown", desc: "Proportion of Wide vs Narrow Moat businesses in the portfolio", prompt: "Break down the fund's Weighted Moat Index and proportion of Wide vs Narrow Moat businesses." },
                { icon: "icon-insights", title: "Core Fortress Compounders", desc: "Top holdings contributing structural economic moats", prompt: "Which top holdings contribute the strongest structural economic moats?" },
                { icon: "icon-risk", title: "Pricing Power Endurance", desc: "Long-term pricing power and ROIC endurance of underlying holdings", prompt: "Evaluate the pricing power and return on capital endurance of the underlying portfolio." }
            ]
        },
        holdings: {
            headerTitle: "Constituent Holdings & Allocation Desk",
            introHeadline: "Dual-Sleeve Allocation Workspace",
            introText: (ticker) => `Auditing equity vs debt vs cash sleeves and top 10 portfolio concentration for <strong>${ticker || 'this Fund'}</strong>.`,
            features: [
                { icon: "icon-portfolio", title: "Dual-Sleeve Asset Mix", desc: "Asset weights and cash deployment across sleeves", prompt: "Analyze the equity vs debt vs cash allocation and portfolio concentration." },
                { icon: "icon-screen", title: "Top 10 Concentration Risk", desc: "Single-stock risk across the top 10 constituent holdings", prompt: "Evaluate the concentration risk of the top 10 constituent holdings." },
                { icon: "icon-multi-asset", title: "Sector Allocation Distribution", desc: "Sector exposure breakdown against category averages", prompt: "Break down the sector allocation and asset weights across the fund." }
            ]
        }
    },
    equity: {
        solvency: {
            headerTitle: "Balance Sheet Solvency & Health Desk",
            introHeadline: "Solvency & Health Matrix Workspace",
            introText: (ticker) => `Evaluating balance sheet solvency, leverage ratios, and financial resilience under macroeconomic stress for <strong>${ticker || 'this equity'}</strong>.`,
            features: [
                { icon: "icon-risk", title: "Balance Sheet Solvency", desc: "Audit solvency margin of safety, net debt/EBITDA, and current ratio", prompt: "Evaluate balance sheet solvency and leverage ratios for this company." },
                { icon: "icon-doc", title: "Accrual Quality Audit", desc: "Forensic accounting screening for aggressive revenue and accruals", prompt: "Are there any forensic accounting or earnings manipulation red flags?" },
                { icon: "icon-doc", title: "Promoter Pledging Check", desc: "Audit promoter pledge encumbrances and ownership stability", prompt: "Are there any promoter pledging or corporate governance red flags in recent disclosures?" }
            ]
        },
        reverse_dcf: {
            headerTitle: "Reverse DCF Implied Growth Desk",
            introHeadline: "Reverse DCF Implied Growth Workspace",
            introText: (ticker) => `Deconstructing market price to calculate what annual FCF growth is currently priced into CMP for <strong>${ticker || 'this equity'}</strong>.`,
            features: [
                { icon: "icon-valuation", title: "Implied FCF Growth Priced In", desc: "Calculate implied growth rate priced into current CMP", prompt: "What implied growth rate is priced into current CMP based on Reverse DCF?" },
                { icon: "icon-screen", title: "Hurdle Rate Sensitivity", desc: "Sensitivity analysis across 10%, 12%, and 15% discount rates", prompt: "How sensitive is the Reverse DCF valuation to hurdle rate assumptions?" }
            ]
        },
        countercase: {
            headerTitle: "Countercase & Failure Modes Desk",
            introHeadline: "Countercase Workspace",
            introText: (ticker) => `Reasoning backward from failure to expose structural failure modes and thesis risks for <strong>${ticker || 'this equity'}</strong>.`,
            features: [
                { icon: "icon-compare", title: "Key Risks & Assumptions That Could Fail", desc: "Expose top operational and regulatory risks that destroy shareholder value", prompt: "Run a countercase analysis on this stock: what failure modes could destroy shareholder value?" },
                { icon: "icon-alerts", title: "Structural Vulnerabilities", desc: "Identify top 3 structural risks that could permanently impair earnings", prompt: "Identify the top 3 structural risks that could permanently impair business earnings." }
            ]
        }
    },
    debt: {
        covenants: {
            headerTitle: "Asset Coverage & Covenants Desk",
            introHeadline: "Asset Coverage & Covenants Workspace",
            introText: (ticker) => `Stress-testing Asset Coverage Ratios (ACR), DSCR headroom, and security charge integrity for <strong>${ticker || 'this instrument'}</strong>.`,
            features: [
                { icon: "icon-risk", title: "Asset Coverage Ratio (ACR)", desc: "Stress-test security charge cover against stressed valuation", prompt: "Stress-test the Asset Coverage Ratio (ACR) and DSCR covenant headroom for this instrument." },
                { icon: "icon-valuation", title: "Recovery Seniority Hierarchy", desc: "Evaluate IBC liquidation priority and unencumbered asset pool", prompt: "Evaluate recovery seniority and investor recourse in a stressed debt restructuring or liquidation." }
            ]
        },
        contagion: {
            headerTitle: "Credit Contagion & Group Solvency Desk",
            introHeadline: "Credit Contagion Radar Workspace",
            introText: (ticker) => `Monitoring parent-group leverage, cross-default triggers, and systemic equity contagion for <strong>${ticker || 'this issuer'}</strong>.`,
            features: [
                { icon: "icon-radar", title: "Credit Contagion Radar", desc: "Analyze parent entity leverage and cross-default covenants", prompt: "What does the Credit Contagion Radar say about the parent group and systemic risks for this issuer?" },
                { icon: "icon-alerts", title: "Cross-Default Trigger Analysis", desc: "Audit group-level debt acceleration clauses and encumbrances", prompt: "Are there any cross-default triggers or related-party exposure in the group structure?" }
            ]
        }
    },
    etf: {
        arbitrage: {
            headerTitle: "Arbitrage & Fair NAV Corridor Desk",
            introHeadline: "Arbitrage Spread & Fair NAV Workspace",
            introText: (ticker) => `Auditing secondary market premium/discount spreads vs Fair NAV and Authorized Participant basket incentives for <strong>${ticker || 'this ETF'}</strong>.`,
            features: [
                { icon: "icon-valuation", title: "Arbitrage & Fair NAV Spread", desc: "Audit CMP vs statutory Fair NAV premium/discount", prompt: "Evaluate the secondary market premium/discount spread and arbitrage corridor for this ETF." },
                { icon: "icon-multi-asset", title: "AP Creation/Redemption Arbitrage", desc: "How Authorized Participants keep CMP aligned with iNAV", prompt: "How do Authorized Participants arbitrage this spread via creation/redemption baskets?" }
            ]
        },
        tracking_error: {
            headerTitle: "Tracking Error & Replication Desk",
            introHeadline: "Tracking Error & Replication Workspace",
            introText: (ticker) => `Auditing 1-year annualized tracking error, cash drag, and replication fidelity vs benchmark index for <strong>${ticker || 'this ETF'}</strong>.`,
            features: [
                { icon: "icon-screen", title: "1Y Tracking Error Fidelity", desc: "1-year annualized tracking error vs benchmark index", prompt: "Audit the 1-year annualized tracking error and replication fidelity for this ETF." },
                { icon: "icon-valuation", title: "Drag Attribution Breakdown", desc: "Attribute tracking error to TER, cash drag, and dividend lag", prompt: "What portion of tracking error comes from TER, cash drag, and dividend reinvestment latency?" }
            ]
        }
    }
};

function detectAssetType(ticker) {
    if (window.__CURRENT_ASSET_TYPE) return window.__CURRENT_ASSET_TYPE;
    const loc = window.location.pathname.toLowerCase();
    if (loc.includes("/reits")) return "reit";
    if (loc.includes("/etfs")) return "etf";
    if (loc.includes("/funds")) return "mutual_fund";
    if (loc.includes("/debt")) return "debt";
    if (!ticker) return "equity";

    const clean = String(ticker).trim().toUpperCase();
    if (["EMBASSY", "MINDSPACE", "BIRET", "NEXUS", "PGINVIT", "INDIGRID", "IRBINVIT", "NHIT", "ORIENTINVIT", "BHARATINV", "PROPSHARE", "STRATA", "SMREIT_BLR_01", "SMREIT_HYD_02", "IRB_INVIT", "NHAI_INVIT"].includes(clean) || clean.includes("REIT") || clean.includes("INVIT")) {
        return "reit";
    }
    if (clean.endsWith("BEES") || clean.endsWith("ETF") || ["NIFTYBEES", "GOLDBEES", "BANKBEES", "SILVERBEES", "SETFNIF50", "HDFCNIFTY", "CPSEETF", "MON100"].includes(clean)) {
        return "etf";
    }
    if (/^\d+$/.test(clean) || clean.endsWith("_DIR") || clean.endsWith("_REG") || clean.includes("FLEXICAP") || clean.includes("MIDCAP") || clean.includes("SMALLCAP") || clean.includes("FUND") || clean.includes("GROWTH")) {
        return "mutual_fund";
    }
    if (clean.startsWith("IN") || clean.includes("BOND") || clean.includes("SDI") || clean.includes("NCD")) {
        return "debt";
    }
    return "equity";
}

/**
 * Lightweight, safe markdown formatter for Research Desk analysis responses.
 * Escapes raw HTML to prevent injection and turns markdown elements into rich UI tokens.
 */
function renderCopilotMarkdown(rawText) {
    if (!rawText) return "";

    // 1. Escape HTML entities
    let text = String(rawText)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");

    // 2. Code blocks (```lang ... ```)
    text = text.replace(/```([a-zA-Z0-9_-]*)\n([\s\S]*?)```/g, function(_, lang, code) {
        return `<pre class="copilot-table-wrap" style="background: rgba(15, 23, 42, 0.9); padding: 10px; border-radius: 6px;"><code class="copilot-inline-code" style="display:block; white-space:pre;">${code.trim()}</code></pre>`;
    });

    // 3. Inline code (`code`)
    text = text.replace(/`([^`]+)`/g, '<code class="copilot-inline-code">$1</code>');

    // 4. Headings (### Title / ## Title)
    text = text.replace(/^### (.*$)/gim, '<h4>$1</h4>');
    text = text.replace(/^## (.*$)/gim, '<h4>$1</h4>');
    text = text.replace(/^# (.*$)/gim, '<h4>$1</h4>');

    // 5. Bold & Italic
    text = text.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    text = text.replace(/\*([^*]+)\*/g, '<em>$1</em>');

    // 6. Markdown Tables
    const lines = text.split("\n");
    let inTable = false;
    let tableHtml = "";
    let processedLines = [];

    for (let i = 0; i < lines.length; i++) {
        const line = lines[i].trim();
        if (line.startsWith("|") && line.endsWith("|")) {
            // Check if delimiter row
            if (/^\|[-:\s|]+\|$/.test(line)) {
                continue;
            }
            const cells = line.split("|").slice(1, -1).map(c => c.trim());
            if (!inTable) {
                inTable = true;
                tableHtml = '<div class="copilot-table-wrap"><table class="copilot-table"><thead><tr>';
                cells.forEach(c => { tableHtml += `<th>${c}</th>`; });
                tableHtml += '</tr></thead><tbody>';
            } else {
                tableHtml += '<tr>';
                cells.forEach(c => { tableHtml += `<td>${c}</td>`; });
                tableHtml += '</tr>';
            }
        } else {
            if (inTable) {
                tableHtml += '</tbody></table></div>';
                processedLines.push(tableHtml);
                inTable = false;
                tableHtml = "";
            }
            processedLines.push(lines[i]);
        }
    }
    if (inTable) {
        tableHtml += '</tbody></table></div>';
        processedLines.push(tableHtml);
    }

    // 8. Bullet Lists (- Item or * Item)
    const listLines = processedLines;
    let inList = false;
    let inOrderedList = false;
    let listOutput = [];

    for (let i = 0; i < listLines.length; i++) {
        const line = listLines[i];
        const trimmed = line.trim();

        if (trimmed.startsWith("- ") || trimmed.startsWith("* ")) {
            if (!inList) {
                if (inOrderedList) { listOutput.push("</ol>"); inOrderedList = false; }
                listOutput.push("<ul>");
                inList = true;
            }
            listOutput.push(`<li>${trimmed.substring(2)}</li>`);
        } else if (/^\d+\.\s/.test(trimmed)) {
            if (!inOrderedList) {
                if (inList) { listOutput.push("</ul>"); inList = false; }
                listOutput.push("<ol>");
                inOrderedList = true;
            }
            const content = trimmed.replace(/^\d+\.\s/, "");
            listOutput.push(`<li>${content}</li>`);
        } else {
            if (inList) { listOutput.push("</ul>"); inList = false; }
            if (inOrderedList) { listOutput.push("</ol>"); inOrderedList = false; }
            listOutput.push(line);
        }
    }
    if (inList) listOutput.push("</ul>");
    if (inOrderedList) listOutput.push("</ol>");

    // 9. Clean paragraph separation
    const finalBlocks = [];
    let curParaLines = [];
    const isBlockTag = (str) => {
        const s = str.trim();
        return s.startsWith("<h4>") || s.startsWith("<div") || s.startsWith("</div>") ||
               s.startsWith("<pre") || s.startsWith("<ul>") || s.startsWith("<ol>") ||
               s.startsWith("<li>") || s.startsWith("</ul>") || s.startsWith("</ol>");
    };

    for (let i = 0; i < listOutput.length; i++) {
        const l = listOutput[i];
        const trimmed = l.trim();
        if (!trimmed) {
            if (curParaLines.length > 0) {
                finalBlocks.push("<p>" + curParaLines.join("<br>") + "</p>");
                curParaLines = [];
            }
        } else if (isBlockTag(trimmed)) {
            if (curParaLines.length > 0) {
                finalBlocks.push("<p>" + curParaLines.join("<br>") + "</p>");
                curParaLines = [];
            }
            finalBlocks.push(trimmed);
        } else {
            curParaLines.push(trimmed);
        }
    }
    if (curParaLines.length > 0) {
        finalBlocks.push("<p>" + curParaLines.join("<br>") + "</p>");
    }

    // 10. Wrap SEBI Non-Advisory Notices in high-clarity notice cards
    for (let i = 0; i < finalBlocks.length; i++) {
        if (finalBlocks[i].includes("<strong>SEBI Regulatory Non-Advisory Notice:</strong>")) {
            finalBlocks[i] = `<div class="copilot-notice-box">${finalBlocks[i]}</div>`;
        }
    }

    const joinedHtml = finalBlocks.join("\n");
    const lowerRaw = String(rawText || "").toLowerCase();
    let microWidgetHtml = "";

    if ((lowerRaw.includes("reverse dcf") || lowerRaw.includes("wacc") || lowerRaw.includes("intrinsic value")) && !lowerRaw.includes("copilot-micro-dcf")) {
        const uid = "dcf_" + Math.random().toString(36).substring(2, 7);
        microWidgetHtml = `
        <div class="copilot-micro-dcf" style="margin-top:12px;padding:12px;background:rgba(15,23,42,0.85);border:1px solid rgba(56,189,248,0.3);border-radius:10px;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
            <span style="font-size:11px;font-weight:800;color:#38bdf8;text-transform:uppercase;letter-spacing:0.05em;">${brandGlyph("icon-insights")} Interactive Reverse DCF Stress Sandbox</span>
            <span id="${uid}_out" style="font-size:12px;font-weight:800;color:#34d399;font-variant-numeric:tabular-nums;">Fair Multiple: 21.8x</span>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:11px;color:#cbd5e1;">
            <label style="display:flex;flex-direction:column;gap:3px;">
              <span>10Y FCF CAGR (<strong id="${uid}_glbl">14%</strong>)</span>
              <input type="range" min="4" max="28" step="1" value="14" oninput="(function(el){var g=parseFloat(el.value),w=parseFloat(document.getElementById('${uid}_w').value);document.getElementById('${uid}_glbl').textContent=g+'%';var mult=Math.max(8,Math.min(45,(1+g/100)*15/(Math.max(0.05,w/100-0.04))*0.11)).toFixed(1);document.getElementById('${uid}_out').textContent='Fair Multiple: '+mult+'x';})(this)">
            </label>
            <label style="display:flex;flex-direction:column;gap:3px;">
              <span>WACC Hurdle (<strong id="${uid}_wlbl">12.0%</strong>)</span>
              <input id="${uid}_w" type="range" min="9" max="16" step="0.5" value="12" oninput="(function(el){var w=parseFloat(el.value),g=parseFloat(el.parentNode.parentNode.querySelector('input').value);document.getElementById('${uid}_wlbl').textContent=w.toFixed(1)+'%';var mult=Math.max(8,Math.min(45,(1+g/100)*15/(Math.max(0.05,w/100-0.04))*0.11)).toFixed(1);document.getElementById('${uid}_out').textContent='Fair Multiple: '+mult+'x';})(this)">
            </label>
          </div>
        </div>`;
    } else if ((lowerRaw.includes("fee drag") || lowerRaw.includes("expense ratio") || lowerRaw.includes("ter")) && !lowerRaw.includes("copilot-micro-ter")) {
        const uid = "ter_" + Math.random().toString(36).substring(2, 7);
        microWidgetHtml = `
        <div class="copilot-micro-ter" style="margin-top:12px;padding:12px;background:rgba(15,23,42,0.85);border:1px solid rgba(16,185,129,0.3);border-radius:10px;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
            <span style="font-size:11px;font-weight:800;color:#34d399;text-transform:uppercase;letter-spacing:0.05em;">${brandGlyph("icon-valuation")} 20Y Direct vs Regular Fee Drag</span>
            <span id="${uid}_out" style="font-size:12px;font-weight:800;color:#f87171;font-variant-numeric:tabular-nums;">Comm. Loss: ₹14.2L</span>
          </div>
          <label style="display:flex;flex-direction:column;gap:4px;font-size:11px;color:#cbd5e1;">
            <span>Initial Corpus: <strong id="${uid}_clbl">₹10 Lakhs</strong> (at 110 bps TER spread, 12% CAGR)</span>
            <input type="range" min="1" max="100" step="1" value="10" oninput="(function(el){var c=parseFloat(el.value);document.getElementById('${uid}_clbl').textContent='₹'+c+' Lakhs';var loss=(c*(Math.pow(1.114,20)-Math.pow(1.103,20))).toFixed(1);document.getElementById('${uid}_out').textContent='Comm. Loss: ₹'+loss+'L';})(this)">
          </label>
        </div>`;
    }

    return joinedHtml + microWidgetHtml;
}

function formatCopilotMarkdown(rawText) {
    return renderCopilotMarkdown(rawText);
}
window.formatCopilotMarkdown = formatCopilotMarkdown;
window.renderCopilotMarkdown = renderCopilotMarkdown;

function formatCurrentTime() {
    const now = new Date();
    return now.toLocaleTimeString('en-IN', {
        timeZone: 'Asia/Kolkata',
        hour: '2-digit',
        minute: '2-digit',
        hour12: false
    }) + ' IST';
}

function renderIntroWelcomeCard(cfg, ticker, section, sectionLabel) {
    let headline = cfg.headerTitle;
    let descHtml = cfg.introText(ticker);
    let featuresList = cfg.features || [];

    if (section && SECTION_METADATA[activeAssetType] && SECTION_METADATA[activeAssetType][section]) {
        const sm = SECTION_METADATA[activeAssetType][section];
        if (sm.introHeadline) headline = sm.introHeadline;
        if (sm.introText) descHtml = sm.introText(ticker);
        if (sm.features && sm.features.length) featuresList = sm.features;
    }

    let html = `
        <div class="copilot-intro-headline">
          <span>${brandGlyph("icon-insights")}</span> ${headline}
        </div>
        <div style="color: #cbd5e1; font-size: 0.88rem; line-height: 1.55;">
          ${descHtml}
        </div>
    `;

    if (sectionLabel) {
        html += `
            <div style="margin-top: 10px; padding: 8px 12px; background: rgba(168, 85, 247, 0.12); border: 1px solid rgba(168, 85, 247, 0.35); border-radius: 8px; font-size: 0.8rem; color: #d8b4fe; display: flex; align-items: center; gap: 6px;">
                <span>${brandGlyph("icon-watchlist")}</span> <span><strong>Focused Workspace:</strong> ${sectionLabel}. Diagnostic tools and queries below are calibrated directly to this section.</span>
            </div>
        `;
    }

    if (featuresList && featuresList.length) {
        html += `<div class="copilot-intro-features">`;
        featuresList.forEach(f => {
            html += `
                <div class="copilot-intro-feature-item" data-copilot-prompt="${encodeURIComponent(f.prompt)}" role="button" tabindex="0">
                    <span style="font-size: 1.1rem; pointer-events: none;">${brandGlyph(f.icon)}</span>
                    <div style="pointer-events: none;">
                        <div style="font-weight: 700; color: #f8fafc; font-size: 0.90rem;">${f.title}</div>
                        <div style="color: #94a3b8; font-size: 0.82rem; line-height: 1.4; margin-top: 2px;">${f.desc}</div>
                    </div>
                </div>
            `;
        });
        html += `</div>`;
    }

    return html;
}

function openCopilot(ticker, assetType, section, sectionLabel, initialPrompt) {
    const prevTicker = activeTicker;
    const prevSection = activeSection;

    activeTicker = ticker ? String(ticker).trim() : "";
    activeAssetType = assetType || detectAssetType(activeTicker);
    activeSection = section || null;
    activeSectionLabel = sectionLabel || "";

    const cfg = COPILOT_CONFIGS[activeAssetType] || COPILOT_CONFIGS.equity;
    const secMeta = (activeSection && SECTION_METADATA[activeAssetType] && SECTION_METADATA[activeAssetType][activeSection])
        ? SECTION_METADATA[activeAssetType][activeSection]
        : null;

    // Reset conversation session if switching securities or section
    if (prevTicker !== activeTicker || prevSection !== activeSection || !activeConversationId) {
        activeConversationId = "COPILOT-" + Date.now() + "-" + Math.random().toString(36).substr(2, 6);

        // Reset message container with styled intro card
        const container = document.getElementById("copilotMessages");
        if (container) {
            container.innerHTML = `
                <div id="copilotIntroBubble" class="copilot-intro-card">
                    ${renderIntroWelcomeCard(cfg, activeTicker, activeSection, activeSectionLabel)}
                </div>
            `;
            container.scrollTop = 0;
        }
    }

    // Update Header and Badges
    const headerTitleEl = document.getElementById("copilotHeaderTitle");
    if (headerTitleEl) {
        headerTitleEl.textContent = secMeta ? secMeta.headerTitle : cfg.headerTitle;
    }

    const assetBadgeEl = document.getElementById("copilotAssetBadge");
    if (assetBadgeEl) assetBadgeEl.textContent = cfg.assetBadge;

    const sectionBadgeEl = document.getElementById("copilotSectionBadge");
    if (sectionBadgeEl) {
        if (activeSectionLabel) {
            sectionBadgeEl.innerHTML = brandGlyph("icon-watchlist") + " ";
            sectionBadgeEl.appendChild(document.createTextNode(activeSectionLabel));
            sectionBadgeEl.style.display = "inline-flex";
        } else {
            sectionBadgeEl.style.display = "none";
        }
    }

    const tickerSpan = document.getElementById("copilotContextTicker");
    if (tickerSpan) tickerSpan.textContent = activeTicker || "UNIVERSAL";

    // Populate Quick Prompt Chips
    const chipsContainer = document.getElementById("copilotQuickChips");
    if (chipsContainer) {
        let chipsToRender = [];
        if (activeSection && SECTION_CHIPS[activeAssetType] && SECTION_CHIPS[activeAssetType][activeSection]) {
            chipsToRender = SECTION_CHIPS[activeAssetType][activeSection];
        } else {
            chipsToRender = cfg.chips || [];
        }

        chipsContainer.innerHTML = chipsToRender.map(chip => `
            <button type="button" class="copilot-chip-btn" data-copilot-prompt="${encodeURIComponent(chip.prompt)}">
                ${chip.icon ? brandGlyph(chip.icon) + " " : ""}${chip.label}
            </button>
        `).join("");
    }

    // Show modal with smooth class-based slide animation
    const modal = document.getElementById("copilotModalBackdrop");
    const container = document.getElementById("copilotMessages");
    const panel = document.querySelector(".copilot-panel");

    if (container) container.scrollTop = 0;
    if (panel) panel.scrollTop = 0;

    if (modal) {
        if (modal.parentElement !== document.body) {
            document.body.appendChild(modal);
        }
        modal.inert = false;
        modal.removeAttribute("inert");
        modal.style.display = "flex";
        void modal.offsetWidth;
        modal.classList.add("copilot-open");
        const mainEl = document.querySelector("main");
        if (mainEl && !mainEl.contains(modal)) {
            mainEl.inert = true;
        }
    }

    // Prepare and focus input synchronously (required for mobile virtual keyboard) + post-transition fallback
    const input = document.getElementById("copilotInput");
    if (input) {
        if (initialPrompt) {
            input.value = initialPrompt;
        }
        handleCopilotInput(input);
        try {
            input.focus({ preventScroll: true });
        } catch (e) {
            input.focus();
        }
        setTimeout(() => {
            if (container) container.scrollTop = 0;
            if (panel) panel.scrollTop = 0;
            try {
                input.focus({ preventScroll: true });
            } catch (e) {
                input.focus();
            }
            if (container) container.scrollTop = 0;
            if (panel) panel.scrollTop = 0;
        }, 100);
    }
}

function closeCopilot() {
    const modal = document.getElementById("copilotModalBackdrop");
    const mainEl = document.querySelector("main");
    if (mainEl) {
        mainEl.inert = false;
        mainEl.removeAttribute("inert");
    }
    if (modal) {
        modal.classList.remove("copilot-open");
        setTimeout(() => {
            if (!modal.classList.contains("copilot-open")) {
                modal.style.display = "none";
            }
        }, 320);
    }
}

function resetCopilotChat() {
    activeConversationId = "COPILOT-" + Date.now() + "-" + Math.random().toString(36).substr(2, 6);
    const cfg = COPILOT_CONFIGS[activeAssetType] || COPILOT_CONFIGS.equity;
    const container = document.getElementById("copilotMessages");
    const panel = document.querySelector(".copilot-panel");

    if (container) {
        container.innerHTML = `
            <div id="copilotIntroBubble" class="copilot-intro-card">
                ${renderIntroWelcomeCard(cfg, activeTicker, activeSection, activeSectionLabel)}
            </div>
        `;
        container.scrollTop = 0;
    }
    if (panel) panel.scrollTop = 0;

    const input = document.getElementById("copilotInput");
    if (input) {
        input.value = "";
        handleCopilotInput(input);
        try {
            input.focus({ preventScroll: true });
        } catch (e) {
            input.focus();
        }
        if (container) container.scrollTop = 0;
        if (panel) panel.scrollTop = 0;
    }
}

function handleCopilotBackdropClick(event) {
    if (event.target && event.target.id === "copilotModalBackdrop") {
        closeCopilot();
    }
}

function handleCopilotInput(el) {
    if (!el) return;
    // Auto-resize textarea
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 120) + "px";

    // Toggle send button active state
    const sendBtn = document.getElementById("copilotSendBtn");
    if (sendBtn) {
        const hasText = el.value.trim().length > 0;
        if (hasText) {
            sendBtn.classList.add("active");
            sendBtn.removeAttribute("disabled");
        } else {
            sendBtn.classList.remove("active");
            sendBtn.setAttribute("disabled", "true");
        }
    }
}

function handleCopilotKeydown(event) {
    if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        // Block premature submission during IME composition (including Safari keyCode 229 quirk)
        if (event.isComposing || event.keyCode === 229) {
            return;
        }
        submitCopilotMessage();
    }
}

function sendQuickPrompt(promptText) {
    if (!promptText) return;
    const input = document.getElementById("copilotInput");
    if (input) {
        input.value = promptText;
        handleCopilotInput(input);
        submitCopilotMessage();
    }
}

function copyCopilotTurn(btn, contentText) {
    if (!navigator.clipboard || !contentText) return;
    navigator.clipboard.writeText(contentText).then(() => {
        const origText = btn.innerHTML;
        btn.innerHTML = `Copied`;
        btn.style.color = "#38bdf8";
        setTimeout(() => {
            btn.innerHTML = origText;
            btn.style.color = "";
        }, 2000);
    }).catch(err => {
        console.warn("Failed to copy copilot text:", err);
    });
}

let isSubmitting = false;

function scrollToBottom() {
    const container = document.getElementById("copilotMessages");
    if (container) {
        container.scrollTop = container.scrollHeight;
    }
}

function escapeHtml(str) {
    if (!str) return "";
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

async function submitCopilotMessage() {
    const input = document.getElementById("copilotInput");
    const sendBtn = document.getElementById("copilotSendBtn");
    const container = document.getElementById("copilotMessages");

    if (isSubmitting) return;
    if (!input || !input.value.trim()) return;

    isSubmitting = true;
    const userMsg = input.value.trim();
    input.value = "";
    handleCopilotInput(input);

    const currentTime = formatCurrentTime();

    // Transition from empty welcome state to active conversation:
    // Hide the welcome intro card to prevent half-scrolled clipping and maximize message height
    const introCard = document.getElementById("copilotIntroBubble");
    if (introCard) {
        introCard.style.display = "none";
    }

    // Append user message bubble
    const userTurn = document.createElement("div");
    userTurn.className = "copilot-turn copilot-turn-user";
    userTurn.innerHTML = `
        <div class="copilot-bubble-user">
            ${userMsg.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/\n/g, "<br>")}
        </div>
        <div class="copilot-turn-meta">You • ${currentTime}</div>
    `;
    container.appendChild(userTurn);
    scrollToBottom();

    // Append animated thinking wave indicator with live timer and dynamic background info
    const thinkingCard = document.createElement("div");
    thinkingCard.className = "copilot-thinking-card";
    const thinkingEl = thinkingCard;
    
    let thinkingStages = [
        "Scanning verified filings & baseline disclosures...",
        "Stress-testing thesis against 7-pillar accounting framework...",
        "Evaluating capital allocation & Reverse DCF hurdles...",
        "Generating diagnosis & Countercase failure modes..."
    ];
    if (activeAssetType === "mutual_fund") {
        thinkingStages = [
            "Scanning AMFI portfolio disclosures & constituent weights...",
            "Evaluating Active Share, closet indexing & 10Y fee drag...",
            "Auditing ASRI accounting stress across underlying holdings...",
            "Generating look-through portfolio health verdict..."
        ];
    } else if (activeAssetType === "debt") {
        thinkingStages = [
            "Inspecting BSE Debt registry & credit rating rationales...",
            "Calculating YTM, Macaulay Duration & interest rate shock...",
            "Auditing statutory recovery seniority & equity contagion...",
            "Formulating solvency diagnosis..."
        ];
    }

    thinkingCard.innerHTML = `
        <div class="copilot-thinking-row" style="display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap;">
            <div style="display: flex; align-items: center; gap: 8px;">
                <div class="copilot-typing-dots">
                    <span class="copilot-typing-dot"></span>
                    <span class="copilot-typing-dot"></span>
                    <span class="copilot-typing-dot"></span>
                </div>
                <span id="copilotThinkingText" class="copilot-thinking-text">${thinkingStages[0]}</span>
            </div>
            <span id="copilotThinkingTimer" class="copilot-thinking-timer" style="font-size: 11px; font-weight: 700; color: #38bdf8; font-variant-numeric: tabular-nums; background: rgba(15, 23, 42, 0.7); padding: 2px 8px; border-radius: 9999px; border: 1px solid rgba(56, 189, 248, 0.3); font-family: monospace;">0s / ~10s</span>
        </div>
    `;
    container.appendChild(thinkingCard);
    container.scrollTop = container.scrollHeight;

    const thinkingStartMs = Date.now();
    const thinkingTimer = setInterval(() => {
        const sec = Math.floor((Date.now() - thinkingStartMs) / 1000);
        const timerEl = document.getElementById("copilotThinkingTimer");
        const textEl = document.getElementById("copilotThinkingText");
        if (timerEl) timerEl.innerText = `${sec}s / ~10s`;
        if (textEl) {
            if (sec < 3) textEl.innerText = thinkingStages[0];
            else if (sec < 6) textEl.innerText = thinkingStages[1];
            else if (sec < 9) textEl.innerText = thinkingStages[2];
            else textEl.innerText = thinkingStages[3];
        }
    }, 250);

    sendBtn.disabled = true;
    sendBtn.classList.remove("active");

    const payload = {
        conversation_id: activeConversationId,
        message: userMsg,
        ticker: activeTicker,
        asset_type: activeAssetType,
        asset_class: activeAssetType ? (activeAssetType === "mutual_fund" ? "MUTUAL_FUND" : activeAssetType === "debt" ? "CORPORATE_DEBT" : activeAssetType.toUpperCase()) : "EQUITY",
        section: activeSection,
        section_label: activeSectionLabel
    };

    try {
        let data = {};
        try {
            const resp = await fetch('/api/copilot/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            const rawText = await resp.text();
            try {
                data = rawText ? JSON.parse(rawText) : {};
            } catch (_) {
                data = { detail: rawText || `Server returned HTTP ${resp.status}` };
            }

            if (!resp.ok) {
                const errMsg = typeof data.detail === 'string'
                    ? data.detail
                    : (data.detail?.message || data.error || `Server error (${resp.status})`);
                throw new Error(errMsg);
            }
        } finally {
            clearInterval(thinkingTimer);
        }

        if (data.conversation_id) {
            activeConversationId = data.conversation_id;
        }

        const answerHtml = formatCopilotMarkdown(data.answer || data.response || "No response received from desk.");
        const citations = data.citations || [];
        let citHtml = '';
        if (citations.length > 0) {
            const badges = citations.map(c => `<span class="copilot-citation-tag">${escapeHtml(c)}</span>`).join('');
            citHtml = `<div class="copilot-citations"><span class="cit-label">Sources:</span> ${badges}</div>`;
        }

        let guardHtml = '';
        if (data.guardrail_triggered) {
            guardHtml = `<div class="copilot-guardrail-badge">${brandGlyph("icon-risk")} SEBI Safe-Harbor Guardrail Applied</div>`;
        }

        thinkingEl.outerHTML = `
            <div class="copilot-msg copilot-msg-assistant">
                ${guardHtml}
                <div class="copilot-msg-bubble">${answerHtml}</div>
                ${citHtml}
            </div>
        `;

        if (data.unlock_required && typeof window.unlockAssetDeepDive === "function") {
            const lastMsg = container.querySelector(".copilot-msg-assistant:last-child .copilot-msg-bubble") || container.querySelector(".copilot-msg-assistant:last-child");
            if (lastMsg) {
                const unlockBtn = document.createElement("button");
                unlockBtn.type = "button";
                unlockBtn.className = "btn btn-primary btn-sm";
                unlockBtn.style.cssText = "margin-top: 10px; font-weight: 700; border-radius: 9999px; cursor: pointer;";
                unlockBtn.textContent = "Unlock Deep Dive for 1 credit";
                unlockBtn.addEventListener("click", function() {
                    window.unlockAssetDeepDive(data.unlock_required.asset_kind, data.unlock_required.asset_id);
                });
                lastMsg.appendChild(unlockBtn);
            }
        }
    } catch (e) {
        clearInterval(thinkingTimer);
        console.error('Copilot chat error:', e);
        const safeReason = escapeHtml(e?.message || 'Unable to reach the Research Desk service.');
        thinkingEl.outerHTML = `
            <div class="copilot-msg copilot-msg-assistant">
                <div class="copilot-notice">
                    <strong>${brandGlyph("icon-alerts")} Copilot Notice:</strong> ${safeReason}
                </div>
            </div>
        `;
    } finally {
        isSubmitting = false;
        if (sendBtn) sendBtn.disabled = false;
        scrollToBottom();
    }
}

// Delegated click listener for all interactive Copilot prompts & copy buttons
document.addEventListener("click", function(e) {
    // 1. Quick Prompt triggers (intro feature cards & chip buttons)
    const promptTrigger = e.target.closest("[data-copilot-prompt]");
    if (promptTrigger) {
        e.preventDefault();
        e.stopPropagation();
        const rawPrompt = promptTrigger.getAttribute("data-copilot-prompt");
        if (rawPrompt) {
            sendQuickPrompt(decodeURIComponent(rawPrompt));
        }
        return;
    }

    // 2. Copy turn button
    const copyBtn = e.target.closest("[data-copilot-copy]");
    if (copyBtn) {
        e.preventDefault();
        e.stopPropagation();
        const rawCopy = copyBtn.getAttribute("data-copilot-copy");
        if (rawCopy) {
            copyCopilotTurn(copyBtn, decodeURIComponent(rawCopy));
        }
        return;
    }
});

// Accessible keyboard navigation (Enter/Space on feature cards)
document.addEventListener("keydown", function(e) {
    if (e.key === "Enter" || e.key === " ") {
        const promptTrigger = e.target.closest(".copilot-intro-feature-item[data-copilot-prompt]");
        if (promptTrigger && document.activeElement === promptTrigger) {
            e.preventDefault();
            const rawPrompt = promptTrigger.getAttribute("data-copilot-prompt");
            if (rawPrompt) {
                sendQuickPrompt(decodeURIComponent(rawPrompt));
            }
        }
    }
});

function toggleResearchDesk() {
    const modal = document.getElementById("copilotModalBackdrop");
    if (modal && (modal.classList.contains("copilot-open") || modal.style.display === "flex")) {
        closeCopilot();
    } else {
        const ticker = activeTicker || window.__CURRENT_TICKER || "";
        const assetType = activeAssetType || window.__CURRENT_ASSET_TYPE || "equity";
        openCopilot(ticker, assetType);
    }
}

// Global shortcut listener: ⌘K or Ctrl+K (without Shift) toggles Research Desk on dossier pages;
// '/' and ⇧⌘K are reserved globally for 7-Asset Omni-Search in main.js.
document.addEventListener("keydown", function(e) {
    if ((e.metaKey || e.ctrlKey) && !e.shiftKey && e.key.toLowerCase() === "k") {
        const omniModal = document.getElementById("omniSearchModal");
        if (omniModal && omniModal.classList.contains("active") && typeof window.closeOmniSearchModal === "function") {
            window.closeOmniSearchModal();
        }
        e.preventDefault();
        toggleResearchDesk();
    }
});

// Global escape key listener to smoothly close modal
document.addEventListener("keydown", function(e) {
    if (e.key === "Escape") {
        const modal = document.getElementById("copilotModalBackdrop");
        if (modal && (modal.classList.contains("copilot-open") || modal.style.display === "flex")) {
            closeCopilot();
        }
    }
});

// Ensure global functions are available on window
window.openCopilot = openCopilot;
window.closeCopilot = closeCopilot;
window.openResearchDesk = openCopilot;
window.closeResearchDesk = closeCopilot;
window.toggleResearchDesk = toggleResearchDesk;
window.resetCopilotChat = resetCopilotChat;
window.handleCopilotBackdropClick = handleCopilotBackdropClick;
window.handleCopilotInput = handleCopilotInput;
window.handleCopilotKeydown = handleCopilotKeydown;
window.sendQuickPrompt = sendQuickPrompt;
window.copyCopilotTurn = copyCopilotTurn;
window.submitCopilotMessage = submitCopilotMessage;

// Hoist Copilot Modal & Floating Dock out of <main> to document.body so <main inert> never locks out the drawer
function hoistCopilotToBody() {
    const modal = document.getElementById("copilotModalBackdrop");
    if (modal && modal.parentElement !== document.body) {
        document.body.appendChild(modal);
    }
    const fab = document.getElementById("researchDeskFloatingDock");
    if (fab && fab.parentElement !== document.body) {
        document.body.appendChild(fab);
    }
}
if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", hoistCopilotToBody);
} else {
    hoistCopilotToBody();
}

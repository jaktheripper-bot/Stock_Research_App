/**
 * Institutional Investor Copilot Frontend Controller.
 * Institutional Forensic Intelligence Architecture.
 * Supports Multi-Asset Dispatch across Fundamental Equities, Mutual Funds, and Corporate Debt,
 * with Deep Section Contextual Awareness and SEBI Non-Advisory Safe Harbor Guardrails.
 */

let activeConversationId = null;
let activeTicker = "";
let activeAssetType = "equity";
let activeSection = null;
let activeSectionLabel = "";

const COPILOT_CONFIGS = {
    equity: {
        headerTitle: "Institutional Forensic Copilot",
        assetBadge: "Fundamental Equity",
        introText: (ticker) => `Welcome to the <strong>Forensic Copilot</strong>. I can assist in stress-testing your investment thesis on <strong>${ticker || 'the selected equity'}</strong>, deriving implied growth rates via Reverse DCF, or running a <strong>Pre-Mortem Inversion analysis</strong>.`,
        chips: [
            { label: "💀 Pre-Mortem Inversion", prompt: "Run Pre-Mortem Inversion analysis on this stock: what failure modes could destroy shareholder value?" },
            { label: "📉 Reverse DCF Implied Growth", prompt: "What implied growth rate is priced into current CMP based on Reverse DCF?" },
            { label: "🚩 Governance & Pledging Check", prompt: "Are there any promoter pledging or corporate governance red flags in recent disclosures?" }
        ]
    },
    mutual_fund: {
        headerTitle: "Fund Look-Through Copilot",
        assetBadge: "Mutual Fund Intelligence",
        introText: (ticker) => `Welcome to the <strong>Fund Look-Through Copilot</strong>. I evaluate underlying constituent quality, weighted moat endurance, look-through ASRI accounting stress, active share vs benchmark, and <strong>direct vs regular intermediary fee drag</strong> for <strong>${ticker || 'this scheme'}</strong>.`,
        chips: [
            { label: "🛡️ Moat & Quality Score", prompt: "Evaluate the constituent moat distribution and overall portfolio quality for this fund." },
            { label: "⚠️ High-Risk Holdings", prompt: "Which underlying constituent holdings carry the highest accounting risk or lowest health score?" },
            { label: "🧭 Style Drift & Active Share", prompt: "Audit the active share and check if this fund is exhibiting benchmark hugging or style drift." },
            { label: "💸 Intermediary Fee Drag", prompt: "What is the 20-year compounded fee drag and wealth lost to distributor commissions for this fund?" }
        ]
    },
    debt: {
        headerTitle: "Credit & Solvency Copilot",
        assetBadge: "Fixed Income & SDI Solvency",
        introText: (ticker) => `Welcome to the <strong>Credit & Solvency Copilot</strong>. I can stress-test Asset Coverage Ratios (ACR), recovery seniority in liquidation, DSCR covenant headroom, and <strong>credit contagion risk</strong> for <strong>${ticker || 'this security'}</strong>.`,
        chips: [
            { label: "🛡️ Asset Coverage & Covenants", prompt: "Stress-test the Asset Coverage Ratio (ACR) and DSCR covenant headroom for this instrument." },
            { label: "⚖️ Recovery Seniority Tier", prompt: "Evaluate recovery seniority and investor recourse in a stressed debt restructuring or liquidation." },
            { label: "📡 Credit Contagion Radar", prompt: "What does the Credit Contagion Radar say about the parent group and systemic risks for this issuer?" }
        ]
    }
};

const SECTION_CHIPS = {
    mutual_fund: {
        fee_drag: [
            { label: "💸 20-Yr Compounded Drag", prompt: "What is the 20-year compounded fee drag and total wealth lost between Direct and Regular plans for this fund?" },
            { label: "📉 TER Spread Analysis", prompt: "Analyze the distributor commission spread (bps/year) and why direct plans protect compounding." },
            { label: "⚖️ Fiduciary Takeaway", prompt: "What is the fiduciary takeaway regarding the expense ratio and distributor commissions?" }
        ],
        active_share: [
            { label: "🧭 Closet Indexing Check", prompt: "Is this fund exhibiting benchmark hugging or closet indexing based on its Active Share?" },
            { label: "📊 Active Share vs Benchmark", prompt: "Evaluate the Active Share score and concentration vs benchmark index." },
            { label: "⚠️ Style Drift Diagnostic", prompt: "Check if this fund is drifting away from its stated mandate or category style." }
        ],
        asri_solvency: [
            { label: "⚠️ High-Risk Constituents", prompt: "Which underlying constituent holdings carry the highest accounting risk or lowest health score?" },
            { label: "🚩 Promoter Pledging Check", prompt: "Are any constituent companies flagged for elevated promoter pledging or governance risks?" },
            { label: "🛡️ Look-Through ASRI", prompt: "Evaluate the portfolio-wide Accounting Stress & Risk Index (ASRI)." }
        ],
        moat_index: [
            { label: "🏰 Weighted Moat Breakdown", prompt: "Break down the fund's Weighted Moat Index and proportion of Wide vs Narrow Moat businesses." },
            { label: "⭐ Core Compounders", prompt: "Which top holdings contribute the strongest structural economic moats?" },
            { label: "🛡️ Pricing Power Endurance", prompt: "Evaluate the pricing power and return on capital endurance of the underlying portfolio." }
        ],
        margin_of_safety: [
            { label: "📐 Weighted MoS (DCF)", prompt: "What is the weighted Margin of Safety across the portfolio based on DCF models?" },
            { label: "🏷️ Intrinsic Valuation Gap", prompt: "Are the top constituent holdings trading at a discount or premium to intrinsic value?" }
        ],
        promoter_pledge: [
            { label: "🚩 Promoter Pledge Exposure", prompt: "What percentage of fund capital is allocated to companies with elevated promoter pledge levels?" },
            { label: "🔍 Governance Watchlist", prompt: "Identify any holdings with related-party transactions or accounting friction." }
        ],
        holdings: [
            { label: "📊 Dual-Sleeve Allocation", prompt: "Analyze the equity vs debt vs cash allocation and portfolio concentration." },
            { label: "🎯 Top 10 Concentration", prompt: "Evaluate the concentration risk of the top 10 constituent holdings." },
            { label: "🌐 Sector & Asset Distribution", prompt: "Break down the sector allocation and asset weights across the fund." }
        ],
        downside_capture: [
            { label: "🛡️ Bear Market Resilience", prompt: "How does this fund perform during market drawdowns based on its Downside Capture ratio?" },
            { label: "📈 Capture Spread & Alpha", prompt: "Explain the spread between Upside Capture and Downside Capture ratios." },
            { label: "⚖️ Sortino & Momentum", prompt: "Interpret the Sortino ratio and Hurst exponent momentum metric for this fund." }
        ],
        dossier_narrative: [
            { label: "📝 Summarize AI Audit", prompt: "Synthesize the key findings, strengths, and vulnerabilities from the forensic audit narrative." },
            { label: "🚨 Critical Red Flags", prompt: "Highlight any fiduciary concerns or governance warnings identified in the qualitative audit." }
        ],
        lookthrough_metrics: [
            { label: "🔬 7-Pillar Overview", prompt: "Provide an institutional overview of the fund's 7-pillar look-through metrics." },
            { label: "🛡️ Moat vs Solvency Spread", prompt: "Compare the fund's Weighted Moat Index against its Look-Through ASRI accounting risk." }
        ]
    },
    equity: {
        reverse_dcf: [
            { label: "📉 Implied Growth Priced In", prompt: "What implied growth rate is priced into current CMP based on Reverse DCF?" },
            { label: "🎯 Hurdle Rate Sensitivity", prompt: "How sensitive is the Reverse DCF valuation to hurdle rate assumptions?" }
        ],
        solvency: [
            { label: "🛡️ Balance Sheet Solvency", prompt: "Evaluate balance sheet solvency, Altman Z-Score, and leverage ratios." },
            { label: "🚩 Beneish M-Score Check", prompt: "Are there any forensic accounting or earnings manipulation red flags?" }
        ],
        pre_mortem: [
            { label: "💀 Thesis Failure Modes", prompt: "Run Pre-Mortem Inversion analysis on this stock: what failure modes could destroy shareholder value?" },
            { label: "⚠️ Structural Vulnerabilities", prompt: "Identify the top 3 structural risks that could permanently impair business earnings." }
        ]
    },
    debt: {
        covenants: [
            { label: "🛡️ Asset Coverage (ACR)", prompt: "Stress-test the Asset Coverage Ratio (ACR) and DSCR covenant headroom for this instrument." },
            { label: "⚖️ Recovery Seniority Tier", prompt: "Evaluate recovery seniority and investor recourse in a stressed debt restructuring or liquidation." }
        ],
        contagion: [
            { label: "📡 Credit Contagion Radar", prompt: "What does the Credit Contagion Radar say about the parent group and systemic risks for this issuer?" },
            { label: "🚨 Cross-Default Risks", prompt: "Are there any cross-default triggers or related-party exposure in the group structure?" }
        ]
    }
};

function detectAssetType(ticker) {
    const loc = window.location.pathname.toLowerCase();
    if (loc.includes("/funds")) return "mutual_fund";
    if (loc.includes("/debt")) return "debt";
    if (!ticker) return "equity";

    const clean = String(ticker).trim().toUpperCase();
    if (/^\d+$/.test(clean) || clean.endsWith("_DIR") || clean.endsWith("_REG") || clean.includes("FLEXICAP") || clean.includes("MIDCAP") || clean.includes("SMALLCAP") || clean.includes("NIFTY") || clean.includes("FUND") || clean.includes("GROWTH")) {
        return "mutual_fund";
    }
    if (clean.startsWith("IN") || clean.includes("BOND") || clean.includes("SDI") || clean.includes("NCD")) {
        return "debt";
    }
    return "equity";
}

function openCopilot(ticker, assetType, section, sectionLabel, initialPrompt) {
    const prevTicker = activeTicker;
    const prevSection = activeSection;

    activeTicker = ticker ? String(ticker).trim() : "";
    activeAssetType = assetType || detectAssetType(activeTicker);
    activeSection = section || null;
    activeSectionLabel = sectionLabel || "";

    const cfg = COPILOT_CONFIGS[activeAssetType] || COPILOT_CONFIGS.equity;

    // Reset conversation session if switching securities or section
    if (prevTicker !== activeTicker || prevSection !== activeSection || !activeConversationId) {
        activeConversationId = "COPILOT-" + Date.now() + "-" + Math.random().toString(36).substr(2, 6);

        // Reset message container with tailored intro bubble
        const container = document.getElementById("copilotMessages");
        if (container) {
            let introHtml = cfg.introText(activeTicker);
            if (activeSectionLabel) {
                introHtml += `<div style="margin-top: 0.65rem; padding-top: 0.65rem; border-top: 1px solid rgba(255, 255, 255, 0.08); font-size: 0.82rem; color: #38bdf8; display: flex; align-items: center; gap: 0.35rem;">
                    <span>📍</span> <span><strong>Focused Workspace:</strong> ${activeSectionLabel}. Ask any diagnostic question anchored to this section.</span>
                </div>`;
            }
            container.innerHTML = `
                <div id="copilotIntroBubble" style="background: rgba(30, 41, 59, 0.4); border: 1px solid rgba(255, 255, 255, 0.05); border-radius: 8px; padding: 1rem; font-size: 0.88rem; color: #cbd5e1; line-height: 1.5;">
                    ${introHtml}
                </div>
            `;
        }
    }

    // Update Header and Badges
    const headerTitleEl = document.getElementById("copilotHeaderTitle");
    if (headerTitleEl) headerTitleEl.textContent = cfg.headerTitle;

    const assetBadgeEl = document.getElementById("copilotAssetBadge");
    if (assetBadgeEl) assetBadgeEl.textContent = cfg.assetBadge;

    const sectionBadgeEl = document.getElementById("copilotSectionBadge");
    if (sectionBadgeEl) {
        if (activeSectionLabel) {
            sectionBadgeEl.textContent = `📍 ${activeSectionLabel}`;
            sectionBadgeEl.style.display = "inline-flex";
        } else {
            sectionBadgeEl.style.display = "none";
        }
    }

    const tickerSpan = document.getElementById("copilotContextTicker");
    if (tickerSpan) tickerSpan.textContent = activeTicker || "Universal";

    // Populate Quick Prompt Chips (contextually anchored to active section)
    const chipsContainer = document.getElementById("copilotQuickChips");
    if (chipsContainer) {
        let chipsToRender = [];
        if (activeSection && SECTION_CHIPS[activeAssetType] && SECTION_CHIPS[activeAssetType][activeSection]) {
            chipsToRender = SECTION_CHIPS[activeAssetType][activeSection];
        } else {
            chipsToRender = cfg.chips || [];
        }

        chipsContainer.innerHTML = chipsToRender.map(chip => `
            <button onclick="sendQuickPrompt(${JSON.stringify(chip.prompt)})" style="white-space: nowrap; font-size: 0.75rem; background: #1e293b; color: #38bdf8; border: 1px solid #334155; padding: 0.35rem 0.65rem; border-radius: 9999px; cursor: pointer; transition: background 0.15s ease;">
                ${chip.label}
            </button>
        `).join("");
    }

    const modal = document.getElementById("copilotModalBackdrop");
    if (modal) {
        modal.style.display = "flex";
    }

    const input = document.getElementById("copilotInput");
    if (input) {
        if (initialPrompt) {
            input.value = initialPrompt;
        }
        input.focus();
    }
}

function closeCopilot() {
    const modal = document.getElementById("copilotModalBackdrop");
    if (modal) {
        modal.style.display = "none";
    }
}

function sendQuickPrompt(promptText) {
    const input = document.getElementById("copilotInput");
    if (input) {
        input.value = promptText;
        submitCopilotMessage();
    }
}

async function submitCopilotMessage() {
    const input = document.getElementById("copilotInput");
    const sendBtn = document.getElementById("copilotSendBtn");
    const container = document.getElementById("copilotMessages");

    if (!input || !input.value.trim()) return;
    const userMsg = input.value.trim();
    input.value = "";

    // Append user message to stream
    const userBubble = document.createElement("div");
    userBubble.style.cssText = "align-self: flex-end; max-width: 85%; background: #0284c7; color: #f8fafc; padding: 0.75rem 1rem; border-radius: 8px 8px 2px 8px; font-size: 0.88rem; line-height: 1.4;";
    userBubble.textContent = userMsg;
    container.appendChild(userBubble);
    container.scrollTop = container.scrollHeight;

    // Append thinking bubble
    const thinkingBubble = document.createElement("div");
    thinkingBubble.style.cssText = "align-self: flex-start; max-width: 85%; background: rgba(30, 41, 59, 0.6); color: #94a3b8; padding: 0.75rem 1rem; border-radius: 8px 8px 8px 2px; font-size: 0.85rem; font-style: italic;";
    const thinkingLabel = activeAssetType === "mutual_fund" 
        ? "🧠 Copilot is evaluating fund portfolio forensics & look-through data..." 
        : (activeAssetType === "debt" 
            ? "🧠 Copilot is stress-testing capital hierarchy & credit contagion..." 
            : "🧠 Copilot is evaluating filings & stress-testing thesis...");
    thinkingBubble.textContent = thinkingLabel;
    container.appendChild(thinkingBubble);
    container.scrollTop = container.scrollHeight;

    sendBtn.disabled = true;
    input.disabled = true;

    try {
        const resp = await fetch("/api/copilot/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                conversation_id: activeConversationId,
                message: userMsg,
                ticker: activeTicker,
                asset_type: activeAssetType,
                section: activeSection,
                section_label: activeSectionLabel
            })
        });
        const data = await resp.json();
        thinkingBubble.remove();

        const agentBubble = document.createElement("div");
        agentBubble.style.cssText = "align-self: flex-start; max-width: 90%; background: #1e293b; border: 1px solid rgba(255,255,255,0.08); color: #f8fafc; padding: 0.85rem 1.15rem; border-radius: 8px 8px 8px 2px; font-size: 0.88rem; line-height: 1.5; white-space: pre-wrap;";
        agentBubble.textContent = data.response || "No response generated.";
        container.appendChild(agentBubble);
        container.scrollTop = container.scrollHeight;
    } catch (e) {
        thinkingBubble.textContent = "⚠️ Failed to communicate with Copilot API: " + e;
    } finally {
        sendBtn.disabled = false;
        input.disabled = false;
        input.focus();
    }
}

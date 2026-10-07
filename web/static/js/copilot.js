/**
 * Institutional Investor Copilot Frontend Controller.
 * Powered by Google Antigravity SDK.
 * Supports Multi-Asset Dispatch across Fundamental Equities, Mutual Funds, and Corporate Debt.
 */

let activeConversationId = null;
let activeTicker = "";
let activeAssetType = "equity";

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
        introText: (ticker) => `Welcome to the <strong>Fund Look-Through Copilot</strong>. I can evaluate constituent moat & quality scores, uncover hidden promoter pledge exposure, audit active share vs benchmark, and flag <strong>style drift or high-risk holdings</strong> for <strong>${ticker || 'this scheme'}</strong>.`,
        chips: [
            { label: "🛡️ Moat & Quality Score", prompt: "Evaluate the constituent moat distribution and overall portfolio quality for this fund." },
            { label: "⚠️ High-Risk Holdings", prompt: "Which underlying constituent holdings carry the highest accounting risk or lowest health score?" },
            { label: "🧭 Style Drift & Active Share", prompt: "Audit the active share and check if this fund is exhibiting benchmark hugging or style drift." }
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

function detectAssetType(ticker) {
    if (!ticker) return "equity";
    const clean = String(ticker).trim().toUpperCase();
    if (/^\d+$/.test(clean)) return "mutual_fund";
    if (clean.startsWith("IN") || clean.includes("BOND") || clean.includes("SDI") || clean.includes("NCD")) return "debt";
    return "equity";
}

function openCopilot(ticker, assetType) {
    const prevTicker = activeTicker;
    activeTicker = ticker ? String(ticker).trim() : "";
    activeAssetType = assetType || detectAssetType(activeTicker);

    const cfg = COPILOT_CONFIGS[activeAssetType] || COPILOT_CONFIGS.equity;

    // Reset conversation session if switching securities
    if (prevTicker !== activeTicker || !activeConversationId) {
        activeConversationId = "COPILOT-" + Date.now() + "-" + Math.random().toString(36).substr(2, 6);
        
        // Reset message container with tailored intro bubble
        const container = document.getElementById("copilotMessages");
        if (container) {
            container.innerHTML = `
                <div id="copilotIntroBubble" style="background: rgba(30, 41, 59, 0.4); border: 1px solid rgba(255, 255, 255, 0.05); border-radius: 8px; padding: 1rem; font-size: 0.88rem; color: #cbd5e1; line-height: 1.5;">
                    ${cfg.introText(activeTicker)}
                </div>
            `;
        }
    }

    // Update Header and Badges
    const headerTitleEl = document.getElementById("copilotHeaderTitle");
    if (headerTitleEl) headerTitleEl.textContent = cfg.headerTitle;

    const assetBadgeEl = document.getElementById("copilotAssetBadge");
    if (assetBadgeEl) assetBadgeEl.textContent = cfg.assetBadge;

    const tickerSpan = document.getElementById("copilotContextTicker");
    if (tickerSpan) tickerSpan.textContent = activeTicker || "Universal";

    // Populate Quick Prompt Chips
    const chipsContainer = document.getElementById("copilotQuickChips");
    if (chipsContainer) {
        chipsContainer.innerHTML = cfg.chips.map(chip => `
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
    if (input) input.focus();
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
    thinkingBubble.textContent = "🧠 Copilot is evaluating filings & stress-testing thesis...";
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
                ticker: activeTicker
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

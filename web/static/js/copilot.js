/**
 * Forensic Intelligence Desk Frontend Controller (v2.0).
 * Institutional Forensic Intelligence Architecture.
 * Supports Multi-Asset Dispatch across Fundamental Equities, Mutual Funds, and Corporate Debt,
 * with Deep Section Contextual Awareness, Smooth Slide-In Transitions, and SEBI Safe Harbor Guardrails.
 */

let activeConversationId = null;
let activeTicker = "";
let activeAssetType = "equity";
let activeSection = null;
let activeSectionLabel = "";

const COPILOT_CONFIGS = {
    equity: {
        headerTitle: "Forensic Intelligence Desk",
        assetBadge: "Fundamental Equity Intelligence",
        introText: (ticker) => `Welcome to the <strong>Forensic Intelligence Desk</strong>. I can assist in stress-testing your investment thesis on <strong>${ticker || 'the selected equity'}</strong>, deriving implied growth rates via Reverse DCF, or running a <strong>Pre-Mortem Inversion analysis</strong>.`,
        features: [
            { icon: "💀", title: "Pre-Mortem Inversion", desc: "Expose failure modes & thesis destruction risks", prompt: "Run Pre-Mortem Inversion analysis on this stock: what failure modes could destroy shareholder value?" },
            { icon: "📉", title: "Reverse DCF Growth", desc: "Deconstruct implied growth priced into current CMP", prompt: "What implied growth rate is priced into current CMP based on Reverse DCF?" },
            { icon: "🚩", title: "Governance Forensic", desc: "Audit promoter pledging & related-party transactions", prompt: "Are there any promoter pledging or corporate governance red flags in recent disclosures?" }
        ],
        chips: [
            { label: "💀 Pre-Mortem Inversion", prompt: "Run Pre-Mortem Inversion analysis on this stock: what failure modes could destroy shareholder value?" },
            { label: "📉 Reverse DCF Implied Growth", prompt: "What implied growth rate is priced into current CMP based on Reverse DCF?" },
            { label: "🚩 Governance & Pledging Check", prompt: "Are there any promoter pledging or corporate governance red flags in recent disclosures?" },
            { label: "🛡️ Balance Sheet Solvency", prompt: "Evaluate balance sheet solvency, Altman Z-Score, and leverage ratios for this company." }
        ]
    },
    mutual_fund: {
        headerTitle: "Fund Look-Through Intelligence Desk",
        assetBadge: "Mutual Fund Intelligence",
        introText: (ticker) => `Welcome to the <strong>Fund Look-Through Intelligence Desk</strong>. I evaluate underlying constituent quality, weighted moat endurance, look-through ASRI accounting stress, active share vs benchmark, and <strong>direct vs regular intermediary fee drag</strong> for <strong>${ticker || 'this scheme'}</strong>.`,
        features: [
            { icon: "🏰", title: "Weighted Moat Index", desc: "Constituent economic moat distribution & quality", prompt: "Evaluate the constituent moat distribution and overall portfolio quality for this fund." },
            { icon: "💸", title: "Intermediary Fee Drag", desc: "20-yr compounded wealth lost to distributor commissions", prompt: "What is the 20-year compounded fee drag and wealth lost to distributor commissions for this fund?" },
            { icon: "🧭", title: "Active Share & Style Drift", desc: "Audit closet indexing and benchmark hugging", prompt: "Audit the active share and check if this fund is exhibiting benchmark hugging or style drift." }
        ],
        chips: [
            { label: "🛡️ Moat & Quality Score", prompt: "Evaluate the constituent moat distribution and overall portfolio quality for this fund." },
            { label: "⚠️ High-Risk Holdings", prompt: "Which underlying constituent holdings carry the highest accounting risk or lowest health score?" },
            { label: "🧭 Style Drift & Active Share", prompt: "Audit the active share and check if this fund is exhibiting benchmark hugging or style drift." },
            { label: "💸 Intermediary Fee Drag", prompt: "What is the 20-year compounded fee drag and wealth lost to distributor commissions for this fund?" }
        ]
    },
    debt: {
        headerTitle: "Credit & Solvency Intelligence Desk",
        assetBadge: "Fixed Income & SDI Solvency",
        introText: (ticker) => `Welcome to the <strong>Credit & Solvency Intelligence Desk</strong>. I can stress-test Asset Coverage Ratios (ACR), recovery seniority in liquidation, DSCR covenant headroom, and <strong>credit contagion risk</strong> for <strong>${ticker || 'this security'}</strong>.`,
        features: [
            { icon: "🛡️", title: "Asset Coverage & Covenants", desc: "Stress-test ACR and DSCR covenant headroom", prompt: "Stress-test the Asset Coverage Ratio (ACR) and DSCR covenant headroom for this instrument." },
            { icon: "⚖️", title: "Recovery Seniority Tier", desc: "Evaluate recovery seniority & liquidation hierarchy", prompt: "Evaluate recovery seniority and investor recourse in a stressed debt restructuring or liquidation." },
            { icon: "📡", title: "Credit Contagion Radar", desc: "Analyze parent group linkages and contagion risk", prompt: "What does the Credit Contagion Radar say about the parent group and systemic risks for this issuer?" }
        ],
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

/**
 * Lightweight, safe markdown formatter for forensic copilot analysis responses.
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

    return finalBlocks.join("\n");
}

function formatCurrentTime() {
    const now = new Date();
    return now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function renderIntroWelcomeCard(cfg, ticker, sectionLabel) {
    let html = `
        <div class="copilot-intro-headline">
          <span>🧠</span> ${cfg.headerTitle}
        </div>
        <div>
          ${cfg.introText(ticker)}
        </div>
    `;

    if (sectionLabel) {
        html += `
            <div style="margin-top: 10px; padding: 8px 12px; background: rgba(168, 85, 247, 0.12); border: 1px solid rgba(168, 85, 247, 0.35); border-radius: 8px; font-size: 0.8rem; color: #d8b4fe; display: flex; align-items: center; gap: 6px;">
                <span>📍</span> <span><strong>Focused Workspace:</strong> ${sectionLabel}. All responses are calibrated to this section.</span>
            </div>
        `;
    }

    if (cfg.features && cfg.features.length) {
        html += `<div class="copilot-intro-features">`;
        cfg.features.forEach(f => {
            html += `
                <div class="copilot-intro-feature-item" data-copilot-prompt="${encodeURIComponent(f.prompt)}" role="button" tabindex="0">
                    <span style="font-size: 1.1rem; pointer-events: none;">${f.icon}</span>
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

    // Reset conversation session if switching securities or section
    if (prevTicker !== activeTicker || prevSection !== activeSection || !activeConversationId) {
        activeConversationId = "COPILOT-" + Date.now() + "-" + Math.random().toString(36).substr(2, 6);

        // Reset message container with styled intro card
        const container = document.getElementById("copilotMessages");
        if (container) {
            container.innerHTML = `
                <div id="copilotIntroBubble" class="copilot-intro-card">
                    ${renderIntroWelcomeCard(cfg, activeTicker, activeSectionLabel)}
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
                ${chip.label}
            </button>
        `).join("");
    }

    // Show modal with smooth class-based slide animation
    const modal = document.getElementById("copilotModalBackdrop");
    if (modal) {
        modal.style.display = "flex";
        // Force reflow for smooth CSS transition
        void modal.offsetWidth;
        modal.classList.add("copilot-open");
    }

    // Prepare and focus input
    const input = document.getElementById("copilotInput");
    if (input) {
        if (initialPrompt) {
            input.value = initialPrompt;
        }
        handleCopilotInput(input);
        setTimeout(() => input.focus(), 100);
    }
}

function closeCopilot() {
    const modal = document.getElementById("copilotModalBackdrop");
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
    if (container) {
        container.innerHTML = `
            <div id="copilotIntroBubble" class="copilot-intro-card">
                ${renderIntroWelcomeCard(cfg, activeTicker, activeSectionLabel)}
            </div>
        `;
    }
    const input = document.getElementById("copilotInput");
    if (input) {
        input.value = "";
        handleCopilotInput(input);
        input.focus();
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
        btn.innerHTML = `✓ Copied`;
        btn.style.color = "#38bdf8";
        setTimeout(() => {
            btn.innerHTML = origText;
            btn.style.color = "";
        }, 2000);
    }).catch(err => {
        console.warn("Failed to copy copilot text:", err);
    });
}

async function submitCopilotMessage() {
    const input = document.getElementById("copilotInput");
    const sendBtn = document.getElementById("copilotSendBtn");
    const container = document.getElementById("copilotMessages");

    if (!input || !input.value.trim()) return;
    const userMsg = input.value.trim();
    input.value = "";
    handleCopilotInput(input);

    const currentTime = formatCurrentTime();

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
    container.scrollTop = container.scrollHeight;

    // Append animated thinking wave indicator
    const thinkingCard = document.createElement("div");
    thinkingCard.className = "copilot-thinking-card";
    
    let thinkingLabel = "Evaluating disclosures & stress-testing thesis...";
    if (activeAssetType === "mutual_fund") {
        thinkingLabel = "Evaluating look-through constituents & fee drag...";
    } else if (activeAssetType === "debt") {
        thinkingLabel = "Stress-testing capital hierarchy & credit contagion...";
    }

    thinkingCard.innerHTML = `
        <div class="copilot-thinking-row">
            <div class="copilot-typing-dots">
                <span class="copilot-typing-dot"></span>
                <span class="copilot-typing-dot"></span>
                <span class="copilot-typing-dot"></span>
            </div>
            <span class="copilot-thinking-text">${thinkingLabel}</span>
        </div>
    `;
    container.appendChild(thinkingCard);
    container.scrollTop = container.scrollHeight;

    sendBtn.disabled = true;
    sendBtn.classList.remove("active");
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
        thinkingCard.remove();

        const agentText = data.response || "No response generated.";
        const formattedHtml = renderCopilotMarkdown(agentText);
        const agentTime = formatCurrentTime();

        const agentTurn = document.createElement("div");
        agentTurn.className = "copilot-turn copilot-turn-agent";
        
        // Escape raw text for safe passing into copy handler via data attribute
        const encodedRaw = encodeURIComponent(agentText);

        agentTurn.innerHTML = `
            <div class="copilot-bubble-agent">
                <div class="copilot-bubble-header">
                    <div class="copilot-bubble-header-left">
                        <svg class="glyph" style="width: 12px; height: 12px;"><use href="#glyph-shield"></use></svg>
                        <span>Forensic AI Copilot</span>
                    </div>
                    <button type="button" class="copilot-copy-btn" data-copilot-copy="${encodedRaw}" title="Copy analysis to clipboard">
                        📋 Copy
                    </button>
                </div>
                <div class="copilot-bubble-body">
                    ${formattedHtml}
                </div>
            </div>
            <div class="copilot-turn-meta">Institutional Forensic Engine • ${agentTime}</div>
        `;
        container.appendChild(agentTurn);
        container.scrollTop = container.scrollHeight;
    } catch (e) {
        thinkingCard.remove();
        const errTurn = document.createElement("div");
        errTurn.className = "copilot-turn copilot-turn-agent";
        errTurn.innerHTML = `
            <div class="copilot-bubble-agent" style="border-color: rgba(239, 68, 68, 0.4); background: rgba(239, 68, 68, 0.08);">
                <div style="color: #f87171; font-weight: 700; margin-bottom: 4px;">⚠️ Copilot Communication Notice</div>
                <div style="color: #fca5a5; font-size: 0.82rem;">Failed to communicate with Copilot API: ${String(e)}</div>
            </div>
        `;
        container.appendChild(errTurn);
        container.scrollTop = container.scrollHeight;
    } finally {
        input.disabled = false;
        handleCopilotInput(input);
        input.focus();
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

function toggleForensicDesk() {
    const modal = document.getElementById("copilotModalBackdrop");
    if (modal && (modal.classList.contains("copilot-open") || modal.style.display === "flex")) {
        closeCopilot();
    } else {
        const ticker = activeTicker || window.__CURRENT_TICKER || "";
        const assetType = activeAssetType || window.__CURRENT_ASSET_TYPE || "equity";
        openCopilot(ticker, assetType);
    }
}

// Global shortcut listener: ⌘K or Ctrl+K or / (when not typing in an input)
document.addEventListener("keydown", function(e) {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        toggleForensicDesk();
    } else if (e.key === "/" && !["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName)) {
        e.preventDefault();
        toggleForensicDesk();
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
window.openForensicDesk = openCopilot;
window.closeForensicDesk = closeCopilot;
window.toggleForensicDesk = toggleForensicDesk;
window.resetCopilotChat = resetCopilotChat;
window.handleCopilotBackdropClick = handleCopilotBackdropClick;
window.handleCopilotInput = handleCopilotInput;
window.handleCopilotKeydown = handleCopilotKeydown;
window.sendQuickPrompt = sendQuickPrompt;
window.copyCopilotTurn = copyCopilotTurn;
window.submitCopilotMessage = submitCopilotMessage;



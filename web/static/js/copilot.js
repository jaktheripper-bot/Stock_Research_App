/**
 * Institutional Investor Copilot Frontend Controller.
 * Powered by Google Antigravity SDK.
 */

let activeConversationId = null;
let activeTicker = "";

function openCopilot(ticker) {
    activeTicker = ticker || "";
    if (!activeConversationId) {
        activeConversationId = "COPILOT-" + Date.now() + "-" + Math.random().toString(36).substr(2, 6);
    }
    const tickerSpan = document.getElementById("copilotContextTicker");
    if (tickerSpan) {
        tickerSpan.textContent = activeTicker || "Universal";
    }
    const modal = document.getElementById("copilotModalBackdrop");
    if (modal) {
        modal.style.display = "flex";
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

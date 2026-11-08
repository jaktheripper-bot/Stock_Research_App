/**
 * Durable Paid Mutual Fund Audit Request Helper.
 * Provides account-scoped idempotent request recovery, cross-device job discovery,
 * accessible quote-confirmation modal (hoisted to document.body with inert siblings),
 * and itemised settlement receipts.
 */
const pendingFundAuditRequests = new Map();

function _activeAuditAccountScope() {
  try {
    const raw = localStorage.getItem("sr_user");
    if (raw) {
      const parsed = JSON.parse(raw);
      if (parsed && parsed.id) return String(parsed.id).trim();
    }
  } catch {
    // Fall back to session scope when localStorage is unavailable.
  }
  return "session";
}

function buildFundAuditStorageKey(schemeCode, allowDeepDive) {
  return `fund-audit:${_activeAuditAccountScope()}:${String(schemeCode || "").toUpperCase()}:${Number(Boolean(allowDeepDive))}`;
}

function readPendingFundAudit(key) {
  try {
    const stored = sessionStorage.getItem(key);
    return stored ? JSON.parse(stored) : pendingFundAuditRequests.get(key);
  } catch {
    return pendingFundAuditRequests.get(key);
  }
}

function rememberPendingFundAudit(key, pending) {
  pendingFundAuditRequests.set(key, pending);
  try {
    sessionStorage.setItem(key, JSON.stringify(pending));
  } catch {
    // In-page map protects retries when sessionStorage is restricted.
  }
}

function clearPendingFundAudit(key) {
  pendingFundAuditRequests.delete(key);
  try {
    sessionStorage.removeItem(key);
  } catch {
    // Browser storage unavailable.
  }
}

function clearAllPendingFundAudits() {
  pendingFundAuditRequests.clear();
  try {
    const toRemove = [];
    for (let i = 0; i < sessionStorage.length; i += 1) {
      const k = sessionStorage.key(i);
      if (k && k.startsWith("fund-audit:")) toRemove.push(k);
    }
    toRemove.forEach((k) => sessionStorage.removeItem(k));
  } catch {
    // Ignore storage cleanup errors in restricted browsing modes.
  }
}

if (typeof window !== "undefined" && typeof window.addEventListener === "function") {
  window.addEventListener("moat:auth-logout", clearAllPendingFundAudits);
}

function confirmFundAuditQuoteModal(quote, allowDeepDive, displayedCredits) {
  if (typeof document === "undefined" || !document.body) {
    const credits = quote.credits_due;
    const changed = displayedCredits !== null && displayedCredits !== credits ? "The credit quote has changed. " : "";
    const prompt = `${changed}Portfolio disclosure ${quote.portfolio_as_on}. Authorize ${credits} credit${credits === 1 ? "" : "s"} for this audit?`;
    return Promise.resolve(typeof window !== "undefined" && typeof window.confirm === "function" ? window.confirm(prompt) : true);
  }

  return new Promise((resolve) => {
    const triggerEl = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const credits = Number(quote.credits_due || 0);
    const layer1 = Number(quote.layer1_credits || 0);
    const layer2 = Number(quote.layer2_deep_dive_credits || 0);
    const balance = typeof quote.credits_balance === "number" ? quote.credits_balance : null;
    const excludedForeign = Number(quote.excluded_foreign_count || 0);
    const quoteChanged = displayedCredits !== null && Number(displayedCredits) !== credits;

    const existing = document.getElementById("fundAuditConfirmBackdrop");
    if (existing) existing.remove();

    const backdrop = document.createElement("div");
    backdrop.id = "fundAuditConfirmBackdrop";
    backdrop.className = "modal-backdrop active";
    backdrop.style.cssText = "position:fixed;inset:0;z-index:10050;background:rgba(2,6,23,0.78);display:flex;align-items:center;justify-content:center;padding:16px;";

    const dialog = document.createElement("div");
    dialog.id = "fundAuditConfirmDialog";
    dialog.className = "modal-dialog";
    dialog.setAttribute("role", "dialog");
    dialog.setAttribute("aria-modal", "true");
    dialog.setAttribute("aria-labelledby", "fundAuditConfirmTitle");
    dialog.setAttribute("aria-describedby", "fundAuditConfirmDesc");
    dialog.style.cssText = "max-width:480px;width:100%;background:#0f172a;color:#f8fafc;border:1px solid rgba(148,163,184,0.28);border-radius:16px;padding:24px;box-shadow:0 24px 48px rgba(0,0,0,0.45);";

    const title = document.createElement("h2");
    title.id = "fundAuditConfirmTitle";
    title.style.cssText = "margin:0 0 8px 0;font-size:20px;font-weight:800;color:#f8fafc;";
    title.textContent = "Confirm Mutual Fund Audit Quote";

    const desc = document.createElement("div");
    desc.id = "fundAuditConfirmDesc";
    desc.style.cssText = "font-size:14px;line-height:1.55;color:#cbd5e1;margin-bottom:16px;";

    if (quoteChanged) {
      const changedBanner = document.createElement("p");
      changedBanner.style.cssText = "margin:0 0 10px 0;padding:8px 12px;border-radius:8px;background:rgba(245,158,11,0.16);border:1px solid rgba(245,158,11,0.35);color:#fcd34d;font-weight:600;";
      changedBanner.textContent = `Updated credit quote: ${credits} credit${credits === 1 ? "" : "s"} (previously displayed ${displayedCredits}).`;
      desc.appendChild(changedBanner);
    }

    const summaryList = document.createElement("ul");
    summaryList.style.cssText = "margin:0 0 12px 0;padding-left:18px;display:flex;flex-direction:column;gap:6px;";
    const lines = [
      `Scheme: ${quote.scheme_code} (Disclosure as of ${quote.portfolio_as_on})`,
      `Layer-1 Fund Look-Through Unlock: ${layer1} credit${layer1 === 1 ? "" : "s"}`,
    ];
    if (allowDeepDive) {
      lines.push(`Layer-2 Domestic Constituent Synthesis: ${layer2} credit${layer2 === 1 ? "" : "s"}`);
    }
    if (excludedForeign > 0) {
      lines.push(`Foreign equity holdings excluded from domestic billing: ${excludedForeign}`);
    }
    lines.push(`Total reserved now: ${credits} credit${credits === 1 ? "" : "s"}${balance !== null ? ` (Available balance: ${balance.toFixed(1)})` : ""}`);
    lines.forEach((txt) => {
      const li = document.createElement("li");
      li.textContent = txt;
      summaryList.appendChild(li);
    });
    desc.appendChild(summaryList);

    const guarantee = document.createElement("p");
    guarantee.style.cssText = "margin:0;font-size:13px;color:#94a3b8;";
    guarantee.textContent = "Any constituent or dossier line item that is already eligible or cannot be delivered within the SLA is automatically refunded.";
    desc.appendChild(guarantee);

    const actions = document.createElement("div");
    actions.style.cssText = "display:flex;justify-content:flex-end;gap:10px;margin-top:18px;flex-wrap:wrap;";

    const cancelBtn = document.createElement("button");
    cancelBtn.type = "button";
    cancelBtn.className = "btn btn-secondary";
    cancelBtn.style.cssText = "font-size:16px;padding:9px 16px;border-radius:8px;cursor:pointer;";
    cancelBtn.textContent = "Cancel";

    const confirmBtn = document.createElement("button");
    confirmBtn.type = "button";
    confirmBtn.className = "btn btn-primary";
    confirmBtn.style.cssText = "font-size:16px;padding:9px 18px;border-radius:8px;font-weight:700;cursor:pointer;";
    confirmBtn.textContent = `Authorize ${credits} Credit${credits === 1 ? "" : "s"}`;

    actions.append(cancelBtn, confirmBtn);
    dialog.append(title, desc, actions);
    backdrop.appendChild(dialog);
    document.body.appendChild(backdrop);

    const siblingStates = [];
    Array.from(document.body.children).forEach((child) => {
      if (child !== backdrop && child instanceof HTMLElement) {
        siblingStates.push([child, Boolean(child.inert)]);
        child.inert = true;
      }
    });

    let settled = false;
    function finish(accepted) {
      if (settled) return;
      settled = true;
      document.removeEventListener("keydown", onKeyDown);
      siblingStates.forEach(([el, prevInert]) => {
        el.inert = prevInert;
      });
      backdrop.remove();
      if (triggerEl && typeof triggerEl.focus === "function") {
        triggerEl.focus({ preventScroll: true });
      }
      resolve(accepted);
    }

    function onKeyDown(ev) {
      if (ev.key === "Escape") {
        ev.preventDefault();
        finish(false);
      }
    }

    document.addEventListener("keydown", onKeyDown);
    cancelBtn.addEventListener("click", () => finish(false));
    confirmBtn.addEventListener("click", () => finish(true));
    backdrop.addEventListener("click", (ev) => {
      if (ev.target === backdrop) finish(false);
    });

    confirmBtn.focus({ preventScroll: true });
  });
}

async function submitFundAudit(schemeCode, allowDeepDive, displayedCredits = null) {
  const key = buildFundAuditStorageKey(schemeCode, allowDeepDive);
  let pending = readPendingFundAudit(key);
  if (!pending) {
    const url = `/api/funds/deep-dive-quote/${encodeURIComponent(schemeCode)}?allow_deep_dive=${Boolean(allowDeepDive)}`;
    const response = await fetch(url, { cache: "no-store" });
    const quote = await response.json();
    if (!response.ok) return { res: response, data: quote, key, canceled: false };

    if (!quote.is_admin) {
      if (allowDeepDive && quote.deep_dive_available === false) {
        return {
          res: new Response(null, { status: 422 }),
          data: { detail: quote.deep_dive_unavailable_reason || "Deep-dive synthesis exceeds single-job SLA bounds." },
          key,
          canceled: false,
        };
      }
      const accepted = await confirmFundAuditQuoteModal(quote, Boolean(allowDeepDive), displayedCredits);
      if (!accepted) {
        return { res: null, data: { canceled: true }, key, canceled: true };
      }
    }
    const reqId = (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function")
      ? crypto.randomUUID()
      : `req-${Date.now()}-${Math.random().toString(16).slice(2, 12)}`;
    pending = {
      requestId: reqId,
      payload: {
        scheme_code: schemeCode,
        allow_deep_dive: Boolean(allowDeepDive),
        quote_revision: quote.quote_revision,
      },
    };
    rememberPendingFundAudit(key, pending);
  }

  const res = await fetch("/api/funds/on-demand-audit", {
    method: "POST",
    headers: { "Content-Type": "application/json", "Idempotency-Key": pending.requestId },
    body: JSON.stringify(pending.payload),
  });
  const data = await res.json();
  if ([400, 402, 404, 409, 422].includes(res.status)) clearPendingFundAudit(key);
  return { res, data, key, canceled: false };
}

async function findActiveOwnerFundAudit(schemeCode) {
  try {
    const qs = schemeCode ? `scheme_code=${encodeURIComponent(schemeCode)}&limit=5` : "limit=10";
    const res = await fetch(`/api/funds/my-audits?${qs}`, { cache: "no-store" });
    if (!res.ok) return null;
    const body = await res.json();
    const audits = Array.isArray(body.items) ? body.items : (Array.isArray(body.audits) ? body.audits : []);
    return audits.find((a) => a.status === "QUEUED" || a.status === "PROCESSING") || null;
  } catch {
    return null;
  }
}

function showFundAuditSettlement(element, task) {
  if (!element || !task.audit_settlement) return;
  const { credits_charged: charged, credits_refunded: refunded, items } = task.audit_settlement;
  const summary = document.createElement("p");
  summary.textContent = `Credits reserved: ${charged}. Refunded: ${refunded}. Retained: ${charged - refunded}.`;
  const list = document.createElement("ul");
  for (const item of items) {
    const line = document.createElement("li");
    line.textContent = `${item.layer === 1 ? "Fund dossier" : item.ticker}: ${item.status.toLowerCase()}`;
    list.appendChild(line);
  }
  element.append(summary, list);
  if (task.dossier_revision) {
    const link = document.createElement("a");
    link.href = `/api/funds/audit-status/${encodeURIComponent(task.task_id)}?include_dossier=true`;
    link.textContent = "View this audit's saved revision";
    element.appendChild(link);
  }
}

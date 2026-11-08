/**
 * Opportunity Terminal Client Controller.
 * Renders cards, the debt matrix, a table, and the persistent comparison tray.
 */

let allOpportunities = [];
let heatmapData = null;
let currentView = 'cards';
let currentPersona = '';
let currentSearch = '';
let pinnedIds = [];
let arbitrageInvokerEl = null;
let arbitrageInertRestores = [];

// Initialize state on DOM load
document.addEventListener('DOMContentLoaded', () => {
  try {
    const saved = localStorage.getItem('arbitrage_docket_ids');
    if (saved) {
      pinnedIds = JSON.parse(saved);
    }
  } catch (e) {
    pinnedIds = [];
  }

  // Keyboard shortcut listener for 1, 2, 3, 4 and Escape modal dismissal
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      const modal = document.getElementById('arbitrageModal');
      if (modal && modal.style.display === 'block') {
        e.preventDefault();
        closeArbitrageModal();
        return;
      }
    }
    if (e.target && (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT' || e.target.tagName === 'TEXTAREA')) {
      return;
    }
    if (e.key === '1') switchView('cards');
    else if (e.key === '2') switchView('heatmap');
    else if (e.key === '3' || e.key === '4') switchView('table');
  });

  loadUniverse();
  loadHeatmap();
  updateDocketUI();
});

// Fetch normalized opportunities
async function loadUniverse() {
  try {
    const url = `/api/v2/opportunities/universe?persona=${encodeURIComponent(currentPersona)}`;
    const res = await fetch(url);
    const data = await res.json();
    allOpportunities = data.items || [];

    // Update summary metrics if present
    const totalEl = document.getElementById('kpiTotalItems');
    if (totalEl) totalEl.textContent = `${allOpportunities.length} Offerings`;
    const coverageEl = document.getElementById('terminalMetricCoverage');
    const available = allOpportunities.filter(item => item.metric_status === 'available').length;
    if (coverageEl) coverageEl.textContent = `${available} with current source-dated measures`;

    renderActiveView();
    updateDocketUI();
  } catch (err) {
    console.error('Failed to load opportunities universe:', err);
  }
}

// Fetch heatmap data
async function loadHeatmap() {
  try {
    const res = await fetch(`/api/v2/opportunities/heatmap`);
    heatmapData = await res.json();
    if (currentView === 'heatmap') {
      renderHeatmap();
    }
  } catch (err) {
    console.error('Failed to load heatmap:', err);
  }
}

// Switch the active view
function switchView(viewName) {
  currentView = viewName;

  // Update button active styling
  const viewBtns = {
    cards: document.getElementById('viewBtnCards'),
    heatmap: document.getElementById('viewBtnHeatmap'),
    table: document.getElementById('viewBtnTable')
  };

  Object.keys(viewBtns).forEach((k) => {
    const btn = viewBtns[k];
    if (btn) {
      if (k === viewName) {
        btn.classList.remove('btn-secondary');
        btn.classList.add('btn-primary');
      } else {
        btn.classList.remove('btn-primary');
        btn.classList.add('btn-secondary');
      }
    }
  });

  // Toggle container visibility
  const panels = {
    cards: document.getElementById('viewBentoContainer'),
    heatmap: document.getElementById('viewHeatmapContainer'),
    table: document.getElementById('viewTableContainer')
  };

  Object.keys(panels).forEach((k) => {
    const p = panels[k];
    if (p) p.style.display = (k === viewName) ? 'block' : 'none';
  });

  renderActiveView();
}

function renderActiveView() {
  const filtered = getFilteredItems();
  if (currentView === 'cards') {
    renderBentoCards(filtered);
  } else if (currentView === 'heatmap') {
    renderHeatmap();
  } else if (currentView === 'table') {
    renderDenseTable(filtered);
  }
}

function getFilteredItems() {
  let list = allOpportunities;
  if (currentSearch.trim()) {
    const q = currentSearch.toLowerCase();
    list = list.filter(x =>
      (x.symbol && x.symbol.toLowerCase().includes(q)) ||
      (x.name && x.name.toLowerCase().includes(q)) ||
      (x.credit_rating && x.credit_rating.toLowerCase().includes(q)) ||
      (x.category_label && x.category_label.toLowerCase().includes(q)) ||
      (x.asset_class && x.asset_class.toLowerCase().includes(q))
    );
  }
  return list;
}

const METRIC_LABELS = {
  CONTRACTUAL_YTM: 'Quoted yield to maturity',
  AUCTION_CUTOFF_YIELD: 'Auction cut-off yield',
  DISTRIBUTION_YIELD_TTM: 'Trailing distribution yield',
  HISTORICAL_CAGR_3Y: 'Historical 3-year CAGR',
  EARNINGS_YIELD_TTM: 'Trailing earnings yield',
  DIVIDEND_YIELD_TTM: 'Trailing dividend yield'
};

function metricLabel(item) {
  return METRIC_LABELS[item.yield_type] || 'Measure unavailable';
}

function ticketValue(item) {
  return Number.isFinite(item.min_ticket_inr)
    ? `₹${item.min_ticket_inr.toLocaleString('en-IN')}`
    : 'Unavailable';
}

function metricValue(item) {
  if (Number.isFinite(item.gross_yield_pct) && item.metric_status === 'available') {
    return `${item.gross_yield_pct.toFixed(2)}%`;
  }
  if (item.metric_status === 'stale' && Number.isFinite(item.last_observed_pct)) {
    return `${item.last_observed_pct.toFixed(2)}% (stale)`;
  }
  return 'Unavailable';
}

function copilotAssetType(item) {
  if (item.asset_class === 'MF') return 'mutual_fund';
  if (['BOND', 'SDI'].includes(item.asset_class)) return 'debt';
  if (item.asset_class === 'ETF') return 'etf';
  if (['REIT', 'INVIT', 'SM_REIT'].includes(item.asset_class)) return 'reit';
  return 'equity';
}

// =========================================================================
// MODALITY 1: RENDER BENTO OPPORTUNITY CARDS
// =========================================================================
function renderBentoCards(items) {
  const container = document.getElementById('bentoCardsGrid');
  if (!container) return;

  if (items.length === 0) {
    container.innerHTML = `
      <div style="grid-column: 1 / -1; text-align: center; padding: 48px 20px; background: rgba(15, 23, 42, 0.6); border: 1px dashed rgba(255, 255, 255, 0.15); border-radius: 12px; color: #94a3b8;">
        <div style="font-size: 28px; margin-bottom: 8px;"><svg class="glyph" style="width: 28px; height: 28px;"><use href="#glyph-search"></use></svg></div>
        <div style="font-size: 16px; font-weight: 700; color: #f8fafc; margin-bottom: 4px;">No offerings match your filter</div>
        <div style="font-size: 13px;">Switch research categories or clear the search keyword.</div>
      </div>
    `;
    return;
  }

  container.innerHTML = items.map(item => {
    const isPinned = pinnedIds.includes(item.id);
    const seniorBadgeColor =
      item.seniority_tier === 'SOVEREIGN' ? '#38bdf8' :
      item.seniority_tier === 'AAA_PSU' ? '#10b981' :
      item.seniority_tier === 'SENIOR_SECURED' ? '#34d399' :
      item.seniority_tier === 'COMMODITY_BACKED_TRUST' ? '#eab308' :
      item.seniority_tier === 'REAL_ASSET' ? '#c084fc' :
      item.seniority_tier === 'SDI' ? '#f59e0b' : '#f87171';

    return `
      <div class="card asset-card-accent" style="padding: 20px; display: flex; flex-direction: column; justify-content: space-between; position: relative; border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 14px; background: rgba(30, 41, 59, 0.55); transition: transform 0.2s, border-color 0.2s;">
        <div>
          <!-- Header Bar -->
          <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px;">
            <div style="display: flex; gap: 6px; flex-wrap: wrap; align-items: center;">
              <span style="font-size: 12px; font-weight: 700; padding: 3px 9px; border-radius: 4px; background: rgba(255, 255, 255, 0.08); color: ${seniorBadgeColor}; border: 1px solid ${seniorBadgeColor}40;">
                ${String(item.seniority_tier || '').replace(/_/g, ' ')}
              </span>
              <span style="font-size: 12px; font-weight: 700; padding: 3px 9px; border-radius: 4px; background: rgba(255, 255, 255, 0.05); color: #cbd5e1;">
                ${item.credit_rating || 'RATED'}
              </span>
            </div>

            <!-- Pin Button -->
            <button type="button" onclick="togglePin('${item.id}')" aria-label="Pin ${item.symbol} to comparison tray" style="background: ${isPinned ? 'rgba(14, 165, 233, 0.3)' : 'rgba(255, 255, 255, 0.08)'}; border: 1px solid ${isPinned ? '#0ea5e9' : 'rgba(255, 255, 255, 0.15)'}; border-radius: 6px; color: ${isPinned ? '#38bdf8' : '#94a3b8'}; padding: 5px 10px; font-size: 12.5px; cursor: pointer; display: flex; align-items: center; gap: 4px;">
              <span>${isPinned ? '✓ Pinned' : '+ Pin'}</span>
            </button>
          </div>

          <!-- Title -->
          <div style="margin-bottom: 14px;">
            <div style="font-size: 18px; font-weight: 800; color: #f8fafc; letter-spacing: -0.01em;">${item.symbol}</div>
            <div style="font-size: 13.5px; color: #94a3b8; line-height: 1.4; margin-top: 2px; min-height: 34px;">${item.name}</div>
          </div>

          <div style="background: rgba(15, 23, 42, 0.6); padding: 12px; border-radius: 8px; margin-bottom: 14px;">
            <div style="font-size: 12px; color: #94a3b8;">${metricLabel(item)}</div>
            <div class="tnum" style="font-size: 16px; font-weight: 800; color: #38bdf8;">${metricValue(item)}</div>
            <div style="font-size: 12px; color: #94a3b8;">As of ${item.metric_as_of || 'unavailable'}</div>
          </div>

          <!-- Micro Details -->
          <div style="font-size: 13px; color: #94a3b8; margin-bottom: 16px; line-height: 1.5;">
            <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
              <span style="color: #64748b;">Min Ticket:</span>
              <span style="font-weight: 600; color: #cbd5e1;">${ticketValue(item)}</span>
            </div>
            <div style="display: flex; justify-content: space-between;">
              <span style="color: #64748b;">Recourse:</span>
              <span style="font-weight: 600; color: #cbd5e1; max-width: 220px; text-align: right; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${item.recovery_recourse}">${item.recovery_recourse}</span>
            </div>
          </div>
        </div>

        <!-- Action Controls -->
        <div style="display: flex; gap: 8px;">
          <a href="${item.detail_url}" class="btn btn-secondary btn-sm" style="flex: 1; text-align: center; font-size: 13px; font-weight: 600; padding: 8px 12px;">
            Dossier &rarr;
          </a>
          <button type="button" onclick="openCopilot('${item.symbol || item.id}', '${copilotAssetType(item)}')" class="btn btn-hero-ai btn-sm" style="font-size: 13px; font-weight: 700; padding: 8px 12px; cursor: pointer;">
            <svg class="glyph" style="width: 13px; height: 13px;"><use href="#glyph-shield"></use></svg> Research Desk
          </button>
        </div>
      </div>
    `;
  }).join('');
}

// =========================================================================
// MODALITY 2: RENDER DATED DEBT OBSERVATIONS MATRIX
// =========================================================================
function renderHeatmap() {
  const tbody = document.getElementById('heatmapTableBody');
  if (!tbody || !heatmapData) return;

  tbody.innerHTML = heatmapData.rows.map(row => {
    return `
      <tr style="border-bottom: 1px solid rgba(255, 255, 255, 0.06);">
        <th scope="row" style="padding: 14px; text-align: left; font-weight: 700; color: #f8fafc; background: rgba(15, 23, 42, 0.4);">
          ${row.category_label}
        </th>
        ${heatmapData.tenure_buckets.map(b => {
          const cell = row.cells[b];
          if (!cell || !cell.has_data) {
            return `
              <td style="padding: 14px; text-align: center; color: #475569; background: rgba(15, 23, 42, 0.2);">
                —
              </td>
            `;
          }

          return `
            <td style="padding: 10px; text-align: center;">
              <a href="${cell.detail_url}">${cell.symbol}</a>
              <div class="tnum">${metricValue(cell)}</div>
              <div>${cell.metric_as_of}</div>
            </td>
          `;
        }).join('')}
      </tr>
    `;
  }).join('');
}

// =========================================================================
// DENSE TABLE
// =========================================================================
function renderDenseTable(items) {
  const tbody = document.getElementById('denseTableBody');
  if (!tbody) return;

  tbody.innerHTML = items.map(item => {
    const isPinned = pinnedIds.includes(item.id);
    return `
      <tr style="border-bottom: 1px solid rgba(255, 255, 255, 0.05); transition: background 0.15s ease;">
        <th scope="row" style="padding: 12px 14px; text-align: left;">
          <div style="font-weight: 800; color: #f8fafc; font-size: 14.5px;">${item.symbol}</div>
          <div style="font-size: 12.5px; color: #94a3b8; font-weight: 500; max-width: 240px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${item.name}</div>
        </th>
        <td style="padding: 12px 14px; font-size: 13px; color: #cbd5e1;">
          ${item.category_label}
        </td>
        <td style="padding: 12px 14px; font-size: 12.5px;">
          <span style="padding: 3px 9px; border-radius: 4px; background: rgba(255, 255, 255, 0.06); color: #cbd5e1; font-weight: 600;">${String(item.seniority_tier || '').replace(/_/g, ' ')}</span>
        </td>
        <td style="padding: 12px 14px;">${metricLabel(item)}</td>
        <td style="padding: 12px 14px; text-align: right;" class="tnum">${metricValue(item)}</td>
        <td style="padding: 12px 14px;">${item.metric_as_of || 'Unavailable'}</td>
        <td style="padding: 12px 14px; text-align: right; color: #cbd5e1; font-size: 13px;" class="tnum">
          ${ticketValue(item)}
        </td>
        <td style="padding: 12px 14px; text-align: center; white-space: nowrap;">
          <button type="button" onclick="togglePin('${item.id}')" aria-label="Pin ${item.symbol} to comparison tray" style="background: ${isPinned ? 'rgba(14, 165, 233, 0.3)' : 'rgba(255, 255, 255, 0.08)'}; border: 1px solid ${isPinned ? '#0ea5e9' : 'rgba(255, 255, 255, 0.15)'}; border-radius: 6px; color: ${isPinned ? '#38bdf8' : '#94a3b8'}; padding: 5px 10px; font-size: 12px; cursor: pointer; margin-right: 4px;">
            ${isPinned ? '✓ Pinned' : '+ Pin'}
          </button>
          <button type="button" onclick="openCopilot('${item.symbol || item.id}', '${copilotAssetType(item)}')" class="btn btn-hero-ai btn-sm" style="padding: 4px 8px; font-size: 11px; cursor: pointer;">
            <svg class="glyph" style="width: 12px; height: 12px;"><use href="#glyph-shield"></use></svg> Research Desk
          </button>
        </td>
      </tr>
    `;
  }).join('');
}

// =========================================================================
// FILTERS
// =========================================================================
function setPersonaFilter(persona) {
  currentPersona = persona;

  // Update button active states
  document.querySelectorAll('.persona-btn').forEach(btn => {
    if (btn.getAttribute('data-persona') === persona) {
      btn.classList.remove('btn-secondary');
      btn.classList.add('btn-primary');
    } else {
      btn.classList.remove('btn-primary');
      btn.classList.add('btn-secondary');
    }
  });

  loadUniverse();
}

function handleSearch(q) {
  currentSearch = q;
  renderActiveView();
}

// =========================================================================
// PERSISTENT COMPARISON DOCKET
// =========================================================================
function togglePin(id) {
  const index = pinnedIds.indexOf(id);
  if (index > -1) {
    pinnedIds.splice(index, 1);
  } else {
    if (pinnedIds.length >= 4) {
      alert('You can compare up to 4 opportunities at a time.');
      return;
    }
    pinnedIds.push(id);
  }

  try {
    localStorage.setItem('arbitrage_docket_ids', JSON.stringify(pinnedIds));
  } catch (e) {}

  updateDocketUI();
  renderActiveView();
}

function updateDocketUI() {
  const docket = document.getElementById('arbitrageDocket');
  const countEl = document.getElementById('docketCount');
  const chipsEl = document.getElementById('docketChips');

  if (!docket || !countEl || !chipsEl) return;

  countEl.textContent = pinnedIds.length;

  if (pinnedIds.length === 0) {
    docket.style.display = 'none';
    return;
  }

  docket.style.display = 'block';

  // Build chips
  chipsEl.innerHTML = pinnedIds.map(id => {
    const item = allOpportunities.find(x => x.id === id);
    const sym = item ? item.symbol : id;
    const netY = item ? `${metricLabel(item)} · ${metricValue(item)}` : '';
    return `
      <div style="background: rgba(30, 41, 59, 0.9); border: 1px solid rgba(14, 165, 233, 0.3); border-radius: 9999px; padding: 4px 12px; display: inline-flex; align-items: center; gap: 6px; font-size: 12.5px; color: #f8fafc;">
        <span><strong>${sym}</strong> ${netY}</span>
        <button type="button" onclick="togglePin('${id}')" aria-label="Remove ${sym} from comparison tray" style="background: none; border: none; color: #94a3b8; font-size: 13px; cursor: pointer; padding: 0;">✕</button>
      </div>
    `;
  }).join('');
}

function clearDocket() {
  pinnedIds = [];
  try {
    localStorage.removeItem('arbitrage_docket_ids');
  } catch (e) {}
  updateDocketUI();
  renderActiveView();
}

// =========================================================================
// SIDE-BY-SIDE COMPARISON MODAL
// =========================================================================
async function openArbitrageModal() {
  if (pinnedIds.length === 0) {
    alert('Pin at least one opportunity to compare.');
    return;
  }

  arbitrageInvokerEl = document.activeElement;
  const modal = document.getElementById('arbitrageModal');
  if (modal) {
    if (modal.parentElement !== document.body) {
      document.body.appendChild(modal);
    }
    arbitrageInertRestores = [];
    Array.from(document.body.children).forEach(child => {
      if (child !== modal && child.tagName !== 'SCRIPT') {
        const wasInert = Boolean(child.inert);
        child.inert = true;
        arbitrageInertRestores.push({ el: child, wasInert });
      }
    });
    modal.style.display = 'block';
    const closeBtn = document.getElementById('closeArbitrageModalBtn');
    if (closeBtn) closeBtn.focus({ preventScroll: true });
  }

  try {
    const res = await fetch('/api/v2/opportunities/arbitrage', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ item_ids: pinnedIds })
    });
    const data = await res.json();
    renderScorecardTable(data.items || []);
    const note = document.getElementById('comparisonMeasureNote');
    if (note) {
      note.textContent = data.same_comparison_group
        ? 'The selected values use the same measure and comparison group.'
        : 'The selected items have different measures, periods, or data availability. Read each value on its own.';
    }
  } catch (err) {
    console.error('Failed to load arbitrage scorecard:', err);
  }
}

function closeArbitrageModal() {
  const modal = document.getElementById('arbitrageModal');
  if (modal) modal.style.display = 'none';
  arbitrageInertRestores.forEach(({ el, wasInert }) => {
    try { el.inert = wasInert; } catch (_) {}
  });
  arbitrageInertRestores = [];
  if (arbitrageInvokerEl && typeof arbitrageInvokerEl.focus === 'function') {
    try { arbitrageInvokerEl.focus({ preventScroll: true }); } catch (_) {}
  }
  arbitrageInvokerEl = null;
}

function renderScorecardTable(items) {
  const thead = document.getElementById('scorecardHead');
  const tbody = document.getElementById('scorecardBody');
  if (!thead || !tbody) return;

  thead.innerHTML = `
    <tr style="border-bottom: 2px solid rgba(255, 255, 255, 0.15); text-align: left;">
      <th scope="col" style="padding: 12px; color: #64748b; font-size: 12px; text-transform: uppercase;">Diagnostic Dimension</th>
      ${items.map(it => `
        <th scope="col" style="padding: 12px; font-size: 15px; font-weight: 800; color: #f8fafc;">
          ${it.symbol}
          <div style="font-size: 12px; font-weight: 500; color: #94a3b8;">${it.category_label}</div>
        </th>
      `).join('')}
    </tr>
  `;

  const rows = [
    { label: 'Measure', fn: metricLabel },
    { label: 'Value', fn: metricValue },
    { label: 'As of', fn: it => it.metric_as_of || 'Unavailable' },
    { label: 'Capital Seniority Tier', fn: it => `<span style="padding: 2px 8px; border-radius: 4px; background: rgba(255,255,255,0.08);">${String(it.seniority_tier || '').replace(/_/g, ' ')}</span>` },
    { label: 'Recovery / Security Recourse', fn: it => `<span style="color: #cbd5e1; font-size: 12px;">${it.recovery_recourse}</span>` },
    { label: 'Minimum Ticket Size', fn: it => `<strong>${ticketValue(it)}</strong>` },
    { label: 'Secondary Exit Liquidity', fn: it => `<span>${String(it.liquidity_tier || '').replace(/_/g, ' ')}</span>` },
    { label: 'Countercase Failure Mode', fn: it => `<span style="color: #f87171; font-size: 12px;"><svg class="glyph" style="width: 12px; height: 12px; vertical-align: -1px;"><use href="#glyph-alert"></use></svg> ${it.primary_failure_mode}</span>` }
  ];

  tbody.innerHTML = rows.map(r => `
    <tr style="border-bottom: 1px solid rgba(255, 255, 255, 0.06);">
      <th scope="row" style="padding: 12px; text-align: left; font-weight: 700; color: #94a3b8; font-size: 12px;">${r.label}</th>
      ${items.map(it => `
        <td style="padding: 12px;" class="tnum">
          ${r.fn(it)}
        </td>
      `).join('')}
    </tr>
  `).join('');
}

// =========================================================================
// EXPORT CAPABILITIES
// =========================================================================
function exportOpportunities(format) {
  const filtered = getFilteredItems();
  if (filtered.length === 0) {
    alert('No data to export.');
    return;
  }

  const istDateSlug = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Kolkata' }).format(new Date());

  if (format === 'json') {
    const dataStr = 'data:text/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(filtered, null, 2));
    const a = document.createElement('a');
    a.href = dataStr;
    a.download = `opportunities_universe_${istDateSlug}.json`;
    a.click();
  } else if (format === 'csv') {
    const headers = ['Symbol', 'Name', 'Asset_Class', 'Measure', 'Value_Pct', 'Last_Observed_Pct', 'As_Of', 'Source', 'Status', 'Comparison_Group'];
    function csvCell(value) {
      if (value == null) return '';
      if (typeof value === 'number') return String(value);
      const text = String(value);
      const safeText = /^[\s]*[=+@-]|^[\t\r\n]/.test(text) ? "'" + text : text;
      return '"' + safeText.replace(/"/g, '""') + '"';
    }
    const rows = filtered.map(it => [
      it.symbol, it.name, it.asset_class, it.yield_type, it.gross_yield_pct, it.last_observed_pct,
      it.metric_as_of, it.metric_source, it.metric_status, it.comparison_group
    ].map(csvCell).join(','));
    const csvContent = [headers.join(','), ...rows].join('\n');
    const encodedUri = 'data:text/csv;charset=utf-8,' + encodeURIComponent(csvContent);
    const a = document.createElement('a');
    a.href = encodedUri;
    a.download = `opportunities_universe_${istDateSlug}.csv`;
    a.click();
  }
}

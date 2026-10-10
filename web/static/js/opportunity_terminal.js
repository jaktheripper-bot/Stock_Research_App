/**
 * Opportunity Terminal & Arbitrage Scanner Client Controller.
 * Powers dynamic multi-modal rendering (Cards, Heatmap, Scatter, Table),
 * real-time tax waterfall calculation, and persistent Cross-Asset Arbitrage Docket.
 */

let allOpportunities = [];
let heatmapData = null;
let currentView = 'cards';
let currentSlab = 30.0;
let currentInflation = 4.5;
let currentPersona = '';
let currentSearch = '';
let pinnedIds = [];
let scatterChartInstance = null;

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

  // Keyboard shortcut listener for 1, 2, 3, 4
  document.addEventListener('keydown', (e) => {
    if (e.target && (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT' || e.target.tagName === 'TEXTAREA')) {
      return;
    }
    if (e.key === '1') switchView('cards');
    else if (e.key === '2') switchView('heatmap');
    else if (e.key === '3') switchView('scatter');
    else if (e.key === '4') switchView('table');
  });

  loadUniverse();
  loadHeatmap();
  updateDocketUI();
});

// Fetch normalized opportunities
async function loadUniverse() {
  try {
    const url = `/api/opportunities/universe?tax_slab=${currentSlab}&cpi_inflation=${currentInflation}&persona=${encodeURIComponent(currentPersona)}`;
    const res = await fetch(url);
    const data = await res.json();
    allOpportunities = data.items || [];
    
    // Update summary metrics if present
    const totalEl = document.getElementById('kpiTotalItems');
    if (totalEl) totalEl.textContent = `${allOpportunities.length} Offerings`;

    renderActiveView();
  } catch (err) {
    console.error('Failed to load opportunities universe:', err);
  }
}

// Fetch heatmap data
async function loadHeatmap() {
  try {
    const res = await fetch(`/api/opportunities/heatmap`);
    heatmapData = await res.json();
    if (currentView === 'heatmap') {
      renderHeatmap();
    }
  } catch (err) {
    console.error('Failed to load heatmap:', err);
  }
}

// Switch between the 4 view modalities
function switchView(viewName) {
  currentView = viewName;
  
  // Update button active styling
  const viewBtns = {
    cards: document.getElementById('viewBtnCards'),
    heatmap: document.getElementById('viewBtnHeatmap'),
    scatter: document.getElementById('viewBtnScatter'),
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
    scatter: document.getElementById('viewScatterContainer'),
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
  } else if (currentView === 'scatter') {
    renderScatterChart(filtered);
  } else if (currentView === 'table') {
    renderDenseTable(filtered);
  }
}

function getFilteredItems() {
  let list = allOpportunities;
  if (currentSearch.trim()) {
    const q = currentSearch.toLowerCase();
    list = list.filter(x => 
      x.symbol.toLowerCase().includes(q) ||
      x.name.toLowerCase().includes(q) ||
      (x.credit_rating && x.credit_rating.toLowerCase().includes(q)) ||
      x.category_label.toLowerCase().includes(q) ||
      x.asset_class.toLowerCase().includes(q)
    );
  }
  return list;
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
        <div style="font-size: 28px; margin-bottom: 8px;">🔍</div>
        <div style="font-size: 16px; font-weight: 700; color: #f8fafc; margin-bottom: 4px;">No offerings match your filter</div>
        <div style="font-size: 13px;">Try switching personas or adjusting the search keyword.</div>
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
      item.seniority_tier === 'REAL_ASSET' ? '#c084fc' :
      item.seniority_tier === 'SDI' ? '#f59e0b' : '#f87171';

    // Waterfall bar widths (normalized against 16.0% max visual scale)
    const maxScale = 16.0;
    const grossWidth = Math.min(100, Math.max(5, (item.gross_yield_pct / maxScale) * 100));
    const netWidth = Math.min(100, Math.max(5, (item.net_yield_pct / maxScale) * 100));
    const realAlpha = item.real_yield_pct;
    const realWidth = Math.min(100, Math.max(5, (Math.max(0, realAlpha) / maxScale) * 100));

    return `
      <div class="card" style="padding: 20px; display: flex; flex-direction: column; justify-content: space-between; position: relative; border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 14px; background: rgba(30, 41, 59, 0.55); transition: transform 0.2s, border-color 0.2s;">
        <div>
          <!-- Header Bar -->
          <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px;">
            <div style="display: flex; gap: 6px; flex-wrap: wrap; align-items: center;">
              <span style="font-size: 12px; font-weight: 700; padding: 3px 9px; border-radius: 4px; background: rgba(255, 255, 255, 0.08); color: ${seniorBadgeColor}; border: 1px solid ${seniorBadgeColor}40;">
                ${item.seniority_tier.replace('_', ' ')}
              </span>
              <span style="font-size: 12px; font-weight: 700; padding: 3px 9px; border-radius: 4px; background: rgba(255, 255, 255, 0.05); color: #cbd5e1;">
                ${item.credit_rating || 'RATED'}
              </span>
            </div>

            <!-- Pin Button -->
            <button onclick="togglePin('${item.id}')" title="Pin to Cross-Asset Arbitrage Docket" style="background: ${isPinned ? 'rgba(14, 165, 233, 0.3)' : 'rgba(255, 255, 255, 0.08)'}; border: 1px solid ${isPinned ? '#0ea5e9' : 'rgba(255, 255, 255, 0.15)'}; border-radius: 6px; color: ${isPinned ? '#38bdf8' : '#94a3b8'}; padding: 5px 10px; font-size: 12.5px; cursor: pointer; display: flex; align-items: center; gap: 4px;">
              <span>${isPinned ? '📌 Pinned' : '➕ Pin'}</span>
            </button>
          </div>

          <!-- Title -->
          <div style="margin-bottom: 14px;">
            <div style="font-size: 18px; font-weight: 800; color: #f8fafc; letter-spacing: -0.01em;">${item.symbol}</div>
            <div style="font-size: 13.5px; color: #94a3b8; line-height: 1.4; margin-top: 2px; min-height: 34px;">${item.name}</div>
          </div>

          <!-- Yield Highlights Grid -->
          <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; background: rgba(15, 23, 42, 0.6); padding: 10px 12px; border-radius: 8px; margin-bottom: 14px; text-align: center;">
            <div>
              <div style="font-size: 12px; font-weight: 600; color: #64748b; text-transform: uppercase;">Gross YTM</div>
              <div style="font-size: 16px; font-weight: 800; color: #38bdf8;" class="tnum">${item.gross_yield_pct}%</div>
            </div>
            <div>
              <div style="font-size: 12px; font-weight: 600; color: #64748b; text-transform: uppercase;">Net (Post-Tax)</div>
              <div style="font-size: 16px; font-weight: 800; color: #10b981;" class="tnum">${item.net_yield_pct}%</div>
            </div>
            <div>
              <div style="font-size: 12px; font-weight: 600; color: #64748b; text-transform: uppercase;">10Y Spread</div>
              <div style="font-size: 16px; font-weight: 800; color: ${item.spread_vs_10y_gsec_bps >= 0 ? '#f59e0b' : '#ef4444'};" class="tnum">${item.spread_vs_10y_gsec_bps >= 0 ? '+' : ''}${item.spread_vs_10y_gsec_bps} bps</div>
            </div>
          </div>

          <!-- In-Cell SVG Yield Waterfall Sparkbar -->
          <div style="background: rgba(15, 23, 42, 0.4); border-radius: 8px; padding: 10px 12px; margin-bottom: 14px; font-size: 13px;">
            <div style="display: flex; justify-content: space-between; margin-bottom: 4px; color: #94a3b8;">
              <span>Gross Nominal: <strong style="color: #38bdf8;">${item.gross_yield_pct}%</strong></span>
              <span>Net in Hand: <strong style="color: #10b981;">${item.net_yield_pct}%</strong></span>
            </div>
            <!-- Progress Sparkbars -->
            <div style="width: 100%; height: 6px; background: rgba(255, 255, 255, 0.08); border-radius: 3px; overflow: hidden; margin-bottom: 4px; display: flex;">
              <div style="width: ${grossWidth}%; background: linear-gradient(90deg, #38bdf8, #0ea5e9);"></div>
            </div>
            <div style="width: 100%; height: 6px; background: rgba(255, 255, 255, 0.08); border-radius: 3px; overflow: hidden; margin-bottom: 6px; display: flex;">
              <div style="width: ${netWidth}%; background: linear-gradient(90deg, #10b981, #34d399);"></div>
            </div>
            <div style="display: flex; justify-content: space-between; font-size: 12px; color: #64748b;">
              <span>Real Alpha (Net - ${currentInflation}% CPI):</span>
              <span style="font-weight: 700; color: ${realAlpha >= 0 ? '#34d399' : '#f87171'};" class="tnum">${realAlpha >= 0 ? '+' : ''}${realAlpha}%</span>
            </div>
          </div>

          <!-- Micro Details -->
          <div style="font-size: 13px; color: #94a3b8; margin-bottom: 16px; line-height: 1.5;">
            <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
              <span style="color: #64748b;">Min Ticket:</span>
              <span style="font-weight: 600; color: #cbd5e1;">₹${Number(item.min_ticket_inr).toLocaleString('en-IN')}</span>
            </div>
            <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
              <span style="color: #64748b;">Statute:</span>
              <span style="font-weight: 600; color: #cbd5e1; max-width: 220px; text-align: right; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${item.tax_statute}">${item.tax_statute.split(' ')[0]} ${item.tax_statute.split(' ')[1] || ''}</span>
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
          <button onclick="openCopilot('${item.symbol || item.id}', '${item.asset_class === 'MF' ? 'mutual_fund' : (['BOND', 'SDI'].includes(item.asset_class) ? 'debt' : 'equity')}')" class="btn btn-hero-ai btn-sm" style="font-size: 13px; font-weight: 700; padding: 8px 12px; cursor: pointer;" title="Launch Forensic Intelligence Desk">
            ⚡ Forensic Desk
          </button>
        </div>
      </div>
    `;
  }).join('');
}

// =========================================================================
// MODALITY 2: RENDER RELATIVE YIELD SPREAD HEATMAP
// =========================================================================
function renderHeatmap() {
  const tbody = document.getElementById('heatmapTableBody');
  if (!tbody || !heatmapData) return;

  tbody.innerHTML = heatmapData.rows.map(row => {
    return `
      <tr style="border-bottom: 1px solid rgba(255, 255, 255, 0.06);">
        <td style="padding: 14px; font-weight: 700; color: #f8fafc; background: rgba(15, 23, 42, 0.4);">
          ${row.category_label}
        </td>
        ${heatmapData.tenure_buckets.map(b => {
          const cell = row.cells[b];
          if (!cell || !cell.has_data) {
            return `
              <td style="padding: 14px; text-align: center; color: #475569; background: rgba(15, 23, 42, 0.2);">
                —
              </td>
            `;
          }

          const spread = cell.spread_bps;
          // Color based on spread bps
          let bgStyle = 'rgba(14, 165, 233, 0.15)';
          let borderStyle = 'rgba(14, 165, 233, 0.3)';
          let textStyle = '#38bdf8';

          if (spread >= 250) {
            bgStyle = 'rgba(245, 158, 11, 0.2)';
            borderStyle = 'rgba(245, 158, 11, 0.4)';
            textStyle = '#fbbf24';
          } else if (spread >= 75) {
            bgStyle = 'rgba(16, 185, 129, 0.2)';
            borderStyle = 'rgba(16, 185, 129, 0.4)';
            textStyle = '#34d399';
          } else if (spread < 0) {
            bgStyle = 'rgba(244, 63, 94, 0.2)';
            borderStyle = 'rgba(244, 63, 94, 0.4)';
            textStyle = '#f87171';
          }

          const isPinned = pinnedIds.includes(cell.item_id);

          return `
            <td style="padding: 10px; text-align: center;">
              <div style="background: ${bgStyle}; border: 1px solid ${borderStyle}; border-radius: 8px; padding: 8px; position: relative; transition: transform 0.15s ease;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 2px;">
                  <span style="font-weight: 800; font-size: 13px; color: #f8fafc;">${cell.symbol}</span>
                  <button onclick="togglePin('${cell.item_id}')" title="Pin to Docket" style="background: none; border: none; font-size: 12px; cursor: pointer; color: ${isPinned ? '#38bdf8' : '#64748b'};">
                    ${isPinned ? '📌' : '➕'}
                  </button>
                </div>
                <div style="font-size: 14.5px; font-weight: 800; color: ${textStyle};" class="tnum">
                  ${cell.gross_yield_pct}%
                </div>
                <div style="font-size: 12px; font-weight: 600; color: ${textStyle};" class="tnum">
                  ${spread >= 0 ? '+' : ''}${spread} bps
                </div>
              </div>
            </td>
          `;
        }).join('')}
      </tr>
    `;
  }).join('');
}

// =========================================================================
// MODALITY 3: RENDER RISK VS NET REAL YIELD SCATTER FRONTIER
// =========================================================================
function renderScatterChart(items) {
  const canvas = document.getElementById('opportunityScatterChart');
  if (!canvas || typeof Chart === 'undefined') return;

  if (scatterChartInstance) {
    scatterChartInstance.destroy();
  }

  const categoryColors = {
    SOVEREIGN: '#38bdf8',
    AAA_PSU: '#10b981',
    SENIOR_SECURED: '#34d399',
    SUBORDINATED: '#f59e0b',
    SDI: '#f97316',
    REAL_ASSET: '#c084fc',
    EQUITY: '#f43f5e'
  };

  const datasets = [];
  const groups = {};

  items.forEach(item => {
    const groupKey = item.seniority_tier;
    if (!groups[groupKey]) groups[groupKey] = [];

    // Logarithmic radius based on min_ticket
    const ticket = Math.max(100, item.min_ticket_inr);
    let radius = 6;
    if (ticket >= 1000000) radius = 14;
    else if (ticket >= 10000) radius = 9;

    groups[groupKey].push({
      x: item.seniority_rank,
      y: item.real_yield_pct,
      r: radius,
      rawItem: item
    });
  });

  Object.keys(groups).forEach(k => {
    datasets.push({
      label: k.replace('_', ' '),
      data: groups[k],
      backgroundColor: (categoryColors[k] || '#94a3b8') + '88',
      borderColor: categoryColors[k] || '#94a3b8',
      borderWidth: 1.5,
      hoverRadius: 10
    });
  });

  const ctx = canvas.getContext('2d');
  scatterChartInstance = new Chart(ctx, {
    type: 'bubble',
    data: { datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: 'top',
          labels: {
            color: '#94a3b8',
            font: { family: 'Plus Jakarta Sans', size: 12 }
          }
        },
        tooltip: {
          backgroundColor: '#0f172a',
          titleColor: '#f8fafc',
          bodyColor: '#cbd5e1',
          borderColor: 'rgba(255, 255, 255, 0.15)',
          borderWidth: 1,
          padding: 12,
          callbacks: {
            title: (items) => {
              const raw = items[0].raw.rawItem;
              return `${raw.symbol} — ${raw.name}`;
            },
            label: (item) => {
              const raw = item.raw.rawItem;
              return [
                `Net Real Yield: ${raw.real_yield_pct}% (Net of ${currentInflation}% CPI)`,
                `Gross Yield: ${raw.gross_yield_pct}% | Post-Tax: ${raw.net_yield_pct}%`,
                `Tax Statute: ${raw.tax_statute}`,
                `Min Ticket: ₹${Number(raw.min_ticket_inr).toLocaleString('en-IN')}`,
                `Recourse: ${raw.recovery_recourse}`
              ];
            }
          }
        }
      },
      scales: {
        x: {
          title: {
            display: true,
            text: 'Capital Hierarchy Seniority Risk Tier',
            color: '#94a3b8',
            font: { size: 12, weight: '700' }
          },
          min: -0.5,
          max: 5.5,
          ticks: {
            stepSize: 1,
            color: '#64748b',
            callback: function(val) {
              const labels = ['0: Sovereign', '1: AAA PSU', '2: Senior Sec', '3: Sub / SDI', '4: Real Asset', '5: Equity'];
              return labels[val] || '';
            }
          },
          grid: { color: 'rgba(255, 255, 255, 0.05)' }
        },
        y: {
          title: {
            display: true,
            text: `Net Real Post-Tax Yield (%) (Net of ${currentInflation}% CPI)`,
            color: '#94a3b8',
            font: { size: 12, weight: '700' }
          },
          ticks: {
            color: '#64748b',
            callback: (val) => `${val}%`
          },
          grid: { color: 'rgba(255, 255, 255, 0.05)' }
        }
      }
    }
  });
}

// =========================================================================
// MODALITY 4: RENDER DENSE INSTITUTIONAL TABLE
// =========================================================================
function renderDenseTable(items) {
  const tbody = document.getElementById('denseTableBody');
  if (!tbody) return;

  tbody.innerHTML = items.map(item => {
    const isPinned = pinnedIds.includes(item.id);
    return `
      <tr style="border-bottom: 1px solid rgba(255, 255, 255, 0.05); transition: background 0.15s ease;">
        <td style="padding: 12px 14px;">
          <div style="font-weight: 800; color: #f8fafc; font-size: 14.5px;">${item.symbol}</div>
          <div style="font-size: 12.5px; color: #94a3b8; max-width: 240px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${item.name}</div>
        </td>
        <td style="padding: 12px 14px; font-size: 13px; color: #cbd5e1;">
          ${item.category_label}
        </td>
        <td style="padding: 12px 14px; font-size: 12.5px;">
          <span style="padding: 3px 9px; border-radius: 4px; background: rgba(255, 255, 255, 0.06); color: #cbd5e1; font-weight: 600;">${item.seniority_tier.replace('_', ' ')}</span>
        </td>
        <td style="padding: 12px 14px; text-align: right; font-weight: 700; color: #38bdf8; font-size: 14px;" class="tnum">
          ${item.gross_yield_pct}%
        </td>
        <td style="padding: 12px 14px; text-align: right; font-weight: 800; color: #10b981; font-size: 14px;" class="tnum">
          ${item.net_yield_pct}%
        </td>
        <td style="padding: 12px 14px; text-align: right; font-weight: 700; color: ${item.real_yield_pct >= 0 ? '#34d399' : '#f87171'}; font-size: 14px;" class="tnum">
          ${item.real_yield_pct >= 0 ? '+' : ''}${item.real_yield_pct}%
        </td>
        <td style="padding: 12px 14px; text-align: right; font-weight: 600; color: #f59e0b; font-size: 13.5px;" class="tnum">
          ${item.spread_vs_10y_gsec_bps >= 0 ? '+' : ''}${item.spread_vs_10y_gsec_bps} bps
        </td>
        <td style="padding: 12px 14px; text-align: right; color: #cbd5e1; font-size: 13px;" class="tnum">
          ₹${Number(item.min_ticket_inr).toLocaleString('en-IN')}
        </td>
        <td style="padding: 12px 14px; text-align: center; white-space: nowrap;">
          <button onclick="togglePin('${item.id}')" title="Pin to Arbitrage Docket" style="background: ${isPinned ? 'rgba(14, 165, 233, 0.3)' : 'rgba(255, 255, 255, 0.08)'}; border: 1px solid ${isPinned ? '#0ea5e9' : 'rgba(255, 255, 255, 0.15)'}; border-radius: 6px; color: ${isPinned ? '#38bdf8' : '#94a3b8'}; padding: 5px 10px; font-size: 12px; cursor: pointer; margin-right: 4px;">
            ${isPinned ? '📌' : '➕ Pin'}
          </button>
          <button onclick="openCopilot('${item.symbol || item.id}', '${item.asset_class === 'MF' ? 'mutual_fund' : (['BOND', 'SDI'].includes(item.asset_class) ? 'debt' : 'equity')}')" title="Launch Forensic Intelligence Desk" class="btn btn-hero-ai btn-sm" style="padding: 4px 8px; font-size: 11px; cursor: pointer;">
            ⚡ Forensic Desk
          </button>
        </td>
      </tr>
    `;
  }).join('');
}

// =========================================================================
// REACTIVE SLIDERS & FILTERS
// =========================================================================
function updateTaxSlab(val) {
  currentSlab = parseFloat(val);
  loadUniverse();
}

function updateInflation(val) {
  currentInflation = parseFloat(val);
  const label = document.getElementById('inflationValLabel');
  if (label) label.textContent = `${val}%`;
  
  // Recompute real yields on existing items without refetching
  allOpportunities.forEach(item => {
    item.real_yield_pct = parseFloat((item.net_yield_pct - currentInflation).toFixed(2));
  });
  renderActiveView();
}

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
// PERSISTENT ARBITRAGE DOCKET
// =========================================================================
function togglePin(id) {
  const index = pinnedIds.indexOf(id);
  if (index > -1) {
    pinnedIds.splice(index, 1);
  } else {
    if (pinnedIds.length >= 4) {
      alert('You can compare a maximum of 4 opportunities simultaneously in the Arbitrage Docket.');
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
    const netY = item ? `${item.net_yield_pct}% Net` : '';
    return `
      <div style="background: rgba(30, 41, 59, 0.9); border: 1px solid rgba(14, 165, 233, 0.3); border-radius: 9999px; padding: 4px 12px; display: inline-flex; align-items: center; gap: 6px; font-size: 12.5px; color: #f8fafc;">
        <span><strong>${sym}</strong> ${netY}</span>
        <button onclick="togglePin('${id}')" style="background: none; border: none; color: #94a3b8; font-size: 13px; cursor: pointer; padding: 0;">✕</button>
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
// SIDE-BY-SIDE ARBITRAGE SCORECARD MODAL
// =========================================================================
async function openArbitrageModal() {
  if (pinnedIds.length === 0) {
    alert('Please pin at least 1 opportunity to compare.');
    return;
  }

  try {
    const res = await fetch('/api/opportunities/arbitrage', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        item_ids: pinnedIds,
        tax_slab: currentSlab,
        cpi_inflation: currentInflation
      })
    });
    const data = await res.json();
    renderScorecardTable(data.items || []);

    const modal = document.getElementById('arbitrageModal');
    if (modal) modal.style.display = 'block';
  } catch (err) {
    console.error('Failed to load arbitrage scorecard:', err);
  }
}

function closeArbitrageModal() {
  const modal = document.getElementById('arbitrageModal');
  if (modal) modal.style.display = 'none';
}

function renderScorecardTable(items) {
  const thead = document.getElementById('scorecardHead');
  const tbody = document.getElementById('scorecardBody');
  if (!thead || !tbody) return;

  thead.innerHTML = `
    <tr style="border-bottom: 2px solid rgba(255, 255, 255, 0.15); text-align: left;">
      <th style="padding: 12px; color: #64748b; font-size: 12px; text-transform: uppercase;">Diagnostic Dimension</th>
      ${items.map(it => `
        <th style="padding: 12px; font-size: 15px; font-weight: 800; color: #f8fafc;">
          ${it.symbol}
          <div style="font-size: 12px; font-weight: 500; color: #94a3b8;">${it.category_label}</div>
        </th>
      `).join('')}
    </tr>
  `;

  const rows = [
    { label: 'Gross Yield / Return', fn: it => `<strong style="color: #38bdf8;">${it.gross_yield_pct}%</strong>` },
    { label: `Net Post-Tax (${currentSlab}% Slab)`, fn: it => `<strong style="color: #10b981; font-size: 15px;">${it.net_yield_pct}%</strong>` },
    { label: `Real Alpha (Net - ${currentInflation}% CPI)`, fn: it => `<strong style="color: ${it.real_yield_pct >= 0 ? '#34d399' : '#f87171'};">${it.real_yield_pct >= 0 ? '+' : ''}${it.real_yield_pct}%</strong>` },
    { label: '10Y Sovereign Spread', fn: it => `<span>${it.spread_vs_10y_gsec_bps >= 0 ? '+' : ''}${it.spread_vs_10y_gsec_bps} bps</span>` },
    { label: 'Capital Seniority Tier', fn: it => `<span style="padding: 2px 8px; border-radius: 4px; background: rgba(255,255,255,0.08);">${it.seniority_tier.replace('_', ' ')}</span>` },
    { label: 'Statutory Tax Regime', fn: it => `<span style="color: #cbd5e1; font-size: 12px;">${it.tax_statute}</span>` },
    { label: 'Recovery / Security Recourse', fn: it => `<span style="color: #cbd5e1; font-size: 12px;">${it.recovery_recourse}</span>` },
    { label: 'Minimum Ticket Size', fn: it => `<strong>₹${Number(it.min_ticket_inr).toLocaleString('en-IN')}</strong>` },
    { label: 'Secondary Exit Liquidity', fn: it => `<span>${it.liquidity_tier.replace('_', ' ')}</span>` },
    { label: 'Pre-Mortem Failure Mode', fn: it => `<span style="color: #f87171; font-size: 12px;">⚠️ ${it.primary_failure_mode}</span>` }
  ];

  tbody.innerHTML = rows.map(r => `
    <tr style="border-bottom: 1px solid rgba(255, 255, 255, 0.06);">
      <td style="padding: 12px; font-weight: 700; color: #94a3b8; font-size: 12px;">${r.label}</td>
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

  if (format === 'json') {
    const dataStr = 'data:text/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(filtered, null, 2));
    const a = document.createElement('a');
    a.href = dataStr;
    a.download = `opportunities_universe_${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
  } else if (format === 'csv') {
    const headers = ['Symbol', 'Name', 'Asset_Class', 'Seniority', 'Gross_Yield_Pct', 'Net_Yield_Pct', 'Real_Yield_Pct', 'Spread_10Y_Bps', 'Min_Ticket_INR', 'Tax_Statute'];
    const rows = filtered.map(it => [
      `"${it.symbol}"`,
      `"${it.name.replace(/"/g, '""')}"`,
      `"${it.asset_class}"`,
      `"${it.seniority_tier}"`,
      it.gross_yield_pct,
      it.net_yield_pct,
      it.real_yield_pct,
      it.spread_vs_10y_gsec_bps,
      it.min_ticket_inr,
      `"${it.tax_statute}"`
    ]);
    const csvContent = 'data:text/csv;charset=utf-8,' + [headers.join(','), ...rows.map(e => e.join(','))].join('\n');
    const encodedUri = encodeURI(csvContent);
    const a = document.createElement('a');
    a.href = encodedUri;
    a.download = `opportunities_universe_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
  }
}

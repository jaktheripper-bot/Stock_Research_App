/**
 * Moatnomics - Main Client-Side Logic
 * Autocomplete, Instant Lookup, Razorpay Checkout Modal, and Report Generation
 */

// Immediate OAuth Fragment Interceptor (captures #access_token=... or #error=... if Supabase redirects to root or any page)
(function checkOAuthFragment() {
  if (window.location.hash) {
    try {
      const hashParams = new URLSearchParams(window.location.hash.substring(1));
      const accessToken = hashParams.get('access_token');
      const err = hashParams.get('error_description') || hashParams.get('error');
      const hasAdminCookie = document.cookie.split(';').some(c => c.trim().startsWith('oauth_admin_intent='));
      const isAdmin = window.location.pathname.startsWith('/admin') || hasAdminCookie;
      if (accessToken) {
        if (hasAdminCookie) {
          document.cookie = 'oauth_admin_intent=; Max-Age=0; path=/';
        }
        const callbackUrl = isAdmin ? '/admin/auth/callback' : '/auth/callback';
        window.location.replace(callbackUrl + '?access_token=' + encodeURIComponent(accessToken));
      } else if (err) {
        const target = isAdmin ? '/admin?err=' : '/?err=';
        window.location.replace(target + encodeURIComponent(err));
      }
    } catch (e) {
      console.error('Error handling OAuth fragment:', e);
    }
  }
})();


document.addEventListener('DOMContentLoaded', () => {
  initSearchAutocomplete();
  initCheckoutModals();
  initGenerateModal();
  initAuthModal();
  initNavigationDropdowns();
  initPricingCurrency();
  initThemeToggle();
});

// ==============================================================================
// 1. Search and Autocomplete (Homepage)
// ==============================================================================
function initSearchAutocomplete() {
  const searchInput = document.getElementById('mainSearchInput');
  const suggestionsBox = document.getElementById('searchSuggestions');
  const searchForm = document.getElementById('mainSearchForm');

  if (!searchInput || !searchForm) return;

  searchForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const query = searchInput.value.trim().toUpperCase();
    if (query) {
      const submitBtn = searchForm.querySelector('button[type="submit"], .btn-search, .search-btn');
      if (submitBtn) startButtonProgressFill(submitBtn, 'Searching');
      window.location.href = `/dossier/${encodeURIComponent(query)}`;
    }
  });

  let debounceTimer;
  searchInput.addEventListener('input', (e) => {
    clearTimeout(debounceTimer);
    const q = e.target.value.trim();
    if (q.length < 2) {
      if (suggestionsBox) suggestionsBox.style.display = 'none';
      return;
    }

    debounceTimer = setTimeout(async () => {
      try {
        const resp = await fetch(`/api/suggest?q=${encodeURIComponent(q)}`);
        if (resp.ok) {
          const data = await resp.json();
          renderSuggestions(data.suggestions || []);
        }
      } catch (err) {
        console.error('Failed to fetch suggestions:', err);
      }
    }, 250);
  });

  function renderSuggestions(items) {
    if (!suggestionsBox) return;
    if (!items || items.length === 0) {
      suggestionsBox.style.display = 'none';
      return;
    }

    suggestionsBox.innerHTML = items.map(ticker => `
      <div class="suggestion-item" onclick="window.location.href='/dossier/${encodeURIComponent(ticker)}'">
        <span class="ticker-badge">${ticker}</span>
        <span class="view-label">View Stock Report →</span>
      </div>
    `).join('');
    suggestionsBox.style.display = 'block';
  }

  // Close suggestions on outside click
  document.addEventListener('click', (e) => {
    if (suggestionsBox && !searchForm.contains(e.target)) {
      suggestionsBox.style.display = 'none';
    }
  });
}

// ==============================================================================
// 2. Global Generate Report Modal & Autocomplete
// ==============================================================================
function initGenerateModal() {
  const modal = document.getElementById('generateModal');
  const closeBtn = document.getElementById('closeGenerateModalBtn');
  const tickerInput = document.getElementById('generateModalTickerInput');
  const suggestionsBox = document.getElementById('generateModalSuggestions');

  if (closeBtn && modal) {
    closeBtn.addEventListener('click', () => {
      modal.classList.remove('active');
    });
    modal.addEventListener('click', (e) => {
      if (e.target === modal) {
        modal.classList.remove('active');
      }
    });
  }

  if (tickerInput && suggestionsBox) {
    let debounceTimer;
    tickerInput.addEventListener('input', (e) => {
      clearTimeout(debounceTimer);
      const q = e.target.value.trim();
      if (q.length < 2) {
        suggestionsBox.style.display = 'none';
        return;
      }

      debounceTimer = setTimeout(async () => {
        try {
          const resp = await fetch(`/api/suggest?q=${encodeURIComponent(q)}`);
          if (resp.ok) {
            const data = await resp.json();
            const items = data.suggestions || [];
            if (items.length === 0) {
              suggestionsBox.style.display = 'none';
              return;
            }
            suggestionsBox.innerHTML = items.map(ticker => `
              <div class="suggestion-item" style="padding: 10px 14px; cursor: pointer; display: flex; justify-content: space-between; border-bottom: 1px solid var(--border-color); background: var(--bg-card);" onclick="selectGenerateTicker('${ticker}')">
                <span class="ticker-badge" style="font-weight: 700; color: var(--accent-cyan);">${ticker}</span>
                <span style="font-size: 12px; color: var(--text-muted);">Select</span>
              </div>
            `).join('');
            suggestionsBox.style.display = 'block';
          }
        } catch (err) {
          console.error('Failed to fetch modal suggestions:', err);
        }
      }, 250);
    });

    document.addEventListener('click', (e) => {
      if (suggestionsBox && !tickerInput.contains(e.target) && !suggestionsBox.contains(e.target)) {
        suggestionsBox.style.display = 'none';
      }
    });
  }
}

window.selectGenerateTicker = function(ticker) {
  const tickerInput = document.getElementById('generateModalTickerInput');
  const suggestionsBox = document.getElementById('generateModalSuggestions');
  if (tickerInput) tickerInput.value = ticker;
  if (suggestionsBox) suggestionsBox.style.display = 'none';
};

window.openGenerateModal = function() {
  const user = getStoredUser();
  if (!user) {
    alert('Please sign in first to generate stock reports. You will receive 2 free research credits.');
    openSignInModal();
    return;
  }

  const balanceText = document.getElementById('generateModalCreditsText');
  if (balanceText) {
    const bal = user.credits_balance !== undefined ? user.credits_balance : 0;
    balanceText.innerText = `${bal} Credits Available`;
    if (bal < 1) {
      balanceText.style.color = '#ef4444';
      balanceText.innerText = `${bal} Credits (Top-up required)`;
    } else {
      balanceText.style.color = 'var(--accent-emerald)';
    }
  }

  const modal = document.getElementById('generateModal');
  if (modal) {
    modal.classList.add('active');
    const input = document.getElementById('generateModalTickerInput');
    if (input) {
      input.value = '';
      setTimeout(() => input.focus(), 150);
    }
  }
};

window.handleGenerateModalSubmit = async function(e) {
  if (e) e.preventDefault();
  const input = document.getElementById('generateModalTickerInput');
  if (!input || !input.value.trim()) {
    alert('Please enter a BSE/NSE stock symbol or company name.');
    return;
  }

  const ticker = input.value.trim().toUpperCase();
  const modal = document.getElementById('generateModal');
  if (modal) modal.classList.remove('active');

  await synthesizeReport(ticker);
};

// ==============================================================================
// 3. Razorpay Checkout Modal & Payment Processing
// ==============================================================================
function initCheckoutModals() {
  const modal = document.getElementById('checkoutModal');
  const closeBtn = document.getElementById('closeModalBtn');

  if (closeBtn && modal) {
    closeBtn.addEventListener('click', () => {
      modal.classList.remove('active');
    });

    modal.addEventListener('click', (e) => {
      if (e.target === modal) {
        modal.classList.remove('active');
      }
    });
  }
}

// ==============================================================================
// Multi-Currency Converter & Indicative Pricing Architecture
// ==============================================================================
const SUPPORTED_CURRENCIES = {
  INR: { code: 'INR', symbol: '₹', name: 'Indian Rupee', flag: '🇮🇳', rate: 1.0, buffer: 0.0, is_base: true },
  USD: { code: 'USD', symbol: '$', name: 'US Dollar', flag: '🇺🇸', rate: 88.50, buffer: 0.035, is_base: false },
  EUR: { code: 'EUR', symbol: '€', name: 'Euro', flag: '🇪🇺', rate: 96.50, buffer: 0.035, is_base: false }
};

let currentCurrency = 'INR';

function convertInrPrice(amountInr, currencyCode) {
  const code = (currencyCode || 'INR').toUpperCase();
  const curr = SUPPORTED_CURRENCIES[code] || SUPPORTED_CURRENCIES.INR;
  if (curr.is_base) {
    return {
      code: 'INR',
      symbol: '₹',
      amount: amountInr,
      formatted: '₹' + Number(amountInr).toLocaleString('en-IN'),
      is_base: true
    };
  }
  const rawForeign = amountInr / curr.rate;
  const effectiveAmount = rawForeign * (1.0 + curr.buffer);
  const formatted = curr.symbol + effectiveAmount.toFixed(2);
  return {
    code: code,
    symbol: curr.symbol,
    amount: effectiveAmount,
    formatted: formatted,
    is_base: false
  };
}

function detectUserCurrency() {
  const saved = localStorage.getItem('preferred_currency');
  if (saved && SUPPORTED_CURRENCIES[saved.toUpperCase()]) {
    return saved.toUpperCase();
  }
  if (window.__DETECTED_CURRENCY && SUPPORTED_CURRENCIES[window.__DETECTED_CURRENCY.toUpperCase()]) {
    return window.__DETECTED_CURRENCY.toUpperCase();
  }
  try {
    const tz = (Intl.DateTimeFormat().resolvedOptions().timeZone || '').toLowerCase();
    if (tz.includes('calcutta') || tz.includes('kolkata')) return 'INR';
    if (tz.startsWith('europe/') || tz.includes('london')) return 'EUR';
    if (tz.startsWith('america/') || tz.includes('tokyo') || tz.includes('singapore') || tz.includes('dubai') || tz.includes('sydney')) return 'USD';
  } catch (e) {
    console.debug('Timezone currency detection notice:', e);
  }
  return 'INR';
}

window.setPricingCurrency = function(code) {
  if (!SUPPORTED_CURRENCIES[code]) return;
  currentCurrency = code;
  localStorage.setItem('preferred_currency', code);

  const select = document.getElementById('currencySelect');
  if (select && select.value !== code) {
    select.value = code;
  }

  updatePricingDisplay();
};

function updatePricingDisplay() {
  const isBase = currentCurrency === 'INR';
  const curr = SUPPORTED_CURRENCIES[currentCurrency] || SUPPORTED_CURRENCIES.INR;

  const noticeBanner = document.getElementById('currencyNoticeBanner');
  const noticeCode = document.getElementById('noticeCurrencyCode');
  if (noticeBanner) {
    if (isBase) {
      noticeBanner.style.display = 'none';
    } else {
      noticeBanner.style.display = 'block';
      if (noticeCode) {
        noticeCode.innerText = `${curr.name} (${curr.code} ${curr.symbol.trim()})`;
      }
    }
  }

  document.querySelectorAll('.plan-price[data-base-inr]').forEach(el => {
    const baseInr = parseFloat(el.getAttribute('data-base-inr'));
    if (!isNaN(baseInr)) {
      const conv = convertInrPrice(baseInr, currentCurrency);
      const isMonthly = el.innerHTML.includes('/month') || el.querySelector('.cycle');
      if (isBase) {
        el.innerHTML = isMonthly ? `<span class="price-val">₹${baseInr.toLocaleString('en-IN')}</span> <span class="cycle">/month</span>` : `₹${baseInr.toLocaleString('en-IN')}`;
      } else {
        el.innerHTML = isMonthly ? `<span class="price-val">~${conv.formatted}</span> <span class="cycle">/month</span>` : `~${conv.formatted}`;
      }
    }
  });

  document.querySelectorAll('.plan-price-sub[data-base-inr]').forEach(el => {
    const baseInr = parseFloat(el.getAttribute('data-base-inr'));
    if (!isNaN(baseInr)) {
      if (isBase) {
        el.style.display = 'none';
      } else {
        el.style.display = 'block';
        el.innerText = `(Billed as ₹${baseInr.toLocaleString('en-IN')} INR)`;
      }
    }
  });

  document.querySelectorAll('.unit-rate[data-per-stock-inr]').forEach(el => {
    const rateInr = parseFloat(el.getAttribute('data-per-stock-inr'));
    if (!isNaN(rateInr)) {
      if (isBase) {
        el.innerText = `(₹${rateInr}/stock)`;
      } else {
        const conv = convertInrPrice(rateInr, currentCurrency);
        el.innerText = `(~${conv.formatted}/stock)`;
      }
    }
  });

  document.querySelectorAll('.plan-checkout-btn[data-base-inr]').forEach(btn => {
    const baseInr = parseFloat(btn.getAttribute('data-base-inr'));
    const baseText = btn.getAttribute('data-base-label') || btn.innerText.split(' (~')[0].split(' (₹')[0].trim();
    if (!btn.getAttribute('data-base-label')) {
      btn.setAttribute('data-base-label', baseText);
    }
    if (isBase) {
      btn.innerText = baseText;
    } else {
      const conv = convertInrPrice(baseInr, currentCurrency);
      btn.innerText = `${baseText} (~${conv.formatted})`;
    }
  });

  document.querySelectorAll('.b2b-btn[data-base-inr]').forEach(btn => {
    const baseInr = parseFloat(btn.getAttribute('data-base-inr'));
    const label = btn.getAttribute('data-label') || 'Pack';
    if (isBase) {
      btn.innerText = `${label} (₹${baseInr.toLocaleString('en-IN')})`;
    } else {
      const conv = convertInrPrice(baseInr, currentCurrency);
      btn.innerText = `${label} (~${conv.formatted})`;
    }
  });
}

function initPricingCurrency() {
  const detected = detectUserCurrency();
  currentCurrency = detected;
  const select = document.getElementById('currencySelect');
  if (select) {
    select.value = detected;
  }
  updatePricingDisplay();
}

// Global checkout trigger
window.openCheckout = function(planId, planName, amountInr, credits) {
  const storedUser = getStoredUser();
  if (!storedUser) {
    window._pendingCheckout = { planId: planId, planName: planName, amountInr: amountInr, credits: credits };
    alert('Please enter your email to sign in or create your account first. You will receive 2 free welcome credits and your purchased credits will be credited directly to your account.');
    openSignInModal();
    return;
  }

  const modal = document.getElementById('checkoutModal');
  if (!modal) return;

  const conv = convertInrPrice(amountInr, currentCurrency);
  const isBase = currentCurrency === 'INR';

  document.getElementById('modalPlanName').innerText = planName;
  document.getElementById('modalPlanCredits').innerText = credits + ' Research Credits';

  const priceEl = document.getElementById('modalPlanPrice');
  const localEquivEl = document.getElementById('modalLocalEquiv');
  const basePriceEl = document.getElementById('modalBasePrice');
  const bufferRow = document.getElementById('modalBufferRow');
  const intlNotice = document.getElementById('modalIntlNotice');
  const confirmBtn = document.getElementById('modalConfirmBtn');

  if (isBase) {
    if (priceEl) priceEl.innerText = '₹' + Number(amountInr).toLocaleString('en-IN');
    if (localEquivEl) localEquivEl.style.display = 'none';
    if (basePriceEl) basePriceEl.innerText = '₹' + Number(amountInr).toLocaleString('en-IN') + ' INR';
    if (bufferRow) bufferRow.style.display = 'none';
    if (intlNotice) intlNotice.style.display = 'none';
    if (confirmBtn) confirmBtn.innerText = 'Pay via UPI / Card (Instant Confirmation)';
  } else {
    if (priceEl) priceEl.innerText = '~' + conv.formatted;
    if (localEquivEl) {
      localEquivEl.style.display = 'block';
      localEquivEl.innerText = 'Billed as ₹' + Number(amountInr).toLocaleString('en-IN') + ' INR';
    }
    if (basePriceEl) basePriceEl.innerText = '₹' + Number(amountInr).toLocaleString('en-IN') + ' INR';
    if (bufferRow) bufferRow.style.display = 'flex';
    if (intlNotice) intlNotice.style.display = 'block';
    if (confirmBtn) confirmBtn.innerText = 'Pay ₹' + Number(amountInr).toLocaleString('en-IN') + ' INR (~' + conv.formatted + ')';
  }

  if (confirmBtn) {
    confirmBtn.onclick = async () => {
      confirmBtn.disabled = true;
      confirmBtn.innerText = 'Initializing Razorpay Checkout...';

      try {
        const activeUser = getStoredUser() || storedUser;
        const effectiveUserId = (activeUser && activeUser.id) ? activeUser.id : 'guest_web_user';
        const effectiveUserEmail = (activeUser && activeUser.email) ? activeUser.email : '';
        const resp = await fetch('/api/create-order', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            plan_id: planId,
            user_id: effectiveUserId,
            email: effectiveUserEmail
          })
        });
        
        if (!resp.ok) {
          const errData = await resp.json().catch(() => ({}));
          throw new Error(errData.detail || errData.message || 'Failed to initialize Razorpay order');
        }

        const orderData = await resp.json();

        if (orderData.is_simulated) {
          // Simulation fulfillment for dev/offline testing
          const simPayId = 'pay_sim_' + Date.now();
          const verifyResp = await fetch('/api/verify-payment', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              order_id: orderData.order_id || orderData.id,
              payment_id: simPayId,
              signature: 'sig_sim_' + (orderData.order_id || orderData.id) + '_' + simPayId,
              plan_id: planId,
              user_id: effectiveUserId
            })
          });
          const verifyResult = await verifyResp.json();
          if (verifyResp.ok && verifyResult.success) {
            let user = getStoredUser() || activeUser;
            if (user) {
              user.credits_balance = verifyResult.new_balance !== undefined ? verifyResult.new_balance : ((parseFloat(user.credits_balance) || 0) + parseFloat(credits));
              localStorage.setItem('sr_user', JSON.stringify(user));
              syncUserSession();
            }
            await refreshUserBalance(user);
            alert(`🎉 Payment verified successfully! Added ${credits} credits to your account.\nNew Balance: ${verifyResult.new_balance !== undefined ? verifyResult.new_balance : (user ? user.credits_balance : credits)} Credits\nInvoice: ${verifyResult.invoice_number}`);
            modal.classList.remove('active');
            window.location.reload();
          } else {
            alert('Payment verification failed: ' + (verifyResult.detail || verifyResult.message || 'Verification error'));
          }
        } else {
          // Official Razorpay Standard Web Checkout
          const options = {
            key: orderData.key_id,
            amount: orderData.amount,
            currency: orderData.currency || 'INR',
            name: 'Moatnomics',
            description: planName + ' — Research Credits',
            order_id: orderData.order_id || orderData.id,
            prefill: {
              name: (activeUser && activeUser.full_name) ? activeUser.full_name : 'Test Investor',
              email: effectiveUserEmail || 'investor@moatnomics.com',
              contact: (activeUser && activeUser.phone) ? activeUser.phone : '9820098200'
            },
            theme: {
              color: '#0ea5e9'
            },
            handler: async function (response) {
              confirmBtn.innerText = 'Verifying Signature...';
              try {
                const verifyResp = await fetch('/api/verify-payment', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({
                    order_id: response.razorpay_order_id,
                    payment_id: response.razorpay_payment_id,
                    signature: response.razorpay_signature,
                    plan_id: planId,
                    user_id: effectiveUserId
                  })
                });
                const verifyResult = await verifyResp.json();
                if (verifyResp.ok && verifyResult.success) {
                  let user = getStoredUser();
                  if (user) {
                    user.credits_balance = verifyResult.new_balance !== undefined ? verifyResult.new_balance : ((parseFloat(user.credits_balance) || 0) + parseFloat(credits));
                    localStorage.setItem('sr_user', JSON.stringify(user));
                    syncUserSession();
                  }
                  await refreshUserBalance(user);
                  alert(`🎉 Payment Confirmed! Added ${credits} credits to your account.\nNew Balance: ${verifyResult.new_balance !== undefined ? verifyResult.new_balance : (user ? user.credits_balance : credits)} Credits\nInvoice: ${verifyResult.invoice_number}`);
                  modal.classList.remove('active');
                  window.location.reload();
                } else {
                  alert('Payment verification failed: ' + (verifyResult.detail || verifyResult.message || 'Signature mismatch'));
                }
              } catch (verifyErr) {
                alert('Verification Error: ' + verifyErr.message);
              } finally {
                confirmBtn.disabled = false;
                confirmBtn.innerText = 'Pay via UPI / Card (Instant Confirmation)';
              }
            },
            modal: {
              ondismiss: function () {
                console.log('Razorpay modal dismissed by user');
                confirmBtn.disabled = false;
                confirmBtn.innerText = 'Pay via UPI / Card (Instant Confirmation)';
              }
            }
          };

          const rzpInstance = new Razorpay(options);
          rzpInstance.on('payment.failed', function (failResp) {
            console.error('Razorpay payment failed:', failResp.error);
            const errDesc = failResp.error ? (failResp.error.description || failResp.error.reason) : 'Payment cancelled or failed';
            alert('Payment Failed: ' + errDesc);
            confirmBtn.disabled = false;
            confirmBtn.innerText = 'Pay via UPI / Card (Instant Confirmation)';
          });
          rzpInstance.open();
        }
      } catch (err) {
        alert('Checkout error: ' + err.message);
        confirmBtn.disabled = false;
        confirmBtn.innerText = 'Pay via UPI / Card (Instant Confirmation)';
      }
    };
  }

  modal.classList.add('active');
};

// ==============================================================================
// 4. Sitewide Report Evaluation HUD & Progressive Timer Engine
// ==============================================================================

const EVALUATION_CONFIGS = {
  equity: {
    badge: 'Fundamental Equity Engine',
    title: (ticker) => `Evaluating Equity Dossier: ${ticker || 'Selected Company'}`,
    stages: [
      { maxSec: 7, stage: "Step 1/4: Ingesting BSE Filings & L2 Depth", msg: "Ingesting verified corporate filings from BSE and parsing Level-2 order book depth..." },
      { maxSec: 16, stage: "Step 2/4: Executing 7-Pillar Cortex & Sieve", msg: "Running Chanakya clean-room filter, DuPont ROE decomposition, and promoter pledge audits..." },
      { maxSec: 25, stage: "Step 3/4: Solving Reverse DCF & Valuation", msg: "Computing implied market growth rate vs. 12% WACC hurdle rate and sector benchmarks..." },
      { maxSec: 30, stage: "Step 4/4: Finalizing Thesis", msg: "Assembling Countercase failure modes, statutory footnotes, and executive dossier..." }
    ]
  },
  fund: {
    badge: 'Mutual Fund Look-Through Engine',
    title: (code) => `Evaluating Mutual Fund Dossier: ${code || 'Selected Scheme'}`,
    stages: [
      { maxSec: 7, stage: "Step 1/4: Ingesting AMFI Portfolios & NAVs", msg: "Ingesting verified AMFI scheme portfolio disclosures, NAV time-series, and category baselines..." },
      { maxSec: 16, stage: "Step 2/4: Decomposing Constituents & Active Share", msg: "Auditing constituent equity & debt weights, style drift, and closet-indexing divergence..." },
      { maxSec: 25, stage: "Step 3/4: Stress-Testing ASRI & 10Y Fee Drag", msg: "Calculating accounting stress risk index and 10-year Direct vs Regular TER cost..." },
      { maxSec: 30, stage: "Step 4/4: Generating Health Scorecard", msg: "Aggregating 7-pillar weighted moat distribution and composite look-through health score..." }
    ]
  },
  debt: {
    badge: 'Fixed Income & Credit Solvency Engine',
    title: (isin) => `Evaluating Credit Dossier: ${isin || 'Selected Bond'}`,
    stages: [
      { maxSec: 7, stage: "Step 1/4: Ingesting BSE Debt & Rating Registry", msg: "Querying BSE Debt / SEBI OBPP registry and parsing credit rating agency monitoring rationales..." },
      { maxSec: 16, stage: "Step 2/4: Calculating YTM & Macaulay Duration", msg: "Computing statutory Yield to Maturity (YTM), interest rate shock sensitivities, and cash flows..." },
      { maxSec: 25, stage: "Step 3/4: Auditing Recovery Seniority & Contagion", msg: "Evaluating statutory IBC recovery hierarchy, collateral coverage, and equity contagion radar..." },
      { maxSec: 30, stage: "Step 4/4: Formulating Solvency Rating Posture", msg: "Generating 5-pillar credit solvency score, debt service coverage (DSCR), and credit summary..." }
    ]
  },
  compare: {
    badge: 'Cross-Company Disparity Comparator',
    title: (pair) => `Benchmarking Peer Disparity: ${pair || 'Selected Peers'}`,
    stages: [
      { maxSec: 7, stage: "Step 1/4: Ingesting Dual-Entity Exchange Filings", msg: "Parsing audited statutory financials, P/E multiples, and balance sheet schedules for both entities..." },
      { maxSec: 16, stage: "Step 2/4: Decomposing Comparative Capital Moats", msg: "Benchmarking DuPont ROE drivers, ROCE persistence, operating leverage, and liquidity buffers..." },
      { maxSec: 25, stage: "Step 3/4: Gating Valuation Disparity Triggers", msg: "Auditing relative valuation spread, Reverse DCF implied growth differentials, and market hurdles..." },
      { maxSec: 30, stage: "Step 4/4: Compiling Comparison Verdict", msg: "Generating 3-tier disparity diagnostic table, key trade-offs, and relative risk-reward summary..." }
    ]
  },
  opportunity: {
    badge: 'Multi-Asset Arbitrage Scanner',
    title: (name) => `Evaluating Multi-Asset Opportunity: ${name || 'Selected Opportunity'}`,
    stages: [
      { maxSec: 7, stage: "Step 1/4: Parsing Multi-Asset Yield Spreads", msg: "Scanning equity earnings yields, bond spreads, sovereign curve rates, and real asset distributions..." },
      { maxSec: 16, stage: "Step 2/4: Computing Post-Tax Hurdle Rates", msg: "Deducting statutory LTCG/STCG tax drag and CPI inflation hurdles from nominal yields..." },
      { maxSec: 25, stage: "Step 3/4: Stress-Testing Capital Recovery", msg: "Benchmarking asset coverage ratios, insolvency recovery tiers, and liquidity lock-in rules..." },
      { maxSec: 30, stage: "Step 4/4: Rendering Risk-Adjusted Matrix", msg: "Compiling multi-asset opportunity matrix, tax efficiency profile, and tactical allocator verdict..." }
    ]
  },
  macro: {
    badge: 'National Macro & Asset Monitoring',
    title: (name) => `Evaluating Market Intelligence: ${name || 'Terminal Feed'}`,
    stages: [
      { maxSec: 7, stage: "Step 1/4: Ingesting Official Regulatory Data", msg: "Connecting to RBI, AMFI, CCIL, and exchange feeds for live curve and pricing quotes..." },
      { maxSec: 16, stage: "Step 2/4: Calibrating Yields & Valuation Spreads", msg: "Evaluating tenor term premia, sovereign spreads, and historical percentile corridors..." },
      { maxSec: 25, stage: "Step 3/4: Calculating Accounting Stress Metrics", msg: "Auditing tracking error, premium/discount to NAV, and shadow-banking contagion risk..." },
      { maxSec: 30, stage: "Step 4/4: Assembling Terminal View", msg: "Rendering interactive analytics, sovereign curve visualizations, and diagnostic scorecards..." }
    ]
  },
  unlock: {
    badge: 'Cryptographic Entitlement Engine',
    title: (target) => `Unlocking Deep-Dive: ${target || 'Security'}`,
    stages: [
      { maxSec: 5, stage: "Step 1/3: Verifying Cryptographic Entitlement", msg: "Validating research credit balance, authorizing ledger transaction, and securing session tokens..." },
      { maxSec: 10, stage: "Step 2/3: Decrypting Forensic Accounting Schedules", msg: "Unlocking 7-pillar forensic accounting ledger, Beneish M-score breakdowns, and Reverse DCF sandbox..." },
      { maxSec: 15, stage: "Step 3/3: Assembling PDF Report Package", msg: "Generating high-resolution SVG charts, printable schedules, and refreshing dossier view..." }
    ]
  }
};

let _globalEvaluationTimer = null;

window.showEvaluationHUD = function(options = {}) {
  const overlay = document.getElementById('synthesizingOverlay');
  if (!overlay) return;

  const overlayTitle = document.getElementById('overlayTickerTitle');
  const overlayBadge = document.getElementById('overlayAssetBadge');
  const overlayBar = document.getElementById('overlayProgressBar');
  const overlayStage = document.getElementById('overlayProgressStage');
  const overlayTime = document.getElementById('overlayProgressTime');
  const overlayStatusMsg = document.getElementById('overlayStatusMsg');

  const assetType = options.assetType || 'equity';
  const cfg = EVALUATION_CONFIGS[assetType] || EVALUATION_CONFIGS.equity;
  const targetName = options.ticker || options.name || options.title || 'Security';

  if (overlayBadge) {
    overlayBadge.innerText = cfg.badge;
  }
  if (overlayTitle) {
    overlayTitle.innerText = options.customTitle || cfg.title(targetName);
  }

  const maxSeconds = options.totalSec || 30;

  if (overlayBar) overlayBar.style.width = '14%';
  if (overlayTime) overlayTime.innerText = `0s / ~${maxSeconds}s`;
  if (overlayStage) overlayStage.innerText = cfg.stages[0].stage;
  if (overlayStatusMsg) overlayStatusMsg.innerText = cfg.stages[0].msg;

  overlay.classList.add('active');

  if (_globalEvaluationTimer) {
    clearInterval(_globalEvaluationTimer);
    _globalEvaluationTimer = null;
  }

  const startMs = Date.now();

  _globalEvaluationTimer = setInterval(() => {
    const elapsedSec = Math.floor((Date.now() - startMs) / 1000);
    const cappedSec = Math.min(maxSeconds, elapsedSec);
    const pct = Math.min(96, 14 + (cappedSec / maxSeconds) * 82);

    if (overlayBar) overlayBar.style.width = `${pct.toFixed(1)}%`;
    if (overlayTime) overlayTime.innerText = `${cappedSec}s / ~${maxSeconds}s`;

    const currentStage = cfg.stages.find(s => cappedSec <= s.maxSec) || cfg.stages[cfg.stages.length - 1];
    if (overlayStage && currentStage) overlayStage.innerText = currentStage.stage;
    if (overlayStatusMsg && currentStage) overlayStatusMsg.innerText = currentStage.msg;
  }, 250);
};

window.hideEvaluationHUD = function() {
  if (_globalEvaluationTimer) {
    clearInterval(_globalEvaluationTimer);
    _globalEvaluationTimer = null;
  }
  const overlay = document.getElementById('synthesizingOverlay');
  if (overlay) {
    overlay.classList.remove('active');
  }
};

/**
 * Safely extract a human-readable string from FastAPI error responses
 * (handles string `detail`, structured `{detail: {error, message}}` objects,
 * validation error arrays, top-level `message`, and top-level `error`).
 */
function extractApiError(data, fallbackMessage = 'An unexpected error occurred.') {
  if (!data) return fallbackMessage;
  if (typeof data === 'string') return data;
  if (typeof data.detail === 'string') return data.detail;
  if (data.detail && typeof data.detail === 'object') {
    if (Array.isArray(data.detail)) {
      const msgs = data.detail
        .map(d => {
          if (!d) return '';
          if (typeof d === 'string') return d;
          if (d.msg) return `${d.loc ? d.loc.slice(-1)[0] + ': ' : ''}${d.msg}`;
          return JSON.stringify(d);
        })
        .filter(Boolean);
      if (msgs.length > 0) return msgs.join(', ');
    }
    if (typeof data.detail.message === 'string') return data.detail.message;
    if (typeof data.detail.error === 'string') return data.detail.error;
  }
  if (typeof data.message === 'string') return data.message;
  if (typeof data.error === 'string') return data.error;
  return fallbackMessage;
}
window.extractApiError = extractApiError;

window.synthesizeReport = async function(ticker, forceRefresh = false) {
  if (!ticker) return;

  const user = getStoredUser();
  if (!user || !user.id) {
    alert('Please sign in first to generate stock reports. You will receive 2 free research credits.');
    openSignInModal();
    return;
  }

  const balance = parseFloat(user.credits_balance) || 0;
  if (balance < 1) {
    if (confirm(`You need at least 1 research credit to generate a new dossier.\n\nCurrent balance: ${balance} credits.\n\nWould you like to visit the Pricing page to top up credits?`)) {
      if (typeof openPricingModal === 'function') {
        openPricingModal();
      } else {
        window.location.href = '/pricing';
      }
    }
    return;
  }

  const actionDesc = forceRefresh ? `Refresh and re-synthesize the 7-pillar stock report for ${ticker}?` : `Generate a fresh 7-pillar stock report for ${ticker}?`;
  if (!confirm(`${actionDesc}\n\nThis will consume 1 research credit.\nCurrent balance: ${balance} credits.`)) {
    return;
  }

  const buttons = document.querySelectorAll(`button[onclick*="synthesizeReport('${ticker}')"], #synthesizeBtn`);
  const originalTexts = [];
  buttons.forEach((btn, idx) => {
    originalTexts[idx] = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = `<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Generating Report (15-30s)...`;
  });

  // Show the evaluation HUD with progressive timer & background info
  if (typeof window.showEvaluationHUD === 'function') {
    window.showEvaluationHUD({ assetType: 'equity', ticker, customTitle: `Generating Report: ${ticker}`, totalSec: 30 });
  }

  try {
    const resp = await fetch('/api/synthesize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ticker: ticker,
        user_id: user.id,
        force_refresh: !!forceRefresh
      })
    });

    let data = {};
    try {
      data = await resp.json();
    } catch (_) {
      data = {};
    }

    if (typeof window.hideEvaluationHUD === 'function') window.hideEvaluationHUD();

    if (resp.ok && (data.success || data.status === 'success')) {
      // Update local credits atomically (supports new_balance and remaining_credits)
      const newBal = typeof data.new_balance === 'number' ? data.new_balance : (typeof data.remaining_credits === 'number' ? data.remaining_credits : undefined);
      if (typeof newBal === 'number') {
        user.credits_balance = newBal;
        user.credits = newBal;
        localStorage.setItem('sr_user', JSON.stringify(user));
        syncUserSession();
        if (typeof updateNavAuthUI === 'function') updateNavAuthUI(user);
      }

      if (data.already_exists) {
        alert('✅ ' + (data.message || `Dossier for ${ticker} is already available.`));
      } else {
        alert('🎉 ' + (data.message || `Dossier for ${ticker} compiled successfully!`));
      }

      // Navigate directly to the newly generated dossier
      const targetUrl = data.dossier_url || data.redirect_url || `/dossier/${encodeURIComponent(ticker)}`;
      window.location.href = targetUrl;
      return;
    }

    const errMsg = extractApiError(data, 'Report generation failed. Please try again.');
    if (resp.status === 402 || (data.detail && data.detail.error === 'INSUFFICIENT_CREDITS')) {
      if (confirm(`${errMsg}\n\nWould you like to purchase more credits on the Pricing page?`)) {
        if (typeof openPricingModal === 'function') {
          openPricingModal();
        } else {
          window.location.href = '/pricing';
        }
      }
    } else if (resp.status === 401 || resp.status === 403) {
      localStorage.removeItem('sr_user');
      if (typeof updateNavAuthUI === 'function') updateNavAuthUI(null);
      alert(errMsg || 'Your session has expired. Please sign in again.');
      openSignInModal();
    } else {
      alert(`Report Alert: ${errMsg}`);
    }

    // Refresh balance in background in case of refund
    if (typeof refreshUserBalance === 'function') {
      await refreshUserBalance(user);
    }
  } catch (err) {
    if (typeof window.hideEvaluationHUD === 'function') window.hideEvaluationHUD();
    console.error('Report request failed:', err);
    alert('Network error while requesting your report. Please try again.');
    if (typeof refreshUserBalance === 'function') {
      await refreshUserBalance(user);
    }
  } finally {
    buttons.forEach((btn, idx) => {
      btn.disabled = false;
      if (originalTexts[idx]) btn.innerHTML = originalTexts[idx];
    });
  }
};

// ==============================================================================
// 4b. Deep-Dive Unlock — Consumes 1 Credit to unlock Pillars 03 & 05 & PDF
// ==============================================================================

window.unlockDeepDive = async function(ticker) {
  const cleanTicker = (ticker || '').trim().toUpperCase();
  if (!cleanTicker) return;

  const user = getStoredUser();
  if (!user || !user.id) {
    alert('Sign in required to unlock deep dives. You will receive 2 free welcome research credits on registration.');
    openSignInModal();
    return;
  }

  const balance = parseFloat(user.credits_balance) || 0;
  if (balance < 1) {
    if (confirm(`Unlocking the Deep-Dive (Forensic Accounting Ledger, Reverse DCF & PDF Report Export) requires 1 research credit.\n\nCurrent balance: ${balance} credits.\n\nWould you like to visit the Pricing page to top up credits?`)) {
      if (typeof openPricingModal === 'function') {
        openPricingModal();
      } else {
        window.location.href = '/pricing';
      }
    }
    return;
  }

  if (!confirm(`Unlock the full Deep-Dive for ${cleanTicker}?\n\nThis permanently unlocks Pillar 03 (Accounting Check), Pillar 05 (Reverse DCF Sandbox), and full PDF download for this equity.\n\nCost: 1 Research Credit\nCurrent Balance: ${balance} credits`)) {
    return;
  }

  const btn = document.getElementById('unlockDeepDiveBtn') || (typeof event !== 'undefined' && event?.currentTarget ? event.currentTarget : null);
  let origHtml = '';
  if (btn) {
    origHtml = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Unlocking Deep-Dive...';
  }

  if (typeof window.showEvaluationHUD === 'function') {
    window.showEvaluationHUD({ assetType: 'unlock', ticker: cleanTicker, totalSec: 15 });
  }

  try {
    const resp = await fetch(`/api/dossier/unlock/${cleanTicker}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ticker: cleanTicker,
        user_id: user.id
      })
    });

    let data = {};
    try {
      data = await resp.json();
    } catch (_) {
      data = {};
    }

    if (typeof window.hideEvaluationHUD === 'function') window.hideEvaluationHUD();

    if (resp.ok && (data.success || data.status === 'success')) {
      const newBal = typeof data.new_balance === 'number' ? data.new_balance : (typeof data.remaining_credits === 'number' ? data.remaining_credits : undefined);
      if (typeof newBal === 'number') {
        user.credits_balance = newBal;
        user.credits = newBal;
        localStorage.setItem('sr_user', JSON.stringify(user));
        syncUserSession();
        if (typeof updateNavAuthUI === 'function') updateNavAuthUI(user);
      }
      alert(`🎉 ${data.message || `Deep-Dive for ${cleanTicker} unlocked successfully!`}\n\nRemaining Balance: ${user.credits_balance} credits.`);
      window.location.reload();
      return;
    }

    const errMsg = extractApiError(data, 'Could not unlock Deep-Dive.');
    if (resp.status === 402 || (data.detail && data.detail.error === 'INSUFFICIENT_CREDITS')) {
      if (confirm(`${errMsg}\n\nWould you like to purchase more credits on the Pricing page?`)) {
        if (typeof openPricingModal === 'function') {
          openPricingModal();
        } else {
          window.location.href = '/pricing';
        }
      }
    } else if (resp.status === 401 || resp.status === 403) {
      localStorage.removeItem('sr_user');
      if (typeof updateNavAuthUI === 'function') updateNavAuthUI(null);
      alert(errMsg || 'Your session has expired. Please sign in again.');
      openSignInModal();
    } else {
      alert('❌ ' + errMsg);
    }
  } catch (err) {
    if (typeof window.hideEvaluationHUD === 'function') window.hideEvaluationHUD();
    console.error('Unlock error:', err);
    alert('Network error while processing deep-dive unlock: ' + err.message);
  } finally {
    if (btn) {
      btn.disabled = false;
      if (origHtml) btn.innerHTML = origHtml;
    }
  }
};

// Mutual Fund / Corporate Debt Deep Dive unlock (1 credit, permanent per scheme or security)
window.unlockAssetDeepDive = async function(kind, assetId) {
  const cleanKind = (kind || '').toUpperCase();
  const cleanId = (assetId || '').trim();
  if (!cleanId || !['FUND', 'DEBT', 'REIT'].includes(cleanKind)) return;

  const user = getStoredUser();
  if (!user || !user.id) {
    alert('Sign in to unlock the Deep Dive. New accounts get 2 free welcome credits.');
    openSignInModal();
    return;
  }

  const balance = parseFloat(user.credits_balance) || 0;
  if (balance < 1) {
    if (confirm(`The Deep Dive costs 1 research credit and your balance is ${balance}.\n\nOpen the Pricing page to top up?`)) {
      if (typeof openPricingModal === 'function') {
        openPricingModal();
      } else {
        window.location.href = '/pricing';
      }
    }
    return;
  }

  const entityType = cleanKind === 'FUND' ? 'scheme' : (cleanKind === 'REIT' ? 'trust' : 'security');
  if (!confirm(`Unlock the Deep Dive for ${cleanId}?\n\nCost: 1 research credit (permanent for this ${entityType}).\nBalance: ${balance} credits.`)) {
    return;
  }

  const btn = (typeof event !== 'undefined' && event?.currentTarget ? event.currentTarget : null) || document.getElementById(`btnUnlock${cleanKind}`);
  let origHtml = '';
  if (btn) {
    origHtml = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Unlocking...';
  }

  if (typeof window.showEvaluationHUD === 'function') {
    window.showEvaluationHUD({ assetType: 'unlock', ticker: cleanId, totalSec: 15 });
  }

  const path = cleanKind === 'FUND' ? 'funds' : (cleanKind === 'REIT' ? 'reits' : 'debt');
  try {
    const resp = await fetch(`/api/${path}/unlock/${encodeURIComponent(cleanId)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: user.id })
    });
    let data = {};
    try {
      data = await resp.json();
    } catch (_) {
      data = {};
    }

    if (typeof window.hideEvaluationHUD === 'function') window.hideEvaluationHUD();

    if (resp.ok && (data.success || data.status === 'success')) {
      const newBal = typeof data.new_balance === 'number' ? data.new_balance : (typeof data.remaining_credits === 'number' ? data.remaining_credits : undefined);
      if (typeof newBal === 'number') {
        user.credits_balance = newBal;
        user.credits = newBal;
        localStorage.setItem('sr_user', JSON.stringify(user));
        syncUserSession();
        if (typeof updateNavAuthUI === 'function') updateNavAuthUI(user);
      }
      alert(`🎉 ${data.message || `Deep Dive unlocked for ${cleanId}!`}\n\nRemaining Balance: ${user.credits_balance} credits.`);
      window.location.reload();
      return;
    }

    const errMsg = extractApiError(data, 'Could not unlock asset deep-dive.');
    if (resp.status === 402 || (data.detail && data.detail.error === 'INSUFFICIENT_CREDITS')) {
      if (confirm(`${errMsg}\n\nOpen the Pricing page?`)) {
        if (typeof openPricingModal === 'function') {
          openPricingModal();
        } else {
          window.location.href = '/pricing';
        }
      }
    } else if (resp.status === 401 || resp.status === 403) {
      localStorage.removeItem('sr_user');
      if (typeof updateNavAuthUI === 'function') updateNavAuthUI(null);
      alert(errMsg || 'Your session has expired. Please sign in again.');
      openSignInModal();
    } else {
      alert('❌ ' + errMsg);
    }
  } catch (err) {
    if (typeof window.hideEvaluationHUD === 'function') window.hideEvaluationHUD();
    console.error('Asset unlock error:', err);
    alert('Network error while unlocking: ' + err.message);
  } finally {
    if (btn) {
      btn.disabled = false;
      if (origHtml) btn.innerHTML = origHtml;
    }
  }
};



// ==============================================================================
// 5. Authentication & User Session Management
// ==============================================================================

function initAuthModal() {
  const authModal = document.getElementById('authModal');
  const closeBtn = document.getElementById('closeAuthModalBtn');

  if (closeBtn && authModal) {
    closeBtn.addEventListener('click', () => {
      authModal.classList.remove('active');
    });
    authModal.addEventListener('click', (e) => {
      if (e.target === authModal) {
        authModal.classList.remove('active');
      }
    });
  }

  syncUserSession();

  // Background balance sync or session hydration on page load
  const user = getStoredUser();
  if (user && user.id) {
    refreshUserBalance(user);
  } else {
    // Attempt hydration from active HTTP session cookie
    fetch('/api/auth/me')
      .then(res => res.ok ? res.json() : null)
      .then(data => {
        if (data && data.authenticated && data.user) {
          localStorage.setItem('sr_user', JSON.stringify(data.user));
          syncUserSession();
          refreshUserBalance(data.user);
        }
      })
      .catch(() => {});
  }
}

window.openSignInModal = function() {
  const user = getStoredUser();
  if (user) {
    if (confirm(`Logged in as ${user.full_name} (${user.email})\nCredits Balance: ${user.credits_balance} Credits\n\nWould you like to sign out?`)) {
      fetch('/api/auth/signout', { method: 'POST' }).catch(() => {});
      localStorage.removeItem('sr_user');
      window.location.reload();
    }
    return;
  }
  const modal = document.getElementById('authModal');
  if (modal) modal.classList.add('active');
};

window.closeSignInModal = function() {
  const modal = document.getElementById('authModal');
  if (modal) modal.classList.remove('active');
};

let _authOtpRequested = false;

window.handleAuthFormSubmit = async function(e) {
  e.preventDefault();
  const emailInput = document.getElementById('authEmailInput');
  const otpGroup = document.getElementById('authOtpGroup');
  const otpInput = document.getElementById('authOtpInput');
  const submitBtn = document.getElementById('authSubmitBtn');
  const noticeEl = document.getElementById('authOtpNotice');

  if (!emailInput || !emailInput.value.trim()) return;
  const email = emailInput.value.trim().toLowerCase();

  if (!_authOtpRequested) {
    // Step 1: Request OTP
    submitBtn.disabled = true;
    submitBtn.innerText = 'Dispatching Verification Code...';

    try {
      const resp = await fetch('/api/auth/send-otp', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email })
      });
      const data = await resp.json();
      if (resp.ok && data.success) {
        _authOtpRequested = true;
        if (otpGroup) otpGroup.style.display = 'block';
        if (otpInput) {
          otpInput.required = true;
          otpInput.focus();
          if (data.test_code) otpInput.value = data.test_code;
        }
        if (noticeEl) {
          noticeEl.style.display = 'block';
          noticeEl.innerText = data.test_code 
            ? `✅ Test code: ${data.test_code} (auto-filled).` 
            : `📬 Verification code sent to ${email}. Valid for 10 minutes.`;
        }
        submitBtn.innerText = 'Verify & Claim 2 Credits →';
      } else {
        alert('Authentication Error: ' + extractApiError(data, 'Could not send verification code.'));
      }
    } catch (err) {
      alert('Authentication Error: ' + err.message);
    } finally {
      submitBtn.disabled = false;
      if (!_authOtpRequested) submitBtn.innerText = 'Send Verification Code →';
    }
  } else {
    // Step 2: Verify OTP
    const code = (otpInput?.value || '').trim();
    if (!code || code.length < 6) {
      alert('Please enter the 6-digit verification code.');
      if (otpInput) otpInput.focus();
      return;
    }

    submitBtn.disabled = true;
    submitBtn.innerText = 'Verifying Code & Authenticating...';

    try {
      const resp = await fetch('/api/auth/verify-otp', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email, code: code })
      });
      const data = await resp.json();
      if (resp.ok && data.success) {
        localStorage.setItem('sr_user', JSON.stringify(data.user));
        const modal = document.getElementById('authModal');
        if (modal) modal.classList.remove('active');
        syncUserSession();

        if (window._pendingCheckout) {
          const p = window._pendingCheckout;
          window._pendingCheckout = null;
          alert(`🎉 Welcome ${data.user.full_name}! 2 Free Welcome Credits have been claimed.\nOpening checkout for ${p.planName}...`);
          openCheckout(p.planId, p.planName, p.amountInr, p.credits);
          return;
        }

        alert(`🎉 Welcome ${data.user.full_name}! You have received 2 free research credits.`);
        window.location.reload();
      } else {
        alert('Verification Failed: ' + extractApiError(data, 'Invalid or expired code.'));
      }
    } catch (err) {
      alert('Verification Failed: ' + err.message);
    } finally {
      submitBtn.disabled = false;
      submitBtn.innerText = 'Verify & Claim 2 Credits →';
    }
  }
};

window.handleResendOtp = async function() {
  const emailInput = document.getElementById('authEmailInput');
  const noticeEl = document.getElementById('authOtpNotice');
  const email = emailInput?.value?.trim()?.toLowerCase();
  if (!email) return;

  try {
    const resp = await fetch('/api/auth/send-otp', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: email })
    });
    const data = await resp.json();
    if (resp.ok && data.success) {
      if (noticeEl) {
        noticeEl.style.display = 'block';
        noticeEl.innerText = data.test_code 
          ? `✅ New test code: ${data.test_code}` 
          : `📬 Fresh code dispatched to ${email}.`;
      }
      alert('A fresh verification code has been dispatched.');
    } else {
      alert('Notice: ' + extractApiError(data, 'Could not resend code.'));
    }
  } catch (err) {
    alert('Resend Error: ' + err.message);
  }
};

window.handleSignInSubmit = window.handleAuthFormSubmit;

window.sendAdminLoginOtp = window.sendAdminLoginOtp || async function() {
  const emailEl = document.getElementById('adminEmail');
  const pwdEl = document.getElementById('adminPassword');
  const btnEl = document.getElementById('sendAdminOtpBtn');
  const statusEl = document.getElementById('adminOtpStatus');
  const email = (emailEl && emailEl.value || '').trim().toLowerCase();
  if (!email || !email.includes('@')) {
    alert('Please enter your whitelisted admin email first.');
    if (emailEl) emailEl.focus();
    return;
  }
  if (btnEl) {
    btnEl.disabled = true;
    btnEl.textContent = 'Sending...';
  }
  try {
    const resp = await fetch('/api/auth/send-otp', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: email })
    });
    const data = await resp.json();
    if (resp.ok && data.success) {
      if (pwdEl) {
        pwdEl.type = 'text';
        pwdEl.placeholder = 'Enter 6-digit verification code from email';
        pwdEl.focus();
        if (data.test_code) pwdEl.value = data.test_code;
      }
      if (statusEl) {
        statusEl.style.display = 'block';
        statusEl.style.color = '#34d399';
        statusEl.textContent = '📬 6-digit verification code sent to ' + email + '. Enter it above to continue.';
      }
    } else if (statusEl) {
      statusEl.style.display = 'block';
      statusEl.style.color = '#f87171';
      statusEl.textContent = '❌ ' + (data.detail || data.message || 'Could not send verification code.');
    }
  } catch (e) {
    if (statusEl) {
      statusEl.style.display = 'block';
      statusEl.style.color = '#f87171';
      statusEl.textContent = '❌ Network error: ' + e.message;
    }
  } finally {
    if (btnEl) {
      btnEl.disabled = false;
      btnEl.textContent = 'Resend 6-Digit Code';
    }
  }
};

window.handleCountercaseSubmit = async function(e, ticker) {
  if (e) e.preventDefault();
  const vector = document.getElementById('countercaseVector')?.value || '';
  const notes = document.getElementById('countercaseNotes')?.value || '';
  const statusEl = document.getElementById('countercaseStatus');
  const btn = document.getElementById('btnCommitCountercase');

  if (btn) {
    btn.disabled = true;
    btn.innerText = 'Anchoring Anti-Thesis...';
  }

  try {
    const user = getStoredUser();
    const resp = await fetch('/api/countercase', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ticker: ticker,
        failure_vector: vector,
        anti_thesis_notes: notes,
        user_id: user ? user.id : 'guest_web_user'
      })
    });
    const data = await resp.json();
    if (resp.ok && data.success) {
      if (statusEl) {
        statusEl.innerText = '✅ Committed to Decision Ledger!';
        statusEl.style.color = 'var(--accent-emerald)';
      }
      alert(`🔒 ${data.message}`);
    } else {
      alert('Error: ' + extractApiError(data, 'Could not record.'));
    }
  } catch (err) {
    alert('Error recording pre-mortem: ' + err.message);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerText = '🔒 Save Countercase to Audit Ledger';
    }
  }
};

window.openThesisModal = function() {
  const modal = document.getElementById('thesisModalBackdrop');
  if (modal) {
    modal.style.display = 'flex';
  }
};

window.closeThesisModal = function() {
  const modal = document.getElementById('thesisModalBackdrop');
  if (modal) {
    modal.style.display = 'none';
  }
};

window.handleThesisCheckpointSubmit = async function(e, ticker) {
  if (e) e.preventDefault();
  const decisionEl = document.querySelector('input[name="thesisDecision"]:checked');
  const decision = decisionEl ? decisionEl.value : 'WOULD_BUY_TODAY';
  const rationale = document.getElementById('thesisRationale')?.value || '';
  const priceVal = parseFloat(document.getElementById('thesisCurrentPrice')?.value || '0');
  const statusEl = document.getElementById('thesisStatus');
  const btn = document.getElementById('btnCommitThesis');

  if (!rationale.trim()) {
    alert('Please enter an objective rationale before committing your thesis verdict.');
    return;
  }

  if (btn) {
    btn.disabled = true;
    btn.innerText = 'Committing Verdict...';
  }

  try {
    const user = getStoredUser();
    const resp = await fetch('/api/thesis-checkpoint', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ticker: ticker,
        decision: decision,
        rationale: rationale,
        current_price: priceVal,
        user_id: user ? user.id : 'guest_web_user'
      })
    });
    const data = await resp.json();
    if (resp.ok && data.success) {
      if (statusEl) {
        statusEl.innerText = '✅ Committed to Decision Ledger!';
        statusEl.style.color = 'var(--accent-emerald)';
      }
      alert(`⚖️ ${data.message}`);
      window.closeThesisModal();
    } else {
      alert('Error: ' + extractApiError(data, 'Could not record checkpoint.'));
    }
  } catch (err) {
    alert('Error recording thesis checkpoint: ' + err.message);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerText = '🔒 Commit to Ledger';
    }
  }
};

// Contact Form Submission Tactile Feedback & Double-Submit Guard
let _contactFormSubmitting = false;

window.handleContactTicketSubmit = function(e) {
  if (_contactFormSubmitting) {
    if (e && typeof e.preventDefault === 'function') {
      e.preventDefault();
    }
    return false;
  }

  const form = document.getElementById('contactTicketForm');
  if (form && typeof form.checkValidity === 'function' && !form.checkValidity()) {
    return true;
  }

  _contactFormSubmitting = true;

  const btn = document.getElementById('contactSubmitBtn');
  const btnIcon = document.getElementById('contactSubmitBtnIcon');
  const btnText = document.getElementById('contactSubmitBtnText');

  if (btnIcon) {
    btnIcon.innerText = '⏳';
  }
  if (btnText) {
    btnText.innerText = 'Sending Ticket...';
  }
  if (btn) {
    btn.style.opacity = '0.75';
    btn.style.cursor = 'not-allowed';
    btn.style.pointerEvents = 'none';
  }

  setTimeout(function() {
    if (btn) btn.disabled = true;
  }, 10);

  return true;
};

window.addEventListener('pageshow', function() {
  _contactFormSubmitting = false;
  const btn = document.getElementById('contactSubmitBtn');
  const btnIcon = document.getElementById('contactSubmitBtnIcon');
  const btnText = document.getElementById('contactSubmitBtnText');
  if (btn) {
    btn.disabled = false;
    btn.style.opacity = '';
    btn.style.cursor = '';
    btn.style.pointerEvents = '';
  }
  if (btnIcon) {
    btnIcon.innerText = '📨';
  }
  if (btnText) {
    btnText.innerText = 'Send Support Ticket';
  }
});

function getStoredUser() {
  try {
    const raw = localStorage.getItem('sr_user');
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

// Persistent Visitor Acquisition Attribution & Journey Tracking
function getTelemetrySessionId() {
  try {
    let sid = sessionStorage.getItem('sr_session_id');
    if (!sid) {
      sid = 'sess_' + Math.random().toString(36).substring(2, 9) + Date.now().toString(36);
      sessionStorage.setItem('sr_session_id', sid);
    }
    return sid;
  } catch {
    return 'sess_anonymous';
  }
}

function stripTrackingParams() {
  // Remove campaign tags from the visible URL after they have been captured, so a copied address-bar link is clean
  try {
    const url = new URL(window.location.href);
    let changed = false;
    ['utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content', 'ref', 'source'].forEach(function(k) {
      if (url.searchParams.has(k)) { url.searchParams.delete(k); changed = true; }
    });
    if (changed) window.history.replaceState(window.history.state, '', url.pathname + url.search + url.hash);
  } catch {}
}

function getAcquisitionData() {
  try {
    const params = new URLSearchParams(window.location.search);
    const hasCampaign = !!(params.get('utm_source') || params.get('ref') || params.get('source'));
    let data = sessionStorage.getItem('sr_acquisition');
    if (data && !hasCampaign) return JSON.parse(data);

    // Initial landing capture (or a fresh campaign/share link opened in an existing tab session)
    const ref = document.referrer || '';
    // Discard internal navigation from same origin
    const isInternal = ref && ref.startsWith(window.location.origin);
    const cleanRef = isInternal ? '' : ref;

    const acquisition = {
      referrer: cleanRef,
      landing_url: window.location.href,
      landing_path: window.location.pathname,
      utm_source: params.get('utm_source') || '',
      utm_medium: params.get('utm_medium') || '',
      utm_campaign: params.get('utm_campaign') || '',
      utm_term: params.get('utm_term') || '',
      utm_content: params.get('utm_content') || '',
      ref: params.get('ref') || params.get('source') || '',
      captured_at: new Date().toISOString()
    };
    sessionStorage.setItem('sr_acquisition', JSON.stringify(acquisition));
    stripTrackingParams();
    return acquisition;
  } catch {
    return {};
  }
}

window.trackUserEvent = function(eventType, ticker, details) {
  try {
    const user = getStoredUser();
    const acq = getAcquisitionData();
    const currentPath = window.location.pathname;
    const landingPath = acq.landing_path || currentPath;
    const mergedDetails = Object.assign({
      path: currentPath,
      landing_page: landingPath,
      landing_url: acq.landing_url || window.location.href,
      title: document.title || ''
    }, details || {});

    const payload = {
      event_type: eventType,
      ticker: ticker || '',
      user_id: user ? user.id : null,
      user_email: user ? user.email : null,
      session_id: getTelemetrySessionId(),
      referrer: acq.referrer || (document.referrer && !document.referrer.startsWith(window.location.origin) ? document.referrer : ''),
      landing_url: acq.landing_url || window.location.href,
      landing_page: landingPath,
      utm_source: acq.utm_source || '',
      utm_medium: acq.utm_medium || '',
      utm_campaign: acq.utm_campaign || '',
      ref: acq.ref || '',
      details: mergedDetails
    };
    fetch('/api/telemetry/event', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    }).catch(() => {});
  } catch {}
};

function formatActiveStudyClock(sec) {
  const s = Math.max(0, Math.floor(sec || 0));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}m ${r < 10 ? '0' : ''}${r}s`;
}

function initDwellAndTransitionTelemetry() {
  if (typeof window === 'undefined' || typeof document === 'undefined') return;
  if (window.location.pathname.startsWith('/admin')) return;

  const IDLE_CUTOFF_MS = 60000; // 60s idle cutoff: only count active reading attention
  let lastActivityTime = Date.now();
  let totalActiveSeconds = 0;
  let unsentActiveSeconds = 0;
  let maxScrollPct = 0;
  let unsentPillarDwell = {};

  // Detect Dossier Reading Container for User-Facing Progress Bar & Read Time Badge
  const dossierContainer = document.getElementById('dossierReadingContainer');
  const progressFill = document.getElementById('dossierReadingProgressFill');
  const estReadLabel = document.getElementById('dossierEstReadMinutes');
  const activeTimerLabel = document.getElementById('dossierActiveTimerText');

  if (dossierContainer && estReadLabel) {
    const rawWords = (dossierContainer.innerText || '').trim().split(/\s+/).filter(Boolean).length;
    const estMins = Math.max(2, Math.ceil(rawWords / 220));
    estReadLabel.textContent = `~${estMins} min read`;
  }

  function computeCurrentScrollPct() {
    const docEl = document.documentElement;
    const scrollTop = window.scrollY || docEl.scrollTop || 0;
    const scrollable = Math.max(1, (docEl.scrollHeight || 1) - window.innerHeight);
    const pct = Math.min(100, Math.max(0, Math.round((scrollTop / scrollable) * 100)));
    if (pct > maxScrollPct) maxScrollPct = pct;
    if (progressFill) {
      progressFill.style.width = `${pct}%`;
    }
    return pct;
  }

  function detectVisiblePillarLabel() {
    const candidates = document.querySelectorAll(
      'details.pillar-card[open], .pillar-section, .fund-dimension-card, [id^="pillar-"], #reverseDcfSandbox, #epistemicFalsificationCard'
    );
    if (!candidates || candidates.length === 0) return null;
    const vh = window.innerHeight || 800;
    let bestLabel = null;
    let bestOverlap = 0;

    candidates.forEach((el) => {
      const rect = el.getBoundingClientRect();
      const visibleTop = Math.max(0, rect.top);
      const visibleBottom = Math.min(vh, rect.bottom);
      const overlap = Math.max(0, visibleBottom - visibleTop);
      if (overlap > bestOverlap && overlap > 80) {
        bestOverlap = overlap;
        const heading = el.querySelector('summary, h2, h3, .pillar-title');
        let rawLabel = (
          el.getAttribute('data-pillar-label') ||
          (heading ? heading.textContent : '') ||
          el.id ||
          ''
        ).replace(/\s+/g, ' ').trim();
        if (el.id === 'reverseDcfSandbox') {
          rawLabel = 'Pillar 05 — Interactive Reverse DCF Sandbox';
        } else if (el.id === 'epistemicFalsificationCard') {
          rawLabel = 'Epistemic & Thesis Falsification Ledger';
        }
        if (rawLabel) {
          bestLabel = rawLabel.slice(0, 72);
        }
      }
    });
    return bestLabel;
  }

  function markActivity() {
    lastActivityTime = Date.now();
  }

  ['mousemove', 'mousedown', 'keydown', 'touchstart', 'click'].forEach((evtName) => {
    window.addEventListener(evtName, markActivity, { passive: true });
  });
  window.addEventListener('scroll', () => {
    markActivity();
    const curPct = computeCurrentScrollPct();
    if (activeTimerLabel) {
      activeTimerLabel.textContent = `${formatActiveStudyClock(totalActiveSeconds)} active • ${curPct}% read`;
    }
  }, { passive: true });

  computeCurrentScrollPct();

  // 1-second Active Reading Attention ticker (only ticks when tab is visible AND user interacted within 60s)
  const attentionInterval = setInterval(() => {
    if (document.visibilityState !== 'visible') return;
    if (Date.now() - lastActivityTime > IDLE_CUTOFF_MS) return;

    totalActiveSeconds += 1;
    unsentActiveSeconds += 1;

    const activePillar = detectVisiblePillarLabel();
    if (activePillar) {
      unsentPillarDwell[activePillar] = (unsentPillarDwell[activePillar] || 0) + 1;
    }

    if (activeTimerLabel) {
      const curPct = computeCurrentScrollPct();
      activeTimerLabel.textContent = `${formatActiveStudyClock(totalActiveSeconds)} active • ${curPct}% read`;
    }
  }, 1000);

  function sendDwellBeacon(destinationPath) {
    // Only dispatch when there is genuine active attention (>= 1s) or an explicit internal link transition
    if (unsentActiveSeconds < 1 && !destinationPath) return;
    const dwellToSend = Math.min(1800, Math.max(1, unsentActiveSeconds));
    const pillarSnapshot = Object.assign({}, unsentPillarDwell);

    // Reset unsent accumulators so subsequent reading in the same tab is captured incrementally
    unsentActiveSeconds = 0;
    unsentPillarDwell = {};

    try {
      const user = getStoredUser();
      const acq = getAcquisitionData();
      const currentPath = window.location.pathname;

      const payload = {
        event_type: 'PAGE_DWELL',
        ticker: '',
        user_id: user ? user.id : null,
        user_email: user ? user.email : null,
        session_id: getTelemetrySessionId(),
        referrer: acq.referrer || '',
        landing_url: acq.landing_url || window.location.href,
        landing_page: currentPath,
        path: currentPath,
        dwell_seconds: dwellToSend,
        max_scroll_pct: maxScrollPct,
        pillar_dwell: pillarSnapshot,
        details: {
          path: currentPath,
          dwell_seconds: dwellToSend,
          max_scroll_pct: maxScrollPct,
          pillar_dwell: pillarSnapshot,
          to_path: destinationPath || null,
          title: document.title || ''
        }
      };

      const blob = new Blob([JSON.stringify(payload)], { type: 'application/json' });
      if (navigator.sendBeacon) {
        navigator.sendBeacon('/api/telemetry/dwell', blob);
      } else {
        fetch('/api/telemetry/dwell', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
          keepalive: true
        }).catch(() => {});
      }
    } catch {}
  }

  document.addEventListener('click', (e) => {
    const link = e.target.closest('a[href]');
    if (!link) return;
    const href = link.getAttribute('href');
    if (!href || href.startsWith('#') || href.startsWith('javascript:') || href.startsWith('mailto:') || href.startsWith('tel:')) return;

    let targetPath = '';
    try {
      const url = new URL(href, window.location.origin);
      if (url.origin === window.location.origin) {
        targetPath = url.pathname;
      }
    } catch {}

    if (targetPath && targetPath !== window.location.pathname) {
      sendDwellBeacon(targetPath);
    }
  }, { capture: true, passive: true });

  window.addEventListener('pagehide', () => {
    clearInterval(attentionInterval);
    sendDwellBeacon(null);
  });

  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') {
      sendDwellBeacon(null);
    } else {
      lastActivityTime = Date.now();
    }
  });
}

function showShareToast(message) {
  const el = document.createElement('div');
  el.textContent = message;
  el.setAttribute('role', 'status');
  el.style.cssText = 'position:fixed;left:50%;bottom:28px;transform:translateX(-50%);background:#0f172a;color:#e2e8f0;border:1px solid rgba(14,165,233,0.5);padding:10px 18px;border-radius:10px;font-size:13px;font-weight:600;z-index:10000;box-shadow:0 8px 30px rgba(0,0,0,0.4);';
  document.body.appendChild(el);
  setTimeout(function() { el.remove(); }, 2600);
}

window.shareCurrentPage = async function(kind) {
  try {
    // Prefer the canonical origin so links shared from a preview/render URL still point at the real domain
    let origin = window.location.origin;
    const canon = document.querySelector('link[rel="canonical"]');
    if (canon && canon.href) { origin = new URL(canon.href).origin; }

    const url = new URL(origin + window.location.pathname);
    if (window.location.pathname === '/compare') {
      const cur = new URLSearchParams(window.location.search);
      if (cur.get('a')) url.searchParams.set('a', cur.get('a'));
      if (cur.get('b')) url.searchParams.set('b', cur.get('b'));
    }
    url.searchParams.set('utm_source', 'share');
    url.searchParams.set('utm_medium', 'referral');
    url.searchParams.set('utm_campaign', kind || 'page');
    const link = url.toString();
    const title = document.title || 'Moatnomics';

    let method = 'copy';
    if (navigator.share) {
      try {
        await navigator.share({ title: title, text: title, url: link });
        method = 'native';
      } catch (err) {
        if (err && err.name === 'AbortError') return;
        method = 'copy';
      }
    }
    if (method === 'copy') {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(link);
      } else {
        const ta = document.createElement('textarea');
        ta.value = link; document.body.appendChild(ta); ta.select();
        document.execCommand('copy'); ta.remove();
      }
      showShareToast('Link copied. Recipients see the public report; unlocked sections stay with your account.');
    }
    const parts = window.location.pathname.split('/');
    window.trackUserEvent('share_click', kind === 'dossier' ? (parts[2] || '') : '', { method: method, kind: kind || 'page' });
  } catch {
    showShareToast('Could not copy the link. Please copy it from the address bar.');
  }
};

// Track initial page view with logged-in user attribution and source retention
(function initUserTelemetry() {
  const acq = getAcquisitionData();
  const path = window.location.pathname;
  let pageEvent = 'page_view';
  let currentTicker = '';
  if (path.startsWith('/dossier/')) {
    pageEvent = 'dossier_view';
    currentTicker = path.split('/')[2];
  } else if (path.startsWith('/funds/')) {
    pageEvent = 'fund_view';
  } else if (path.startsWith('/debt/')) {
    pageEvent = 'debt_view';
  } else if (path === '/funds') {
    pageEvent = 'funds_directory_view';
  } else if (path === '/debt') {
    pageEvent = 'debt_directory_view';
  } else if (path === '/compare') {
    pageEvent = 'compare_view';
  } else if (path === '/discovery') {
    pageEvent = 'discovery_view';
  } else if (path === '/pricing') {
    pageEvent = 'pricing_view';
  } else if (path === '/opportunities') {
    pageEvent = 'opportunities_view';
  } else if (path === '/reits') {
    pageEvent = 'reits_view';
  } else if (path === '/sovereign' || path === '/sovereign-curve') {
    pageEvent = 'sovereign_view';
  } else if (path === '/safety-radar') {
    pageEvent = 'safety_radar_view';
  }
  setTimeout(() => window.trackUserEvent(pageEvent, currentTicker, {
    path: path,
    landing_page: acq.landing_path || path,
    title: document.title || ''
  }), 300);
})();

/**
 * Fetches the latest user profile/balance from the server and updates localStorage.
 * Called on page load and after payments/syntheses to ensure credits are always accurate.
 */
async function refreshUserBalance(user) {
  if (!user || !user.id) return;
  try {
    const resp = await fetch(`/api/user/${encodeURIComponent(user.id)}`);
    if (resp.ok) {
      const data = await resp.json();
      const freshUser = (data && data.user) ? data.user : data;
      if (freshUser && (freshUser.id || freshUser.email)) {
        localStorage.setItem('sr_user', JSON.stringify(freshUser));
        updateNavAuthUI(freshUser);
        syncUserSession();
      }
    } else if (resp.status === 401 || resp.status === 403 || resp.status === 404) {
      // Session cookie expired or invalidated — clear stale client state
      localStorage.removeItem('sr_user');
      updateNavAuthUI(null);
      syncUserSession();
    }
  } catch (err) {
    console.warn('Could not refresh user balance:', err);
  }
}
window.refreshUserBalance = refreshUserBalance;

/**
 * Updates navbar and modal authentication triggers based on current session.
 */
function updateNavAuthUI(user) {
  const navBtn = document.getElementById('navSignInBtn');
  if (navBtn) {
    if (user && user.id) {
      const bal = user.credits_balance !== undefined ? user.credits_balance : (user.credits !== undefined ? user.credits : 0);
      navBtn.innerText = `👤 ${user.full_name || 'Account'} (${bal} Credits)`;
      navBtn.classList.remove('btn-primary');
      navBtn.classList.add('btn-secondary');
    } else {
      navBtn.innerHTML = '<span>Sign In / 2 Credits</span>';
      navBtn.classList.remove('btn-primary');
      navBtn.classList.add('btn-secondary');
    }
  }

  const modalBal = document.getElementById('generateModalCreditsText');
  if (modalBal) {
    if (user && user.id) {
      const bal = user.credits_balance !== undefined ? user.credits_balance : (user.credits !== undefined ? user.credits : 0);
      modalBal.innerText = `${bal} Credits Available`;
    } else {
      modalBal.innerText = '2 Free Credits on Sign In';
    }
  }
}
window.updateNavAuthUI = updateNavAuthUI;

function syncUserSession() {
  const user = getStoredUser();
  updateNavAuthUI(user);
}
window.syncUserSession = syncUserSession;

// ==============================================================================
// 7. Responsive Navigation, Dropdown Sub-Tabs & Mobile Drawer
// ==============================================================================
function initNavigationDropdowns() {
  const dropdownToggles = document.querySelectorAll('.nav-item.dropdown .dropdown-toggle');

  dropdownToggles.forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const parent = btn.closest('.nav-item.dropdown');
      if (!parent) return;

      const isOpen = parent.classList.contains('open');

      // Close all other dropdowns
      document.querySelectorAll('.nav-item.dropdown.open').forEach(d => {
        if (d !== parent) {
          d.classList.remove('open');
          const toggle = d.querySelector('.dropdown-toggle');
          if (toggle) toggle.setAttribute('aria-expanded', 'false');
        }
      });

      // Toggle current dropdown
      if (isOpen) {
        parent.classList.remove('open');
        btn.setAttribute('aria-expanded', 'false');
      } else {
        parent.classList.add('open');
        btn.setAttribute('aria-expanded', 'true');
      }
    });

    // Keyboard support: Escape closes dropdown
    btn.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        const parent = btn.closest('.nav-item.dropdown');
        if (parent && parent.classList.contains('open')) {
          parent.classList.remove('open');
          btn.setAttribute('aria-expanded', 'false');
          btn.focus();
        }
      }
    });
  });

  // Close open dropdowns when clicking outside
  document.addEventListener('click', (e) => {
    if (!e.target.closest('.nav-item.dropdown')) {
      document.querySelectorAll('.nav-item.dropdown.open').forEach(d => {
        d.classList.remove('open');
        const toggle = d.querySelector('.dropdown-toggle');
        if (toggle) toggle.setAttribute('aria-expanded', 'false');
      });
    }
  });

  // Close dropdowns on global Escape key
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      document.querySelectorAll('.nav-item.dropdown.open').forEach(d => {
        d.classList.remove('open');
        const toggle = d.querySelector('.dropdown-toggle');
        if (toggle) toggle.setAttribute('aria-expanded', 'false');
      });
    }
  });
}

function toggleMobileMenu() {
  const nav = document.getElementById('mainNav');
  const btn = document.getElementById('mobileMenuBtn');
  if (!nav) return;
  const isOpen = nav.classList.toggle('mobile-open');
  if (btn) btn.classList.toggle('active', isOpen);
}

// Close mobile menu on click outside or on non-dropdown nav link
document.addEventListener('click', (e) => {
  const nav = document.getElementById('mainNav');
  const btn = document.getElementById('mobileMenuBtn');
  if (nav && nav.classList.contains('mobile-open')) {
    if (!nav.contains(e.target) && (!btn || !btn.contains(e.target))) {
      nav.classList.remove('mobile-open');
      if (btn) btn.classList.remove('active');
    }
  }
});

// ==============================================================================
// 8. 7-Pillar Accordion Minimise / Maximise Controls
// ==============================================================================
function toggleAllPillars(expand) {
  const accordions = document.querySelectorAll('details.pillar-accordion');
  accordions.forEach(el => {
    el.open = expand;
  });
  const expandBtn = document.getElementById('btnExpandAllPillars');
  const collapseBtn = document.getElementById('btnCollapseAllPillars');
  if (expandBtn && collapseBtn) {
    if (expand) {
      expandBtn.classList.add('active');
      collapseBtn.classList.remove('active');
    } else {
      collapseBtn.classList.add('active');
      expandBtn.classList.remove('active');
    }
  }
}

function toggleAllFundPillars(expand) {
  const accordions = document.querySelectorAll('#fundDossierPillars details.pillar-accordion, details.pillar-accordion');
  accordions.forEach(el => {
    el.open = expand;
  });
  const expandBtn = document.getElementById('btnExpandAllFundPillars');
  const collapseBtn = document.getElementById('btnCollapseAllFundPillars');
  if (expandBtn && collapseBtn) {
    if (expand) {
      expandBtn.classList.add('active');
      collapseBtn.classList.remove('active');
    } else {
      collapseBtn.classList.add('active');
      expandBtn.classList.remove('active');
    }
  }
}

// ==============================================================================
// 9. Instant Hover Prefetching for Fluid Navigation
// ==============================================================================
(function initLinkPrefetching() {
  const prefetched = new Set();
  function prefetchUrl(url) {
    if (!url || prefetched.has(url) || url.startsWith('http') || url.includes('#') || url.includes('/api/')) return;
    prefetched.add(url);
    const link = document.createElement('link');
    link.rel = 'prefetch';
    link.href = url;
    document.head.appendChild(link);
  }

  document.addEventListener('mouseover', (e) => {
    const a = e.target.closest('a');
    if (a && a.getAttribute('href') && a.getAttribute('href').startsWith('/')) {
      prefetchUrl(a.getAttribute('href'));
    }
  }, { passive: true });

  document.addEventListener('touchstart', (e) => {
    const a = e.target.closest('a');
    if (a && a.getAttribute('href') && a.getAttribute('href').startsWith('/')) {
      prefetchUrl(a.getAttribute('href'));
    }
  }, { passive: true });
})();

// ==============================================================================
// 10. Monitoring Feed Controller (Phase 4)
// ==============================================================================
async function toggleMonitoringFeed() {
  const modal = document.getElementById('monitoringModal');
  if (!modal) return;
  const isHidden = modal.style.display === 'none' || !modal.style.display;
  if (isHidden) {
    modal.style.display = 'block';
    loadMonitoringEvents();
  } else {
    modal.style.display = 'none';
  }
}

async function loadMonitoringEvents() {
  const container = document.getElementById('monitoringEventsList');
  if (!container) return;
  container.innerHTML = '<div style="color: #94a3b8; font-size: 12.5px; padding: 16px; text-align: center;">Loading real-time autonomous feed...</div>';
  try {
    const res = await fetch('/api/autonomous/events?limit=8');
    const data = await res.json();
    const events = data.events || [];
    if (!events.length) {
      container.innerHTML = '<div style="color: #94a3b8; font-size: 12.5px; padding: 16px; text-align: center;">No recent autonomous events recorded. System active.</div>';
      return;
    }
    container.innerHTML = events.map(evt => {
      const typeIcons = {
        'DAILY_FUND_AUDIT': '🔍',
        'AMFI_NAV_SYNC': '📊',
        'bse_material_filing': '🚨',
        'bse_reaudit_completed': '⚡'
      };
      const icon = typeIcons[evt.event_type] || '🤖';
      return `
        <div style="background: rgba(30, 41, 59, 0.6); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 8px; padding: 12px; font-size: 12.5px;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
            <div style="display: flex; align-items: center; gap: 6px;">
              <span>${icon}</span>
              <strong style="color: #f8fafc;">${evt.ticker || 'SYSTEM'}</strong>
              <span style="font-size: 10px; padding: 2px 6px; border-radius: 4px; background: rgba(14, 165, 233, 0.15); color: #38bdf8; font-weight: 700;">${(evt.action_taken || evt.event_type).replace(/_/g, ' ')}</span>
            </div>
            <span style="font-size: 11px; color: #64748b;">${(evt.created_at || '').slice(0, 16)}</span>
          </div>
          <div style="color: #cbd5e1; line-height: 1.4; font-size: 12px;">${evt.summary || 'Autonomous task executed successfully.'}</div>
        </div>
      `;
    }).join('');
  } catch (err) {
    container.innerHTML = '<div style="color: #ef4444; font-size: 12.5px; padding: 12px;">Failed to load events. Please try again.</div>';
  }
}

// ==============================================================================
// Instant Dossier Hover Prefetcher & Tactile Click Feedback
// ==============================================================================
const _prefetchedDossierUrls = new Set();

function prefetchDossierUrl(url) {
  if (!url || _prefetchedDossierUrls.has(url)) return;
  _prefetchedDossierUrls.add(url);
  const link = document.createElement('link');
  link.rel = 'prefetch';
  link.href = url;
  document.head.appendChild(link);
}

document.addEventListener('mouseover', (e) => {
  const a = e.target.closest('a');
  if (a && a.href && a.origin === window.location.origin) {
    const p = a.pathname;
    if (p.startsWith('/dossier/') || p.startsWith('/funds/') || p.startsWith('/debt/') || p.startsWith('/opportunities')) {
      prefetchDossierUrl(p);
    }
  }
}, { passive: true });

// ==============================================================================
// 30-Second Progressive Fill Loading Animation & BFCache Navigation Lifecycle
// ==============================================================================
const _activeProgressButtons = new Set();

function resetButtonProgressFill(btn) {
  if (!btn) return;
  if (btn._progressInterval) {
    clearInterval(btn._progressInterval);
    btn._progressInterval = null;
  }
  if (btn._progressSafetyTimeout) {
    clearTimeout(btn._progressSafetyTimeout);
    btn._progressSafetyTimeout = null;
  }
  if (btn.dataset.originalHtml) {
    btn.innerHTML = btn.dataset.originalHtml;
    delete btn.dataset.originalHtml;
    btn.removeAttribute('data-original-html');
  }
  btn.classList.remove('btn-loading-progress');
  btn.classList.remove('btn-instant-pressed');
  btn.style.removeProperty('--btn-progress');
  delete btn.dataset.progressActive;
  btn.removeAttribute('data-progress-active');
  _activeProgressButtons.delete(btn);
}

function resetAllButtonProgressFills() {
  _activeProgressButtons.forEach(btn => resetButtonProgressFill(btn));
  _activeProgressButtons.clear();
  document.querySelectorAll('.btn-loading-progress, [data-progress-active]').forEach(btn => {
    resetButtonProgressFill(btn);
  });
}

window.resetButtonProgressFill = resetButtonProgressFill;
window.resetAllButtonProgressFills = resetAllButtonProgressFills;

function startButtonProgressFill(btn, baseLabel = 'Loading Dossier') {
  if (!btn || btn.dataset.progressActive) return;

  // Cache original innerHTML before mutating DOM so it can be restored on Back navigation
  if (!btn.dataset.originalHtml) {
    btn.dataset.originalHtml = btn.innerHTML;
  }

  btn.dataset.progressActive = 'true';
  btn.classList.add('btn-loading-progress');
  _activeProgressButtons.add(btn);

  const startMs = Date.now();
  const INITIAL_PCT = 14; // Immediate perceptible progress bar start on the first frame

  const updateProgress = () => {
    const elapsedMs = Date.now() - startMs;
    const elapsedSec = Math.min(30, Math.floor(elapsedMs / 1000));

    // Progress fill percentage: Starts immediately at 14%, fills smoothly to 88% over 24s, crawls to 96%
    let pct = INITIAL_PCT;
    if (elapsedMs < 24000) {
      pct = INITIAL_PCT + (elapsedMs / 24000) * (88 - INITIAL_PCT);
    } else {
      pct = Math.min(96, 88 + ((elapsedMs - 24000) / 6000) * 8);
    }

    btn.style.setProperty('--btn-progress', `${pct.toFixed(1)}%`);

    let stage = baseLabel;
    if (elapsedSec < 8) {
      stage = 'Ingesting Data';
    } else if (elapsedSec < 18) {
      stage = '7-Pillar Cortex';
    } else if (elapsedSec < 26) {
      stage = 'Reverse DCF';
    } else {
      stage = 'Finalizing';
    }

    btn.innerHTML = `<span class="btn-progress-label"><span style="display:inline-block; animation: spin 0.6s linear infinite;">⚡</span> ${stage}... ${elapsedSec}s / ~30s</span>`;
  };

  // Synchronous immediate visual update on the exact click tick
  updateProgress();

  // High-frequency 100ms interval for silky-smooth continuous progress movement
  btn._progressInterval = setInterval(updateProgress, 100);

  // Safety watchdog: Auto-reset button if navigation didn't happen after 40 seconds
  btn._progressSafetyTimeout = setTimeout(() => {
    resetButtonProgressFill(btn);
  }, 40000);
}

// ==============================================================================
// 10. Global Event Interceptors, Tactile Feedback & Sitewide Evaluation Activation
// ==============================================================================

// Helper: Determine asset evaluation metadata from URL or link element
function resolveEvaluationTarget(a) {
  if (!a || !a.pathname) return null;
  const p = a.pathname;

  // 1. Fundamental Equity Dossier
  if (p.startsWith('/dossier/')) {
    const raw = p.replace('/dossier/', '').split('/')[0] || '';
    const ticker = decodeURIComponent(raw).trim() || 'Selected Equity';
    return { assetType: 'equity', ticker, label: 'Evaluating Dossier' };
  }

  // 2. Mutual Fund Look-Through
  if (p.startsWith('/funds/compare/overlap') || p.startsWith('/funds/compare')) {
    return { assetType: 'compare', ticker: 'Portfolio Overlap & Divergence', label: 'Computing Overlap' };
  }
  if (p.startsWith('/funds/')) {
    const raw = p.replace('/funds/', '').split('/')[0] || '';
    const cardTitle = a.querySelector?.('h3, h4, .fund-title, [data-name]')?.innerText?.trim();
    const code = decodeURIComponent(raw).trim();
    return { assetType: 'fund', ticker: cardTitle || code || 'Selected Scheme', label: 'Auditing Fund' };
  }

  // 3. Fixed Income & Credit Solvency
  if (p.startsWith('/debt/')) {
    const raw = p.replace('/debt/', '').split('/')[0] || '';
    const cardTitle = a.querySelector?.('h3, h4, .debt-title, [data-name]')?.innerText?.trim();
    const isin = decodeURIComponent(raw).trim();
    return { assetType: 'debt', ticker: cardTitle || isin || 'Corporate Bond', label: 'Auditing Credit' };
  }

  // 4. Cross-Company Disparity Comparator
  if (p === '/compare') {
    try {
      const u = new URL(a.href);
      const t1 = u.searchParams.get('a') || u.searchParams.get('ticker1');
      const t2 = u.searchParams.get('b') || u.searchParams.get('ticker2');
      if (t1 && t2) {
        return { assetType: 'compare', ticker: `${t1} vs ${t2}`, label: 'Benchmarking Peers' };
      }
    } catch (_) {}
    return { assetType: 'compare', ticker: 'Peer Disparity Matrix', label: 'Benchmarking Peers' };
  }

  // 5. Multi-Asset Arbitrage Scanner / Opportunities
  if (p === '/opportunities') {
    return { assetType: 'opportunity', ticker: 'Multi-Asset Arbitrage Scanner', label: 'Scanning Spreads' };
  }

  // 6. Sovereign Curve & Macro Terminal
  if (p === '/sovereign') {
    return { assetType: 'macro', ticker: 'Sovereign Yield Curve & RBI Rates', label: 'Ingesting G-Secs' };
  }

  // 7. Alternative Real Assets (REITs / InvITs)
  if (p === '/reits') {
    return { assetType: 'opportunity', ticker: 'REITs & InvITs Yield Engine', label: 'Auditing Real Assets' };
  }

  // 8. ETFs & Index Arbitrage
  if (p === '/etfs') {
    return { assetType: 'macro', ticker: 'ETF Tracking Error & Arbitrage Matrix', label: 'Auditing ETFs' };
  }

  // 9. Accounting Red Flag Radar
  if (p === '/safety-radar') {
    return { assetType: 'equity', ticker: 'Forensic Accounting Red Flag Radar', label: 'Scanning Hazards' };
  }

  // 10. Discovery Screener
  if (p === '/discovery') {
    return { assetType: 'equity', ticker: 'Daily Exchange Discovery @ 9AM IST', label: 'Scanning Moats' };
  }

  // 11. MSME Emerging Growth Watchlist
  if (p === '/msme') {
    return { assetType: 'equity', ticker: 'MSME Emerging Growth & Solvency Radar', label: 'Auditing MSMEs' };
  }

  // 12. Post-Tax Purchasing Power Calculator
  if (p === '/calculator/tax') {
    return { assetType: 'opportunity', ticker: 'Post-Tax Purchasing Power Matrix', label: 'Calculating Real Yield' };
  }

  return null;
}

// Global click interceptor with capture: true for instant reaction
document.addEventListener('click', (e) => {
  const a = e.target.closest('a, button');
  if (!a) return;

  // Prevent multiple double-clicks if already actively loading
  if (a.dataset.progressActive === 'true') {
    e.preventDefault();
    e.stopPropagation();
    return;
  }

  if (a.tagName === 'A' && a.href && a.origin === window.location.origin && !a.target && !e.ctrlKey && !e.metaKey && !e.shiftKey) {
    const targetMeta = resolveEvaluationTarget(a);
    if (targetMeta) {
      // Trigger the sitewide Report Evaluation HUD
      window.showEvaluationHUD({
        assetType: targetMeta.assetType,
        ticker: targetMeta.ticker,
        totalSec: 30
      });

      // If clicked element is or contains a button, activate button progress fill
      if (a.classList.contains('btn')) {
        startButtonProgressFill(a, targetMeta.label);
      } else {
        const childBtn = a.querySelector?.('.btn');
        if (childBtn) {
          startButtonProgressFill(childBtn, targetMeta.label);
        }
      }
    }
  }
}, true); // Use capture phase so listener fires immediately at the top of the event tree

// Global Form Submission Interceptor for Analytical Engines
document.addEventListener('submit', (e) => {
  const form = e.target;
  if (!form || !form.action) return;

  try {
    const u = new URL(form.action, window.location.origin);
    const p = u.pathname;

    // 1. Peer Comparison Form (/compare)
    if (p === '/compare') {
      const aVal = form.querySelector('[name="a"], [name="ticker1"]')?.value?.trim() || '';
      const bVal = form.querySelector('[name="b"], [name="ticker2"]')?.value?.trim() || '';
      const pair = (aVal && bVal) ? `${aVal.toUpperCase()} vs ${bVal.toUpperCase()}` : 'Peer Comparison';
      window.showEvaluationHUD({ assetType: 'compare', ticker: pair, totalSec: 30 });
      const submitBtn = form.querySelector('button[type="submit"], input[type="submit"], .btn-primary');
      if (submitBtn) startButtonProgressFill(submitBtn, 'Benchmarking');
    }
    // 2. Fund Overlap Form (/funds/compare/overlap)
    else if (p === '/funds/compare/overlap') {
      const sA = form.querySelector('[name="scheme_a"]')?.selectedOptions?.[0]?.text?.trim() || 'Scheme A';
      const sB = form.querySelector('[name="scheme_b"]')?.selectedOptions?.[0]?.text?.trim() || 'Scheme B';
      const cleanA = sA.split('(')[0].trim();
      const cleanB = sB.split('(')[0].trim();
      window.showEvaluationHUD({ assetType: 'compare', ticker: `${cleanA} vs ${cleanB}`, totalSec: 30 });
      const submitBtn = form.querySelector('button[type="submit"], input[type="submit"], .btn-primary');
      if (submitBtn) startButtonProgressFill(submitBtn, 'Calculating Overlap');
    }
    // 3. Tax Calculator Form (/calculator/tax)
    else if (p === '/calculator/tax') {
      window.showEvaluationHUD({ assetType: 'opportunity', ticker: 'Post-Tax Purchasing Power Matrix', totalSec: 30 });
      const submitBtn = form.querySelector('button[type="submit"], input[type="submit"], .btn-primary');
      if (submitBtn) startButtonProgressFill(submitBtn, 'Recalculating');
    }
  } catch (_) {}
});

// Tactile press state for instantaneous pointer responsiveness
document.addEventListener('pointerdown', (e) => {
  if (e.button !== 0) return; // Left click only
  const a = e.target.closest('a, button');
  if (a && !a.dataset.progressActive && a.origin === window.location.origin) {
    if (resolveEvaluationTarget(a)) {
      a.classList.add('btn-instant-pressed');
    }
  }
}, { passive: true, capture: true });

['pointerup', 'pointercancel', 'pointerleave'].forEach(evt => {
  document.addEventListener(evt, () => {
    document.querySelectorAll('.btn-instant-pressed').forEach(el => el.classList.remove('btn-instant-pressed'));
  }, { passive: true });
});

// Dismiss HUD on Escape key
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    window.hideEvaluationHUD();
  }
});

// BFCache and History Navigation Lifecycle Guards
// Resets all loading buttons and hides HUD whenever page is shown (back/forward cache)
window.addEventListener('pageshow', (event) => {
  window.hideEvaluationHUD();
  resetAllButtonProgressFills();
});

// Terminate active background intervals immediately when navigating away
window.addEventListener('pagehide', () => {
  window.hideEvaluationHUD();
  _activeProgressButtons.forEach(btn => {
    if (btn._progressInterval) {
      clearInterval(btn._progressInterval);
      btn._progressInterval = null;
    }
    if (btn._progressSafetyTimeout) {
      clearTimeout(btn._progressSafetyTimeout);
      btn._progressSafetyTimeout = null;
    }
  });
});

window.addEventListener('popstate', () => {
  window.hideEvaluationHUD();
  resetAllButtonProgressFills();
});

document.addEventListener('DOMContentLoaded', () => {
  window.hideEvaluationHUD();
  resetAllButtonProgressFills();
  initDwellAndTransitionTelemetry();
});

/**
 * 1. Top-Layer Non-Blocking Toast Notification (popover="manual")
 * Replaces blocking window.alert() calls across the platform.
 */
window.showToast = function(message, variant = "info", durationMs = 4200) {
  const toast = document.createElement("div");
  toast.className = "toast-popover";
  toast.setAttribute("popover", "manual");
  toast.setAttribute("role", "status");
  toast.setAttribute("aria-live", "polite");

  const borderColors = {
    info: "rgba(56, 189, 248, 0.45)",
    success: "rgba(16, 185, 129, 0.55)",
    warning: "rgba(245, 158, 11, 0.55)",
    error: "rgba(239, 68, 68, 0.6)"
  };
  toast.style.borderColor = borderColors[variant] || borderColors.info;

  const textSpan = document.createElement("span");
  textSpan.textContent = String(message || "");

  const closeBtn = document.createElement("button");
  closeBtn.type = "button";
  closeBtn.textContent = "✕";
  closeBtn.setAttribute("aria-label", "Dismiss notification");
  closeBtn.style.cssText = "background:none;border:none;color:#94a3b8;cursor:pointer;font-size:14px;padding:2px 6px;";

  const dismiss = () => {
    try {
      if (typeof toast.hidePopover === "function") toast.hidePopover();
    } catch (_) {}
    toast.remove();
  };
  closeBtn.addEventListener("click", dismiss);

  toast.append(textSpan, closeBtn);
  document.body.appendChild(toast);

  if (typeof toast.showPopover === "function") {
    toast.showPopover();
  } else {
    toast.classList.add(":popover-open");
  }

  if (durationMs > 0) {
    setTimeout(dismiss, durationMs);
  }
};

/**
 * 2. Native <dialog closedby="any"> Light-Dismiss Fallback
 * Safely handles backdrop clicks in browsers without native `closedBy` support.
 */
window.initDialogLightDismiss = function(dialogEl) {
  if (!dialogEl || ("closedBy" in HTMLDialogElement.prototype)) return;
  dialogEl.addEventListener("click", (e) => {
    if (e.target === dialogEl) {
      const rect = dialogEl.getBoundingClientRect();
      const clickedInDialog =
        e.clientY >= rect.top &&
        e.clientY <= rect.top + rect.height &&
        e.clientX >= rect.left &&
        e.clientX <= rect.left + rect.width;
      if (!clickedInDialog) {
        dialogEl.close();
      }
    }
  });
};

/**
 * 3. Universal Escape Key Handler for Legacy .modal-backdrop Overlays
 * Ensures #ingestModalBackdrop on /debt and all page-local backdrops close on Escape.
 */
document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  document.querySelectorAll(".modal-backdrop").forEach((backdrop) => {
    const isVisible =
      backdrop.classList.contains("active") ||
      backdrop.style.display === "flex" ||
      backdrop.style.display === "block";
    if (isVisible) {
      backdrop.classList.remove("active");
      if (backdrop.style.display) backdrop.style.display = "none";
    }
  });
});

document.addEventListener("click", (e) => {
  const target = e.target;
  if (target && target.classList && target.classList.contains("modal-backdrop") && target.id !== "synthesizingOverlay") {
    target.classList.remove("active");
    if (target.style.display && target.style.display !== "none") {
      target.style.display = "none";
    }
  }
});

/**
 * 4. Sync ARIA `aria-invalid` with CSS `:user-invalid` after interaction
 */
(function initUserInvalidAriaSync() {
  const syncAria = (el) => {
    if (!el || typeof el.matches !== "function" || !("checkValidity" in el)) return;
    try {
      if (CSS.supports("selector(:user-invalid)")) {
        el.setAttribute("aria-invalid", el.matches(":user-invalid") ? "true" : "false");
      }
    } catch (_) {}
  };
  document.addEventListener("blur", (e) => syncAria(e.target), true);
  document.addEventListener("input", (e) => {
    if (e.target && e.target.hasAttribute && e.target.hasAttribute("aria-invalid")) {
      syncAria(e.target);
    }
  });
})();

/**
 * 5. Searchable Collapsible Disclosure Sync (hidden="until-found" & beforematch)
 * Automatically reveals collapsed panels when browser Find-in-Page (Ctrl+F) matches content.
 */
function initUntilFoundPanels() {
  document.querySelectorAll('[hidden="until-found"]').forEach((panel) => {
    panel.addEventListener("beforematch", () => {
      panel.removeAttribute("hidden");
      const trigger = document.querySelector(`[aria-controls="${panel.id}"]`);
      if (trigger) trigger.setAttribute("aria-expanded", "true");
    });
  });
}
document.addEventListener("DOMContentLoaded", initUntilFoundPanels);

// Attach to any custom collapsible panel using hidden="until-found"
document.querySelectorAll('[hidden="until-found"]').forEach((panel) => {
  panel.addEventListener("beforematch", () => {
    panel.removeAttribute("hidden");
    const trigger = document.querySelector(`[aria-controls="${panel.id}"]`);
    if (trigger) trigger.setAttribute("aria-expanded", "true");
  });
});

/**
 * 6. Dual-Theme Architecture (Dark & Editorial Warm Ivory)
 */
function syncThemeToggleUI(theme) {
  const btn = document.getElementById("themeToggleBtn");
  if (!btn) return;
  const isLight = theme === "light";
  btn.setAttribute("aria-pressed", isLight ? "true" : "false");
  const iconUse = btn.querySelector("use");
  if (iconUse) {
    iconUse.setAttribute("href", isLight ? "#icon-theme-moon" : "#icon-theme-sun");
  }
}

function initThemeToggle() {
  try {
    const saved = localStorage.getItem("moatnomics_theme");
    const theme = saved === "light" ? "light" : "dark";
    document.documentElement.dataset.theme = theme;
    syncThemeToggleUI(theme);

    const savedReading = localStorage.getItem("moatnomics_dossier_ivory");
    const dossierWrap = document.getElementById("dossierReadingContainer");
    const readingBtn = document.getElementById("dossierReadingToggleBtn");
    if (dossierWrap && savedReading === "1") {
      dossierWrap.classList.add("dossier-ivory-surface");
      if (readingBtn) {
        readingBtn.setAttribute("aria-pressed", "true");
      }
    }
  } catch (e) {
    console.warn("Theme initialization storage notice:", e);
  }
}

window.toggleSiteTheme = function () {
  const current = document.documentElement.dataset.theme === "light" ? "light" : "dark";
  const next = current === "light" ? "dark" : "light";
  document.documentElement.dataset.theme = next;
  try {
    localStorage.setItem("moatnomics_theme", next);
  } catch (e) {
    console.warn("Could not persist theme preference:", e);
  }
  syncThemeToggleUI(next);
};

window.toggleDossierReadingMode = function () {
  const dossierWrap = document.getElementById("dossierReadingContainer");
  const readingBtn = document.getElementById("dossierReadingToggleBtn");
  if (!dossierWrap) return;
  const isIvory = dossierWrap.classList.toggle("dossier-ivory-surface");
  if (readingBtn) {
    readingBtn.setAttribute("aria-pressed", isIvory ? "true" : "false");
  }
  try {
    localStorage.setItem("moatnomics_dossier_ivory", isIvory ? "1" : "0");
  } catch (e) {
    console.warn("Could not persist dossier reading surface preference:", e);
  }
};






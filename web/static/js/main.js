/**
 * Stock Research App - Main Client-Side Logic
 * Autocomplete, Instant Lookup, Razorpay Checkout Modal, and Report Synthesis
 */

document.addEventListener('DOMContentLoaded', () => {
  initSearchAutocomplete();
  initCheckoutModals();
  initGenerateModal();
  initAuthModal();
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
        <span class="view-label">View Institutional Dossier →</span>
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
    alert('Please sign in first to generate institutional dossiers. You will receive 2 free research credits.');
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

  document.getElementById('modalPlanName').innerText = planName;
  document.getElementById('modalPlanPrice').innerText = '₹' + Number(amountInr).toLocaleString('en-IN');
  document.getElementById('modalPlanCredits').innerText = credits + ' Research Credits';
  
  const basePrice = (amountInr / 1.18).toFixed(2);
  const gstPrice = (amountInr - basePrice).toFixed(2);
  document.getElementById('modalBasePrice').innerText = '₹' + basePrice;
  document.getElementById('modalGstPrice').innerText = '₹' + gstPrice;

  const confirmBtn = document.getElementById('modalConfirmBtn');
  if (confirmBtn) {
    confirmBtn.onclick = async () => {
      confirmBtn.disabled = true;
      confirmBtn.innerText = 'Initializing Razorpay Checkout...';

      try {
        const currentUser = getStoredUser();
        const resp = await fetch('/api/create-order', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            plan_id: planId,
            user_id: currentUser ? currentUser.id : 'guest_web_user',
            email: currentUser ? currentUser.email : 'investor@example.com'
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
              user_id: storedUser ? storedUser.id : 'guest_web_user'
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
            name: 'Stock Research AI',
            description: planName + ' — Computational Research Credits',
            order_id: orderData.order_id || orderData.id,
            prefill: {
              name: (storedUser && storedUser.full_name) ? storedUser.full_name : 'Test Investor',
              email: (storedUser && storedUser.email) ? storedUser.email : 'investor@stockresearch.ai',
              contact: (storedUser && storedUser.phone) ? storedUser.phone : '9820098200'
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
                    user_id: storedUser ? storedUser.id : 'guest_web_user'
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
// 4. Report Synthesis — Triggers /api/synthesize with credit deduction & UI feedback
// ==============================================================================

window.synthesizeReport = async function(ticker, forceRefresh = false) {
  const user = getStoredUser();
  if (!user) {
    alert('Please sign in first to generate institutional dossiers. You will receive 2 free research credits.');
    openSignInModal();
    return;
  }

  const balance = parseFloat(user.credits_balance) || 0;
  if (balance < 1) {
    if (confirm(`You need at least 1 research credit to generate a new dossier.\n\nCurrent balance: ${balance} credits.\n\nWould you like to visit the Pricing page to top up credits?`)) {
      window.location.href = '/pricing';
    }
    return;
  }

  const actionDesc = forceRefresh ? `Refresh and re-synthesize the 7-pillar institutional dossier for ${ticker}?` : `Generate a fresh 7-pillar institutional dossier for ${ticker}?`;
  if (!confirm(`${actionDesc}\n\nThis will consume 1 research credit.\nCurrent balance: ${balance} credits.`)) {
    return;
  }

  // Show the institutional synthesis overlay
  const overlay = document.getElementById('synthesizingOverlay');
  const overlayTitle = document.getElementById('overlayTickerTitle');
  if (overlayTitle) {
    overlayTitle.innerText = `Synthesizing Dossier: ${ticker}`;
  }
  if (overlay) {
    overlay.classList.add('active');
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

    const data = await resp.json();

    if (resp.ok && data.success) {
      // Update local credits atomically
      if (data.new_balance !== undefined) {
        user.credits_balance = data.new_balance;
        localStorage.setItem('sr_user', JSON.stringify(user));
        syncUserSession();
      }

      if (overlay) overlay.classList.remove('active');

      if (data.already_exists) {
        alert('✅ ' + data.message);
      } else {
        alert('🎉 ' + data.message);
      }

      // Navigate directly to the newly generated dossier
      window.location.href = data.dossier_url;
    } else {
      if (overlay) overlay.classList.remove('active');

      const detail = data.detail || data.message || 'Synthesis failed.';
      if (resp.status === 402) {
        if (confirm(detail + '\n\nWould you like to purchase more credits?')) {
          window.location.href = '/pricing';
        }
      } else if (resp.status === 401) {
        alert(detail);
        openSignInModal();
      } else {
        alert('❌ ' + detail);
      }

      // Refresh balance in background in case of refund
      await refreshUserBalance(user);
    }
  } catch (err) {
    if (overlay) overlay.classList.remove('active');
    alert('Synthesis Request Error: ' + err.message);
    await refreshUserBalance(user);
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

  // Background balance sync on every page load
  const user = getStoredUser();
  if (user && user.id) {
    refreshUserBalance(user);
  }
}

window.openSignInModal = function() {
  const user = getStoredUser();
  if (user) {
    if (confirm(`Logged in as ${user.full_name} (${user.email})\nCredits Balance: ${user.credits_balance} Credits\n\nWould you like to sign out?`)) {
      localStorage.removeItem('sr_user');
      window.location.reload();
    }
    return;
  }
  const modal = document.getElementById('authModal');
  if (modal) modal.classList.add('active');
};

window.handleSignInSubmit = async function(e) {
  e.preventDefault();
  const emailInput = document.getElementById('authEmailInput');
  const submitBtn = document.getElementById('authSubmitBtn');
  if (!emailInput || !emailInput.value.trim()) return;

  submitBtn.disabled = true;
  submitBtn.innerText = 'Signing In & Granting Credits...';

  try {
    const resp = await fetch('/api/auth/signin', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: emailInput.value.trim() })
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

      alert(`🎉 Welcome ${data.user.full_name}! 2 Free Research Credits have been allocated to your account.`);
      window.location.reload();
    } else {
      alert('Sign-In Error: ' + (data.detail || data.message || 'Could not complete sign in.'));
    }
  } catch (err) {
    alert('Sign-In Error: ' + err.message);
  } finally {
    submitBtn.disabled = false;
    submitBtn.innerText = 'Continue with Email & Claim 2 Credits →';
  }
};

window.handlePreMortemSubmit = async function(e, ticker) {
  if (e) e.preventDefault();
  const vector = document.getElementById('premortemVector')?.value || '';
  const notes = document.getElementById('premortemNotes')?.value || '';
  const statusEl = document.getElementById('premortemStatus');
  const btn = document.getElementById('btnCommitPremortem');

  if (btn) {
    btn.disabled = true;
    btn.innerText = 'Anchoring Anti-Thesis...';
  }

  try {
    const user = getStoredUser();
    const resp = await fetch('/api/premortem', {
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
      alert('Error: ' + (data.detail || data.message || 'Could not record.'));
    }
  } catch (err) {
    alert('Error recording pre-mortem: ' + err.message);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerText = '🔒 Commit Pre-Mortem to Audit Ledger';
    }
  }
};

function getStoredUser() {
  try {
    const raw = localStorage.getItem('sr_user');
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

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
      if (data.success && data.user) {
        localStorage.setItem('sr_user', JSON.stringify(data.user));
        syncUserSession();
      }
    }
  } catch (err) {
    console.error('Failed to refresh user balance:', err);
  }
}

function syncUserSession() {
  const user = getStoredUser();
  const navBtn = document.getElementById('navSignInBtn');
  if (navBtn && user) {
    const bal = user.credits_balance !== undefined ? user.credits_balance : 0;
    navBtn.innerText = `👤 ${user.full_name || 'Account'} (${bal} Credits)`;
    navBtn.classList.remove('btn-primary');
    navBtn.classList.add('btn-secondary');
  }

  const modalBal = document.getElementById('generateModalCreditsText');
  if (modalBal && user) {
    const bal = user.credits_balance !== undefined ? user.credits_balance : 0;
    modalBal.innerText = `${bal} Credits Available`;
  }
}

// ==============================================================================
// 7. Responsive Navigation & Mobile Drawer
// ==============================================================================
function toggleMobileMenu() {
  const nav = document.getElementById('mainNav');
  const btn = document.getElementById('mobileMenuBtn');
  if (!nav) return;
  const isOpen = nav.classList.toggle('mobile-open');
  if (btn) btn.classList.toggle('active', isOpen);
}

// Close mobile menu on click outside or on nav link
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

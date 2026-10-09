/**
 * Stock Research App - Main Client-Side Logic
 * Autocomplete, Instant Lookup, Razorpay Checkout Modal, and Report Synthesis
 */

// Immediate OAuth Fragment Interceptor (captures #access_token=... if Supabase redirects to root or any page)
(function checkOAuthFragment() {
  if (window.location.hash && window.location.hash.includes('access_token=')) {
    try {
      const hashParams = new URLSearchParams(window.location.hash.substring(1));
      const accessToken = hashParams.get('access_token');
      if (accessToken) {
        const isAdmin = window.location.pathname.startsWith('/admin');
        const callbackUrl = isAdmin ? '/admin/auth/callback' : '/auth/callback';
        window.location.href = callbackUrl + '?access_token=' + encodeURIComponent(accessToken);
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
            user_id: currentUser ? currentUser.id : getTelemetrySessionId(),
            email: currentUser ? currentUser.email : ''
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
      fetch('/api/auth/signout', { method: 'POST' }).catch(() => {});
      localStorage.removeItem('sr_user');
      window.location.reload();
    }
    return;
  }
  const modal = document.getElementById('authModal');
  if (modal) modal.classList.add('active');
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
        alert('Authentication Error: ' + (data.detail || data.message || 'Could not send verification code.'));
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
        alert('Verification Failed: ' + (data.detail || data.message || 'Invalid or expired code.'));
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
      alert('Notice: ' + (data.detail || data.message || 'Could not resend code.'));
    }
  } catch (err) {
    alert('Resend Error: ' + err.message);
  }
};

window.handleSignInSubmit = window.handleAuthFormSubmit;

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
      alert('Error: ' + (data.detail || data.message || 'Could not record checkpoint.'));
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

function getAcquisitionData() {
  try {
    let data = sessionStorage.getItem('sr_acquisition');
    if (data) return JSON.parse(data);

    // Initial landing capture
    const params = new URLSearchParams(window.location.search);
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
// 10. Autonomous Surveillance Feed Controller (Phase 4)
// ==============================================================================
async function toggleSurveillanceFeed() {
  const modal = document.getElementById('surveillanceModal');
  if (!modal) return;
  const isHidden = modal.style.display === 'none' || !modal.style.display;
  if (isHidden) {
    modal.style.display = 'block';
    loadSurveillanceEvents();
  } else {
    modal.style.display = 'none';
  }
}

async function loadSurveillanceEvents() {
  const container = document.getElementById('surveillanceEventsList');
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


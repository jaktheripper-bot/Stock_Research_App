/**
 * Stock Research App - Main Client-Side Logic
 * Autocomplete, Instant Lookup, and Razorpay Checkout Modal
 */

document.addEventListener('DOMContentLoaded', () => {
  initSearchAutocomplete();
  initCheckoutModals();
  initAuthModal();
});

// Search and Autocomplete
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

// Checkout Modal
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
        const storedUser = getStoredUser();
        const resp = await fetch('/api/create-order', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            plan_id: planId,
            user_id: storedUser ? storedUser.id : 'guest_web_user',
            email: storedUser ? storedUser.email : 'investor@example.com'
          })
        });
        
        if (!resp.ok) {
          const errData = await resp.json().catch(() => ({}));
          throw new Error(errData.detail || errData.message || 'Failed to initialize Razorpay order');
        }

        const orderData = await resp.json();

        if (orderData.is_simulated) {
          // Instant simulation fulfillment for dev/offline testing
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
            // Update localStorage with new balance from server
            await refreshUserBalance(storedUser);
            alert('🎉 Payment verified successfully! Added ' + credits + ' credits to your account. Invoice: ' + verifyResult.invoice_number);
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
              name: storedUser ? storedUser.full_name : 'Guest Investor',
              email: storedUser ? storedUser.email : 'investor@stockresearch.ai'
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
                  // Update localStorage with new balance from server
                  await refreshUserBalance(storedUser);
                  alert('🎉 Payment Confirmed! ' + credits + ' Credits added. Invoice: ' + verifyResult.invoice_number);
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
// Report Synthesis — Triggers /api/synthesize with credit deduction
// ==============================================================================

window.synthesizeReport = async function(ticker) {
  const user = getStoredUser();
  if (!user) {
    alert('Please sign in first to generate reports. You will receive 2 free research credits.');
    openSignInModal();
    return;
  }

  if ((user.credits_balance || 0) < 1) {
    if (confirm('You need at least 1 research credit to generate a new dossier.\n\nCurrent balance: ' + (user.credits_balance || 0) + ' credits.\n\nWould you like to purchase credits?')) {
      window.location.href = '/pricing';
    }
    return;
  }

  if (!confirm(`Generate a full 7-pillar institutional dossier for ${ticker}?\n\nThis will consume 1 research credit.\nCurrent balance: ${user.credits_balance} credits.`)) {
    return;
  }

  // Find the button that triggered this and show progress
  const btn = event && event.target ? event.target.closest('button') || event.target : null;
  const originalText = btn ? btn.innerText : '';
  if (btn) {
    btn.disabled = true;
    btn.innerText = '⏳ Synthesizing 7-Pillar Thesis...';
    btn.style.opacity = '0.7';
  }

  try {
    const resp = await fetch('/api/synthesize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ticker: ticker,
        user_id: user.id
      })
    });

    const data = await resp.json();

    if (resp.ok && data.success) {
      // Update local credits
      if (data.new_balance !== undefined) {
        user.credits_balance = data.new_balance;
        localStorage.setItem('sr_user', JSON.stringify(user));
        syncUserSession();
      }

      if (data.already_exists) {
        alert('✅ ' + data.message);
      } else {
        alert('🎉 ' + data.message);
      }

      // Navigate to the dossier
      window.location.href = data.dossier_url;
    } else {
      const detail = data.detail || data.message || 'Synthesis failed.';
      if (resp.status === 402) {
        // Insufficient credits
        if (confirm(detail + '\n\nWould you like to purchase more credits?')) {
          window.location.href = '/pricing';
        }
      } else if (resp.status === 401) {
        alert(detail);
        openSignInModal();
      } else {
        alert('❌ ' + detail);
      }
    }
  } catch (err) {
    alert('Synthesis Error: ' + err.message);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerText = originalText;
      btn.style.opacity = '1';
    }
  }
};

// ==============================================================================
// Authentication & User Session Management
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
      alert(`🎉 Welcome ${data.user.full_name}! 2 Free Research Credits have been allocated to your account.`);
      const modal = document.getElementById('authModal');
      if (modal) modal.classList.remove('active');
      syncUserSession();
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
 * Called after successful payments to ensure credit balance is always in sync.
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
    navBtn.innerText = `👤 ${user.full_name || 'Account'} (${user.credits_balance} Credits)`;
    navBtn.classList.remove('btn-primary');
    navBtn.classList.add('btn-secondary');
  }
}

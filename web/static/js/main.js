/**
 * Stock Research App - Main Client-Side Logic
 * Autocomplete, Instant Lookup, and Razorpay Checkout Modal
 */

document.addEventListener('DOMContentLoaded', () => {
  initSearchAutocomplete();
  initCheckoutModals();
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
        const resp = await fetch('/api/create-order', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ plan_id: planId })
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
              plan_id: planId
            })
          });
          const verifyResult = await verifyResp.json();
          if (verifyResp.ok && verifyResult.success) {
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
              name: 'Guest Investor',
              email: 'investor@stockresearch.ai'
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
                    plan_id: planId
                  })
                });
                const verifyResult = await verifyResp.json();
                if (verifyResp.ok && verifyResult.success) {
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

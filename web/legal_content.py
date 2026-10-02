"""
Mandatory Legal, Privacy, and Compliance Policies for Razorpay Merchant Verification.

Complies with:
- Information Technology Act, 2000 & IT (Intermediary Guidelines) Rules, 2021
- Consumer Protection (E-Commerce) Rules, 2020
- SEBI (Research Analysts) Regulations, 2014 Safe-Harbor Disclaimers
- Goods and Services Tax (GST) SAC Code 998314 (Information Technology Software Services)
"""

POLICIES = {
    "terms": {
        "title": "Terms and Conditions",
        "last_updated": "October 2026",
        "description": "Terms governing the use of the Stock Research App and computational research synthesis services.",
        "content_html": """
        <h3>1. Acceptance of Terms</h3>
        <p>By accessing or using the Stock Research App (the "Platform", "Service"), you agree to be bound by these Terms and Conditions. If you do not agree with any part of these terms, you must refrain from using the Service.</p>

        <h3>2. Description of Service</h3>
        <p>The Platform provides an automated, computational financial research synthesis software utility. Under Service Accounting Code (SAC) <strong>998314</strong> (Information Technology Software Services), the Platform aggregates publicly available exchange filings from the Bombay Stock Exchange (BSE) and National Stock Exchange (NSE), computes algorithmic financial ratios, and formats educational 7-pillar qualitative research dossiers using artificial intelligence.</p>

        <h3>3. Non-Advisory Safe Harbor (SEBI Compliance)</h3>
        <p><strong>The Platform does not provide investment advice, financial planning, portfolio management services, or buy/hold/sell recommendations.</strong></p>
        <p>Neither the Platform nor its operators are registered as Research Analysts under the SEBI (Research Analysts) Regulations, 2014, nor as Investment Advisers under SEBI (Investment Advisers) Regulations, 2013. All data, scores, qualitative pillar matrices, and syntheses are for informational, computational, and educational purposes only. You are solely responsible for conducting independent due diligence and consulting a SEBI-registered financial advisor before making any financial investment decisions.</p>

        <h3>4. User Accounts and Research Credits</h3>
        <p>Access to automated live AI syntheses requires computational research credits or an active Pro subscription. Credits are non-transferable, possess no cash surrender value, and represent consumption units of server processing compute.</p>

        <h3>5. Intellectual Property</h3>
        <p>All software architecture, algorithms, user interfaces, branding, and aggregated analysis formats are the intellectual property of the Platform operator. Users may download and print individual research reports for personal, non-commercial educational use.</p>

        <h3>6. Limitation of Liability</h3>
        <p>While the Platform ingests public data directly from verified exchange endpoints, no guarantee of absolute accuracy or uninterrupted server uptime is made. The operators shall not be liable for any direct, indirect, incidental, or consequential financial losses arising from the use or inability to use the Platform.</p>

        <h3>7. Governing Law and Jurisdiction</h3>
        <p>These Terms shall be governed by and construed in accordance with the laws of India. Any disputes arising in connection with the Service shall be subject to the exclusive jurisdiction of the competent courts in Bengaluru/Mumbai, India.</p>
        """
    },
    "privacy": {
        "title": "Privacy Policy",
        "last_updated": "October 2026",
        "description": "How the Platform collects, handles, and protects user data and privacy.",
        "content_html": """
        <h3>1. Information We Collect</h3>
        <p>We respect your privacy and enforce strict data minimization:</p>
        <ul>
            <li><strong>Account Information:</strong> When you sign in via Google OAuth or Email Magic Link, we collect your verified email address and basic profile display name.</li>
            <li><strong>Transactional Data:</strong> For credit purchases, our payment partner (Razorpay) securely processes your payment. We store order IDs, transaction statuses, and invoice records. <em>We never store your credit/debit card numbers, UPI PINs, or banking passwords on our servers.</em></li>
            <li><strong>Usage Logs:</strong> Anonymized query logs and feature telemetry to monitor API compute costs, server latency, and error diagnostics.</li>
        </ul>

        <h3>2. What We Explicitly DO NOT Collect</h3>
        <p><strong>We never collect or request:</strong></p>
        <ul>
            <li>Personal portfolio holdings or net worth figures.</li>
            <li>Bank account login credentials, Aadhaar numbers, or Demat account numbers.</li>
            <li>Personalized risk profiles or individualized investment targets.</li>
        </ul>

        <h3>3. How We Use Your Information</h3>
        <p>Collected information is used exclusively to:</p>
        <ul>
            <li>Authenticate your account and maintain your credit balance in our database.</li>
            <li>Deliver requested research syntheses and issue tax invoices.</li>
            <li>Prevent abuse, rate limiting violations, and bot scraping.</li>
        </ul>

        <h3>4. Data Security</h3>
        <p>All communication between your browser and our servers is encrypted using industry-standard Transport Layer Security (TLS 1.3 / HTTPS). Database storage is hosted in enterprise PostgreSQL clusters with automated daily backups and encrypted connections.</p>

        <h3>5. Third-Party Service Providers</h3>
        <p>We work with trusted third-party providers:</p>
        <ul>
            <li><strong>Razorpay:</strong> Payment processing gateway (PCI-DSS Level 1 certified).</li>
            <li><strong>Supabase:</strong> Encrypted authentication and PostgreSQL database storage.</li>
            <li><strong>Google Gemini / Perplexity:</strong> LLM inference compute for document summarization.</li>
        </ul>

        <h3>6. Contact and Grievance Officer</h3>
        <p>In accordance with the Information Technology Act, 2000, inquiries or data deletion requests may be directed to our Grievance Officer at <code>privacy@stockresearch.app</code>.</p>
        """
    },
    "refund-policy": {
        "title": "Cancellation and Refund Policy",
        "last_updated": "October 2026",
        "description": "Clear rules regarding credit purchases, cancellations, and refunds.",
        "content_html": """
        <h3>1. Nature of the Product (Digital Software Utility)</h3>
        <p>The Stock Research App provides on-demand computational research synthesis credits and subscription memberships. Credits power live server processing and AI inference against public exchange filings.</p>

        <h3>2. 7-Day Refund Policy for Unused Credits</h3>
        <p>We want you to be completely satisfied with our platform:</p>
        <ul>
            <li>If you purchased an <strong>On-Demand Credit Pack</strong> (Single Pass, Analyst 3-Pack, Portfolio 10-Pack) and have <strong>not consumed</strong> any of the purchased credits, you may request a <strong>100% full refund within 7 calendar days</strong> of the purchase date.</li>
            <li>Refund requests must be submitted via email to <code>support@stockresearch.app</code> along with your order ID or invoice number.</li>
            <li>Approved refunds are processed through Razorpay back to the original payment source (UPI account or Card) within <strong>5 to 7 business days</strong>.</li>
        </ul>

        <h3>3. Consumed Research Credits</h3>
        <p>Once a research credit has been consumed to execute a fresh live 7-pillar AI synthesis and the report has been generated, that specific computational unit is deemed consumed and is non-refundable, as server processing and API compute costs have already been incurred on your behalf.</p>

        <h3>4. Pro Subscriptions & Cancellations</h3>
        <ul>
            <li><strong>Monthly Pro Subscriptions:</strong> You may cancel your subscription renewal at any time from your account settings or by emailing support. Cancellation takes effect at the end of the current 30-day billing cycle. No further charges will occur.</li>
            <li><strong>Annual Subscriptions:</strong> If you cancel within the first 14 days and have consumed fewer than 10 syntheses, you are eligible for a prorated refund minus transaction gateway fees.</li>
        </ul>

        <h3>5. Payment Failures or Erroneous Charges</h3>
        <p>In the event of a technical issue where your account was debited by your bank but credits were not allocated, our automated reconciliation engine will credit the units within 15 minutes. If unresolved, please contact support for an immediate credit top-up or refund.</p>
        """
    },
    "contact": {
        "title": "Contact Us",
        "last_updated": "October 2026",
        "description": "Official business contact information, support hours, and grievance redressal.",
        "content_html": """
        <h3>Get in Touch</h3>
        <p>We are here to assist with any questions regarding research credits, institutional access, technical support, or billing queries.</p>

        <div style="background: rgba(14, 165, 233, 0.08); border-left: 4px solid #0284c7; padding: 16px; border-radius: 6px; margin: 20px 0;">
            <p style="margin: 0 0 8px 0;"><strong>🏢 Entity Name:</strong> Stock Research App / Equity Research AI</p>
            <p style="margin: 0 0 8px 0;"><strong>📧 Support Email:</strong> <a href="mailto:support@stockresearch.app">support@stockresearch.app</a></p>
            <p style="margin: 0 0 8px 0;"><strong>⏱️ Support Hours:</strong> Monday to Friday, 9:30 AM – 6:30 PM IST</p>
            <p style="margin: 0 0 8px 0;"><strong>📍 Operational Address:</strong> Indiranagar, 100 Feet Road, Bengaluru, Karnataka 560038, India</p>
            <p style="margin: 0;"><strong>📱 Support Hotline / WhatsApp:</strong> +91 98450 00000 (Business hours)</p>
        </div>

        <h3>Grievance Officer (IT Rules, 2021)</h3>
        <p>For regulatory compliance, privacy escalations, or legal communications:</p>
        <p><strong>Name:</strong> Compliance & Operations Lead<br>
        <strong>Email:</strong> <code>grievance@stockresearch.app</code><br>
        <strong>Turnaround Time:</strong> Acknowledgment within 24 hours, resolution within 15 business days.</p>
        """
    },
    "shipping-policy": {
        "title": "Shipping and Delivery Policy",
        "last_updated": "October 2026",
        "description": "Instant digital delivery policy for software research credits and analytical dossiers.",
        "content_html": """
        <h3>1. Digital Software Products & Services</h3>
        <p>All items sold on the Stock Research App (Computational Research Credits, Analyst Packs, Pro Memberships, and Institutional Dossiers) are <strong>purely digital software services</strong> under SAC Code 998314.</p>

        <h3>2. Delivery Mechanism and Timelines</h3>
        <ul>
            <li><strong>Instant Digital Delivery:</strong> Upon successful confirmation of payment via UPI or Card through Razorpay, your purchased research credits are credited to your online account ledger <strong>immediately (within 1 to 5 seconds)</strong>.</li>
            <li><strong>Report Generation:</strong> Research syntheses and PDF export dossiers are generated in real-time in your web browser and are immediately downloadable.</li>
            <li><strong>Invoice Receipt:</strong> An official Indian tax invoice receipt is dispatched to your registered email address and is permanently accessible in your account ledger.</li>
            <li><strong>No Physical Shipping:</strong> Because all products are electronic software services, there is <strong>zero physical delivery, zero postal shipping, and zero shipping charges</strong> applicable to any transaction on this platform.</li>
        </ul>

        <h3>3. Delivery Issues</h3>
        <p>If your account balance does not immediately reflect purchased credits following a confirmed bank deduction, please email your transaction receipt to <code>support@stockresearch.app</code>. We guarantee manual fulfillment within 2 hours.</p>
        """
    },
    "disclaimer": {
        "title": "SEBI Regulatory & Safe Harbor Disclaimer",
        "last_updated": "October 2026",
        "description": "Statutory non-advisory disclosures and educational safe-harbor terms.",
        "content_html": """
        <div style="background: rgba(245, 158, 11, 0.1); border-left: 4px solid #f59e0b; padding: 16px; border-radius: 6px; margin: 20px 0;">
            <h4 style="margin: 0 0 10px 0; color: #b45309;">MANDATORY SEBI NON-ADVISORY SAFE HARBOR NOTICE</h4>
            <p style="margin: 0; font-size: 14px; line-height: 1.6; color: #78350f;">
                This platform is an automated, computational financial research synthesis software utility. 
                <strong>We are NOT a SEBI-registered Research Analyst or Investment Adviser.</strong> 
                No content, scorecards, qualitative matrices, valuation estimates, or synthesized dossiers constitute personal financial advice, 
                investment recommendations, or an endorsement to BUY, SELL, or HOLD any security. 
                All research outputs are generated algorithmically using publicly available exchange filings from the Bombay Stock Exchange (BSE) 
                and National Stock Exchange (NSE) for strictly educational and research purposes.
            </p>
        </div>

        <h3>Key Compliance Guardrails</h3>
        <ul>
            <li><strong>No Individual Financial Profiling:</strong> We do not assess your personal risk tolerance, financial goals, or asset allocation.</li>
            <li><strong>No Performance Guarantees:</strong> Past financial metrics or historical valuation multiples do not guarantee future stock performance.</li>
            <li><strong>Algorithmic & AI Ingestion:</strong> Qualitative health matrix assessments are synthesized using computational reasoning from public filings. Users must independently verify all filings on <a href="https://www.bseindia.com" target="_blank" rel="noopener">bseindia.com</a>.</li>
            <li><strong>Consult a Professional:</strong> Always consult an independent SEBI-registered investment advisor (RIA) before committing capital to Indian equity markets.</li>
        </ul>
        """
    }
}

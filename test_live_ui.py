#!/usr/bin/env python3
"""
Automated Live Production UI & Interaction Test Suite
Target: https://stock-research-app-2ljm.onrender.com
Uses Headless Chrome (Selenium) to simulate real user interactions, button clicks,
mobile drawers, collapsible accordions, peer comparison, and checkout triggers.
"""

import os
import sys
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

BASE_URL = os.environ.get("TARGET_URL", "https://stock-research-app-2ljm.onrender.com")

passed_steps = 0
failed_steps = 0

def log_step(name: str, passed: bool, detail: str = ""):
    global passed_steps, failed_steps
    if passed:
        passed_steps += 1
        print(f"   ✅ PASS: {name}")
    else:
        failed_steps += 1
        print(f"   ❌ FAIL: {name}")
    if detail:
        print(f"      └── {detail}")

def init_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1400,900")
    if os.path.exists("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"):
        options.binary_location = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    return webdriver.Chrome(options=options)

def run_live_ui_audit():
    print("=" * 70)
    print(f"🌐 SIMULATING LIVE USER ACTIONS ON: {BASE_URL}")
    print("=" * 70)

    driver = init_driver()
    wait = WebDriverWait(driver, 15)

    try:
        # -------------------------------------------------------------
        # 1. Desktop Navigation & Brand Spillover Audit
        # -------------------------------------------------------------
        print("\n1. Auditing Desktop Navbar & Brand Header...")
        driver.get(BASE_URL)
        time.sleep(2)
        
        # Verify title
        title_ok = "Stock Research" in driver.title or "Institutional" in driver.title
        log_step("Page Title Integrity", title_ok, driver.title)

        # Verify Brand Title & Subtitle presence
        brand_text = driver.find_element(By.CLASS_NAME, "brand-text")
        log_step("Navbar Brand Element", brand_text.is_displayed(), brand_text.text)

        # -------------------------------------------------------------
        # 2. Simulating Search Bar Interaction
        # -------------------------------------------------------------
        print("\n2. Simulating Search Input & Form Submission...")
        search_inputs = driver.find_elements(By.ID, "mainSearchInput")
        if search_inputs:
            search_box = search_inputs[0]
            search_box.clear()
            search_box.send_keys("INFY")
            time.sleep(0.5)
            
            # Click search submit button or form submit
            search_form = driver.find_element(By.ID, "mainSearchForm")
            search_form.submit()
            time.sleep(3)
            
            is_dossier = "/dossier/INFY" in driver.current_url or "INFY" in driver.title
            log_step("Search Navigation to INFY Dossier", is_dossier, f"URL: {driver.current_url}")
        else:
            log_step("Search Input Present", False, "No search field found")

        # -------------------------------------------------------------
        # 3. Simulating 7-Pillar Collapsible Accordions on Dossier View
        # -------------------------------------------------------------
        print("\n3. Simulating 7-Pillar Accordion & Toggle Buttons...")
        if "/dossier/" not in driver.current_url:
            driver.get(f"{BASE_URL}/dossier/INFY")
            time.sleep(3)

        accordions = driver.find_elements(By.CLASS_NAME, "pillar-accordion")
        log_step(f"Found {len(accordions)} Pillar Accordion Containers", len(accordions) >= 7, f"Count: {len(accordions)}")

        # Click [⊟ Collapse All (Mobile View)]
        btn_collapse_all = wait.until(EC.element_to_be_clickable((By.ID, "btnCollapseAllPillars")))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn_collapse_all)
        time.sleep(0.5)
        btn_collapse_all.click()
        time.sleep(1)

        # Verify all accordions are collapsed (open attribute removed)
        collapsed_elements = [el for el in accordions if not el.get_attribute("open")]
        log_step("Simulate Click: [⊟ Collapse All (Mobile View)]", len(collapsed_elements) == len(accordions), f"Collapsed: {len(collapsed_elements)}/{len(accordions)}")

        # Click [⊞ Expand All Pillars]
        btn_expand_all = wait.until(EC.element_to_be_clickable((By.ID, "btnExpandAllPillars")))
        btn_expand_all.click()
        time.sleep(1)

        expanded_elements = [el for el in accordions if el.get_attribute("open")]
        log_step("Simulate Click: [⊞ Expand All Pillars]", len(expanded_elements) == len(accordions), f"Expanded: {len(expanded_elements)}/{len(accordions)}")

        # Click first individual accordion summary to toggle
        if accordions:
            first_summary = accordions[0].find_element(By.TAG_NAME, "summary")
            first_summary.click()
            time.sleep(0.5)
            first_is_closed = not accordions[0].get_attribute("open")
            log_step("Simulate Click: Individual Pillar Accordion Header", first_is_closed, "Toggled cleanly")

        # Verify verified BSE Regulatory citations exist
        bse_links = driver.find_elements(By.CSS_SELECTOR, "a[href*='bseindia.com']")
        log_step(f"Verified BSE Regulatory Citations Deep Links", len(bse_links) >= 7, f"Found {len(bse_links)} BSE deep citations")

        # -------------------------------------------------------------
        # 4. Simulating Mobile Responsive Menu Drawer
        # -------------------------------------------------------------
        print("\n4. Simulating Mobile Viewport & Hamburger Menu Drawer...")
        driver.set_window_size(375, 812)
        time.sleep(1)

        mobile_btn = wait.until(EC.presence_of_element_located((By.ID, "mobileMenuBtn")))
        log_step("Mobile Menu Hamburger Present (<1120px)", mobile_btn.is_displayed())

        # Click hamburger to open drawer
        main_nav = driver.find_element(By.ID, "mainNav")
        driver.execute_script("arguments[0].click();", mobile_btn)
        time.sleep(0.5)
        nav_open = "mobile-open" in main_nav.get_attribute("class")
        log_step("Simulate Click: Hamburger Toggle Opens Drawer", nav_open)

        # Click hamburger again to close drawer
        driver.execute_script("arguments[0].click();", mobile_btn)
        time.sleep(0.5)
        nav_closed = "mobile-open" not in main_nav.get_attribute("class")
        log_step("Simulate Click: Hamburger Toggle Closes Drawer", nav_closed)

        # Restore desktop window
        driver.set_window_size(1400, 900)
        time.sleep(1)

        # -------------------------------------------------------------
        # 5. Simulating Peer Comparison Flow
        # -------------------------------------------------------------
        print("\n5. Simulating Peer Comparison Flow (/compare)...")
        driver.get(f"{BASE_URL}/compare")
        time.sleep(2)

        input_a = wait.until(EC.presence_of_element_located((By.NAME, "a")))
        input_b = wait.until(EC.presence_of_element_located((By.NAME, "b")))
        input_a.clear()
        input_a.send_keys("INFY")
        input_b.clear()
        input_b.send_keys("TCS")

        compare_btn = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", compare_btn)
        time.sleep(0.5)
        compare_btn.click()

        # Wait for comparison table/cards to render
        compare_wait = WebDriverWait(driver, 20)
        has_comparison = False
        try:
            compare_wait.until(lambda d: "INFY" in d.page_source and "TCS" in d.page_source and ("Disparity" in d.page_source or "Ratios" in d.page_source or "Alignment" in d.page_source))
            has_comparison = True
        except Exception:
            has_comparison = False

        log_step("Simulate Click: Run Side-by-Side Diagnostic", has_comparison, f"Current URL: {driver.current_url}")

        # -------------------------------------------------------------
        # 6. Simulating Pricing & Checkout Modal Trigger
        # -------------------------------------------------------------
        print("\n6. Simulating Pricing Page & Checkout Modal...")
        driver.get(f"{BASE_URL}/pricing")
        time.sleep(2)

        # Set up a test user session in localStorage so purchase modal opens cleanly
        driver.execute_script("""
            const user = {
                id: 'live_test_' + Date.now(),
                email: 'analyst@veritex.ai',
                full_name: 'Institutional Auditor',
                phone: '9820098200',
                credits_balance: 2.0
            };
            localStorage.setItem('sr_user', JSON.stringify(user));
        """)
        driver.refresh()
        time.sleep(2)

        buy_btns = driver.find_elements(By.XPATH, "//button[contains(text(), 'Purchase') or contains(text(), 'Activate')]")
        if buy_btns:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", buy_btns[0])
            time.sleep(0.5)
            buy_btns[0].click()
            time.sleep(1)

            modal = driver.find_element(By.ID, "checkoutModal")
            modal_visible = "active" in modal.get_attribute("class") or modal.is_displayed()
            log_step("Simulate Click: Purchase Single Pass Opens Checkout Modal", modal_visible)

            # Close modal
            close_btn = driver.find_element(By.ID, "closeModalBtn")
            close_btn.click()
            time.sleep(0.5)
            modal_hidden = "active" not in modal.get_attribute("class")
            log_step("Simulate Click: Modal Close Button (✕)", modal_hidden)
        else:
            log_step("Purchase CTA Buttons Present", False)

        # -------------------------------------------------------------
        # 7. Simulating Grievance & Complaint Desk Form
        # -------------------------------------------------------------
        print("\n7. Auditing Contact & Grievance Desk Form (/contact)...")
        driver.get(f"{BASE_URL}/contact")
        time.sleep(2)

        has_contact_fields = (
            len(driver.find_elements(By.NAME, "user_name")) > 0
            and len(driver.find_elements(By.NAME, "user_email")) > 0
            and len(driver.find_elements(By.NAME, "message")) > 0
            and len(driver.find_elements(By.NAME, "category")) > 0
        )
        log_step("Grievance Desk Form Fields Audited", has_contact_fields)

        # -------------------------------------------------------------
        # 8. Stock Discovery @9AM Section Verification
        # -------------------------------------------------------------
        print("\n8. Auditing Stock Discovery @9AM Section (/discovery)...")
        driver.get(f"{BASE_URL}/discovery")
        time.sleep(2)

        has_9am_title = "Stock Discovery @9AM" in driver.page_source
        has_cards = len(driver.find_elements(By.CLASS_NAME, "reel-card")) > 0 or "Edition" in driver.page_source
        log_step("Stock Discovery @9AM Section Rendered", has_9am_title and has_cards)

    except Exception as e:
        log_step("Unexpected Exception During Live Simulation", False, str(e))
    finally:
        driver.quit()

    print("\n" + "=" * 70)
    print(f"📊 LIVE AUDIT RESULTS: {passed_steps} PASSED, {failed_steps} FAILED")
    print("=" * 70)
    if failed_steps > 0:
        sys.exit(1)

if __name__ == "__main__":
    run_live_ui_audit()

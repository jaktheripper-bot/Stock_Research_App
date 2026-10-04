import time
import os
import sys
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

TARGET_URL = "https://stock-research-app-2ljm.onrender.com/pricing"
CARD_NUM = "4100280000001007"
CARD_EXP = "1226"
CARD_CVV = "123"

options = Options()
options.add_argument('--headless=new')
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')
options.add_argument('--window-size=1280,900')
options.binary_location = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'

driver = webdriver.Chrome(options=options)
wait = WebDriverWait(driver, 35)

try:
    print(f"1. Navigating to live URL: {TARGET_URL}...")
    driver.get(TARGET_URL)
    time.sleep(3)

    print("2. Setting up user session in localStorage...")
    driver.execute_script("""
        const user = {
            id: 'live_test_advisor_' + Date.now(),
            email: 'test_advisor@example.com',
            full_name: 'Test Advisor',
            phone: '9820098200',
            credits_balance: 2.0
        };
        localStorage.setItem('sr_user', JSON.stringify(user));
    """)
    driver.refresh()
    time.sleep(3)

    print("3. Clicking 'Purchase Single Pass'...")
    single_pass_btn = wait.until(EC.presence_of_element_located((By.XPATH, "//button[contains(text(), 'Purchase Single Pass')]")))
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", single_pass_btn)
    time.sleep(1)
    driver.execute_script("arguments[0].click();", single_pass_btn)
    print("Clicked Purchase Single Pass button.")

    print("4. Waiting for checkout modal and clicking Pay / Confirm...")
    confirm_btn = wait.until(EC.element_to_be_clickable((By.ID, "modalConfirmBtn")))
    time.sleep(1)
    confirm_btn.click()

    print("5. Waiting for Razorpay Checkout iframe...")
    iframe = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "iframe.razorpay-checkout-frame")))
    print("Razorpay iframe located! Switching to iframe context...")
    driver.switch_to.frame(iframe)
    time.sleep(3)

    # Check if contact details modal is present
    try:
        close_x = driver.find_elements(By.XPATH, "//div[contains(., 'Contact details')]//button[contains(@class, 'close') or text()='✕' or text()='×']")
        if close_x:
            print("Closing contact details modal...")
            driver.execute_script("arguments[0].click();", close_x[0])
            time.sleep(1)
        else:
            contact_inputs = driver.find_elements(By.CSS_SELECTOR, "input[name='contact'], input[placeholder*='Mobile']")
            if contact_inputs and contact_inputs[0].is_displayed():
                print("Contact details modal detected. Entering mobile number...")
                contact_inputs[0].clear()
                contact_inputs[0].send_keys("9820098200")
                time.sleep(1)
                cont_btn = driver.find_element(By.XPATH, "//button[contains(text(), 'Continue') or contains(., 'Continue')]")
                driver.execute_script("arguments[0].click();", cont_btn)
                time.sleep(2)
                print("Submitted contact modal.")
    except Exception as ce:
        print("Contact modal handling exception:", ce)

    # Click Card payment option
    print("Selecting Card payment option...")
    card_option = wait.until(EC.element_to_be_clickable((By.XPATH, "//*[contains(text(), 'Card') or contains(@class, 'card')]")))
    driver.execute_script("arguments[0].click();", card_option)
    time.sleep(2)

    # Enter Card Number
    print(f"Entering card details: {CARD_NUM}, {CARD_EXP}, {CARD_CVV}...")
    card_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[name*='number'], input[id*='number'], input[placeholder*='Card Number']")))
    card_input.clear()
    for ch in CARD_NUM:
        card_input.send_keys(ch)
        time.sleep(0.04)
    time.sleep(0.5)

    # Expiry
    exp_input = driver.find_element(By.CSS_SELECTOR, "input[name*='expiry'], input[id*='expiry'], input[placeholder*='MM / YY'], input[placeholder*='MM/YY']")
    for ch in CARD_EXP:
        exp_input.send_keys(ch)
        time.sleep(0.04)
    time.sleep(0.5)

    # CVV
    cvv_input = driver.find_element(By.CSS_SELECTOR, "input[name*='cvv'], input[id*='cvv'], input[placeholder*='CVV']")
    for ch in CARD_CVV:
        cvv_input.send_keys(ch)
        time.sleep(0.04)
    time.sleep(1)

    driver.save_screenshot("scratch/live_step_card_filled.png")
    print("Saved screenshot scratch/live_step_card_filled.png")

    # Click Continue / Pay button
    action_btn = driver.find_element(By.XPATH, "//button[contains(., 'Continue') or contains(., 'Pay') or contains(@id, 'pay-button')]")
    print(f"Clicking submission button: '{action_btn.text}'...")
    driver.execute_script("arguments[0].click();", action_btn)
    time.sleep(3)

    # Check for "Save your card as per RBI guidelines?" modal
    try:
        maybe_later_btns = driver.find_elements(By.XPATH, "//button[contains(text(), 'Maybe later') or contains(., 'Maybe later') or contains(text(), 'Yes, secure')]")
        if maybe_later_btns:
            print("RBI card tokenization prompt detected. Clicking 'Maybe later'...")
            driver.execute_script("arguments[0].click();", maybe_later_btns[0])
            time.sleep(3)
    except Exception as re:
        print("RBI modal check exception:", re)

    driver.save_screenshot("scratch/live_step_after_card_submit.png")
    print("Saved screenshot scratch/live_step_after_card_submit.png")

    # In Razorpay test mode, OTP / Bank simulator screen will open. Check for Success button.
    driver.switch_to.default_content()
    time.sleep(2)

    found_success = False
    for attempt in range(15):
        # Look in default content
        success_btns = driver.find_elements(By.XPATH, "//button[text()='Success' or contains(@class, 'success') or contains(text(), 'Success')]")
        if success_btns and success_btns[0].is_displayed():
            print("Found Success button in main document! Clicking...")
            driver.execute_script("arguments[0].click();", success_btns[0])
            found_success = True
            break

        # Look in all iframes
        all_frames = driver.find_elements(By.TAG_NAME, "iframe")
        for f in all_frames:
            try:
                driver.switch_to.frame(f)
                s_btns = driver.find_elements(By.XPATH, "//button[text()='Success' or contains(text(), 'Success')]")
                if s_btns and s_btns[0].is_displayed():
                    print("Found Success button in iframe! Clicking...")
                    driver.execute_script("arguments[0].click();", s_btns[0])
                    found_success = True
                    break
            except Exception:
                pass
            driver.switch_to.default_content()

        if found_success:
            break
        print(f"Waiting for Razorpay simulator Success button... (attempt {attempt+1}/15)")
        time.sleep(2)

    driver.switch_to.default_content()
    time.sleep(6)

    driver.save_screenshot("scratch/live_step_final_card_result.png")
    print("Final live Card screenshot saved to scratch/live_step_final_card_result.png")

except Exception as e:
    print(f"Error during Live Card test: {e}")
    try:
        driver.save_screenshot("scratch/live_razorpay_card_error.png")
    except Exception:
        pass
finally:
    driver.quit()
    print("Live Card test script finished.")

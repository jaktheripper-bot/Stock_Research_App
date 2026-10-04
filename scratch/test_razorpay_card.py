import time
import os
import sys
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys

options = Options()
options.add_argument('--headless=new')
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')
options.add_argument('--window-size=1280,900')
options.binary_location = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'

driver = webdriver.Chrome(options=options)
wait = WebDriverWait(driver, 25)

try:
    print("1. Navigating to http://localhost:8501/pricing...")
    driver.get("http://localhost:8501/pricing")
    time.sleep(2)

    print("2. Setting up user session in localStorage...")
    driver.execute_script("""
        const user = {
            id: 'test_advisor_' + Date.now(),
            email: 'test_advisor@example.com',
            full_name: 'Test Advisor',
            phone: '9999999999',
            credits_balance: 2.0
        };
        localStorage.setItem('sr_user', JSON.stringify(user));
    """)
    driver.refresh()
    time.sleep(2)

    print("3. Clicking 'Purchase Single Pass'...")
    single_pass_btn = wait.until(EC.presence_of_element_located((By.XPATH, "//button[contains(text(), 'Purchase Single Pass')]")))
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", single_pass_btn)
    time.sleep(1)
    driver.execute_script("arguments[0].click();", single_pass_btn)
    print("Clicked Purchase Single Pass button.")

    print("4. Waiting for checkout modal and clicking Confirm...")
    confirm_btn = wait.until(EC.element_to_be_clickable((By.ID, "modalConfirmBtn")))
    time.sleep(1)
    confirm_btn.click()

    print("5. Waiting for Razorpay Checkout iframe...")
    iframe = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "iframe.razorpay-checkout-frame")))
    print("Razorpay iframe located! Switching to iframe context...")
    driver.switch_to.frame(iframe)
    time.sleep(3)

    # Check if contact modal is present; if so, dismiss via close button or fill phone
    try:
        modal_close = driver.find_elements(By.CSS_SELECTOR, "button[aria-label='Close'], button.close, [class*='modal'] button")
        # In screenshot, the modal has an '×' button on top-right:
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
                for ch in "9820098200":
                    contact_inputs[0].send_keys(ch)
                    time.sleep(0.05)
                time.sleep(1)
                continue_btn = driver.find_element(By.XPATH, "//button[contains(text(), 'Continue') or contains(., 'Continue')]")
                driver.execute_script("arguments[0].click();", continue_btn)
                time.sleep(2)
                print("Submitted contact modal.")
    except Exception as ce:
        print("Contact modal handling error (or not present):", ce)

    # Click Card payment option
    print("Selecting Card payment option...")
    card_option = wait.until(EC.element_to_be_clickable((By.XPATH, "//*[contains(text(), 'Card') or contains(@class, 'card')]")))
    driver.execute_script("arguments[0].click();", card_option)
    time.sleep(2)

    driver.save_screenshot("scratch/step_card_selected.png")
    print("Saved screenshot step_card_selected.png")

    print("Entering card details (4100 2800 0000 1007, 12/26, 123)...")
    # In Razorpay checkout, card fields might be individual inputs or within sub-iframes
    # Let's inspect inputs in frame
    inputs = driver.find_elements(By.TAG_NAME, "input")
    for inp in inputs:
        name = inp.get_attribute("name") or ""
        placeholder = inp.get_attribute("placeholder") or ""
        id_attr = inp.get_attribute("id") or ""
        print(f"Found input: id='{id_attr}', name='{name}', placeholder='{placeholder}'")

    # Locate card number input
    card_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[name*='number'], input[id*='number'], input[placeholder*='Card Number']")))
    card_input.clear()
    for ch in "4100280000001007":
        card_input.send_keys(ch)
        time.sleep(0.05)
    time.sleep(1)

    # Expiry
    exp_input = driver.find_element(By.CSS_SELECTOR, "input[name*='expiry'], input[id*='expiry'], input[placeholder*='MM / YY'], input[placeholder*='MM/YY']")
    for ch in "1226":
        exp_input.send_keys(ch)
        time.sleep(0.05)
    time.sleep(1)

    # CVV
    cvv_input = driver.find_element(By.CSS_SELECTOR, "input[name*='cvv'], input[id*='cvv'], input[placeholder*='CVV']")
    for ch in "123":
        cvv_input.send_keys(ch)
        time.sleep(0.05)
    time.sleep(1)

    driver.save_screenshot("scratch/step_card_filled.png")
    print("Saved screenshot step_card_filled.png")

    # Click Pay button
    pay_btn = driver.find_element(By.XPATH, "//button[contains(., 'Pay') or contains(@id, 'pay-button') or contains(@class, 'pay-btn')]")
    print("Clicking Pay button...")
    driver.execute_script("arguments[0].click();", pay_btn)
    time.sleep(5)

    driver.save_screenshot("scratch/step_after_pay.png")
    print("Saved screenshot step_after_pay.png")

    # In Razorpay test mode, it redirects to the bank simulator or displays an OTP screen
    # Check if inside a subframe or redirected
    driver.switch_to.default_content()
    time.sleep(2)

    # Check for success button across all frames or main content
    found_success = False
    for attempt in range(10):
        # Look in default content
        success_btns = driver.find_elements(By.XPATH, "//button[text()='Success' or contains(@class, 'success')]")
        if success_btns:
            print("Found Success button in main document! Clicking...")
            success_btns[0].click()
            found_success = True
            break

        # Look in iframes
        all_frames = driver.find_elements(By.TAG_NAME, "iframe")
        for f in all_frames:
            try:
                driver.switch_to.frame(f)
                s_btns = driver.find_elements(By.XPATH, "//button[text()='Success' or contains(text(), 'Success')]")
                if s_btns:
                    print("Found Success button in iframe! Clicking...")
                    driver.execute_script("arguments[0].click();", s_btns[0])
                    found_success = True
                    break
            except Exception:
                pass
            driver.switch_to.default_content()

        if found_success:
            break
        time.sleep(2)

    driver.switch_to.default_content()
    time.sleep(5)

    driver.save_screenshot("scratch/step_final_card_result.png")
    print("Final screenshot saved to scratch/step_final_card_result.png")
    print("Final page body:\n", driver.find_element(By.TAG_NAME, "body").text[:400])

except Exception as e:
    print(f"Error during Card test: {e}")
    try:
        driver.save_screenshot("scratch/razorpay_card_error.png")
        print("Error screenshot saved to scratch/razorpay_card_error.png")
    except Exception:
        pass
finally:
    driver.quit()
    print("Test finished.")

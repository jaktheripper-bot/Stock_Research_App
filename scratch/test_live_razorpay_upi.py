import time
import os
import sys
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

TARGET_URL = "https://stock-research-app-2ljm.onrender.com/pricing"
UPI_ID = "test@razorpay"

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
            id: 'live_test_upi_' + Date.now(),
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
        print("Contact modal check:", ce)

    # Click UPI payment option
    print("Selecting UPI payment option...")
    upi_option = wait.until(EC.element_to_be_clickable((By.XPATH, "//*[contains(text(), 'UPI') or contains(@class, 'upi')]")))
    driver.execute_script("arguments[0].click();", upi_option)
    time.sleep(2)

    driver.save_screenshot("scratch/live_upi_selected.png")
    print("Saved scratch/live_upi_selected.png")

    # In Razorpay UPI screen, there is an option for 'UPI ID / VPA'
    # Look for UPI input field or button to enter UPI ID
    vpa_inputs = driver.find_elements(By.CSS_SELECTOR, "input[name*='vpa'], input[placeholder*='UPI ID'], input[placeholder*='Google Pay / PhonePe / Paytm ID']")
    if not vpa_inputs:
        # Maybe there's a button like 'UPI ID / Number'
        enter_vpa_btn = driver.find_elements(By.XPATH, "//*[contains(text(), 'UPI ID') or contains(text(), 'Enter UPI ID') or contains(text(), 'Add new UPI ID')]")
        if enter_vpa_btn:
            print("Clicking 'Enter UPI ID' selector...")
            driver.execute_script("arguments[0].click();", enter_vpa_btn[0])
            time.sleep(1.5)
            vpa_inputs = driver.find_elements(By.CSS_SELECTOR, "input[name*='vpa'], input[placeholder*='UPI ID'], input[type='text']")

    if vpa_inputs:
        print(f"Entering UPI ID: {UPI_ID}...")
        vpa_inputs[0].clear()
        vpa_inputs[0].send_keys(UPI_ID)
        time.sleep(1)
    else:
        print("Could not find VPA input directly, printing all inputs:")
        for inp in driver.find_elements(By.TAG_NAME, "input"):
            print(f"Input: name='{inp.get_attribute('name')}', placeholder='{inp.get_attribute('placeholder')}'")

    driver.save_screenshot("scratch/live_upi_filled.png")
    print("Saved scratch/live_upi_filled.png")

    # Click Pay / Verify and Pay
    pay_btn = driver.find_element(By.XPATH, "//button[contains(., 'Pay') or contains(., 'Continue') or contains(., 'Verify')]")
    print(f"Clicking pay button '{pay_btn.text}'...")
    driver.execute_script("arguments[0].click();", pay_btn)
    time.sleep(5)

    driver.save_screenshot("scratch/live_upi_after_pay.png")
    print("Saved scratch/live_upi_after_pay.png")

    # Check for success button in simulator (main window or iframes)
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
        print(f"Waiting for Razorpay UPI simulator Success button... (attempt {attempt+1}/15)")
        time.sleep(2)

    driver.switch_to.default_content()
    time.sleep(6)

    driver.save_screenshot("scratch/live_upi_final_result.png")
    print("Final live UPI screenshot saved to scratch/live_upi_final_result.png")

except Exception as e:
    print(f"Error during Live UPI test: {e}")
    try:
        driver.save_screenshot("scratch/live_razorpay_upi_error.png")
    except Exception:
        pass
finally:
    driver.quit()
    print("Live UPI test finished.")

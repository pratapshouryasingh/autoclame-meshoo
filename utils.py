from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import json
import time
import os
import csv
import shutil
import signal
import sys
from pathlib import Path
from datetime import datetime

# ===================== GLOBALS =====================
driver = None
wait = None
current_account = None
processed_awbs_in_session = []
should_shutdown = False

# ===================== GRACEFUL SHUTDOWN HANDLER =====================
def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully"""
    global should_shutdown, driver, current_account, processed_awbs_in_session
    print("\n⚠️ Received interrupt signal (Ctrl+C). Shutting down gracefully...")
    should_shutdown = True
    
    # Save current state if we have account info
    if current_account and processed_awbs_in_session:
        save_session_state(current_account, processed_awbs_in_session)
        print(f"Session state saved for {current_account}")
    
    # Close driver if open
    if driver:
        print("Closing browser...")
        driver.quit()
    
    print("✅ Graceful shutdown complete")
    sys.exit(0)

def register_signal_handlers():
    """Register signal handlers for graceful shutdown"""
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

def save_session_state(account_name, processed_awbs):
    """Save current processing state to resume later"""
    try:
        state_dir = Path("Data") / "sessions"
        state_dir.mkdir(parents=True, exist_ok=True)
        state_file = state_dir / f"session_{account_name}.json"
        
        state_data = {
            "account": account_name,
            "processed_awbs": processed_awbs,
            "timestamp": datetime.now().isoformat(),
            "last_processed": processed_awbs[-1] if processed_awbs else None
        }
        
        with open(state_file, "w") as f:
            json.dump(state_data, f, indent=2)
        
        return True
    except Exception as e:
        print(f"Failed to save session state: {e}")
        return False

def load_session_state(account_name):
    """Load previous session state"""
    try:
        state_file = Path("Data") / "sessions" / f"session_{account_name}.json"
        if state_file.exists():
            with open(state_file, "r") as f:
                state_data = json.load(f)
            print(f"Loaded session state - previously processed {len(state_data.get('processed_awbs', []))} folders")
            return state_data
    except Exception as e:
        print(f"Failed to load session state: {e}")
    return None

def clear_session_state(account_name):
    """Clear session state after successful completion"""
    try:
        state_file = Path("Data") / "sessions" / f"session_{account_name}.json"
        if state_file.exists():
            state_file.unlink()
    except Exception as e:
        pass

# ===================== DRIVER SETUP =====================
def setup_driver():
    """Initialize the WebDriver"""
    global driver, wait
    driver = webdriver.Chrome()
    driver.maximize_window()
    wait = WebDriverWait(driver, 15)
    return driver, wait

def quit_driver():
    """Quit the WebDriver"""
    global driver
    if driver:
        driver.quit()
        driver = None

# ===================== EXTRACT ACCOUNT CODE FROM HOME URL =====================
def extract_account_code_from_home_url(driver):
    """
    Extracts the unique account code (e.g., 'lr4cm') from the current home page URL.
    Pattern: https://supplier.meesho.com/panel/v3/new/growth/{account_code}/home
    """
    current_url = driver.current_url
    parts = current_url.split('/')
    
    try:
        # Find the index of 'growth' and get the next segment
        growth_index = parts.index('growth')
        account_code = parts[growth_index + 1]
        print(f"Extracted account code: {account_code}")
        return account_code
    except (ValueError, IndexError):
        print("Warning: Could not extract account code from URL.")
        print(f"Current URL: {current_url}")
        return None

# ===================== LOGIN FUNCTION =====================
def login_to_account(email, password):
    print(f"\nLogging in with: {email}")

    driver.get("https://supplier.meesho.com/panel/v3/new/root/login")
    time.sleep(5)  # allow full React + bot check render

    # Type email
    email_input = wait.until(
        EC.presence_of_element_located((By.XPATH, "//input[@type='text' or @type='email']"))
    )
    email_input.clear()
    email_input.send_keys(email)

    # Type password
    password_input = wait.until(
        EC.presence_of_element_located((By.XPATH, "//input[@type='password']"))
    )
    password_input.clear()
    password_input.send_keys(password)

    time.sleep(2)

    # JS click on "Log in" button (bypasses MUI/React issues)
    driver.execute_script("""
        const btn = [...document.querySelectorAll('button')]
            .find(b => b.innerText.trim().toLowerCase() === 'log in');
        if (btn) btn.click();
    """)

    time.sleep(6)

    # simple success check
    if "login" in driver.current_url.lower():
        print("Login might have failed.")
        return False

    print("Login successful!")
    return True

# ===================== LOGOUT FUNCTION =====================
def logout_from_account(driver, wait):
    print("\nLogging out...")
    try:
        # Click on profile/avatar
        profile_button = wait.until(
            EC.element_to_be_clickable(
                (By.XPATH, "//button[contains(@class,'MuiIconButton-root') or .//*[contains(@class,'MuiAvatar-root')]]")
            )
        )
        profile_button.click()
        time.sleep(0.5)
        
        # Find and click logout option
        logout_option = wait.until(
            EC.element_to_be_clickable(
                (By.XPATH, "//li[contains(.,'Logout') or contains(.,'Log out') or contains(.,'Sign out')]")
            )
        )
        logout_option.click()
        time.sleep(2)
        
        # Wait for logout to complete
        wait.until(EC.presence_of_element_located((By.XPATH, "//input[@type='password']")))
        print("Logout successful!")
        return True
    except Exception as e:
        print(f"Logout failed: {e}")
        # Force logout by clearing cookies and refreshing
        driver.delete_all_cookies()
        driver.refresh()
        time.sleep(2)
        return True

# ===================== POPUP KILLER =====================
def force_close_popup(driver):
    driver.switch_to.default_content()
    try:
        driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
    except:
        pass

    driver.execute_script("""
        document.querySelectorAll('[role="dialog"], .MuiDialog-root, .MuiModal-root')
        .forEach(el => el.remove());
        document.querySelectorAll('.MuiBackdrop-root')
        .forEach(el => el.remove());
        document.body.style.overflow = 'auto';
    """)
    time.sleep(0.5)

# ===================== DATA EXTRACTION =====================
def get_next_pending_folder(account_name, processed_awbs):
    """Get the next pending folder for processing, skipping already processed ones and checking status.csv"""
    base = Path("Data") / "pending" / account_name
    if not base.exists():
        return None
    
    # Load status.csv to know which ones are already done/skipped/already_raised/failed
    CSV_PATH = Path("Data") / "status.csv"
    completed_suborders = set()
    
    if CSV_PATH.exists():
        with open(CSV_PATH, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader, None)  # Skip header
            for row in reader:
                if len(row) >= 2 and row[1] in ["done", "skipped", "already_raised", "failed"]:
                    completed_suborders.add(row[0])
    
    folders = [f for f in base.iterdir() if f.is_dir()]
    if not folders:
        return None
    
    # Sort by creation time or name
    folders.sort(key=lambda x: x.stat().st_ctime)
    
    # Find first folder with AWB not already processed
    for folder in folders:
        parts = folder.name.split("_")
        if len(parts) >= 2:
            awb = parts[0]
            suborder_id = parts[0]  # First part is suborder_id
            
            # Skip if already processed in this session or marked as done/skipped/already_raised/failed in CSV
            if awb not in processed_awbs and suborder_id not in completed_suborders:
                return {
                    "awb": awb,
                    "packet_id": parts[1],
                    "folder": folder,
                    "suborder_id": suborder_id
                }
    return None

# ===================== FORM HELPERS =====================
def fill_mui_input_by_label(driver, wait, label_partial_text, value):
    """Fill normal text input field"""
    wrapper = wait.until(
        EC.element_to_be_clickable((
            By.XPATH,
            f"//label[contains(normalize-space(.), '{label_partial_text}')]/ancestor::div[contains(@class,'MuiFormControl')]//div[contains(@class,'MuiInputBase-root')]"
        ))
    )
    
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", wrapper)
    time.sleep(0.2)
    wrapper.click()
    time.sleep(0.1)
    
    input_el = wrapper.find_element(By.TAG_NAME, "input")
    
    try:
        input_el.click()
        input_el.send_keys(Keys.CONTROL + "a")
        input_el.send_keys(Keys.DELETE)
        time.sleep(0.05)
    except:
        pass
    
    input_el.send_keys(value)

def select_meesho_dropdown(driver, wait, label_text, option_text):
    """Select option from any dropdown by label"""
    print(f"Selecting '{option_text}' for '{label_text}'...")
    
    try:
        # Try to find the label element
        label_xpath = f"//p[contains(normalize-space(.), '{label_text}')]"
        wait.until(EC.presence_of_element_located((By.XPATH, label_xpath)))
        
        # Find the trigger element (dropdown)
        trigger_xpath = f"{label_xpath}/ancestor::div[contains(@class, 'MuiBox-root')][1]"
        trigger = wait.until(EC.element_to_be_clickable((By.XPATH, trigger_xpath)))
        
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", trigger)
        time.sleep(0.3)
        
        driver.execute_script("arguments[0].click();", trigger)
        time.sleep(0.5)
        
        # Try multiple ways to find and click the option
        option_selectors = [
            f"//li[contains(., '{option_text}')]",
            f"//div[@role='option'][contains(., '{option_text}')]",
            f"//*[not(self::script)][text()='{option_text}']",
            f"//*[contains(text(), '{option_text}')]"
        ]
        
        success = False
        for selector in option_selectors:
            try:
                option_el = WebDriverWait(driver, 1).until(
                    EC.element_to_be_clickable((By.XPATH, selector))
                )
                driver.execute_script("arguments[0].click();", option_el)
                print(f"Successfully selected: {option_text}")
                success = True
                break
            except:
                continue
        
        if not success:
            print(f"Could not select '{option_text}', trying fallback method...")
            # Try keyboard navigation
            trigger.click()
            time.sleep(0.3)
            from selenium.webdriver import ActionChains
            ActionChains(driver).send_keys(Keys.DOWN).send_keys(Keys.DOWN).send_keys(Keys.ENTER).perform()
            
    except Exception as e:
        print(f"Dropdown Error for '{label_text}': {e}")
        # Try alternative method to find and select dropdown
        try:
            # Look for any dropdown that might be related to the label
            dropdown_xpath = f"//div[contains(@class, 'MuiFormControl-root')]//p[contains(text(), '{label_text}')]/following::div[contains(@class, 'MuiSelect-root')][1]"
            dropdown = wait.until(EC.element_to_be_clickable((By.XPATH, dropdown_xpath)))
            dropdown.click()
            time.sleep(0.5)
            
            # Try to find and click the option
            option_xpath = f"//ul[@role='listbox']//li[contains(., '{option_text}')]"
            option = wait.until(EC.element_to_be_clickable((By.XPATH, option_xpath)))
            option.click()
            print(f"Selected '{option_text}' via alternative method")
        except Exception as e2:
            print(f"Alternative dropdown method also failed: {e2}")
    
    time.sleep(0.5)

def get_issue_serial_from_folder(folder: Path) -> int:
    """
    Determine issue serial number based on packet_id (second part of folder name).
    If packet_id contains "TP" -> RTO case (139)
    Otherwise -> Wrong product case (1)
    """
    name = folder.name
    parts = name.split("_")
    
    if len(parts) >= 2:
        packet_id = parts[1]  # Second part like TP1ELEU02376822
        
        # Check if packet_id contains "TP" - RTO case
        if "TP" in packet_id:
            return 139  # Wrong barcoded package in RTO
        
        # Anything else is wrong product
        return 1  # Wrong return
    
    return 1  # Default to wrong return

def upload_by_input_id_prefix(driver, wait, id_prefix, file_path, is_video=False):
    """Upload file and wait for completion if it's a video"""
    print(f"Uploading {os.path.basename(file_path)} → {id_prefix}")
    
    file_input = wait.until(
        EC.presence_of_element_located((
            By.XPATH,
            f"//input[@type='file' and starts-with(@id, '{id_prefix}')]"
        ))
    )
    
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", file_input)
    time.sleep(0.2)
    
    file_input.send_keys(file_path)
    print(f"File selected: {os.path.basename(file_path)}")
    
    if is_video:
        # For video files, wait longer
        print("Video file detected. Waiting for upload to complete...")
        time.sleep(5)  # Initial wait for upload to start
        time.sleep(10)
    else:
        # For images, shorter wait
        time.sleep(3)
    
    print(f"Upload completed for {os.path.basename(file_path)}")

def get_product_files(folder: Path):
    label = product = video = None
    
    for f in folder.iterdir():
        name = f.name.lower()
        
        if "label" in name:
            label = str(f.resolve())
        elif "product" in name and f.suffix.lower() in [".jpg", ".jpeg", ".png"]:
            product = str(f.resolve())
        elif f.suffix.lower() == ".mp4":
            video = str(f.resolve())
    
    if not label or not product or not video:
        raise Exception(f"Missing required files in product folder: {folder.name}")
    
    return label, product, video


def fill_description(driver, wait, description_text):
    """Fill description field - precise targeting without touching attachments"""
    try:
        print(f"Filling description with: {description_text}")
        
        # Wait for page to be ready
        time.sleep(1)
        
        # PRECISE SELECTOR - Target by the label "Describe the issue" and find the textarea
        field = None
        
        # Method 1: Find by the exact label "Describe the issue" and get the textarea
        try:
            label = driver.find_element(By.XPATH, "//*[contains(text(), 'Describe the issue')]")
            print("Found 'Describe the issue' label")
            
            field = driver.find_element(By.XPATH, "//*[contains(text(), 'Describe the issue')]/ancestor::div[contains(@class, 'MuiFormControl-root')]//textarea")
            if field and field.is_displayed():
                print("Found description textarea via label")
        except:
            pass
        
        # Method 2: Find textarea by placeholder text
        if not field or not field.is_displayed():
            try:
                field = driver.find_element(By.XPATH, "//textarea[contains(@placeholder, 'Describe') or contains(@placeholder, 'issue')]")
                if field.is_displayed():
                    print("Found description field by placeholder")
            except:
                pass
        
        # Method 3: Find textarea by name or id pattern
        if not field or not field.is_displayed():
            try:
                field = driver.find_element(By.XPATH, "//textarea[@name='description' or contains(@id, 'description')]")
                if field.is_displayed():
                    print("Found description field by name/id")
            except:
                pass
        
        # Method 4: Find any visible textarea with rows > 1
        if not field or not field.is_displayed():
            textareas = driver.find_elements(By.TAG_NAME, "textarea")
            for ta in textareas:
                if ta.is_displayed():
                    rows = ta.get_attribute("rows")
                    if rows and int(rows) > 1:
                        field = ta
                        print("Found description field by row count")
                        break
        
        if not field or not field.is_displayed():
            raise Exception("Could not find description textarea field")
        
        # Scroll to field
        driver.execute_script("arguments[0].scrollIntoView({block: 'center', behavior: 'smooth'});", field)
        time.sleep(0.3)
        
        # Click to focus
        field.click()
        time.sleep(0.1)
        
        # Clear existing text
        field.clear()
        time.sleep(0.1)
        
        # Type the text character by character
        for char in description_text:
            field.send_keys(char)
            time.sleep(0.001)  # Very short delay to mimic natural typing
        
        time.sleep(0.1)
        
        # Trigger React events
        driver.execute_script("""
            var element = arguments[0];
            element.dispatchEvent(new Event('input', { bubbles: true }));
            element.dispatchEvent(new Event('change', { bubbles: true }));
        """, field)
        
        # Press Tab to move focus
        field.send_keys(Keys.TAB)
        time.sleep(0.3)
        
        # Verify
        current_value = field.get_attribute("value")
        if current_value == description_text:
            print(f"✅ Description successfully filled")
        else:
            print(f"⚠️ Verification - Current: '{current_value[:50]}'")
            driver.execute_script("arguments[0].value = arguments[1];", field, description_text)
            driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", field)
            print("Used JavaScript fallback")
        
        print("Description field processing complete")
        time.sleep(0.5)
        
    except Exception as e:
        print(f"Error in fill_description: {e}")
        import traceback
        traceback.print_exc()

def check_for_existing_ticket_error(driver, wait):
    """Check if there's an error message about ticket already being raised"""
    try:
        error_xpaths = [
            "//*[contains(text(), 'Ticket') and contains(text(), 'has already been raised')]",
            "//*[contains(text(), 'already been raised for this issue')]",
            "//*[contains(text(), 'Please reply on the same ticket')]",
            "//p[contains(text(), 'has already been raised')]",
            "//div[contains(@class, 'MuiAlert-message')][contains(text(), 'already been raised')]"
        ]
        
        for xpath in error_xpaths:
            try:
                error_element = driver.find_element(By.XPATH, xpath)
                if error_element.is_displayed():
                    error_text = error_element.text
                    print(f"❌ ERROR DETECTED: {error_text}")
                    return True
            except:
                continue
        
        return False
        
    except Exception as e:
        print(f"Error checking for existing ticket: {e}")
        return False

def check_confirmation_and_continue(driver, wait):
    """Check for confirmation page and click continue button if present"""
    try:
        print("Checking for confirmation page...")
        
        confirmation_button_xpaths = [
            "//*[@id='mainWrapper']/div/div/div[2]/div/button[1]",
            "//button[contains(text(), 'Create Another')]",
            "//button[contains(text(), 'Back to Home')]",
            "//button[contains(text(), 'Done')]",
            "//button[contains(@class, 'MuiButton-contained')][contains(text(), 'Create')]"
        ]
        
        for xpath in confirmation_button_xpaths:
            try:
                button = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, xpath))
                )
                print(f"✅ Found confirmation button: {xpath}")
                
                driver.execute_script("arguments[0].click();", button)
                print("Clicked confirmation button")
                time.sleep(2)
                return True
            except:
                continue
        
        success_messages = [
            "//*[contains(text(), 'ticket has been raised')]",
            "//*[contains(text(), 'successfully')]",
            "//*[contains(text(), 'Ticket ID')]"
        ]
        
        for xpath in success_messages:
            try:
                element = driver.find_element(By.XPATH, xpath)
                if element.is_displayed():
                    print(f"✅ Confirmation message detected: {element.text[:50]}")
                    return True
            except:
                continue
        
        print("No confirmation detected")
        return False
        
    except Exception as e:
        print(f"Error checking confirmation: {e}")
        return False

def finalize_current_task(account_name, pending_data, submitted):
    """Move folder to done directory and update status.csv"""
    work_folder = pending_data["folder"]
    suborder_id = work_folder.name.split("_")[0]
    folder_name = work_folder.name
    
    BASE_DONE = Path("Data") / "done" / account_name
    CSV_PATH = Path("Data") / "status.csv"
    
    BASE_DONE.mkdir(parents=True, exist_ok=True)
    
    status = "pending"
    error_detail = ""
    
    if submitted:
        try:
            dest_path = BASE_DONE / work_folder.name
            shutil.move(str(work_folder), str(dest_path))
            status = "done"
            print(f"✅ Moved {work_folder.name} to Data/done/{account_name}/ folder")
        except Exception as e:
            print(f"❌ Error moving folder: {e}")
            status = "pending"
            error_detail = f"Move error: {str(e)[:100]}"
    else:
        status = "failed"
        error_detail = "Submission failed - no confirmation received"
        print(f"⚠️ {work_folder.name} - Submission failed (keeping in pending for retry)")
    
    # Update status.csv
    rows = []
    if CSV_PATH.exists():
        with open(CSV_PATH, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)
    else:
        rows = [["suborder_id", "status", "account_name", "folder_name", "timestamp", "error_details"]]
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    updated = False
    for i, r in enumerate(rows):
        if r and len(r) > 0 and r[0] == suborder_id:
            rows[i] = [suborder_id, status, account_name, folder_name, timestamp, error_detail]
            updated = True
            break
    
    if not updated:
        rows.append([suborder_id, status, account_name, folder_name, timestamp, error_detail])
    
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerows(rows)
    
    print(f"[STATUS] {suborder_id} → {status.upper()} (Account: {account_name})")
    if error_detail:
        print(f"  Error: {error_detail}")
    
    return suborder_id

def finalize_current_task_with_error(account_name, pending_data, error_type="already_raised"):
    """Mark task as already_raised and MOVE folder to already_raised directory"""
    work_folder = pending_data["folder"]
    suborder_id = work_folder.name.split("_")[0]
    folder_name = work_folder.name
    
    # Create already_raised directory
    ALREADY_RAISED_DIR = Path("Data") / "already_raised" / account_name
    CSV_PATH = Path("Data") / "status.csv"
    
    # Move folder to already_raised directory
    try:
        ALREADY_RAISED_DIR.mkdir(parents=True, exist_ok=True)
        dest_path = ALREADY_RAISED_DIR / work_folder.name
        shutil.move(str(work_folder), str(dest_path))
        print(f"✅ Moved {work_folder.name} to Data/already_raised/{account_name}/ folder")
    except Exception as e:
        print(f"❌ Error moving folder to already_raised: {e}")
    
    # Update status.csv
    rows = []
    if CSV_PATH.exists():
        with open(CSV_PATH, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)
    else:
        rows = [["suborder_id", "status", "account_name", "folder_name", "timestamp", "error_details"]]
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    error_detail = "Ticket already raised for this issue"
    
    updated = False
    for i, r in enumerate(rows):
        if r and len(r) > 0 and r[0] == suborder_id:
            rows[i] = [suborder_id, error_type, account_name, folder_name, timestamp, error_detail]
            updated = True
            break
    
    if not updated:
        rows.append([suborder_id, error_type, account_name, folder_name, timestamp, error_detail])
    
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerows(rows)
    
    print(f"[STATUS] {suborder_id} → {error_type.upper()} - {error_detail}")
    return suborder_id

def check_if_table_exists(driver, wait):
    """ULTRA-FAST check if search results table exists - only 1 second"""
    try:
        WebDriverWait(driver, 1).until(
            EC.presence_of_element_located(
                (By.XPATH, "//table//tbody//tr")
            )
        )
        return True
    except:
        return False

def check_if_no_results_message(driver, wait):
    """Check if "No results found" message appears (even faster)"""
    try:
        no_results_indicators = [
            "//*[contains(text(), 'No result') or contains(text(), 'No data') or contains(text(), 'not found')]",
            "//*[contains(@class, 'no-data') or contains(@class, 'empty')]"
        ]
        
        for indicator in no_results_indicators:
            try:
                element = WebDriverWait(driver, 0.5).until(
                    EC.presence_of_element_located((By.XPATH, indicator))
                )
                print("No results message detected!")
                return True
            except:
                continue
        return False
    except:
        return False

def get_suborder_id_from_table(driver, wait):
    """Get suborder ID from search results table - looks for numeric ID in Suborder ID column"""
    try:
        # Method 1: Look for Suborder ID column header and get value from that column
        try:
            headers = driver.find_elements(By.XPATH, "//table//thead//th")
            suborder_col_index = -1
            
            for i, header in enumerate(headers):
                header_text = header.text.strip().lower()
                if "suborder" in header_text or "sub order" in header_text:
                    suborder_col_index = i
                    break
            
            if suborder_col_index != -1:
                cell_xpath = f"//table//tbody//tr[1]//td[{suborder_col_index + 1}]"
                suborder_cell = WebDriverWait(driver, 2).until(
                    EC.visibility_of_element_located((By.XPATH, cell_xpath))
                )
                suborder_id = suborder_cell.text.strip()
                if suborder_id:
                    print(f"Found suborder ID via column index: {suborder_id}")
                    return suborder_id
        except:
            pass
        
        # Method 2: Look for numeric values (suborder IDs are numeric)
        cells = driver.find_elements(By.XPATH, "//table//tbody//tr[1]//td")
        
        for cell in cells:
            cell_text = cell.text.strip()
            # Suborder ID is numeric (like 271572329404)
            if cell_text and cell_text.isdigit() and len(cell_text) >= 10:
                print(f"Found suborder ID by numeric pattern: {cell_text}")
                return cell_text
        
        raise Exception("Could not find suborder ID in search results")
        
    except Exception as e:
        print(f"Error getting suborder ID: {e}")
        raise Exception("Could not find suborder ID in search results")
    
def fill_awb_number(driver, wait, awb_value):
    """
    Stable handler for MUI Autocomplete AWB field
    Works for both text input and dropdown selection scenarios
    """
    print(f"Processing AWB Number: {awb_value}")

    try:
        # Find AWB container using multiple strategies
        container = None
        strategies = [
            "//*[@id='mainWrapper']/div/div/form/div[1]/div[3]/div/div",
            "//label[contains(text(), 'AWB Number')]/ancestor::div[contains(@class, 'MuiFormControl')]//div[contains(@class, 'MuiInputBase-root')]",
            "//div[contains(@class, 'MuiAutocomplete-root')]//input[@placeholder or @aria-label]",
            "//input[@name='awbNumber' or contains(@id, 'awb') or contains(@name, 'awb')]"
        ]
        
        for strategy in strategies:
            try:
                container = wait.until(EC.element_to_be_clickable((By.XPATH, strategy)))
                if container:
                    print(f"Found AWB container using strategy: {strategy[:50]}...")
                    break
            except:
                continue
        
        if not container:
            # Try to find input directly
            input_el = None
            input_strategies = [
                "//input[@placeholder='AWB Number' or @placeholder='AWB']",
                "//input[contains(@id, 'awb')]",
                "//input[contains(@name, 'awb')]"
            ]
            
            for strategy in input_strategies:
                try:
                    input_el = wait.until(EC.presence_of_element_located((By.XPATH, strategy)))
                    if input_el and input_el.is_displayed():
                        print(f"Found AWB input directly using: {strategy}")
                        break
                except:
                    continue
            
            if not input_el:
                raise Exception("Could not find AWB input field")
        else:
            # Get the actual input element from container
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", container)
            container.click()
            time.sleep(0.3)
            
            input_el = WebDriverWait(driver, 3).until(
                lambda d: [
                    el for el in container.find_elements(By.TAG_NAME, "input")
                    if el.is_displayed() and el.is_enabled()
                ][0]
            )
        
        # Clear existing value safely (React-safe)
        driver.execute_script("""
            const input = arguments[0];
            input.focus();
            input.value = '';
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
        """, input_el)
        
        time.sleep(0.2)
        
        # Type the AWB value
        input_el.send_keys(awb_value)
        time.sleep(0.3)
        
        # Check if dropdown appears and handle it
        dropdown_selectors = [
            "//*[@id='creatable-select-menu-1']",
            "//ul[@role='listbox']",
            "//div[@role='listbox']",
            "//li[contains(@role, 'option')]"
        ]
        
        dropdown_detected = False
        for selector in dropdown_selectors:
            try:
                dropdown = driver.find_element(By.XPATH, selector)
                if dropdown.is_displayed():
                    print("Dropdown detected - selecting via ENTER")
                    input_el.send_keys(Keys.ENTER)
                    dropdown_detected = True
                    time.sleep(0.3)
                    break
            except:
                continue
        
        # Verify the entered value
        entered_value = input_el.get_attribute("value")
        
        if entered_value != awb_value:
            print(f"⚠️ Value mismatch. Expected: '{awb_value}', Got: '{entered_value}'")
            
            # Try alternative approach for text input
            if not dropdown_detected:
                print("Retrying as text input...")
                input_el.clear()
                time.sleep(0.1)
                input_el.send_keys(awb_value)
                time.sleep(0.2)
                
                # Try pressing Tab to commit the value
                input_el.send_keys(Keys.TAB)
                time.sleep(0.2)
                
                entered_value = input_el.get_attribute("value")
                if entered_value == awb_value:
                    print(f"✅ AWB entered successfully on retry: {awb_value}")
                else:
                    # Last resort: JavaScript to set value
                    print("Using JavaScript fallback...")
                    driver.execute_script("""
                        const input = arguments[0];
                        input.value = arguments[1];
                        input.dispatchEvent(new Event('input', { bubbles: true }));
                        input.dispatchEvent(new Event('change', { bubbles: true }));
                    """, input_el, awb_value)
                    time.sleep(0.2)
                    print(f"✅ AWB set via JavaScript: {awb_value}")
        else:
            print(f"✅ AWB entered successfully: {awb_value}")
        
        return True
        
    except Exception as e:
        print(f"❌ Failed to enter AWB: {e}")
        
        # Emergency fallback - try to find ANY visible input and fill it
        try:
            print("Attempting emergency fallback...")
            all_inputs = driver.find_elements(By.XPATH, "//input[@type='text' and not(@hidden)]")
            for inp in all_inputs:
                if inp.is_displayed() and inp.is_enabled():
                    placeholder = inp.get_attribute("placeholder") or ""
                    if "awb" in placeholder.lower() or "awb" in (inp.get_attribute("id") or "").lower():
                        inp.clear()
                        inp.send_keys(awb_value)
                        print(f"✅ Emergency fill successful on: {placeholder}")
                        return True
        except:
            pass
        
        return False
import json
import time
from pathlib import Path
from datetime import datetime
from utils import *

# Global results tracking
account_results = {}

def generate_summary_report(all_results):
    """Generate a summary report with folder names"""
    try:
        report_dir = Path("Reports")
        report_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = report_dir / f"summary_report_{timestamp}.txt"
        
        with open(report_file, "w", encoding="utf-8") as f:
            f.write("="*80 + "\n")
            f.write("AUTOMATION SUMMARY REPORT\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("="*80 + "\n\n")
            
            total_processed = 0
            total_successful = 0
            total_failed = 0
            total_already_raised = 0
            total_skipped = 0
            
            for account, results in all_results.items():
                f.write(f"\n{'='*80}\n")
                f.write(f"ACCOUNT: {account}\n")
                f.write(f"{'='*80}\n")
                f.write(f"Total Processed: {results['processed']}\n")
                f.write(f"✅ Successful: {results['successful']}\n")
                f.write(f"❌ Failed: {results['failed']}\n")
                f.write(f"⚠️  Already Raised: {results['already_raised']}\n")
                f.write(f"⏭️  Skipped: {results['skipped']}\n\n")
                
                # Write successful folders
                if results['successful_folders']:
                    f.write("✅ SUCCESSFUL FOLDERS (Moved to done folder):\n")
                    for folder in results['successful_folders']:
                        f.write(f"   - {folder}\n")
                    f.write("\n")
                
                # Write failed folders with errors (stay in pending)
                if results['failed_folders']:
                    f.write("❌ FAILED FOLDERS (Stay in pending - can retry):\n")
                    for folder, error in results['failed_folders']:
                        f.write(f"   - {folder} | Error: {error}\n")
                    f.write("\n")
                
                # Write already raised folders (moved to already_raised)
                if results['already_raised_folders']:
                    f.write("⚠️  ALREADY RAISED FOLDERS (Moved to already_raised folder):\n")
                    for folder in results['already_raised_folders']:
                        f.write(f"   - {folder}\n")
                    f.write("\n")
                
                # Write skipped folders (stay in pending)
                if results['skipped_folders']:
                    f.write("⏭️  SKIPPED FOLDERS (Stay in pending - can retry):\n")
                    for folder in results['skipped_folders']:
                        f.write(f"   - {folder}\n")
                    f.write("\n")
                
                total_processed += results['processed']
                total_successful += results['successful']
                total_failed += results['failed']
                total_already_raised += results['already_raised']
                total_skipped += results['skipped']
            
            f.write("\n" + "="*80 + "\n")
            f.write("TOTAL SUMMARY\n")
            f.write("="*80 + "\n")
            f.write(f"Total Processed: {total_processed}\n")
            f.write(f"✅ Total Successful: {total_successful}\n")
            f.write(f"❌ Total Failed: {total_failed}\n")
            f.write(f"⚠️  Total Already Raised: {total_already_raised}\n")
            f.write(f"⏭️  Total Skipped: {total_skipped}\n")
            if total_processed > 0:
                f.write(f"Success Rate: {(total_successful/total_processed*100):.1f}%\n")
        
        print(f"\n✅ Summary report generated: {report_file}")
        
        # Print summary to console
        print("\n" + "="*70)
        print("PROCESSING SUMMARY")
        print("="*70)
        print(f"Total Processed: {total_processed}")
        print(f"✅ Successful: {total_successful}")
        print(f"❌ Failed: {total_failed}")
        print(f"⚠️  Already Raised: {total_already_raised}")
        print(f"⏭️  Skipped: {total_skipped}")
        if total_processed > 0:
            print(f"Success Rate: {(total_successful/total_processed*100):.1f}%")
        print("="*70)
        
        return report_file
        
    except Exception as e:
        print(f"Failed to generate summary report: {e}")
        return None

def check_for_existing_ticket_error(driver, wait):
    """Check if there's an error message about ticket already being raised"""
    try:
        # Wait a moment for error messages to appear
        time.sleep(0.5)
        
        error_xpaths = [
            # From your image - specific helper text ID pattern
            "//*[contains(@id, 'helper-text') and contains(text(), 'has already been raised')]",
            "//*[@id='mui-4-helper-text' and contains(text(), 'already been raised')]",
            "//*[contains(@id, '-helper-text') and contains(text(), 'Ticket') and contains(text(), 'already been raised')]",
            
            # Generic patterns
            "//*[contains(text(), 'Ticket') and contains(text(), 'has already been raised')]",
            "//*[contains(text(), 'already been raised for this issue')]",
            "//*[contains(text(), 'Please reply on the same ticket')]",
            
            # MUI Alert patterns
            "//p[contains(@class, 'MuiFormHelperText-root')][contains(text(), 'already been raised')]",
            "//div[contains(@class, 'MuiAlert-message')][contains(text(), 'already been raised')]",
            
            # Direct text match
            "//*[contains(text(), 'has already been raised for this issue')]",
            "//*[contains(text(), 'Ticket')][contains(text(), 'already been raised')]"
        ]
        
        for xpath in error_xpaths:
            try:
                elements = driver.find_elements(By.XPATH, xpath)
                for element in elements:
                    if element.is_displayed():
                        error_text = element.text
                        print(f"❌ ERROR DETECTED: {error_text}")
                        return True
            except:
                continue
        
        # Also check for any element with helper-text class that contains ticket related text
        try:
            helper_texts = driver.find_elements(By.XPATH, "//p[contains(@class, 'MuiFormHelperText-root')]")
            for helper in helper_texts:
                text = helper.text
                if helper.is_displayed() and "ticket" in text.lower() and "already" in text.lower():
                    print(f"❌ ERROR DETECTED via helper text: {text}")
                    return True
        except:
            pass
        
        return False
        
    except Exception as e:
        print(f"Error checking for existing ticket: {e}")
        return False

def process_account(account_data, driver, wait):
    """Process all pending folders for a single account"""
    global current_account, processed_awbs_in_session, should_shutdown, account_results
    
    user_email = account_data["email"]
    user_password = account_data["password"]
    account_name = account_data["accountName"]
    state = account_data["state"]
    
    # Initialize results for this account
    account_results[account_name] = {
        "processed": 0,
        "successful": 0,
        "failed": 0,
        "already_raised": 0,
        "skipped": 0,
        "successful_folders": [],
        "failed_folders": [],
        "already_raised_folders": [],
        "skipped_folders": []
    }
    
    print(f"\n{'='*60}")
    print(f"STARTING PROCESS FOR ACCOUNT: {account_name}")
    print(f"{'='*60}")
    
    # Login to account
    if not login_to_account(user_email, user_password):
        print(f"Failed to login to account: {account_name}")
        account_results[account_name]["failed"] += 1
        account_results[account_name]["failed_folders"].append([f"LOGIN_FAILED_{account_name}", "Login failed"])
        return False
    
    # Extract account code
    print("Extracting account code from home page URL...")
    account_code = extract_account_code_from_home_url(driver)
    
    if not account_code:
        print("Failed to get account code. Using default 'lr4cm' as fallback.")
        account_code = "lr4cm"
    
    # Load previous session state
    previous_state = load_session_state(account_name)
    if previous_state and previous_state.get('processed_awbs'):
        processed_awbs_in_session = previous_state['processed_awbs']
        print(f"Resuming from previous session - already processed {len(processed_awbs_in_session)} folders")
    else:
        processed_awbs_in_session = []
    
    total_processed = 0
    
    while True:
        # Check for shutdown signal
        if should_shutdown:
            print("Shutdown signal received. Exiting processing loop...")
            break
        
        # Get next pending folder
        pending_data = get_next_pending_folder(account_name, processed_awbs_in_session)
        if not pending_data:
            print(f"No more pending folders to process for {account_name}.")
            break
        
        folder_name = pending_data['folder'].name
        
        print(f"\n{'='*60}")
        print(f"Processing: {folder_name}")
        print(f"AWB: {pending_data['awb']}")
        print(f"Packet ID: {pending_data['packet_id']}")
        print(f"{'='*60}")
        
        try:
            # Navigate to returns search using AWB
            returns_search_url = f"https://supplier.meesho.com/panel/v3/new/fulfillment/{account_code}/returns/search-returns?q={pending_data['awb']}"
            print(f"Navigating to: {returns_search_url}")
            
            driver.get(returns_search_url)
            time.sleep(2)
            
            # Check for table
            print("ULTRA-FAST checking for table (1 second max)...")
            
            no_results = check_if_no_results_message(driver, wait)
            if no_results:
                print("No results message found! Skipping this folder immediately...")
                processed_awbs_in_session.append(pending_data["awb"])
                finalize_current_task(account_name, pending_data, False)
                account_results[account_name]["skipped"] += 1
                account_results[account_name]["skipped_folders"].append(folder_name)
                
                if len(processed_awbs_in_session) % 5 == 0:
                    save_session_state(account_name, processed_awbs_in_session)
                continue
            
            table_exists = check_if_table_exists(driver, wait)
            
            if not table_exists:
                print("No table found in 1 second! Skipping this folder...")
                processed_awbs_in_session.append(pending_data["awb"])
                finalize_current_task(account_name, pending_data, False)
                account_results[account_name]["skipped"] += 1
                account_results[account_name]["skipped_folders"].append(folder_name)
                
                if len(processed_awbs_in_session) % 5 == 0:
                    save_session_state(account_name, processed_awbs_in_session)
                continue
            
            # Get suborder ID from table
            try:
                suborder_id = get_suborder_id_from_table(driver, wait)
                print(f"✅ Suborder ID from table: {suborder_id}")
                print(f"State from config: {state}")
            except Exception as e:
                print(f"❌ Error getting suborder ID from table: {e}")
                processed_awbs_in_session.append(pending_data["awb"])
                account_results[account_name]["failed"] += 1
                account_results[account_name]["failed_folders"].append([folder_name, f"Suborder ID error: {str(e)[:100]}"])
                continue
            
            # Open support page
            print("Opening support page...")
            issue_serial = get_issue_serial_from_folder(pending_data["folder"])
            
            support_url = (
                f"https://supplier.meesho.com/panel/v3/new/experience/"
                f"{account_code}/support/1/{issue_serial}/create"
            )
            print(f"Using dynamic support URL: {support_url}")
            
            driver.execute_script("window.open(arguments[0], '_blank');", support_url)
            driver.switch_to.window(driver.window_handles[-1])
            wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            time.sleep(5)
            
            # Fill form
            print("Starting to fill complete form...")
            
            # Step 1: Select State
            target_state = state.strip().capitalize()
            print(f"Step 1: Selecting state: {target_state}")
            select_meesho_dropdown(driver, wait, "State of the packet", target_state)
            time.sleep(1)
            
            # Step 2: Fill Sub Order Number
            print(f"Step 2: Filling sub order number: {suborder_id}")
            fill_mui_input_by_label(driver, wait, "Sub Order Number", suborder_id)
            time.sleep(0.5)
            
            # Step 3: Handle AWB Number (can be dropdown or text input)
            print(f"Step 3: Processing AWB number: {pending_data['awb']}")
            fill_awb_number(driver, wait, pending_data["awb"])
            
            # CHECK FOR ALREADY RAISED ERROR IMMEDIATELY AFTER AWB NUMBER
            print("Checking for 'already raised' error after AWB Number...")
            if check_for_existing_ticket_error(driver, wait):
                print("⚠️ Ticket already raised detected after AWB Number! Moving to already_raised folder...")
                
                if len(driver.window_handles) > 1:
                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])
                time.sleep(1)
                
                finalize_current_task_with_error(account_name, pending_data, "already_raised")
                processed_awbs_in_session.append(pending_data["awb"])
                account_results[account_name]["already_raised"] += 1
                account_results[account_name]["already_raised_folders"].append(folder_name)
                
                if len(processed_awbs_in_session) % 5 == 0:
                    save_session_state(account_name, processed_awbs_in_session)
                continue

            # Step 4: Fill Packet ID
            print(f"Step 4: Filling packet ID: {pending_data['packet_id']}")
            fill_mui_input_by_label(driver, wait, "Packet ID", pending_data["packet_id"])
            time.sleep(0.5)
            
            # CHECK FOR ALREADY RAISED ERROR AFTER PACKET ID (most common case)
            print("Checking for 'already raised' error after Packet ID...")
            if check_for_existing_ticket_error(driver, wait):
                print("⚠️ Ticket already raised detected after Packet ID! Moving to already_raised folder...")
                
                if len(driver.window_handles) > 1:
                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])
                time.sleep(1)
                
                finalize_current_task_with_error(account_name, pending_data, "already_raised")
                processed_awbs_in_session.append(pending_data["awb"])
                account_results[account_name]["already_raised"] += 1
                account_results[account_name]["already_raised_folders"].append(folder_name)
                
                if len(processed_awbs_in_session) % 5 == 0:
                    save_session_state(account_name, processed_awbs_in_session)
                continue

            # Step 5: Upload files
            print("Step 5: Uploading files...")
            try:
                reverse_waybill_img, product_img, unpacking_video = get_product_files(pending_data["folder"])
                
                print(f"Uploading unpacking video: {os.path.basename(unpacking_video)}")
                upload_by_input_id_prefix(driver, wait, "product_openingvideo_link_", unpacking_video, is_video=True)
                
                print(f"Uploading reverse waybill: {os.path.basename(reverse_waybill_img)}")
                upload_by_input_id_prefix(driver, wait, "product_reverse_way_bill_link_", reverse_waybill_img, is_video=False)
                
                print(f"Uploading product image: {os.path.basename(product_img)}")
                upload_by_input_id_prefix(driver, wait, "product_image_link_", product_img, is_video=False)
                
                print("All files uploaded successfully!")
                
            except Exception as e:
                print(f"Error uploading files: {e}")
            
            # Wait for video processing
            print("Waiting additional 8 seconds for video processing...")
            time.sleep(8)
            
            # Step 6: Fill Description
            print("Step 6: Filling description...")
            try:
                if issue_serial == 139:
                    description_text = "I have received wrong barcoded package in RTO"
                else:
                    description_text = "I have received wrong product"
                
                fill_description(driver, wait, description_text)
                
            except Exception as e:
                print(f"Error filling description: {e}")
            
            print("Form filled successfully.")
            
            # Submit and wait for confirmation
            submitted = wait_for_submit_and_click(driver, wait, timeout=15)
            
            # Finalize
            finalize_current_task(account_name, pending_data, submitted)
            
            if submitted:
                account_results[account_name]["successful"] += 1
                account_results[account_name]["successful_folders"].append(folder_name)
            else:
                account_results[account_name]["failed"] += 1
                account_results[account_name]["failed_folders"].append([folder_name, "Submission failed - no confirmation"])
            
            processed_awbs_in_session.append(pending_data["awb"])
            account_results[account_name]["processed"] += 1
            total_processed += 1
            
            # Close support tab
            if len(driver.window_handles) > 1:
                driver.close()
                driver.switch_to.window(driver.window_handles[0])
            
            time.sleep(1)
            print(f"Completed processing: {folder_name}")
            
            # Save session state periodically
            if total_processed % 5 == 0:
                save_session_state(account_name, processed_awbs_in_session)
            
        except Exception as e:
            error_msg = str(e)[:200]
            print(f"Error processing {folder_name}: {error_msg}")
            import traceback
            traceback.print_exc()
            
            processed_awbs_in_session.append(pending_data["awb"])
            account_results[account_name]["failed"] += 1
            account_results[account_name]["failed_folders"].append([folder_name, error_msg])
            
            try:
                if len(driver.window_handles) > 1:
                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])
            except:
                pass
            
            time.sleep(1)
            continue
    
    # Clear session state after successful completion
    clear_session_state(account_name)
    
    print(f"\n{'='*60}")
    print(f"PROCESSING COMPLETE FOR ACCOUNT: {account_name}")
    print(f"Total processed: {total_processed}")
    print(f"{'='*60}")
    
    return True

def wait_for_submit_and_click(driver, wait, timeout=15):
    """Wait for submit button to become enabled, click it, and confirm submission"""
    try:
        print(f"\n{'='*50}")
        print(f"Waiting for submit button to become enabled (max {timeout} seconds)...")
        print(f"{'='*50}")
        
        start_time = time.time()
        last_status_time = 0
        
        while time.time() - start_time < timeout:
            try:
                submit_btn = driver.find_element(By.XPATH, "//button[.//span[normalize-space()='Submit']]")
                
                btn_class = submit_btn.get_attribute("class") or ""
                is_disabled = "Mui-disabled" in btn_class
                
                if not is_disabled:
                    print(f"\n✅ Submit button is now enabled! (Waited {int(time.time() - start_time)} seconds)")
                    
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", submit_btn)
                    time.sleep(0.5)
                    driver.execute_script("arguments[0].click();", submit_btn)
                    print("Submit button clicked successfully.")
                    
                    print("Waiting for confirmation page...")
                    time.sleep(5)
                    
                    try:
                        print("Looking for confirmation button...")
                        confirmation_btn = WebDriverWait(driver, 30).until(
                            EC.presence_of_element_located((By.XPATH, "//*[@id='mainWrapper']/div/div/div[2]/div/button[1]"))
                        )
                        print("✅ Confirmation page detected! Ticket successfully submitted!")
                        
                        try:
                            driver.execute_script("arguments[0].click();", confirmation_btn)
                            print("Clicked on confirmation button")
                            time.sleep(2)
                        except Exception as e:
                            print(f"Could not click confirmation button: {e}")
                        
                        return True
                        
                    except TimeoutException:
                        print("Confirmation button not found, checking alternatives...")
                        
                        alternative_xpaths = [
                            "//button[contains(text(), 'Create Another')]",
                            "//button[contains(text(), 'Back to Home')]",
                            "//button[contains(text(), 'Done')]",
                            "//*[contains(text(), 'ticket has been raised')]",
                            "//*[contains(text(), 'successfully')]",
                            "//*[contains(text(), 'Ticket ID')]"
                        ]
                        
                        for xpath in alternative_xpaths:
                            try:
                                element = WebDriverWait(driver, 3).until(
                                    EC.presence_of_element_located((By.XPATH, xpath))
                                )
                                if element.is_displayed():
                                    print(f"✅ Confirmation detected via: {xpath}")
                                    
                                    if "button" in xpath:
                                        try:
                                            driver.execute_script("arguments[0].click();", element)
                                            print("Clicked on confirmation button")
                                        except:
                                            pass
                                    
                                    return True
                            except:
                                continue
                        
                        print("❌ No confirmation detected after submit")
                        return False
                
                current_time = int(time.time() - start_time)
                if current_time - last_status_time >= 10:
                    print(f"⏳ Still waiting for upload to complete... ({current_time}s elapsed)")
                    last_status_time = current_time
                    
            except Exception as e:
                pass
            
            time.sleep(2)
        
        print(f"\n❌ Submit button did not become enabled within {timeout} seconds")
        return False
        
    except Exception as e:
        print(f"Error in wait_for_submit_and_click: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main execution function"""
    # Register signal handlers for graceful shutdown
    register_signal_handlers()
    
    print("="*70)
    print("AUTOMATION SCRIPT STARTED")
    print("="*70)
    
    # Load accounts
    try:
        with open("details.json", "r") as f:
            all_accounts = json.load(f)
        print(f"Loaded {len(all_accounts)} accounts from details.json")
    except FileNotFoundError:
        print("details.json file not found!")
        return
    except json.JSONDecodeError as e:
        print(f"Invalid JSON in details.json: {e}")
        return
    
    # Setup driver
    driver, wait = setup_driver()
    
    start_time = time.time()
    
    try:
        for i, account_data in enumerate(all_accounts, 1):
            # Check for shutdown signal
            if should_shutdown:
                print("Shutdown signal received. Stopping...")
                break
            
            print(f"\n{'#'*70}")
            print(f"ACCOUNT {i}/{len(all_accounts)}")
            print(f"{'#'*70}")
            
            # Set current account for graceful shutdown
            global current_account
            current_account = account_data['accountName']
            
            success = process_account(account_data, driver, wait)
            
            if success:
                if i < len(all_accounts):
                    logout_from_account(driver, wait)
                    time.sleep(2)
            else:
                print(f"Failed to process account: {account_data['accountName']}")
                try:
                    logout_from_account(driver, wait)
                except:
                    pass
            
            time.sleep(2)
        
    except KeyboardInterrupt:
        print("\n⚠️ Keyboard interrupt received")
    except Exception as e:
        print(f"Unexpected error in main: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Generate summary report
        elapsed_time = time.time() - start_time
        hours = int(elapsed_time // 3600)
        minutes = int((elapsed_time % 3600) // 60)
        seconds = int(elapsed_time % 60)
        
        print(f"\n{'='*70}")
        print(f"Total execution time: {hours}h {minutes}m {seconds}s")
        print(f"{'='*70}")
        
        generate_summary_report(account_results)
        
        # Quit driver
        quit_driver()
        
        print("="*70)
        print("AUTOMATION SCRIPT COMPLETED")
        print("="*70)

if __name__ == "__main__":
    main()
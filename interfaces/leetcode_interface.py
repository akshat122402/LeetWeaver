import os
import re
import time
import logging
import undetected_chromedriver as uc
from typing import Optional, Dict, Any, Tuple

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    ElementClickInterceptedException,
    WebDriverException
)
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Constants
LEETCODE_LOGIN_URL = "https://leetcode.com/accounts/login/"
LEETCODE_PROBLEMSET_URL = "https://leetcode.com/problemset/" # Base problems URL
DEFAULT_WAIT_TIME = 40 # Increased default wait time from 20 to 40
SHORT_WAIT_TIME = 10 # Increased short wait time slightly too
SELENIUM_RETRY_ATTEMPTS = 3
RETRY_DELAY = 5 # Seconds


class LeetCodeInterface:
    """
    Handles interaction with the LeetCode website using Selenium.
    Responsible for login, navigation, fetching problem details,
    and submitting solutions.
    """
    def __init__(self, headless: bool = False):
        logger.info("Initializing LeetCodeInterface...")
        self.username = os.getenv("LEETCODE_USERNAME")
        self.password = os.getenv("LEETCODE_PASSWORD")
        if not self.username or not self.password:
            logger.warning("LeetCode username or password not found in .env. Manual login might be required.")
            # raise ValueError("LEETCODE_USERNAME and LEETCODE_PASSWORD must be set in .env")

        options = uc.ChromeOptions()
        if headless:
             options.add_argument('--headless')
             options.add_argument('--disable-gpu') # Often needed for headless
             options.add_argument('--no-sandbox') # May be needed in some environments
             options.add_argument('--disable-dev-shm-usage') # Overcome limited resource problems

        # Try to initialize undetected_chromedriver
        try:
            self.driver = uc.Chrome(options=options, use_subprocess=True)
            self.wait = WebDriverWait(self.driver, DEFAULT_WAIT_TIME)
            logger.info("WebDriver initialized successfully.")
        except WebDriverException as e:
             logger.error(f"Failed to initialize WebDriver: {e}", exc_info=True)
             logger.error("Please ensure ChromeDriver is installed and compatible with your Chrome version.")
             logger.error("You might need to download ChromeDriver from: https://chromedriver.chromium.org/downloads")
             raise ConnectionError("Failed to initialize WebDriver.") from e


    def _find_element(self, by, value, wait_time=DEFAULT_WAIT_TIME):
        """Safely finds an element with explicit wait."""
        try:
            wait = self.wait if wait_time == DEFAULT_WAIT_TIME else WebDriverWait(self.driver, wait_time)
            element = wait.until(EC.presence_of_element_located((by, value)))
            # logger.debug(f"Element found by {by}: {value}")
            return element
        except TimeoutException:
            logger.warning(f"Timeout waiting for element by {by}: {value}")
            return None
        except Exception as e:
            logger.error(f"Error finding element by {by}: {value} - {e}", exc_info=True)
            return None

    def _click_element(self, by, value, wait_time=DEFAULT_WAIT_TIME):
        """Safely clicks an element with explicit wait and retry."""
        for attempt in range(SELENIUM_RETRY_ATTEMPTS):
            try:
                wait = self.wait if wait_time == DEFAULT_WAIT_TIME else WebDriverWait(self.driver, wait_time)
                element = wait.until(EC.element_to_be_clickable((by, value)))
                element.click()
                # logger.debug(f"Clicked element by {by}: {value}")
                return True
            except (TimeoutException, ElementClickInterceptedException, NoSuchElementException) as e:
                logger.warning(f"Attempt {attempt + 1} failed to click element by {by}: {value} - {type(e).__name__}")
                if attempt < SELENIUM_RETRY_ATTEMPTS - 1:
                    time.sleep(RETRY_DELAY)
                else:
                    logger.error(f"Failed to click element by {by}: {value} after {SELENIUM_RETRY_ATTEMPTS} attempts.", exc_info=True)
                    return False
            except Exception as e:
                 logger.error(f"Unexpected error clicking element by {by}: {value} - {e}", exc_info=True)
                 return False


    def _input_text(self, by, value, text, wait_time=DEFAULT_WAIT_TIME):
        """Safely inputs text into an element."""
        element = self._find_element(by, value, wait_time)
        if element:
            try:
                element.clear()
                element.send_keys(text)
                # logger.debug(f"Input text into element by {by}: {value}")
                return True
            except Exception as e:
                logger.error(f"Error inputting text into element by {by}: {value} - {e}", exc_info=True)
                return False
        return False

    def navigate_to(self, url: str):
        """Navigates the WebDriver to the specified URL."""
        logger.info(f"Navigating to {url}...")
        try:
            self.driver.get(url)
            logger.info(f"Navigation to {url} complete.")
            return True
        except WebDriverException as e:
            logger.error(f"Failed to navigate to {url}: {e}", exc_info=True)
            return False

    def login(self):
        """Logs into LeetCode using GitHub credentials from .env."""
        if not self.username or not self.password:
             logger.error("Cannot attempt login: LeetCode credentials not provided.")
             return False

        logger.info("Attempting LeetCode login via GitHub...")
        if not self.navigate_to(LEETCODE_LOGIN_URL):
            return False

        # Wait for potential initial loading overlay
        try:
            WebDriverWait(self.driver, SHORT_WAIT_TIME).until(
                EC.invisibility_of_element_located((By.ID, "initial-loading"))
            )
        except TimeoutException:
            logger.debug("Initial loading overlay not found or did not disappear quickly.")

        # Click GitHub login button
        if not self._click_element(By.CSS_SELECTOR, 'a[href*="github/login"]'):
             logger.error("Could not find or click the GitHub login button.")
             # Fallback: Try finding by icon class if selector fails
             if not self._click_element(By.CSS_SELECTOR, 'svg.text-label-2'):
                 logger.error("Could not find GitHub login button by icon either.")
                 self.manual_login_prompt()
                 return self.is_logged_in() # Check status after manual prompt
             else:
                 logger.info("Clicked GitHub login button via icon selector.")


        # --- GitHub Interaction ---
        # Wait for GitHub login page (username field)
        logger.info("Waiting for GitHub login page...")
        if not self._find_element(By.ID, "login_field"):
             logger.warning("Did not find GitHub username field. Already logged into GitHub? Or page changed?")
             # If already logged into GitHub, it might skip straight to authorization
             # Check if we are back on LeetCode or on an authorize page
             current_url = self.driver.current_url
             if "github.com/login/oauth/authorize" in current_url:
                 logger.info("Detected GitHub authorization page.")
                 # Try to find and click the "Authorize" or "Continue" button
                 authorize_button_xpath = "//button[contains(normalize-space(), 'Authorize') or contains(normalize-space(), 'Continue')]"
                 if self._click_element(By.XPATH, authorize_button_xpath):
                     logger.info("Clicked GitHub authorize/continue button.")
                 else:
                     logger.error("Could not find or click GitHub authorize/continue button.")
                     self.manual_login_prompt("GitHub authorization")
                     return self.is_logged_in()
             elif "leetcode.com" in current_url:
                 logger.info("Redirected back to LeetCode, likely already logged into GitHub.")
                 # Proceed assuming login will complete
             else:
                 logger.error("Unexpected URL after clicking GitHub login.")
                 self.manual_login_prompt("GitHub login process")
                 return self.is_logged_in()

        else:
             # Found GitHub login fields, proceed with entering credentials
             logger.info("Entering GitHub credentials...")
             if not self._input_text(By.ID, "login_field", self.username): return False
             if not self._input_text(By.ID, "password", self.password): return False
             if not self._click_element(By.CSS_SELECTOR, 'input[type="submit"][value="Sign in"]'):
                 logger.error("Could not click GitHub Sign in button.")
                 self.manual_login_prompt("GitHub sign in")
                 return self.is_logged_in()

        # --- Wait for Redirect and Final Login Check ---
        logger.info("Waiting for redirect back to LeetCode after GitHub interaction...")
        try:
            self.wait.until(EC.url_contains("leetcode.com"))
            logger.info("Successfully redirected back to LeetCode.")
            # Add a small delay for page elements to settle after redirect
            time.sleep(SHORT_WAIT_TIME)

            # Final check to ensure login was successful
            if self.is_logged_in():
                logger.info("LeetCode login successful.")
                return True
            else:
                logger.error("Login failed. Ended up on LeetCode but couldn't confirm logged-in state.")
                self.manual_login_prompt("final login check")
                return self.is_logged_in() # Check again after prompt

        except TimeoutException:
            logger.error("Timeout waiting for redirect back to LeetCode.")
            current_url = self.driver.current_url
            logger.error(f"Current URL is: {current_url}")
            if "github.com" in current_url:
                 logger.error("Stuck on GitHub page (check for 2FA, CAPTCHA, or other issues).")
                 self.manual_login_prompt("GitHub 2FA/CAPTCHA")
                 return self.is_logged_in() # Check again after prompt
            else:
                 self.manual_login_prompt("redirect timeout")
                 return self.is_logged_in() # Check again after prompt
        except Exception as e:
             logger.error(f"An unexpected error occurred during login: {e}", exc_info=True)
             self.manual_login_prompt("unexpected error")
             return self.is_logged_in()


    def manual_login_prompt(self, context="login"):
        """Prompts the user to log in manually if automatic login fails."""
        logger.warning(f"Automatic login failed during: {context}.")
        print("\n--- MANUAL LOGIN REQUIRED ---")
        print(f"Could not automatically log in at the '{context}' step.")
        print(f"Current browser URL: {self.driver.current_url}")
        print("Please complete the login process manually in the browser window.")
        input("Press Enter here after you have successfully logged in...")
        logger.info("Continuing after manual login prompt.")

    def is_logged_in(self) -> bool:
        """Checks if the user appears to be logged in."""
        # Check for profile picture/avatar element, common indicator of login
        # Adjust selector if LeetCode changes layout
        profile_element = self._find_element(By.CSS_SELECTOR, 'img.h-6.w-6.cursor-pointer.rounded-full', wait_time=SHORT_WAIT_TIME)
        if profile_element:
            logger.info("Login check: Found profile element, assuming logged in.")
            return True

        # Fallback check: presence of logout button in dropdown (might require clicking profile first)
        # This is more complex and less reliable, use profile element if possible.

        # Fallback check 2: Navigate to base URL and check URL doesn't redirect to login
        logger.info("Login check: Profile element not found, checking URL.")
        self.navigate_to("https://leetcode.com/")
        time.sleep(2) # Allow potential redirect
        current_url = self.driver.current_url
        if "login" in current_url or "accounts" in current_url:
             logger.warning("Login check: Redirected to login page, assuming not logged in.")
             return False
        else:
             logger.info("Login check: Not redirected to login page, assuming logged in.")
             return True


    def get_problem_details(self, problem_url: str) -> Optional[Dict[str, str]]:
        """Navigates to a problem URL and extracts description and starting code."""
        if not self.navigate_to(problem_url):
            return None

        logger.info(f"Fetching details for problem: {problem_url}")
        details = {}

        # --- Get Problem Description ---
        try:
            description_element = self._find_element(By.CSS_SELECTOR, 'div[data-track-load="description_content"]')
            if description_element:
                html_content = description_element.get_attribute('innerHTML')
                soup = BeautifulSoup(html_content, 'html.parser')

                # Simple text extraction (can be improved like in original Solver.py)
                # For now, focusing on basic text content.
                # Consider re-implementing the detailed parsing from Solver.py if needed.
                raw_text = soup.get_text(separator='\n', strip=True)
                details['description'] = re.sub(r'\n\s*\n', '\n\n', raw_text).strip() # Clean up newlines
                logger.info("Successfully extracted problem description.")
                # logger.debug(f"Description:\n{details['description'][:200]}...") # Log snippet
            else:
                logger.warning("Could not find description element.")
                details['description'] = ""
        except Exception as e:
            logger.error(f"Error getting problem description: {e}", exc_info=True)
            details['description'] = ""


        # --- Get Starting Code ---
        try:
            # Ensure Python is selected (implement if necessary, similar to Solver.py's ensure_python_language)
            # self.ensure_python_language() # Add this call if language selection is needed

            # Wait for the Monaco editor lines to be present
            code_editor_lines = WebDriverWait(self.driver, DEFAULT_WAIT_TIME).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, '.view-line'))
            )
            if code_editor_lines:
                 # Give editor a moment to fully render text
                 time.sleep(1)
                 # Re-fetch elements to get updated text content
                 code_lines_text = [line.text for line in self.driver.find_elements(By.CSS_SELECTOR, '.view-line') if line.text]
                 details['starting_code'] = '\n'.join(code_lines_text) # <-- Already storing it
                 logger.info("Successfully extracted starting code.")
                 # logger.debug(f"Starting Code:\n{details['starting_code']}")
            else:
                 logger.warning("Could not find code editor lines.")
                 details['starting_code'] = ""

        except TimeoutException:
             logger.error("Timeout waiting for code editor to load.")
             details['starting_code'] = ""
        except Exception as e:
            logger.error(f"Error getting starting code: {e}", exc_info=True)
            details['starting_code'] = ""

        if not details.get('description') and not details.get('starting_code'):
             logger.error("Failed to retrieve both description and starting code.")
             return None

        return details


    def input_code_to_editor(self, code: str) -> bool:
        """Inputs the given code into the LeetCode Monaco editor."""
        logger.info("Inputting code into editor...")
        try:
            # First ensure Python is selected
            if not self.ensure_python_language():
                logger.error("Failed to ensure Python language before code input.")
                return False

            # Rest of the existing input_code_to_editor implementation...
            self._find_element(By.CSS_SELECTOR, '.monaco-editor textarea')
            
            escaped_code = code.replace('\\', '\\\\').replace('`', '\\`').replace('$', '\\$')
            
            js_set_editor_value = f"""
            try {{
                var editor = monaco.editor.getEditors()[0];
                if (editor) {{
                    editor.setValue(`{escaped_code}`);
                    return true;
                }} else {{
                    console.error('Monaco editor instance not found.');
                    return false;
                }}
            }} catch (e) {{
                console.error('Error setting editor value:', e);
                return false;
            }}
            """
            result = self.driver.execute_script(js_set_editor_value)
            if result:
                logger.info("Code input successful via JavaScript.")
                return True
            else:
                logger.error("JavaScript execution failed to set editor value.")
                return False

        except Exception as e:
            logger.error(f"Error inputting code into editor: {e}", exc_info=True)
            return False

    def run_example_tests(self) -> bool:
        """Clicks the 'Run' button to execute code against example tests."""
        logger.info("Clicking 'Run' button for example tests...")
        # Use the specific locator from Solver.py
        if self._click_element(By.CSS_SELECTOR, 'button[data-e2e-locator="console-run-button"]'):
            logger.info("Clicked 'Run' button successfully.")
            return True
        else:
            logger.error("Failed to click 'Run' button.")
            # Consider adding fallback (e.g., keyboard shortcut) if needed
            return False

    def get_run_results(self) -> Optional[Dict[str, Any]]:
        """
        Waits for and parses the results after clicking 'Run'.
        Handles Accepted, Runtime Error, Compile Error, Wrong Answer etc.
        Returns a dictionary with results or None on timeout/error.
        """
        logger.info("Waiting for example test run results...")
        result_data = {"status": "Unknown", "details": None, "raw_text": ""}

        try:
            # Wait for a container that holds the result status message
            # Adjust selectors based on LeetCode's current structure
            result_indicator = WebDriverWait(self.driver, DEFAULT_WAIT_TIME * 2).until(
                EC.presence_of_element_located((
                    By.XPATH,
                    "//div[contains(@class, 'text-green-s') or contains(@class, 'text-red-s') or contains(@class, 'text-error') or contains(@class, 'text-red-s dark:text-dark-red-s')]" # Covers Accepted, Wrong Answer, Runtime Error, Compile Error
                    # Add more specific selectors if needed
                ))
            )
            raw_text = result_indicator.text
            result_data["raw_text"] = raw_text
            logger.info(f"Raw result indicator text: {raw_text}")

            # Determine status based on text content or class
            if "Accepted" in raw_text:
                result_data["status"] = "Accepted"
            elif "Wrong Answer" in raw_text:
                result_data["status"] = "Wrong Answer"
            elif "Runtime Error" in raw_text:
                result_data["status"] = "Runtime Error"
            elif "Compile Error" in raw_text:
                 result_data["status"] = "Compile Error"
            # Add Time Limit Exceeded, Memory Limit Exceeded if necessary

            # --- Extract Details (Input, Output, Expected) ---
            # This part is complex as structure varies based on result type
            # Using a simplified approach here; needs refinement like in Solver.py
            details = {}
            try:
                # Try finding common panels for input/output/expected
                # These selectors might need frequent updates
                input_el = self._find_element(By.XPATH, "//div[text()='Input']/following-sibling::div//pre", wait_time=SHORT_WAIT_TIME)
                output_el = self._find_element(By.XPATH, "//div[text()='Output']/following-sibling::div//pre", wait_time=SHORT_WAIT_TIME)
                expected_el = self._find_element(By.XPATH, "//div[text()='Expected']/following-sibling::div//pre", wait_time=SHORT_WAIT_TIME)
                stderr_el = self._find_element(By.XPATH, "//div[text()='Stderr']/following-sibling::div//pre", wait_time=SHORT_WAIT_TIME) # For runtime/compile errors

                if input_el: details["input"] = input_el.text
                if output_el: details["output"] = output_el.text
                if expected_el: details["expected"] = expected_el.text
                if stderr_el: details["stderr"] = stderr_el.text

                # If stderr has content, often that's the primary error message
                if details.get("stderr"):
                     details["error_message"] = details["stderr"]
                elif result_data["status"] in ["Runtime Error", "Compile Error"]:
                     # Try finding the main error message panel if stderr wasn't specific
                     error_panel = self._find_element(By.CSS_SELECTOR, "div.error-message-panel-selector", wait_time=SHORT_WAIT_TIME) # Replace with actual selector
                     if error_panel:
                         details["error_message"] = error_panel.text
                     else: # Fallback to raw text if specific panel not found
                         details["error_message"] = raw_text

                result_data["details"] = details if details else raw_text # Store details or raw text if parsing failed

            except Exception as parse_error:
                logger.warning(f"Could not parse detailed run results: {parse_error}. Storing raw text.")
                result_data["details"] = raw_text

            logger.info(f"Run results obtained: Status='{result_data['status']}'")
            return result_data

        except TimeoutException:
            logger.error("Timeout waiting for run results to appear.")
            return None
        except Exception as e:
            logger.error(f"Error getting run results: {e}", exc_info=True)
            return None


    def submit_solution(self) -> bool:
        """Clicks the 'Submit' button."""
        logger.info("Clicking 'Submit' button...")
        # Use the specific locator from Solver.py
        if self._click_element(By.CSS_SELECTOR, 'button[data-e2e-locator="console-submit-button"]'):
            logger.info("Clicked 'Submit' button successfully.")
            # It's good practice to wait briefly for submission process to start
            time.sleep(SHORT_WAIT_TIME)
            return True
        else:
            logger.error("Failed to click 'Submit' button.")
            return False

    def get_submission_status(self) -> Optional[Dict[str, Any]]:
        """
        Waits for and parses the final submission status (Accepted, Wrong Answer, TLE, etc.).
        Returns a dictionary with status, runtime, memory, etc., or None on timeout/error.
        """
        logger.info("Waiting for final submission status...")
        submission_result = {"status": "Unknown", "details": None}
        # Increased wait time significantly for submission results
        submission_wait_time = DEFAULT_WAIT_TIME * 5 # e.g., 200 seconds

        # --- Wait for the status message itself ---
        # This is often the most reliable indicator that results are ready.
        # Selectors need verification against the live LeetCode page.
        # This XPath tries to find common status texts within elements that might indicate the result.
        status_xpath = (
            "//div[contains(@class, 'text-xl') and ("
            "contains(., 'Accepted') or "
            "contains(., 'Wrong Answer') or "
            "contains(., 'Time Limit Exceeded') or "
            "contains(., 'Runtime Error') or "
            "contains(., 'Compile Error') or "
            "contains(., 'Memory Limit Exceeded')"
            ")] | " # Added pipe for OR condition in XPath
            "//span[contains(@class, 'text-red') and contains(., 'Runtime Error')] | " # Alternative for runtime error
            "//span[contains(@class, 'text-red') and contains(., 'Compile Error')] | " # Alternative for compile error
            "//span[contains(@class, 'text-green') and contains(., 'Accepted')]" # Alternative for accepted
        )
        # These selectors are common patterns but might need adjustment
        runtime_xpath = "//div[text()='Runtime']/following-sibling::div/span[@class='font-semibold'] | //span[contains(text(), 'Runtime')]/following-sibling::span"
        memory_xpath = "//div[text()='Memory']/following-sibling::div/span[@class='font-semibold'] | //span[contains(text(), 'Memory')]/following-sibling::span"
        # Selector for detailed error messages (e.g., Wrong Answer details)
        error_detail_selector = "div.flex.flex-col.gap-4 > div.flex.flex-col.gap-2" # Example selector, needs verification

        try:
            logger.info(f"Waiting up to {submission_wait_time} seconds for submission status element...")
            status_element = WebDriverWait(self.driver, submission_wait_time).until(
                EC.presence_of_element_located((By.XPATH, status_xpath))
            )
            logger.info("Submission status element found.")

            # Extract Status
            status_text = status_element.text.strip()
            # Normalize status text (e.g., handle cases like "Accepted\nRuntime: 10 ms")
            if "Accepted" in status_text:
                submission_result["status"] = "Accepted"
            elif "Wrong Answer" in status_text:
                submission_result["status"] = "Wrong Answer"
            elif "Time Limit Exceeded" in status_text:
                submission_result["status"] = "Time Limit Exceeded"
            elif "Runtime Error" in status_text:
                submission_result["status"] = "Runtime Error"
            elif "Compile Error" in status_text:
                submission_result["status"] = "Compile Error"
            elif "Memory Limit Exceeded" in status_text:
                submission_result["status"] = "Memory Limit Exceeded"
            else:
                 # Fallback if specific text not found but element was located
                 submission_result["status"] = status_text if status_text else "Unknown Status"

            logger.info(f"Submission Status: {submission_result['status']}")

            # Extract Runtime and Memory if status is Accepted
            if submission_result["status"] == "Accepted":
                try:
                    runtime_element = self._find_element(By.XPATH, runtime_xpath, wait_time=SHORT_WAIT_TIME)
                    if runtime_element:
                        submission_result["runtime"] = runtime_element.text.strip()
                        logger.info(f"Runtime: {submission_result['runtime']}")
                    else:
                        logger.warning("Could not find runtime element.")
                except Exception as e:
                    logger.warning(f"Error extracting runtime: {e}")

                try:
                    memory_element = self._find_element(By.XPATH, memory_xpath, wait_time=SHORT_WAIT_TIME)
                    if memory_element:
                        submission_result["memory"] = memory_element.text.strip()
                        logger.info(f"Memory: {submission_result['memory']}")
                    else:
                        logger.warning("Could not find memory element.")
                except Exception as e:
                    logger.warning(f"Error extracting memory: {e}")

            # Extract error details if not accepted (similar logic to get_run_results)
            elif submission_result["status"] != "Unknown Status":
                 try:
                     # Try finding the detailed error panel
                     error_panel = self._find_element(By.CSS_SELECTOR, error_detail_selector, wait_time=SHORT_WAIT_TIME)
                     if error_panel:
                         # Extract input, output, expected, stderr etc. from within the panel
                         # This part needs specific selectors based on the error type panel structure
                         details = {}
                         # Example: Find input/output/expected within the error panel
                         input_el = self._find_element_from_parent(error_panel, By.XPATH, ".//div[text()='Input']/following-sibling::div//pre")
                         output_el = self._find_element_from_parent(error_panel, By.XPATH, ".//div[text()='Output']/following-sibling::div//pre")
                         expected_el = self._find_element_from_parent(error_panel, By.XPATH, ".//div[text()='Expected']/following-sibling::div//pre")
                         stderr_el = self._find_element_from_parent(error_panel, By.XPATH, ".//div[text()='Stderr']/following-sibling::div//pre")

                         if input_el: details["input"] = input_el.text
                         if output_el: details["output"] = output_el.text
                         if expected_el: details["expected"] = expected_el.text
                         if stderr_el: details["stderr"] = stderr_el.text
                         if details:
                             submission_result["details"] = details
                             logger.info(f"Extracted error details: {details}")
                         else:
                             submission_result["details"] = error_panel.text # Fallback to raw panel text
                             logger.info("Extracted raw error panel text.")
                     else:
                         logger.warning("Could not find detailed error panel. Storing status text as details.")
                         submission_result["details"] = status_text # Use the status text if no better details found
                 except Exception as e:
                     logger.warning(f"Error extracting error details: {e}. Storing status text.")
                     submission_result["details"] = status_text

            return submission_result

        except TimeoutException:
            logger.error(f"Timeout ({submission_wait_time}s) waiting for submission status element ({status_xpath}).")
            # Check if still on the same page or navigated away unexpectedly
            current_url = self.driver.current_url
            logger.error(f"Current URL is: {current_url}")
            if "submissions" in current_url:
                 logger.warning("Navigated to submissions page, result might be there but specific status element not found by XPath.")
                 # Could add logic here to parse the submissions page if needed
            return None
        except Exception as e:
            logger.error(f"Error getting submission status: {e}", exc_info=True)
            return None

    # Helper function to find element relative to a parent
    def _find_element_from_parent(self, parent_element, by, value, wait_time=SHORT_WAIT_TIME):
        """Safely finds an element relative to a parent element."""
        try:
            # Use a short wait relative to the parent being present
            return WebDriverWait(parent_element, wait_time).until(
                EC.presence_of_element_located((by, value))
            )
        except TimeoutException:
            # logger.debug(f"Timeout waiting for child element by {by}: {value} within parent.")
            return None
        except Exception as e:
            logger.error(f"Error finding child element by {by}: {value} - {e}", exc_info=True)
            return None

    def close(self):
        """Closes the WebDriver."""
        if self.driver:
            logger.info("Closing WebDriver.")
            try:
                self.driver.quit()
            except Exception as e:
                logger.error(f"Error closing WebDriver: {e}", exc_info=True)
            self.driver = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def ensure_python_language(self) -> bool:
        """Checks if Python is selected in the editor, selects it if not."""
        logger.info("Ensuring Python language is selected...")
        try:
            # Wait for and find the language selector button
            lang_select = self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button.text-sm.font-normal.group")))
            
            # Check if Python is already selected
            if "python" in lang_select.text.lower():
                logger.info("Python is already selected.")
                return True

            logger.info("Clicking language selector...")
            lang_select.click()  # Click to open dropdown
            time.sleep(1)  # Wait for dropdown animation

            logger.info("Selecting Python from dropdown...")
            python_option = self.wait.until(EC.element_to_be_clickable(
                (By.XPATH, "//div[contains(@class, 'text-text-primary') and text()='Python3']")
            ))
            python_option.click()  # Select Python
            
            # Verify the selection took effect
            time.sleep(1)  # Wait for selection to apply
            updated_lang = self.wait.until(EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "button.text-sm.font-normal.group")
            ))
            if "python" in updated_lang.text.lower():
                logger.info("Successfully set language to Python.")
                return True
            else:
                logger.warning("Language selection may not have taken effect.")
                return False

        except (TimeoutException, NoSuchElementException) as e:
            logger.error(f"Error setting language to Python: {str(e)}")
            return False


# Example Usage (for testing the interface directly)
if __name__ == "__main__":
    # Example: Login and fetch details for "Two Sum"
    PROBLEM_URL = "https://leetcode.com/problems/two-sum/"
    # Make sure .env file has credentials

    # Use headless=False to see the browser interaction
    with LeetCodeInterface(headless=False) as interface:
        if interface.login():
            print("\nLogin seemed successful.")
            details = interface.get_problem_details(PROBLEM_URL)
            if details:
                print(f"\n--- Problem Details for {PROBLEM_URL} ---")
                print("\nDescription (first 300 chars):")
                print(details.get('description', 'N/A')[:300] + "...")
                print("\nStarting Code:")
                fetched_starting_code = details.get('starting_code')
                print(fetched_starting_code if fetched_starting_code else 'N/A')

                # --- Example: Input code, run, get results ---
                # Use the fetched starting code if available
                if fetched_starting_code:
                    print("\nUsing fetched starting code template.")
                    code_to_input = fetched_starting_code
                    # Optional: Add a basic implementation within the template for testing run/submit
                    # This is still a placeholder, but uses the correct structure
                    if "class Solution:" in code_to_input and "def " in code_to_input:
                         # Very basic placeholder logic - might need adjustment based on problem
                         placeholder_logic = "        # Placeholder implementation\n        return []"
                         # Find the first function definition to insert the placeholder
                         match = re.search(r"(def\s+\w+\(self,[^)]*\):\s*\n)", code_to_input)
                         if match:
                             insert_point = match.end()
                             code_to_input = code_to_input[:insert_point] + placeholder_logic + code_to_input[insert_point:]
                             print("\nAdded placeholder logic to starting code for testing.")
                         else:
                             print("\nWarning: Could not automatically add placeholder logic to starting code.")
                    else:
                         print("\nWarning: Fetched code doesn't look like a standard LeetCode Python template.")

                else:
                    print("\nWarning: Failed to fetch starting code. Using a generic placeholder.")
                    # Fallback placeholder if fetching failed
                    code_to_input = """
class Solution:
    def solve(self, input_data):
        # Fallback placeholder
        return None
"""

                if interface.input_code_to_editor(code_to_input):
                     print(f"\nInputting code into editor:\n---\n{code_to_input}\n---")
                     if interface.run_example_tests():
                         print("Running example tests...")
                         run_results = interface.get_run_results()
                         if run_results:
                             print("\n--- Run Results ---")
                             import json
                             print(json.dumps(run_results, indent=2))
                         else:
                             print("\nFailed to get run results.")

                         # --- Example: Submit ---
                         # Be cautious submitting incorrect code frequently
                         # print("\nAttempting submission (commented out by default)...")
                         # if interface.submit_solution():
                         #     print("\nSubmitting solution...")
                         #     submission_status = interface.get_submission_status()
                         #     if submission_status:
                         #         print("\n--- Submission Status ---")
                         #         print(json.dumps(submission_status, indent=2))
                         #     else:
                         #         print("\nFailed to get submission status.")
                         # else:
                         #      print("\nFailed to click submit button.")

                     else:
                         print("\nFailed to run example tests.")
                else:
                     print("\nFailed to input code.")

            else:
                print(f"\nFailed to get problem details for {PROBLEM_URL}")
        else:
            print("\nLogin failed.")

    print("\nInterface closed.") 
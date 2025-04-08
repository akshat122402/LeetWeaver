# Import necessary libraries
import os  # For operating system related operations
import re  # For regular expression operations
import time  # For adding delays in the script
import random  # For making random selections
import undetected_chromedriver as uc  # For using an undetected version of Chrome WebDriver
from google import genai
from typing import Optional
from ratelimit import limits, sleep_and_retry
import json
from datetime import datetime, timedelta

# Import Selenium WebDriver and related modules for web automation
from selenium import webdriver
from selenium.webdriver.common.by import By  # For locating elements on web pages
from selenium.webdriver.common.keys import Keys  # For simulating keyboard input
from selenium.webdriver.support.ui import WebDriverWait  # For waiting for elements to appear
from selenium.webdriver.support import expected_conditions as EC  # For defining expected conditions for WebDriverWait
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException  # For handling specific exceptions
from selenium.webdriver.common.action_chains import ActionChains  # For performing complex user interactions
from selenium.common.exceptions import TimeoutException  # For handling timeout exceptions
from bs4 import BeautifulSoup  # For parsing HTML content

from dotenv import load_dotenv
import os

# Load environment variables from the .env file 
load_dotenv()


# Constants and Global Variables
MAX_TOKENS = 1000  # Maximum number of tokens for Gemini API responses
TEMPERATURE = 0  # Controls randomness in Gemini's responses (0 means deterministic)
FAILED_PROBLEMS = set()  # Stores problems that couldn't be solved
STARTING_A_NEW_PROBLEM_PROMPT = "Solve this LeetCode problem in Python, optimizing for the fastest runtime approach with the best time complexity unless there is a required time complexity in the description, in that case your solution must match that time complexity. Provide only the Python code solution, with no additional text, comments, or questions before or after the code:"  # Prompt for Gemini when starting a new problem
SUBMITTING_A_CODE_ERROR_PROMPT = "We need to fix our code for a leetcode python problem. Here's what the problem description was: "  # Prompt for Gemini when submitting a code with errors
OUR_CURRENT_CODE_PROMPT = "Here's what the Python code we tried was:"  # Prompt to introduce the current code to Gemini
END_OF_PROMPT_INSTRUCTIONS_FOR_CLEAR_RESPONSE = "Provide only the Python code solution, with no additional text, comments, or questions before or after the code. The solution must start with the same class solution object and function definition(s) and their parameter(s) that the starting code had."  # Instructions for Gemini to provide a clear response
ADVOCATE_FOR_BETTER_SOLUTION_ON_RETRY = "Don't use the same approach as the current code which looks like this, review what part of the description we're likely not meeting the requirements of and make a new solution with an approach that likely is a better fix."  # Prompt for Gemini to suggest a better solution on retry
CODE_EXAMPLE_PREFIX = "Here's the starting code provided by LeetCode:"  # Prefix for introducing LeetCode's starting code to Gemini

CURRENT_PAGE = 1  # Tracks the current page of LeetCode problems

MAX_RETRIES = 2  # Maximum number of attempts to solve a problem
LEETCODE_PROBLEMSET_URL = "https://leetcode.com/problemset/?page=1&topicSlugs=array&status=NOT_STARTED"  # URL for LeetCode problem set
LEETCODEFILTER = 'https://leetcode.com/problemset/?page='  # Base URL for filtered LeetCode problems
LEETCODEPOSTFILTER = '&topicSlugs=array&status=NOT_STARTED'  # Additional filter parameters for LeetCode problems

LEETCODE_PROBLEM_URL_PREFIX = "https://leetcode.com/problems/"  # Prefix for individual LeetCode problem URLs
LEETCODE_LOGIN_URL = "https://leetcode.com/accounts/login/"  # URL for LeetCode login page
problem_title = ''  # Placeholder for storing the current problem title

MAX_PROBLEMS_TO_SOLVE = int(os.getenv("MAX_PROBLEMS", "2"))  # Default to 10 if not specified in .env

class WebAutomation:
    def __init__(self):
        print("Initializing WebAutomation...")
        self.driver = webdriver.Chrome()  # Initialize a Chrome WebDriver instance
        self.wait = WebDriverWait(self.driver, 30)  # Create a WebDriverWait object with a 30-second timeout
        print("WebAutomation initialized.")

    def navigate_to(self, url):
        print(f"Navigating to {url}...")
        self.driver.get(url)  # Use the WebDriver to navigate to the specified URL
        print(f"Navigation complete.")

    def find_element(self, by, value):
        print(f"Finding element by {by}: {value}...")
        element = self.wait.until(EC.presence_of_element_located((by, value)))  # Wait for the element to be present in the DOM
        print("Element found.")
        return element

    def click_element(self, by, value):
        print(f"Clicking element by {by}: {value}...")
        element = self.wait.until(EC.element_to_be_clickable((by, value)))  # Wait for the element to be clickable
        element.click()  # Click the element
        print("Element clicked.")

    def input_text(self, by, value, text):
        print(f"Inputting text into element by {by}: {value}...")
        element = self.find_element(by, value)  # Find the input element
        element.clear()  # Clear any existing text in the element
        element.send_keys(text)  # Input the new text
        print("Text input complete.")

    def get_text(self, by, value):
        print(f"Getting text from element by {by}: {value}...")
        text = self.find_element(by, value).text  # Find the element and get its text content
        print(f"Text retrieved: {text}...") 
        return text

    def current_url(self):
        url = self.driver.current_url  # Get the current URL from the WebDriver
        print(f"Current URL: {url}")
        return url

    def press_keys(self, by, value, *keys):
        print(f"Pressing keys {keys} on element by {by}: {value}...")
        element = self.find_element(by, value)  # Find the element to send keys to
        element.send_keys(keys)  # Send the specified keys to the element
        print("Keys pressed.")

    def ensure_python_language(self):
        print("Ensuring Python language is selected...")
        try:
            lang_select = self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button.text-sm.font-normal.group")))  # Wait for the language selector to be clickable
            
            if "python" in lang_select.text.lower():
                print("Python is already selected.")
                return

            print("Clicking language selector...")
            lang_select.click()  # Click the language selector to open the dropdown
            time.sleep(1)  # Wait for dropdown to open

            print("Selecting Python from dropdown...")
            python_option = self.wait.until(EC.element_to_be_clickable((By.XPATH, "//div[contains(@class, 'text-text-primary') and text()='Python']")))  # Wait for the Python option to be clickable
            python_option.click()  # Select Python
            
            print("Successfully set language to Python.")
        except (TimeoutException, NoSuchElementException) as e:
            print(f"Error setting language to Python: {str(e)}")
            print("Attempting to continue with current language selection.")

    def login(self, username, password):
        print("Attempting to log in...")
        self.navigate_to(LEETCODE_LOGIN_URL)  # Navigate to the LeetCode login page
        
        # Wait for the loading overlay to disappear
        try:
            self.wait.until(EC.invisibility_of_element_located((By.ID, "initial-loading")))
        except TimeoutException:
            print("Loading overlay did not disappear. Attempting to continue...")

        # Wait for and click GitHub login button
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                github_login_button = self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'a[href*="github/login"]')))  # Wait for the GitHub login button to be clickable
                github_login_button.click()  # Click the GitHub login button
                break
            except (TimeoutException, ElementClickInterceptedException) as e:
                if attempt < max_attempts - 1:
                    print(f"Attempt {attempt + 1} failed. Retrying in 5 seconds...")
                    time.sleep(5)  # Wait for 5 seconds before retrying
                else:
                    print("Failed to click GitHub login button after multiple attempts.")
                    raise e

        # Wait for the "Continue" button on GitHub authorization page and click it
        # print("Waiting for Continue button...")
        # try:
        #     continue_button = self.wait.until(EC.element_to_be_clickable((By.XPATH, '//div[@id="base_content"]//button[text()="Continue"]')))  # Wait for the Continue button to be clickable
        #     continue_button.click()  # Click the Continue button
        #     print("Clicked Continue button.")
        # except TimeoutException:
        #     print("Continue button not found. Please check the page manually.")
        #     input("Press Enter after manually clicking Continue or if you need to proceed...")

        # Wait for GitHub login page to load
        print("Waiting for GitHub login page to load...")
        self.wait.until(EC.presence_of_element_located((By.ID, "login_field")))  # Wait for the username field to be present
        
        # Input username and password
        self.input_text(By.ID, "login_field", username)  # Enter the username
        self.input_text(By.ID, "password", password)  # Enter the password
        
        # Click Sign in button
        sign_in_button = self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'input[type="submit"][value="Sign in"]')))  # Wait for the Sign in button to be clickable
        sign_in_button.click()  # Click the Sign in button
        
        # Wait for login to complete
        try:
            self.wait.until(EC.url_contains("https://leetcode.com/"))  # Wait for the URL to change to LeetCode
            print("Login successful.")
            
            # Wait for 5 seconds after successful login
            print("Waiting 5 seconds after successful login...")
            time.sleep(5)
            
            # Navigate to the problems page
            print("Navigating to problems page...")
            self.navigate_to(LEETCODE_PROBLEMSET_URL)  # Navigate to the LeetCode problem set page
            
            # Wait for the problems page to load
            self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'div[role="rowgroup"]')))  # Wait for the problem list to be present
            print("Successfully navigated to problems page.")
            
        except TimeoutException:
            print("Login failed. Please check your credentials or solve any CAPTCHA manually.")
            input("Press Enter after solving any CAPTCHA...")  # Wait for manual intervention if needed

    def manual_login(self):
        print("Navigating to login page...")
        self.navigate_to(LEETCODE_LOGIN_URL)  # Navigate to the LeetCode login page
        print("Please log in manually.")
        print("Waiting for login to complete or 30 seconds to pass...")
        
        try:
            # Wait until we're on the problems page or 30 seconds have passed
            self.wait.until(EC.url_contains("https://leetcode.com/problemset/"))  # Wait for the URL to change to the problem set page
            print("Successfully reached the problems page.")
        except TimeoutException:
            print("30 seconds have passed. Proceeding with the script.")
        
        # Check if we're logged in by looking for a common element on the logged-in homepage
        try:
            self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'div[role="rowgroup"]')))  # Wait for the problem list to be present
            print("Login successful.")
        except TimeoutException:
            print("Login status uncertain. Please ensure you're logged in before proceeding.")
            input("Press Enter to continue...")

class LeetCodeInteraction:
    def __init__(self, web_automation):
        self.web = web_automation  # Store the WebAutomation instance for interacting with the website

    def get_problem_description(self):
        print("Getting problem description...")
        try:
            # Get the HTML content of the description
            description_element = self.web.find_element(By.CSS_SELECTOR, 'div[data-track-load="description_content"]')  # Find the element containing the problem description
            html_content = description_element.get_attribute('innerHTML')  # Get the HTML content of the description
            
            # Parse the HTML
            soup = BeautifulSoup(html_content, 'html.parser')  # Create a BeautifulSoup object to parse the HTML
            
            # Function to recursively process elements
            def process_element(element):
                if isinstance(element, str):
                    return element
                if element.name == 'sup':
                    return f'^{element.text}'  # Format superscript
                elif element.name == 'sub':
                    return f'_{element.text}'  # Format subscript
                elif element.name == 'code':
                    code_content = ''.join(process_element(child) for child in element.children)
                    return f'`{code_content}`'  # Format inline code
                elif element.name in ['p', 'div', 'li']:
                    return '\n' + ''.join(process_element(child) for child in element.children)  # Add newlines for paragraphs, divs, and list items
                elif element.name == 'strong' or element.name == 'b':
                    return f'**{element.text}**'  # Format bold text
                elif element.name == 'em' or element.name == 'i':
                    return f'*{element.text}*'  # Format italic text
                elif element.name == 'pre':
                    return f'\n```\n{element.text}\n```\n'  # Format code blocks
                else:
                    return ''.join(process_element(child) for child in element.children)  # Process other elements recursively

            # Process the entire soup
            processed_text = process_element(soup)
            
            # Remove extra newlines and spaces
            processed_text = re.sub(r'\n\s*\n', '\n\n', processed_text).strip()  # Clean up the processed text
            
            print(f"Problem description retrieved: {processed_text}...") 
            return processed_text
        except Exception as e:
            print(f"Error getting problem description: {str(e)}")
            return ""

    def get_starting_code(self):
        print("Getting starting code...")
        try:
            # Wait for 5 seconds before attempting to get the starting code
            time.sleep(5)
            # Wait for the Monaco editor to load
            self.web.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '.view-lines')))  # Wait for the code editor to be present
            
            # Get all lines of code
            code_lines = self.web.driver.find_elements(By.CSS_SELECTOR, '.view-line')  # Find all lines of code in the editor
            
            # Combine all lines into a single string
            code = '\n'.join([line.text for line in code_lines if line.text])  # Join all non-empty lines of code
            
            print(f"Starting code retrieved: {code}...")
            return code
        except Exception as e:
            print(f"Error getting starting code: {str(e)}")
            return ""

    def clear_code_editor(self):
        print("Clearing code editor...")
        try:
            # Use JavaScript to clear the editor
            js_clear_editor = """
            var editor = monaco.editor.getEditors()[0];
            editor.setValue('');
            """
            self.web.driver.execute_script(js_clear_editor)  # Execute JavaScript to clear the editor
            print("Code editor cleared.")
        except Exception as e:
            print(f"Error clearing code editor: {str(e)}")

    def input_code(self, code):
        print("Inputting code into editor...")
        self.clear_code_editor()  # Clear the existing code in the editor
        try:
            # Use JavaScript to set the value of the editor
            js_set_editor_value = f"""
            var editor = monaco.editor.getEditors()[0];
            editor.setValue(`{code}`);
            """
            self.web.driver.execute_script(js_set_editor_value)  # Execute JavaScript to set the new code in the editor
            print("Code input complete.")
        except Exception as e:
            print(f"Error inputting code: {str(e)}")

    def run_code(self):
        print("Running code...")
        try:
            # Find and click the "Run" button
            run_button = self.web.find_element(By.CSS_SELECTOR, 'button[data-e2e-locator="console-run-button"]')  # Find the Run button
            run_button.click()  # Click the Run button
            print("Code execution initiated.")
        except Exception as e:
            print(f"Error running code: {str(e)}")
            # Fallback to keyboard shortcut if button not found
            self.web.press_keys(By.CSS_SELECTOR, '.monaco-editor textarea', Keys.CONTROL, Keys.ENTER)  # Use keyboard shortcut to run code

    def get_test_results(self):
        print("Getting test results...")
        try:
            # Wait for either the test result or runtime error
            result_or_error = self.web.wait.until(EC.presence_of_element_located((
                By.CSS_SELECTOR, 
                'div[data-e2e-locator="console-result"], div.font-menlo.text-xs.text-red-60'
            )))  # Wait for either the test result or error message to appear
            
            if "Runtime Error" in result_or_error.text:
                # Handle runtime error
                error_message = result_or_error.text
                input_elements = self.web.driver.find_elements(By.XPATH, "//div[contains(@class, 'bg-fill-4')]/div/div[contains(@class, 'font-menlo')]")
                input_text = input_elements[0].text if input_elements else "Input not found"
                
                full_results = {
                    "result": "Runtime Error",
                    "error_message": error_message,
                    "cases": [{"Input": input_text}]
                }
            else:
                # Handle normal test results (existing code)
                result_text = result_or_error.text
                detailed_results = []
                case_buttons = self.web.driver.find_elements(By.CSS_SELECTOR, 'div.cursor-pointer.rounded-lg.px-4.py-1.font-medium')  # Find all test case buttons
                
                for button in case_buttons:
                    button.click()  # Click each test case button
                    time.sleep(1)  # Wait for the case details to load
                    
                    case_details = {}
                    
                    # Find Input section
                    input_elements = self.web.driver.find_elements(By.XPATH, "//div[contains(@class, 'bg-fill-4')]/div/div[contains(@class, 'font-menlo')]")
                    if input_elements:
                        case_details['Input'] = input_elements[0].text
                    
                    # Find Output and Expected sections
                    sections = self.web.driver.find_elements(By.CSS_SELECTOR, 'div.flex.h-full.w-full.flex-col.space-y-2')
                    
                    for section in sections:
                        try:
                            label = section.find_element(By.CSS_SELECTOR, 'div.text-xs.font-medium').text.strip()
                            if label in ['Output', 'Expected']:
                                content = section.find_element(By.CSS_SELECTOR, 'div.font-menlo').text
                                case_details[label] = content
                        except NoSuchElementException:
                            continue
                    
                    if case_details:
                        detailed_results.append(case_details)
                
                full_results = {
                    "result": result_text,
                    "cases": detailed_results
                }
            
            print(f"Test results retrieved: {full_results}")
            return full_results
        except TimeoutException:
            print("Timeout waiting for test results")
            return {"result": "Timeout waiting for test results", "cases": []}
        except Exception as e:
            print(f"An error occurred while getting test results: {str(e)}")
            return {"result": f"Error: {str(e)}", "cases": []}

    def submit_solution(self):
        print("Submitting solution...")
        try:
            submit_button = self.web.find_element(By.CSS_SELECTOR, 'button[data-e2e-locator="console-submit-button"]')  # Find the Submit button
            submit_button.click()  # Click the Submit button
            print("Solution submitted successfully.")
            time.sleep(5)  # Wait for submit sleep
            print("Sleeping for 5 seconds after submit.")
        except Exception as e:
            print(f"Error submitting solution: {str(e)}")

class GeminiAPIIntegration:
    def __init__(self, api_key):
        print("Initializing Gemini API...")
        self.client = genai.Client(api_key=api_key)  # Initialize the Anthropic client with the provided API key
        print("Gemini API initialized.")

    # Add rate limit of 60 calls per minute
    @sleep_and_retry
    @limits(calls=int(os.getenv("GEMINI_RPM")), period=60)
    def send_prompt(self, prompt):
        print("Sending prompt to Gemini API...", prompt)
        message = self.client.models.generate_content(
            model=os.getenv("GEMINI_MODEL"),
            contents=prompt,
            config=genai.types.GenerateContentConfig(
                temperature=TEMPERATURE
            )
        )
        # Pass message.text instead of message.content
        response_text = message.text
        if response_text is None:
             # Handle cases where the response might be blocked or empty
             print("Warning: Received None text from Gemini API. Checking prompt feedback.")
             if message.prompt_feedback:
                 print(f"Prompt Feedback: {message.prompt_feedback}")
             # Decide how to handle this - maybe return empty string or raise an error
             response_text = "" # Default to empty string for now

        response = self.extract_text_from_response(response_text)  # Extract the text from Gemini's response
        print(f"Received response from Gemini API: {response}...")
        return response

    @staticmethod
    def extract_text_from_response(text_content):
        print("Extracting text from Gemini API response...")
        # Directly use the text_content passed in
        if text_content:
            # Basic cleaning: remove code block markers and backticks
            text = re.sub(r'```\w*\n?|```', '', text_content)  # Remove code block markers
            # text = re.sub(r'`([^`\n]+)`', r'\1', text) # Removing this as it might strip intended backticks in code
            return text.strip() # Remove leading/trailing whitespace
        print("No text content received or text was empty.")
        return ""

class CodeGenerationAndErrorHandling:
    def __init__(self, gemini_api):
        self.gemini_api = gemini_api  # Store the GeminiAPIIntegration instance

    def generate_code(self, problem_description, starting_code):
        print("Generating code for problem...")
        prompt = f"{STARTING_A_NEW_PROBLEM_PROMPT}\n\n{problem_description}\n\n{CODE_EXAMPLE_PREFIX}\n{starting_code}"  # Create a prompt for Gemini to generate code
        return self.gemini_api.send_prompt(prompt)  # Send the prompt to Gemini and return the response

    def handle_error(self, problem_description, current_code, starting_code, error_message, error_info):
        print("Handling error and generating corrected code...")
        prompt = f"{SUBMITTING_A_CODE_ERROR_PROMPT}\n\n{problem_description}\n\n{ADVOCATE_FOR_BETTER_SOLUTION_ON_RETRY}\n{current_code}\n\nError Message:\n{error_message}\n\nDetailed Error Information:\n{error_info}\n\n{CODE_EXAMPLE_PREFIX}\n{starting_code}\n\n{END_OF_PROMPT_INSTRUCTIONS_FOR_CLEAR_RESPONSE}"  # Create a prompt for Gemini to fix the code
        print("Prompt we're sending is: ", prompt)
        return self.gemini_api.send_prompt(prompt)  # Send the prompt to Gemini and return the response

# --- New Module for Storing Results ---
class ResultsManager:
    def __init__(self, filename="leetcode_results.json"):
        """Initializes the ResultsManager."""
        self.filename = filename
        self.results = self._load_results()
        self.stats = self._calculate_stats()
        print(f"Results will be saved to {self.filename}")
        self._print_current_stats()

    def _load_results(self):
        """Loads existing results from the JSON file."""
        if os.path.exists(self.filename):
            try:
                with open(self.filename, 'r') as f:
                    print(f"Loading existing results from {self.filename}")
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                print(f"Error loading results file {self.filename}: {e}. Starting with empty results.")
                return {"problems": [], "statistics": {"total_attempted": 0, "total_solved": 0, "accuracy": 0.0}}
        else:
            print("No existing results file found. Starting with empty results.")
            return {"problems": [], "statistics": {"total_attempted": 0, "total_solved": 0, "accuracy": 0.0}}

    def _calculate_stats(self):
        """Calculate current statistics from results."""
        total_attempted = len(self.results["problems"])
        total_solved = sum(1 for result in self.results["problems"] if result["status"] == "solved")
        accuracy = (total_solved / total_attempted * 100) if total_attempted > 0 else 0.0
        
        stats = {
            "total_attempted": total_attempted,
            "total_solved": total_solved,
            "accuracy": round(accuracy, 2)
        }
        
        self.results["statistics"] = stats
        return stats

    def _print_current_stats(self):
        """Print current statistics to terminal."""
        print("\n=== Current Statistics ===")
        print(f"Total Problems Attempted: {self.stats['total_attempted']}")
        print(f"Total Problems Solved: {self.stats['total_solved']}")
        print(f"Current Accuracy: {self.stats['accuracy']}%")
        print("=======================\n")

    def save_result(self, problem_title, status, attempts, details=None):
        """Adds a new result and saves the updated list to the JSON file."""
        if details is None:
            details = {}
        
        # Add solving duration if available
        if "start_time" in details:
            end_time = datetime.now()
            start_time = details.pop("start_time")  # Remove start_time from details
            duration = end_time - start_time
            duration_seconds = duration.total_seconds()
            details["solving_duration_seconds"] = round(duration_seconds, 2)
            details["solving_duration_formatted"] = str(timedelta(seconds=int(duration_seconds)))

        result_entry = {
            "problem_title": problem_title,
            "status": status,
            "attempts": attempts,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "details": details
        }
        
        self.results["problems"].append(result_entry)
        self.stats = self._calculate_stats()
        
        try:
            with open(self.filename, 'w') as f:
                json.dump(self.results, f, indent=4)
            print(f"Saved result for '{problem_title}' to {self.filename}")
            self._print_current_stats()
        except IOError as e:
            print(f"Error saving results to {self.filename}: {e}")

# --- End of New Module ---

def complete_individual_problem(leetcode, code_gen, problem_title, results_manager):
    print(f"Starting to solve problem: {problem_title}")
    start_time = datetime.now()  # Start timing
    
    current_url = leetcode.web.current_url()
    if not current_url.startswith(LEETCODE_PROBLEM_URL_PREFIX):
        print("Error: Not on a LeetCode problem page")
        results_manager.save_result(
            problem_title, 
            "error", 
            0, 
            {
                "message": "Not on a problem page",
                "start_time": start_time
            }
        )
        raise ValueError("Not on a LeetCode problem page")

    leetcode.web.ensure_python_language()
    problem_description = leetcode.get_problem_description()
    starting_code = leetcode.get_starting_code()
    final_status = "failed"
    final_details = {"start_time": start_time}  # Include start_time in details
    solved_attempt = -1

    for attempt in range(MAX_RETRIES):
        current_attempt = attempt + 1
        print(f"Attempt {current_attempt} of {MAX_RETRIES}")
        if attempt == 0:
            code = code_gen.generate_code(problem_description, starting_code)
        else:
            code = code_gen.handle_error(problem_description, code, starting_code, results['result'], error_info)

        print(f"Code for attempt {current_attempt}:\n{code}")
        if not code:
            print("Error: Received empty code from generation/error handling. Skipping attempt.")
            error_info = "Received empty code from API"
            final_details.update({
                "error": error_info,
                "last_code_attempt": ""
            })
            continue

        leetcode.input_code(code)
        leetcode.run_code()
        print("Waiting for test results...")
        time.sleep(5)
        results = leetcode.get_test_results()

        print(f"Test Results:\n{results}")

        if results['result'] == "Accepted":
            print("Problem solved successfully!")
            leetcode.submit_solution()
            final_status = "solved"
            solved_attempt = current_attempt
            final_details.update({
                "final_code": code
            })
            results_manager.save_result(problem_title, final_status, solved_attempt, final_details)
            return True
        elif results['result'] == "Runtime Error":
            print(f"Runtime Error encountered. Error message: {results.get('error_message', 'N/A')}")
            error_info = f"Runtime Error:\n{results.get('error_message', 'N/A')}\nInput: {results.get('cases', [{}])[0].get('Input', 'N/A')}"
            final_details.update({
                "error": results.get('error_message', 'N/A'),
                "input": results.get('cases', [{}])[0].get('Input', 'N/A'),
                "last_code_attempt": code
            })
        elif "Error" in results['result'] or "Timeout" in results['result']:
            print(f"Error/Timeout encountered: {results['result']}")
            error_info = results['result']
            final_details.update({
                "error": error_info,
                "last_code_attempt": code
            })
        else:
            print(f"Incorrect answer or other issue: {results['result']}. Attempting to fix...")
            error_info = "\n".join([f"Case {i+1}:\n" + "\n".join([f"{k}: {v}" for k, v in case.items()]) for i, case in enumerate(results.get('cases', []))])
            final_details.update({
                "error": results['result'],
                "failed_cases": results.get('cases', []),
                "last_code_attempt": code
            })

    print(f"Max retries reached. Adding problem '{problem_title}' to failed list and moving to next problem.")
    FAILED_PROBLEMS.add(problem_title)
    results_manager.save_result(problem_title, final_status, MAX_RETRIES, final_details)
    return False

def navigate_to_new_problem(web_automation):
    global CURRENT_PAGE
    print(f"Navigating to problem set page {CURRENT_PAGE}...")
    web_automation.navigate_to(f"{LEETCODEFILTER}{CURRENT_PAGE}{LEETCODEPOSTFILTER}")  # Navigate to the problem set page
    
    while True:
        print(f"Waiting 5 seconds for problem list on page {CURRENT_PAGE} to load...")
        time.sleep(5)

        print("Waiting for problem list to load...")
        WebDriverWait(web_automation.driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'div[role="rowgroup"]'))
        )  # Wait for the problem list to load
        
        print("Selecting a random non-premium, non-failed problem...")
        problem_rows = web_automation.driver.find_elements(By.CSS_SELECTOR, 'div[role="row"]')  # Find all problem rows
        available_problems = []

        for row in problem_rows:
            cells = row.find_elements(By.CSS_SELECTOR, 'div[role="cell"]')
            if len(cells) >= 2:
                title_cell = cells[1]  # The title is in the second cell
                
                # Check if the problem is not premium and not failed
                title_link = title_cell.find_element(By.CSS_SELECTOR, 'a[href^="/problems/"]')
                if 'opacity-60' not in title_link.get_attribute('class') and title_link.text not in FAILED_PROBLEMS:
                    available_problems.append(title_link)
        
        if available_problems:
            random_problem = random.choice(available_problems)  # Choose a random problem from available problems
            problem_url = random_problem.get_attribute('href')
            problem_title = random_problem.text
            print(f"Selected problem: {problem_title} from page {CURRENT_PAGE}")
            print(f"Navigating to: {problem_url}")
            web_automation.navigate_to(problem_url)  # Navigate to the selected problem
            print("Waiting 5 seconds for problem page to load...")
            time.sleep(5)  # Wait for 5 seconds after navigating to the problem
            return problem_title
        else:
            print(f"No available problems on page {CURRENT_PAGE}. Attempting to go to next page...")
            next_button = web_automation.driver.find_element(By.XPATH, '//button[@aria-label="next"]')
            if next_button.is_enabled():
                next_button.click()  # Click the next page button if available
                CURRENT_PAGE += 1
                print(f"Navigating to page {CURRENT_PAGE}...")
                time.sleep(5)  # Wait for 5 seconds after clicking next
            else:
                print("No more pages available. Resetting to page 1 and falling back to 'Two Sum' problem...")
                CURRENT_PAGE = 1
                web_automation.navigate_to(f"{LEETCODE_PROBLEM_URL_PREFIX}two-sum")  # Navigate to the 'Two Sum' problem as a fallback
                print("Waiting 5 seconds for problem page to load...")
                time.sleep(5)
                return "Two Sum"

    # Ensure Python language is selected
    web_automation.ensure_python_language()
    
def main():
    global CURRENT_PAGE
    print("Starting LeetCode Solver...")
    print(f"Will attempt to solve {MAX_PROBLEMS_TO_SOLVE} problems")
    
    web_automation = WebAutomation()
    leetcode = LeetCodeInteraction(web_automation)
    gemini_api = GeminiAPIIntegration(os.getenv("GEMINI_API_KEY"))
    code_gen = CodeGenerationAndErrorHandling(gemini_api)
    results_manager = ResultsManager()

    # Use the new automated login method
    web_automation.login(os.getenv("LEETCODE_USERNAME"), os.getenv("LEETCODE_PASSWORD"))

    problems_attempted = 0
    
    while problems_attempted < MAX_PROBLEMS_TO_SOLVE:
        try:
            remaining_problems = MAX_PROBLEMS_TO_SOLVE - problems_attempted
            print(f"\n=== Attempting problem {problems_attempted + 1} of {MAX_PROBLEMS_TO_SOLVE} ({remaining_problems} remaining) ===\n")
            
            problem_title = navigate_to_new_problem(web_automation)
            if complete_individual_problem(leetcode, code_gen, problem_title, results_manager):
                print(f"Successfully solved problem: {problem_title}. Moving to next problem...")
            else:
                print(f"Failed to solve problem: {problem_title}. Skipping to next problem...")
            
            problems_attempted += 1
            
        except Exception as e:
            print(f"A critical error occurred in the main loop: {e}")
            try:
                current_problem = problem_title
            except NameError:
                current_problem = "Unknown (error before problem selection)"

            results_manager.save_result(current_problem, "critical_error", 0, {"message": str(e)})
            print("Attempting to continue with next problem...")
            CURRENT_PAGE = 1
            problems_attempted += 1  # Count failed attempts toward the total
    
    print("\n=== LeetCode Solver Completed ===")
    print(f"Attempted {problems_attempted} problems")
    results_manager._print_current_stats()  # Print final statistics
    web_automation.driver.quit()  # Clean up by closing the browser

if __name__ == "__main__":
    main()
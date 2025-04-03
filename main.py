import argparse
import logging
from logging.handlers import RotatingFileHandler
from core.orchestrator import Orchestrator
from dotenv import load_dotenv
import os

load_dotenv()

# --- Configure Logging ---
log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log_level = logging.INFO

# Console Handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)

# File Handler (Rotating)
# Creates a file 'leetweaver.log', backs it up when it reaches 1MB, keeps 3 backup files.
file_handler = RotatingFileHandler('leetweaver.log', maxBytes=1024*1024, backupCount=3)
file_handler.setFormatter(log_formatter)

# Get the root logger and add handlers
root_logger = logging.getLogger()
root_logger.setLevel(log_level)
root_logger.addHandler(console_handler)
root_logger.addHandler(file_handler)

# Get the logger for the current module
logger = logging.getLogger(__name__)
# --- End Logging Configuration ---

def main():
    parser = argparse.ArgumentParser(description="LeetWeaver: AI Agent for solving LeetCode problems.")

    parser.add_argument("url", help="The URL of the LeetCode problem to solve.")
    # Add arguments for benchmarking later
    # parser.add_argument("--benchmark", choices=['humaneval', 'mbpp'], help="Run evaluation on a specific benchmark instead of solving a LeetCode problem.")
    # parser.add_argument("--code_file", help="Path to the code file to benchmark (required if --benchmark is used).")

    args = parser.parse_args()

    # Basic input validation
    if not args.url.startswith("https://leetcode.com/problems/"):
        logger.error(f"Invalid LeetCode problem URL: {args.url}")
        print("Please provide a valid LeetCode problem URL (e.g., https://leetcode.com/problems/two-sum/)")
        return

    # Check essential environment variables
    if not os.getenv("LEETCODE_USERNAME") or not os.getenv("LEETCODE_PASSWORD") or not os.getenv("GEMINI_API_KEY"):
         logger.error("Missing required environment variables (LEETCODE_USERNAME, LEETCODE_PASSWORD, GEMINI_API_KEY).")
         print("Error: Please ensure LEETCODE_USERNAME, LEETCODE_PASSWORD, and GEMINI_API_KEY are set in your .env file.")
         return

    # --- Check this section carefully ---
    max_iter = 5 # Default value
    try:
        # Are you reading it from env? Is the name correct? Is there a default?
        env_max_iter = os.getenv('MAX_ITERATIONS')
        if env_max_iter:
            max_iter = int(env_max_iter) # Example: Reads from .env, defaults to 5
        else:
            logger.info("MAX_ITERATIONS not found in .env. Using default value: %d", max_iter)
    except ValueError:
        logger.warning("Warning: MAX_ITERATIONS in .env is not a valid integer. Using default value: %d", max_iter)
        # Keep the default max_iter = 5

    orchestrator = Orchestrator(max_iterations=max_iter) # Make sure max_iter holds the correct value here

    try:
        final_state = orchestrator.run_problem(args.url)

        print("\n--- LeetWeaver Run Summary ---")
        print(f"Problem: {final_state.problem_title} ({final_state.problem_url})")
        print(f"Status: {final_state.status}")
        if final_state.error_message:
            print(f"Details: {final_state.error_message}")
        if final_state.submission_results:
            print("Submission Result:")
            import json
            print(json.dumps(final_state.submission_results, indent=2))
        print(f"Iterations: {final_state.iteration}")

    except Exception as e:
        logger.critical(f"A critical error occurred during execution: {e}", exc_info=True)
        print(f"\nAn unexpected error stopped the process: {e}")
    finally:
        logger.info("LeetWeaver finished.")


if __name__ == "__main__":
    main() 
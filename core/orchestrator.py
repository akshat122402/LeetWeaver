import logging
import os
from typing import Dict, Any, Optional
from dotenv import load_dotenv

from agents.base_agent import BaseAgent
from agents.problem_analyzer import ProblemAnalyzerAgent
from agents.coding_agent import CodingAgent
from agents.debugging_agent import DebuggingAgent

from interfaces.leetcode_interface import LeetCodeInterface
from core.state import WorkflowState

logger = logging.getLogger(__name__)
load_dotenv()

class Orchestrator:
    """
    Manages the workflow of agents to solve a LeetCode problem by submitting directly.

    Note: This implementation differs from the original plan.md architecture:
    1. TestingAgent has been removed - solutions are submitted directly to LeetCode without local testing
    2. OptimizationAgent has been removed - no optimization phase is performed

    This simplified workflow focuses on: Plan -> Code -> Submit -> Debug (if needed) -> Code...
    """
    def __init__(self,  max_iterations: Optional[int] = None):
        """Initialize the orchestrator with a list of agents."""
        load_dotenv()  # Ensure environment variables are loaded
        # Use environment variable with fallback to default
        self.max_iterations = (
            max_iterations or
            int(os.getenv('MAX_ITERATIONS', 5))  # Default to 5 if not set or specified
        )
        logger.info(f"Orchestrator initialized with max_iterations: {self.max_iterations}")

        # Agent Initialization
        # Only using a subset of agents from plan.md: Analyzer, Coder, and Debugger
        self.agents: Dict[str, BaseAgent] = {
            "analyzer": ProblemAnalyzerAgent(),
            "coder": CodingAgent(),
            "debugger": DebuggingAgent(),
            # Additional agents could be added here in future versions
        }
        logger.info("Orchestrator initialized with agents: %s", list(self.agents.keys()))


    def run_problem(self, problem_url: str) -> WorkflowState:
        """
        Executes the workflow: Analyze -> Code -> Submit -> Debug (if needed) -> Code ...
        """
        logger.info(f"Starting workflow for problem: {problem_url}")
        state = WorkflowState(problem_url=problem_url, max_iterations=self.max_iterations)
        previous_code = None

        try:
            with LeetCodeInterface() as leetcode_interface:
                # --- Login ---
                if not leetcode_interface.login():
                    state.status = "Failed"
                    state.error_message = "LeetCode login failed."
                    logger.error(state.error_message)
                    return state

                # --- Get Problem Details ---
                details = leetcode_interface.get_problem_details(problem_url)
                if not details or not details.get('description') or not details.get('starting_code'):
                    state.status = "Failed"
                    state.error_message = f"Failed to retrieve problem details from {problem_url}."
                    logger.error(state.error_message)
                    return state
                state.problem_description = details['description']
                state.starting_code = details['starting_code']
                state.problem_title = details.get('title', problem_url.split('/')[-2] if problem_url.endswith('/') else problem_url.split('/')[-1])
                if state.current_code is None:
                    state.current_code = state.starting_code

                # --- Main Iteration Loop ---
                state.status = "Planning"
                iteration_count = 0
                # Use "Success" as the accepted terminal state
                while state.status not in ["Success", "Failed", "Error"] and iteration_count < self.max_iterations:
                    iteration_count += 1
                    state.iteration = iteration_count # Update state iteration count
                    logger.info(f"--- Iteration {iteration_count}/{self.max_iterations} --- Status: {state.status} ---")

                    if state.status == "Planning":
                        logger.info("Calling Problem Analyzer Agent...")
                        state = self.agents["analyzer"].execute(state)
                        if not state.plan:
                            state.status = "Failed"
                            state.error_message = state.error_message or "Planning phase failed (no plan generated)."
                            logger.error(f"Analyzer agent failed: {state.error_message}")
                            break
                        logger.info("Planning complete. Moving to Coding.")
                        state.status = "Coding"
                        # Ensure starting code is set if current_code is somehow None
                        if state.current_code is None:
                             state.current_code = state.starting_code

                    elif state.status == "Coding":
                        logger.info("Calling Coding Agent...")
                        previous_code = state.current_code
                        state = self.agents["coder"].execute(state)

                        if state.error_message and not state.current_code:
                            state.status = "Failed"
                            logger.error(f"Coding agent failed critically: {state.error_message}")
                            break
                        elif state.current_code == previous_code and iteration_count > 1 and not state.debug_analysis:
                            # If code hasn't changed and it wasn't based on new debug info, it's stuck in a loop
                            logger.error("Coding agent did not produce new code. Loop detected.")
                            state.status = "Failed"
                            state.error_message = "Coding agent stuck in a loop - unable to generate new code."
                            break

                        logger.info("Coding agent finished. Moving to Submission.")
                        state.status = "Submitting"
                        state.debug_analysis = None # Clear debug analysis after coding attempt

                    # REMOVED Testing State
                    # REMOVED Optimizing State

                    elif state.status == "Debugging":
                        # This state is reached *after* a failed submission
                        logger.info("Calling Debugging Agent...")
                        state = self.agents["debugger"].execute(state) # Debugger uses state.submission_results

                        if state.error_message and state.status == "Failed": # Check if debugger itself failed critically
                            logger.error(f"Debugging agent failed critically: {state.error_message}")
                            break
                        elif not state.debug_analysis and not state.current_code: # Debugger didn't provide analysis or code
                             logger.error("Debugging agent failed to provide analysis or corrected code.")
                             state.status = "Failed"
                             state.error_message = state.error_message or "Debugging failed to produce results."
                             break

                        logger.info("Debugging agent finished. Moving back to Coding to apply fixes/analysis.")
                        state.status = "Coding" # Go back to coding with the debug_analysis

                    elif state.status == "Submitting":
                        logger.info("Attempting LeetCode submission...")
                        if not state.current_code:
                            state.status = "Failed"
                            state.error_message = "No code available to submit."
                            logger.error(state.error_message)
                            break

                        # Ensure language is Python before submitting
                        if not leetcode_interface.ensure_python_language():
                             logger.error("Failed to explicitly set language to Python before submission.")
                             state.status = "Failed"
                             state.error_message = "Failed to set Python language for submission."
                             break

                        if leetcode_interface.input_code_to_editor(state.current_code):
                            if leetcode_interface.submit_solution():
                                submission_results = leetcode_interface.get_submission_status()
                                state.submission_results = submission_results # Store results regardless of status

                                if submission_results and submission_results.get("status") == "Accepted":
                                    state.status = "Success" # Use "Success" as the final good state
                                    logger.info(f"Problem {state.problem_title} SOLVED successfully!")
                                    # No need to break here, the while loop condition will handle it
                                else:
                                    # Submission failed or was not accepted
                                    logger.warning(f"Submission failed or not accepted: {submission_results}")
                                    state.test_results = None # Clear any stale local test results (though none should exist)
                                    state.status = "Debugging" # Go to debugging state
                                    # Max iteration check is handled by the main loop condition
                            else:
                                state.status = "Failed"
                                state.error_message = "Failed to click submit button (interface error)."
                                logger.error(state.error_message)
                                # No need to break here, the while loop condition will handle it
                        else:
                            state.status = "Failed"
                            state.error_message = "Failed to input code into editor for submission (interface error)."
                            logger.error(state.error_message)
                            # No need to break here, the while loop condition will handle it

                    else:
                        logger.error(f"Reached unknown state: {state.status}")
                        state.status = "Failed"
                        state.error_message = "Workflow entered unknown state."
                        break # Break on unknown state

                # --- End of Loop ---
                if state.status not in ["Success", "Failed", "Error"]:
                    # If loop finished due to max iterations without success/failure
                    state.status = "Failed"
                    state.error_message = f"Max iterations ({self.max_iterations}) reached without success."
                    logger.warning(state.error_message)

        except Exception as e:
            logger.error(f"An unexpected error occurred in the orchestrator: {e}", exc_info=True)
            state.status = "Failed" # Use Failed state for consistency
            state.error_message = f"Orchestrator error: {str(e)}"
            # Ensure status is terminal if an exception occurs mid-workflow
            if state.status not in ["Success", "Failed", "Error"]:
                 state.status = "Failed"


        logger.info(f"Workflow finished for {problem_url}. Final Status: {state.status}")
        return state

    # Placeholder for future benchmark functionality
    def run_benchmark(self, benchmark_name: str) -> Dict[str, Any]:
         """Placeholder for future benchmark functionality.

         This method would run the solution against standard coding benchmarks
         as described in plan.md, but is not implemented in the current version.

         Args:
             benchmark_name: The name of the benchmark to run

         Returns:
             A dictionary with the benchmark status
         """
         logger.info(f"Running benchmark '{benchmark_name}'...")
         logger.warning("Benchmarking not currently supported in this workflow.")
         return {"status": "Not Supported", "message": "BenchmarkAgent not implemented in this version."}


# Example Usage (Optional - update if needed)
if __name__ == "__main__":
    # Ensure required env vars are checked before running
    if not os.getenv("LEETCODE_USERNAME") or not os.getenv("LEETCODE_PASSWORD") or not os.getenv("GEMINI_API_KEY"):
        print("ERROR: Please set LEETCODE_USERNAME, LEETCODE_PASSWORD, and GEMINI_API_KEY in the .env file.")
    else:
        # Get max iterations from env or use default
        max_iter_env = os.getenv('MAX_ITERATIONS')
        max_iter_val = 5 # Default
        if max_iter_env:
            try:
                max_iter_val = int(max_iter_env)
            except ValueError:
                 print(f"Warning: Invalid MAX_ITERATIONS value '{max_iter_env}'. Using default {max_iter_val}.")
        else:
             print(f"Info: MAX_ITERATIONS not set. Using default {max_iter_val}.")


        orchestrator = Orchestrator(max_iterations=max_iter_val)
        # test_problem_url = "https://leetcode.com/problems/two-sum/"
        test_problem_url = "https://leetcode.com/problems/add-two-numbers/" # Example different problem

        final_state = orchestrator.run_problem(test_problem_url)

        print("\n--- Orchestrator Run Complete ---")
        print(f"Problem URL: {final_state.problem_url}")
        print(f"Final Status: {final_state.status}")
        if final_state.plan: print("\n--- Generated Plan ---"); print(final_state.plan)
        if final_state.constraints: print("\n--- Identified Constraints ---"); print(final_state.constraints)
        if final_state.current_code and final_state.status == "Success": print("\n--- Final Accepted Code ---"); print(final_state.current_code)
        elif final_state.current_code: print("\n--- Last Generated Code ---"); print(final_state.current_code)
        # Local test results are no longer generated
        # if final_state.test_results is not None: print("\n--- Local Test Results ---"); import json; print(json.dumps(final_state.test_results, indent=2))
        if final_state.debug_analysis: print("\n--- Last Debugging Analysis ---"); print(final_state.debug_analysis)
        # Optimization analysis is no longer generated
        # if final_state.optimization_analysis: print("\n--- Last Optimization Analysis ---"); print(final_state.optimization_analysis)
        if final_state.error_message: print(f"\nError Message: {final_state.error_message}")
        if final_state.submission_results: print("\nLast Submission Results:"); import json; print(json.dumps(final_state.submission_results, indent=2))
        print(f"Total Iterations: {final_state.iteration}")

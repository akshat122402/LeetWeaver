import logging
import re
import json
from agents.base_agent import BaseAgent
from core.state import WorkflowState
from utils.llm_api import generate_content
from typing import Optional, List, Dict, Any, Tuple

logger = logging.getLogger(__name__)

class DebuggingAgent(BaseAgent):
    """
    Agent responsible for analyzing failed test results or submission errors
    and suggesting fixes for the code.
    """
    def __init__(self):
        super().__init__(name="Debugging Agent")

    def execute(self, state: WorkflowState) -> WorkflowState:
        """
        Analyzes failures and uses an LLM to suggest fixes or provide corrected code.

        Args:
            state: The current workflow state, containing 'current_code',
                   'problem_description', 'plan', 'starting_code', and either
                   'test_results' (with failures) or 'submission_results'
                   (if not accepted).

        Returns:
            The updated workflow state. 'debug_analysis' will be populated with
            the LLM's findings. 'current_code' might be updated if the LLM
            provides a full corrected code block. Sets error message if debugging fails.
        """
        logger.info(f"Executing {self.name} for problem: {state.problem_title}")

        # --- Validate Inputs ---
        if not state.current_code:
            logger.error("Current code is missing for debugging.")
            state.error_message = f"{self.name}: Current code missing."
            state.status = "Failed"
            return state
        if not state.starting_code:
             logger.warning("Starting code template is missing. Debugging might be less effective.")
             # Allow proceeding, but flag the risk

        # Determine the source of failure: local tests or submission
        failure_context = self._prepare_failure_context(state)
        if not failure_context:
             logger.error("No failure context (failed tests or submission error) found for debugging.")
             state.error_message = f"{self.name}: No failure context provided."
             # If there's no failure, maybe we shouldn't be debugging?
             # Let's return the state as is, maybe orchestrator logic error.
             logger.warning("Debugging agent called without failure context. Returning state unchanged.")
             return state # Return state, let orchestrator handle this unexpected call

        # --- Construct Prompt ---
        prompt = self._create_debugging_prompt(
            state.problem_description,
            state.plan,
            state.current_code,
            state.starting_code, # Pass starting code
            failure_context
        )

        # --- Get Debugging Analysis from LLM ---
        try:
            llm_response = generate_content(prompt)

            if not llm_response:
                logger.error("LLM debugging analysis returned an empty result.")
                state.error_message = f"{self.name}: LLM failed to provide debugging analysis."
                # Keep current code, let orchestrator decide if retry or fail
                return state

            # --- Parse Response and Update State ---
            analysis, corrected_code = self._parse_debugging_response(llm_response)

            state.debug_analysis = analysis or "LLM did not provide specific analysis."
            logger.info(f"Debugging analysis received:\n{state.debug_analysis}")

            if corrected_code:
                logger.info("LLM provided corrected code. Updating current code.")
                state.current_code = corrected_code
                state.error_message = None # Clear error if new code is provided
            else:
                logger.info("LLM did not provide a full corrected code block. Keeping previous code.")
                # The coding agent will use the debug_analysis in the next iteration

        except Exception as e:
            logger.error(f"An error occurred during debugging analysis: {e}", exc_info=True)
            state.error_message = f"{self.name}: Exception during debugging - {e}"
            # Keep previous state, let orchestrator handle

        return state

    def _prepare_failure_context(self, state: WorkflowState) -> Optional[str]:
        """Extracts information about failures from test_results or submission_results."""
        context_lines = []

        # Priority 1: Failed LeetCode submission (Primary source in the new workflow)
        if state.submission_results and state.submission_results.get("status") != "Accepted":
            context_lines.append("The code failed LeetCode submission with the following result:")
            # Include relevant details from submission_results
            # Prioritize common useful fields
            priority_keys = ["status", "error_message", "last_testcase", "expected_output", "runtime_error", "compile_error"]
            present_keys = [k for k in priority_keys if k in state.submission_results and state.submission_results[k]]
            other_keys = [k for k in state.submission_results if k not in priority_keys and state.submission_results[k]]

            for key in present_keys + other_keys:
                 value = state.submission_results[key]
                 # Avoid overly long fields if necessary
                 context_lines.append(f"- {key.replace('_', ' ').title()}: {str(value)[:300]}") # Limit value length slightly more
            return "\n".join(context_lines)

        # Priority 2: Failed local tests (If ever re-enabled)
        if state.test_results:
            failed_tests = [r for r in state.test_results if not r.get('passed')]
            if failed_tests:
                context_lines.append("The code failed the following local test cases:")
                for test in failed_tests[:3]: # Limit context size further for local tests if used
                    context_lines.append(f"- ID: {test.get('id', 'N/A')}")
                    context_lines.append(f"  Input: {json.dumps(test.get('input'))}")
                    context_lines.append(f"  Expected Output: {json.dumps(test.get('expected_output'))}")
                    context_lines.append(f"  Actual Output: {json.dumps(test.get('actual_output'))}")
                    if test.get('error'):
                        context_lines.append(f"  Error: {test['error']}")
                if len(failed_tests) > 3:
                     context_lines.append(f"... and {len(failed_tests) - 3} more failed tests.")
                return "\n".join(context_lines)


        return None # No failure context found

    def _create_debugging_prompt(
        self,
        description: str,
        plan: Optional[str],
        code: str,
        starting_code: Optional[str], # Added parameter
        failure_context: str
    ) -> str:
        """Creates the prompt for the LLM to debug the code."""

        prompt_lines = [
            "You are an expert Python programmer acting as a debugger.",
            "The following Python code was written to solve a LeetCode problem, but it failed during submission.",
            "Analyze the code, the problem description, the plan (if available), the required starting code structure, and the submission failure context provided below.",
            "\nProblem Description:",
            "---",
            description,
            "---",
        ]

        if plan:
            prompt_lines.extend([
                "\nOriginal Plan/Pseudocode:",
                "---",
                plan,
                "---",
            ])

        # Include the starting code template for reference
        if starting_code:
            prompt_lines.extend([
                "\nRequired Starting Code Structure (The corrected code MUST use this):",
                "```python",
                starting_code,
                "```",
                "---",
            ])

        prompt_lines.extend([
            "\nCode with potential bugs:",
            "---",
            "```python",
            code,
            "```",
            "---",
            "\nSubmission Failure Context:",
            "---",
            failure_context,
            "---",
            "\nIMPORTANT Analysis Instructions:",
            "- Carefully analyze the 'Submission Failure Context'. This contains the reason for failure (e.g., 'Wrong Answer', 'Time Limit Exceeded', 'Runtime Error').",
            "- If 'Wrong Answer', focus on the 'Last Testcase', 'Expected Output', and the code's logic to understand why it produced an incorrect result for that input.",
            "- If 'Time Limit Exceeded', analyze the code's time complexity. Identify bottlenecks or inefficient algorithms/data structures relative to the problem constraints. Suggest a more efficient approach.",
            "- If 'Runtime Error', examine the specific error message and the 'Last Testcase' that triggered it. Pinpoint the cause (e.g., division by zero, index out of bounds, null pointer).",
            "- If 'Compile Error', identify the syntax error in the code.",
            "\nPlease perform the following:",
            "1. **Identify the bug(s):** Based *specifically* on the submission failure context, explain the root cause of the failure (logical error, inefficiency, runtime issue, syntax error).",
            "2. **Suggest a fix:** Describe precisely how to correct the identified bug(s) in the code's logic, structure, or algorithm.",
            "3. **Provide Corrected Code:** Provide the *complete*, corrected Python code within a single markdown code block (```python ... ```). Ensure it:",
            "    - Addresses the identified bug(s).",
            "    - **Strictly adheres** to the 'Required Starting Code Structure' (class name, method names, parameters).",
            "    - Is ready for direct submission.",
            "   If you believe the original code was actually correct *despite* the failure (e.g., a very rare edge case or potential platform issue you cannot fix), explain why and do NOT include a code block.",
            "\nFormat your response clearly: Start with the analysis/explanation, then provide the corrected code block *only if* a correction was identified.",
        ])

        return "\n".join(prompt_lines)

    def _parse_debugging_response(self, text: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Parses the LLM's debugging response to extract the analysis
        and the corrected code block (if provided).
        """
        analysis = None
        corrected_code = None
        raw_extracted_code = None # Store the raw extraction first

        # Try to extract corrected code first
        # Use re.DOTALL to make '.' match newlines within the code block
        code_match = re.search(r"```python\s*([\s\S]+?)\s*```", text, re.IGNORECASE | re.DOTALL)
        if code_match:
            raw_extracted_code = code_match.group(1).strip()
            # Assume the text before the code block is the analysis
            analysis = text[:code_match.start()].strip()

            # Check if the extracted code is substantial and likely actual code
            if raw_extracted_code and any(line.strip() and not line.strip().startswith('#') for line in raw_extracted_code.splitlines()):
                 corrected_code = raw_extracted_code
                 logger.debug("Found substantial corrected code block.")
            else:
                 logger.info("Found python code block, but content seems empty or non-code. Ignoring.")
                 # If analysis wasn't found before, maybe it's the whole text
                 if not analysis:
                     analysis = text.strip() # Fallback: treat whole text as analysis

        else:
            # If no code block, assume the entire response is the analysis
            logger.debug("No python code block found in LLM response.")
            analysis = text.strip()

        # Basic cleanup of analysis text
        if analysis:
             analysis_lines = analysis.split('\n')
             # Remove potential leading/trailing boilerplate if simple
             if analysis_lines and ("here's the analysis" in analysis_lines[0].lower() or "sure, i can help" in analysis_lines[0].lower()):
                 analysis_lines.pop(0)
             if analysis_lines and ("let me know if" in analysis_lines[-1].lower()):
                 analysis_lines.pop()
             analysis = "\n".join(analysis_lines).strip()
             # Ensure analysis is not empty after cleanup
             if not analysis:
                 analysis = "LLM provided a response, but analysis could not be cleanly extracted."


        return analysis, corrected_code
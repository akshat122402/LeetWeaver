import logging
import re
import json
from agents.base_agent import BaseAgent
from core.state import WorkflowState
from utils.llm_api import generate_content
from utils.execution import run_python_code # Import the local execution function
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class TestingAgent(BaseAgent):
    """
    Agent responsible for generating test cases and executing the current code
    against them locally.
    """
    def __init__(self):
        super().__init__(name="Testing Agent")

    def execute(self, state: WorkflowState) -> WorkflowState:
        """
        Generates/extracts test cases and runs the current code against them.

        Args:
            state: The current workflow state, must contain 'current_code',
                   'problem_description', and 'constraints'.

        Returns:
            The updated workflow state with 'test_cases' and 'test_results' populated.
            Sets error message if testing fails critically.
        """
        logger.info(f"Executing {self.name} for problem: {state.problem_title}")

        # --- Validate Inputs ---
        if not state.current_code:
            logger.error("Current code is missing.")
            state.error_message = f"{self.name}: Current code missing."
            state.status = "Failed" # Cannot test without code
            return state
        if not state.problem_description:
            logger.error("Problem description is missing.")
            state.error_message = f"{self.name}: Problem description missing."
            state.status = "Failed" # Needed for test generation
            return state

        # --- Test Case Generation ---
        # 1. Extract examples (Placeholder - complex parsing needed)
        extracted_examples = self._extract_example_test_cases(state.problem_description)
        logger.info(f"Extracted {len(extracted_examples)} example test cases (basic extraction).")

        # 2. Generate additional cases using LLM
        generated_cases = self._generate_llm_test_cases(state.problem_description, state.constraints)
        logger.info(f"Generated {len(generated_cases)} additional test cases using LLM.")

        all_test_cases = extracted_examples + generated_cases
        if not all_test_cases:
             logger.warning("No test cases were extracted or generated. Cannot perform local testing.")
             # Decide how to proceed: Skip testing? Fail? For now, skip and let submission handle it.
             state.test_results = [] # Indicate testing was attempted but no cases run
             return state

        state.test_cases = all_test_cases # Store the cases used

        # --- Execute Code Locally ---
        logger.info(f"Running code locally against {len(all_test_cases)} test cases...")
        try:
            # Use the imported run_python_code function
            # NOTE: This relies on the INSECURE placeholder in execution.py for now!
            execution_results = run_python_code(state.current_code, state.test_cases)
            state.test_results = execution_results
            passed_count = sum(1 for r in execution_results if r.get('passed'))
            failed_count = len(execution_results) - passed_count
            logger.info(f"Local execution complete. Passed: {passed_count}, Failed: {failed_count}")

        except Exception as e:
            logger.error(f"An error occurred during local code execution: {e}", exc_info=True)
            state.error_message = f"{self.name}: Exception during code execution - {e}"
            state.test_results = None # Indicate critical failure in execution
            # Let orchestrator handle this potential failure

        return state

    def _extract_example_test_cases(self, description: str) -> List[Dict[str, Any]]:
        """Extract example test cases from the problem description."""
        examples = []
        # Updated regex to better handle variations and multiline inputs/outputs
        pattern = re.compile(
            r"Input:\s*(.*?)\s*Output:\s*(.*?)(?=\s*Input:|\s*Example \d+:|\s*Constraints:|\Z)",
            re.IGNORECASE | re.DOTALL | re.MULTILINE
        )
        matches = pattern.findall(description)

        for i, (input_str, output_str) in enumerate(matches):
            input_str = input_str.strip()
            output_str = output_str.strip()
            logger.debug(f"Attempting to parse Example {i+1}: Input='{input_str}', Output='{output_str}'")
            try:
                # Parse input string
                input_args = self._parse_value(input_str)

                # Check if parsing resulted in the expected format (list of args)
                # For "nums = ..., target = ..." it should return a list [list, int]
                if isinstance(input_args, list):
                    # Parse output
                    parsed_output = self._parse_value(output_str)

                    examples.append({
                        "id": f"example_{i+1}",
                        "input": input_args, # Already a list from _parse_value
                        "expected_output": parsed_output
                    })
                    logger.debug(f"Successfully parsed Example {i+1}")
                else:
                    # Handle cases where _parse_value returns a single value or fails
                    # This might happen if the input format isn't "nums = ..., target = ..."
                    # or if it's just a single value like "5" or "[1,2,3]"
                    # For now, we'll log a warning if it wasn't the specific nums/target format
                    # but still try to parse the output and add it if input_args is not None
                    if input_args is not None:
                         parsed_output = self._parse_value(output_str)
                         examples.append({
                            "id": f"example_{i+1}",
                            "input": [input_args], # Wrap single input value in a list
                            "expected_output": parsed_output
                         })
                         logger.debug(f"Parsed Example {i+1} as single input value.")
                    else:
                        logger.warning(f"Could not determine input arguments structure for Example {i+1}: Input='{input_str}'")


            except Exception as e:
                logger.warning(f"Failed to parse example test case {i+1}: Input='{input_str}', Output='{output_str}'. Error: {str(e)}", exc_info=True) # Added exc_info
                continue

        return examples

    def _parse_value(self, value_str: str) -> Any:
        """Attempts to parse a string value into a Python object."""
        value_str = value_str.strip()
        logger.debug(f"Parsing value: '{value_str}'")

        # Handle "nums = [2,7,11,15], target = 9" format specifically
        nums_match = re.search(r"nums\s*=\s*(\[.*?\])", value_str, re.IGNORECASE | re.DOTALL)
        target_match = re.search(r"target\s*=\s*(-?\d+)", value_str, re.IGNORECASE) # Allow negative targets

        if nums_match and target_match:
            try:
                nums_str = nums_match.group(1)
                target_str = target_match.group(1)
                logger.debug(f"Found nums/target format: nums='{nums_str}', target='{target_str}'")
                nums = json.loads(nums_str)
                target = int(target_str)
                return [nums, target]  # Return as list of two elements
            except (json.JSONDecodeError, ValueError, IndexError) as e:
                logger.warning(f"Failed to parse extracted nums/target format: nums='{nums_match.group(1)}', target='{target_match.group(1)}'. Error: {e}")
                # Fall through to other parsing methods if this specific format fails unexpectedly

        # Handle standard JSON list format
        if value_str.startswith('[') and value_str.endswith(']'):
            try:
                # Attempt to parse as JSON list first
                return json.loads(value_str)
            except json.JSONDecodeError as e:
                logger.debug(f"String looks like list but failed JSON parsing: {e}. Treating as raw string.")
                # Fall through to treat as a plain string if JSON parsing fails

        # Handle standard JSON object format
        if value_str.startswith('{') and value_str.endswith('}'):
            try:
                return json.loads(value_str)
            except json.JSONDecodeError as e:
                logger.debug(f"String looks like dict but failed JSON parsing: {e}. Treating as raw string.")
                # Fall through

        # Handle quoted strings (remove quotes)
        if (value_str.startswith('"') and value_str.endswith('"')) or \
           (value_str.startswith("'") and value_str.endswith("'")):
            return value_str[1:-1]

        # Handle boolean and null values
        if value_str.lower() == 'true': return True
        if value_str.lower() == 'false': return False
        if value_str.lower() == 'null': return None

        # Handle numbers (int or float)
        try:
            return int(value_str)
        except ValueError:
            try:
                return float(value_str)
            except ValueError:
                # If all else fails, return the original string stripped of whitespace
                logger.debug(f"Could not parse '{value_str}' as JSON, bool, null, or number. Returning as string.")
                return value_str

    def _generate_llm_test_cases(self, description: str, constraints: List[str]) -> List[Dict[str, Any]]:
        """Generates additional test cases using the LLM."""
        prompt = f"""Based on the following LeetCode problem description and constraints, generate a diverse set of test cases in JSON format.

Problem Description:
---
{description}
---

Constraints:
---
{chr(10).join(f'- {c}' for c in constraints)}
---

Generate test cases covering:
- Edge cases (e.g., empty inputs, single element inputs, large inputs near limits, zero values, negative values if applicable).
- Cases based on constraints (e.g., values at the boundaries of specified ranges).
- Typical cases with varying input sizes.
- Cases that might challenge common incorrect assumptions.

Format the output as a JSON list of objects. Each object should have:
- "id": A unique identifier string (e.g., "edge_empty", "constraint_max_n").
- "input": A list representing the arguments to be passed to the solution function (matching the expected input structure).
- "expected_output": The expected result for the given input. Use `null` for JSON null.

Example JSON format:
[
  {{
    "id": "example_case_1",
    "input": [[2, 7, 11, 15], 9],
    "expected_output": [0, 1]
  }},
  {{
    "id": "edge_empty_list",
    "input": [[], 5],
    "expected_output": []
  }}
]

Provide *only* the JSON list. Do not include any other text or explanations.
"""
        try:
            response = generate_content(prompt)
            if not response:
                logger.warning("LLM test case generation returned empty response.")
                return []

            # Extract JSON part (sometimes LLMs wrap it in ```json ... ```)
            json_match = re.search(r"```json\s*([\s\S]+?)\s*```", response, re.IGNORECASE)
            if json_match:
                json_str = json_match.group(1)
            else:
                # Assume the whole response might be JSON if not wrapped
                json_str = response.strip()

            # Ensure the string looks like a list before parsing
            if not json_str.startswith('[') or not json_str.endswith(']'):
                 logger.error(f"LLM response for test cases is not a JSON list: {json_str[:100]}...")
                 return []

            test_cases = json.loads(json_str)
            if isinstance(test_cases, list):
                # Basic validation of structure
                valid_cases = []
                for i, case in enumerate(test_cases):
                     if isinstance(case, dict) and "id" in case and "input" in case and "expected_output" in case and isinstance(case["input"], list):
                         valid_cases.append(case)
                     else:
                         logger.warning(f"Generated test case {i} has invalid format: {case}")
                return valid_cases
            else:
                logger.error(f"LLM response for test cases did not parse into a list: {test_cases}")
                return []
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response from LLM for test cases: {e}\nResponse:\n{response[:500]}...")
            return []
        except Exception as e:
            logger.error(f"An error occurred during LLM test case generation: {e}", exc_info=True)
            return []

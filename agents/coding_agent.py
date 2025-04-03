import logging
import re
from agents.base_agent import BaseAgent
from core.state import WorkflowState
from typing import Optional, List
from utils.llm_api import generate_content # Use the centralized API call

logger = logging.getLogger(__name__)

class CodingAgent(BaseAgent):
    """
    Agent responsible for generating Python code based on the problem description,
    plan, constraints, and potentially previous attempts.
    """
    def __init__(self):
        super().__init__(name="Coding Agent")

    def execute(self, state: WorkflowState) -> WorkflowState:
        """
        Generates Python code using an LLM based on the current state.

        Args:
            state: The current workflow state, containing problem description,
                   plan, constraints, starting_code, and optionally debug_analysis.

        Returns:
            The updated workflow state with 'current_code' populated or updated.
            Sets error message if code generation fails critically.
        """
        logger.info(f"Executing {self.name} for problem: {state.problem_title}")

        # --- Validate Inputs ---
        if not state.problem_description:
            logger.error("Problem description is missing.")
            state.error_message = f"{self.name}: Problem description missing."
            state.status = "Failed"
            return state
        if not state.plan:
            logger.warning("Plan is missing, proceeding with description and constraints only.")
            # Allow proceeding without a plan, but it might affect quality
        if not state.starting_code:
             logger.warning("Starting code template is missing. LLM might not generate the correct structure.")
             # Allow proceeding, but flag the risk

        # --- Construct Prompt ---
        prompt = self._create_coding_prompt(
            state.problem_description,
            state.plan,
            state.constraints,
            state.starting_code, # Pass starting code
            state.debug_analysis,
            state.current_code if state.debug_analysis else None # Pass current code only if debugging
        )

        # --- Generate Code ---
        try:
            llm_response = generate_content(prompt)

            if not llm_response:
                logger.error("LLM code generation returned an empty result.")
                state.error_message = f"{self.name}: LLM failed to generate code."
                # Keep previous code? Or set to None? Let's keep previous for now.
                return state

            # --- Extract Code ---
            extracted_code = self._extract_python_code(llm_response)

            if extracted_code:
                logger.info("Successfully generated and extracted Python code.")
                state.current_code = extracted_code
                state.error_message = None # Clear previous errors if new code is generated
            else:
                logger.error("Failed to extract Python code from the LLM response.")
                state.error_message = f"{self.name}: Failed to extract code from LLM response."
                # Keep previous code if extraction fails

        except Exception as e:
            logger.error(f"An error occurred during code generation: {e}", exc_info=True)
            state.error_message = f"{self.name}: Exception during code generation - {e}"
            # Keep previous code on exception

        return state

    def _create_coding_prompt(
        self,
        description: str,
        plan: Optional[str],
        constraints: Optional[list[str]],
        starting_code: Optional[str], # Added parameter
        debug_analysis: Optional[str] = None,
        previous_code: Optional[str] = None
    ) -> str:
        """Creates the prompt for the LLM to generate Python code."""

        prompt_lines = [
            "You are an expert Python programmer tasked with solving a LeetCode problem.",
            "Analyze the problem description, plan (if provided), constraints, and starting code template.",
        ]

        if debug_analysis:
            prompt_lines.extend([
                "\nIMPORTANT: You are revising code based on previous errors.",
                "Debugging Analysis from previous attempt:",
                "---",
                debug_analysis,
                "---",
                "Previous Code with bugs:",
                "```python",
                previous_code or "# No previous code provided",
                "```",
                "\nFocus on applying the suggested fixes from the debugging analysis to the previous code.",
                "Ensure your new code directly addresses the identified issues.",
            ])
        else:
            prompt_lines.append("\nGenerate a complete Python solution based on the following details:")

        prompt_lines.extend([
            "\nProblem Description:",
            "---",
            description,
            "---",
        ])

        if plan:
            prompt_lines.extend([
                "\nPlan/Pseudocode:",
                "---",
                plan,
                "---",
            ])

        if constraints:
            prompt_lines.extend([
                "\nConstraints:",
                "---",
                "\n".join(f"- {c}" for c in constraints),
                "---",
            ])

        # Include the starting code template
        if starting_code:
            prompt_lines.extend([
                "\nStarting Code Template (Your solution MUST use this structure):",
                "```python",
                starting_code,
                "```",
                "---",
            ])
        else:
             prompt_lines.append("\nWarning: No starting code template provided. Ensure your solution defines the necessary class and method(s).")


        prompt_lines.extend([
            "\nInstructions:",
            "- Write a complete Python code solution.",
            "- Adhere strictly to the class and method structure provided in the 'Starting Code Template' if available.",
            "- Implement the logic described in the plan or derived from the description.",
            "- Consider the constraints provided.",
            "- Optimize for clarity, efficiency (time and space complexity), and correctness.",
            "- Include necessary imports.",
            "- Provide ONLY the final Python code within a single markdown code block (```python ... ```).",
            "- Do NOT include explanations, comments outside the code, or any text before or after the code block.",
        ])

        return "\n".join(prompt_lines)

    def _extract_python_code(self, text: str) -> Optional[str]:
        """Extracts Python code from a markdown code block."""
        # Use re.DOTALL to make '.' match newlines
        match = re.search(r"```python\s*([\s\S]+?)\s*```", text, re.IGNORECASE | re.DOTALL)
        if match:
            code = match.group(1).strip()
            # Basic check to see if it's not just whitespace or comments
            if any(line.strip() and not line.strip().startswith('#') for line in code.splitlines()):
                return code
            else:
                logger.warning("Extracted code block appears empty or contains only comments.")
                return None
        else:
            # Fallback: Maybe the LLM just returned raw code? (Less ideal)
            # Be cautious with this, as it might grab non-code text.
            # Only use if the response seems *very likely* to be just code.
            # Let's disable this fallback for now to prefer explicit blocks.
            # if "class Solution:" in text or "def " in text: # Basic heuristic
            #    logger.warning("No markdown code block found, attempting to treat entire response as code.")
            #    return text.strip()
            return None

import logging
import re
from agents.base_agent import BaseAgent
from core.state import WorkflowState
from utils.llm_api import generate_content
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

class OptimizationAgent(BaseAgent):
    """
    Agent responsible for analyzing code for performance improvements
    (time/space complexity) and suggesting or providing optimized code.
    """
    def __init__(self):
        super().__init__(name="Optimization Agent")

    def execute(self, state: WorkflowState) -> WorkflowState:
        """
        Analyzes the current code for optimization opportunities using an LLM.

        Args:
            state: The current workflow state, must contain 'current_code',
                   'problem_description', and 'constraints'. Assumes the
                   'current_code' has passed basic functional tests.

        Returns:
            The updated workflow state. 'optimization_analysis' will be populated.
            'current_code' might be updated if the LLM provides optimized code.
            Sets error message if optimization analysis fails.
        """
        logger.info(f"Executing {self.name} for problem: {state.problem_title}")

        # --- Validate Inputs ---
        if not state.current_code:
            logger.error("Current code is missing for optimization analysis.")
            state.error_message = f"{self.name}: Current code missing."
            state.status = "Failed" # Cannot optimize without code
            return state
        if not state.problem_description:
            # Less critical than for other agents, but helpful for context
            logger.warning("Problem description is missing. Optimization context may be limited.")
        if not state.constraints:
            logger.warning("Constraints are missing. Optimization context may be limited.")


        # --- Construct Prompt ---
        prompt = self._create_optimization_prompt(
            state.problem_description,
            state.constraints,
            state.current_code
        )

        # --- Get Optimization Analysis from LLM ---
        try:
            llm_response = generate_content(prompt)

            if not llm_response:
                logger.error("LLM optimization analysis returned an empty result.")
                state.error_message = f"{self.name}: LLM failed to provide optimization analysis."
                # Keep current code, let orchestrator decide how to proceed (e.g., submit anyway)
                return state

            # --- Parse Response and Update State ---
            analysis, optimized_code = self._parse_optimization_response(llm_response)

            state.optimization_analysis = analysis or "LLM did not provide specific optimization analysis."
            logger.info(f"Optimization analysis received:\n{state.optimization_analysis}")

            if optimized_code and optimized_code != state.current_code:
                logger.info("LLM provided potentially optimized code. Updating current code.")
                state.current_code = optimized_code
                # Indicate that code was updated so orchestrator might re-test
                state.status = "Testing" # Go back to testing after optimization
            else:
                logger.info("LLM did not provide new optimized code or code is unchanged. Proceeding.")
                # Keep previous code, move on (orchestrator will handle next state)

        except Exception as e:
            logger.error(f"An error occurred during optimization analysis: {e}", exc_info=True)
            state.error_message = f"{self.name}: Exception during optimization - {e}"
            # Keep previous state, let orchestrator handle

        return state

    def _create_optimization_prompt(
        self,
        description: Optional[str],
        constraints: Optional[list],
        code: str
    ) -> str:
        """Creates the prompt for the LLM to analyze and optimize the code."""

        prompt_lines = [
            "You are an expert Python programmer specializing in algorithm optimization.",
            "The following Python code solves a LeetCode problem and has passed basic functional tests.",
            "Analyze the code for potential performance improvements, focusing on time and space complexity.",
            "Consider the problem description and constraints if provided.",
            "\nProblem Description:",
            "---",
            description or "Not provided.",
            "---",
            "\nConstraints:",
            "---",
            "\n".join(f"- {c}" for c in constraints) if constraints else "Not provided.",
            "---",
            "\nCurrent Code:",
            "---",
            "```python",
            code,
            "```",
            "---",
            "\nPlease perform the following:",
            "1. **Analyze Complexity:** Determine the time and space complexity of the current solution. Explain your reasoning.",
            "2. **Identify Bottlenecks:** Point out any specific parts of the code that are inefficient or could be improved.",
            "3. **Suggest Optimizations:** Describe potential optimizations (e.g., using different data structures, algorithms, or techniques). Explain the expected impact on complexity.",
            "4. **(Optional but preferred) Provide Optimized Code:** If significant improvements are possible, provide the complete, optimized Python code within a single markdown code block (```python ... ```). Ensure it maintains the original functionality and class/method structure.",
            "\nFormat your response clearly. Start with the analysis, then provide the optimized code block if applicable.",
        ]

        return "\n".join(prompt_lines)

    def _parse_optimization_response(self, text: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Parses the LLM's optimization response to extract the analysis
        and the optimized code block (if provided).
        (Similar structure to the debugging parser)
        """
        analysis = None
        optimized_code = None

        # Try to extract optimized code first
        code_match = re.search(r"```python\s*([\s\S]+?)\s*```", text, re.IGNORECASE)
        if code_match:
            optimized_code = code_match.group(1).strip()
            # Assume the text before the code block is the analysis
            analysis = text[:code_match.start()].strip()
        else:
            # If no code block, assume the entire response is the analysis
            analysis = text.strip()

        # Basic cleanup of analysis text (optional, similar to debugger)
        if analysis:
             analysis_lines = analysis.split('\n')
             if analysis_lines and ("here's the analysis" in analysis_lines[0].lower()): analysis_lines.pop(0)
             if analysis_lines and ("let me know if" in analysis_lines[-1].lower()): analysis_lines.pop()
             analysis = "\n".join(analysis_lines).strip()

        return analysis, optimized_code
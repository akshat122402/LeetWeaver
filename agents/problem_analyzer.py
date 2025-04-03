import logging
from agents.base_agent import BaseAgent
from core.state import WorkflowState
from utils.llm_api import generate_content # Use the centralized API call

logger = logging.getLogger(__name__)

class ProblemAnalyzerAgent(BaseAgent):
    """
    Agent responsible for analyzing the problem description, identifying constraints,
    suggesting algorithms/data structures, and creating a high-level plan.
    """
    def __init__(self):
        super().__init__(name="Problem Analyzer & Planner")

    def execute(self, state: WorkflowState) -> WorkflowState:
        """
        Analyzes the problem description using an LLM.

        Args:
            state: The current workflow state, must contain 'problem_description'.

        Returns:
            The updated workflow state with 'plan' and 'constraints' fields populated.
            If analysis fails, an error message might be set in the state.
        """
        logger.info(f"Executing {self.name} for problem: {state.problem_title}")

        if not state.problem_description:
            logger.error("Problem description is missing in the state.")
            state.error_message = f"{self.name}: Problem description is missing."
            state.status = "Failed"
            return state

        prompt = self._create_analysis_prompt(state.problem_description)

        try:
            analysis_result = generate_content(prompt)

            if not analysis_result:
                logger.error("LLM analysis returned an empty result.")
                state.error_message = f"{self.name}: LLM analysis failed to produce a result."
                # Don't immediately fail the whole workflow, maybe coding agent can proceed without plan?
                # Or set status to Failed here? For now, let orchestrator decide based on empty plan.
                return state

            # Attempt to parse the result (assuming a structured output format)
            # This parsing logic needs to be robust based on the prompt's instructions
            state = self._parse_analysis_result(analysis_result, state)
            logger.info(f"Analysis complete. Plan generated: {bool(state.plan)}. Constraints identified: {len(state.constraints)}")

        except Exception as e:
            logger.error(f"An error occurred during problem analysis: {e}", exc_info=True)
            state.error_message = f"{self.name}: Exception during analysis - {e}"
            # Decide if this is fatal for the workflow
            # state.status = "Failed" # Optional: Mark as failed immediately

        return state

    def _create_analysis_prompt(self, description: str) -> str:
        """Creates the prompt for the LLM to analyze the problem."""
        # This prompt guides the LLM to provide structured output.
        # Adjust the structure (e.g., using JSON, XML, or specific headings) as needed.
        prompt = f"""Analyze the following LeetCode problem description:

Problem Description:
---
{description}
---

Perform the following tasks:
1.  **Identify Constraints:** List all explicit and implicit constraints mentioned (e.g., input size limits, value ranges, time/space complexity requirements). If none are obvious, state that.
2.  **Suggest Algorithms/Data Structures:** Based on the problem type and constraints, suggest 1-2 suitable algorithms and/or data structures. Briefly explain why they are appropriate.
3.  **Create Plan:** Outline a high-level step-by-step plan or pseudocode to implement the solution using one of the suggested approaches. Focus on the core logic.

Format the output clearly using the following headings:

## Constraints
- [Constraint 1]
- [Constraint 2]
...

## Suggested Approach
- **Algorithm/Data Structure:** [Name]
  - **Reasoning:** [Brief explanation]
- **Algorithm/Data Structure:** [Name (Optional)]
  - **Reasoning:** [Brief explanation (Optional)]

## Plan/Pseudocode
1. [Step 1]
2. [Step 2]
...

Provide only the analysis based on the description. Do not write the full code solution yet.
"""
        return prompt

    def _parse_analysis_result(self, result: str, state: WorkflowState) -> WorkflowState:
        """Parses the LLM's analysis result and updates the state."""
        # Basic parsing based on headings. More robust parsing (regex, dedicated parser) might be needed.
        try:
            constraints_section = result.split("## Constraints")[1].split("## Suggested Approach")[0].strip()
            plan_section = result.split("## Plan/Pseudocode")[1].strip()

            # Extract constraints (simple line splitting)
            constraints = [line.strip('- ').strip() for line in constraints_section.split('\n') if line.strip() and line.strip().startswith('-')]
            state.constraints = constraints if constraints else ["No specific constraints identified."]

            # Store the full plan/pseudocode section
            state.plan = plan_section

            # Optionally, parse the suggested approach as well if needed later
            # suggested_approach = result.split("## Suggested Approach")[1].split("## Plan/Pseudocode")[0].strip()
            # state.suggested_approach = suggested_approach # Add field to WorkflowState if needed

        except IndexError:
            logger.warning("Could not parse the analysis result using standard headings. Storing raw result as plan.")
            state.plan = result # Store the raw result if parsing fails
            state.constraints = ["Parsing failed."]
        except Exception as e:
             logger.error(f"Error parsing analysis result: {e}", exc_info=True)
             state.plan = result # Store raw result on error
             state.constraints = ["Parsing error."]

        return state

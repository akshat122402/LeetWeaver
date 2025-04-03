from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)

class BaseAgent(ABC):
    """Abstract base class for all agents in the LeetWeaver system."""

    def __init__(self, name: str):
        self.name = name
        logger.info(f"Initializing agent: {self.name}")

    @abstractmethod
    def execute(self, state: dict) -> dict:
        """
        Executes the agent's specific task.

        Args:
            state: The current workflow state dictionary containing relevant information
                   (e.g., problem description, code, test results).

        Returns:
            An updated state dictionary with the results of the agent's execution
            (e.g., generated code, test analysis, optimization suggestions).
            Should return the input state potentially modified, or a new dictionary.
        """
        pass

    def __str__(self):
        return f"Agent({self.name})" 
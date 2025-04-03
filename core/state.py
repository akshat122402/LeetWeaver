from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

@dataclass
class WorkflowState:
    """Holds the state of the problem-solving process."""
    problem_url: Optional[str] = None
    problem_title: Optional[str] = None
    problem_description: Optional[str] = None
    starting_code: Optional[str] = None
    plan: Optional[str] = None # Output from Planner Agent
    constraints: List[str] = field(default_factory=list) # Output from Planner Agent
    current_code: Optional[str] = None
    test_cases: List[Dict[str, Any]] = field(default_factory=list) # From Tester Agent (examples + generated)
    test_results: Optional[List[Dict[str, Any]]] = None # Output from local execution or LeetCode run
    submission_results: Optional[Dict[str, Any]] = None # Output from LeetCode submission
    debug_analysis: Optional[str] = None # Output from Debugger Agent
    optimization_analysis: Optional[str] = None # Output from Optimizer Agent
    iteration: int = 0
    max_iterations: int = 30 # Default value is 5 HERE
    status: str = "Initialized" # e.g., Planning, Coding, Testing, Debugging, Optimizing, Submitting, Success, Failed
    error_message: Optional[str] = None # General error message if workflow fails

    # You can add more fields as needed, e.g., complexity analysis, benchmark results etc. 
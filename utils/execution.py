import subprocess
import sys
import logging
import tempfile
import os
import json
from typing import List, Dict, Any, Tuple

logger = logging.getLogger(__name__)

# Timeout for code execution in seconds
EXECUTION_TIMEOUT = 10

def run_python_code(code: str, test_cases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Execute Python code against test cases."""
    results = []
    
    try:
        # Create namespace and execute the solution code
        namespace = {}
        exec(code, namespace)
        Solution = namespace['Solution']
        solution_instance = Solution()
        
        # Run each test case
        for test_case in test_cases:
            try:
                # Unpack input arguments - assuming first element is nums list, second is target
                input_args = test_case['input']
                if len(input_args) != 2:
                    raise ValueError(f"Expected 2 input arguments (nums, target), got {len(input_args)}")
                
                nums, target = input_args
                
                # Call the solution method
                actual_output = solution_instance.twoSum(nums, target)
                expected_output = test_case['expected_output']
                
                # Compare results
                passed = actual_output == expected_output
                
                results.append({
                    'id': test_case['id'],
                    'input': input_args,
                    'expected_output': expected_output,
                    'actual_output': actual_output,
                    'passed': passed,
                    'error': None
                })
                
            except Exception as e:
                results.append({
                    'id': test_case['id'],
                    'input': test_case['input'],
                    'expected_output': test_case['expected_output'],
                    'actual_output': None,
                    'passed': False,
                    'error': str(e)
                })
                
    except Exception as e:
        # Handle global execution errors
        logger.error(f"Error executing solution code: {e}")
        results.append({
            'id': 'execution_error',
            'input': None,
            'expected_output': None,
            'actual_output': None,
            'passed': False,
            'error': f"Failed to execute solution: {str(e)}"
        })
    
    return results

# Example usage (optional)
if __name__ == "__main__":
    sample_code = """
import math

class Solution:
    def solve(self, n):
        if n < 0:
            raise ValueError("Input must be non-negative")
        return math.sqrt(n)
"""
    sample_test_cases = [
        {'input': [4], 'expected_output': 2.0},
        {'input': [9], 'expected_output': 3.0},
        {'input': [2], 'expected_output': 1.4142135623730951}, # Approximate
        {'input': [-1], 'expected_output': None} # Expecting an error
    ]

    print("Running sample code execution (INSECURE PLACEHOLDER)...")
    test_results = run_python_code(sample_code, sample_test_cases)
    print("\nResults:")
    import pprint
    pprint.pprint(test_results) 
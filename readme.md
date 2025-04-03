# LeetWeaver 🤖

LeetWeaver is an experimental AI-powered system designed to automatically solve LeetCode programming problems. It utilizes a multi-agent architecture, leveraging Google's Gemini language models to understand problem descriptions, devise plans, write code, generate tests, debug errors, and interact with the LeetCode website.

**Disclaimer:** This project is for educational and experimental purposes. Automating LeetCode submissions may violate their terms of service. Use responsibly and primarily for learning about AI agent workflows and LLM integration. The code execution component currently uses an insecure method and should **not** be run in untrusted environments or with untrusted code.

## Overview

The goal of LeetWeaver is to simulate a programmer's workflow when tackling a LeetCode problem:

1.  **Analyze:** Understand the problem statement and constraints.
2.  **Plan:** Devise a high-level algorithm or approach.
3.  **Code:** Implement the solution in Python.
4.  **Test:** Run the code against example and generated test cases locally.
5.  **Debug:** If tests fail or submission is rejected, analyze the errors and attempt to fix the code.
6.  **Submit:** Submit the code to LeetCode and check the result.

## Features

*   **Multi-Agent System:** Different agents specialize in specific tasks (planning, coding, testing, debugging).
*   **LLM Integration:** Uses the Gemini API (via `google-genai`) for natural language understanding, code generation, and analysis.
*   **LeetCode Interaction:** Uses Selenium (`undetected-chromedriver`) to log in, fetch problem details, input code, and submit solutions.
*   **Local Testing:** Generates test cases (using LLM) and executes the code locally before submission (using `subprocess` - **currently insecure**).
*   **Iterative Refinement:** Employs a loop where code is tested and debugged iteratively until it passes or reaches a maximum iteration limit.

## Architecture

The system is orchestrated by the `Orchestrator` (`core/orchestrator.py`), which manages the flow between different agents:

*   **`ProblemAnalyzerAgent`:** Analyzes the description, identifies constraints, and creates a plan.
*   **`CodingAgent`:** Generates Python code based on the plan, description, and previous attempts/debug info.
*   **`TestingAgent`:** Extracts/generates test cases and runs the code locally using `utils/execution.py`.
*   **`DebuggingAgent`:** Analyzes failed test results or submission errors and asks the LLM for fixes.
*   **(Future Agents):** `OptimizationAgent`, `BenchmarkAgent`.

Core components:
*   **`LeetCodeInterface`:** Handles Selenium-based web interactions.
*   **`WorkflowState`:** A dataclass holding the state passed between agents.
*   **`llm_api`:** Centralized utility for interacting with the Gemini API.
*   **`execution`:** Utility for running Python code (currently insecure).

## Setup

**Prerequisites:**

*   Python 3.8+
*   `pip` (Python package installer)
*   Google Chrome or Chromium browser installed (for Selenium/`undetected-chromedriver`)

**Installation:**

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your-username/leetweaver.git # Replace with your repo URL if applicable
    cd leetweaver
    ```

2.  **Create a virtual environment (recommended):**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows use `venv\Scripts\activate`
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Set up environment variables:**
    *   Copy the `.env.example` file (if provided) or create a new file named `.env` in the project root.
    *   Add your credentials and API key:
        ```dotenv:.env
        # LeetCode Credentials
        LEETCODE_USERNAME="your_leetcode_username"
        LEETCODE_PASSWORD="your_leetcode_password"

        # Gemini API Key (https://aistudio.google.com/app/apikey)
        GEMINI_API_KEY="your_gemini_api_key"

        # Optional: Gemini Configuration
        GEMINI_MODEL="gemini-1.5-pro-latest" # Or another suitable model like gemini-1.5-flash-latest
        GEMINI_RPM=60 # Rate limit (requests per minute for the API)

        # Optional: Orchestrator Configuration
        MAX_ITERATIONS=5 # Max attempts per problem
        ```
    *   **Important:** Ensure your LeetCode account does **not** have Two-Factor Authentication (2FA) enabled, as the current Selenium script cannot handle it. Consider using a dedicated account for testing if necessary.

## Usage

Run the main script from the project root directory, providing the URL of the LeetCode problem you want to solve:

```bash
python main.py "https://leetcode.com/problems/two-sum/"
```

Replace the URL with the desired problem URL. The script will log the process, including agent actions, LLM interactions (prompts/responses can be enabled via logging level), test results, and submission status.

## Limitations & Future Work

*   **Security:** The `utils/execution.py` module uses `subprocess` to run generated code, which is **highly insecure**. A proper sandboxed environment (e.g., using Docker containers, `nsjail`, or specialized libraries) is crucial for running untrusted code safely.
*   **LeetCode Interaction Robustness:** Web scraping is fragile. Changes to LeetCode's website structure can break the `LeetCodeInterface`. Error handling and element selection need continuous refinement. 2FA is not supported.
*   **Test Case Parsing/Generation:** Extracting examples and generating comprehensive, accurate test cases (especially parsing complex input/output formats) is challenging and needs improvement.
*   **Debugging Complexity:** The current debugging agent is basic. Handling complex logical errors or understanding subtle submission feedback requires more sophisticated analysis.
*   **LLM Reliability:** LLM responses can vary. Code generation might be incorrect, incomplete, or fail to follow instructions. Parsing LLM output requires robust error handling.
*   **Missing Agents:** The `OptimizationAgent` and `BenchmarkAgent` are not yet implemented.
*   **Token Limits:** Complex problems or long conversations might exceed LLM context window or token limits.

## Contributing

Contributions are welcome! Please feel free to open issues or submit pull requests. Focus areas include improving security, web interaction robustness, agent capabilities, and testing.

## License

(Optional: Add a license, e.g., MIT License)

```
MIT License

Copyright (c) [Year] [Your Name/Organization]

Permission is hereby granted, free of charge, to any person obtaining a copy
... (rest of MIT license text) ...

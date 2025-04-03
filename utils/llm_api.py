import os
from google import genai
from google.genai import types
from ratelimit import limits, sleep_and_retry
from dotenv import load_dotenv
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Constants from environment variables or defaults
API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-1.5-pro-latest")
REQUESTS_PER_MINUTE = int(os.getenv("GEMINI_RPM", 60))
TEMPERATURE = 0 # Keep deterministic for coding tasks initially

if not API_KEY:
    raise ValueError("GEMINI_API_KEY not found in environment variables.")

# Configure the google-genai client
try:
    client = genai.Client(api_key=API_KEY)
    logger.info("Google GenAI Client initialized.")
except Exception as e:
    logger.error(f"Failed to initialize Google GenAI Client: {e}", exc_info=True)
    raise ConnectionError("Failed to initialize Google GenAI Client.") from e

# Configuration object for generate_content
generation_config = types.GenerateContentConfig(
    temperature=TEMPERATURE
    # Add other config like max_output_tokens if needed, e.g., max_output_tokens=2048
)


# Tool configuration (optional, example for future use like code execution)
# Based on docs, CodeExecution is a tool type, might need specific setup
# code_execution_tool = types.Tool(code_execution=types.ToolCodeExecution())
# tool_config = types.ToolConfig(...) # If needed

@sleep_and_retry
@limits(calls=REQUESTS_PER_MINUTE, period=60)
def generate_content(prompt: str) -> str:
    """
    Sends a prompt to the configured Gemini model using google-genai client
    and returns the text response.

    Args:
        prompt: The prompt string to send to the model.

    Returns:
        The generated text content, or an empty string if an error occurs
        or no text is returned.
    """
    logger.info(f"Sending prompt to Gemini via google-genai ({MODEL_NAME})...")
    # logger.debug(f"Prompt content:\n{prompt}") # Uncomment for debugging prompts
    try:
        # Use client.models.generate_content
        response = client.models.generate_content(
            model=MODEL_NAME, # Pass model name here
            contents=prompt,  # Pass the prompt string directly to contents
            config=generation_config # Pass the generation config
            # tools=[code_execution_tool], # Example if using tools
            # tool_config=tool_config,     # Example if using tools
        )

        # Accessing the text safely using response.text
        # google-genai typically returns the main text content in response.text
        if hasattr(response, 'text') and response.text:
            generated_text = response.text
            logger.info("Received response from Gemini.")
            # logger.debug(f"Response content:\n{generated_text}") # Uncomment for debugging responses
            return generated_text
        else:
            # Handle cases where the response might be blocked or empty
            logger.warning("Gemini response was empty or blocked.")
            # Log safety feedback if available (structure might differ slightly)
            if hasattr(response, 'prompt_feedback') and hasattr(response.prompt_feedback, 'block_reason') and response.prompt_feedback.block_reason:
                 logger.warning(f"Prompt blocked due to: {response.prompt_feedback.block_reason}")
                 if hasattr(response.prompt_feedback, 'safety_ratings') and response.prompt_feedback.safety_ratings:
                     logger.warning(f"Safety Ratings: {response.prompt_feedback.safety_ratings}")

            # Check candidates for finish reason (structure might differ slightly)
            if hasattr(response, 'candidates') and response.candidates:
                 # Assuming the first candidate is relevant
                 candidate = response.candidates[0]
                 if hasattr(candidate, 'finish_reason') and candidate.finish_reason.name != "STOP":
                     logger.warning(f"Generation finished unexpectedly: {candidate.finish_reason.name}")
                     if hasattr(candidate, 'safety_ratings') and candidate.safety_ratings:
                         logger.warning(f"Candidate Safety Ratings: {candidate.safety_ratings}")

            return ""

    except Exception as e:
        logger.error(f"Error calling Gemini API via google-genai: {e}", exc_info=True)
        # Consider more specific error handling based on google.api_core.exceptions if needed
        return ""

# Example usage (optional, for testing this module directly)
if __name__ == "__main__":
    test_prompt = "Explain the concept of recursion in one sentence."
    print(f"Testing google-genai API with prompt: '{test_prompt}'")
    response_text = generate_content(test_prompt)
    if response_text:
        print("\nResponse:")
        print(response_text)
    else:
        print("\nFailed to get response from Gemini.") 
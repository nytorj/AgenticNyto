# prompts.py (root)

# This file is for initial structuring and will be (or has been partially)
# refactored into lib/prompts.py.
# For now, we directly import the necessary prompts from lib.prompts.

from lib.prompts import (
    PLANNING_AGENT_PROMPT,
    SOFTWARE_ENGINEER_AGENT_PROMPT,
    CODING_AGENT_PROMPT,
    SENIOR_ENGINEER_AGENT_PROMPT,
    REFORMAT_DESCRIPTION_AGENT_PROMPT, # Included for completeness, though not strictly "old"
    DOCUMENTATION_AGENT_PROMPT       # Included for completeness
)

# You can also add a small test or print statement here if needed,
# for example, to ensure imports are working.
if __name__ == '__main__':
    print("--- Root prompts.py ---")
    print("Testing import of PLANNING_AGENT_PROMPT (first 30 chars):")
    print(PLANNING_AGENT_PROMPT[:30] + "...")
    print("\nTesting import of REFORMAT_DESCRIPTION_AGENT_PROMPT (first 30 chars):")
    print(REFORMAT_DESCRIPTION_AGENT_PROMPT[:30] + "...")

# lib/tools.py
import os
import subprocess
import tempfile
import json
from typing import Optional, List # Added List

# Import CodeReviewResult from lib.models
# To handle local execution of this script if __name__ == '__main__':
import sys
if __name__ == '__main__':
    # Add project root to sys.path to allow direct execution of this script for testing
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
from lib.models import CodeReviewResult

# --- File I/O Helpers (already implemented) ---
def write_code_to_file(file_path: str, code: str) -> bool:
    try:
        parent_dir = os.path.dirname(file_path)
        if parent_dir and not os.path.exists(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(code)
        return True
    except IOError as e:
        # Using print for now, consider logging for more robust applications
        print(f"Error writing file {file_path}: {e}")
        return False
    except Exception as e:
        print(f"An unexpected error occurred in write_code_to_file: {e}")
        return False

def create_docs_dir_if_not_exists(docs_dir: str = "docs") -> bool:
    try:
        if not os.path.exists(docs_dir):
            os.makedirs(docs_dir, exist_ok=True)
        return True
    except OSError as e:
        print(f"Error creating directory {docs_dir}: {e}")
        return False
    except Exception as e:
        print(f"An unexpected error occurred in create_docs_dir_if_not_exists: {e}")
        return False

import shutil # Import shutil for which()

# --- Code Verification ---
def verify_code(code: str, file_path: str, language: str = "python") -> CodeReviewResult:
    """
    Verifies the given code using linters and formatters.
    Currently supports Python with Ruff and Black.
    - Saves code to a temporary file.
    - Runs Ruff for linting.
    - Runs Black for formatting checks.
    - Parses results into a CodeReviewResult.
    """
    if language.lower() != "python":
        return CodeReviewResult(passed=True, feedback=f"Verification for {language} not implemented. Assuming pass.")

    passed = True
    feedback_messages: List[str] = []
    revised_code_suggestion = None # Black might suggest changes

    # Determine file extension for temp file
    # file_path often gives a hint, but language param is more direct for temp file.
    suffix = ".py" # Default for python

    with tempfile.NamedTemporaryFile(mode='w+', suffix=suffix, delete=False, encoding='utf-8') as tmp_file:
        tmp_file_path = tmp_file.name
        tmp_file.write(code)

    original_file_dir = os.path.dirname(file_path) or '.' # Get directory of original file path for Ruff context
    # Ensure Ruff can find pyproject.toml if it's in a parent directory
    # Ruff automatically searches upwards for pyproject.toml, so this might not be strictly needed
    # unless running Ruff from a very different CWD.

    try:
        # 1. Run Ruff
        # Ruff needs to be run in an environment where it can find configurations like pyproject.toml if they exist.
        # Using `cwd=original_file_dir` might help if Ruff's config is relative to the file's location.
        # However, Ruff typically searches upwards for pyproject.toml from the linted file's location.
        # For simplicity, let's assume ruff is globally configured or config is in repo root.
        # If Ruff isn't installed, this will raise FileNotFoundError.
        # Adding --force-exclude to ensure it respects .gitignore, etc. if run from a general temp dir.
        # Ruff's JSON output is a list of issues.
        ruff_executable = shutil.which("ruff")
        if not ruff_executable:
            feedback_messages.append("Ruff executable not found in PATH. Skipping Ruff linting.")
        else:
            ruff_command = [ruff_executable, "check", "--output-format=json", "--force-exclude", tmp_file_path]
            try: # For subprocess.run
                ruff_process = subprocess.run(ruff_command, capture_output=True, text=True, check=False)
                ruff_issues = []
                if ruff_process.stdout.strip():
                    try:
                        ruff_issues = json.loads(ruff_process.stdout)
                    except json.JSONDecodeError:
                        feedback_messages.append(f"Ruff: Could not parse JSON output: {ruff_process.stdout[:200]}")
                        passed = False

                if ruff_issues:
                    passed = False
                    feedback_messages.append("Ruff found issues:")
                    for issue in ruff_issues[:5]:
                        feedback_messages.append(
                            f"- {issue.get('code')}: {issue.get('message')} (line {issue.get('location',{}).get('row')})"
                        )
                    if len(ruff_issues) > 5:
                        feedback_messages.append(f"  ...and {len(ruff_issues) - 5} more issues.")

                if ruff_process.stderr.strip():
                    feedback_messages.append(f"Ruff stderr: {ruff_process.stderr.strip()}")
            except FileNotFoundError: # Specific to subprocess.run if executable path is somehow wrong despite shutil.which
                feedback_messages.append(f"Ruff executable at '{ruff_executable}' not found when trying to run. Skipping Ruff.")
            except Exception as e: # Catch other errors during ruff execution
                feedback_messages.append(f"Error running Ruff: {e}")
                passed = False

        # 2. Run Black
        black_executable = shutil.which("black")
        if not black_executable:
            feedback_messages.append("Black executable not found in PATH. Skipping Black formatting check.")
        else:
            black_command = [black_executable, "--check", "--diff", tmp_file_path]
            try: # For subprocess.run
                black_process = subprocess.run(black_command, capture_output=True, text=True, check=False)

                if black_process.returncode == 1:
                    passed = False
                    feedback_messages.append("Black: Code needs formatting.")
                    diff_output = black_process.stderr or black_process.stdout
                    if diff_output.strip():
                        feedback_messages.append("Black diff:\n" + diff_output.strip()[:500] + "...")
                elif black_process.returncode != 0:
                    passed = False
                    feedback_messages.append(f"Black: Error during check (exit code {black_process.returncode}).")
                    if black_process.stderr.strip():
                        feedback_messages.append(f"Black stderr: {black_process.stderr.strip()}")
            except FileNotFoundError: # Specific to subprocess.run
                feedback_messages.append(f"Black executable at '{black_executable}' not found when trying to run. Skipping Black.")
            except Exception as e: # Catch other errors during black execution
                feedback_messages.append(f"Error running Black: {e}")
                passed = False

    finally:
        if os.path.exists(tmp_file_path): # Check if tmp_file_path was created before removing
            os.remove(tmp_file_path)

    return CodeReviewResult(
        passed=passed,
        feedback="\n".join(feedback_messages) if feedback_messages else None,
        revised_code=None # Black --check --diff doesn't provide the full reformatted code directly
    )


if __name__ == '__main__':
    print("--- Testing Code Verification (`verify_code`) ---")

    # Test Case 1: Clean Python code
    clean_code = "def hello():\n    print(\"Hello, world!\")\n\nhello()\n"
    print("\n--- Test 1: Clean Code ---")
    # Assuming ruff and black are installed in the environment
    # Create a dummy file_path context
    if not os.path.exists("temp_test_context"): os.makedirs("temp_test_context")
    # Create a dummy pyproject.toml in the context directory or project root if needed for ruff/black
    # For this test, we assume global/default behavior of ruff/black.

    # Ensure tools are available for test, otherwise it's not a good test of verify_code
    ruff_path_test = shutil.which("ruff")
    black_path_test = shutil.which("black")

    if ruff_path_test and black_path_test:
        tools_available = True
        print(f"Ruff found at: {ruff_path_test}")
        print(f"Black found at: {black_path_test}")
    else:
        tools_available = False
        print(f"Skipping full verify_code tests: Ruff ({ruff_path_test}) or Black ({black_path_test}) not found in PATH.")
        if not ruff_path_test:
            print("Consider adding the directory containing 'ruff' to your PATH or reinstalling it.")
            print("Typically, if installed via 'pip install --user ruff', it might be in ~/.local/bin")
        if not black_path_test:
            print("Consider adding the directory containing 'black' to your PATH or reinstalling it.")
            print("Typically, if installed via 'pip install --user black', it might be in ~/.local/bin")

    if tools_available:
        review_clean = verify_code(clean_code, "temp_test_context/clean.py")
        print(f"Clean Code Review: Passed={review_clean.passed}")
        if review_clean.feedback:
            print(f"Feedback:\n{review_clean.feedback}")
        assert review_clean.passed # This might fail if default ruff/black have very strict rules

        # Test Case 2: Python code with Ruff issues (e.g., unused import)
        ruff_issue_code = "import os\ndef unused_var():\n    x = 1\n" # x is unused, os is unused
        print("\n--- Test 2: Code with Ruff Issues ---")
        review_ruff = verify_code(ruff_issue_code, "temp_test_context/ruff_issue.py")
        print(f"Ruff Issue Code Review: Passed={review_ruff.passed}")
        if review_ruff.feedback:
            print(f"Feedback:\n{review_ruff.feedback}")
        assert not review_ruff.passed
        assert "Ruff found issues" in review_ruff.feedback

        # Test Case 3: Python code needing Black formatting
        black_issue_code = "def func(arg1,arg2):\n  return arg1+arg2\n" # Needs formatting
        print("\n--- Test 3: Code needing Black Formatting ---")
        review_black = verify_code(black_issue_code, "temp_test_context/black_issue.py")
        print(f"Black Issue Code Review: Passed={review_black.passed}")
        if review_black.feedback:
            print(f"Feedback:\n{review_black.feedback}")
        assert not review_black.passed # Black reformatting means it didn't "pass" current state
        assert "Black: Code needs formatting" in review_black.feedback

        # Test Case 4: Code with both Ruff and Black issues
        combined_issue_code = "import sys\ndef another_func ( a, b ):\n    unused_variable = sys.path\n    return a+b"
        print("\n--- Test 4: Code with Ruff & Black Issues ---")
        review_combined = verify_code(combined_issue_code, "temp_test_context/combined_issue.py")
        print(f"Combined Issue Code Review: Passed={review_combined.passed}")
        if review_combined.feedback:
            print(f"Feedback:\n{review_combined.feedback}")
        assert not review_combined.passed
        assert "Ruff found issues" in review_combined.feedback
        assert "Black: Code needs formatting" in review_combined.feedback

    # Test Case 5: Non-Python language
    js_code = "function hello() { console.log('Hello'); }"
    print("\n--- Test 5: Non-Python Code (JavaScript) ---")
    review_js = verify_code(js_code, "test.js", "javascript")
    print(f"JavaScript Code Review: Passed={review_js.passed}")
    if review_js.feedback:
        print(f"Feedback: {review_js.feedback}")
    assert review_js.passed # Default pass for non-Python
    assert "not implemented" in review_js.feedback

    # Cleanup
    if os.path.exists("temp_test_context"):
        import shutil
        shutil.rmtree("temp_test_context")
    print("\n--- Tests Complete ---")

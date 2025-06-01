from typing import List, Optional
from pydantic import BaseModel

class FileDetail(BaseModel):
    path: str
    description: str

class FileList(BaseModel):
    files: List[FileDetail]

class ProjectPlan(BaseModel):
    project_description: str
    technical_description: str # Detailed breakdown of components, modules, classes, functions
    mermaid_diagram: str       # For visualizing architecture or flow
    # Add other fields as identified from the PlanningAgent's expected output
    # For example:
    # key_features: List[str]
    # tech_stack_recommendations: List[str]
    # potential_challenges: List[str]

class CodeReviewResult(BaseModel):
    passed: bool
    revised_code: Optional[str] = None
    feedback: Optional[str] = None

if __name__ == '__main__':
    # Example Usage (optional, for testing)
    print("--- Test 1: FileDetail ---")
    fd = FileDetail(path="./src/main.py", description="Main application entry point.")
    print(fd.model_dump_json(indent=2))

    print("\n--- Test 2: FileList ---")
    fl = FileList(files=[
        FileDetail(path="./src/utils.py", description="Utility functions."),
        FileDetail(path="./README.md", description="Project documentation.")
    ])
    print(fl.model_dump_json(indent=2))

    print("\n--- Test 3: ProjectPlan ---")
    pp = ProjectPlan(
        project_description="A new AI-powered coding assistant.",
        technical_description="The system will use a modular architecture with a central orchestrator...",
        mermaid_diagram="graph TD\nA[Start] --> B[Process Data];\nB --> C[End];"
    )
    print(pp.model_dump_json(indent=2))

    print("\n--- Test 4: CodeReviewResult - Passed ---")
    cr_pass = CodeReviewResult(passed=True, revised_code="print('Hello, world!')")
    print(cr_pass.model_dump_json(indent=2))

    print("\n--- Test 5: CodeReviewResult - Failed with feedback ---")
    cr_fail = CodeReviewResult(passed=False, feedback="Syntax error on line 5. Variable not defined.")
    print(cr_fail.model_dump_json(indent=2))

    print("\n--- Test 6: CodeReviewResult - Failed with revised_code and feedback ---")
    cr_fail_revised = CodeReviewResult(passed=False, revised_code="print('Hllo, world!') # incorrect spelling", feedback="Typo in output string.")
    print(cr_fail_revised.model_dump_json(indent=2))

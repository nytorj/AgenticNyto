# Agentic System for Coding Models - Project Plan

This document outlines the plan for building the Agentic System for Coding Models using Ollama.

## Phase 1: Foundation & Core Components

1.  **Project Setup:**
    *   Confirm the file structure:
        ```
        ./
        ├── agent.py         # Main application logic, TUI
        ├── Project.md       # Project description (exists)
        ├── prompts.py       # Agent prompts (exists)
        ├── PLAN.md          # This plan file
        ├── .vscode/         # VSCode settings (exists)
        │   └── settings.json
        └── lib/
            ├── __init__.py
            ├── ollama_client.py # Wrapper for Ollama API interaction
            ├── models.py        # Pydantic models for data structures
            ├── prompts.py       # Module to load/manage prompts (refactor from root)
            └── tools.py         # Code execution/linting tools
        ```
    *   Initialize Python environment (e.g., `python -m venv .venv`, `source .venv/bin/activate`).
    *   Create `requirements.txt` with initial dependencies:
        *   `ollama`
        *   `pydantic`
        *   `rich`
        *   Linters/formatters (e.g., `ruff`, `black`)
    *   Install dependencies: `pip install -r requirements.txt`.

2.  **Ollama Client (`lib/ollama_client.py`):**
    *   Create a class `OllamaClient`.
    *   Constructor (`__init__`) to configure the default model (`qwen3:32b`) and host.
    *   Method `generate(prompt: str, model: str = None) -> str` for raw API interaction.
    *   Handle potential API errors.

3.  **Data Models (`lib/models.py`):**
    *   Define Pydantic models:
        *   `FileDetail(BaseModel)`: `path: str`, `description: str`
        *   `FileList(BaseModel)`: `files: List[FileDetail]`
        *   `ProjectPlan(BaseModel)`: Fields based on `PlanningAgent` prompt (e.g., `project_description`, `technical_description`, `mermaid_diagram`, etc.).
        *   `CodeReviewResult(BaseModel)`: `passed: bool`, `revised_code: Optional[str] = None`, `feedback: Optional[str] = None`

4.  **Prompts (`lib/prompts.py`):**
    *   Move existing prompts to `lib/prompts.py`.
    *   Add `ReformatDescriptionAgent` prompt (as defined previously).
    *   Add `DocumentationAgent` prompt (to be defined, focusing on README/docs folder).
    *   Create functions/constants for easy access.
    *   Ensure consistent placeholder usage (`[[...]]`).

## Phase 2: Agent Logic & Workflow

5.  **Core Agent Logic (`agent.py`):**
    *   Import necessary modules.
    *   Initialize `OllamaClient`.
    *   Implement `run_project(user_description: str)`:
        *   **Step 1: Reformat Description:** Call `ReformatDescriptionAgent`.
        *   **Step 2: Planning:** Call `PlanningAgent`, parse output into `ProjectPlan`, display via TUI.
        *   **Step 3: File List Generation:** Call `SoftwareEngineerAgent`, parse JSON into `FileList`, display via TUI.
        *   **Step 4: Code Generation & Review Loop:**
            *   Iterate through `file_list.files`.
            *   Initialize `retry_count = 0`.
            *   Loop (while `retry_count <= 2`):
                *   Call `CodingAgent`.
                *   Call `SeniorEngineerAgent`.
                *   Use `lib/tools.py.verify_code` on the reviewed code.
                *   If `passed`: Write file, break inner loop.
                *   If `failed`: Increment `retry_count`, add feedback to next `CodingAgent` prompt.
                *   If `retry_count > 2`: Ask user (Continue/Skip/Stop) via TUI, handle choice.
        *   **Step 5: Documentation Generation (Refined Scope):**
            *   Trigger after Step 4 completes successfully.
            *   Input: `project_plan`, `file_list`, final code content.
            *   Define and call `DocumentationAgent` prompt (focused on README/docs).
            *   Parse output.
            *   Write/update `README.md` and create files in `docs/`. **Do not modify source code.**
            *   Display progress via TUI.
        *   **Clarification Hook:** Implement logic to detect ambiguity, pause, ask user via TUI, update context, and resume.

6.  **Tooling (`lib/tools.py`):**
    *   Implement `verify_code(code: str, file_path: str) -> CodeReviewResult`:
        *   Save code to temp file.
        *   Run linters (e.g., `ruff`) using `subprocess`.
        *   Run formatters (e.g., `black --check`).
        *   Parse results.
        *   Return `CodeReviewResult`.
    *   Add helper functions for file I/O (writing generated code, creating `docs/` dir).

7.  **TUI Integration (`agent.py` using `rich`):**
    *   Use `rich` components (`Console`, `Panel`, `Progress`, `Prompt`) for clear status updates and user interaction.

## Phase 3: Refinement & Testing

8.  **Error Handling:** Implement robust error handling throughout.
9.  **Testing:** Unit tests, integration tests (mock Ollama), end-to-end tests.
10. **Documentation Review:** Review the automatically generated `README.md` and `docs/` files.

## Mermaid Diagram (Agent Flow)

\`\`\`mermaid
graph TD
    A[User Input: Project Description] --> B{Reformat Description Agent};
    B --> C[Reformatted Description];
    C --> D{Planning Agent};
    D --> E[Project Plan (todo.md content)];
    E --> F{Software Engineer Agent};
    F --> G[File List (JSON)];
    G --> H{Loop Each File};
    H -- File Details --> I{CodingAgent};
    I --> J[Generated Code];
    J --> K{Senior Engineer Agent};
    K --> L[Reviewed Code];
    L --> M{Code Verification Tool (Lint/Test)};
    M -- Passed --> N[Write File];
    N --> H;
    M -- Failed --> O{Retry < 2?};
    O -- Yes --> P[Add Error to Context];
    P --> I;
    O -- No --> Q{Ask User: Continue/Skip/Stop?};
    Q -- Continue --> P;
    Q -- Skip --> H;
    Q -- Stop --> R[End Process];
    H -- All Files Done --> S{Documentation Agent};
    S --> T[Update README.md & Create docs/ Files];
    T --> U[Phase 3: Refinement & Testing];
    U --> R;

    subgraph Clarification Hook
        X{Ambiguity Detected?} -- Yes --> Y{Ask User via TUI};
        Y --> Z[Update Context];
    end

    B -.-> X;
    D -.-> X;
    F -.-> X;
    M -.-> X;
    S -.-> X;
\`\`\`

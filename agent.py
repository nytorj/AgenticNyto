# agent.py
import json
import time
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.prompt import Prompt

from lib.ollama_client import OllamaClient
from lib.models import ProjectPlan, FileList, FileDetail, CodeReviewResult
from lib.prompts import (
    REFORMAT_DESCRIPTION_AGENT_PROMPT,
    PLANNING_AGENT_PROMPT,
    SOFTWARE_ENGINEER_AGENT_PROMPT,
    CODING_AGENT_PROMPT,
    SENIOR_ENGINEER_AGENT_PROMPT,
    DOCUMENTATION_AGENT_PROMPT
)
from lib.tools import write_code_to_file, verify_code, create_docs_dir_if_not_exists

try:
    ollama_client = OllamaClient()
except Exception as e:
    print(f"Critical Warning: OllamaClient could not be initialized: {e}. Agent calls WILL FAIL.")
    ollama_client = None
console = Console()

def run_project(user_description: str):
    global ollama_client, console

    if not ollama_client:
        console.print("[bold yellow]Warning: Ollama client is not available. LLM-based operations will use fallbacks or be skipped.[/bold yellow]")

    console.print(f"[bold blue]Starting project generation for:[/bold blue] {user_description[:100]}...")

    # Step 1: Reformat Description
    console.print("\n[bold green]Step 1: Reformatting Description...[/bold green]")
    reformatted_description = user_description # Fallback
    if ollama_client:
        try:
            prompt_template = REFORMAT_DESCRIPTION_AGENT_PROMPT
            prompt = prompt_template.replace("[[USER_DESCRIPTION]]", user_description)
            raw_output = ollama_client.generate(prompt)
            if raw_output.startswith("Error:"):
                console.print(f"[red]ReformatDescriptionAgent Error: {raw_output}[/red]")
            else:
                reformatted_description = raw_output
        except Exception as e:
            console.print(f"[bold red]Exception during Reformat Description: {e}[/bold red]")
    else:
        console.print("[italic yellow]Skipped ReformatDescriptionAgent (Ollama client not available).[/italic yellow]")
    console.print(Panel(reformatted_description, title="Reformatted Description", expand=False, border_style="blue"))

    # Step 2: Planning
    console.print("\n[bold green]Step 2: Generating Project Plan...[/bold green]")
    project_plan = ProjectPlan(project_description="Default Plan (Ollama N/A or Error)", technical_description="N/A", mermaid_diagram="N/A")
    if ollama_client:
        try:
            prompt_template = PLANNING_AGENT_PROMPT
            prompt = prompt_template.replace("[[USER_DESCRIPTION]]", user_description).replace("[[REFORMATTED_DESCRIPTION]]", reformatted_description)
            raw_output = ollama_client.generate(prompt)
            if raw_output.startswith("Error:"):
                console.print(f"[red]PlanningAgent Error: {raw_output}[/red]")
            else:
                try:
                    json_start = raw_output.find('{'); json_end = raw_output.rfind('}') + 1
                    if json_start != -1 and json_end > json_start:
                        json_str = raw_output[json_start:json_end]
                        project_plan = ProjectPlan(**json.loads(json_str))
                    else:
                        console.print("[red]Could not find valid JSON in PlanningAgent output.[/red]")
                        project_plan = ProjectPlan(project_description="Plan (Invalid JSON)", technical_description=raw_output, mermaid_diagram="N/A")
                except json.JSONDecodeError as e_json:
                    console.print(f"[red]PlanningAgent JSON parsing error: {e_json}[/red]")
                    project_plan = ProjectPlan(project_description="Plan (JSON Decode Error)", technical_description=raw_output, mermaid_diagram="N/A")
                except Exception as e_val: # Pydantic validation or other errors
                    console.print(f"[red]PlanningAgent Pydantic model validation error: {e_val}[/red]")
                    project_plan = ProjectPlan(project_description="Plan (Validation Error)", technical_description=raw_output, mermaid_diagram="N/A")
        except Exception as e:
            console.print(f"[bold red]Exception during Project Planning: {e}[/bold red]")
    else:
        console.print("[italic yellow]Skipped PlanningAgent (Ollama client not available).[/italic yellow]")
    console.print(Panel(f"Title: {project_plan.project_description}\nTech Dsc: {project_plan.technical_description[:100]}...", title="Project Plan Summary", expand=False, border_style="blue"))

    # Step 3: File List Generation
    console.print("\n[bold green]Step 3: Generating File List...[/bold green]")
    file_list = FileList(files=[])
    if ollama_client:
        try:
            plan_content_for_agent = project_plan.model_dump_json(indent=2)
            prompt_template = SOFTWARE_ENGINEER_AGENT_PROMPT
            prompt = prompt_template.replace("[[PROJECT_PLAN_CONTENT]]", plan_content_for_agent)
            raw_output = ollama_client.generate(prompt)
            if raw_output.startswith("Error:"):
                console.print(f"[red]SoftwareEngineerAgent Error: {raw_output}[/red]")
            else:
                try:
                    json_start = raw_output.find('{'); json_end = raw_output.rfind('}') + 1
                    if json_start != -1 and json_end > json_start:
                        json_str = raw_output[json_start:json_end]
                        file_list = FileList(**json.loads(json_str))
                    else:
                        console.print("[red]Could not find valid JSON in SoftwareEngineerAgent output.[/red]")
                except json.JSONDecodeError as e_json:
                    console.print(f"[red]File List JSON parsing error: {e_json}[/red]")
                except Exception as e_val: # Pydantic validation or other errors
                    console.print(f"[red]File List Pydantic model validation error: {e_val}[/red]")
        except Exception as e:
            console.print(f"[bold red]Exception during File List Generation: {e}[/bold red]")
    else:
        console.print("[italic yellow]Skipped SoftwareEngineerAgent (Ollama client not available).[/italic yellow]")
    # Ensure file_list.files is not None if file_list itself is None (though it's initialized with files=[])
    if not hasattr(file_list, 'files') or file_list.files is None : file_list = FileList(files=[]) # Extra safety
    console.print(Panel(f"Files to generate: {len(file_list.files)}", title="File List Summary", expand=False, border_style="blue"))

    # Step 4: Code Generation & Review Loop
    console.print("\n[bold green]Step 4: Code Generation & Review...[/bold green]")
    final_code_outputs = {}
    # The `or True` part forces mock logic for TUI demo when ollama_client is None.
    # Remove `or True` for actual LLM runs.
    use_mock_logic_for_tui_demo = not ollama_client or True

    if use_mock_logic_for_tui_demo:
        console.print("[italic yellow]Using mock logic for code generation loop (Ollama client not available or TUI demo forced).[/italic yellow]")
        # Ensure file_list has mock data for TUI demo if it's empty
        if not file_list.files:
            file_list = FileList(files=[
                FileDetail(path="mock/main.py", description="Mock main file"),
                FileDetail(path="mock/utils.py", description="Mock utils file to demonstrate failure prompt"),
                FileDetail(path="mock/README.md", description="Mock Readme")
            ])

        # Mock logic to demonstrate TUI for Step 4
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), BarColumn(), TextColumn("[progress.percentage]{task.percentage:>3.0f}%"), TimeElapsedColumn(), console=console, transient=False) as progress:
            file_gen_task = progress.add_task("[cyan]File Generation (Mock Demo)", total=len(file_list.files))
            for i, file_detail in enumerate(file_list.files): # Ensure this uses the potentially mocked file_list
                progress.update(file_gen_task, description=f"Mock processing: {file_detail.path}")
                time.sleep(0.2)
                # Simulate one success, one failure for prompt, one more success
                if file_detail.path == "mock/main.py":
                     final_code_outputs[file_detail.path] = f"# Mock code for {file_detail.path}"
                     progress.console.print(f"[green]✓ Mock code for {file_detail.path} 'passed'.[/green]")
                elif file_detail.path == "mock/utils.py":
                    progress.console.print(Panel(f"Mock failure for [bold]{file_detail.path}[/bold] after 3 attempts.", title="[red]Mock File Failed[/red]", expand=False))
                    if console.is_interactive:
                        choice = Prompt.ask(f"Action for [bold]{file_detail.path}[/bold]?", choices=["c","s","a"], default="c", console=console).lower()
                        if choice == 's': progress.console.print(f"[yellow]Skipping {file_detail.path}.[/yellow]")
                        elif choice == 'a': console.print("[bold red]Aborting (mock).[/bold red]"); return
                elif file_detail.path == "mock/README.md":
                     final_code_outputs[file_detail.path] = f"# Mock code for {file_detail.path}"
                     progress.console.print(f"[green]✓ Mock code for {file_detail.path} 'passed'.[/green]")
                progress.update(file_gen_task, advance=1)

    elif not file_list.files: # If not using mock logic, and file list is still empty
        console.print("[yellow]Skipping code generation: File list is empty.[/yellow]")

    else: # Actual logic with Ollama client AND file_list is not empty
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), BarColumn(), TextColumn("[progress.percentage]{task.percentage:>3.0f}%"), TimeElapsedColumn(), console=console, transient=False) as progress:
            file_gen_task = progress.add_task("[cyan]File Generation Progress", total=len(file_list.files))
            for file_detail in file_list.files:
                progress.update(file_gen_task, description=f"Processing: {file_detail.path}")
                current_code = ""
                feedback_history = []
                file_processed_successfully = False
                for retry_count in range(3):
                    progress.console.print(f"[gray]Attempt {retry_count + 1}/3 for {file_detail.path}...[/gray]")
                    try:
                        # 1. CodingAgent
                        coding_prompt_template = CODING_AGENT_PROMPT
                        coding_prompt = coding_prompt_template.replace("[[FILE_PATH]]", file_detail.path) \
                            .replace("[[FILE_DESCRIPTION]]", file_detail.description) \
                            .replace("[[PROJECT_PLAN_CONTENT]]", project_plan.model_dump_json()) \
                            .replace("[[EXISTING_CODE]]", current_code if current_code else "") \
                            .replace("[[FEEDBACK]]", "\n".join(feedback_history[-2:]) if feedback_history else "No feedback yet.") \
                            .replace("[[RELEVANT_FILES_CONTEXT]]", "") # Placeholder

                        generated_code = ollama_client.generate(coding_prompt)
                        if generated_code.startswith("Error:"):
                            progress.console.print(f"[red]CodingAgent Error for {file_detail.path}: {generated_code}[/red]")
                            feedback_history.append(f"CodingAgent Error: {generated_code}")
                            if retry_count == 2: break # Failed all retries for this agent
                            current_code = "" # Reset code on agent error
                            continue

                        # 2. SeniorEngineerAgent
                        senior_prompt_template = SENIOR_ENGINEER_AGENT_PROMPT
                        senior_prompt = senior_prompt_template.replace("[[FILE_PATH]]", file_detail.path) \
                            .replace("[[FILE_DESCRIPTION]]", file_detail.description) \
                            .replace("[[GENERATED_CODE]]", generated_code) \
                            .replace("[[PROJECT_PLAN_CONTENT]]", project_plan.model_dump_json())

                        raw_senior_review = ollama_client.generate(senior_prompt)
                        senior_review_passed = False
                        senior_feedback_text = f"Senior Engineer review failed to parse or returned an error for {file_detail.path}"
                        senior_revised_code = None

                        if raw_senior_review.startswith("Error:"):
                            progress.console.print(f"[red]SeniorEngineerAgent Error for {file_detail.path}: {raw_senior_review}[/red]")
                        else:
                            try:
                                sr_json_start = raw_senior_review.find('{'); sr_json_end = raw_senior_review.rfind('}') + 1
                                if sr_json_start != -1 and sr_json_end > sr_json_start:
                                    review_data = json.loads(raw_senior_review[sr_json_start:sr_json_end])
                                    senior_review_passed = review_data.get("review_passed", False)
                                    senior_feedback_text = review_data.get("feedback", "No specific feedback provided.")
                                    senior_revised_code = review_data.get("revised_code")
                                else:
                                    progress.console.print(f"[red]SeniorEngineerAgent output for {file_detail.path} was not valid JSON.[/red]")
                            except json.JSONDecodeError as e_sr_json:
                                progress.console.print(f"[red]SeniorEngineerAgent JSON parsing error for {file_detail.path}: {e_sr_json}[/red]")
                            except Exception as e_sr_val:
                                progress.console.print(f"[red]SeniorEngineerAgent Pydantic/validation error for {file_detail.path}: {e_sr_val}[/red]")

                        feedback_history.append(f"Senior Feedback: {senior_feedback_text}")
                        code_to_verify = senior_revised_code if senior_revised_code and senior_revised_code.strip() else generated_code

                        # 3. verify_code Tool
                        language = "python" if file_detail.path.endswith(".py") else "generic"
                        tool_review_result = verify_code(code_to_verify, file_detail.path, language=language)
                        if tool_review_result.feedback:
                            feedback_history.append(f"Tool Verification Feedback: {tool_review_result.feedback}")

                        # 4. Decision
                        if senior_review_passed and tool_review_result.passed:
                            progress.console.print(f"[green]✓ Code for {file_detail.path} passed all checks.[/green]")
                            if write_code_to_file(file_detail.path, code_to_verify):
                                final_code_outputs[file_detail.path] = code_to_verify
                            else:
                                progress.console.print(f"[bold red]Failed to write {file_detail.path} to disk. This attempt will be marked as failed.[/bold red]")
                                # Treat write failure as a cycle failure, could retry or mark file as failed.
                                # For now, it just means this attempt didn't save.
                                if retry_count == 2 : break # If write fails on last attempt, it's a fail for the file.
                                continue # Try to regenerate.

                            file_processed_successfully = True
                            break # Exit retry loop for this file
                        else:
                            failed_checks = []
                            if not senior_review_passed: failed_checks.append("Senior Review")
                            if not tool_review_result.passed: failed_checks.append("Tool Verification")
                            progress.console.print(f"[yellow]Attempt {retry_count+1} for {file_detail.path} failed ({', '.join(failed_checks)}). Retrying if attempts left.[/yellow]")
                            current_code = tool_review_result.revised_code if tool_review_result.revised_code and tool_review_result.revised_code.strip() else \
                                           senior_revised_code if senior_revised_code and senior_revised_code.strip() else \
                                           generated_code

                    except Exception as e_attempt:
                        progress.console.print(f"[bold red]Exception during attempt {retry_count+1} for {file_detail.path}: {e_attempt}[/bold red]")
                        feedback_history.append(f"Exception in attempt: {e_attempt}")
                        if retry_count == 2: break # Failed all retries
                        current_code = "" # Reset on major error for this attempt
                        continue # To next attempt


                if not file_processed_successfully:
                    progress.console.print(Panel(f"Failed to generate/verify [bold]{file_detail.path}[/bold] after 3 attempts.", title="[red]File Processing Failed[/red]", border_style="red", expand=False))
                    if console.is_interactive:
                        choice = Prompt.ask(f"Action for [bold]{file_detail.path}[/bold]?", choices=["c","s","a"], default="c", console=console).lower()
                        if choice == 's': progress.console.print(f"[yellow]Skipping file: {file_detail.path}[/yellow]")
                        elif choice == 'a': console.print("[bold red]Aborting project generation by user choice.[/bold red]"); return
                    else: progress.console.print(f"[yellow]Non-interactive: Continuing after failure of {file_detail.path}.[/yellow]")
                progress.update(file_gen_task, advance=1)

    # Step 5: Documentation Generation
    console.print("\n[bold green]Step 5: Generating Documentation...[/bold green]")
    # The `or True` part forces mock logic for TUI demo when ollama_client is None.
    # Remove `or True` for actual LLM runs.
    use_mock_logic_for_tui_demo_step5 = not ollama_client or True

    if not final_code_outputs:
        console.print("[yellow]No code successfully generated. Skipping documentation generation.[/yellow]")
    elif use_mock_logic_for_tui_demo_step5:
        console.print("[italic yellow]Using mock logic for documentation (Ollama client not available or mock forced).[/italic yellow]")
        # Mock logic for Step 5
        mock_doc_files = {"README.md": "# Mock Project\nThis is a mock README.", "docs/USAGE.md": "## How to Use\nRun the mock."}
        if any(path.startswith("docs/") for path in mock_doc_files.keys()): create_docs_dir_if_not_exists()
        with Progress(SpinnerColumn(),TextColumn("[progress.description]{task.description}"),BarColumn(),TimeElapsedColumn(),console=console,transient=False) as progress:
            doc_task = progress.add_task("[cyan]Writing Docs (Mock)", total=len(mock_doc_files))
            for path, content in mock_doc_files.items():
                progress.update(doc_task, description=f"Mock writing: {path}")
                write_code_to_file(path, content) # Use actual write tool
                time.sleep(0.1)
                progress.update(doc_task, advance=1)
        console.print(f"[green]Mock documentation generated. {len(mock_doc_files)} file(s) processed.[/green]")
    else: # Actual logic with Ollama client
        try:
            project_plan_json = project_plan.model_dump_json(indent=2)
            file_list_json = file_list.model_dump_json(indent=2)
            code_content_map_json = json.dumps(final_code_outputs, indent=2)
            doc_prompt_template = DOCUMENTATION_AGENT_PROMPT
            doc_prompt = doc_prompt_template.replace("[[PROJECT_PLAN_CONTENT]]", project_plan_json) \
                .replace("[[FILE_LIST_JSON]]", file_list_json) \
                .replace("[[FINAL_CODE_CONTENT_MAP]]", code_content_map_json)

            console.print("[italic gray]Calling DocumentationAgent...[/italic gray]")
            raw_doc_output = ollama_client.generate(doc_prompt)

            if raw_doc_output.startswith("Error:"):
                console.print(f"[red]DocumentationAgent Error: {raw_doc_output}[/red]")
            else:
                try:
                    doc_json_start = raw_doc_output.find('{'); doc_json_end = raw_doc_output.rfind('}') + 1
                    if doc_json_start != -1 and doc_json_end > doc_json_start:
                        doc_files_map = json.loads(raw_doc_output[doc_json_start:doc_json_end])
                        if doc_files_map:
                            if any(path.startswith("docs/") for path in doc_files_map.keys()): create_docs_dir_if_not_exists()
                            with Progress(SpinnerColumn(),TextColumn("[progress.description]{task.description}"),BarColumn(),TimeElapsedColumn(),console=console,transient=False) as progress:
                                doc_write_task = progress.add_task("[cyan]Writing Documentation", total=len(doc_files_map))
                                for doc_path, doc_content in doc_files_map.items():
                                    progress.update(doc_write_task, description=f"Writing: {doc_path}")
                                    if not write_code_to_file(doc_path, doc_content):
                                        progress.console.print(f"[red]Failed to write documentation file: {doc_path}[/red]")
                                    progress.update(doc_write_task, advance=1)
                            console.print(f"[green]Documentation generation complete. {len(doc_files_map)} file(s) processed.[/green]")
                        else: console.print("[yellow]DocumentationAgent returned no documentation files.[/yellow]")
                    else: console.print("[red]Could not find valid JSON in DocumentationAgent output.[/red]")
                except json.JSONDecodeError as e_doc_json:
                    console.print(f"[red]Documentation JSON parsing error: {e_doc_json}[/red]")
                except Exception as e_doc_val:
                     console.print(f"[red]Documentation Pydantic/validation error: {e_doc_val}[/red]")
        except Exception as e:
            console.print(f"[bold red]Exception during Documentation Generation: {e}[/bold red]")

    console.print("\n[bold blue]Project generation process complete.[/bold blue]")

if __name__ == "__main__":
    sample_user_desc = "A simple CLI to-do app in Python, with basic file operations and a README."
    console.print("[bold yellow]=== Agentic Coding System - Error Handling & Refinements Demo ===[/bold yellow]")
    user_desc_input = sample_user_desc
    if console.is_interactive:
        response = Prompt.ask("Enter project description (or press Enter for sample)", default=sample_user_desc, console=console)
        user_desc_input = response if response.strip() else sample_user_desc
    else:
        console.print(f"[italic gray]Non-interactive mode. Using sample description: '{user_desc_input}'[/italic gray]")
    run_project(user_desc_input)

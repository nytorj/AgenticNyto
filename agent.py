# agent.py
import json
from rich.console import Console
from rich.panel import Panel # For displaying feedback

# Import core components
from lib.ollama_client import OllamaClient
from lib.models import ProjectPlan, FileList, FileDetail, CodeReviewResult # Ensure CodeReviewResult is imported
from lib.prompts import (
    REFORMAT_DESCRIPTION_AGENT_PROMPT,
    PLANNING_AGENT_PROMPT,
    SOFTWARE_ENGINEER_AGENT_PROMPT,
    CODING_AGENT_PROMPT,
    SENIOR_ENGINEER_AGENT_PROMPT,
    DOCUMENTATION_AGENT_PROMPT
)
from lib.tools import write_code_to_file, verify_code, create_docs_dir_if_not_exists # Import necessary tools

# Initialize Rich Console for TUI later
console = Console()

# Initialize OllamaClient
try:
    ollama_client = OllamaClient()
except Exception as e:
    console.print(f"[bold red]Error initializing OllamaClient: {e}[/bold red]")
    console.print("Please ensure Ollama is running and configured correctly.")
    exit(1)

def run_project(user_description: str):
    global ollama_client, console # Ensure globals are accessible

    console.print(f"[bold blue]Starting project generation for:[/bold blue] {user_description[:100]}...")

    # Step 1: Reformat Description
    console.print("\n[bold green]Step 1: Reformatting Description...[/bold green]")
    reformatted_description = ""
    try:
        prompt_template_reformat = REFORMAT_DESCRIPTION_AGENT_PROMPT
        prompt_reformat = prompt_template_reformat.replace("[[USER_DESCRIPTION]]", user_description)
        raw_reformatted_output = ollama_client.generate(prompt_reformat)
        if raw_reformatted_output.startswith("Error:"):
            console.print(f"[bold red]Error from ReformatDescriptionAgent: {raw_reformatted_output}[/bold red]")
            reformatted_description = user_description
        else:
            reformatted_description = raw_reformatted_output
    except Exception as e:
        console.print(f"[bold red]An error occurred during description reformatting: {e}[/bold red]")
        reformatted_description = user_description
    console.print(Panel(reformatted_description, title="Reformatted Description", expand=False, border_style="blue"))

    # Step 2: Planning
    console.print("\n[bold green]Step 2: Generating Project Plan...[/bold green]")
    project_plan: ProjectPlan = None
    try:
        prompt_template_plan = PLANNING_AGENT_PROMPT
        prompt_plan = prompt_template_plan.replace("[[USER_DESCRIPTION]]", user_description)
        prompt_plan = prompt_plan.replace("[[REFORMATTED_DESCRIPTION]]", reformatted_description)
        raw_plan_output = ollama_client.generate(prompt_plan)
        if raw_plan_output.startswith("Error:"):
            console.print(f"[bold red]Error from PlanningAgent: {raw_plan_output}[/bold red]")
        else:
            try:
                json_start_index = raw_plan_output.find('{')
                json_end_index = raw_plan_output.rfind('}') + 1
                if json_start_index != -1 and json_end_index > json_start_index :
                    json_string = raw_plan_output[json_start_index:json_end_index]
                    plan_data = json.loads(json_string)
                    project_plan = ProjectPlan(**plan_data)
                else:
                    console.print("[bold red]Could not find JSON in PlanningAgent output for ProjectPlan.[/bold red]")
                    project_plan = ProjectPlan(project_description="Raw output (No JSON)", technical_description=raw_plan_output, mermaid_diagram="N/A")
            except json.JSONDecodeError as e:
                console.print(f"[bold red]Failed to parse Project Plan JSON: {e}[/bold red]")
                project_plan = ProjectPlan(project_description="Raw output (JSON error)", technical_description=raw_plan_output, mermaid_diagram="N/A")
            except Exception as e: # Catch Pydantic validation errors etc.
                console.print(f"[bold red]Error creating ProjectPlan model: {e}[/bold red]")
                project_plan = ProjectPlan(project_description="Raw output (Pydantic error)", technical_description=raw_plan_output, mermaid_diagram="N/A")
    except Exception as e:
        console.print(f"[bold red]An error occurred during project planning: {e}[/bold red]")
    if not project_plan:
        project_plan = ProjectPlan(project_description="Empty plan due to error", technical_description="N/A", mermaid_diagram="N/A")
    console.print(Panel(f"Title: {project_plan.project_description}\nTech: {project_plan.technical_description[:200]}...", title="Project Plan Summary", expand=False, border_style="blue"))

    # Step 3: File List Generation
    console.print("\n[bold green]Step 3: Generating File List...[/bold green]")
    file_list: FileList = None
    try:
        plan_content_for_agent = project_plan.model_dump_json(indent=2)
        prompt_template_files = SOFTWARE_ENGINEER_AGENT_PROMPT
        prompt_files = prompt_template_files.replace("[[PROJECT_PLAN_CONTENT]]", plan_content_for_agent)
        raw_file_list_output = ollama_client.generate(prompt_files)
        if raw_file_list_output.startswith("Error:"):
            console.print(f"[bold red]Error from SoftwareEngineerAgent: {raw_file_list_output}[/bold red]")
        else:
            try:
                json_start_index = raw_file_list_output.find('{')
                json_end_index = raw_file_list_output.rfind('}') + 1
                if json_start_index != -1 and json_end_index > json_start_index:
                    json_string = raw_file_list_output[json_start_index:json_end_index]
                    file_list_data = json.loads(json_string)
                    file_list = FileList(**file_list_data)
                else:
                    console.print("[bold red]Could not find JSON in SoftwareEngineerAgent output for FileList.[/bold red]")
            except json.JSONDecodeError as e:
                console.print(f"[bold red]Failed to parse File List JSON: {e}[/bold red]")
            except Exception as e: # Catch Pydantic validation errors etc.
                console.print(f"[bold red]Error creating FileList model: {e}[/bold red]")
    except Exception as e:
        console.print(f"[bold red]An error occurred during file list generation: {e}[/bold red]")
    if not file_list or not file_list.files: # Ensure file_list itself is not None
        file_list = FileList(files=[]) # Initialize with an empty list if None
    console.print(Panel(f"Files to generate: {len(file_list.files)}", title="File List Summary", expand=False, border_style="blue"))

    # Step 4: Code Generation & Review Loop
    console.print("\n[bold green]Step 4: Code Generation & Review...[/bold green]")
    final_code_outputs = {}

    if not file_list.files:
        console.print("[yellow]Skipping code generation as file list is empty.[/yellow]")
    else:
        for file_detail in file_list.files:
            console.print(f"\n[cyan]Processing file: {file_detail.path}[/cyan]")
            current_code = ""
            feedback_history = []

            for retry_count in range(3):
                console.print(f"Attempt {retry_count + 1}/3 for {file_detail.path}")

                coding_prompt = CODING_AGENT_PROMPT \
                    .replace("[[FILE_PATH]]", file_detail.path) \
                    .replace("[[FILE_DESCRIPTION]]", file_detail.description) \
                    .replace("[[PROJECT_PLAN_CONTENT]]", project_plan.model_dump_json()) \
                    .replace("[[EXISTING_CODE]]", current_code if current_code else "") \
                    .replace("[[FEEDBACK]]", "\n".join(feedback_history) if feedback_history else "No feedback yet.") \
                    .replace("[[RELEVANT_FILES_CONTEXT]]", "")

                console.print("[italic gray]Calling CodingAgent...[/italic gray]")
                generated_code = ollama_client.generate(coding_prompt)
                if generated_code.startswith("Error:"):
                    console.print(f"[red]CodingAgent Error: {generated_code}[/red]")
                    feedback_history.append(f"CodingAgent Error: {generated_code}")
                    current_code = ""
                    if retry_count == 2: console.print(f"[bold red]Failed to generate code for {file_detail.path} after 3 attempts.[/bold red]"); break
                    continue

                senior_engineer_prompt = SENIOR_ENGINEER_AGENT_PROMPT \
                    .replace("[[FILE_PATH]]", file_detail.path) \
                    .replace("[[FILE_DESCRIPTION]]", file_detail.description) \
                    .replace("[[GENERATED_CODE]]", generated_code) \
                    .replace("[[PROJECT_PLAN_CONTENT]]", project_plan.model_dump_json())

                console.print("[italic gray]Calling SeniorEngineerAgent for review...[/italic gray]")
                raw_senior_review = ollama_client.generate(senior_engineer_prompt)

                senior_review_passed = False
                senior_feedback_text = f"Senior Engineer review failed to parse or returned an error: {raw_senior_review}"
                senior_revised_code = None

                if raw_senior_review.startswith("Error:"):
                    console.print(f"[red]SeniorEngineerAgent Error: {raw_senior_review}[/red]")
                else:
                    try:
                        json_start_idx = raw_senior_review.find('{')
                        json_end_idx = raw_senior_review.rfind('}') + 1
                        if json_start_idx != -1 and json_end_idx > json_start_idx:
                            review_json_str = raw_senior_review[json_start_idx:json_end_idx]
                            review_data = json.loads(review_json_str)
                            senior_review_passed = review_data.get("review_passed", False)
                            senior_feedback_text = review_data.get("feedback")
                            senior_revised_code = review_data.get("revised_code")
                            console.print(f"Senior Review: Passed={senior_review_passed}, Feedback: {senior_feedback_text[:100] if senior_feedback_text else 'N/A'}...")
                        else:
                            console.print("[red]SeniorEngineerAgent output was not valid JSON.[/red]")
                    except json.JSONDecodeError as e:
                        console.print(f"[red]SeniorEngineerAgent JSON parsing error: {e}[/red]")
                    except Exception as e:
                        console.print(f"[red]SeniorEngineerAgent error processing review: {e}[/red]")

                feedback_history.append(f"Senior Engineer Feedback: {senior_feedback_text if senior_feedback_text else 'No specific feedback.'}")
                code_to_verify = senior_revised_code if senior_revised_code and senior_revised_code.strip() else generated_code

                console.print("[italic gray]Calling verify_code tool...[/italic gray]")
                language = "python" if file_detail.path.endswith(".py") else "generic"
                tool_review_result: CodeReviewResult = verify_code(code_to_verify, file_detail.path, language=language)
                console.print(f"Tool Verification: Passed={tool_review_result.passed}")
                if tool_review_result.feedback:
                    console.print(Panel(tool_review_result.feedback, title="Tool Feedback", border_style="red", expand=False))
                    feedback_history.append(f"Tool Verification Feedback: {tool_review_result.feedback}")

                if senior_review_passed and tool_review_result.passed:
                    console.print(f"[bold green]Code for {file_detail.path} passed all checks![/bold green]")
                    write_success = write_code_to_file(file_detail.path, code_to_verify)
                    if write_success:
                        console.print(f"Successfully wrote code to {file_detail.path}")
                        final_code_outputs[file_detail.path] = code_to_verify
                    else:
                        console.print(f"[bold red]Failed to write code to {file_detail.path}[/bold red]")
                    break
                else:
                    console.print(f"[yellow]Code for {file_detail.path} failed checks. Retry {retry_count + 1}/3.[/yellow]")
                    if tool_review_result.revised_code and tool_review_result.revised_code.strip():
                        current_code = tool_review_result.revised_code
                        feedback_history.append("Using revised code from tools for next attempt.")
                    elif senior_revised_code and senior_revised_code.strip():
                        current_code = senior_revised_code
                        feedback_history.append("Using revised code from Senior Engineer for next attempt.")
                    else:
                        current_code = generated_code
                        feedback_history.append("Retrying with original code and accumulated feedback.")
                    if retry_count == 2:
                        console.print(f"[bold red]Failed to generate and verify code for {file_detail.path} after 3 attempts.[/bold red]")
                        console.print(f"[italic]For now, stopping generation for this file: {file_detail.path}[/italic]")
                        break

    # Step 5: Documentation Generation
    console.print("\n[bold green]Step 5: Generating Documentation...[/bold green]")
    if not final_code_outputs: # Check if any code was successfully generated
        console.print("[yellow]No code was successfully generated in Step 4. Skipping documentation generation.[/yellow]")
    else:
        try:
            console.print(f"Preparing documentation for {len(final_code_outputs)} generated file(s).")

            project_plan_json = project_plan.model_dump_json(indent=2)
            file_list_json = file_list.model_dump_json(indent=2)
            code_content_map_json = json.dumps(final_code_outputs, indent=2)

            doc_prompt_template = DOCUMENTATION_AGENT_PROMPT
            doc_prompt = doc_prompt_template \
                .replace("[[PROJECT_PLAN_CONTENT]]", project_plan_json) \
                .replace("[[FILE_LIST_JSON]]", file_list_json) \
                .replace("[[FINAL_CODE_CONTENT_MAP]]", code_content_map_json)

            console.print("[italic gray]Calling DocumentationAgent...[/italic gray]")
            raw_doc_output = ollama_client.generate(doc_prompt)

            if raw_doc_output.startswith("Error:"):
                console.print(f"[bold red]Error from DocumentationAgent: {raw_doc_output}[/bold red]")
            else:
                console.print("[bold green]Raw Documentation Output from Agent:[/bold green]\n" + raw_doc_output[:500] + "...")
                try:
                    json_start_idx = raw_doc_output.find('{')
                    json_end_idx = raw_doc_output.rfind('}') + 1
                    if json_start_idx != -1 and json_end_idx > json_start_idx:
                        doc_json_str = raw_doc_output[json_start_idx:json_end_idx]
                        doc_files_map = json.loads(doc_json_str)

                        if not doc_files_map:
                            console.print("[yellow]DocumentationAgent returned an empty map of documentation files.[/yellow]")
                        else:
                            console.print(f"DocumentationAgent proposed {len(doc_files_map)} documentation file(s).")
                            has_docs_subdir_files = any(path.startswith("docs/") for path in doc_files_map.keys())
                            if has_docs_subdir_files:
                                create_docs_dir_if_not_exists()

                            for doc_path, doc_content in doc_files_map.items():
                                console.print(f"Writing documentation to: {doc_path}")
                                if write_code_to_file(doc_path, doc_content):
                                    console.print(f"  Successfully wrote {doc_path}")
                                else:
                                    console.print(f"  [bold red]Failed to write {doc_path}[/bold red]")
                    else:
                        console.print("[bold red]Could not find JSON in DocumentationAgent output.[/bold red]")

                except json.JSONDecodeError as e:
                    console.print(f"[bold red]Failed to parse Documentation JSON: {e}[/bold red]")
                except Exception as e:
                    console.print(f"[bold red]Error processing documentation files: {e}[/bold red]")

        except Exception as e:
            console.print(f"[bold red]An error occurred during documentation generation: {e}[/bold red]")

    console.print("\n[bold blue]Project generation process complete.[/bold blue]")

if __name__ == "__main__":
    sample_user_description = (
        "I need a Python application that acts as a simple CLI to-do list manager. "
        "It should allow users to add tasks, view all tasks, mark tasks as complete, "
        "and delete tasks. Tasks should be stored in a JSON file."
    )
    console.print("[bold yellow]=== Agentic Coding System - DEMO ===[/bold yellow]")
    use_sample_default = "yes"
    user_input_main = ""
    try:
        if not console.is_interactive: # Assume 'yes' in non-interactive environments
            user_input_main = use_sample_default
            console.print(f"Non-interactive mode. Using default for sample: {user_input_main}")
        else:
            user_input_main = console.input(f"Use sample project description? (yes/no) [{use_sample_default}]: ").strip().lower()
            if not user_input_main: # User just pressed Enter
                 user_input_main = use_sample_default
    except Exception:
        user_input_main = use_sample_default
        console.print(f"Input error or non-interactive. Using default for sample: {user_input_main}")

    if user_input_main == "no":
        if not console.is_interactive:
            console.print("Non-interactive mode. Cannot ask for project description. Using sample.")
            final_user_description = sample_user_description
        else:
            final_user_description = console.input("Enter your project description: ")
    else:
        final_user_description = sample_user_description
        console.print(f"[italic gray]Using sample description: '{final_user_description}'[/italic gray]")

    if 'ollama_client' in globals() and ollama_client is not None:
        run_project(final_user_description)
    else:
        console.print("[bold red]Ollama client not available. Exiting.[/bold red]")

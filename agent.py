import json
import time
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from typing import Dict, List
import ollama

from lib.models import ProjectPlan, FileList, FileDetail, CodeReviewResult
from lib.prompts import (
    REFORMAT_DESCRIPTION_AGENT_PROMPT,
    PLANNING_AGENT_PROMPT,
    SOFTWARE_ENGINEER_AGENT_PROMPT,
    CODING_AGENT_PROMPT,
    SENIOR_ENGINEER_AGENT_PROMPT,
    DOCUMENTATION_AGENT_PROMPT,
)
from lib.tools import (
    write_code_to_file,
    verify_code,
    create_docs_dir_if_not_exists,
    search_web_duckduckgo,
    view_text_website_content,
)

console = Console()

# Real Ollama Client Setup
ollama_model = "qwen3_40k"
ollama_client = ollama.Client("http://localhost:11434")


def _call_agent_interactive_loop(
    agent_name: str,
    prompt_template: str,
    initial_prompt_data: Dict[str, str],
    max_clarification_attempts: int = 1,
    max_tool_uses_per_cycle: int = 2,
) -> str:
    """
    Interact with an agent using the real Ollama client, handling clarification and tool requests.

    Args:
        agent_name: Name of the agent being called.
        prompt_template: The prompt template with placeholders.
        initial_prompt_data: Initial data to fill the prompt template.
        max_clarification_attempts: Maximum number of clarification attempts.
        max_tool_uses_per_cycle: Maximum number of tool uses per cycle.

    Returns:
        The agent's final response as a string.
    """
    current_prompt_data = initial_prompt_data.copy()
    current_prompt_data.setdefault("[[USER_CLARIFICATION]]", "")
    current_prompt_data.setdefault("[[TOOL_OUTPUT]]", "No tool output yet.")
    current_agent_response = (
        f"Error: Agent {agent_name} did not produce an initial valid response."
    )

    # Clarification Phase
    for clar_attempt in range(max_clarification_attempts + 1):
        prompt_for_clar_phase = prompt_template
        temp_prompt_data_for_clar = current_prompt_data.copy()
        if temp_prompt_data_for_clar.get("[[TOOL_OUTPUT]]") == "No tool output yet.":
            temp_prompt_data_for_clar.pop("[[TOOL_OUTPUT]]", None)
        if temp_prompt_data_for_clar.get("[[USER_CLARIFICATION]]") == "":
            temp_prompt_data_for_clar.pop("[[USER_CLARIFICATION]]", None)

        for placeholder, value in temp_prompt_data_for_clar.items():
            prompt_for_clar_phase = prompt_for_clar_phase.replace(
                placeholder, str(value)
            )

        console.print(
            f"[italic gray]Calling {agent_name} (Clarification Phase, Attempt {clar_attempt + 1})...[/italic gray]"
        )
        messages = [{"role": "user", "content": prompt_for_clar_phase}]
        try:
            response = ollama_client.chat(
                model=ollama_model, messages=messages, stream=False
            )
            raw_output_clar = (
                response["message"]["content"]
                if "message" in response and "content" in response["message"]
                else "Error: Invalid response from LLM"
            )
        except Exception as e:
            return f"Error: Exception during {agent_name} call - {e}"

        try:
            potential_json = json.loads(raw_output_clar.strip())
            if (
                isinstance(potential_json, dict)
                and potential_json.get("action") == "request_user_clarification"
            ):
                question = potential_json.get("question", "Missing question")
                if clar_attempt < max_clarification_attempts:
                    console.print(
                        Panel(
                            f"{agent_name} requests clarification:\n[yellow]{question}[/yellow]",
                            title="Agent Clarification Request",
                            border_style="yellow",
                        )
                    )
                    user_resp = Prompt.ask(
                        "Your answer",
                        default="No clarification provided",
                        console=console,
                    )
                    current_prompt_data["[[USER_CLARIFICATION]]"] = (
                        f"\n--- User Clarification ---\nAgent asked: '{question}'\nUser responded: '{user_resp}'\n--- End User Clarification ---"
                    )
                    current_prompt_data["[[TOOL_OUTPUT]]"] = "No tool output yet."
                else:
                    return (
                        f"Error: {agent_name} still needs clarification: '{question}'"
                    )
            else:
                current_agent_response = raw_output_clar
                break
        except json.JSONDecodeError:
            current_agent_response = raw_output_clar
            break

    # Tool Use Phase
    for tool_attempt_num in range(max_tool_uses_per_cycle + 1):
        try:
            potential_json = json.loads(current_agent_response.strip())
            if isinstance(potential_json, dict) and "action" in potential_json:
                action = potential_json["action"]
                if action in ["search_web_duckduckgo", "view_text_website_content"]:
                    tool_output_str = "Error: Tool execution failed."
                    if action == "search_web_duckduckgo" and "query" in potential_json:
                        query = potential_json["query"]
                        tool_output_str = search_web_duckduckgo(query)
                    elif (
                        action == "view_text_website_content"
                        and "url" in potential_json
                    ):
                        url = potential_json["url"]
                        tool_output_str = view_text_website_content(url)
                    current_prompt_data["[[TOOL_OUTPUT]]"] = (
                        f"\n--- Tool Output ---\nAction: {action}\nResult: {tool_output_str}\n--- End Tool Output ---"
                    )
                    prompt_for_next_tool_cycle = prompt_template
                    for placeholder, value in current_prompt_data.items():
                        prompt_for_next_tool_cycle = prompt_for_next_tool_cycle.replace(
                            placeholder, str(value)
                        )
                    messages = [{"role": "user", "content": prompt_for_next_tool_cycle}]
                    try:
                        response = ollama_client.chat(
                            model=ollama_model, messages=messages, stream=False
                        )
                        current_agent_response = (
                            response["message"]["content"]
                            if "message" in response
                            and "content" in response["message"]
                            else "Error: Invalid response from LLM"
                        )
                    except Exception as e:
                        return f"Error: Exception during {agent_name} call after tool use - {e}"
                else:
                    return current_agent_response
            else:
                return current_agent_response
        except json.JSONDecodeError:
            return current_agent_response

    return current_agent_response


def run_project(user_description: str):
    """
    Run the project generation process using the real Ollama client.

    Args:
        user_description: The user's description of the project.
    """
    console.print(
        f"[bold blue]Starting project generation for:[/bold blue] {user_description[:100]}..."
    )

    # Step 1: Reformatting Description
    console.print("\n[bold green]Step 1: Reformatting Description...[/bold green]")
    initial_reformat_data = {"[[USER_DESCRIPTION]]": user_description}
    reformatted_description = _call_agent_interactive_loop(
        "ReformatDescriptionAgent",
        REFORMAT_DESCRIPTION_AGENT_PROMPT,
        initial_reformat_data,
        max_clarification_attempts=1,
        max_tool_uses_per_cycle=0,
    )
    console.print(
        Panel(
            reformatted_description,
            title="Reformatted Description",
            expand=False,
            border_style="blue",
        )
    )

    # Step 2: Generating Project Plan
    console.print("\n[bold green]Step 2: Generating Project Plan...[/bold green]")
    initial_plan_data = {
        "[[USER_DESCRIPTION]]": user_description,
        "[[REFORMATTED_DESCRIPTION]]": reformatted_description,
    }
    raw_plan_output = _call_agent_interactive_loop(
        "PlanningAgent",
        PLANNING_AGENT_PROMPT,
        initial_plan_data,
        max_clarification_attempts=1,
        max_tool_uses_per_cycle=2,
    )
    try:
        project_plan = ProjectPlan(**json.loads(raw_plan_output))
    except Exception as e:
        console.print(f"[red]Error parsing Project Plan: {e}[/red]")
        project_plan = ProjectPlan(
            project_description="Error",
            technical_description=str(e),
            mermaid_diagram="N/A",
        )
    console.print(
        Panel(
            f"Title: {project_plan.project_description}\nTech Dsc: {project_plan.technical_description[:100]}...",
            title="Project Plan Summary",
            expand=False,
            border_style="blue",
        )
    )

    # Step 3: File List Generation
    console.print("\n[bold green]Step 3: File List Generation...[/bold green]")
    plan_json = project_plan.model_dump_json()
    se_prompt = SOFTWARE_ENGINEER_AGENT_PROMPT.replace(
        "[[PROJECT_PLAN_CONTENT]]", plan_json
    )
    messages = [{"role": "user", "content": se_prompt}]
    try:
        response = ollama_client.chat(
            model=ollama_model, messages=messages, stream=False
        )
        raw_se_output = (
            response["message"]["content"]
            if "message" in response and "content" in response["message"]
            else "Error: Invalid response"
        )
        file_list = FileList(**json.loads(raw_se_output))
    except Exception as e:
        console.print(f"[red]Error in File List Generation: {e}[/red]")
        file_list = FileList(files=[])
    console.print(
        Panel(
            f"Files to generate: {len(file_list.files)}",
            title="File List Summary",
            expand=False,
            border_style="blue",
        )
    )

    # Step 4: Code Generation & Review
    console.print("\n[bold green]Step 4: Code Generation & Review...[/bold green]")
    final_code_outputs = {}
    for file_detail in file_list.files:
        initial_coding_data = {
            "[[FILE_PATH]]": file_detail.path,
            "[[FILE_DESCRIPTION]]": file_detail.description,
        }
        code_output = _call_agent_interactive_loop(
            "CodingAgent",
            CODING_AGENT_PROMPT,
            initial_coding_data,
            max_tool_uses_per_cycle=1,
        )
        if not code_output.startswith("Error:"):
            final_code_outputs[file_detail.path] = code_output
            write_code_to_file(file_detail.path, code_output)
    console.print(f"[green]Generated code for {len(final_code_outputs)} files.[/green]")

    # Step 5: Generating Documentation
    console.print("\n[bold green]Step 5: Generating Documentation...[/bold green]")
    for path, code in final_code_outputs.items():
        initial_doc_data = {"[[FILE_PATH]]": path, "[[CODE_CONTENT]]": code}
        doc_output = _call_agent_interactive_loop(
            "DocumentationAgent", DOCUMENTATION_AGENT_PROMPT, initial_doc_data
        )
        if not doc_output.startswith("Error:"):
            doc_json = json.loads(doc_output)
            for doc_path, content in doc_json.items():
                write_code_to_file(doc_path, content)
    create_docs_dir_if_not_exists()
    console.print("[green]Documentation generated.[/green]")


if __name__ == "__main__":
    sample_user_desc = input("What do you want to create?:> ")
    run_project(sample_user_desc)

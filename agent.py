# agent.py
import json
import time
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.prompt import Prompt, Confirm
from typing import Dict, List

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
from lib.tools import (
    write_code_to_file, verify_code, create_docs_dir_if_not_exists,
    search_web_duckduckgo, view_text_website_content
)

try:
    ollama_client = OllamaClient()
except Exception as e:
    print(f"Critical Warning: OllamaClient could not be initialized: {e}. Agent calls WILL FAIL.")
    ollama_client = None
console = Console()

# Global flag for __main__ to control mocking
MOCK_OLLAMA_TOOLS_ACTIVE = False

class MockOllamaClientForTools:
    _call_counts = {}
    _user_desc_input_for_mock = "sample project"
    _clarification_was_processed_for_planning = False

    def generate(self, prompt_str: str) -> str:
        agent_name = "UnknownAgent"
        stripped_prompt = prompt_str.strip()
        # Corrected agent name detection
        if stripped_prompt.startswith("**Role**: AI Reformat Description Agent"): agent_name = "ReformatDescriptionAgent"
        elif stripped_prompt.startswith("**Role**: AI Planning Agent"): agent_name = "PlanningAgent"
        elif stripped_prompt.startswith("**Role**: AI Software Engineer Agent"): agent_name = "SoftwareEngineerAgent"
        elif stripped_prompt.startswith("**Role**: AI Coding Agent"): agent_name = "CodingAgent"
        elif stripped_prompt.startswith("**Role**: AI Senior Engineer Agent"): agent_name = "SeniorEngineerAgent"
        elif stripped_prompt.startswith("**Role**: AI Documentation Agent"): agent_name = "DocumentationAgent"
        else: console.print(f"[bold red][Mock Client Warning] Agent role not detected from prompt prefix. Prompt: '{stripped_prompt[:100]}...'[/bold red]")

        current_call_for_agent = self._call_counts.get(agent_name, 0) + 1
        self._call_counts[agent_name] = current_call_for_agent

        console.print(f"[italic mock]MockOllamaClient: Called for {agent_name} (Agent's call #{current_call_for_agent})[/italic mock]")

        has_clarification_content = "--- User Clarification ---" in prompt_str and "User responded:" in prompt_str
        has_tool_output_content = "--- Tool Output ---" in prompt_str

        console.print(f"[italic mock]State for {agent_name}: call={current_call_for_agent}, has_clar_content={has_clarification_content}, has_tool_content={has_tool_output_content}, _clar_processed_flag={getattr(self, '_clarification_was_processed_for_planning', False)}[/italic mock]")

        if agent_name == "PlanningAgent":
            if current_call_for_agent == 1:
                console.print(f"[italic mock]PlanningAgent: Path 1 (Call {current_call_for_agent}). Requesting clarification.[/italic mock]")
                self._clarification_was_processed_for_planning = False
                return json.dumps({"action": "request_user_clarification", "question": f"Mock question from PlanningAgent: What is the main goal of '{self._user_desc_input_for_mock[:20]}'?"})

            elif current_call_for_agent == 2:
                console.print(f"[italic mock]PlanningAgent: Path 2 (Call {current_call_for_agent}). Clarification received. Requesting tool.[/italic mock]")
                self._clarification_was_processed_for_planning = True
                return json.dumps({"action": "search_web_duckduckgo", "query": f"info on {self._user_desc_input_for_mock[:20]}"})

            # Path 3: Tool output has been incorporated. Generate plan.
            # This path is taken if has_tool_output_content is true for the incoming prompt_str.
            elif current_call_for_agent >= 3 and has_tool_output_content:
                tool_output_summary = "Tool output error or not parsed." # Default
                start_marker_tool = "resulted in:\n" # This is from the prompt construction in _call_agent_interactive_loop
                end_marker_tool = "\n--- End Tool Output ---"
                start_idx_tool = prompt_str.find(start_marker_tool)
                if start_idx_tool != -1:
                    end_idx_tool = prompt_str.find(end_marker_tool, start_idx_tool)
                    if end_idx_tool != -1:
                        tool_output_summary = prompt_str[start_idx_tool + len(start_marker_tool) : end_idx_tool].strip()

                console.print(f"[italic mock]PlanningAgent: Path 3 (Call {current_call_for_agent}). Tool output ('{tool_output_summary[:60]}...'). Generating plan.[/italic mock]")
                # Simplified JSON to match current ProjectPlan Pydantic model in lib/models.py
                return json.dumps({
                    "project_description": f"Mock Plan for '{self._user_desc_input_for_mock[:20]}' (clarified, tool used: {tool_output_summary[:30]}...)",
                    "technical_description": f"Detailed technical breakdown for '{self._user_desc_input_for_mock[:20]}' including architecture (Modular), components (CoreSim), and data models (Particle), incorporating insights from web search: {tool_output_summary}",
                    "mermaid_diagram": "graph TD;\n    Input-->CoreSim;\n    CoreSim-->Output;"
                })
            else: # Fallback or unexpected state for PlanningAgent
                 # This case might be hit if max_tool_uses is exceeded and the last agent response was a tool request.
                 console.print(f"[italic mock]PlanningAgent: Fallback/Error Path (Call {current_call_for_agent}). Current prompt did not contain expected tool output after tool request. Generating error response or basic plan.[/italic mock]")
                 return f"Error: PlanningAgent mock in unexpected state for call {current_call_for_agent} (has_clar_text={has_clarification_content}, has_tool_text={has_tool_output_content}, clar_flag={self._clarification_was_processed_for_planning})"

        elif agent_name == "ReformatDescriptionAgent":
             return f"Mock reformatted description of '{self._user_desc_input_for_mock[:30]}'."
        elif agent_name == "SoftwareEngineerAgent": # For Step 3
             return json.dumps({"files": [{"path": "src/simulation_core.py", "description":"Core CUDA simulation logic."}]})
        elif agent_name == "CodingAgent": return "# Mock code by CodingAgent"
        elif agent_name == "SeniorEngineerAgent": return json.dumps({"review_passed": True, "feedback": "Mock LGTM", "revised_code": None})
        elif agent_name == "DocumentationAgent": return json.dumps({"README.md": "# Mock Readme"})

        return f"Error: No specific mock response defined for {agent_name} (call #{current_call_for_agent}). This indicates an issue in mock logic or agent name detection."


def _call_agent_interactive_loop(
    agent_name: str,
    prompt_template: str,
    initial_prompt_data: Dict[str, str],
    max_clarification_attempts: int = 1,
    max_tool_uses_per_cycle: int = 2
) -> str:
    global ollama_client, console, MOCK_OLLAMA_TOOLS_ACTIVE

    active_client = ollama_client
    if MOCK_OLLAMA_TOOLS_ACTIVE:
        if not isinstance(ollama_client, MockOllamaClientForTools):
            console.print(f"[bold red]Warning: MOCK_OLLAMA_TOOLS_ACTIVE is True, but global ollama_client is not MockOllamaClientForTools instance. Using provided client anyway.[/bold red]")

    if not active_client:
        return f"Error: Ollama client (real or mock) not available for {agent_name}."

    current_prompt_data = initial_prompt_data.copy()
    current_prompt_data.setdefault("[[USER_CLARIFICATION]]", "")
    current_prompt_data.setdefault("[[TOOL_OUTPUT]]", "No tool output yet.")
    current_agent_response = f"Error: Agent {agent_name} did not produce an initial valid response."

    if max_clarification_attempts > 0:
        for clar_attempt in range(max_clarification_attempts + 1):
            prompt_for_clar_phase = prompt_template
            temp_prompt_data_for_clar = current_prompt_data.copy()
            if temp_prompt_data_for_clar.get("[[TOOL_OUTPUT]]") == "No tool output yet.":
                 temp_prompt_data_for_clar.pop("[[TOOL_OUTPUT]]", None)
            if temp_prompt_data_for_clar.get("[[USER_CLARIFICATION]]") == "":
                 temp_prompt_data_for_clar.pop("[[USER_CLARIFICATION]]", None)

            # Add all placeholders from prompt_template that are not yet in temp_prompt_data_for_clar
            # This ensures [[TOOL_OUTPUT]] is in the prompt if the template expects it, even if it's the first tool cycle.
            import re
            placeholders_in_template = re.findall(r"(\[\[[A-Z_]+\]\])", prompt_template)
            for ph in placeholders_in_template:
                temp_prompt_data_for_clar.setdefault(ph, "")


            for placeholder, value in temp_prompt_data_for_clar.items():
                if placeholder in prompt_for_clar_phase: # Only replace if placeholder exists in template
                    prompt_for_clar_phase = prompt_for_clar_phase.replace(placeholder, str(value))
                elif value: # If placeholder not in template but has value (e.g. dynamic like tool output), append
                    prompt_for_clar_phase += f"\n{placeholder}:\n{str(value)}"


            console.print(f"[italic gray]Calling {agent_name} (Clarification Phase, Attempt {clar_attempt + 1})...[/italic gray]")
            raw_output_clar = ""
            try: raw_output_clar = active_client.generate(prompt_for_clar_phase)
            except Exception as e_call: return f"Error: Exception during {agent_name} call - {e_call}"
            if raw_output_clar.startswith("Error:"): return raw_output_clar

            is_clar_req = False; question = ""
            if isinstance(raw_output_clar, str) and raw_output_clar.strip().startswith("{") and raw_output_clar.strip().endswith("}"):
                try:
                    potential_json = json.loads(raw_output_clar.strip())
                    if isinstance(potential_json, dict) and potential_json.get("action") == "request_user_clarification":
                        is_clar_req = True; question = str(potential_json.get("question","Missing question"))
                except json.JSONDecodeError: pass

            if is_clar_req:
                if clar_attempt < max_clarification_attempts:
                    console.print(Panel(f"{agent_name} requests clarification:\n[yellow]{question}[/yellow]",title="Agent Clarification Request",border_style="yellow"))
                    user_resp = "No clarification provided by user (non-interactive or empty)."
                    if console.is_interactive:
                        user_resp_raw = Prompt.ask("Your answer", default="", console=console)
                        if user_resp_raw.strip(): user_resp = user_resp_raw
                    current_prompt_data["[[USER_CLARIFICATION]]"] = f"\n--- User Clarification ---\nAgent previously asked: '{question}'\nUser responded: '{user_resp}'\n--- End User Clarification ---"
                    current_prompt_data["[[TOOL_OUTPUT]]"] = "No tool output yet."
                    console.print(Panel(f"Resuming with: '{user_resp[:100]}...'",title="Clarification Received",border_style="green"))
                else:
                    console.print(f"[yellow]Max clarification attempts ({max_clarification_attempts}) for {agent_name}. Unable to resolve: '{question}'[/yellow]")
                    return f"Error: {agent_name} still needs clarification: '{question}'"
            else:
                current_agent_response = raw_output_clar; break
        else:
            return f"Error: {agent_name} ended clarification cycle still asking questions. Last question: '{question}'" if question else current_agent_response
    else:
        prompt_direct = prompt_template
        temp_prompt_data_direct = current_prompt_data.copy()
        if temp_prompt_data_direct.get("[[TOOL_OUTPUT]]") == "No tool output yet.": temp_prompt_data_direct.pop("[[TOOL_OUTPUT]]", None)
        if temp_prompt_data_direct.get("[[USER_CLARIFICATION]]") == "": temp_prompt_data_direct.pop("[[USER_CLARIFICATION]]", None)

        import re
        placeholders_in_template_direct = re.findall(r"(\[\[[A-Z_]+\]\])", prompt_template)
        for ph_direct in placeholders_in_template_direct:
            temp_prompt_data_direct.setdefault(ph_direct, "")

        for placeholder, value in temp_prompt_data_direct.items():
            if placeholder in prompt_direct:
                prompt_direct = prompt_direct.replace(placeholder, str(value))
            elif value:
                 prompt_direct += f"\n{placeholder}:\n{str(value)}"

        try:
            console.print(f"[italic gray]Calling {agent_name} (Direct, no clarification cycle)...[/italic gray]")
            current_agent_response = active_client.generate(prompt_direct)
        except Exception as e_call: return f"Error: Exception during {agent_name} call - {e_call}"
        if current_agent_response.startswith("Error:"): return current_agent_response

    if current_agent_response.startswith("Error:"): return current_agent_response

    for tool_attempt_num in range(max_tool_uses_per_cycle + 1):
        is_tool_request = False; tool_action = None; tool_params = {}
        if isinstance(current_agent_response, str) and current_agent_response.strip().startswith("{") and current_agent_response.strip().endswith("}"):
            try:
                potential_json = json.loads(current_agent_response.strip())
                if isinstance(potential_json, dict) and "action" in potential_json:
                    action_name = potential_json.get("action")
                    if action_name in ["search_web_duckduckgo", "view_text_website_content"]:
                        is_tool_request = True; tool_action = action_name; tool_params = potential_json
            except json.JSONDecodeError: pass

        if not is_tool_request: return current_agent_response

        if tool_attempt_num < max_tool_uses_per_cycle:
            tool_output_str = f"Error: Tool {tool_action} failed or params missing."
            if tool_action == "search_web_duckduckgo" and "query" in tool_params:
                query = str(tool_params['query'])
                console.print(Panel(f"Agent requests Search: `{query}`", title="Agent Action: Web Search",border_style="blue"))
                tool_output_str = search_web_duckduckgo(query)
            elif tool_action == "view_text_website_content" and "url" in tool_params:
                url = str(tool_params['url'])
                console.print(Panel(f"Agent requests View URL: `{url}`", title="Agent Action: View URL",border_style="blue"))
                tool_output_str = view_text_website_content(url)

            console.print(Panel(f"Tool Output (summary):\n{tool_output_str[:200]}{'...' if len(tool_output_str)>200 else ''}", title="Tool Output", expand=False, border_style="green" if not tool_output_str.startswith("Error:") else "red"))
            current_prompt_data["[[TOOL_OUTPUT]]"] = f"\n\n--- Tool Output ---\nPreviously, you requested action '{tool_action}' with parameters '{json.dumps(tool_params)}'. That action resulted in:\n{tool_output_str}\n--- End Tool Output ---\n"

            prompt_for_next_tool_cycle = prompt_template
            temp_prompt_data_for_tool = current_prompt_data.copy()
            if temp_prompt_data_for_tool.get("[[USER_CLARIFICATION]]") == "": temp_prompt_data_for_tool.pop("[[USER_CLARIFICATION]]", None)

            # Ensure all template placeholders are present for replacement
            import re
            placeholders_in_template_tool = re.findall(r"(\[\[[A-Z_]+\]\])", prompt_template)
            for ph_tool in placeholders_in_template_tool:
                temp_prompt_data_for_tool.setdefault(ph_tool, "")

            for placeholder, value in temp_prompt_data_for_tool.items():
                if placeholder in prompt_for_next_tool_cycle:
                    prompt_for_next_tool_cycle = prompt_for_next_tool_cycle.replace(placeholder, str(value))
                elif value and value != "No tool output yet." and value != "": # Append if not a default empty value
                     prompt_for_next_tool_cycle += f"\n{placeholder}:\n{str(value)}"


            console.print(f"[italic gray]Re-calling {agent_name} with tool output (Tool Cycle Attempt {tool_attempt_num + 1})...[/italic gray]")
            try: current_agent_response = active_client.generate(prompt_for_next_tool_cycle)
            except Exception as e_call: return f"Error: Exception during {agent_name} call after tool use - {e_call}"
            if current_agent_response.startswith("Error:"): return current_agent_response
        else:
            console.print(f"[yellow]Max tool uses ({max_tool_uses_per_cycle}) for {agent_name} in this cycle.[/yellow]")
            return f"Error: {agent_name} may be stuck requesting tools. Last request: {current_agent_response[:200]}"

    return current_agent_response

def run_project(user_description: str):
    global ollama_client, console, MOCK_OLLAMA_TOOLS_ACTIVE
    is_mock_run = MOCK_OLLAMA_TOOLS_ACTIVE

    if not ollama_client and not is_mock_run:
        console.print("[bold yellow]Warning: Ollama client not available and not in active mock mode.[/bold yellow]")
    console.print(f"[bold blue]Starting project generation for:[/bold blue] {user_description[:100]}...")

    # Step 1
    console.print("\n[bold green]Step 1: Reformatting Description...[/bold green]")
    reformatted_description = user_description
    if ollama_client or is_mock_run:
        try:
            initial_reformat_data = {"[[USER_DESCRIPTION]]": user_description}
            raw_output_reformat = _call_agent_interactive_loop("ReformatDescriptionAgent", REFORMAT_DESCRIPTION_AGENT_PROMPT, initial_reformat_data, max_clarification_attempts=1, max_tool_uses_per_cycle=0)
            if not raw_output_reformat.startswith("Error:") and not (isinstance(raw_output_reformat, str) and raw_output_reformat.strip().startswith("{") and "request_user_clarification" in raw_output_reformat):
                reformatted_description = raw_output_reformat
        except Exception as e: console.print(f"[bold red]Critical error in Reformat Step: {e}[/bold red]")
    else: console.print("[italic yellow]Skipped ReformatDescriptionAgent.[/italic yellow]")
    console.print(Panel(reformatted_description, title="Reformatted Description", expand=False, border_style="blue"))

    # Step 2
    console.print("\n[bold green]Step 2: Generating Project Plan...[/bold green]")
    project_plan = ProjectPlan(project_description="Default Plan", technical_description="N/A", mermaid_diagram="N/A")
    if ollama_client or is_mock_run:
        try:
            initial_plan_data = {"[[USER_DESCRIPTION]]": user_description, "[[REFORMATTED_DESCRIPTION]]": reformatted_description}
            raw_plan_output = _call_agent_interactive_loop("PlanningAgent", PLANNING_AGENT_PROMPT, initial_plan_data, max_clarification_attempts=1, max_tool_uses_per_cycle=2)

            final_output_is_action = False
            if isinstance(raw_plan_output, str) and raw_plan_output.strip().startswith("{") and raw_plan_output.strip().endswith("}"):
                try:
                    potential_action = json.loads(raw_plan_output.strip())
                    if isinstance(potential_action, dict) and potential_action.get("action") in ["request_user_clarification", "search_web_duckduckgo", "view_text_website_content"]:
                        final_output_is_action = True
                        console.print(f"[red]PlanningAgent ended by requesting action: {potential_action.get('action')}. Plan may be incomplete.[/red]")
                        project_plan = ProjectPlan(project_description="Plan (Agent Stuck Requesting Action/Clarification)", technical_description=raw_plan_output, mermaid_diagram="N/A")
                except json.JSONDecodeError: pass

            if not raw_plan_output.startswith("Error:") and not final_output_is_action:
                try:
                    json_start = raw_plan_output.find('{'); json_end = raw_plan_output.rfind('}') + 1
                    if json_start != -1 and json_end > json_start:
                        project_plan = ProjectPlan(**json.loads(raw_plan_output[json_start:json_end]))
                    else:
                        project_plan = ProjectPlan(project_description="Plan (Raw Text, Not JSON)", technical_description=raw_plan_output, mermaid_diagram="N/A")
                except Exception as e_parse:
                    console.print(f"[red]Error parsing Project Plan from agent output: {e_parse}. Raw output was: {raw_plan_output[:300]}[/red]")
                    project_plan = ProjectPlan(project_description="Plan (Parse Error on Final Output)", technical_description=raw_plan_output, mermaid_diagram="N/A")
        except Exception as e: console.print(f"[bold red]Critical error in Planning Step: {e}[/bold red]")
    else: console.print("[italic yellow]Skipped PlanningAgent.[/italic yellow]")
    console.print(Panel(f"Title: {project_plan.project_description}\nTech Dsc: {project_plan.technical_description[:100]}...", title="Project Plan Summary", expand=False, border_style="blue"))

    active_ollama_for_later_steps = ollama_client

    console.print("\n[bold green]Step 3: File List Generation...[/bold green]")
    file_list = FileList(files=[])
    if active_ollama_for_later_steps:
        try:
            plan_json = project_plan.model_dump_json()
            se_prompt = SOFTWARE_ENGINEER_AGENT_PROMPT.replace("[[PROJECT_PLAN_CONTENT]]", plan_json)
            raw_se_output = active_ollama_for_later_steps.generate(se_prompt) # Direct call
            if not raw_se_output.startswith("Error:"):
                 try:
                     json_start_se = raw_se_output.find('{'); json_end_se = raw_se_output.rfind('}') + 1
                     if json_start_se != -1 and json_end_se > json_start_se:
                         file_list = FileList(**json.loads(raw_se_output[json_start_se:json_end_se]))
                     else: console.print(f"[red]SE Agent: Output not valid JSON: {raw_se_output[:100]}[/red]")
                 except Exception as e_parse_se: console.print(f"[red]SE Agent: Failed to parse JSON output: {e_parse_se} Raw: {raw_se_output[:100]}[/red]")
            else: console.print(f"[red]SE Agent Error: {raw_se_output}[/red]")
        except Exception as e: console.print(f"[red]SE Agent Exception: {e}[/red]")
    else: console.print("[italic yellow]Skipped File List Gen.[/italic yellow]")
    console.print(Panel(f"Files to generate: {len(file_list.files)}",title="File List Summary",expand=False,border_style="blue"))

    console.print("\n[bold green]Step 4: Code Generation & Review... (condensed)[/bold green]")
    final_code_outputs = {}
    if not file_list.files or not active_ollama_for_later_steps:
        console.print("[yellow]Skipping Code Gen (no files or no client).[/yellow]")
    else:
        console.print(f"[italic gray]Simulating code generation for {len(file_list.files)} files...[/italic gray]")
        for file_detail in file_list.files:
            final_code_outputs[file_detail.path] = f"# Mock code for {file_detail.path}"
        console.print(f"[green]Finished mock code generation for {len(final_code_outputs)} files.[/green]")

    console.print("\n[bold green]Step 5: Generating Documentation... (condensed)[/bold green]")
    if not final_code_outputs or not active_ollama_for_later_steps:
        console.print("[yellow]Skipping Documentation (no code or no client).[/yellow]")
    else:
        console.print(f"[italic gray]Simulating documentation for {len(final_code_outputs)} files...[/italic gray]")
        console.print("[green]Finished mock documentation generation.[/green]")

    console.print("\n[bold blue]Project generation process (ReAct demo focused) complete.[/bold blue]")

if __name__ == "__main__":
    sample_user_desc = "Develop a Python library for advanced particle simulations using CUDA."
    console.print("[bold yellow]=== Agentic Coding System - ReAct Pattern Demo ===[/bold yellow]")
    user_desc_input = sample_user_desc

    MOCK_OLLAMA_TOOLS_ACTIVE = True

    console.print(f"[italic gray]Forcing MOCK for demo. Using sample: '{user_desc_input}'[/italic gray]")

    if MOCK_OLLAMA_TOOLS_ACTIVE:
        console.print("[italic magenta]Using MOCK Ollama responses for this ReAct run.[/italic magenta]")
        mock_client_instance = MockOllamaClientForTools()
        mock_client_instance._user_desc_input_for_mock = user_desc_input
        ollama_client = mock_client_instance
    elif ollama_client is not None:
        console.print("[italic green]Attempting to use REAL Ollama client for ReAct run.[/italic green]")
    else:
        console.print("[bold red]Error: No client (real or mock) configured for ReAct. Exiting.[/bold red]")
        exit()

    run_project(user_desc_input)

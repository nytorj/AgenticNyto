# Agentic System for Coding Models

This project is an Agentic System designed to assist with software development tasks using Large Language Models (LLMs) through Ollama.

## Overview

The system aims to automate various parts of the coding lifecycle, including:

*   Understanding project requirements.
*   Generating project plans.
*   Defining file structures.
*   Generating code.
*   Reviewing code.
*   Creating documentation.

## Core Components

The system is being built with the following key Python modules:

*   `agent.py`: Main application logic and Textual User Interface (TUI).
*   `lib/ollama_client.py`: A wrapper for interacting with the Ollama API, allowing communication with various LLMs.
*   `lib/models.py`: Pydantic models defining the data structures used throughout the system (e.g., project plans, file details, review results).
*   `lib/prompts.py`: Manages the prompts used to guide the behavior of different agents (e.g., Planning Agent, Coding Agent).
*   `lib/tools.py`: Contains utility functions for tasks like code verification (linting/formatting) and file I/O.

## Project Plan

The detailed project plan can be found in [PLAN.md](PLAN.md).

## Getting Started

(To be updated as the project progresses - will include setup and usage instructions)

1.  **Prerequisites:**
    *   Python 3.8+
    *   Ollama installed and running (with models like `qwen2:7b` pulled: `ollama pull qwen2:7b`)
2.  **Setup:**
    *   Clone the repository.
    *   Create a virtual environment: `python -m venv .venv`
    *   Activate it: `source .venv/bin/activate` (or `.\.venv\Scriptsctivate` on Windows)
    *   Install dependencies: `pip install -r requirements.txt`
3.  **Running the System:**
    *   (Instructions to be added once `agent.py` is developed)

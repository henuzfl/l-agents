# Repository Guidelines

## Project Structure & Module Organization

Application code lives under `app/`. `app/main.py` creates the FastAPI application, while `app/container.py` wires settings, agents, sessions, and services. HTTP routes and exception handling are in `app/api/`; request and response models are in `app/schemas/`. Core configuration, logging, and application exceptions belong in `app/core/`.

Agent implementations are isolated in `app/agents/manager/` and `app/agents/agent1/` through `agent4/`. Keep each child agent’s factory and prompt in its own directory. Short-term SQLite memory is implemented in `app/memory/`, and orchestration belongs in `app/services/`.

The server-rendered UI uses `app/templates/chat.html` with assets in `app/static/`. Tests are split into `tests/unit/` and `tests/integration/`.

## Build, Test, and Development Commands

- `python -m pip install -e ".[dev]"`: install runtime and development dependencies.
- `uvicorn app.main:app --reload --port 8091`: run the application locally. Port 8000 may be reserved on Windows.
- `pytest`: run the complete offline test suite.
- `ruff check .`: enforce imports, style, and async correctness.
- `python -m compileall app`: verify that application modules compile.
- `python -m app.knowledge.cli {init,rebuild,status}`: manage the pgvector knowledge index.
- `make install`, `make test`, `make lint`, and `make compile`: equivalent shortcuts where Make is available.

## Coding Style & Naming Conventions

Use Python 3.11+ syntax, four-space indentation, complete type annotations, and `async`/`await` for I/O. Ruff enforces a 100-character line limit and the `E`, `F`, `I`, `UP`, `B`, and `ASYNC` rule sets.

Use `snake_case` for modules, functions, and variables; `PascalCase` for classes. Preserve the established names `manager`, `agent1`–`agent4`, `create_agent1()`–`create_agent4()`, and `run_agent1`–`run_agent4`.

## Testing Guidelines

Use pytest and pytest-asyncio. Name files `test_*.py` and tests `test_<behavior>()`. Tests must not call real model APIs or external networks. Inject fake runners or services at API and orchestration boundaries. Add unit tests for configuration and agent structure, plus integration tests for changed HTTP behavior.

## Architecture & Security Constraints

Only the Manager receives a Session. Child agents must remain stateless and must not access Manager history. Only agent1 may register the internal `search_knowledge_base` tool; agent2–agent4 remain tool-free. Keep API keys and database URLs in `.env`; never commit secrets, SQLite data, traces, or raw model requests.

## Commit & Pull Request Guidelines

No Git history is currently available. Use concise imperative commits, preferably Conventional Commit prefixes such as `feat: add chat history UI` or `test: cover session reuse`. Pull requests should describe behavior changes, list validation commands, link relevant issues, and include screenshots for UI changes. Never weaken tests to make a change pass.

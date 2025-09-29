# Modcord Development Workflow
# Development Guide (Modernized)

This short development guide focuses on getting set up quickly and following
the project's conventions. The previous `DEVELOPMENT.md` was archived and
replaced with this concise, actionable reference.

## Prerequisites
- Python 3.11+ recommended (3.10 is supported).
- A virtual environment (venv, tox, or similar).

## Quickstart
1. Create and activate a venv:

```bash
python -m venv .venv
source .venv/bin/activate
```

2. Install project in editable mode:

```bash
pip install -e .
```

3. Run unit tests quickly:

```bash
python -m pytest -q
```

## Project layout and imports
- Source code lives under `src/modcord/` and uses absolute imports (e.g.
	`from modcord.ai import ...`).
- Keep standard-library imports first, third-party second, project-local last.

## Running the bot locally
- Create a `.env` file in the project root with `DISCORD_BOT_TOKEN=...`.
- Start the bot while developing with the entry point or module:

```bash
python -m modcord
# or, when installed editable
modcord
```

## Testing
- Unit tests use `pytest`. Prefer running only changed tests where possible.
- Add tests for new features and include both happy-path and a couple of edge
	cases.

## Code style and linting
- Follow PEP8 and generally use black/ruff for formatting/linting.
- Keep function/method sizes reasonable and prefer small modules.

## Releasing and packaging
- The project uses setuptools; `setup.py` is present for building sdist/wheel.

## Local development tips
- Use `pip install -e .` for iterative development.
- Keep logs under `logs/`; the logging module rotates files automatically.

## Security notes
- Never commit `.env` with secrets. Use CI secrets for automated workflows.

## Contact
- For questions about architecture or APIs, open an issue outlining your
	proposal with enough context for reviewers to reproduce and test locally.

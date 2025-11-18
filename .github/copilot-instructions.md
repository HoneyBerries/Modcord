## Modcord AI Coding Agent Instructions

This guide enables AI agents to work productively in the Modcord Discord moderation bot codebase. It covers architecture, workflows, conventions, and integration points unique to this project.

---

### 1. Architecture Overview
- **Async Py-Cord Bot**: Main entry at `src/modcord/main.py`. Orchestrates bot startup, AI initialization, and event loop.
- **AI Moderation Pipeline**: Core logic in `src/modcord/ai/ai_core.py`, `ai_moderation_processor.py`, and `moderation/moderation_helper.py`. Batches Discord messages, builds prompts, runs vLLM inference, parses/validates responses, and enforces actions.
- **Batching**: `moderation/message_batch_manager.py` uses a global timer (configurable in `config/app_config.yml`) to batch messages from all channels for efficient GPU inference.
- **Config & Persistence**: Guild settings and rules managed in `configuration/guild_settings.py` and persisted to SQLite (`data/app.db`). Default rules and AI settings in `config/app_config.yml`.
- **Manual Commands**: All moderation actions (warn, timeout, kick, ban) are available as slash commands in `bot/moderation_cmds.py` and related cogs.
- **Console UI**: Interactive control via `ui/console.py`.

---

### 2. Developer Workflows
- **Run/Debug**: Use `./start.sh` from project root. It auto-creates/activates a Python 3.12 venv, installs dependencies, applies patches, and launches the bot.
- **Environment**: Place your Discord bot token in `.env` (see README for format). Linux is required for vLLM.
- **Testing**: Run tests with `pytest` (configured via `pytest.ini` and `pyproject.toml`). Coverage reports are generated in `htmlcov/`.
- **Unit Tests**: Focus on utility/data modules in `tests/`. Integration tests require a running Discord bot context.

---

### 3. Project-Specific Patterns & Conventions
- **Global Batching**: All channel batches are processed together in one vLLM call for maximum throughput. See `message_batch_manager.py` and `ai_moderation_processor.py`.
- **Guided Decoding**: AI outputs are constrained by per-channel JSON schemas and xgrammar grammars. See `moderation_parsing.py`.
- **Fail-Safe Defaults**: Any config/AI error results in neutral actions; bot continues operating with manual commands.
- **Config-Driven**: Most runtime behavior (batch window, history depth, rules) is set in `config/app_config.yml` or per-guild settings.
- **Separation of Concerns**: Each layer (intake, batching, AI, parsing, enforcement) is isolated for testability and clarity.
- **Async-First**: All long-running operations are async to avoid blocking the Discord gateway loop.

---

### 4. Integration Points & External Dependencies
- **AI Model**: vLLM, transformers, unsloth, bitsandbytes (see `requirements.txt`). Model path/config in `config/app_config.yml`.
- **Discord API**: Py-Cord (`py-cord`), all bot logic in `src/modcord/bot/`.
- **Database**: SQLite, auto-created at `data/app.db`.
- **Config**: YAML (`pyyaml`), JSON, dotenv.

---

### 5. Key Files & Directories
- `src/modcord/main.py`: Entry point, bot startup.
- `src/modcord/ai/`: AI orchestration and inference.
- `src/modcord/moderation/`: Batching, parsing, enforcement.
- `src/modcord/bot/`: Discord event and command cogs.
- `src/modcord/configuration/`: Config and guild settings management.
- `config/app_config.yml`: Main config (batching, AI, rules).
- `data/app.db`: SQLite database.
- `tests/`: Unit tests.

---

### 6. Example: Adding a Moderation Action
1. Define the action in `moderation/moderation_datatypes.py`.
2. Update parsing logic in `moderation_parsing.py`.
3. Add enforcement in `moderation_helper.py` and `util/discord_utils.py`.
4. Register command in `bot/moderation_cmds.py`.
5. Update config/rules as needed.

---

### 7. Contributor License
See `CONTRIBUTING.md` and `LICENSE.md` for details on commercial license tiers for contributors.

---

For more details, see `LOGIC.md`, `README.md`, and config files. Ask for clarification if any section is unclear or incomplete.
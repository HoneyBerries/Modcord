## Modcord AI Coding Agent Instructions

This guide enables AI agents to work productively in the Modcord Discord moderation bot codebase. It covers architecture, workflows, conventions, and integration points unique to this project.

---

### 1. Architecture Overview
- **Async Py-Cord Bot**: Main entry at `src/modcord/main.py`. Orchestrates bot startup, AI initialization, and event loop.
- **AI Moderation Pipeline**: Core logic in `src/modcord/ai/ai_core.py`, `ai_moderation_processor.py`, and `moderation/moderation_helper.py`. Batches Discord messages, builds prompts, runs vLLM inference, parses/validates responses, and enforces actions.
- **Batching**: `moderation/message_batch_manager.py` uses a global timer (configurable in `config/app_config.yml`) to batch messages from all channels for efficient GPU inference.
- **Config & Persistence**: Guild settings managed in `configuration/guild_settings.py` and persisted to SQLite (`data/app.db`) via the `Database` class. Default rules and AI settings in `config/app_config.yml`.
- **Human Moderator Review System**: When the AI returns a `review` action, the `HumanReviewManager` in `moderation/human_review_manager.py` batches and consolidates review requests per guild, sends interactive embeds with quick-action buttons to configured review channels, and tracks resolution status in the database.
- **Manual Commands**: All moderation actions (warn, timeout, kick, ban) are available as slash commands in `command/moderation_cmds.py` and related cogs.
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
- **Custom Discord ID Types**: Use custom types like `UserID`, `GuildID`, `ChannelID`, `MessageID` from `datatypes/discord_datatypes.py` for type safety and clarity. These wrap Discord snowflake IDs and support equality with both strings and integers.
- **Fail-Safe Defaults**: Any config/AI error results in neutral actions; bot continues operating with manual commands.
- **Config-Driven**: Most runtime behavior (batch window, history depth, rules) is set in `config/app_config.yml` or per-guild settings.
- **Separation of Concerns**: Each layer (intake, batching, AI, parsing, enforcement, review) is isolated for testability and clarity.
- **Async-First**: All long-running operations are async to avoid blocking the Discord gateway loop.
- **Database Class Pattern**: Use `database` to access the singleton `Database` instance. Call methods like `database.log_moderation_action()` and `database.get_past_actions()`.

---

### 4. Integration Points & External Dependencies
- **AI Model**: vLLM, transformers, unsloth, bitsandbytes (see `requirements.txt`). Model path/config in `config/app_config.yml`.
- **Discord API**: Py-Cord (`py-cord`), bot logic in `src/modcord/listener/` (events, messages) and `src/modcord/command/` (slash commands).
- **Database**: SQLite via aiosqlite, auto-created at `data/app.db`. Schema includes `guild_settings`, `moderation_actions`, `review_requests`, and `schema_version` tables.
- **Config**: YAML (`pyyaml`), JSON, dotenv.

---

### 5. Key Files & Directories

**Core Application:**
- `src/modcord/main.py`: Entry point, bot startup.
- `src/modcord/ai/`: AI orchestration (`ai_core.py`) and moderation inference (`ai_moderation_processor.py`).
- `src/modcord/configuration/`: Config and guild settings management.

**Moderation System:**
- `src/modcord/moderation/`: Batching (`message_batch_manager.py`), parsing (`moderation_parsing.py`), enforcement (`moderation_helper.py`), and human review (`human_review_manager.py`).
- `src/modcord/datatypes/`: Type definitions including `action_datatypes.py` (ActionType, ActionData), `discord_datatypes.py` (UserID, GuildID, ChannelID, MessageID), `moderation_datatypes.py` (ModerationUser, ModerationMessage, ModerationChannelBatch), `human_review_datatypes.py`, and `image_datatypes.py`.

**Discord Integration:**
- `src/modcord/listener/`: Event handlers (`events_listener.py`) and message processing (`message_listener.py`).
- `src/modcord/command/`: Slash commands for moderation (`moderation_cmds.py`), settings (`guild_settings_cmds.py`), and debug (`debug_cmds.py`).

**UI Components:**
- `src/modcord/ui/`: Console UI (`console.py`), guild settings panel (`guild_settings_ui.py`), review resolution buttons (`review_ui.py`), and punishment embeds (`action_embed.py`).

**Supporting Systems:**
- `src/modcord/database/database.py`: SQLite database operations via `Database` class singleton.
- `src/modcord/scheduler/`: Scheduled unban operations.
- `src/modcord/rules_cache/`: Server rules caching.
- `src/modcord/history/`: Discord message history fetching.
- `src/modcord/util/`: Utilities including `discord_utils.py`, `image_utils.py`, `format_utils.py`, `review_embed_helper.py`.

**Configuration:**
- `config/app_config.yml`: Main config (batching, AI, rules, system prompt).
- `config/commands.json`: Registered Discord slash commands.
- `data/app.db`: SQLite database.
- `tests/`: Unit tests.

---

### 6. Example: Adding a Moderation Action
1. Add the action type to `ActionType` enum in `datatypes/action_datatypes.py`.
2. Update `ActionData` if new fields are needed.
3. Update parsing logic in `moderation/moderation_parsing.py`.
4. Add enforcement in `moderation/moderation_helper.py` and `util/discord_utils.py`.
5. Register command in `command/moderation_cmds.py`.
6. Update `ACTION_FLAG_FIELDS` in `configuration/guild_settings.py` for guild-level toggles.
7. Update config/rules and system prompt in `config/app_config.yml` as needed.

---

### 7. Human Review System
The review system provides human oversight for ambiguous AI moderation decisions:

- **Triggering**: AI returns `action: "review"` for content requiring human judgment.
- **Batch Consolidation**: `HumanReviewManager` aggregates multiple reviews per guild into a single embed to prevent notification spam.
- **Interactive UI**: Review embeds include buttons for quick actions (Mark Resolved, Warn, Timeout, Kick, Ban, Delete) via `HumanReviewResolutionView`.
- **Context Enrichment**: Embeds display flagged user's 7-day moderation history, message content, jump links, and attached images.
- **Persistence**: Reviews tracked in `review_requests` database table with batch ID, status, and resolution audit trail.
- **Configuration**: Guilds configure review channels via `/mods add-channel` and moderator roles via `/mods add-role`.

---

### 8. Contributor License
See `CONTRIBUTING.md` and `LICENSE.md` for details on commercial license tiers for contributors.

---

For more details, see `LOGIC.md`, `IMPLEMENTATION_SUMMARY.md`, `README.md`, and config files. Ask for clarification if any section is unclear or incomplete.
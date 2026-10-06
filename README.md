# Modcord

[![GitHub Repo](https://img.shields.io/badge/repo-HoneyBerries%2FModcord-181717?logo=github)](https://github.com/HoneyBerries/Modcord)
[![Latest Release](https://img.shields.io/github/v/release/HoneyBerries/Modcord?sort=semver)](https://github.com/HoneyBerries/Modcord/releases/latest)
[![Java 25+](https://img.shields.io/badge/java-25%2B-orange?logo=openjdk&logoColor=white)](https://openjdk.org/)
[![License: GPL v3](https://img.shields.io/badge/license-GPLv3-blue.svg)](LICENSE)

An AI-powered Discord moderation bot. Instead of matching keywords, Modcord sends recent conversation history and your server's rules to an LLM and acts on the result, so it can tell "that's fire" in #gaming from an actual threat.

- ✅ Context-aware: reads recent channel history (50 messages by default)
- ✅ Per-server rules and per-channel guidelines
- ✅ Every action is logged with its reasoning
- ✅ Self-hostable, works with any OpenAI-compatible API (OpenAI, Ollama, etc.)
- ✅ Free software under the GPL-3.0

## Contents

- [How it works](#how-it-works)
- [Quick start](#quick-start)
- [Commands](#commands)
- [Configuration](#configuration)
- [Testing](#testing)
- [Data handling and privacy](#data-handling-and-privacy)
- [Contributing](#contributing)
- [License](#license)
- [Support](#support)

## How it works

1. A message arrives and is queued per guild for a short delay (30s by default) so nearby messages are batched.
2. The bot fetches recent history from the channel and loads the guild's rules and channel guidelines from the database.
3. The batch and rules are sent to the configured LLM, which returns structured JSON.
4. The response is parsed into actions (warn, delete, timeout, kick, ban). The user is notified and a summary is posted to the audit log channel.
5. The action is recorded in the database for auditing and appeals.

If nothing is wrong, the message is left alone. LLM calls are retried (Resilience4j), and the last success/failure time is shown in `/status`.

## Quick start

You need Java 25+, PostgreSQL 14+, a [Discord bot token](https://discord.com/developers/applications), and an OpenAI API key or an Ollama instance.

```bash
git clone https://github.com/HoneyBerries/Modcord.git
cd Modcord
cp .env.example .env
```

Fill in `.env`:

```env
DISCORD_BOT_TOKEN=your_discord_bot_token
OPENAI_API_KEY=your_openai_api_key
POSTGRES_DB_PASSWORD=your_database_password
```

Review [`config/app_config.yml`](config/app_config.yml) (database, AI endpoint and model, timing, default rules) and [`config/system_prompt.md`](config/system_prompt.md), then:

```bash
./gradlew run        # run the bot
./gradlew assemble   # build build/libs/modcord-all.jar
./gradlew runTest    # start and auto-shut down after 5s
```

## Commands

**`/preferences`** configures the bot for your server:
- `ai`: enable or disable AI moderation
- `rules_channel`, `audit_channel`: where rules are read from and actions are logged
- `action`: enable or disable warn, delete, timeout, kick, or ban
- `appeals`: allow or block appeals (default: allow)
- `remove_on_delete`: whether deleted messages leave the queue (default: keep, to catch ghost pings)
- `settings`: interactive view of current preferences
- `reset`: restore defaults

**`/mod`** takes manual action: `warn`, `timeout` (1-40,320 minutes), `kick`, `ban` (1-365 days), `unban`.

**Others:** `/status` (health, ping, uptime), `/exclude` (exempt users, roles, or channels), `/rollback` (undo actions), `/appeal` (appeal or review decisions), `/shutdown`.

## Configuration

`config/app_config.yml` holds the database connection, cache refresh times, moderation timing, retention windows, and AI settings. The database password comes from `POSTGRES_DB_PASSWORD`.

```yaml
moderation:
  moderation_queue_duration: 30     # seconds before a batch is processed
  num_history_context_messages: 50
  history_context_max_age: 86400    # seconds

ai_settings:
  base_url: "https://your-api-endpoint/v1"
  model_name: "your-model-name"
  api_request_timeout: 300          # seconds
```

`config/system_prompt.md` is the system prompt that guides the LLM's decisions. Edit it to fit your community.

## Testing

```bash
./gradlew test              # unit tests, no network
./gradlew integrationTest   # needs Docker for a Testcontainers Postgres
```

Some integration tests also need a live Discord bot or an LLM API key, and skip themselves if those aren't available.

## Data handling and privacy

This describes what the code does. It is not a privacy policy or terms of service. If you run a public instance, you are the operator and need your own policy and terms that match your deployment.

**Stored in PostgreSQL:** guild settings (preferences, rules, channel guidelines, exclusions) and moderation records (target user ID, action, reason, durations, deleted message IDs, reversals, and appeals including the appeal text).

**Not stored:** message content. Messages are held in memory only while a batch is processed. The old `ai_log` table, which held AI conversations, was dropped in migration `changelog-v23.sql`.

**Sent to your LLM provider:** the batch's message text, images, usernames, user IDs, roles, and your guild's rules, sent to the endpoint in `ai_settings.base_url`. That provider's terms govern what happens to it. Pick one that fits your needs, or self-host a model.

**Retention:** a daily task enforces the `retention` settings in `config/app_config.yml`.

| Setting | Default | Effect |
|---------|---------|--------|
| `retention.actions_days` | 365 | Deletes older actions with their appeals, reversals, and deletions. Actions with an open appeal or an unexpired temporary ban are kept. |
| `retention.appeal_text_days` | 90 | Redacts appeal text this long after the appeal is resolved. |

If you change these, update your privacy policy to match.

**Operators** of a self-hosted instance are responsible for publishing their own privacy policy and terms (including that message content goes to a third-party LLM), complying with the [Discord Terms](https://discord.com/terms), [Developer Policy](https://discord.com/developers/docs/policies-and-agreements/developer-policy), and applicable privacy law, and securing their database and credentials. The maintainers do not receive data from self-hosted instances.

## Contributing

Contributions are welcome. Run `./gradlew test` and `./gradlew spotlessApply` before opening a PR. By submitting a contribution you agree it is licensed under the [GPL-3.0](#license) like the rest of the project, and that you have the right to submit it.

## License

Modcord is licensed under the [GNU General Public License v3.0](LICENSE). Earlier versions of this README described a custom license, which no longer applies.

In short (the license text controls):

- You can use, modify, and redistribute Modcord, including commercially, under the GPL.
- If you distribute it or a modified version (source or the compiled JAR), you must do so under the GPL-3.0, provide the corresponding source, mark your changes, and keep the copyright and license notices.
- The GPL-3.0 is not the AGPL. Running a modified version privately, including as a hosted bot, does not require you to publish your source.
- There is no warranty and no liability for moderation decisions, missed violations, or data loss (sections 15 and 16). AI moderation can be wrong, so staff should review actions and appeals.

Modcord depends on third-party libraries (JDA, HikariCP, Liquibase, Resilience4j, and others), each under its own license. It is not affiliated with Discord Inc., OpenAI, or any LLM provider.

Copyright (C) 2026 Henry Ng and Modcord contributors.

## Support

- [GitHub Issues](https://github.com/HoneyBerries/Modcord/issues)
- [GitHub Discussions](https://github.com/HoneyBerries/Modcord/discussions)
- Email: [henry.rainbowfish@gmail.com](mailto:henry.rainbowfish@gmail.com)

## Stack

Java 25, Gradle, JDA, PostgreSQL, Liquibase, Resilience4j, and an OpenAI-compatible API.

The previous Python version is on the [`old-python-version` branch](https://github.com/HoneyBerries/Modcord/tree/old-python-version). It predates the switch to GPL-3.0 and may have different license terms.

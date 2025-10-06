# Contributing to ModCord

Thank you for your interest in contributing! 🎉

---

## 🎁 Contributor Benefits

**Contributors with merged pull requests receive commercial licenses based on contribution value:**

### 🏆 Tier 1 - Full Commercial License (Unlimited Servers)
Requires ONE of:
- 500+ lines of meaningful code
- 3+ significant bug fixes (security, crashes, data loss)
- 2+ substantial features
- 6+ months of active maintenance

**Benefits:**
- Unlimited commercial use
- Any server size
- Lifetime license

### 🥈 Tier 2 - Limited Commercial License (Up to 5,000 members)
Requires ONE of:
- 100+ lines of meaningful code
- 1 significant bug fix
- 1 meaningful feature

**Benefits:**
- Commercial use for servers up to 5,000 members
- Can upgrade to Tier 1 with more contributions

### 🥉 Tier 3 - Small Commercial License (Up to 1,000 members)
Requires ONE of:
- 20+ lines of meaningful code
- Significant documentation (500+ words)
- Comprehensive test coverage for features

**Benefits:**
- Commercial use for servers up to 1,000 members
- Can upgrade to higher tiers with more contributions

### ❌ What Doesn't Count
- Typo fixes or formatting changes
- Minor README tweaks
- Comment-only changes
- Simple dependency updates

### 📊 Tracking Your Contributions
- Your tier status will be noted when your PR is merged
- Multiple contributions accumulate toward higher tiers
- Quality matters more than quantity
- Check your status anytime by opening an issue

---

## How to Contribute

### 1. Fork the Repository
Click the "Fork" button at the top right of this page.

### 2. Clone Your Fork
```bash
git clone https://github.com/YOUR-USERNAME/modcord.git
cd modcord
```

### 3. Create a Branch
```bash
git checkout -b feature/your-feature-name
```

### 4. Make Your Changes
- Write clean, documented code
- Follow the existing code style
- Add tests for new features
- Update documentation as needed

### 5. Run Tests
```bash
source venv/bin/activate
pytest --cov=src
```
Ensure all tests pass and coverage doesn't decrease.

### 6. Commit Your Changes
```bash
git add .
git commit -m "Add: description of your changes"
```

### 7. Push to Your Fork
```bash
git push origin feature/your-feature-name
```

### 8. Open a Pull Request
- Go to the original repository
- Click "New Pull Request"
- Describe your changes clearly
- Reference any related issues

---

## 📋 Contribution Guidelines

### Code Style
- Follow PEP 8 for Python code
- Use meaningful variable and function names
- Add docstrings to functions and classes
- Keep functions focused and single-purpose

### Testing
- Add tests for new features
- Maintain or improve code coverage
- Ensure all existing tests pass

### Documentation
- Update README.md if adding features
- Add docstrings and comments
- Update configuration examples if needed

---

## 🏅 Types of Contributions We Love

- **Bug Fixes**: Find and fix issues
- **New Features**: Add moderation capabilities
- **Performance Improvements**: Optimize AI processing
- **Documentation**: Improve guides and examples
- **Tests**: Increase code coverage

---

# Development Guide

This development guide focuses on getting set up quickly and following the project's conventions.

## Prerequisites
- Python 3.12+ recommended
- A virtual environment (venv, tox, or similar)

## Quickstart

1. **Create and activate a virtual environment**  
   (Use `venv` or `.venv` as you prefer.)

   ```bash
   python -m venv venv
   source venv/bin/activate
   ```

2. **Install project dependencies (do not install the package in editable mode here):**

   ```bash
   pip install -r requirements.txt
   ```

   Note: the repository's current `requirements.txt` may include an editable install of the package (`-e .`). If you'd like to avoid installing the package in editable mode, either remove or comment out that line from `requirements.txt` before running the command, or install the package separately (see step 4).

3. **Create your `.env` file in the project root with your Discord bot token:**

   ```text
   DISCORD_BOT_TOKEN=your_discord_bot_token_here
   ```

4. **(Optional) Install the package non-editably** — if you need the package installed (for example to use the `modcord` console script), install it without `-e`:

   ```bash
   pip install .
   ```

5. **Run tests to verify your setup:**

   ```bash
   python -m pytest -q
   ```

6. **Launch the bot locally:**

   ```bash
   python -m modcord
   # or, after installing the package
   modcord
   ```

   Alternatively, use the provided shell script if available and executable:

   ```bash
   ./start.sh
   ```

**Notes:**
- Source code is in `src/modcord/`.
- Logs are stored in the `logs/` directory.
- Never commit secrets or your `.env` file.
- For more advanced configuration, see comments in `README.md` and other docs in the repo.

---

## Project Layout and Imports

- Source code is under `src/modcord/` and uses absolute imports (e.g., `from modcord.ai import ...`)
- Keep standard-library imports first, third-party second, project-local last

## Running the Bot Locally

- Create a `.env` file in the project root with `DISCORD_BOT_TOKEN=...`
- Start the bot with:
    ```bash
    python -m modcord
    # or, when installed
    modcord
    ```

## Testing

- Unit tests use `pytest`. Prefer running only changed tests where possible.
- Add tests for new features and include both happy-path and a couple of edge cases.

## Code Style and Linting

- Follow PEP8 and generally use black/ruff for formatting/linting.
- Keep function/method sizes reasonable and prefer small modules.

## Releasing and Packaging

- The project uses setuptools (see `setup.py`) and provides a `modcord` console script entry point.

## Local Development Tips

- Use `pip install -r requirements.txt` for dependency installation; install the package non-editably with `pip install .` when needed for the console script.
- Keep logs under `logs/`; the logging module rotates files automatically.

## Security Notes

- Never commit `.env` with secrets. Use CI secrets for automated workflows.

## Contact

- For questions about architecture or APIs, open an issue outlining your proposal with enough context for reviewers to reproduce and test locally.

---
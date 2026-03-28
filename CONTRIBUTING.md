# Contributing to Modcord

Thank you for your interest in contributing to Modcord! Your help is greatly appreciated.

---

## 🎁 Contributor Benefits

We offer commercial licenses to contributors whose pull requests get merged. The license tier is determined by the value and volume of your contributions.

### 🏆 Tier 1 - Full Commercial License (Unlimited Servers)
Requires **one** of the following:
- 500+ lines of meaningful code
- 3+ significant bug fixes (addressing security, crashes, or data loss)
- 2+ substantial features
- 6+ months of active maintenance

**Benefits:**
- Unlimited commercial use on any server size
- Lifetime license

### 🥈 Tier 2 - Limited Commercial License (Up to 5,000 Members)
Requires **one** of the following:
- 100+ lines of meaningful code
- 1 significant bug fix
- 1 meaningful feature

**Benefits:**
- Commercial use for servers with up to 5,000 members
- Can be upgraded to Tier 1 with further contributions

### 🥉 Tier 3 - Small Commercial License (Up to 1,000 Members)
Requires **one** of the following:
- 20+ lines of meaningful code
- Significant documentation updates (500+ words)
- Comprehensive test coverage for a feature

**Benefits:**
- Commercial use for servers with up to 1,000 members
- Can be upgraded to higher tiers with further contributions

### ❌ What Doesn't Count
- Typo fixes or minor formatting changes
- Minor README tweaks
- Comment-only changes
- Simple dependency updates

### 📊 Tracking Your Contributions
- Your tier status will be noted when your PR is merged.
- Multiple contributions accumulate toward higher tiers.
- Quality is valued over quantity.
- To check your status, please open an issue.

---

## How to Contribute

1.  **Fork the Repository**: Click the "Fork" button at the top right of this page.
2.  **Clone Your Fork**:
    ```bash
    git clone https://github.com/HoneyBerries/Modcord.git
    cd modcord
    ```
3.  **Create a Branch**:
    ```bash
    git checkout -b feature/your-feature-name
    ```
4.  **Make Changes**:
    - Write clean, documented code.
    - Follow the existing code style.
    - Add tests for new features.
    - Update documentation as needed.
5.  **Run Tests**:
    ```bash
    # Make sure you have an active virtual environment
    pytest --cov=src
    ```
    Ensure all tests pass and that coverage does not decrease.
6.  **Commit Your Changes**:
    ```bash
    git add .
    git commit -m "feat: A brief description of your changes"
    ```
7.  **Push to Your Fork**:
    ```bash
    git push origin feature/your-feature-name
    ```
8.  **Open a Pull Request**:
    - Go to the original repository.
    - Click "New Pull Request."
    - Describe your changes clearly and reference any related issues.

---

## 📋 Contribution Guidelines

### Code Style
- Follow PEP 8 for Python code.
- Use meaningful variable and function names.
- Add docstrings to public functions and classes.
- Keep functions focused on a single purpose.

### Testing
- Add tests for new features.
- Maintain or improve code coverage.
- Ensure all existing tests pass.

### Documentation
- Update `README.md` if you are adding user-facing features.
- Add docstrings and code comments where necessary.
- Update configuration examples if needed.

---

# Development Guide

This guide will help you get your local development environment set up.

## Prerequisites
- Python 3.12+
- A virtual environment tool (e.g., `venv`)

## Quickstart

1.  **Create and Activate a Virtual Environment**:
    ```bash
    python -m venv venv
    source venv/bin/activate
    ```

2.  **Install Dependencies**:
    Install the required packages from `requirements.txt`. This will also install the project in editable mode.
    ```bash
    pip install -r requirements.txt
    ```

3.  **Set Up Environment Variables**:
    Create a `.env` file in the project root and add your Discord bot token:
    ```
    DISCORD_BOT_TOKEN=your_discord_bot_token_here
    ```

4.  **Run Tests**:
    Verify your setup by running the test suite:
    ```bash
    pytest -q
    ```

5.  **Launch the Bot**:
    You can run the bot directly using the module or the installed script.
    ```bash
    # Using the module
    python -m modcord

    # Or using the script (since the project is installed in editable mode)
    modcord
    ```

## Project Layout
- Source code is located in `src/modcord/`.
- All imports should be absolute (e.g., `from modcord.ai import ...`).
- Group imports in the following order: standard library, third-party, project-local.

## Security
- **Never commit secrets**. Your `.env` file is ignored by Git, but always be careful not to expose tokens or keys. Use environment variables or CI secrets for automated workflows.

## Contact
For questions about architecture or APIs, please open an issue with a detailed proposal.
"""Setup configuration for Modcord Discord Bot."""

from setuptools import setup, find_packages

setup(
    name="modcord",
    version="0.1.0",
    description="A Discord bot for moderation using AI",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.8",
    install_requires=[
        "py-cord",
        "python-dotenv",
        "pyyaml",
    ],
    entry_points={
        "console_scripts": [
            "modcord=modcord.main:main",
        ],
    },
)
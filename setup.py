from setuptools import setup, find_packages

with open("requirements.txt") as f:
    requirements = f.read().splitlines()

setup(
    name="modcord",
    version="0.1.0",
    description="A Discord moderation bot using an AI model.",
    author="Jules",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "modcord=modcord.main:main",
        ],
    },
    python_requires=">=3.10",
)

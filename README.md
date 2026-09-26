# CodeRepair Lab

CodeRepair Lab is an experimental Python project for studying automated code repair. Its central research question is how a single-shot LLM repair baseline compares with an iterative, agentic code-repair workflow.

The project is currently under development. At present, the repository contains the foundational Python package, development tooling, and a validated YAML contract for benchmark task definitions; repair workflows have not yet been implemented.

## Development setup

Python 3.11 or newer is required.

```bash
python -m venv .venv
```

Activate the virtual environment using the command appropriate for your shell, then install the development dependencies:

```bash
python -m pip install -e ".[dev]"
```

Run the checks with:

```bash
python -m pytest
ruff check .
```

## Planned

Future work will introduce the single-shot baseline and iterative workflow incrementally, once their contracts are defined.

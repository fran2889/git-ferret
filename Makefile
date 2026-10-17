.DEFAULT_GOAL := help
PYTHON ?= python3
SOURCES := git_ferret tests scripts
# Every optional-dependency group in pyproject.toml. Kept in one place so a new
# group cannot be added to pyproject.toml and forgotten here.
EXTRAS := audit,build,lint,test,type

.PHONY: help install format format-check lint lint-fix typecheck test coverage build audit clean check ci

help: ## Show this help
	@echo "Usage: make <target>"
	@echo
	@grep -E '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-14s %s\n", $$1, $$2}'

install: ## Install the package and dev tools (editable)
	$(PYTHON) -m pip install -e ".[$(EXTRAS)]"

format: ## Format the code with ruff
	$(PYTHON) -m ruff format $(SOURCES)

format-check: ## Check formatting
	$(PYTHON) -m ruff format --check $(SOURCES)

lint: ## Lint with ruff
	$(PYTHON) -m ruff check $(SOURCES)

lint-fix: ## Lint and apply safe fixes
	$(PYTHON) -m ruff check --fix $(SOURCES)

typecheck: ## Type check with pyright (strict)
	$(PYTHON) -m pyright --pythonpath "$$($(PYTHON) -c 'import sys; print(sys.executable)')"

test: ## Run the test suite
	$(PYTHON) -m pytest

coverage: ## Run tests with a coverage report
	$(PYTHON) -m pytest --cov --cov-report=term-missing --cov-report=xml --cov-report=html

build: ## Build the sdist and wheel
	rm -rf build dist
	$(PYTHON) -m build
	$(PYTHON) -m twine check dist/*

# Two passes, because neither alone is enough. Given a project path, pip-audit
# resolves `[project.dependencies]` only, so every tool installed from the extras
# is invisible to it. `--local` audits what is actually installed, which in CI
# is this job's own `.[audit]` extra. `--strict` is on the project pass alone: a
# dependency that will not resolve there means the project metadata is broken and
# that should fail, while `--local` legitimately skips anything already installed
# from elsewhere.
audit: ## Audit dependencies for known vulnerabilities
	$(PYTHON) -m pip_audit . --skip-editable --strict --progress-spinner off
	$(PYTHON) -m pip_audit --local --skip-editable --progress-spinner off

clean: ## Remove build artifacts and caches
	rm -rf build dist .pytest_cache .ruff_cache htmlcov .coverage coverage.xml

check: format-check lint typecheck test ## Run the fast local checks

ci: format-check lint typecheck coverage build audit ## Run everything the CI pipeline checks

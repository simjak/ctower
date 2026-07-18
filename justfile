set shell := ["bash", "-euo", "pipefail", "-c"]

python := env_var_or_default("PYTHON", "python3")

default:
    @just --list

# Warm, non-mutating developer and CI gate.
check: python-check web-check repository-tests contract-tests secrets-worktree
    {{python}} -m tools.checks --root . --profile fast

python-check:
    ruff format --check tools/checks tests/repository tests/contracts
    ruff check tools/checks tests/repository tests/contracts
    mypy tools/checks tests/repository tests/contracts
    {{python}} -m compileall -q tools/checks tests/repository tests/contracts

web-check:
    pnpm run format:check
    pnpm run lint
    pnpm run typecheck

repository-tests:
    {{python}} -m unittest discover -s tests/repository -v

contract-tests:
    {{python}} -m unittest discover -s tests/contracts/l0 -v

secrets-worktree:
    pre-commit run gitleaks --all-files

# Full, non-mutating release gate. CI invokes this exact recipe.
verify: check
    {{python}} -m tools.checks --root . --profile full
    {{python}} -m tools.checks --root . --profile full --execute-suites
    {{python}} -m pytest --cov=tools.checks --cov-branch --cov-fail-under=90 tests/repository
    pnpm run test:e2e
    gitleaks git . --no-banner
    git diff --check
    git diff --exit-code

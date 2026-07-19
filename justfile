set shell := ["bash", "-euo", "pipefail", "-c"]

python := env_var_or_default("PYTHON", "python3")
gitleaks := env_var_or_default("GITLEAKS", "gitleaks")
export PYTHONDONTWRITEBYTECODE := "1"

default:
    @just --list

# Warm, non-mutating developer and CI gate.
check: python-check web-check docs-check workflow-check version-check repository-tests contract-tests traceability-check secrets-intended-tree
    {{python}} -m tools.checks --root . --profile fast

python-check: compatibility-coverage
    {{python}} -m ruff format --check tools/checks tools/compatibility tests/repository tests/contracts tests/compatibility
    {{python}} -m ruff check --no-cache tools/checks tools/compatibility tests/repository tests/contracts tests/compatibility
    {{python}} -m mypy --no-incremental tools/checks tools/compatibility tests/repository tests/contracts tests/compatibility

compatibility-coverage:
    @coverage_file="$(mktemp)"; trap 'rm -f "$coverage_file"' EXIT; COVERAGE_FILE="$coverage_file" {{python}} -m pytest -p no:cacheprovider --cov=tools.compatibility --cov-branch --cov-fail-under=90 tests/compatibility

web-check:
    pnpm run format:check
    pnpm run lint
    pnpm run typecheck

# Documentation builds outside the worktree so checks never create or clean `site/`.
docs-check:
    @site_dir="$(mktemp -d)"; trap 'rm -rf -- "$site_dir"' EXIT; {{python}} -m mkdocs build --strict --site-dir "$site_dir"

docs-serve:
    {{python}} -m mkdocs serve --strict

workflow-check:
    actionlint

version-check:
    {{python}} -c 'import json, sys, tomllib; from pathlib import Path; versions = {"VERSION": Path("VERSION").read_text(encoding="utf-8").strip(), "manifest": json.loads(Path(".release-please-manifest.json").read_text(encoding="utf-8"))["."], "package.json": json.loads(Path("package.json").read_text(encoding="utf-8"))["version"], "pyproject.toml": tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]}; sys.exit(f"version drift: {versions}") if len(set(versions.values())) != 1 else print("version mirrors: " + versions["VERSION"])'

repository-tests:
    {{python}} -m unittest discover -s tests/repository -v

contract-tests:
    {{python}} -m unittest discover -s tests/contracts/l0 -v

traceability-check:
    {{python}} -m tools.checks.traceability --root . --check

# Fixed release-gate porcelain: staged, tracked, untracked, submodule, and non-repository safe.
_verify-clean-tree:
    @git -c color.status=false status --porcelain=v1 --untracked-files=all --ignore-submodules=none | awk 'BEGIN { clean = 1 } { print > "/dev/stderr"; clean = 0 } END { exit clean ? 0 : 1 }'

# Scan exactly Git's tracked plus nonignored-untracked intended tree. Building an external
# view avoids traversing `.git`, ignored dependency trees, caches, or runtime state.
secrets-intended-tree:
    @scan_root="$(mktemp -d)"; config_path="$(pwd -P)/.gitleaks.toml"; trap 'rm -rf -- "$scan_root"' EXIT; while IFS= read -r -d '' file_path; do target="$scan_root/$file_path"; mkdir -p -- "$(dirname -- "$target")"; if [[ -L "$file_path" ]]; then readlink "$file_path" > "$target"; elif [[ -f "$file_path" ]]; then cp -p -- "$file_path" "$target"; fi; done < <(git ls-files --cached --others --exclude-standard -z); cd "$scan_root"; {{gitleaks}} dir . --config "$config_path" --no-banner --redact --verbose

secrets-history:
    {{gitleaks}} git . --config .gitleaks.toml --no-banner --redact --verbose

# Full, non-mutating release gate. CT-L0-007 makes CI invoke this exact recipe.
verify: _verify-clean-tree check
    {{python}} -m tools.checks --root . --profile full --execute-suites
    @coverage_file="$(mktemp)"; trap 'rm -f "$coverage_file"' EXIT; COVERAGE_FILE="$coverage_file" {{python}} -m pytest -p no:cacheprovider --cov=tools.checks --cov-branch --cov-fail-under=90 tests/repository
    @just secrets-history
    git diff --check
    @just _verify-clean-tree

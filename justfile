set shell := ["bash", "-euo", "pipefail", "-c"]

python := env_var_or_default("PYTHON", "python3")
gitleaks := env_var_or_default("GITLEAKS", "gitleaks")
export PYTHONDONTWRITEBYTECODE := "1"

# Authoritative coverage verdict, applied to a machine report emitted by the same run.
# `--cov-fail-under` decides its exit status on `round(total, report precision)` and this
# repository reports at the default precision 0, so pytest-cov prints `FAIL ... not reached`
# and still exits 0 for every total in `[threshold - 0.5, threshold)`. Gates therefore fail
# on the exact measured total, never on pytest's exit status alone.
coverage_gate := "import json, sys; total = json.load(open(sys.argv[1], encoding='utf-8'))['totals']['percent_covered']; required = float(sys.argv[2]); sys.exit(f'coverage gate FAILED: exact total {total:.4f}% is below the required {required:g}%') if total < required else print(f'coverage gate passed: exact total {total:.4f}% meets the required {required:g}%')"

default:
    @just --list

# Warm, non-mutating developer and CI gate.
check: python-check web-check docs-check workflow-check version-check repository-tests contract-tests landing-boundary-coverage codegen-check traceability-check secrets-intended-tree
    {{python}} -m tools.checks --root . --profile fast

python-check: compatibility-coverage
    {{python}} -m ruff format --check apps/ctower-api/src apps/ctowerctl/src packages/ctower-kernel/src tools/checks tools/codegen tools/compatibility tools/development_runtime tools/landing_boundary tools/process_execution.py tools/runtime_manifest tools/runtime_preflight.py tests/repository tests/contracts tests/compatibility tests/integration tests/landing_boundary tests/modules tests/artifact tests/development_runtime tests/acceptance/increment-1
    {{python}} -m ruff check --no-cache apps/ctower-api/src apps/ctowerctl/src packages/ctower-kernel/src tools/checks tools/codegen tools/compatibility tools/development_runtime tools/landing_boundary tools/process_execution.py tools/runtime_manifest tools/runtime_preflight.py tests/repository tests/contracts tests/compatibility tests/integration tests/landing_boundary tests/modules tests/artifact tests/development_runtime tests/acceptance/increment-1
    {{python}} -m mypy --no-incremental apps/ctower-api/src apps/ctowerctl/src packages/ctower-kernel/src tools/checks tools/codegen tools/compatibility tools/development_runtime tools/landing_boundary tools/process_execution.py tools/runtime_manifest tools/runtime_preflight.py generated/python tests/repository tests/contracts tests/compatibility tests/integration tests/landing_boundary tests/modules tests/artifact tests/development_runtime tests/acceptance/increment-1

compatibility-coverage:
    @coverage_file="$(mktemp)"; report_file="$(mktemp)"; trap 'rm -f -- "$coverage_file" "$report_file"' EXIT; COVERAGE_FILE="$coverage_file" {{python}} -m pytest -p no:cacheprovider --cov=tools.compatibility --cov-branch --cov-fail-under=90 --cov-report=term --cov-report=json:"$report_file" tests/compatibility; {{python}} -c "{{coverage_gate}}" "$report_file" 90

landing-boundary-coverage:
    @coverage_file="$(mktemp)"; report_file="$(mktemp)"; trap 'rm -f -- "$coverage_file" "$report_file"' EXIT; COVERAGE_FILE="$coverage_file" {{python}} -m pytest -p no:cacheprovider --cov=tools.landing_boundary --cov-branch --cov-fail-under=90 --cov-report=term --cov-report=json:"$report_file" tests/landing_boundary -q; {{python}} -c "{{coverage_gate}}" "$report_file" 90

product-coverage:
    @coverage_file="$(mktemp)"; report_file="$(mktemp)"; trap 'rm -f -- "$coverage_file" "$report_file"' EXIT; COVERAGE_FILE="$coverage_file" {{python}} -m pytest -p no:cacheprovider --cov=ctower_api --cov=ctower_kernel --cov=ctowerctl --cov-branch --cov-fail-under=90 --cov-report=term --cov-report=json:"$report_file" tests/modules tests/acceptance/increment-1 -q; {{python}} -c "{{coverage_gate}}" "$report_file" 90

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
    {{python}} -m pytest tests/contracts/domain tests/contracts/http tests/contracts/migration tests/contracts/project_delivery tests/contracts/company "tests/contracts/event-feed" -q

codegen-check:
    {{python}} -m tools.codegen --root . --check
    @pycache_dir="$(mktemp -d)"; trap 'rm -rf -- "$pycache_dir"' EXIT; PYTHONPYCACHEPREFIX="$pycache_dir" {{python}} -m compileall -q generated/python

traceability-check:
    {{python}} -m tools.checks.traceability --root . --check

# Fixed release-gate porcelain: staged, tracked, untracked, submodule, and non-repository safe.
_verify-clean-tree:
    @git -c color.status=false status --porcelain=v1 --untracked-files=all --ignore-submodules=none | awk 'BEGIN { clean = 1 } { print > "/dev/stderr"; clean = 0 } END { exit clean ? 0 : 1 }'

# Scan exactly Git's tracked plus nonignored-untracked intended tree. Building an external
# view avoids traversing `.git`, ignored dependency trees, caches, or runtime state.
# The listing is materialized through a file, not a process substitution, so a failing
# `git ls-files` is visible. Raw-versus-consumed byte accounting validates its NUL framing,
# and the scanned count is observed independently from the materialized tree. An empty,
# malformed, or partial corpus refuses. `no leaks found` is trustworthy only with that evidence.
secrets-intended-tree:
    @scan_root="$(mktemp -d)"; file_list="$(mktemp)"; config_path="$(pwd -P)/.gitleaks.toml"; trap 'rm -rf -- "$scan_root" "$file_list"' EXIT; git ls-files --cached --others --exclude-standard -z > "$file_list"; LC_ALL=C; manifest_bytes="$(wc -c < "$file_list")"; listed=0; consumed_bytes=0; skipped=""; while IFS= read -r -d '' file_path; do listed=$((listed + 1)); consumed_bytes=$((consumed_bytes + ${#file_path} + 1)); target="$scan_root/$file_path"; mkdir -p -- "$(dirname -- "$target")"; if [[ -L "$file_path" ]]; then readlink "$file_path" > "$target"; elif [[ -f "$file_path" ]]; then cp -p -- "$file_path" "$target"; else skipped="$skipped $file_path"; fi; done < "$file_list"; scanned="$(find "$scan_root" -type f -printf . | wc -c)"; printf 'secret scan corpus: listed=%s scanned=%s manifest-bytes=%s consumed-bytes=%s\n' "$listed" "$scanned" "$manifest_bytes" "$consumed_bytes"; if [[ "$manifest_bytes" -ne "$consumed_bytes" || "$listed" -eq 0 || "$scanned" -ne "$listed" ]]; then printf 'secret scan corpus is empty or incomplete; refusing to report a clean scan (skipped:%s)\n' "${skipped:- none}" >&2; exit 1; fi; cd "$scan_root"; {{gitleaks}} dir . --config "$config_path" --no-banner --redact --verbose

secrets-history:
    {{gitleaks}} git . --config .gitleaks.toml --no-banner --redact --verbose

# Full, non-mutating release gate. CT-L0-007 makes CI invoke this exact recipe.
verify: _verify-clean-tree check product-coverage
    {{python}} -m tools.checks --root . --profile full --execute-suites
    @coverage_file="$(mktemp)"; report_file="$(mktemp)"; trap 'rm -f -- "$coverage_file" "$report_file"' EXIT; COVERAGE_FILE="$coverage_file" {{python}} -m pytest -p no:cacheprovider --cov=tools.checks --cov-branch --cov-fail-under=90 --cov-report=term --cov-report=json:"$report_file" tests/repository; {{python}} -c "{{coverage_gate}}" "$report_file" 90
    @just secrets-history
    git diff --check
    @just _verify-clean-tree

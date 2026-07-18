"""Generated-manifest drift hook used by the full policy profile."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tools.checks.report import Finding, Severity


def _digest(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def verify_generated_manifest(root: Path, manifest_name: str) -> tuple[Finding, ...]:
    artifacts, load_findings = _load_artifacts(root, manifest_name)
    if artifacts is None:
        return load_findings
    findings: list[Finding] = []
    for index, artifact in enumerate(artifacts):
        findings.extend(_verify_artifact(root, manifest_name, index, artifact))
    return tuple(findings)


def _load_artifacts(
    root: Path, manifest_name: str
) -> tuple[list[object] | None, tuple[Finding, ...]]:
    manifest_path = root / manifest_name
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return None, (
            Finding(
                rule_id="generated.manifest",
                path=manifest_name,
                message=f"generated manifest cannot be loaded: {error}",
                severity=Severity.ERROR,
                observed=1,
                limit=0,
            ),
        )
    if not isinstance(manifest, dict) or manifest.get("schema") != "ctower.generated-manifest/v1":
        return None, (
            Finding(
                rule_id="generated.manifest",
                path=manifest_name,
                message="manifest must use ctower.generated-manifest/v1",
                severity=Severity.ERROR,
                observed=1,
                limit=0,
            ),
        )
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        return None, (
            Finding(
                rule_id="generated.manifest",
                path=manifest_name,
                message="manifest artifacts must be a list",
                severity=Severity.ERROR,
                observed=1,
                limit=0,
            ),
        )
    return artifacts, ()


def _verify_artifact(root: Path, manifest: str, index: int, artifact: object) -> list[Finding]:
    if not isinstance(artifact, dict):
        return [_invalid_entry(manifest, index, "artifact must be an object")]
    required = {"id", "generator", "tool_version", "command", "inputs", "outputs"}
    if set(artifact) != required:
        return [_invalid_entry(manifest, index, f"fields must be exactly {sorted(required)}")]
    findings: list[Finding] = []
    for collection in ("inputs", "outputs"):
        findings.extend(
            _verify_digest_entries(root, manifest, index, collection, artifact[collection])
        )
    return findings


def _invalid_entry(manifest: str, index: int, message: str) -> Finding:
    return Finding(
        rule_id="generated.manifest",
        path=manifest,
        message=f"artifacts[{index}] {message}",
        severity=Severity.ERROR,
        observed=1,
        limit=0,
    )


def _verify_digest_entries(
    root: Path, manifest: str, artifact_index: int, collection: str, value: object
) -> list[Finding]:
    if not isinstance(value, list):
        return [_invalid_entry(manifest, artifact_index, f"{collection} must be a list")]
    findings: list[Finding] = []
    for entry_index, entry in enumerate(value):
        if not isinstance(entry, dict) or set(entry) != {"path", "sha256"}:
            findings.append(
                _invalid_entry(
                    manifest, artifact_index, f"{collection}[{entry_index}] needs path and sha256"
                )
            )
            continue
        relative = str(entry["path"])
        path = root / relative
        expected = str(entry["sha256"])
        if not path.is_file() or _digest(path) != expected:
            findings.append(
                Finding(
                    rule_id="generated.drift",
                    path=relative,
                    message=f"{collection} digest does not match generated manifest",
                    severity=Severity.ERROR,
                    observed=1,
                    limit=0,
                )
            )
    return findings

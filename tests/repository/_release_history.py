"""Raw Git object authority for pre-release repository policy."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_OBJECT_ID = re.compile(r"[0-9a-f]+")
_HEADER_KEY = re.compile(r"[a-z][a-z0-9-]*")
_IDENTITY_HEADER = re.compile(r".+ <[^<>]*> [0-9]+ [+-][0-9]{4}")
_COMMIT_TRAILING_HEADERS = frozenset({"encoding", "gpgsig", "gpgsig-sha256", "mergetag"})
_MULTILINE_HEADERS = frozenset({"gpgsig", "gpgsig-sha256", "mergetag"})
_TAG_NAME = re.compile(r"v[0-9].*")
_TAG_REF_FIELDS = 2


@dataclass(frozen=True)
class RawCommit:
    object_id: str
    parents: tuple[str, ...]
    message: str


@dataclass(frozen=True)
class RawHistory:
    candidate: str
    commits: tuple[RawCommit, ...]
    feature_is_member: bool
    problems: tuple[str, ...]
    telemetry: str


@dataclass(frozen=True)
class RawReleaseTags:
    names: tuple[str, ...]
    problems: tuple[str, ...]


class _RawObjectError(ValueError):
    """A raw object cannot be interpreted without ambiguity."""


class RawHistoryReader:
    """Read commit ancestry, messages, and merged tags from raw Git objects."""

    def __init__(self, root: Path, protected_feature: str) -> None:
        self._root = root
        self._protected_feature = protected_feature

    def walk(self, candidate: str) -> RawHistory:
        object_id_length = len(candidate)
        if not self._valid_object_id(candidate, object_id_length):
            return RawHistory(
                candidate=candidate,
                commits=(),
                feature_is_member=False,
                problems=(f"raw parent walk received invalid candidate object ID {candidate!r}",),
                telemetry="## raw no-replace parent walk",
            )
        pending = [(candidate, False)]
        active: set[str] = set()
        visited: set[str] = set()
        commits: list[RawCommit] = []
        rows: list[str] = []
        problems: list[str] = []
        while pending:
            object_id, leaving = pending.pop()
            if leaving:
                active.remove(object_id)
                visited.add(object_id)
                continue
            if object_id in active:
                rows.append(f"{object_id} cycle=true")
                problems.append(f"raw parent walk cycle detected at {object_id}")
                break
            if object_id in visited:
                continue
            active.add(object_id)
            record, problem, row = self._read_raw_commit(object_id, object_id_length)
            rows.append(row)
            if problem is not None or record is None:
                problems.append(problem or f"raw parent walk could not validate commit {object_id}")
                break
            commits.append(record)
            pending.append((object_id, True))
            pending.extend((parent, False) for parent in reversed(record.parents))
        return RawHistory(
            candidate=candidate,
            commits=tuple(commits),
            feature_is_member=any(
                commit.object_id == self._protected_feature for commit in commits
            ),
            problems=tuple(problems),
            telemetry="## raw no-replace parent walk\n" + "\n".join(rows),
        )

    def merged_release_tags(self, history: RawHistory) -> RawReleaseTags:
        result = self._git_text(
            "--no-replace-objects",
            "for-each-ref",
            "--format=%(refname) %(objectname)",
            "refs/tags",
        )
        if result.returncode != 0:
            return RawReleaseTags(
                (),
                (f"release tag references could not be enumerated: {result.stderr.strip()}",),
            )
        history_ids = {commit.object_id for commit in history.commits}
        object_id_length = len(history.candidate)
        names: list[str] = []
        problems: list[str] = []
        for row in result.stdout.splitlines():
            tag_name, object_id, problem = self._tag_reference(row)
            if problem is not None:
                problems.append(problem)
                continue
            if tag_name is None or object_id is None:
                continue
            target, problem = self._raw_tag_target(
                f"refs/tags/{tag_name}",
                object_id,
                object_id_length,
                history_ids,
            )
            if problem is not None:
                problems.append(problem)
            elif target in history_ids:
                names.append(tag_name)
        return RawReleaseTags(tuple(names), tuple(problems))

    def _tag_reference(
        self,
        row: str,
    ) -> tuple[str | None, str | None, str | None]:
        fields = row.split(" ")
        if len(fields) != _TAG_REF_FIELDS or not fields[0].startswith("refs/tags/"):
            return None, None, f"release tag reference record is malformed: {row!r}"
        reference, object_id = fields
        tag_name = reference.removeprefix("refs/tags/")
        if _TAG_NAME.fullmatch(tag_name) is None:
            return None, None, None
        return tag_name, object_id, None

    def _raw_tag_target(
        self,
        reference: str,
        object_id: str,
        object_id_length: int,
        history_ids: set[str],
    ) -> tuple[str | None, str | None]:
        current = object_id
        expected_type: str | None = None
        seen: set[str] = set()
        try:
            while current not in history_ids:
                self._remember_tag_object(reference, current, seen)
                object_type = self._raw_object_type(
                    reference,
                    current,
                    object_id_length,
                    expected_type,
                )
                if object_type == "commit":
                    break
                current, expected_type = self._read_tag_target(
                    reference,
                    current,
                    object_id_length,
                    object_type,
                )
            self._validate_final_tag_type(reference, current, expected_type)
        except _RawObjectError as error:
            return None, str(error)
        return current, None

    def _remember_tag_object(
        self,
        reference: str,
        object_id: str,
        seen: set[str],
    ) -> None:
        if object_id in seen:
            raise _RawObjectError(f"{reference} has a raw tag-object cycle at {object_id}")
        seen.add(object_id)

    def _validate_final_tag_type(
        self,
        reference: str,
        object_id: str,
        expected_type: str | None,
    ) -> None:
        if expected_type not in {None, "commit"}:
            raise _RawObjectError(f"{reference} declares {expected_type!r} for commit {object_id}")

    def _raw_object_type(
        self,
        reference: str,
        object_id: str,
        object_id_length: int,
        expected_type: str | None,
    ) -> str:
        if not self._valid_object_id(object_id, object_id_length):
            raise _RawObjectError(f"{reference} has invalid object ID {object_id!r}")
        result = self._git_bytes("--no-replace-objects", "cat-file", "-t", object_id)
        if result.returncode != 0:
            raise _RawObjectError(f"{reference} points to missing or unreadable object {object_id}")
        object_type = result.stdout.rstrip(b"\n").decode("ascii", errors="replace")
        if expected_type is not None and object_type != expected_type:
            raise _RawObjectError(
                f"{reference} declares {expected_type!r} for {object_id}, "
                f"but the raw object is {object_type!r}"
            )
        return object_type

    def _read_tag_target(
        self,
        reference: str,
        object_id: str,
        object_id_length: int,
        object_type: str,
    ) -> tuple[str, str]:
        if object_type != "tag":
            raise _RawObjectError(
                f"{reference} resolves to non-commit object {object_id} ({object_type!r})"
            )
        result = self._git_bytes("--no-replace-objects", "cat-file", "-p", object_id)
        if result.returncode != 0:
            raise _RawObjectError(f"{reference} has unreadable raw tag object {object_id}")
        return self._parse_raw_tag(object_id, result.stdout, object_id_length)

    def _parse_raw_tag(
        self,
        object_id: str,
        payload: bytes,
        object_id_length: int,
    ) -> tuple[str, str]:
        headers, _ = self._decode_headers(
            object_id,
            payload,
            f"raw tag object {object_id} is unreadable",
            f"raw tag object {object_id} has malformed headers",
        )
        if [key for key, _ in headers] != ["object", "type", "tag", "tagger"]:
            raise _RawObjectError(f"raw tag object {object_id} has unrecognized header state")
        target, declared_type, tag_name, tagger = (value for _, value in headers)
        if not self._valid_object_id(target, object_id_length):
            raise _RawObjectError(f"raw tag object {object_id} has invalid target object ID")
        if declared_type not in {"commit", "tag"} or not tag_name:
            raise _RawObjectError(f"raw tag object {object_id} has invalid target type or tag name")
        if _IDENTITY_HEADER.fullmatch(tagger) is None:
            raise _RawObjectError(f"raw tag object {object_id} has malformed tagger header")
        return target, declared_type

    def _read_raw_commit(
        self,
        object_id: str,
        object_id_length: int,
    ) -> tuple[RawCommit | None, str | None, str]:
        if not self._valid_object_id(object_id, object_id_length):
            return None, f"raw parent walk encountered invalid object ID {object_id!r}", object_id
        type_result = self._git_bytes(
            "--no-replace-objects",
            "cat-file",
            "-t",
            object_id,
        )
        object_type = type_result.stdout.rstrip(b"\n")
        row = (
            f"{object_id} type_rc={type_result.returncode} "
            f"type={object_type.decode('ascii', errors='replace') or '<empty>'}"
        )
        if type_result.returncode != 0:
            return (
                None,
                f"raw parent walk encountered missing or unreadable object {object_id}",
                row,
            )
        if object_type != b"commit":
            return (
                None,
                f"raw parent walk encountered non-commit object {object_id} "
                f"(type {object_type.decode('ascii', errors='replace')!r})",
                row,
            )
        body_result = self._git_bytes(
            "--no-replace-objects",
            "cat-file",
            "-p",
            object_id,
        )
        row += f" body_rc={body_result.returncode}"
        if body_result.returncode != 0:
            return (
                None,
                f"raw parent walk encountered missing or unreadable commit object {object_id}",
                row,
            )
        try:
            record = self._parse_raw_commit(
                object_id,
                body_result.stdout,
                object_id_length,
            )
        except _RawObjectError as error:
            return None, str(error), row
        row += f" parents={','.join(record.parents) or '<root>'}"
        return record, None, row

    def _parse_raw_commit(
        self,
        object_id: str,
        payload: bytes,
        object_id_length: int,
    ) -> RawCommit:
        headers, message = self._decode_headers(
            object_id,
            payload,
            f"raw parent walk encountered unreadable commit object {object_id}",
            f"raw parent walk encountered malformed commit headers at {object_id}",
        )
        parents, remaining = self._commit_lineage(
            object_id,
            headers,
            object_id_length,
        )
        self._validate_commit_identities(object_id, remaining)
        return RawCommit(object_id, parents, message)

    def _commit_lineage(
        self,
        object_id: str,
        headers: list[tuple[str, str]],
        object_id_length: int,
    ) -> tuple[tuple[str, ...], list[tuple[str, str]]]:
        if not headers or headers[0][0] != "tree":
            raise _RawObjectError(f"raw parent walk commit {object_id} has no leading tree header")
        if not self._valid_object_id(headers[0][1], object_id_length):
            raise _RawObjectError(f"raw parent walk commit {object_id} has invalid tree object ID")
        position = 1
        parents: list[str] = []
        while position < len(headers) and headers[position][0] == "parent":
            parent = headers[position][1]
            if not self._valid_object_id(parent, object_id_length):
                raise _RawObjectError(
                    f"raw parent walk commit {object_id} has invalid parent object ID"
                )
            parents.append(parent)
            position += 1
        return tuple(parents), headers[position:]

    def _validate_commit_identities(
        self,
        object_id: str,
        headers: list[tuple[str, str]],
    ) -> None:
        for position, required in enumerate(("author", "committer")):
            if position >= len(headers) or headers[position][0] != required:
                raise _RawObjectError(
                    f"raw parent walk commit {object_id} has invalid {required} header state"
                )
            if _IDENTITY_HEADER.fullmatch(headers[position][1]) is None:
                raise _RawObjectError(
                    f"raw parent walk commit {object_id} has malformed {required} header"
                )
        if any(key not in _COMMIT_TRAILING_HEADERS for key, _ in headers[2:]):
            raise _RawObjectError(
                f"raw parent walk commit {object_id} has unrecognized trailing headers"
            )

    def _decode_headers(
        self,
        object_id: str,
        payload: bytes,
        unreadable_message: str,
        malformed_message: str,
    ) -> tuple[list[tuple[str, str]], str]:
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError as error:
            raise _RawObjectError(f"{unreadable_message}: {error}") from error
        header_text, separator, message = text.partition("\n\n")
        if not separator or "\r" in header_text:
            raise _RawObjectError(malformed_message)
        return self._parse_headers(header_text, object_id), message

    def _parse_headers(
        self,
        header_text: str,
        object_id: str,
    ) -> list[tuple[str, str]]:
        headers: list[tuple[str, str]] = []
        for line in header_text.split("\n"):
            if line.startswith(" "):
                self._append_header_continuation(headers, line, object_id)
                continue
            key, separator, value = line.partition(" ")
            if not separator or not value or _HEADER_KEY.fullmatch(key) is None:
                raise _RawObjectError(f"raw object {object_id} has a malformed header")
            headers.append((key, value))
        return headers

    def _append_header_continuation(
        self,
        headers: list[tuple[str, str]],
        line: str,
        object_id: str,
    ) -> None:
        if not headers or headers[-1][0] not in _MULTILINE_HEADERS:
            raise _RawObjectError(f"raw object {object_id} has an invalid header continuation")
        key, value = headers[-1]
        headers[-1] = (key, f"{value}\n{line}")

    def _valid_object_id(self, value: str, expected_length: int) -> bool:
        return (
            expected_length in {40, 64}
            and len(value) == expected_length
            and bool(_OBJECT_ID.fullmatch(value))
        )

    def _git_text(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        environment = {
            **os.environ,
            "CTOWER_RELEASE_AUTHORITY_GIT_ARGUMENTS": json.dumps(arguments),
        }
        return subprocess.run(
            (
                sys.executable,
                "-c",
                "import json, os; os.execv('/usr/bin/git', "
                "['/usr/bin/git', *json.loads("
                "os.environ['CTOWER_RELEASE_AUTHORITY_GIT_ARGUMENTS'])])",
            ),
            cwd=self._root,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )

    def _git_bytes(self, *arguments: str) -> subprocess.CompletedProcess[bytes]:
        environment = {
            **os.environ,
            "CTOWER_RELEASE_AUTHORITY_GIT_ARGUMENTS": json.dumps(arguments),
        }
        return subprocess.run(
            (
                sys.executable,
                "-c",
                "import json, os; os.execv('/usr/bin/git', "
                "['/usr/bin/git', *json.loads("
                "os.environ['CTOWER_RELEASE_AUTHORITY_GIT_ARGUMENTS'])])",
            ),
            cwd=self._root,
            env=environment,
            check=False,
            capture_output=True,
        )

"""Private owner-only filesystem and durable syscall choreography."""

from __future__ import annotations

import errno
import fcntl
import os
import re
import stat
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Final, Literal, Self
from uuid import uuid4

__all__ = [
    "DirectoryName",
    "LockTimeoutError",
    "LockedStore",
    "SafeTree",
    "StorageError",
    "StoredFile",
]

DirectoryName = Literal["pending", "accepted", "quarantine", "anchors", "tmp"]

_DIRECTORIES: Final[tuple[DirectoryName, ...]] = (
    "pending",
    "accepted",
    "quarantine",
    "anchors",
    "tmp",
)
_RECORD_NAME = re.compile(
    r"^(?P<sequence>[0-9]{20})\."
    r"(?P<kind>command|accepted_receipt|quarantine_receipt|disposition|"
    r"corrupt_disposition|anchor)\.rec$"
)
_TEMP_NAME = re.compile(r"^\.(?:record|control)-[a-f0-9-]{36}\.tmp$")
_EVIDENCE_NAME = re.compile(r"^torn-[a-f0-9-]{36}\.evidence$")
_NETWORK_FILESYSTEMS = frozenset(
    {
        "9p",
        "afs",
        "ceph",
        "cifs",
        "fuse.sshfs",
        "glusterfs",
        "nfs",
        "nfs4",
        "smb3",
    }
)
_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
_FILE_READ_FLAGS = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
_FILE_CREATE_FLAGS = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW
_MAX_CONTROL_BYTES = 64 * 1024
_MOUNTINFO_MIN_FIELDS = 5
_OWNER_ONLY_PATH_COMPONENTS = 4


class StorageError(RuntimeError):
    """The spool filesystem cannot prove a safe durable operation."""


class LockTimeoutError(StorageError):
    """Another process retained the permanent spool lock beyond policy."""


class ScanLimitError(StorageError):
    """A directory exceeded the bounded scan policy."""


@dataclass(frozen=True, slots=True)
class StoredFile:
    directory: DirectoryName
    name: str
    sequence: int
    kind: str
    size: int


class SafeTree:
    """Open one checked per-origin tree and its permanent lock inode."""

    def __init__(self, path: Path, *, scan_limit: int) -> None:
        self._path = path
        self._scan_limit = scan_limit

    @contextmanager
    def locked(self, timeout: float, *, create: bool = True) -> Iterator[LockedStore]:
        """Create/verify the tree, acquire flock, and yield checked directory FDs."""

        previous_umask = os.umask(0o077)
        root_fd = -1
        lock_fd = -1
        directory_fds: dict[DirectoryName, int] = {}
        store: LockedStore | None = None
        try:
            _refuse_network_filesystem(self._path)
            root_fd = _secure_directory_path(self._path, create=create)
            _verify_directory(root_fd, exact_mode=0o700)
            directory_fds = _open_layout(root_fd, create=create)
            lock_fd = _open_lock(root_fd, create=create)
            _acquire_lock(lock_fd, timeout)
            store = LockedStore(root_fd, lock_fd, directory_fds, self._scan_limit)
            yield store
        except OSError as error:
            raise StorageError(_storage_message(error)) from error
        finally:
            if store is not None:
                store.close()
            else:
                for directory_fd in directory_fds.values():
                    os.close(directory_fd)
            if lock_fd >= 0:
                os.close(lock_fd)
            if root_fd >= 0:
                os.close(root_fd)
            os.umask(previous_umask)


class LockedStore:
    """Checked descriptors and exact durable file operations under flock."""

    def __init__(
        self,
        root_fd: int,
        lock_fd: int,
        directory_fds: dict[DirectoryName, int],
        scan_limit: int,
    ) -> None:
        self._root_fd = root_fd
        self._lock_fd = lock_fd
        self._directories = directory_fds
        self._scan_limit = scan_limit

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc_value, traceback
        for file_descriptor in self._directories.values():
            os.close(file_descriptor)
        self._directories.clear()

    def exists_control(self, name: str) -> bool:
        _validate_control_name(name)
        try:
            file_descriptor = os.open(name, _FILE_READ_FLAGS, dir_fd=self._root_fd)
        except FileNotFoundError:
            return False
        try:
            _verify_file(file_descriptor, exact_mode=0o600)
            return True
        finally:
            os.close(file_descriptor)

    def read_control(self, name: str) -> bytes:
        _validate_control_name(name)
        return _read_checked(self._root_fd, name, _MAX_CONTROL_BYTES)

    def write_control(self, name: str, data: bytes) -> None:
        _validate_control_name(name)
        self._atomic_write("tmp", self._root_fd, name, data)
        os.fsync(self._root_fd)

    def append_record(
        self,
        directory: DirectoryName,
        name: str,
        data: bytes,
        head: bytes,
    ) -> None:
        _parse_record_name(name)
        destination = self._directories[directory]
        self._atomic_write("tmp", destination, name, data)
        os.fsync(destination)
        self._atomic_write("tmp", self._root_fd, "head", head)
        os.fsync(self._root_fd)

    def read_file(self, stored: StoredFile, *, maximum: int) -> bytes:
        return _read_checked(self._directories[stored.directory], stored.name, maximum)

    def scan_records(self) -> tuple[StoredFile, ...]:
        records: list[StoredFile] = []
        seen_sequences: set[int] = set()
        for directory in ("pending", "accepted", "quarantine", "anchors"):
            for name in self._scan_names(directory):
                match = _RECORD_NAME.fullmatch(name)
                if match is None:
                    if directory == "quarantine" and _EVIDENCE_NAME.fullmatch(name):
                        continue
                    raise StorageError(f"unknown entry in {directory}")
                sequence = int(match.group("sequence"))
                if sequence in seen_sequences:
                    raise StorageError("duplicate durable record sequence")
                seen_sequences.add(sequence)
                file_descriptor = os.open(
                    name,
                    _FILE_READ_FLAGS,
                    dir_fd=self._directories[directory],
                )
                try:
                    details = _verify_file(file_descriptor, exact_mode=0o600)
                finally:
                    os.close(file_descriptor)
                records.append(
                    StoredFile(
                        directory=directory,
                        name=name,
                        sequence=sequence,
                        kind=match.group("kind"),
                        size=details.st_size,
                    )
                )
                if len(records) > self._scan_limit:
                    raise ScanLimitError("durable records exceed bounded scan policy")
        return tuple(sorted(records, key=lambda item: item.sequence))

    def move(self, stored: StoredFile, destination: DirectoryName) -> StoredFile:
        if stored.directory == destination:
            return stored
        source_fd = self._directories[stored.directory]
        destination_fd = self._directories[destination]
        os.rename(
            stored.name,
            stored.name,
            src_dir_fd=source_fd,
            dst_dir_fd=destination_fd,
        )
        os.fsync(source_fd)
        os.fsync(destination_fd)
        return StoredFile(
            directory=destination,
            name=stored.name,
            sequence=stored.sequence,
            kind=stored.kind,
            size=stored.size,
        )

    def remove(self, stored: StoredFile) -> None:
        os.unlink(stored.name, dir_fd=self._directories[stored.directory])
        os.fsync(self._directories[stored.directory])

    def recover_temps(self) -> int:
        moved = 0
        for name in self._scan_names("tmp"):
            if _TEMP_NAME.fullmatch(name) is None:
                raise StorageError("unknown temporary spool entry")
            evidence_name = f"torn-{uuid4()}.evidence"
            os.rename(
                name,
                evidence_name,
                src_dir_fd=self._directories["tmp"],
                dst_dir_fd=self._directories["quarantine"],
            )
            moved += 1
        if moved:
            os.fsync(self._directories["tmp"])
            os.fsync(self._directories["quarantine"])
        return moved

    def temporary_count(self) -> int:
        names = self._scan_names("tmp")
        if any(_TEMP_NAME.fullmatch(name) is None for name in names):
            raise StorageError("unknown temporary spool entry")
        return len(names)

    def quarantine_evidence_count(self) -> int:
        return sum(
            1
            for name in self._scan_names("quarantine")
            if _EVIDENCE_NAME.fullmatch(name) is not None
        )

    def close(self) -> None:
        """Release checked subdirectory descriptors; flock/root are caller-owned."""

        self.__exit__(None, None, None)

    def _scan_names(self, directory: DirectoryName) -> tuple[str, ...]:
        with os.scandir(self._directories[directory]) as entries:
            names = tuple(entry.name for entry in entries)
        if len(names) > self._scan_limit:
            raise ScanLimitError(f"{directory} exceeds bounded scan policy")
        return names

    def _atomic_write(
        self,
        temporary_directory: DirectoryName,
        destination_fd: int,
        destination_name: str,
        data: bytes,
    ) -> None:
        temporary_name = f".control-{uuid4()}.tmp"
        if _RECORD_NAME.fullmatch(destination_name) is not None:
            temporary_name = f".record-{uuid4()}.tmp"
        temporary_fd = os.open(
            temporary_name,
            _FILE_CREATE_FLAGS,
            0o600,
            dir_fd=self._directories[temporary_directory],
        )
        try:
            _verify_file(temporary_fd, exact_mode=0o600)
            _write_all(temporary_fd, data)
            os.fsync(temporary_fd)
        finally:
            os.close(temporary_fd)
        os.rename(
            temporary_name,
            destination_name,
            src_dir_fd=self._directories[temporary_directory],
            dst_dir_fd=destination_fd,
        )
        os.fsync(self._directories[temporary_directory])


def _secure_directory_path(path: Path, *, create: bool) -> int:
    absolute = path.absolute()
    if not absolute.is_absolute():
        raise StorageError("spool path must be absolute")
    file_descriptor = os.open("/", _DIRECTORY_FLAGS)
    owner_only_start = len(absolute.parts) - _OWNER_ONLY_PATH_COMPONENTS
    try:
        for index, component in enumerate(absolute.parts[1:], start=1):
            child = _open_path_component(file_descriptor, component, create=create)
            if index >= owner_only_start:
                child = _checked_directory(child)
            os.close(file_descriptor)
            file_descriptor = child
    except BaseException:
        os.close(file_descriptor)
        raise
    else:
        return file_descriptor


def _open_layout(root_fd: int, *, create: bool) -> dict[DirectoryName, int]:
    result: dict[DirectoryName, int] = {}
    try:
        for name in _DIRECTORIES:
            result[name] = _open_or_create_directory(root_fd, name, create=create)
    except BaseException:
        for descriptor in result.values():
            os.close(descriptor)
        raise
    else:
        return result


def _open_or_create_directory(parent_fd: int, name: str, *, create: bool) -> int:
    descriptor = _open_path_component(parent_fd, name, create=create)
    return _checked_directory(descriptor)


def _open_path_component(parent_fd: int, name: str, *, create: bool) -> int:
    try:
        descriptor = os.open(name, _DIRECTORY_FLAGS, dir_fd=parent_fd)
    except FileNotFoundError:
        if not create:
            raise
        try:
            os.mkdir(name, 0o700, dir_fd=parent_fd)
        except FileExistsError:
            pass
        else:
            os.fsync(parent_fd)
        descriptor = os.open(name, _DIRECTORY_FLAGS, dir_fd=parent_fd)
    return descriptor


def _open_lock(root_fd: int, *, create: bool) -> int:
    flags = os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW
    if create:
        flags |= os.O_CREAT
    descriptor = os.open(
        "lock",
        flags,
        0o600,
        dir_fd=root_fd,
    )
    return _checked_file(descriptor)


def _acquire_lock(file_descriptor: int, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while True:
        try:
            fcntl.flock(file_descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            if time.monotonic() >= deadline:
                raise LockTimeoutError("spool lock acquisition timed out") from error
            time.sleep(min(0.05, max(0.001, deadline - time.monotonic())))
        else:
            return


def _verify_directory(file_descriptor: int, *, exact_mode: int) -> os.stat_result:
    details = os.fstat(file_descriptor)
    if not stat.S_ISDIR(details.st_mode):
        raise StorageError("spool path entry is not a directory")
    _verify_owner_mode(details, exact_mode)
    return details


def _verify_file(file_descriptor: int, *, exact_mode: int) -> os.stat_result:
    details = os.fstat(file_descriptor)
    if not stat.S_ISREG(details.st_mode):
        raise StorageError("spool path entry is not a regular file")
    if details.st_nlink != 1:
        raise StorageError("spool file has an unsafe link count")
    _verify_owner_mode(details, exact_mode)
    return details


def _checked_directory(file_descriptor: int) -> int:
    try:
        _verify_directory(file_descriptor, exact_mode=0o700)
    except BaseException:
        os.close(file_descriptor)
        raise
    return file_descriptor


def _checked_file(file_descriptor: int) -> int:
    try:
        _verify_file(file_descriptor, exact_mode=0o600)
    except BaseException:
        os.close(file_descriptor)
        raise
    return file_descriptor


def _verify_owner_mode(details: os.stat_result, exact_mode: int) -> None:
    if details.st_uid != os.geteuid():
        raise StorageError("spool path entry has the wrong owner")
    if stat.S_IMODE(details.st_mode) != exact_mode:
        raise StorageError("spool path entry has unsafe permissions")


def _read_checked(directory_fd: int, name: str, maximum: int) -> bytes:
    descriptor = os.open(name, _FILE_READ_FLAGS, dir_fd=directory_fd)
    try:
        details = _verify_file(descriptor, exact_mode=0o600)
        if details.st_size > maximum:
            raise StorageError("spool file exceeds its bounded size")
        chunks: list[bytes] = []
        remaining = details.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 64 * 1024))
            if not chunk:
                raise StorageError("spool file ended before its declared size")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise StorageError("spool file grew during checked read")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _write_all(file_descriptor: int, data: bytes) -> None:
    written = 0
    while written < len(data):
        count = os.write(file_descriptor, data[written:])
        if count <= 0:
            raise StorageError("durable spool write made no progress")
        written += count


def _parse_record_name(name: str) -> re.Match[str]:
    match = _RECORD_NAME.fullmatch(name)
    if match is None:
        raise StorageError("invalid durable record filename")
    return match


def _validate_control_name(name: str) -> None:
    if name not in {"metadata", "head"}:
        raise StorageError("invalid spool control filename")


def _refuse_network_filesystem(path: Path) -> None:
    filesystem = _filesystem_type(path)
    if filesystem is None or filesystem in _NETWORK_FILESYSTEMS or filesystem.startswith("fuse."):
        raise StorageError("spool requires a local filesystem")


def _filesystem_type(path: Path) -> str | None:
    probe = path.absolute()
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    try:
        mountinfo = Path("/proc/self/mountinfo").read_text(encoding="utf-8")
    except OSError:
        return None
    best_mount = "/"
    best_type: str | None = None
    probe_text = str(probe)
    for line in mountinfo.splitlines():
        candidate = _mount_candidate(line)
        if candidate is None:
            continue
        mountpoint, filesystem_type = candidate
        contains_probe = probe_text == mountpoint or probe_text.startswith(
            mountpoint.rstrip("/") + "/"
        )
        if contains_probe and len(mountpoint) >= len(best_mount):
            best_mount = mountpoint
            best_type = filesystem_type
    return best_type


def _mount_candidate(line: str) -> tuple[str, str] | None:
    before, separator, after = line.partition(" - ")
    if not separator:
        return None
    fields = before.split()
    trailing = after.split()
    if len(fields) < _MOUNTINFO_MIN_FIELDS or not trailing:
        return None
    return fields[4].replace(r"\040", " "), trailing[0]


def _storage_message(error: OSError) -> str:
    if error.errno == errno.ENOSPC:
        return "spool storage is full"
    if error.errno == errno.EIO:
        return "spool storage reported an I/O failure"
    if error.errno in {errno.ELOOP, errno.EMLINK}:
        return "spool path contains an unsafe link"
    return "spool filesystem operation failed closed"

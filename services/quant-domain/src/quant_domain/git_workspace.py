from __future__ import annotations

import os
import re
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import cast


_GIT_PATH = Path("/usr/bin/git")
_OID_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_FILE_PATH_PATTERN = re.compile(
    r"^[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*$"
)
_CALLER_MESSAGE_LIMIT = 1024
_AUTHOR_NAME = "Open Quant Studio"
_AUTHOR_EMAIL = "open-quant-studio@localhost"
_ZERO_OID = "0" * 40


@dataclass(frozen=True)
class GitRevisionIdentity:
    commit_oid: str
    tree_oid: str
    blob_oids: dict[str, str]


class GitWorkspaceError(RuntimeError):
    pass


class GitWorkspaceStore:
    def __init__(self, data_root: Path) -> None:
        self.data_root = Path(data_root).absolute()

    def repository_path(self, project_id: str) -> Path:
        project_uuid = uuid.UUID(project_id)
        git_root = self.data_root / "git"
        repository = git_root / f"{project_uuid}.git"
        resolved_git_root = git_root.resolve()
        resolved_repository = repository.resolve(strict=False)
        try:
            resolved_repository.relative_to(resolved_git_root)
        except ValueError as error:
            raise GitWorkspaceError("repository path is outside the data root") from error
        return repository

    def create_commit(
        self,
        *,
        project_id: str,
        revision_id: str,
        files: dict[str, bytes],
        parent_commit_oids: list[str],
        message: str,
        recorded_at: str,
    ) -> GitRevisionIdentity:
        if len(parent_commit_oids) > 1:
            raise GitWorkspaceError("git workspace supports zero or one parent")
        self._validate_file_paths(files)

        repository = self._ensure_repository(project_id)
        blob_oids = {
            path: self._hash_blob(repository, files[path]) for path in sorted(files)
        }
        tree_root: dict[str, object] = {}
        for path in sorted(blob_oids):
            components = path.split("/")
            node = tree_root
            for component in components[:-1]:
                node = cast(dict[str, object], node.setdefault(component, {}))
            node[components[-1]] = blob_oids[path]
        tree_oid = self._build_tree(repository, tree_root)

        commit_arguments = ["commit-tree", tree_oid]
        if parent_commit_oids:
            commit_arguments.extend(("-p", parent_commit_oids[0]))
        commit_message = (
            f"revision_id: {revision_id}\n\n{message[:_CALLER_MESSAGE_LIMIT]}\n"
        ).encode("utf-8")
        commit_oid = self._decode_oid(
            self._run_git(
                repository,
                commit_arguments,
                input_bytes=commit_message,
                environment_overrides={
                    "GIT_AUTHOR_NAME": _AUTHOR_NAME,
                    "GIT_AUTHOR_EMAIL": _AUTHOR_EMAIL,
                    "GIT_COMMITTER_NAME": _AUTHOR_NAME,
                    "GIT_COMMITTER_EMAIL": _AUTHOR_EMAIL,
                    "GIT_AUTHOR_DATE": recorded_at,
                    "GIT_COMMITTER_DATE": recorded_at,
                },
            )
        )
        return GitRevisionIdentity(
            commit_oid=commit_oid,
            tree_oid=tree_oid,
            blob_oids=blob_oids,
        )

    def protect_revision(
        self,
        *,
        project_id: str,
        revision_id: str,
        commit_oid: str,
    ) -> None:
        if _OID_PATTERN.fullmatch(commit_oid) is None:
            raise GitWorkspaceError("git revision commit id is invalid")
        repository = self._ensure_repository(project_id)
        self._run_git(
            repository,
            ["update-ref", self._revision_ref(revision_id), commit_oid, _ZERO_OID],
        )

    def release_revision(
        self,
        *,
        project_id: str,
        revision_id: str,
        commit_oid: str,
    ) -> None:
        if _OID_PATTERN.fullmatch(commit_oid) is None:
            raise GitWorkspaceError("git revision commit id is invalid")
        repository = self.repository_path(project_id)
        self._run_git(
            repository,
            ["update-ref", "-d", self._revision_ref(revision_id), commit_oid],
        )

    @staticmethod
    def _revision_ref(revision_id: str) -> str:
        return f"refs/oqs/revisions/{uuid.UUID(revision_id)}"

    @staticmethod
    def _validate_file_paths(files: dict[str, bytes]) -> None:
        paths = set(files)
        for path in paths:
            components = path.split("/")
            if (
                len(path) > 240
                or _FILE_PATH_PATTERN.fullmatch(path) is None
                or any(component in {".", ".."} for component in components)
                or any(component.lower() == ".git" for component in components)
            ):
                raise GitWorkspaceError("git workspace file path is invalid")
            for index in range(1, len(components)):
                if "/".join(components[:index]) in paths:
                    raise GitWorkspaceError(
                        "git workspace file path collides with a directory"
                    )

    def _ensure_repository(self, project_id: str) -> Path:
        repository = self.repository_path(project_id)
        if repository.joinpath("HEAD").is_file():
            return repository
        repository.parent.mkdir(parents=True, exist_ok=True)
        self._run_git(repository, ["init", "--bare", "--object-format=sha1"])
        return repository

    def _hash_blob(self, repository: Path, body: bytes) -> str:
        return self._decode_oid(
            self._run_git(
                repository,
                ["hash-object", "-w", "--stdin"],
                input_bytes=body,
            )
        )

    def _build_tree(self, repository: Path, node: dict[str, object]) -> str:
        entries: list[str] = []
        for name in sorted(node):
            value = node[name]
            if isinstance(value, dict):
                object_id = self._build_tree(repository, cast(dict[str, object], value))
                entries.append(f"040000 tree {object_id}\t{name}\n")
            else:
                entries.append(f"100644 blob {value}\t{name}\n")
        return self._decode_oid(
            self._run_git(
                repository,
                ["mktree"],
                input_bytes="".join(entries).encode("utf-8"),
            )
        )

    def _run_git(
        self,
        repository: Path,
        arguments: list[str],
        *,
        input_bytes: bytes | None = None,
        environment_overrides: dict[str, str] | None = None,
    ) -> bytes:
        if not _GIT_PATH.is_file():
            raise GitWorkspaceError("git executable unavailable")
        environment = os.environ.copy()
        environment["GIT_DIR"] = str(repository.resolve(strict=False))
        environment.pop("GIT_WORK_TREE", None)
        environment["GIT_CONFIG_NOSYSTEM"] = "1"
        environment["GIT_CONFIG_GLOBAL"] = os.devnull
        if environment_overrides:
            environment.update(environment_overrides)
        try:
            completed = subprocess.run(
                [str(_GIT_PATH), *arguments],
                env=environment,
                input=input_bytes,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                shell=False,
            )
        except OSError as error:
            raise GitWorkspaceError("git command unavailable") from error
        if completed.returncode != 0:
            raise GitWorkspaceError("git command failed")
        return completed.stdout

    @staticmethod
    def _decode_oid(output: bytes) -> str:
        try:
            object_id = output.decode("ascii").strip()
        except UnicodeDecodeError as error:
            raise GitWorkspaceError("git returned an invalid object id") from error
        if _OID_PATTERN.fullmatch(object_id) is None:
            raise GitWorkspaceError("git returned an invalid object id")
        return object_id

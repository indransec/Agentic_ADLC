"""``git``: one bare repository per use case on the bridge volume (feature 010, research R-05).

The model writes only files of the fill layout (the template's fill points, from ``pilot-lab``),
only on the run's bound branch, as one commit per write. ``main`` is never written by an agent. A
write must name the branch head it read (``parent``); if another write landed since, it is
refused ("branch moved; read again"), and the ref update is an atomic compare-and-swap, so nothing
is lost. ``git`` runs as a subprocess with a fixed argument list, no shell, no hooks, no system or
global configuration and no remotes.
"""

import os
import re
import shutil
import subprocess
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from adlc.tools.bridge.records import Records
from adlc.tools.mcp_app import Call, Handler, ToolFailure

MAIN = "main"
MAX_FILES = 20
MAX_TOTAL = 200_000
MAX_READ = 50_000
SAFE = re.compile(r"[^A-Za-z0-9._-]")
COMMIT = re.compile(r"^[0-9a-f]{40}$")
IDENTITY = {"name": "adlc-agent", "email": "agent@adlc.invalid"}
GIT = shutil.which("git") or "/usr/bin/git"


class GitRepos:
    def __init__(
        self,
        root: Path,
        layout: Callable[[], list[str]],
        records: Records,
        example: Callable[[], dict[str, str]] | None = None,
    ) -> None:
        self.root = root
        self.layout = layout
        self.records = records
        self.example = example or dict
        self.lock = threading.Lock()

    # -------------------------------------------------------------- git plumbing

    def _git(self, repo: Path, *args: str, stdin: str | None = None, check: bool = True) -> str:
        done = self._run(repo, *args, stdin=stdin)
        if check and done.returncode != 0:
            raise ToolFailure(f"failed: git {args[0]}")
        return done.stdout

    def _run(
        self, repo: Path, *args: str, stdin: str | None = None
    ) -> "subprocess.CompletedProcess[str]":
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": str(self.root),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_AUTHOR_NAME": IDENTITY["name"],
            "GIT_AUTHOR_EMAIL": IDENTITY["email"],
            "GIT_COMMITTER_NAME": IDENTITY["name"],
            "GIT_COMMITTER_EMAIL": IDENTITY["email"],
        }
        command = [GIT, "-c", f"core.hooksPath={os.devnull}", f"--git-dir={repo}", *args]
        return subprocess.run(  # noqa: S603 - fixed argument list, no shell
            command, input=stdin, capture_output=True, text=True, env=env, check=False, timeout=30
        )

    def repo(self, usecase_id: str) -> Path:
        repo = self.root / f"{SAFE.sub('-', usecase_id)}.git"
        with self.lock:
            if not (repo / "HEAD").exists():
                repo.parent.mkdir(parents=True, exist_ok=True)
                subprocess.run(  # noqa: S603 - fixed argument list, no shell
                    [GIT, "init", "--bare", "--quiet", "--initial-branch", MAIN, str(repo)],
                    check=True,
                    capture_output=True,
                    env={**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull},
                    timeout=30,
                )
                # 011: main starts with the template's example fill (empty files if none)
                example = self.example()
                files = {name: example.get(name, "") for name in self.layout()}
                tree = self._tree(repo, None, files)
                commit = self._commit(repo, tree, None, "Example fill of the golden template")
                self._git(repo, "update-ref", f"refs/heads/{MAIN}", commit, "")
        return repo

    def _head(self, repo: Path, branch: str) -> str | None:
        out = self._git(
            repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}", check=False
        )
        return out.strip() or None

    def _tree(self, repo: Path, parent: str | None, files: dict[str, str]) -> str:
        entries: dict[str, str] = {}
        if parent is not None:
            for line in self._git(repo, "ls-tree", parent).splitlines():
                meta, _, path = line.partition("\t")
                entries[path] = meta
        for path, text in files.items():
            blob = self._git(repo, "hash-object", "-w", "--stdin", stdin=text).strip()
            entries[path] = f"100644 blob {blob}"
        listing = "".join(f"{meta}\t{path}\n" for path, meta in sorted(entries.items()))
        return self._git(repo, "mktree", stdin=listing).strip()

    def _commit(self, repo: Path, tree: str, parent: str | None, message: str) -> str:
        args = ["commit-tree", tree, *(["-p", parent] if parent else []), "-m", message]
        return self._git(repo, *args).strip()

    # -------------------------------------------------------------- operations

    def _ref(self, repo: Path, branch: str, ref: str | None) -> str:
        wanted = ref or branch
        if wanted not in (MAIN, branch):
            raise ToolFailure(f"refused: only {MAIN} or this run's branch can be read")
        head = self._head(repo, wanted) or self._head(repo, MAIN)
        if head is None:
            raise ToolFailure("not found: the repository has no commits")
        return head

    def list(self, usecase_id: str, branch: str, ref: str | None, path: str | None) -> Any:
        repo = self.repo(usecase_id)
        head = self._ref(repo, branch, ref)
        names = self._git(repo, "ls-tree", "-r", "--name-only", head).splitlines()
        prefix = (path or "").strip("/")
        return {
            "ref": ref or branch,
            "commit": head,
            "files": [n for n in names if not prefix or n.startswith(prefix)],
        }

    def read(self, usecase_id: str, branch: str, ref: str | None, path: str) -> Any:
        repo = self.repo(usecase_id)
        head = self._ref(repo, branch, ref)
        names = set(self._git(repo, "ls-tree", "-r", "--name-only", head).splitlines())
        if path not in names:
            raise ToolFailure(f"not found: {path}")
        text = self._git(repo, "show", f"{head}:{path}")
        return {"path": path, "commit": head, "text": text[:MAX_READ], "cut": len(text) > MAX_READ}

    def write(
        self,
        usecase_id: str,
        branch: str,
        files: dict[str, str],
        message: str,
        parent: str | None,
    ) -> Any:
        if branch == MAIN or not branch:
            raise ToolFailure(f"refused: {MAIN} is never written by an agent")
        allowed = set(self.layout())
        outside = sorted(set(files) - allowed)
        if outside:
            raise ToolFailure(f"refused: {', '.join(outside)} not in the fill layout")
        if not files or len(files) > MAX_FILES or sum(map(len, files.values())) > MAX_TOTAL:
            raise ToolFailure(f"invalid arguments: 1 to {MAX_FILES} files, {MAX_TOTAL} characters")
        if parent is not None and not COMMIT.match(parent):
            raise ToolFailure("invalid arguments: parent must be a commit id")
        repo = self.repo(usecase_id)
        with self.lock:
            head = self._head(repo, branch)
            base = head or self._head(repo, MAIN)
            if head is not None and parent != head:
                raise ToolFailure(
                    f"refused: parent must be the branch head {head} (read it with git_list)"
                )
            if head is None and parent is not None and parent != base:
                raise ToolFailure("refused: branch moved; read again (parent is not the head)")
            tree = self._tree(repo, base, files)
            commit = self._commit(repo, tree, base, message[:500])
            # compare-and-swap: fails if the branch moved since it was read
            moved = self._run(repo, "update-ref", f"refs/heads/{branch}", commit, head or "")
        if moved.returncode != 0:
            raise ToolFailure("refused: branch moved; read again")
        return {"branch": branch, "commit": commit, "files": sorted(files)}

    def open_pull_request(
        self, usecase_id: str, run_id: str, branch: str, title: str, description: str
    ) -> Any:
        repo = self.repo(usecase_id)
        head = self._head(repo, branch)
        if head is None:
            raise ToolFailure("refused: the branch has no commits yet")
        opened = [r for r in self.records.read("pull_requests") if r["usecase_id"] == usecase_id]
        number = f"PR-{len(opened) + 1}"
        self.records.add(
            "pull_requests",
            usecase_id=usecase_id,
            run_id=run_id,
            branch=branch,
            commit=head,
            title=title[:200],
            description=description[:5000],
            pull_request=number,
        )
        return {"pull_request": number, "branch": branch, "commit": head, "target": MAIN}

    def files_at(
        self, usecase_id: str, branch: str, commit: str | None
    ) -> tuple[str, dict[str, str]]:
        """The fill files at a commit of the branch (default its head), for CI."""
        repo = self.repo(usecase_id)
        head = self._head(repo, branch)
        if head is None:
            raise ToolFailure("refused: the branch has no commits yet")
        wanted = commit or head
        if not COMMIT.match(wanted):
            raise ToolFailure("invalid arguments: commit must be a commit id")
        ancestors = set(self._git(repo, "rev-list", head).split())
        if wanted not in ancestors:
            raise ToolFailure("refused: the commit is not on this run's branch")
        layout = set(self.layout())
        names = [
            n
            for n in self._git(repo, "ls-tree", "-r", "--name-only", wanted).splitlines()
            if n in layout
        ]
        return wanted, {n: self._git(repo, "show", f"{wanted}:{n}") for n in names}


def handlers(repos: GitRepos) -> dict[str, Handler]:
    def git_list(call: Call, args: dict[str, Any]) -> Any:
        return repos.list(
            call.claims.usecase_id, call.bound("branch"), args.get("ref"), args.get("path")
        )

    def git_read(call: Call, args: dict[str, Any]) -> Any:
        return repos.read(
            call.claims.usecase_id, call.bound("branch"), args.get("ref"), str(args["path"])
        )

    def git_write(call: Call, args: dict[str, Any]) -> Any:
        files = args.get("files")
        if not isinstance(files, dict):
            raise ToolFailure("invalid arguments: files must be an object of path to text")
        return repos.write(
            call.claims.usecase_id,
            call.bound("branch"),
            {str(k): str(v) for k, v in files.items()},
            str(args.get("message") or ""),
            args.get("parent"),
        )

    def git_open_pull_request(call: Call, args: dict[str, Any]) -> Any:
        return repos.open_pull_request(
            call.claims.usecase_id,
            call.claims.run_id,
            call.bound("branch"),
            str(args.get("title") or ""),
            str(args.get("description") or ""),
        )

    return {
        "git_list": git_list,
        "git_read": git_read,
        "git_write": git_write,
        "git_open_pull_request": git_open_pull_request,
    }

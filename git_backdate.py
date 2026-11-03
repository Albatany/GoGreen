#!/usr/bin/env python3
"""
GoGreen Studio - a contribution-graph atelier for GitHub.

Creates backdated empty commits and pushes them to a repository.  It can paint
pixel art, text, gradients, waves, ripples, streaks and classic heatmaps on the
7 x 53 GitHub contribution calendar.

Requirements : Python 3.8+ and Git.
Optional     : Pillow (only for non-PNG image imports).
Run          : python git_backdate_v2.py

Made by Albatany 2026.
"""
from __future__ import annotations

import json
import math
import os
import random
import re
import shutil
import struct
import subprocess
import sys
import time
import zlib
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from getpass import getpass
from pathlib import Path
from typing import Callable, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

APP_NAME = "GoGreen Studio"
VERSION = "2.0"
AUTHOR = "Albatany"
RELEASE = "2026"

MIN_DATE = date(2008, 1, 1)
WINDOW_START_HOUR = 8
WINDOW_END_HOUR = 20
TZ_SUFFIX = "+0000"
DEFAULT_PUSH_BATCH = 900
BIG_RUN_WARNING = 15_000
ROWS = 7
MAX_WEEKS = 53
LEVEL_COMMITS = (0, 1, 3, 5, 7)

GITHUB_COLORS = ("#161b22", "#0e4429", "#006d32", "#26a641", "#39d353")

# ---------------------------------------------------------------------------
# Terminal / visual language
# ---------------------------------------------------------------------------

def _enable_windows_ansi() -> None:
    if os.name == "nt":
        os.system("")
    # The interface uses box drawing and symbols.  Prefer UTF-8 so the same
    # output works on modern Windows terminals and on POSIX systems whose
    # locale is C/ASCII; replace is a last-resort guard against crashes.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:
            try:
                stream.reconfigure(errors="replace")  # type: ignore[attr-defined]
            except Exception:
                pass


_enable_windows_ansi()

NO_COLOR = bool(os.environ.get("NO_COLOR"))
USE_COLOR = sys.stdout.isatty() and not NO_COLOR


def _can_encode(text: str) -> bool:
    try:
        text.encode(sys.stdout.encoding or "utf-8")
        return True
    except Exception:
        return False


UNICODE = _can_encode("╭─█·▸")


def _rgb(text: str, hex_color: str, bold: bool = False) -> str:
    if not USE_COLOR:
        return text
    value = hex_color.lstrip("#")
    r, g, b = int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
    prefix = "\033[1;" if bold else "\033["
    return f"{prefix}38;2;{r};{g};{b}m{text}\033[0m"


def _ansi(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if USE_COLOR else text


def dim(text: str) -> str:
    return _ansi(text, "2")


def bold(text: str) -> str:
    return _ansi(text, "1")


def cyan(text: str) -> str:
    return _rgb(text, "#39d353")


def violet(text: str) -> str:
    return _rgb(text, "#a78bfa")


def amber(text: str) -> str:
    return _rgb(text, "#fbbf24")


def red(text: str) -> str:
    return _rgb(text, "#f87171")


def green(text: str) -> str:
    return _rgb(text, "#4ade80")


def info(message: str) -> None:
    print(f"  {message}")


def bullet(message: str) -> None:
    print(f"  {dim('·')} {message}")


def good(message: str) -> None:
    print(f"  {green('✓')} {message}")


def warn(message: str) -> None:
    print(f"  {amber('!')} {message}")


def fail(message: str) -> None:
    print(f"  {red('×')} {message}")


def rule(width: int = 66) -> None:
    char = "─" if UNICODE else "-"
    print("  " + dim(char * width))


def banner(title: str, subtitle: Optional[str] = None) -> None:
    print()
    rule()
    print(f"  {green(title.upper())}")
    if subtitle:
        print(f"  {dim(subtitle)}")
    rule()


def header() -> None:
    width = 66
    if UNICODE:
        print()
        print("  " + _rgb("╭" + "─" * width + "╮", "#334155"))
        print("  " + _rgb("│", "#334155") + " " * width + _rgb("│", "#334155"))
        title = "G O G R E E N   S T U D I O"
        pad = width - len(title)
        print("  " + _rgb("│", "#334155") + " " * (pad // 2) + _rgb(title, "#4ade80", True)
              + " " * (pad - pad // 2) + _rgb("│", "#334155"))
        sub = "contribution graph atelier · 2026"
        pad = width - len(sub)
        print("  " + _rgb("│", "#334155") + " " * (pad // 2) + _rgb(sub, "#94a3b8")
              + " " * (pad - pad // 2) + _rgb("│", "#334155"))
        print("  " + _rgb("│", "#334155") + " " * width + _rgb("│", "#334155"))
        print("  " + _rgb("╰" + "─" * width + "╯", "#334155"))
    else:
        print()
        print("  +" + "-" * width + "+")
        print("  |" + "GOGREEN STUDIO".center(width) + "|")
        print("  |" + "contribution graph atelier - 2026".center(width) + "|")
        print("  +" + "-" * width + "+")
    print(f"  {dim('Made by Albatany 2026')}")


def box(lines: Sequence[str], width: int = 66, title: Optional[str] = None) -> None:
    if UNICODE:
        top_left, top_right, bottom_left, bottom_right = "╭", "╮", "╰", "╯"
        horizontal, vertical, tee_left, tee_right = "─", "│", "├", "┤"
    else:
        top_left = top_right = bottom_left = bottom_right = "+"
        horizontal, vertical, tee_left, tee_right = "-", "|", "+", "+"
    print("  " + top_left + horizontal * width + top_right)
    if title:
        label = f" {title} "
        print("  " + tee_left + horizontal * 2 + label + horizontal * (width - len(label) - 2) + tee_right)
    for line in lines:
        visible = re.sub(r"\033\[[0-9;]*m", "", line)
        pad = max(0, width - 2 - len(visible))
        print("  " + vertical + "  " + line + " " * pad + vertical)
    print("  " + bottom_left + horizontal * width + bottom_right)


def fmt_seconds(seconds: float) -> str:
    seconds = int(max(0, seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h{minutes:02d}m"
    if minutes:
        return f"{minutes}m{secs:02d}s"
    return f"{secs}s"


def fmt_int(value: int) -> str:
    return f"{value:,}"


def plural(count: int, singular: str, plural_word: Optional[str] = None) -> str:
    if count == 1:
        return singular
    return plural_word or singular + "s"


# ---------------------------------------------------------------------------
# Prompts and validators
# ---------------------------------------------------------------------------

class AppError(RuntimeError):
    pass


class GitError(AppError):
    pass


class ArtError(AppError):
    pass


class Cancelled(Exception):
    """The user declined a confirmation inside a plan builder."""


def ask(
    prompt: str,
    default: Optional[str] = None,
    validator: Optional[Callable[[str], object]] = None,
    secret: bool = False,
) -> str:
    suffix = f" {dim('[' + str(default) + ']')}" if default not in (None, "") else ""
    while True:
        try:
            raw = (getpass if secret else input)(f"  {prompt}{suffix}: ").strip()
        except EOFError:
            raise KeyboardInterrupt
        if not raw and default is not None:
            raw = str(default)
        if not raw:
            warn("A value is required.")
            continue
        if validator is None:
            return raw
        try:
            validator(raw)
            return raw
        except ValueError as exc:
            warn(str(exc))


def ask_int(prompt: str, minimum: int, maximum: int,
            default: Optional[int] = None) -> int:
    if default is not None:
        default = max(minimum, min(maximum, default))

    def check(raw: str) -> None:
        try:
            number = int(raw.replace(",", "").replace("_", ""))
        except ValueError:
            raise ValueError("Please enter a whole number.")
        if not minimum <= number <= maximum:
            raise ValueError(f"Enter a number between {minimum:,} and {maximum:,}.")

    return int(ask(prompt, None if default is None else str(default), check))


def ask_float(prompt: str, minimum: float, maximum: float,
              default: float) -> float:
    default = max(minimum, min(maximum, default))

    def check(raw: str) -> None:
        try:
            number = float(raw)
        except ValueError:
            raise ValueError("Please enter a number.")
        if not minimum <= number <= maximum:
            raise ValueError(f"Enter a number between {minimum:g} and {maximum:g}.")

    return float(ask(prompt, f"{default:g}", check))


def ask_choice(prompt: str, choices: Sequence[Tuple[str, str]],
               default: str = "1") -> str:
    print()
    for key, label in choices:
        marker = green("›") if key == default else " "
        print(f"   {marker} {bold(key):>3}  {label}")
    while True:
        raw = ask(prompt, default).lower()
        valid = {key.lower() for key, _ in choices}
        if raw in valid:
            return raw
        warn("Choose one of: " + ", ".join(key for key, _ in choices))


def confirm(prompt: str, default: bool = False) -> bool:
    hint = "Y/n" if default else "y/N"
    while True:
        try:
            raw = input(f"  {prompt} {dim('[' + hint + ']')}: ").strip().lower()
        except EOFError:
            raise KeyboardInterrupt
        if not raw:
            return default
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False
        warn("Please answer Y or N.")


def check_username(raw: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9-]+", raw):
        raise ValueError("GitHub usernames only contain letters, digits and hyphens.")
    return raw


def check_email(raw: str) -> str:
    if not re.fullmatch(r"[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+", raw):
        raise ValueError("That does not look like an email address.")
    return raw


def check_author_name(raw: str) -> str:
    if any(c in raw for c in "<>\n\r"):
        raise ValueError("Author name cannot contain <, > or line breaks.")
    if len(raw) > 100:
        raise ValueError("Author name is too long (maximum 100 characters).")
    return raw


def check_token(raw: str) -> str:
    if not raw.strip():
        raise ValueError("A token is required.")
    if any(char.isspace() for char in raw):
        raise ValueError("The token contains whitespace; paste it without spaces.")
    return raw


def check_day(raw: str) -> date:
    try:
        day = datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError("Use the format YYYY-MM-DD (for example 2024-04-01).")
    if day < MIN_DATE:
        raise ValueError(f"Date must be on or after {MIN_DATE.isoformat()}.")
    if day > date.today():
        raise ValueError("Date cannot be in the future.")
    return day


def parse_repo_url(raw: str) -> Tuple[str, str]:
    """Accept HTTPS, SSH, scp-like, or plain owner/repo GitHub URLs."""
    text = raw.strip()
    pattern = re.compile(
        r"^(?:(?:https?|ssh|git)://)?(?:[^@/\s]+@)?(?:www\.)?github\.com"
        r"(?::\d+)?[:/]+(.+)$",
        re.I,
    )
    match = pattern.match(text)
    if match:
        text = match.group(1)
    text = text.split("?")[0].split("#")[0].strip("/")
    parts = [part for part in text.split("/") if part]
    if len(parts) < 2:
        raise ValueError(
            "Could not find owner/repo. Expected https://github.com/<owner>/<repo>."
        )
    owner, repo = parts[0], re.sub(r"\.git$", "", parts[1], flags=re.I)
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", owner) or not re.fullmatch(
        r"[A-Za-z0-9_.-]+", repo
    ):
        raise ValueError("Owner or repository name contains unsupported characters.")
    return owner, repo


def check_branch(raw: str) -> str:
    if raw in ("HEAD", "FETCH_HEAD", "ORIG_HEAD", "MERGE_HEAD"):
        raise ValueError("That name is reserved by Git; choose another branch.")
    if raw.startswith("-") or any(c in raw for c in " ~^:?*[\\\n\r\t"):
        raise ValueError("That is not a valid Git branch name.")
    if raw.endswith(("/", ".", ".lock")) or ".." in raw or "@{" in raw:
        raise ValueError("That is not a valid Git branch name.")
    return raw


def sunday_on_or_before(day: date) -> date:
    return day - timedelta(days=(day.weekday() + 1) % 7)


def saturday_on_or_before(day: date) -> date:
    return day - timedelta(days=(day.weekday() - 5) % 7)


def saturday_on_or_after(day: date) -> date:
    return day + timedelta(days=(5 - day.weekday()) % 7)


def week_row(day: date) -> int:
    """Sunday=0 ... Saturday=6."""
    return (day.weekday() + 1) % 7


def days_between(start: date, end: date) -> List[date]:
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


# ---------------------------------------------------------------------------
# Git and GitHub plumbing
# ---------------------------------------------------------------------------

class Git:
    def __init__(self, cwd: Path, secrets: Sequence[str] = ()):
        self.cwd = cwd
        self.secrets = [secret for secret in secrets if secret]

    def redact(self, text: str) -> str:
        for secret in self.secrets:
            text = text.replace(secret, "***")
            text = text.replace(quote(secret, safe=""), "***")
        return re.sub(r"(://)[^/@\s]+:[^/@\s]+@", r"\1***@", text)

    def run(
        self,
        *args: str,
        env: Optional[Dict[str, str]] = None,
        check: bool = True,
        input_data: Optional[bytes] = None,
    ) -> subprocess.CompletedProcess:
        full_env = os.environ.copy()
        full_env["GIT_TERMINAL_PROMPT"] = "0"
        full_env["LC_ALL"] = "C"
        if env:
            full_env.update(env)
        command = ["git", "-c", "credential.helper=", *args]
        try:
            proc = subprocess.run(
                command,
                cwd=str(self.cwd),
                env=full_env,
                input=input_data,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError:
            raise GitError("Git is not installed or is not on PATH.")
        stdout = (proc.stdout or b"").decode("utf-8", "replace")
        stderr = (proc.stderr or b"").decode("utf-8", "replace")
        proc.stdout = self.redact(stdout)  # type: ignore[assignment]
        proc.stderr = self.redact(stderr)  # type: ignore[assignment]
        if check and proc.returncode != 0:
            detail = (proc.stderr or proc.stdout).strip()
            raise GitError(f"`git {args[0]}` failed: {detail}")
        return proc

    def head(self) -> Optional[str]:
        result = self.run("rev-parse", "--verify", "-q", "HEAD", check=False)
        return result.stdout.strip() if result.returncode == 0 else None

    def is_dirty(self) -> bool:
        result = self.run("status", "--porcelain", check=False)
        return bool(result.stdout.strip())


def github_api(token: str, path: str) -> Optional[dict]:
    url = f"https://api.github.com{path}"
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": f"GoGreen-Studio/{VERSION}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urlopen(request, timeout=8) as response:
            return json.loads(response.read().decode("utf-8", "replace"))
    except (HTTPError, URLError, TimeoutError, ValueError, OSError):
        return None


@dataclass
class RepoConfig:
    owner: str
    repo: str
    username: str
    token: str
    name: str
    email: str
    workdir: Path
    branch: str = "main"

    @property
    def auth_url(self) -> str:
        user = quote(self.username, safe="")
        token = quote(self.token, safe="")
        return f"https://{user}:{token}@github.com/{self.owner}/{self.repo}.git"

    @property
    def clean_url(self) -> str:
        return f"https://github.com/{self.owner}/{self.repo}.git"

    @property
    def secrets(self) -> List[str]:
        return [self.token, quote(self.token, safe="")]


def collect_settings() -> RepoConfig:
    banner("Repository setup", "connect once, then paint as many years as you like")
    owner, repo = parse_repo_url(
        ask("Target repository (URL or owner/repo)", validator=parse_repo_url)
    )
    username = ask("GitHub username", default=owner, validator=check_username)

    env_token = (os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or "").strip()
    if env_token:
        token = env_token
        good("Using the token found in GITHUB_TOKEN / GH_TOKEN.")
    else:
        token = ask(
            "Personal Access Token (classic with 'repo' scope, hidden)",
            validator=check_token,
            secret=True,
        )

    name = ask("Git author name", default=username, validator=check_author_name)
    email = ask(
        "Git author email (must be verified on your GitHub account)",
        default=f"{username}@users.noreply.github.com",
        validator=check_email,
    )
    folder = ask("Local working folder", default=f"./{repo}")
    workdir = Path(folder).expanduser().resolve()

    cfg = RepoConfig(owner, repo, username, token, name, email, workdir)
    probe = Git(Path.cwd(), cfg.secrets)
    print()
    info("Checking repository access ...")
    remote = probe.run(
        "ls-remote", "--symref", cfg.auth_url, "HEAD", check=False
    )
    if remote.returncode != 0:
        detail = (remote.stderr or remote.stdout).strip()
        raise GitError(
            "Could not reach the repository. Check the URL, token scope and "
            f"connection.\n  {detail}"
        )
    good("Repository reachable and token accepted.")

    detected: Optional[str] = None
    match = re.search(r"ref:\s+refs/heads/(\S+)\s+HEAD", remote.stdout)
    if match:
        detected = match.group(1)

    api = github_api(cfg.token, f"/repos/{cfg.owner}/{cfg.repo}")
    if api:
        detected = api.get("default_branch") or detected
        if api.get("archived"):
            raise GitError("That repository is archived. Unarchive it before pushing.")
        permissions = api.get("permissions") or {}
        if permissions.get("push") is False:
            raise GitError("This token does not have push permission for the repository.")
        if api.get("fork"):
            warn("This repository is a fork. Commits in forks do not count toward")
            warn("your contribution graph until they are merged into the parent.")
            if not confirm("Continue with this fork anyway?", default=False):
                raise KeyboardInterrupt
        if api.get("private"):
            info("Private repository: enable 'Include private contributions' in your")
            info("profile settings or the art will stay invisible to visitors.")
        info(f"Repository detected · {api.get('full_name', cfg.owner + '/' + cfg.repo)}")
    else:
        info("Repository metadata API unavailable; continuing with Git checks.")

    cfg.branch = check_branch(
        ask("Branch to paint on", default=detected or "main")
    )
    if detected and cfg.branch != detected:
        warn(f"The default branch is '{detected}'. GitHub usually counts commits only")
        warn("on the default branch or a project's gh-pages branch.")
        if not confirm("Use a non-default branch anyway?", default=False):
            cfg.branch = detected
    return cfg


def _origin_matches(git: Git, cfg: RepoConfig) -> Optional[bool]:
    result = git.run("config", "--get", "remote.origin.url", check=False)
    if result.returncode != 0 or not result.stdout.strip():
        return None
    url = result.stdout.strip().rstrip("/")
    if url == cfg.clean_url.rstrip("/"):
        return True
    try:
        return parse_repo_url(url) == (cfg.owner, cfg.repo)
    except ValueError:
        return False


def prepare_repo(cfg: RepoConfig, git: Git) -> None:
    if cfg.workdir.exists() and not cfg.workdir.is_dir():
        raise GitError(f"Working folder is not a directory: {cfg.workdir}")
    cfg.workdir.mkdir(parents=True, exist_ok=True)

    new_repo = not (cfg.workdir / ".git").exists()
    if new_repo:
        parent = git.run("rev-parse", "--show-toplevel", check=False)
        if parent.returncode == 0 and Path(parent.stdout.strip()).resolve() != cfg.workdir:
            warn("This folder is inside another Git repository.")
            if not confirm("Create a nested repository here anyway?", default=False):
                raise AppError("Choose a folder outside the parent repository.")
        git.run("init")
        git.run("symbolic-ref", "HEAD", f"refs/heads/{cfg.branch}")
        good(f"Initialised a fresh repository in {cfg.workdir}")
    else:
        inside = git.run("rev-parse", "--show-toplevel", check=False)
        if inside.returncode != 0:
            raise GitError(f"{cfg.workdir} contains a .git folder that Git cannot read.")

    if git.is_dirty():
        raise GitError(
            "The working tree has uncommitted changes. Commit or stash them "
            "before painting; GoGreen will not overwrite your files."
        )

    origin_state = _origin_matches(git, cfg)
    if origin_state is False:
        warn("origin currently points to a different repository.")
        if not confirm("Re-point origin to the selected repository?", default=False):
            raise AppError("Aborted without changing the existing origin.")
    remotes = git.run("remote", check=False).stdout.split()
    if "origin" in remotes:
        git.run("remote", "set-url", "origin", cfg.clean_url)
    else:
        git.run("remote", "add", "origin", cfg.clean_url)

    print()
    info(f"Syncing with origin/{cfg.branch} ...")
    fetch = git.run(
        "fetch",
        cfg.auth_url,
        f"+refs/heads/{cfg.branch}:refs/remotes/origin/{cfg.branch}",
        check=False,
    )
    remote_exists = fetch.returncode == 0
    if not remote_exists:
        heads = git.run(
            "ls-remote", "--heads", cfg.auth_url, f"refs/heads/{cfg.branch}", check=False
        )
        if heads.returncode != 0:
            detail = (heads.stderr or heads.stdout).strip()
            raise GitError(f"Could not check the remote branch.\n  {detail}")
        remote_exists = bool(heads.stdout.strip())
        if remote_exists:
            raise GitError(
                "The branch exists remotely but could not be fetched.\n  "
                + (fetch.stderr or fetch.stdout).strip()
            )

    current = git.run("symbolic-ref", "--short", "-q", "HEAD", check=False).stdout.strip()
    if current != cfg.branch:
        local_exists = git.run(
            "show-ref", "--verify", "--quiet", f"refs/heads/{cfg.branch}", check=False
        ).returncode == 0
        if local_exists:
            git.run("checkout", cfg.branch)
        elif remote_exists:
            git.run(
                "checkout", "-b", cfg.branch,
                f"refs/remotes/origin/{cfg.branch}",
            )
        else:
            git.run("checkout", "-b", cfg.branch)
        good(f"Switched to branch '{cfg.branch}'.")

    git.run("config", "user.name", cfg.name)
    git.run("config", "user.email", cfg.email)

    if remote_exists:
        local_head = git.head()
        if local_head is None:
            git.run("reset", "--hard", f"refs/remotes/origin/{cfg.branch}")
            good(f"Synced from existing origin/{cfg.branch}.")
        else:
            ahead = git.run(
                "merge-base", "--is-ancestor",
                f"refs/remotes/origin/{cfg.branch}", "HEAD", check=False,
            ).returncode == 0
            behind = git.run(
                "merge-base", "--is-ancestor",
                "HEAD", f"refs/remotes/origin/{cfg.branch}", check=False,
            ).returncode == 0
            if ahead:
                good(f"Local '{cfg.branch}' contains origin/{cfg.branch}.")
            elif behind:
                git.run("merge", "--ff-only", f"refs/remotes/origin/{cfg.branch}")
                good(f"Fast-forwarded to origin/{cfg.branch}.")
            else:
                raise GitError(
                    f"Local '{cfg.branch}' and origin/{cfg.branch} have diverged. "
                    "Push or reset the local branch manually, or use a fresh folder."
                )
        git.run(
            "branch", "--set-upstream-to", f"origin/{cfg.branch}", cfg.branch,
            check=False,
        )
    else:
        info(f"origin/{cfg.branch} does not exist yet; it will be created on push.")

    git.run("remote", "set-url", "origin", cfg.clean_url)
    good(f"Remote ready · author {cfg.name} <{cfg.email}>")


# ---------------------------------------------------------------------------
# Plans and the contribution-level model
# ---------------------------------------------------------------------------

def github_level(count: int, maximum: int) -> int:
    """Approximate GitHub's max-relative 5-shade scale."""
    if count <= 0 or maximum <= 0:
        return 0
    quarter = maximum / 4.0
    return min(4, 1 + int(count / quarter))


@dataclass
class Plan:
    label: str
    start: date
    end: date
    counts: List[int]
    levels: Optional[List[List[int]]] = None
    art_base: int = 1
    notes: List[str] = field(default_factory=list)

    @property
    def span(self) -> int:
        return len(self.counts)

    @property
    def total(self) -> int:
        return sum(self.counts)

    def schedule(self) -> Iterator[Tuple[date, int]]:
        for offset, count in enumerate(self.counts):
            if count:
                yield self.start + timedelta(days=offset), count

    def preview_grid(self) -> Tuple[List[List[int]], date, date]:
        if self.levels is not None:
            width = len(self.levels[0]) if self.levels else 0
            return self.levels, self.start, self.start + timedelta(days=width * 7 - 1)

        grid_start = sunday_on_or_before(self.start)
        grid_end = saturday_on_or_after(self.end)
        weeks = (grid_end - grid_start).days // 7 + 1
        if weeks > MAX_WEEKS:
            grid_start = grid_end - timedelta(days=(MAX_WEEKS - 1) * 7)
            weeks = MAX_WEEKS
        grid = [[0] * weeks for _ in range(ROWS)]
        maximum = max(self.counts) if self.counts else 0
        for offset, count in enumerate(self.counts):
            day = self.start + timedelta(days=offset)
            if day < grid_start or day > grid_end:
                continue
            column = (day - grid_start).days // 7
            grid[week_row(day)][column] = github_level(count, maximum)
        return grid, grid_start, grid_end


def plan_from_grid(
    label: str,
    grid: List[List[int]],
    start: date,
    base: int = 1,
    style_note: str = "",
) -> Plan:
    if len(grid) != ROWS or not grid or not grid[0]:
        raise ArtError("Artwork must be exactly 7 rows tall.")
    width = len(grid[0])
    if any(len(row) != width for row in grid):
        raise ArtError("Every artwork row must have the same width.")
    if width > MAX_WEEKS:
        raise ArtError(f"Artwork is {width} weeks wide; the maximum is {MAX_WEEKS}.")
    if week_row(start) != 0:
        raise ArtError("Artwork must start on a Sunday.")
    base = max(1, base)
    counts: List[int] = []
    for row in grid:
        for level in row:
            if level < 0 or level > 4:
                raise ArtError("Artwork levels must be between 0 and 4.")
            counts.append(LEVEL_COMMITS[level] * base if level else 0)
    end = start + timedelta(days=width * 7 - 1)
    notes = [style_note] if style_note else []
    return Plan(label, start, end, counts, [list(row) for row in grid], base, notes)


def apportion(weights: List[float], total: int) -> List[int]:
    weight_sum = sum(weights)
    if weight_sum <= 0:
        weights = [1.0] * len(weights)
        weight_sum = float(len(weights))
    raw = [weight / weight_sum * total for weight in weights]
    counts = [int(value) for value in raw]
    leftover = total - sum(counts)
    candidates = sorted(
        (index for index, weight in enumerate(weights) if weight > 0),
        key=lambda index: raw[index] - counts[index],
        reverse=True,
    )
    for index in candidates[:leftover]:
        counts[index] += 1
    return counts


# ---------------------------------------------------------------------------
# Pixel-art library
# ---------------------------------------------------------------------------

TEMPLATES: Dict[str, List[str]] = {
    "Heart": [
        "0110110",
        "1331331",
        "1443441",
        "1444441",
        "0134310",
        "0013100",
        "0001000",
    ],
    "Invader": [
        "00400000400",
        "00040004000",
        "00444444400",
        "04404440440",
        "44444444444",
        "40444444404",
        "40400000404",
    ],
    "Ghost": [
        "003333300",
        "033333330",
        "330333033",
        "330333033",
        "333333333",
        "333333333",
        "303030303",
    ],
    "Cat": [
        "03000003000",
        "03300003300",
        "03333333330",
        "33033303333",
        "33334333333",
        "33333333333",
        "03033303000",
    ],
    "Mushroom": [
        "000333000",
        "033444330",
        "344343443",
        "334444433",
        "000333000",
        "000303000",
        "000303000",
    ],
    "Star": [
        "000030000",
        "000343000",
        "003444300",
        "334444433",
        "000343000",
        "003303300",
        "033000330",
    ],
    "Diamond": [
        "0003000",
        "0034300",
        "0344430",
        "3444443",
        "0344430",
        "0034300",
        "0003000",
    ],
    "Skull": [
        "003333300",
        "033333330",
        "330333033",
        "330333033",
        "333333333",
        "033030330",
        "003000300",
    ],
    "Check": [
        "000000030",
        "000000330",
        "000003300",
        "030033000",
        "033330000",
        "003300000",
        "000000000",
    ],
    "Smile": [
        "003333300",
        "033333330",
        "330333033",
        "330333033",
        "333333333",
        "033000330",
        "003333300",
    ],
    "Flower": [
        "001101100",
        "013313310",
        "134313431",
        "013333310",
        "000333000",
        "003030300",
        "030000030",
    ],
    "Sword": [
        "0004000",
        "0004000",
        "0004000",
        "0004000",
        "0334330",
        "0003000",
        "0003000",
    ],
}


def template_grid(name: str) -> List[List[int]]:
    rows = TEMPLATES[name]
    return [[int(char) for char in row] for row in rows]


def validate_templates() -> None:
    for name, rows in TEMPLATES.items():
        if len(rows) != ROWS:
            raise ArtError(f"Template {name} does not have 7 rows.")
        width = len(rows[0])
        if width == 0 or any(len(row) != width for row in rows):
            raise ArtError(f"Template {name} has ragged rows.")
        if any(char not in "01234" for row in rows for char in row):
            raise ArtError(f"Template {name} contains an invalid level.")


def apply_style(grid: List[List[int]], style: str) -> List[List[int]]:
    """Return a new grid with classic, mono, outline, or glow styling."""
    rows, width = len(grid), len(grid[0])
    result = [row[:] for row in grid]
    if style == "mono":
        return [[4 if cell else 0 for cell in row] for row in grid]
    if style == "outline":
        result = [[0] * width for _ in range(rows)]
        for r in range(rows):
            for c in range(width):
                if not grid[r][c]:
                    continue
                edge = (
                    r == 0 or r == rows - 1 or c == 0 or c == width - 1
                    or not grid[r - 1][c] or not grid[r + 1][c]
                    or not grid[r][c - 1] or not grid[r][c + 1]
                )
                result[r][c] = 4 if edge else 1
        return result
    if style == "glow":
        for r in range(rows):
            for c in range(width):
                if grid[r][c]:
                    continue
                neighbours = (
                    (r > 0 and grid[r - 1][c])
                    or (r < rows - 1 and grid[r + 1][c])
                    or (c > 0 and grid[r][c - 1])
                    or (c < width - 1 and grid[r][c + 1])
                )
                if neighbours:
                    result[r][c] = 1
        return result
    return result


def place_grid(
    art: List[List[int]],
    width: int,
    align: str = "center",
    offset: int = 0,
) -> List[List[int]]:
    if len(art) != ROWS:
        raise ArtError("Artwork must have 7 rows.")
    art_width = len(art[0])
    if art_width > width:
        raise ArtError(
            f"Artwork is {art_width} weeks wide but the canvas is only {width} weeks."
        )
    if align == "left":
        left = 0
    elif align == "right":
        left = width - art_width
    elif align == "custom":
        left = max(0, min(width - art_width, offset))
    else:
        left = (width - art_width) // 2
    canvas = [[0] * width for _ in range(ROWS)]
    for r in range(ROWS):
        for c in range(art_width):
            canvas[r][left + c] = art[r][c]
    return canvas


def parse_custom_matrix(lines: Sequence[str]) -> List[List[int]]:
    if len(lines) != ROWS:
        raise ArtError("Custom art needs exactly 7 lines.")
    mapping = {"#": 4, "*": 3, "+": 2, ".": 1, " ": 0, "0": 0, "1": 1,
               "2": 2, "3": 3, "4": 4}
    grid: List[List[int]] = []
    for line in lines:
        # Keep internal spaces: they are a convenient way to draw empty pixels.
        cleaned = re.sub(r"[,|\t]", "", line.strip())
        if not cleaned:
            grid.append([])
            continue
        row: List[int] = []
        for char in cleaned:
            if char not in mapping:
                raise ArtError(f"Unknown pixel '{char}'. Use 0-4, #, *, + or .")
            row.append(mapping[char])
        grid.append(row)
    width = max((len(row) for row in grid), default=0)
    if width == 0 or width > MAX_WEEKS:
        raise ArtError(f"Custom art must be between 1 and {MAX_WEEKS} columns wide.")
    for row in grid:
        row.extend([0] * (width - len(row)))
    return grid


# ---------------------------------------------------------------------------
# 5x7 bitmap font for text banners
# ---------------------------------------------------------------------------

FONT_5X7: Dict[str, List[str]] = {
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
    "B": ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
    "C": ["01110", "10001", "10000", "10000", "10000", "10001", "01110"],
    "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
    "F": ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
    "G": ["01110", "10001", "10000", "10111", "10001", "10001", "01111"],
    "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
    "I": ["01110", "00100", "00100", "00100", "00100", "00100", "01110"],
    "J": ["00111", "00010", "00010", "00010", "00010", "10010", "01100"],
    "K": ["10001", "10010", "10100", "11000", "10100", "10010", "10001"],
    "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
    "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
    "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
    "Q": ["01110", "10001", "10001", "10001", "10101", "10010", "01101"],
    "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
    "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
    "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
    "V": ["10001", "10001", "10001", "10001", "10001", "01010", "00100"],
    "W": ["10001", "10001", "10001", "10101", "10101", "11011", "10001"],
    "X": ["10001", "10001", "01010", "00100", "01010", "10001", "10001"],
    "Y": ["10001", "10001", "01010", "00100", "00100", "00100", "00100"],
    "Z": ["11111", "00001", "00010", "00100", "01000", "10000", "11111"],
    "0": ["01110", "10001", "10011", "10101", "11001", "10001", "01110"],
    "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "2": ["01110", "10001", "00001", "00010", "00100", "01000", "11111"],
    "3": ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
    "4": ["00010", "00110", "01010", "10010", "11111", "00010", "00010"],
    "5": ["11111", "10000", "11110", "00001", "00001", "10001", "01110"],
    "6": ["00110", "01000", "10000", "11110", "10001", "10001", "01110"],
    "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
    "9": ["01110", "10001", "10001", "01111", "00001", "00010", "01100"],
    " ": ["00000", "00000", "00000", "00000", "00000", "00000", "00000"],
    "!": ["00100", "00100", "00100", "00100", "00100", "00000", "00100"],
    "?": ["01110", "10001", "00001", "00010", "00100", "00000", "00100"],
    ".": ["00000", "00000", "00000", "00000", "00000", "00000", "00100"],
    ",": ["00000", "00000", "00000", "00000", "00000", "00100", "01000"],
    ":": ["00000", "00100", "00000", "00000", "00100", "00000", "00000"],
    ";": ["00000", "00100", "00000", "00000", "00100", "00100", "01000"],
    "-": ["00000", "00000", "00000", "11111", "00000", "00000", "00000"],
    "+": ["00000", "00100", "00100", "11111", "00100", "00100", "00000"],
    "/": ["00001", "00010", "00010", "00100", "01000", "01000", "10000"],
    "\\": ["10000", "01000", "01000", "00100", "00010", "00010", "00001"],
    "=": ["00000", "00000", "11111", "00000", "11111", "00000", "00000"],
    "#": ["01010", "01010", "11111", "01010", "11111", "01010", "01010"],
    "@": ["01110", "10001", "10111", "10101", "10111", "10000", "01110"],
    "$": ["00100", "01111", "10100", "01110", "00101", "11110", "00100"],
    "%": ["11001", "11010", "00010", "00100", "01000", "01011", "10011"],
    "&": ["01100", "10010", "10100", "01000", "10101", "10010", "01101"],
    "*": ["00000", "10101", "01110", "11111", "01110", "10101", "00000"],
    "(": ["00010", "00100", "01000", "01000", "01000", "00100", "00010"],
    ")": ["01000", "00100", "00010", "00010", "00010", "00100", "01000"],
    "[": ["01110", "01000", "01000", "01000", "01000", "01000", "01110"],
    "]": ["01110", "00010", "00010", "00010", "00010", "00010", "01110"],
    "<": ["00010", "00100", "01000", "10000", "01000", "00100", "00010"],
    ">": ["01000", "00100", "00010", "00001", "00010", "00100", "01000"],
    "_": ["00000", "00000", "00000", "00000", "00000", "00000", "11111"],
    "'": ["00100", "00100", "00000", "00000", "00000", "00000", "00000"],
    '"': ["01010", "01010", "00000", "00000", "00000", "00000", "00000"],
    "|": ["00100", "00100", "00100", "00100", "00100", "00100", "00100"],
    "^": ["00100", "01010", "10001", "00000", "00000", "00000", "00000"],
    "~": ["00000", "01001", "10110", "00000", "00000", "00000", "00000"],
}


def validate_font() -> None:
    for char, rows in FONT_5X7.items():
        if len(rows) != ROWS or any(len(row) != 5 for row in rows):
            raise ArtError(f"Font glyph {char!r} is malformed.")
        if any(pixel not in "01" for row in rows for pixel in row):
            raise ArtError(f"Font glyph {char!r} contains an invalid pixel.")


def render_text(text: str, spacing: int = 1) -> List[List[int]]:
    text = " ".join(text.upper().split())
    if not text:
        raise ArtError("Text cannot be empty.")
    unsupported = sorted({char for char in text if char not in FONT_5X7})
    if unsupported:
        raise ArtError(
            "Unsupported characters: " + " ".join(repr(char) for char in unsupported)
        )
    width = len(text) * 5 + (len(text) - 1) * spacing
    if width > MAX_WEEKS:
        max_chars = (MAX_WEEKS + spacing) // (5 + spacing)
        raise ArtError(
            f"That text needs {width} weeks; the graph is {MAX_WEEKS} wide. "
            f"Use at most {max_chars} characters."
        )
    grid = [[0] * width for _ in range(ROWS)]
    cursor = 0
    for index, char in enumerate(text):
        pattern = FONT_5X7[char]
        for r in range(ROWS):
            for c in range(5):
                if pattern[r][c] == "1":
                    grid[r][cursor + c] = 4
        cursor += 5
        if index != len(text) - 1:
            cursor += spacing
    return grid


# ---------------------------------------------------------------------------
# Image import: Pillow when available, a small PNG decoder otherwise
# ---------------------------------------------------------------------------

try:
    from PIL import Image as _PILImage  # type: ignore
except Exception:
    _PILImage = None


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def _unfilter_png(raw: bytes, width: int, height: int, channels: int,
                  bit_depth: int) -> List[bytes]:
    stride = (width * channels * bit_depth + 7) // 8
    bpp = max(1, (channels * bit_depth + 7) // 8)
    rows: List[bytes] = []
    previous = bytearray(stride)
    offset = 0
    for _ in range(height):
        if offset >= len(raw):
            raise ArtError("PNG data ended unexpectedly.")
        filter_type = raw[offset]
        offset += 1
        line = bytearray(raw[offset:offset + stride])
        if len(line) != stride:
            raise ArtError("PNG scanline is truncated.")
        offset += stride
        for index in range(stride):
            left = line[index - bpp] if index >= bpp else 0
            up = previous[index]
            upper_left = previous[index - bpp] if index >= bpp else 0
            if filter_type == 1:
                line[index] = (line[index] + left) & 0xFF
            elif filter_type == 2:
                line[index] = (line[index] + up) & 0xFF
            elif filter_type == 3:
                line[index] = (line[index] + ((left + up) // 2)) & 0xFF
            elif filter_type == 4:
                line[index] = (line[index] + _paeth(left, up, upper_left)) & 0xFF
            elif filter_type != 0:
                raise ArtError(f"Unsupported PNG filter type {filter_type}.")
        rows.append(bytes(line))
        previous = line
    return rows


def _unpack_samples(line: bytes, count: int, bit_depth: int) -> List[int]:
    if bit_depth == 8:
        return list(line[:count])
    if bit_depth == 16:
        return [
            (line[index] << 8) | line[index + 1]
            for index in range(0, count * 2, 2)
        ]
    if bit_depth in (1, 2, 4):
        samples: List[int] = []
        per_byte = 8 // bit_depth
        mask = (1 << bit_depth) - 1
        for byte in line:
            for slot in range(per_byte):
                samples.append((byte >> (8 - bit_depth * (slot + 1))) & mask)
                if len(samples) == count:
                    return samples
        return samples
    raise ArtError(f"Unsupported PNG bit depth {bit_depth}.")


def decode_png(path: Path) -> Tuple[int, int, bytes]:
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ArtError("Not a PNG file.")
    position = 8
    width = height = bit_depth = color_type = None
    interlace = 0
    palette: List[Tuple[int, int, int]] = []
    transparency = b""
    idat = bytearray()
    while position + 12 <= len(data):
        length = struct.unpack(">I", data[position:position + 4])[0]
        chunk_type = data[position + 4:position + 8]
        if length > len(data) - position - 12:
            raise ArtError("PNG contains a truncated chunk.")
        chunk = data[position + 8:position + 8 + length]
        position += 12 + length
        if chunk_type == b"IHDR":
            if length != 13:
                raise ArtError("PNG header has an invalid length.")
            (
                width, height, bit_depth, color_type,
                _compression, _filter, interlace,
            ) = struct.unpack(">IIBBBBB", chunk)
        elif chunk_type == b"PLTE":
            if length % 3:
                raise ArtError("PNG palette has an invalid length.")
            palette = [
                (chunk[index], chunk[index + 1], chunk[index + 2])
                for index in range(0, len(chunk), 3)
            ]
        elif chunk_type == b"tRNS":
            transparency = chunk
        elif chunk_type == b"IDAT":
            idat.extend(chunk)
        elif chunk_type == b"IEND":
            break
    if width is None or height is None or bit_depth is None or color_type is None:
        raise ArtError("PNG header is missing.")
    if width <= 0 or height <= 0:
        raise ArtError("PNG has invalid dimensions.")
    if bit_depth not in (1, 2, 4, 8, 16):
        raise ArtError(f"Unsupported PNG bit depth {bit_depth}.")
    if interlace:
        raise ArtError("Interlaced PNG is not supported without Pillow. "
                       "Re-save it without interlacing or install Pillow.")
    if width * height > 25_000_000:
        raise ArtError("Image is too large (maximum 25 million pixels).")
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(color_type)
    if channels is None:
        raise ArtError(f"Unsupported PNG colour type {color_type}.")
    if color_type == 3 and not palette:
        raise ArtError("Indexed PNG is missing its palette.")
    try:
        raw = zlib.decompress(bytes(idat))
    except zlib.error as exc:
        raise ArtError(f"Could not decompress PNG: {exc}")
    rows = _unfilter_png(raw, width, height, channels, bit_depth)

    def scale(sample: int) -> int:
        if bit_depth == 16:
            return sample >> 8
        if bit_depth == 8:
            return sample
        return sample * 255 // ((1 << bit_depth) - 1)

    rgba = bytearray(width * height * 4)
    cursor = 0
    for y in range(height):
        samples = _unpack_samples(rows[y], width * channels, bit_depth)
        for x in range(width):
            if color_type == 0:
                gray = scale(samples[x])
                r = g = b = gray
                a = 255
                if len(transparency) >= 2:
                    key = struct.unpack(">H", transparency[:2])[0]
                    if samples[x] == key:
                        a = 0
            elif color_type == 2:
                base = x * 3
                r, g, b = (scale(samples[base + i]) for i in range(3))
                a = 255
                if len(transparency) >= 6:
                    key = struct.unpack(">HHH", transparency[:6])
                    if (samples[base], samples[base + 1],
                            samples[base + 2]) == key:
                        a = 0
            elif color_type == 3:
                index = samples[x]
                if index >= len(palette):
                    raise ArtError("PNG palette index is out of range.")
                r, g, b = palette[index]
                a = transparency[index] if index < len(transparency) else 255
            elif color_type == 4:
                base = x * 2
                r = g = b = scale(samples[base])
                a = scale(samples[base + 1])
            else:
                base = x * 4
                r, g, b, a = (scale(samples[base + i]) for i in range(4))
            rgba[cursor:cursor + 4] = bytes((r, g, b, a))
            cursor += 4
    return width, height, bytes(rgba)


def load_image_rgba(path: Path) -> Tuple[int, int, bytes]:
    if not path.exists():
        raise ArtError(f"Image not found: {path}")
    if path.is_dir():
        raise ArtError(f"Image path is a folder: {path}")
    if _PILImage is not None:
        try:
            with _PILImage.open(str(path)) as image:
                image = image.convert("RGBA")
                width, height = image.size
                if width * height > 25_000_000:
                    raise ArtError("Image is too large (maximum 25 million pixels).")
                return width, height, image.tobytes()
        except ArtError:
            raise
        except Exception as exc:
            raise ArtError(f"Could not read image: {exc}")
    if path.suffix.lower() == ".png":
        try:
            return decode_png(path)
        except ArtError:
            raise
        except (OSError, ValueError, IndexError, struct.error) as exc:
            raise ArtError(f"Could not decode PNG: {exc}")
    raise ArtError(
        "Only PNG is supported without Pillow. Install it with "
        "`pip install pillow` for JPEG, GIF, WebP and interlaced PNG."
    )


def image_to_art(
    path: Path,
    invert: bool = False,
    dither: bool = False,
    target_width: Optional[int] = None,
) -> List[List[int]]:
    width, height, pixels = load_image_rgba(path)
    if width <= 0 or height <= 0:
        raise ArtError("Image has no pixels.")
    if target_width is None:
        target_width = min(MAX_WEEKS, max(1, round((width / height) * ROWS)))
    target_width = max(1, min(MAX_WEEKS, target_width))

    luminance: List[List[Optional[float]]] = [[None] * target_width for _ in range(ROWS)]
    for row in range(ROWS):
        y0 = row * height // ROWS
        y1 = max(y0 + 1, (row + 1) * height // ROWS)
        step_y = max(1, (y1 - y0) // 32)
        for column in range(target_width):
            x0 = column * width // target_width
            x1 = max(x0 + 1, (column + 1) * width // target_width)
            step_x = max(1, (x1 - x0) // 32)
            total_r = total_g = total_b = total_a = 0
            samples = 0
            for sy in range(y0, y1, step_y):
                base_y = sy * width * 4
                for sx in range(x0, x1, step_x):
                    offset = base_y + sx * 4
                    r, g, b, a = pixels[offset:offset + 4]
                    total_r += r
                    total_g += g
                    total_b += b
                    total_a += a
                    samples += 1
            if samples == 0:
                continue
            alpha = total_a / samples
            if alpha < 32:
                continue
            r = total_r / samples
            g = total_g / samples
            b = total_b / samples
            value = 0.2126 * r + 0.7152 * g + 0.0722 * b
            if invert:
                value = 255.0 - value
            luminance[row][column] = value

    if dither:
        for row in range(ROWS):
            for column in range(target_width):
                value = luminance[row][column]
                if value is None:
                    continue
                level = max(0, min(4, int(round(value / 255.0 * 4.0))))
                quantized = level * 255.0 / 4.0
                error = value - quantized
                luminance[row][column] = float(level)
                for dx, dy, weight, valid in (
                    (1, 0, 7 / 16, column + 1 < target_width),
                    (-1, 1, 3 / 16, column > 0 and row + 1 < ROWS),
                    (0, 1, 5 / 16, row + 1 < ROWS),
                    (1, 1, 1 / 16, column + 1 < target_width and row + 1 < ROWS),
                ):
                    if not valid:
                        continue
                    neighbour = luminance[row + dy][column + dx]
                    if neighbour is not None:
                        luminance[row + dy][column + dx] = neighbour + error * weight
        grid = [
            [0 if value is None else max(0, min(4, int(round(value)))) for value in row]
            for row in luminance
        ]
    else:
        grid = [
            [
                0 if value is None else max(0, min(4, int(value * 5 // 256)))
                for value in row
            ]
            for row in luminance
        ]

    if not any(any(row) for row in grid):
        raise ArtError("The image appears to be empty or fully transparent.")
    return grid


# ---------------------------------------------------------------------------
# Preview rendering, art windows and intensity calibration
# ---------------------------------------------------------------------------

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
WEEK_LABELS = ("Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat")


def _month_labels(grid_start: date, weeks: int) -> str:
    """Place short month labels on a 53-column preview without collisions."""
    slots = [" "] * weeks
    last_end = -2

    def place(column: int, month: int) -> None:
        nonlocal last_end
        label = MONTHS[month - 1]
        start = max(column, last_end + 2)
        if start + len(label) > weeks:
            return
        for index, char in enumerate(label):
            slots[start + index] = char
        last_end = start + len(label) - 1

    # Label the month that owns the first column, then every month whose first
    # day appears inside the canvas.  Shifting a label right by a column keeps
    # the header readable when two months begin in the same week.
    place(0, grid_start.month)
    seen = {(grid_start.year, grid_start.month)}
    for column in range(weeks):
        week_start = grid_start + timedelta(days=column * 7)
        for offset in range(7):
            day = week_start + timedelta(days=offset)
            key = (day.year, day.month)
            if day.day == 1 and key not in seen:
                seen.add(key)
                place(column, day.month)
    return "".join(slots)


def _shade(level: int) -> str:
    if USE_COLOR:
        color = GITHUB_COLORS[max(0, min(4, level))]
        if level == 0:
            return _rgb("·", "#30363d")
        return _rgb("█", color)
    return ("·", "░", "▒", "▓", "█")[max(0, min(4, level))]


def print_preview(plan: Plan) -> None:
    grid, grid_start, grid_end = plan.preview_grid()
    weeks = len(grid[0]) if grid else 0
    if not weeks:
        return
    print()
    print(f"  {bold('CONTRIBUTION PREVIEW')}  {dim(grid_start.isoformat() + '  →  ' + grid_end.isoformat())}")
    print(f"  {dim('     ' + _month_labels(grid_start, weeks))}")
    for row in range(ROWS):
        cells = "".join(_shade(level) for level in grid[row])
        print(f"  {dim(WEEK_LABELS[row]):>3}  {cells}")
    legend = " ".join(_shade(level) for level in range(5))
    print(f"  {dim('     less')} {legend} {dim('more')}")
    if plan.end > date.today():
        warn("Some cells are in the future; GitHub will keep them empty until the date arrives.")


def print_legend_help() -> None:
    print(f"  {dim('Shades are relative to your busiest day.')}")


def _public_year_max(username: str, year: int) -> Optional[int]:
    url = (
        "https://github.com/users/"
        + quote(username, safe="")
        + f"/contributions?from={year}-01-01&to={year}-12-31"
    )
    request = Request(
        url,
        headers={"User-Agent": f"GoGreen-Studio/{VERSION}"},
    )
    try:
        with urlopen(request, timeout=7) as response:
            html = response.read().decode("utf-8", "replace")
    except (HTTPError, URLError, TimeoutError, OSError):
        return None
    counts = [
        int(match.group(1).replace(",", ""))
        for match in re.finditer(r">\s*([\d,]+)\s+contributions?\s+on\s+", html)
    ]
    if counts:
        return max(counts)
    if "No contributions" in html:
        return 0
    return None


def detect_existing_max(username: str, start: date, end: date) -> Optional[int]:
    years = list(range(start.year, end.year + 1))
    if len(years) > 4:
        years = [start.year, end.year]
    values: List[int] = []
    for year in years:
        value = _public_year_max(username, year)
        if value is None:
            return None
        values.append(value)
    return max(values) if values else None


def choose_base(cfg: RepoConfig, start: date, end: date, mode_name: str) -> int:
    print()
    print(f"  {bold('Shade calibration')}")
    info("GitHub shades are relative to your busiest day in the year.")
    info("The tool maps levels to 1×, 3×, 5× and 7× a base value so all four")
    info("greens stay distinct and the darkest green beats your existing maximum.")
    detected: Optional[int] = None
    if confirm("Auto-detect your public busiest day?", default=True):
        detected = detect_existing_max(cfg.username, start, end)
    if detected is None:
        warn("Could not auto-detect the busiest day (or auto-detect was skipped).")
        info("Enter it manually; include private contributions only if your")
        info("profile is set to show them.")
        existing = ask_int(
            "Existing busiest day in the checked year(s) (0 if none/unknown)",
            0, 100_000, default=0,
        )
    else:
        existing = detected
        good(f"Your public busiest day in the checked year(s): "
             f"{fmt_int(existing)} contributions.")

    auto_base = max(1, (existing + 1 + 6) // 7)
    choice = ask_choice(
        f"Intensity for {mode_name}",
        [
            ("1", f"Crisp  · minimal commits, all four shades  (base {auto_base})"),
            ("2", f"Bold   · double commits, same shades         (base {auto_base * 2})"),
            ("3", "Custom · choose the base myself"),
        ],
        default="1",
    )
    if choice == "1":
        base = auto_base
    elif choice == "2":
        base = auto_base * 2
    else:
        base = ask_int("Base commits (level 1)", 1, 100_000, default=auto_base)
    print()
    info(
        f"Levels · L1 {base}  L2 {base * 3}  L3 {base * 5}  "
        f"L4 {base * 7} commits/day"
    )
    if existing >= base * 7:
        warn("Your existing maximum is still higher; the art may look compressed.")
    return base


def choose_art_window() -> Tuple[date, int, str]:
    today = date.today()
    last_saturday = saturday_on_or_before(today - timedelta(days=1))
    print()
    choice = ask_choice(
        "Where should the artwork live?",
        [
            ("1", "Rolling 52 complete weeks  · safest, ends last Saturday"),
            ("2", "Rolling 53 weeks            · includes this week"),
            ("3", "Calendar year               · pick a year"),
            ("4", "Custom Sunday start         · choose your own canvas"),
        ],
        default="1",
    )
    if choice == "1":
        start = last_saturday - timedelta(days=52 * 7 - 1)
        return start, 52, "Rolling 52 complete weeks"
    if choice == "2":
        start = sunday_on_or_before(today) - timedelta(days=52 * 7)
        return start, 53, "Rolling 53 weeks"
    if choice == "3":
        year = ask_int("Year", MIN_DATE.year, today.year, default=today.year)
        first = date(year, 1, 1)
        last = date(year, 12, 31)
        start = sunday_on_or_before(first)
        end = saturday_on_or_after(last)
        weeks = (end - start).days // 7 + 1
        label = f"Calendar year {year}"
        if weeks > MAX_WEEKS:
            # A leap year that begins on Saturday needs 54 aligned columns.
            # GitHub's grid is 53 wide, so keep the end of December and trim
            # the first partial week instead of silently dropping December.
            start += timedelta(days=(weeks - MAX_WEEKS) * 7)
            weeks = MAX_WEEKS
            label += " · 53-week fit"
        return start, weeks, label
    raw = ask("Start date (will align to Sunday)", default=today.isoformat(),
              validator=check_day)
    start = sunday_on_or_before(check_day(raw))
    weeks = ask_int("Canvas width in weeks", 1, MAX_WEEKS, default=52)
    return start, weeks, "Custom window"


# ---------------------------------------------------------------------------
# Classic heatmap modes
# ---------------------------------------------------------------------------

def ask_date_range(allow_year: bool = False) -> Tuple[date, date]:
    today = date.today()
    if allow_year:
        while True:
            try:
                raw = input(
                    f"  Year ({MIN_DATE.year}-{today.year}) or press Enter for a "
                    f"custom range: "
                ).strip()
            except EOFError:
                raise KeyboardInterrupt
            if not raw:
                break
            if raw.isdigit() and MIN_DATE.year <= int(raw) <= today.year:
                year = int(raw)
                return date(year, 1, 1), min(date(year, 12, 31), today)
            warn(f"Enter a year between {MIN_DATE.year} and {today.year}.")
    start = check_day(ask("Start date (YYYY-MM-DD)"))
    while True:
        end = check_day(ask("End date   (YYYY-MM-DD)", default=today.isoformat()))
        if end >= start:
            return start, end
        warn("End date must be on or after the start date.")


def option_random() -> Plan:
    banner("Random scattering", "organic bursts, quiet weekends, natural-looking heat")
    start, end = ask_date_range(allow_year=True)
    total = ask_int("Total number of contributions", 1, 1_000_000)
    empty_pct = ask_int("Roughly what % of days should stay empty", 0, 90, default=30)
    days = days_between(start, end)
    weights: List[float] = []
    for day in days:
        if random.random() < empty_pct / 100:
            weights.append(0.0)
            continue
        weight = random.lognormvariate(0, 0.9)
        if day.weekday() >= 5:
            weight *= 0.5
        weights.append(weight)
    if not any(weights):
        weights[random.randrange(len(days))] = 1.0
    return Plan("Random scattering", start, end, apportion(weights, total))


def option_block() -> Plan:
    banner("Full block", "a solid slab of green; every active day becomes darkest green")
    start, end = ask_date_range()
    per_day = ask_int("Contributions per day", 1, 10_000)
    n_days = (end - start).days + 1
    total = per_day * n_days
    if total > 500_000:
        warn(f"That is {fmt_int(total)} commits. Large runs can take a long time.")
        if not confirm("Continue with this size?", default=False):
            raise Cancelled
    return Plan("Full block", start, end, [per_day] * n_days)


def option_even() -> Plan:
    banner("Even distribution", "split a target total as evenly as possible")
    start, end = ask_date_range()
    n_days = (end - start).days + 1
    total = ask_int("Total target contributions", 1, 1_000_000)
    base, remainder = divmod(total, n_days)
    counts = [base] * n_days
    for index in range(remainder):
        counts[(index * n_days) // remainder] += 1
    if total < n_days:
        warn(f"{fmt_int(total)} {plural(total, 'commit')} over "
             f"{fmt_int(n_days)} days means some days get none; "
             "they are spaced out evenly.")
    return Plan("Even distribution", start, end, counts)


# ---------------------------------------------------------------------------
# Pixel-art studio
# ---------------------------------------------------------------------------

def _thumbnail(grid: List[List[int]], width: int) -> List[str]:
    lines = []
    for row in grid:
        cells = []
        for level in row:
            cells.append(_shade(level) * 2)
        lines.append("".join(cells) + "  " * (width - len(row)))
    return lines


def print_gallery() -> None:
    validate_templates()
    names = list(TEMPLATES)
    width = max(len(TEMPLATES[name][0]) for name in names)
    slot = width * 2 + 4
    terminal = shutil.get_terminal_size((90, 24)).columns
    if terminal >= 82:
        columns = 3
    elif terminal >= 56:
        columns = 2
    else:
        columns = 1
    print()
    print(f"  {bold('BUILT-IN GALLERY')}")
    for group_start in range(0, len(names), columns):
        group = names[group_start:group_start + columns]
        label_parts = []
        for index, name in enumerate(group):
            number = group_start + index + 1
            plain = f"[{number:>2}] {name}"
            pad = max(1, slot - len(plain))
            label_parts.append(green(f"[{number:>2}]") + f" {name}" + " " * pad)
        print("  " + "".join(label_parts).rstrip())
        thumbnails = [
            _thumbnail(template_grid(name), width) for name in group
        ]
        for row in range(ROWS):
            line = ""
            for thumb in thumbnails:
                line += thumb[row] + " " * (slot - width * 2)
            print("  " + line.rstrip())
        print()
    if columns < 3:
        print(f"  {green('[13]')} Paste a custom matrix")
        print(f"  {green('[14]')} Import an image (PNG; Pillow for more)")
    else:
        print(f"  {green('[13]')} Paste a custom matrix      "
              f"{green('[14]')} Import an image (PNG; Pillow for more)")


def choose_art_style() -> str:
    choice = ask_choice(
        "Pixel style",
        [
            ("1", "Classic  · keep the design's original shading"),
            ("2", "Mono     · one solid, darkest shade"),
            ("3", "Outline  · bright edges, dim interior"),
            ("4", "Glow     · add a soft one-pixel halo"),
        ],
        default="1",
    )
    return {"1": "classic", "2": "mono", "3": "outline", "4": "glow"}[choice]


def choose_placement(weeks: int, art_width: int) -> Tuple[str, int]:
    choice = ask_choice(
        "Horizontal placement",
        [
            ("1", "Centre"),
            ("2", "Left"),
            ("3", "Right"),
            ("4", "Custom column"),
        ],
        default="1",
    )
    if choice == "1":
        return "center", 0
    if choice == "2":
        return "left", 0
    if choice == "3":
        return "right", 0
    offset = ask_int("Left column (0-based)", 0, max(0, weeks - art_width), default=0)
    return "custom", offset


def read_custom_matrix() -> List[List[int]]:
    print()
    info("Paste 7 rows. Use 0-4 (0 = empty) or . + * # for levels 1-4.")
    info("Spaces are empty pixels too; commas and | are ignored as separators.")
    info("Rows are Sunday → Saturday; all rows should be the same width.")
    lines = []
    for row in range(ROWS):
        try:
            line = input(f"  {WEEK_LABELS[row]}: ")
        except EOFError:
            raise KeyboardInterrupt
        lines.append(line)
    return parse_custom_matrix(lines)


def read_imported_image() -> Tuple[List[List[int]], str]:
    raw = ask("Image path", validator=lambda value: value)
    path = Path(raw).expanduser()
    invert = confirm("Invert light/dark?", default=False)
    dither = confirm("Dither for smoother photographic detail?", default=True)
    grid = image_to_art(path, invert=invert, dither=dither)
    return grid, f"Image · {path.name}"


def select_art_source() -> Tuple[List[List[int]], str]:
    print_gallery()
    while True:
        choice = ask_int("Choose artwork", 1, 14)
        if 1 <= choice <= len(TEMPLATES):
            name = list(TEMPLATES)[choice - 1]
            return template_grid(name), name
        if choice == 13:
            try:
                return read_custom_matrix(), "Custom matrix"
            except ArtError as exc:
                warn(str(exc))
                continue
        if choice == 14:
            try:
                return read_imported_image()
            except ArtError as exc:
                warn(str(exc))
                continue


def option_pixel_art(cfg: RepoConfig) -> Plan:
    banner("Pixel art studio", "paint the 7 × 53 contribution calendar")
    grid, name = select_art_source()
    style = choose_art_style()
    grid = apply_style(grid, style)
    art_width = len(grid[0])
    print()
    good(f"Selected {name} · {art_width} weeks wide · {style} style")

    start, weeks, window_label = choose_art_window()
    while art_width > weeks:
        warn(f"'{name}' is {art_width} weeks wide but the canvas is {weeks}.")
        start, weeks, window_label = choose_art_window()

    align, offset = choose_placement(weeks, art_width)
    canvas = place_grid(grid, weeks, align, offset)
    end = start + timedelta(days=weeks * 7 - 1)
    base = choose_base(cfg, start, end, "pixel art")
    notes = [f"{style} style", window_label]
    return plan_from_grid(
        f"Pixel Art · {name} · {style.title()}",
        canvas,
        start,
        base,
        " · ".join(notes),
    )


def option_text(cfg: RepoConfig) -> Plan:
    banner("Text banner", "5 × 7 lettering, centred or placed anywhere")
    while True:
        text = ask("Text to draw", default="ALBATANY")
        try:
            grid = render_text(text)
            break
        except ArtError as exc:
            warn(str(exc))
    style = choose_art_style()
    grid = apply_style(grid, style)
    art_width = len(grid[0])

    start, weeks, window_label = choose_art_window()
    while art_width > weeks:
        warn(f"That text is {art_width} weeks wide but the canvas is {weeks}.")
        start, weeks, window_label = choose_art_window()
    align, offset = choose_placement(weeks, art_width)
    canvas = place_grid(grid, weeks, align, offset)
    end = start + timedelta(days=weeks * 7 - 1)
    base = choose_base(cfg, start, end, "text banner")
    return plan_from_grid(
        f"Text Banner · {text.upper()} · {style.title()}",
        canvas,
        start,
        base,
        f"{style} style · {window_label}",
    )


def option_streak() -> Plan:
    banner("Streak builder", "controlled runs of consecutive green days")
    start, end = ask_date_range(allow_year=True)
    n_days = (end - start).days + 1
    count = ask_int("Number of streaks", 1, 100, default=4)
    length = ask_int("Days in each streak", 1, min(366, n_days), default=7)
    per_day = ask_int("Contributions on each streak day", 1, 10_000, default=7)
    if count * length > n_days:
        warn("The streaks are longer than the available range; they will overlap.")
        if not confirm("Continue and merge the overlaps?", default=False):
            raise Cancelled
    counts = [0] * n_days
    if count == 1:
        offsets = [0]
    else:
        step = (n_days - length) / (count - 1)
        offsets = [round(index * step) for index in range(count)]
    for offset in offsets:
        for index in range(offset, min(n_days, offset + length)):
            counts[index] = max(counts[index], per_day)
    return Plan(
        f"Streak Builder · {count} × {length} "
        f"{plural(length, 'day')}",
        start, end, counts,
        notes=[f"{per_day} {plural(per_day, 'commit')} per streak day"],
    )


def option_gradient(cfg: RepoConfig) -> Plan:
    banner("Gradient / fade", "a smooth heat ramp across time")
    start, end = ask_date_range(allow_year=True)
    direction = ask_choice(
        "Gradient direction",
        [
            ("1", "Light → dark   · heat rises through the year"),
            ("2", "Dark → light   · cool down through the year"),
            ("3", "Bloom          · bright centre, soft edges"),
        ],
        default="1",
    )
    base = choose_base(cfg, start, end, "gradient")
    n_days = (end - start).days + 1
    counts: List[int] = []
    for index in range(n_days):
        t = index / (n_days - 1) if n_days > 1 else 0.5
        if direction == "1":
            level = 1 + round(3 * t)
        elif direction == "2":
            level = 4 - round(3 * t)
        else:
            level = round(1 + 3 * math.sin(math.pi * t))
        counts.append(LEVEL_COMMITS[level] * base)
    labels = {"1": "Light to dark", "2": "Dark to light", "3": "Bloom"}
    return Plan(f"Gradient · {labels[direction]}", start, end, counts,
                notes=[f"base {base}"])


def option_wave(cfg: RepoConfig) -> Plan:
    banner("Wave / pulse", "rhythmic bands of green with quiet troughs")
    start, end = ask_date_range(allow_year=True)
    waves = ask_float("Number of waves across the range", 0.25, 24.0, 4.0)
    base = choose_base(cfg, start, end, "wave")
    n_days = (end - start).days + 1
    counts: List[int] = []
    for index in range(n_days):
        t = index / max(1, n_days)
        level = round(2 + 2 * math.sin(2 * math.pi * waves * t - math.pi / 2))
        level = max(0, min(4, level))
        counts.append(LEVEL_COMMITS[level] * base)
    if not any(counts):
        counts[len(counts) // 2] = LEVEL_COMMITS[4] * base
    wave_word = "wave" if waves == 1 else "waves"
    return Plan(f"Wave · {waves:g} {wave_word}", start, end, counts,
                notes=[f"base {base}"])


def option_ripple(cfg: RepoConfig) -> Plan:
    banner("Ripple", "concentric rings radiating from the centre of the calendar")
    start, weeks, window_label = choose_art_window()
    spacing = ask_float("Distance between rings (weeks)", 0.5, 20.0, 3.0)
    end = start + timedelta(days=weeks * 7 - 1)
    base = choose_base(cfg, start, end, "ripple")
    grid = [[0] * weeks for _ in range(ROWS)]
    center_x = (weeks - 1) / 2.0
    for row in range(ROWS):
        for column in range(weeks):
            distance = math.hypot(column - center_x, (row - 3) * 1.35)
            level = round(2 + 2 * math.sin(distance / spacing * math.pi))
            grid[row][column] = max(0, min(4, level))
    if not any(any(row) for row in grid):
        grid[3][weeks // 2] = 4
    return plan_from_grid(
        f"Ripple · {spacing:g}-week rings", grid, start, base, window_label
    )


def option_constellation(cfg: RepoConfig) -> Plan:
    banner("Constellation", "mirrored stars scattered across the calendar")
    start, weeks, window_label = choose_art_window()
    density = ask_int("Star density (%)", 1, 80, default=16)
    symmetry = ask_choice(
        "Symmetry",
        [
            ("1", "Horizontal mirror  · left ↔ right"),
            ("2", "Vertical mirror    · top ↕ bottom"),
            ("3", "Kaleidoscope       · both axes"),
        ],
        default="1",
    )
    end = start + timedelta(days=weeks * 7 - 1)
    base = choose_base(cfg, start, end, "constellation")
    grid = [[0] * weeks for _ in range(ROWS)]
    half = (weeks + 1) // 2
    if symmetry == "1":          # left ↔ right
        rows = range(ROWS)
        columns = range(half)
    elif symmetry == "2":        # top ↕ bottom
        rows = range((ROWS + 1) // 2)
        columns = range(weeks)
    else:                        # both axes
        rows = range((ROWS + 1) // 2)
        columns = range(half)
    for row in rows:
        for column in columns:
            if random.random() * 100 >= density:
                continue
            level = random.choices((1, 2, 3, 4), weights=(4, 3, 2, 1))[0]
            grid[row][column] = max(grid[row][column], level)
            if symmetry in ("1", "3"):
                mirrored = weeks - 1 - column
                grid[row][mirrored] = max(grid[row][mirrored], level)
            if symmetry in ("2", "3"):
                opposite = ROWS - 1 - row
                grid[opposite][column] = max(grid[opposite][column], level)
                if symmetry == "3":
                    mirrored = weeks - 1 - column
                    grid[opposite][mirrored] = max(
                        grid[opposite][mirrored], level
                    )
    if not any(any(row) for row in grid):
        grid[3][weeks // 2] = 4
    labels = {"1": "horizontal", "2": "vertical", "3": "kaleidoscope"}
    return plan_from_grid(
        f"Constellation · {labels[symmetry]}",
        grid, start, base, window_label,
    )


# ---------------------------------------------------------------------------
# Review and execution
# ---------------------------------------------------------------------------

def review(cfg: RepoConfig, plan: Plan) -> bool:
    banner("Review", "a quick look before anything is written")
    active = [count for count in plan.counts if count]
    print_preview(plan)
    print()
    info(f"Mode        · {plan.label}")
    info(f"Repository  · {cfg.owner}/{cfg.repo}  (branch: {cfg.branch})")
    info(f"Author      · {cfg.name} <{cfg.email}>")
    info(f"Window      · {plan.start.isoformat()} → {plan.end.isoformat()}")
    if active:
        info(
            f"Per day     · min {fmt_int(min(active))} / max {fmt_int(max(active))} / "
            f"avg {plan.total / len(active):,.1f} on active days"
        )
        info(
            f"Activity    · {fmt_int(len(active))} active "
            f"{plural(len(active), 'day')}, "
            f"{fmt_int(plan.span - len(active))} empty"
        )
    for note in plan.notes:
        info(f"Note        · {note}")
    print()
    print(f"  {bold('Ready to create ' + fmt_int(plan.total) + ' '
                         + plural(plan.total, 'commit') + ' across '
                         + fmt_int(plan.span) + ' '
                         + plural(plan.span, 'day') + '.')}")
    batches = max(1, math.ceil(plan.total / DEFAULT_PUSH_BATCH))
    if batches > 1:
        info(f"Pushes will be batched ({batches} batches of ≤{DEFAULT_PUSH_BATCH} "
             "commits) so GitHub does not ignore large pushes.")
    if plan.end > date.today():
        warn("This plan includes future dates. Those squares appear only when the day arrives.")
    if plan.span > 371:
        warn("The profile shows a rolling year; older dates are visible in the year view.")
    if plan.total >= BIG_RUN_WARNING:
        warn(f"This is a large run ({fmt_int(plan.total)} commits); it can take a while.")
    print_legend_help()
    return confirm("Generate and push?", default=False)


def progress(done: int, total: int, started: float) -> None:
    width = 28
    fraction = done / total if total else 1.0
    filled = int(width * fraction)
    elapsed = time.time() - started
    rate = done / elapsed if elapsed > 0 else 0.0
    eta = (total - done) / rate if rate else 0.0
    sys.stdout.write(
        f"\r  [{green('#' * filled)}{dim('-' * (width - filled))}] "
        f"{fmt_int(done)}/{fmt_int(total)} ({fraction:5.1%})  "
        f"{rate:5.1f}/s  ETA {fmt_seconds(eta)}   "
    )
    sys.stdout.flush()


def day_stamps(day: date, count: int) -> Iterator[int]:
    origin = datetime(
        day.year, day.month, day.day,
        WINDOW_START_HOUR, tzinfo=timezone.utc,
    )
    span = (WINDOW_END_HOUR - WINDOW_START_HOUR) * 3600
    for index in range(count):
        moment = origin + timedelta(seconds=(index * span) // count)
        yield int(moment.timestamp())


def fast_import_batch(
    git: Git,
    branch: str,
    specs: Sequence[Tuple[int, str]],
    name: str,
    email: str,
    base: Optional[str],
) -> Optional[str]:
    if not specs:
        return base
    identity = f"{name} <{email}>".encode("utf-8")
    stream = bytearray()
    for index, (epoch, message) in enumerate(specs):
        stream += f"commit refs/heads/{branch}\n".encode("utf-8")
        stream += b"author " + identity + b" " + str(epoch).encode() + b" +0000\n"
        stream += b"committer " + identity + b" " + str(epoch).encode() + b" +0000\n"
        payload = message.encode("utf-8")
        stream += b"data " + str(len(payload)).encode() + b"\n" + payload + b"\n"
        if index == 0 and base:
            stream += f"from {base}\n".encode("utf-8")
    stream += b"done\n"
    git.run("fast-import", "--quiet", "--done", input_data=bytes(stream))
    return git.head()


def push_branch(cfg: RepoConfig, git: Git) -> bool:
    for attempt in range(1, 4):
        result = git.run("push", cfg.auth_url, cfg.branch, check=False)
        if result.returncode == 0:
            good(f"Push complete · origin/{cfg.branch}")
            return True
        detail = (result.stderr or result.stdout).strip()
        warn(f"Push attempt {attempt} failed.")
        if detail:
            print("    " + detail.replace("\n", "\n    "))
        lower = detail.lower()
        if "non-fast-forward" in lower or "fetch first" in lower:
            info("The remote moved while we were generating commits. Fetch/rebase")
            info("the local branch, then push again. Nothing is lost locally.")
            return False
        if "protected branch" in lower or "protected" in lower:
            info("The branch is protected. Allow pushes for this account or choose")
            info("another branch / repository.")
            return False
        if attempt < 3 and confirm("Retry the push?", default=True):
            continue
        break
    info(f"Your commits are safe locally in {cfg.workdir}")
    info(f"Retry manually with: git push origin {cfg.branch}")
    return False


def execute(cfg: RepoConfig, git: Git, plan: Plan) -> bool:
    rollback = git.head()
    total = plan.total
    print()
    print(f"  {bold('Painting the calendar')}  {dim('fast-import · batched pushes')}")
    done = 0
    started = time.time()
    batch: List[Tuple[int, str]] = []
    current_base = rollback
    pushed_any = False
    batch_size = DEFAULT_PUSH_BATCH
    report_every = max(50, total // 100)

    def flush(push_now: bool) -> bool:
        nonlocal done, batch, current_base, pushed_any
        if not batch:
            return True
        attempt_base = current_base
        try:
            current_base = fast_import_batch(
                git, cfg.branch, batch, cfg.name, cfg.email, attempt_base
            )
        except GitError:
            warn("fast-import failed; the pending batch was not applied.")
            raise
        done += len(batch)
        batch = []
        progress(done, total, started)
        if push_now:
            sys.stdout.write("\n")
            sys.stdout.flush()
            print(f"  Pushing {fmt_int(done)}/{fmt_int(total)} commits ...")
            if not push_branch(cfg, git):
                return False
            pushed_any = True
        return True

    try:
        for day, count in plan.schedule():
            for number, epoch in enumerate(day_stamps(day, count), start=1):
                prefix = "art" if plan.levels is not None else "chore"
                message = (
                    f"{prefix}: {day.isoformat()} contribution "
                    f"{number}/{count}"
                )
                batch.append((epoch, message))
                if len(batch) >= batch_size:
                    if not flush(push_now=total > batch_size):
                        return False
                elif (done + len(batch)) % report_every == 0:
                    progress(done + len(batch), total, started)
        if not flush(push_now=True):
            return False
    except KeyboardInterrupt:
        sys.stdout.write("\n")
        warn(f"Interrupted after {fmt_int(done)} commits. "
             "Those commits are local and were not necessarily pushed.")
        raise
    sys.stdout.write("\n")
    if total == 0:
        warn("Nothing to create.")
        return False
    good(f"Created {fmt_int(done)} {plural(done, 'commit')} "
         f"in {fmt_seconds(time.time() - started)}.")
    if not pushed_any:
        if not push_branch(cfg, git):
            return False
    if rollback:
        info(f"Rollback point before this run: {rollback}")
        info("To undo locally: git reset --hard " + rollback)
        if pushed_any:
            info("To undo remotely as well: git push --force origin " + cfg.branch)
    return True


def print_graph_checklist(cfg: RepoConfig) -> None:
    print()
    box(
        [
            f"{green('✓')} commit email is verified on your GitHub account",
            f"{green('✓')} push landed on the default branch (or gh-pages)",
            f"{green('✓')} repository is standalone, not a fork",
            f"{green('✓')} private repos: enable 'Include private contributions'",
            f"{green('✓')} graph updates can take a few minutes (occasionally 24h)",
            f"{green('✓')} shades are relative to your busiest day",
            f"{green('✓')} huge pushes are batched to avoid GitHub's contribution cap",
        ],
        width=66,
        title="AFTER THE PUSH",
    )
    info(f"Target · https://github.com/{cfg.owner}/{cfg.repo}")
    info("Old dates are visible through the year selector on your profile.")


# ---------------------------------------------------------------------------
# Menu and entry point
# ---------------------------------------------------------------------------

MENU_SECTIONS = (
    ("CREATE", (
        ("1", "Random Scatter", "organic heat across a year or range"),
        ("2", "Full Block", "one solid slab of green"),
        ("3", "Even Distribution", "spread a total evenly"),
    )),
    ("STUDIO", (
        ("4", "Pixel Art Studio", "gallery, custom matrix, image import"),
        ("5", "Text Banner", "5 × 7 lettering on the graph"),
        ("6", "Streak Builder", "controlled runs of consecutive days"),
        ("7", "Gradient / Fade", "light → dark ramps"),
        ("8", "Wave / Pulse", "rhythmic bands of green"),
        ("9", "Ripple", "concentric rings from the centre"),
        ("10", "Constellation", "mirrored random stars"),
    )),
)


def main_menu(cfg: RepoConfig) -> str:
    print()
    rule()
    print(f"  {green('GOGREEN')}  {dim('·')}  {cfg.owner}/{cfg.repo}  "
          f"{dim('·')}  branch {cfg.branch}")
    print(f"  {dim('author')}  {cfg.name} <{cfg.email}>")
    rule()
    valid = {"0"}
    for section, entries in MENU_SECTIONS:
        print(f"\n  {dim(section)}")
        for key, name, description in entries:
            valid.add(key)
            print(f"   {green(f'[{key:>2}]')}  {name:<22} {dim(description)}")
    print()
    print(f"   {red('[ 0]')}  Quit")
    print()
    print(f"  {dim('Made by Albatany 2026')}  {dim('·')}  "
          f"{dim('paint responsibly, keep a rollback point')}")
    rule()
    while True:
        try:
            choice = input(f"\n  {green('›')} Select an option: ").strip()
        except EOFError:
            raise KeyboardInterrupt
        if choice in valid:
            return choice
        warn("Choose one of the numbers shown above.")


def main() -> int:
    if len(sys.argv) > 1:
        if sys.argv[1] in ("--version", "-V"):
            print(f"{APP_NAME} {VERSION} · Made by {AUTHOR} {RELEASE}")
            return 0
        if sys.argv[1] in ("--help", "-h"):
            print(__doc__.strip())
            return 0

    if shutil.which("git") is None:
        fail("Git is not installed or not on PATH. Install it from https://git-scm.com")
        return 1
    try:
        validate_templates()
        validate_font()
    except ArtError as exc:
        fail(f"Internal artwork error: {exc}")
        return 1

    header()
    cfg: Optional[RepoConfig] = None
    git: Optional[Git] = None
    try:
        cfg = collect_settings()
        git = Git(cfg.workdir, cfg.secrets)
        prepare_repo(cfg, git)

        builders: Dict[str, Callable[[], Plan]] = {
            "1": option_random,
            "2": option_block,
            "3": option_even,
            "4": lambda: option_pixel_art(cfg),
            "5": lambda: option_text(cfg),
            "6": option_streak,
            "7": lambda: option_gradient(cfg),
            "8": lambda: option_wave(cfg),
            "9": lambda: option_ripple(cfg),
            "10": lambda: option_constellation(cfg),
        }

        while True:
            choice = main_menu(cfg)
            if choice == "0":
                break
            try:
                plan = builders[choice]()
            except Cancelled:
                info("Cancelled. Nothing was changed.")
                continue
            except (AppError, ArtError) as exc:
                warn(str(exc))
                continue
            if plan.total <= 0:
                warn("That plan contains no commits.")
                continue
            if not review(cfg, plan):
                info("Cancelled. Nothing was changed.")
                continue
            try:
                finished = execute(cfg, git, plan)
            except GitError as exc:
                fail(str(exc))
                info("Your local repository is intact; fix the error and re-run.")
                finished = False
            if finished:
                print_graph_checklist(cfg)
            else:
                warn("Run stopped before completion; read the messages above.")
            if not confirm("\nRun another job?", default=False):
                break

        print()
        print(f"  {green('Done.')}  {dim('May your graph bloom.')}")
        print(f"  {dim('Made by Albatany 2026')}")
        return 0
    except KeyboardInterrupt:
        print(f"\n  {amber('Aborted by user.')}")
        return 130
    except AppError as exc:
        fail(str(exc))
        return 1
    except Exception as exc:
        fail(f"Unexpected error: {exc}")
        return 1
    finally:
        # Belt and braces: never leave a token in .git/config.  Only rewrite an
        # origin that really belongs to the selected repository; a cancelled
        # origin-mismatch confirmation must leave the user's remote untouched.
        if cfg and (cfg.workdir / ".git").exists():
            try:
                safe_git = Git(cfg.workdir, cfg.secrets)
                if _origin_matches(safe_git, cfg):
                    safe_git.run(
                        "remote", "set-url", "origin", cfg.clean_url, check=False
                    )
            except Exception:
                pass


if __name__ == "__main__":
    sys.exit(main())

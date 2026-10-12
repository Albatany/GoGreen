#!/usr/bin/env python3
"""
git_backdate.py - Interactive tool that creates backdated *empty* commits and
pushes them to a GitHub repository.

Requirements : Python 3.8+ and Git (no third-party packages needed)
Run          : python git_backdate.py        (Windows: py git_backdate.py)

Three placement modes:
  1) Random scattering      - N commits spread organically over a year / range
  2) Full block             - a flat X commits per day over a date range
  3) Even distribution      - total commits divided evenly across the range
"""
from __future__ import annotations

import os
import random
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from getpass import getpass
from pathlib import Path
from typing import Callable, Iterator, List, Optional, Tuple
from urllib.parse import quote

MIN_DATE = date(2021, 1, 1)   # earliest date the tool accepts (you can change sync with your account)
WINDOW_START_HOUR = 8         
WINDOW_END_HOUR = 20          
TZ_SUFFIX = "+0000"           
BIG_RUN_WARNING = 50_000      

if os.name == "nt":
    os.system("")             
USE_COLOR = sys.stdout.isatty()

def paint(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if USE_COLOR else text


def banner(title: str) -> None:
    line = "=" * 66
    print(f"\n{paint(line, '36')}\n{paint('  ' + title, '1;36')}\n{paint(line, '36')}")


def info(msg: str) -> None:
    print(f"  {msg}")


def good(msg: str) -> None:
    print(paint(f"  [ok] {msg}", "32"))


def warn(msg: str) -> None:
    print(paint(f"  [!] {msg}", "33"))


def ask(prompt: str, default: Optional[str] = None,
        validator: Optional[Callable[[str], object]] = None,
        secret: bool = False):
    """Prompt until the answer is non-empty and passes the validator."""
    suffix = f" [{default}]" if default else ""
    while True:
        raw = (getpass if secret else input)(f"{prompt}{suffix}: ").strip()
        if not raw and default is not None:
            raw = default
        if not raw:
            warn("A value is required.")
            continue
        if validator is None:
            return raw
        try:
            return validator(raw)
        except ValueError as exc:
            warn(str(exc))


def ask_int(prompt: str, minimum: int, maximum: int,
            default: Optional[int] = None) -> int:
    def check(raw: str) -> int:
        try:
            number = int(raw.replace(",", "").replace("_", ""))
        except ValueError:
            raise ValueError("Please enter a whole number.")
        if not minimum <= number <= maximum:
            raise ValueError(f"Enter a number between {minimum:,} and {maximum:,}.")
        return number

    return ask(prompt, None if default is None else str(default), check)


def confirm(prompt: str, default: bool = False) -> bool:
    hint = "Y/n" if default else "y/N"
    while True:
        raw = input(f"{prompt} [{hint}]: ").strip().lower()
        if not raw:
            return default
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False
        warn("Please answer Y or N.")

def parse_repo_url(raw: str) -> Tuple[str, str]:
    """Accepts https://github.com/o/r(.git), git@github.com:o/r, or o/r."""
    text = re.sub(r"^(?:https?://(?:[^@/]+@)?|git@)(?:www\.)?github\.com(?:[/:]|$)",
                  "", raw.strip(), flags=re.I)
    text = text.split("?")[0].split("#")[0].strip("/")
    text = re.sub(r"\.git$", "", text)
    parts = [p for p in text.split("/") if p]
    if len(parts) < 2:
        raise ValueError("Could not find owner/repo. Expected something like "
                         "https://github.com/<owner>/<repo>")
    owner, repo = parts[0], parts[1]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", owner) or not re.fullmatch(r"[A-Za-z0-9_.-]+", repo):
        raise ValueError("Owner/repo contain unsupported characters.")
    return owner, repo


def check_username(raw: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9-]+", raw):
        raise ValueError("GitHub usernames only contain letters, digits and hyphens.")
    return raw


def check_email(raw: str) -> str:
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", raw):
        raise ValueError("That does not look like an email address.")
    return raw


def check_day(raw: str) -> date:
    try:
        day = datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError("Use the format YYYY-MM-DD (e.g. 2023-04-01).")
    if day < MIN_DATE:
        raise ValueError(f"Date must be on or after {MIN_DATE.isoformat()}.")
    if day > date.today():
        raise ValueError("Date cannot be in the future.")
    return day


def ask_date_range(allow_year: bool = False) -> Tuple[date, date]:
    today = date.today()
    if allow_year:
        while True:
            raw = input(f"Year ({MIN_DATE.year}-{today.year}) or press Enter for a "
                        f"custom date range: ").strip()
            if not raw:
                break
            if raw.isdigit() and MIN_DATE.year <= int(raw) <= today.year:
                year = int(raw)
                return date(year, 1, 1), min(date(year, 12, 31), today)
            warn(f"Enter a year between {MIN_DATE.year} and {today.year}.")
    start = ask("Start date (YYYY-MM-DD)", validator=check_day)
    while True:
        end = ask("End date   (YYYY-MM-DD)", default=today.isoformat(), validator=check_day)
        if end >= start:
            return start, end
        warn("End date must be on or after the start date.")

class GitError(RuntimeError):
    pass


class Git:
    def __init__(self, cwd: Path, secrets: List[str]):
        self.cwd = cwd
        self.secrets = [s for s in secrets if s]

    def redact(self, text: str) -> str:
        for secret in self.secrets:
            text = text.replace(secret, "***")
        return re.sub(r"(://)[^/@\s]+:[^/@\s]+@", r"\1***@", text)

    def run(self, *args: str, env: Optional[dict] = None,
            check: bool = True) -> subprocess.CompletedProcess:
        full_env = os.environ.copy()
        full_env["GIT_TERMINAL_PROMPT"] = "0"          
        if env:
            full_env.update(env)
        proc = subprocess.run(
            ["git", "-c", "credential.helper=", *args],
            cwd=str(self.cwd), env=full_env, text=True,
            encoding="utf-8", errors="replace",
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        proc.stdout = self.redact(proc.stdout or "")
        proc.stderr = self.redact(proc.stderr or "")
        if check and proc.returncode != 0:
            detail = (proc.stderr or proc.stdout).strip()
            raise GitError(f"`git {args[0]}` failed: {detail}")
        return proc

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
    keep_token: bool = False

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
    banner("1 | REPOSITORY SETUP")
    owner, repo = ask("Target repository URL (https://github.com/<owner>/<repo>)",
                      validator=parse_repo_url)
    username = ask("GitHub username", default=owner, validator=check_username)
    token = ask("Personal Access Token (classic, 'repo' scope; input hidden)", secret=True)
    name = ask("Git author name", default=username)
    email = ask("Git author email (must be verified on your GitHub account)",
                default=f"{username}@users.noreply.github.com", validator=check_email)
    folder = ask("Local working folder", default=f"./{repo}")
    workdir = Path(folder).expanduser().resolve()

    cfg = RepoConfig(owner, repo, username, token, name, email, workdir)

    print("\nChecking access to the repository ...")
    probe = Git(Path.cwd(), cfg.secrets).run(
        "ls-remote", "--symref", cfg.auth_url, "HEAD", check=False)
    if probe.returncode != 0:
        raise GitError("Could not reach the repository - check the URL, the token "
                       f"scope and your connection.\n  {probe.stderr.strip()}")
    good("Repository reachable, token accepted.")
    match = re.search(r"ref: refs/heads/(\S+)\s+HEAD", probe.stdout)
    detected = match.group(1) if match else None

    cfg.branch = ask("Branch to commit to and push", default=detected or "main")
    if detected and cfg.branch != detected:
        warn(f"The repo's default branch is '{detected}'. GitHub only counts commits "
             "on the default branch (or gh-pages).")
    cfg.keep_token = confirm("Keep the token inside the saved remote URL when "
                             "finished? (not recommended)", default=False)
    return cfg


def prepare_repo(cfg: RepoConfig, git: Git) -> None:
    cfg.workdir.mkdir(parents=True, exist_ok=True)
    if not (cfg.workdir / ".git").exists():
        git.run("init")
        good(f"Initialised a new repository in {cfg.workdir}")

    # Make sure we are on the requested branch (works on unborn branches too).
    current = git.run("symbolic-ref", "--short", "-q", "HEAD", check=False).stdout.strip()
    if current != cfg.branch:
        exists = git.run("show-ref", "--verify", "--quiet",
                         f"refs/heads/{cfg.branch}", check=False).returncode == 0
        git.run("checkout", cfg.branch) if exists else git.run("checkout", "-b", cfg.branch)

    remotes = git.run("remote").stdout.split()
    git.run("remote", "set-url" if "origin" in remotes else "add", "origin", cfg.auth_url)
    git.run("config", "user.name", cfg.name)
    git.run("config", "user.email", cfg.email)
    good(f"Remote 'origin' set, author = {cfg.name} <{cfg.email}>")

    # Pull in existing history so the final push is a plain fast-forward.
    fetched = git.run("fetch", "origin", cfg.branch, check=False)
    if fetched.returncode == 0:
        has_commits = git.run("rev-parse", "--verify", "-q", "HEAD",
                              check=False).returncode == 0
        if not has_commits:
            git.run("reset", "--hard", "FETCH_HEAD")
            good(f"Synced with existing origin/{cfg.branch}")
        else:
            merged = git.run("merge", "--ff-only", "FETCH_HEAD", check=False)
            if merged.returncode != 0:
                warn("Local history has diverged from the remote; the push may be rejected.")
    else:
        info(f"origin/{cfg.branch} does not exist yet - it will be created on push.")

@dataclass
class Plan:
    label: str
    start: date
    end: date
    counts: List[int]               # one entry per day, start..end inclusive

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


def days_between(start: date, end: date) -> List[date]:
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def apportion(weights: List[float], total: int) -> List[int]:
    """Split `total` proportionally to `weights` (largest-remainder method)."""
    weight_sum = sum(weights)
    raw = [w / weight_sum * total for w in weights]
    counts = [int(r) for r in raw]
    leftover = total - sum(counts)
    candidates = sorted((i for i, w in enumerate(weights) if w > 0),
                        key=lambda i: raw[i] - counts[i], reverse=True)
    for i in candidates[:leftover]:
        counts[i] += 1
    return counts


def plan_random(days: List[date], total: int, empty_pct: int) -> List[int]:
    weights = []
    for day in days:
        if random.random() < empty_pct / 100:
            weights.append(0.0)                              # a quiet day
            continue
        weight = random.lognormvariate(0, 0.9)               # a few big days, many small
        if day.weekday() >= 5:
            weight *= 0.5                                    # weekends are calmer
        weights.append(weight)
    if not any(weights):
        weights[random.randrange(len(days))] = 1.0
    return apportion(weights, total)


def plan_even(n_days: int, total: int) -> List[int]:
    base, remainder = divmod(total, n_days)
    counts = [base] * n_days
    for k in range(remainder):                              
        counts[(k * n_days) // remainder] += 1
    return counts


def day_stamps(day: date, count: int) -> Iterator[str]:
    """`count` ISO-8601 timestamps spread evenly between the daily window."""
    origin = datetime(day.year, day.month, day.day, WINDOW_START_HOUR)
    span = (WINDOW_END_HOUR - WINDOW_START_HOUR) * 3600
    for i in range(count):
        moment = origin + timedelta(seconds=(i * span) // count)
        yield moment.strftime("%Y-%m-%dT%H:%M:%S") + TZ_SUFFIX

def option_random() -> Plan:
    banner("RANDOM SCATTERING")
    start, end = ask_date_range(allow_year=True)
    total = ask_int("Total number of contributions", 1, 1_000_000)
    empty_pct = ask_int("Roughly what % of days should stay empty", 0, 90, default=30)
    days = days_between(start, end)
    return Plan("Random scattering", start, end, plan_random(days, total, empty_pct))


def option_block() -> Plan:
    banner("FULL BLOCK / SPECIFIC MONTHS")
    start, end = ask_date_range()
    per_day = ask_int("Contributions per day (e.g. 120)", 1, 10_000)
    n_days = (end - start).days + 1
    return Plan("Full block", start, end, [per_day] * n_days)


def option_even() -> Plan:
    banner("EVEN DISTRIBUTION")
    start, end = ask_date_range()
    n_days = (end - start).days + 1
    total = ask_int("Total target contributions", 1, 1_000_000)
    if total < n_days:
        warn(f"{total:,} commits over {n_days:,} days means some days get none "
             "(they are spaced out evenly).")
    elif total % n_days:
        info(f"{total:,} / {n_days:,} is not a whole number; the remainder is "
             "spread evenly (some days get +1).")
    return Plan("Even distribution", start, end, plan_even(n_days, total))

def review(cfg: RepoConfig, plan: Plan) -> bool:
    banner("SUMMARY")
    active = [c for c in plan.counts if c]
    info(f"Mode        : {plan.label}")
    info(f"Repository  : {cfg.owner}/{cfg.repo}  (branch: {cfg.branch})")
    info(f"Author      : {cfg.name} <{cfg.email}>")
    info(f"Date range  : {plan.start.isoformat()} -> {plan.end.isoformat()}")
    info(f"Per day     : min {min(active):,} / max {max(active):,} / "
         f"avg {plan.total / plan.span:,.1f}   "
         f"({len(active):,} active day(s), {plan.span - len(active):,} empty)")
    print()
    print(paint(f"  Ready to generate {plan.total:,} total commits across "
                f"{plan.span:,} days.", "1"))
    if plan.total >= BIG_RUN_WARNING:
        warn("That is a very large run - it can take a long while on slow disks.")
    return confirm("Proceed?", default=False)


def fmt_seconds(seconds: float) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h{m:02d}m" if h else f"{m}m{s:02d}s"


def progress(done: int, total: int, started: float) -> None:
    width = 30
    fraction = done / total
    filled = int(width * fraction)
    elapsed = time.time() - started
    rate = done / elapsed if elapsed > 0 else 0.0
    eta = (total - done) / rate if rate else 0.0
    sys.stdout.write(f"\r  [{'#' * filled}{'-' * (width - filled)}] {done:,}/{total:,} "
                     f"({fraction:5.1%})  {rate:5.1f}/s  ETA {fmt_seconds(eta)}   ")
    sys.stdout.flush()


def execute(cfg: RepoConfig, git: Git, plan: Plan) -> None:
    head = git.run("rev-parse", "--verify", "-q", "HEAD", check=False)
    rollback = head.stdout.strip() if head.returncode == 0 else None

    print()
    done, started = 0, time.time()
    try:
        for day, count in plan.schedule():
            for number, stamp in enumerate(day_stamps(day, count), start=1):
                git.run(
                    "commit", "--allow-empty", "--no-verify", "--no-gpg-sign", "-q",
                    "-m", f"chore: contribution {day.isoformat()} #{number}",
                    env={"GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp},
                )
                done += 1
                if done % 20 == 0 or done == plan.total:
                    progress(done, plan.total, started)
    except KeyboardInterrupt:
        print()
        warn(f"Interrupted after {done:,} commits. They exist locally but were NOT pushed.")
        raise
    print()
    good(f"Created {done:,} commits in {fmt_seconds(time.time() - started)}.")

    print(f"\n  Pushing to origin/{cfg.branch} (this can take a moment) ...")
    pushed = git.run("push", "-u", "origin", cfg.branch, check=False)
    if pushed.returncode != 0:
        warn("Push failed:")
        print("    " + (pushed.stderr or pushed.stdout).strip().replace("\n", "\n    "))
        info("Your commits are safe locally. Fix the problem, then run:")
        info(f"    cd \"{cfg.workdir}\" && git push -u origin {cfg.branch}")
        return
    good("Push complete.")
    if rollback:
        info(f"Rollback point (state before this run): {rollback}")
        info(f"To undo: git reset --hard {rollback} && git push --force origin {cfg.branch}")


def print_graph_checklist() -> None:
    print("""
  If squares do not appear, check that:
    - the commit email is a verified email on your GitHub account
    - the push went to the repository's default branch
    - the repository is not a fork
    - for private repos, 'Include private contributions' is enabled in your profile
  Updates can take a few minutes. Shading is relative to YOUR busiest day, so a
  uniform block (option 2) makes every day in it the darkest green.""")

def main_menu() -> str:
    banner("2 | MAIN MENU")
    print("  [1] Random Scattering          - N commits spread organically (year / range)")
    print("  [2] Full Block / Specific Months - flat commits per day (darkest green)")
    print("  [3] Even Distribution          - total divided equally across the days")
    print("  [0] Quit")
    while True:
        choice = input("\nSelect an option [0-3]: ").strip()
        if choice in {"0", "1", "2", "3"}:
            return choice
        warn("Please type 0, 1, 2 or 3.")


def main() -> int:
    if shutil.which("git") is None:
        print("Git is not installed or not on PATH. Install it from https://git-scm.com")
        return 1

    cfg: Optional[RepoConfig] = None
    git: Optional[Git] = None
    try:
        cfg = collect_settings()
        git = Git(cfg.workdir, cfg.secrets)
        prepare_repo(cfg, git)

        builders = {"1": option_random, "2": option_block, "3": option_even}
        while True:
            choice = main_menu()
            if choice == "0":
                break
            plan = builders[choice]()
            if not review(cfg, plan):
                info("Cancelled - nothing was changed.")
                continue
            execute(cfg, git, plan)
            print_graph_checklist()
            if not confirm("\nRun another job?", default=False):
                break
        print("\nDone.")
        return 0
    except KeyboardInterrupt:
        print("\nAborted by user.")
        return 130
    except GitError as exc:
        print(paint(f"\nError: {exc}", "31"))
        return 1
    finally:
        # Remove the token from .git/config unless the user asked to keep it.
        if cfg and git and not cfg.keep_token and (cfg.workdir / ".git").exists():
            git.run("remote", "set-url", "origin", cfg.clean_url, check=False)


if __name__ == "__main__":
    sys.exit(main())

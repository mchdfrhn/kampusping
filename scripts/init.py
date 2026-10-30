#!/usr/bin/env python3
"""Turn this template into your own project: names, branding, ports, folders.

    python scripts/init.py --name "Acme Portal" --slug acme-portal --color "#0F766E"
    python scripts/init.py                      # prompts for anything you leave out
    python scripts/init.py --dry-run ...        # show what would change, touch nothing

It rewrites package/PM2/Nginx/Docker names, the app name and brand color, the deploy ports, and
renames the two repo folders to ``<slug>-backend`` and ``<slug>-frontend``. Run it once, right
after cloning, before your first commit. Standard library only.
"""

from __future__ import annotations

import argparse
import re
import secrets
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SKIP_DIRS = {".git", ".venv", "venv", "node_modules", ".next", "__pycache__", ".pytest_cache",
             ".ruff_cache", "coverage", "playwright-report", "test-results", ".mypy_cache"}
TEXT_SUFFIXES = {".py", ".ts", ".tsx", ".mts", ".js", ".cjs", ".mjs", ".json", ".md", ".toml",
                 ".txt", ".yml", ".yaml", ".sh", ".conf", ".example", ".ini", ".css", ".html", ""}
TEXT_NAMES = {"Dockerfile", ".env.example", ".dockerignore", ".gitignore", ".gitattributes"}
SKIP_FILES = {"package-lock.json", "LICENSE"}

DEFAULT_NAME = "Webapp"
DEFAULT_COLOR = "#4F46E5"
DEFAULT_API_PORT = 8093
DEFAULT_WEB_PORT = 8094


@dataclass(frozen=True)
class Settings:
    name: str
    slug: str
    color: str
    api_port: int
    web_port: int

    @property
    def snake(self) -> str:
        return self.slug.replace("-", "_")


def find_repo(marker: str) -> Path:
    matches = [p for p in ROOT.iterdir() if p.is_dir() and (p / marker).exists()]
    if len(matches) != 1:
        sys.exit(f"Expected exactly one folder containing {marker!r} under {ROOT}, found {len(matches)}.")
    return matches[0]


def validate(settings: Settings) -> None:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 &.\-]{0,39}", settings.name):
        sys.exit("--name: 1-40 characters: letters, digits, spaces, & . -")
    if not re.fullmatch(r"[a-z][a-z0-9-]{1,39}", settings.slug):
        sys.exit("--slug: lowercase letters, digits and dashes, starting with a letter (2-40 chars)")
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", settings.color):
        sys.exit("--color: a hex color such as #0F766E")
    for label, port in (("--api-port", settings.api_port), ("--web-port", settings.web_port)):
        if not 1024 <= port <= 65535:
            sys.exit(f"{label}: use a port between 1024 and 65535")
    if settings.api_port == settings.web_port:
        sys.exit("--api-port and --web-port must differ")


def text_files(base: Path):
    for path in base.rglob("*"):
        if not path.is_file() or SKIP_DIRS & set(path.relative_to(base).parts):
            continue
        if path.name in SKIP_FILES:
            continue
        if path.name in TEXT_NAMES or path.suffix in TEXT_SUFFIXES:
            yield path


def build_replacements(settings: Settings, old_backend: str, old_frontend: str) -> list[tuple[str, str]]:
    new_backend, new_frontend = f"{settings.slug}-backend", f"{settings.slug}-frontend"
    pairs = [
        # Longest / most specific first so shorter tokens do not clobber them.
        ("webapp_backend_prod", f"{settings.snake}_backend_prod"),
        ("webapp_frontend_prod", f"{settings.snake}_frontend_prod"),
        ("webapp-backend", new_backend),
        ("webapp-frontend", new_frontend),
        (old_backend, new_backend),
        (old_frontend, new_frontend),
        ("Webapp API", f"{settings.name} API"),
        ("Webapp Backend", f"{settings.name} Backend"),
        ("Webapp Frontend", f"{settings.name} Frontend"),
        ("NEXT_PUBLIC_APP_NAME=Webapp", f"NEXT_PUBLIC_APP_NAME={settings.name}"),
        ("NEXT_PUBLIC_APP_NAME ?? 'Webapp'", f"NEXT_PUBLIC_APP_NAME ?? '{settings.name}'"),
        ("NEXT_PUBLIC_APP_NAME=Webapp", f"NEXT_PUBLIC_APP_NAME={settings.name}"),
        ("PREFIX = 'webapp'", f"PREFIX = '{settings.slug}'"),
        (DEFAULT_COLOR, settings.color.upper()),
        (DEFAULT_COLOR.lower(), settings.color.lower()),
    ]
    seen: set[str] = set()
    unique = []
    for old, new in pairs:
        if old and old not in seen and old != new:
            seen.add(old)
            unique.append((old, new))
    return unique


def port_replacements(settings: Settings) -> dict[str, list[tuple[str, str]]]:
    return {
        "backend": [(str(DEFAULT_API_PORT), str(settings.api_port))],
        "frontend": [(str(DEFAULT_WEB_PORT), str(settings.web_port))],
    }


def apply_text(path: Path, pairs: list[tuple[str, str]], dry_run: bool) -> bool:
    try:
        original = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return False
    updated = original
    for old, new in pairs:
        updated = updated.replace(old, new)
    if updated == original:
        return False
    if not dry_run:
        path.write_text(updated, encoding="utf-8", newline="")
    return True


def make_env_files(backend: Path, frontend: Path, dry_run: bool) -> list[str]:
    created = []
    for source, target in ((backend / ".env.example", backend / ".env"),
                           (frontend / ".env.example", frontend / ".env.local")):
        if target.exists() or not source.exists():
            continue
        content = source.read_text(encoding="utf-8")
        content = re.sub(r"^SECRET_KEY=.*$", f"SECRET_KEY={secrets.token_urlsafe(48)}", content, flags=re.M)
        if not dry_run:
            target.write_text(content, encoding="utf-8")
        created.append(str(target.relative_to(ROOT)))
    return created


def prompt(label: str, default: str) -> str:
    try:
        answer = input(f"{label} [{default}]: ").strip()
    except EOFError:  # stdin is not really interactive (CI, piped input): take the default
        print()
        return default
    return answer or default


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--name", help="Display name, e.g. 'Acme Portal'")
    parser.add_argument("--slug", help="Lowercase id used in folder/PM2/package names, e.g. acme-portal")
    parser.add_argument("--color", help=f"Brand color (default {DEFAULT_COLOR})")
    parser.add_argument("--api-port", type=int, help=f"Backend production port (default {DEFAULT_API_PORT})")
    parser.add_argument("--web-port", type=int, help=f"Frontend production port (default {DEFAULT_WEB_PORT})")
    parser.add_argument("--no-rename", action="store_true", help="Keep the folder names")
    parser.add_argument("--make-env", action="store_true", help="Also create local .env files with a fresh SECRET_KEY")
    parser.add_argument("--dry-run", action="store_true", help="Show the changes without writing")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    interactive = sys.stdin.isatty()

    name = args.name or (prompt("Project name", "My App") if interactive else None)
    if not name:
        sys.exit("--name is required (or run in an interactive terminal).")
    default_slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "app"
    slug = args.slug or (prompt("Slug", default_slug) if interactive else default_slug)
    color = args.color or (prompt("Brand color", DEFAULT_COLOR) if interactive else DEFAULT_COLOR)
    api_port = args.api_port or DEFAULT_API_PORT
    web_port = args.web_port or DEFAULT_WEB_PORT

    settings = Settings(name=name, slug=slug, color=color, api_port=api_port, web_port=web_port)
    validate(settings)

    backend = find_repo("alembic.ini")
    frontend = find_repo("next.config.ts")
    new_backend_name, new_frontend_name = f"{slug}-backend", f"{slug}-frontend"

    pairs = build_replacements(settings, backend.name, frontend.name)
    ports = port_replacements(settings)
    changed: list[str] = []

    for path in text_files(ROOT):
        relative = path.relative_to(ROOT)
        file_pairs = list(pairs)
        if "deploy" in relative.parts:
            if relative.parts[0] == backend.name:
                file_pairs += ports["backend"]
            elif relative.parts[0] == frontend.name:
                file_pairs += ports["frontend"]
        if relative.parts[0] == "scripts":
            continue  # never rewrite this script's own defaults
        if apply_text(path, file_pairs, args.dry_run):
            changed.append(str(relative))

    created_env = make_env_files(backend, frontend, args.dry_run) if args.make_env else []

    renamed: list[str] = []
    if not args.no_rename:
        for current, target in ((backend, new_backend_name), (frontend, new_frontend_name)):
            if current.name == target:
                continue
            if (ROOT / target).exists():
                sys.exit(f"Cannot rename {current.name}: {target} already exists.")
            renamed.append(f"{current.name} -> {target}")
            if not args.dry_run:
                try:
                    shutil.move(str(current), str(ROOT / target))
                except OSError as error:
                    sys.exit(
                        f"Could not rename {current.name} ({error}). Close editors/terminals that have "
                        "the folder open (VS Code locks folders on Windows) and run again."
                    )

    prefix = "[dry run] " if args.dry_run else ""
    print(f"{prefix}Updated {len(changed)} file(s).")
    for item in changed:
        print(f"  ~ {item}")
    for item in created_env:
        print(f"  + {item}")
    for item in renamed:
        print(f"  > {item}")
    print(f"\n{prefix}Next: backend `pip install -r requirements-dev.txt`, frontend `npm install`, "
          "then see README.md.")


if __name__ == "__main__":
    main()

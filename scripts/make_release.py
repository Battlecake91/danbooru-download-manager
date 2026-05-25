#!/usr/bin/env python3
"""
Build and optionally publish a Danbooru Download Manager release.

This script is intended to be started from VSCode via .vscode/tasks.json
or .vscode/launch.json.

It will:
- verify the Git working tree
- ensure build artifacts are ignored
- clean build folders
- run PyInstaller
- package the dist output into release/*.zip
- optionally create/upload a GitHub release via gh CLI

Requirements:
- Python 3.10+
- PyInstaller installed in the active environment
- optional: GitHub CLI `gh` for publishing
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Iterable


APP_NAME = "DanbooruManager"
UPDATER_NAME = "DanbooruManagerUpdater"
DEFAULT_VERSION = "1.3.142"
DEFAULT_RELEASE_NAME = "Danbooru Download Manager"
DEFAULT_ENTRYPOINT_CANDIDATES = [
    "main.py",
    "app.py",
    "danbooru_manager.py",
    "src/main.py",
    "src/danbooru_manager/main.py",
]


def print_step(message: str) -> None:
    print(f"\n=== {message} ===")


def print_info(message: str) -> None:
    print(f"[INFO] {message}")


def print_warn(message: str) -> None:
    print(f"[WARN] {message}")


def print_error(message: str) -> None:
    print(f"[ERROR] {message}")


def run_command(
    command: list[str],
    cwd: Path,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    print_info("Running: " + " ".join(command))

    completed = subprocess.run(
        command,
        cwd=str(cwd),
        text=True,
        stdout=sys.stdout,
        stderr=sys.stderr,
        env=env,
    )

    if check and completed.returncode != 0:
        raise RuntimeError(f"Command failed with exit code {completed.returncode}: {' '.join(command)}")

    return completed


def command_exists(command: str) -> bool:
    return shutil.which(command) is not None


def find_project_root() -> Path:
    current = Path(__file__).resolve()

    for parent in [current.parent, *current.parents]:
        if (parent / ".git").exists():
            return parent

    return Path.cwd().resolve()


def ensure_gitignore(project_root: Path) -> None:
    gitignore_path = project_root / ".gitignore"

    required_entries = [
        "",
        "# Release/build artifacts",
        "release/",
        "dist/",
        "build/",
        "*.zip",
        "*.exe",
        "*.msi",
        "*.spec.build/",
        "",
        "# Local application data",
        "danbooru_manager_data/",
        "*.db",
        "*.db-wal",
        "*.db-shm",
        "*.log",
    ]

    existing = gitignore_path.read_text(encoding="utf-8") if gitignore_path.exists() else ""

    changed = False
    lines_to_append: list[str] = []

    for entry in required_entries:
        if entry == "":
            continue
        if entry not in existing:
            lines_to_append.append(entry)
            changed = True

    if changed:
        with gitignore_path.open("a", encoding="utf-8", newline="\n") as f:
            if existing and not existing.endswith("\n"):
                f.write("\n")
            f.write("\n# Release/build artifacts\n")
            for entry in lines_to_append:
                if entry.startswith("#"):
                    continue
                f.write(entry + "\n")

        print_info(".gitignore updated.")
    else:
        print_info(".gitignore already contains release/build ignores.")


def check_git_status(project_root: Path, allow_dirty: bool) -> None:
    if not (project_root / ".git").exists():
        print_warn("No .git directory found. Skipping Git checks.")
        return

    completed = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=str(project_root),
        text=True,
        capture_output=True,
    )

    if completed.returncode != 0:
        print_warn("Could not read Git status. Skipping Git cleanliness check.")
        return

    status = completed.stdout.strip()

    if status and not allow_dirty:
        print_error("Working tree is not clean.")
        print(status)
        raise RuntimeError(
            "Commit or stash changes first, or use --allow-dirty. "
            "Ja, Git will auch Aufmerksamkeit."
        )

    if status:
        print_warn("Working tree is dirty, but --allow-dirty was set.")
    else:
        print_info("Git working tree is clean.")


def remove_paths(paths: Iterable[Path]) -> None:
    for path in paths:
        if not path.exists():
            continue

        if path.is_dir():
            shutil.rmtree(path)
            print_info(f"Removed directory: {path}")
        else:
            path.unlink()
            print_info(f"Removed file: {path}")


def find_spec_file(project_root: Path, explicit_spec: str | None) -> Path | None:
    if explicit_spec:
        spec_path = project_root / explicit_spec
        if not spec_path.exists():
            raise FileNotFoundError(f"Spec file not found: {spec_path}")
        return spec_path

    candidates = [
        project_root / f"{APP_NAME}.spec",
        project_root / "danbooru_manager.spec",
        project_root / "DanbooruManager.spec",
    ]

    for candidate in candidates:
        if candidate.exists():
            return candidate

    spec_files = sorted(project_root.glob("*.spec"))
    if len(spec_files) == 1:
        return spec_files[0]

    return None


def find_entrypoint(project_root: Path, explicit_entrypoint: str | None) -> Path:
    if explicit_entrypoint:
        entrypoint = project_root / explicit_entrypoint
        if not entrypoint.exists():
            raise FileNotFoundError(f"Entrypoint not found: {entrypoint}")
        return entrypoint

    for candidate in DEFAULT_ENTRYPOINT_CANDIDATES:
        path = project_root / candidate
        if path.exists():
            return path

    raise FileNotFoundError(
        "Could not auto-detect entrypoint. "
        "Use --entrypoint path/to/main.py or provide a .spec file."
    )


def build_with_pyinstaller(
    project_root: Path,
    version: str,
    spec_file: Path | None,
    entrypoint: Path | None,
    onefile: bool,
    windowed: bool,
    icon: str | None,
) -> Path:
    if not command_exists("pyinstaller"):
        raise RuntimeError(
            "PyInstaller was not found in PATH. Install it with: pip install pyinstaller"
        )

    print_step("Building application with PyInstaller")

    if spec_file:
        command = [
            "pyinstaller",
            "--noconfirm",
            "--clean",
            str(spec_file.relative_to(project_root)),
        ]
    else:
        if entrypoint is None:
            raise RuntimeError("Internal error: entrypoint is missing.")

        command = [
            "pyinstaller",
            "--noconfirm",
            "--clean",
            "--name",
            APP_NAME,
        ]

        if onefile:
            command.append("--onefile")
        else:
            command.append("--onedir")

        if windowed:
            command.append("--windowed")

        if icon:
            icon_path = project_root / icon
            if icon_path.exists():
                command.extend(["--icon", str(icon_path)])
            else:
                print_warn(f"Icon not found, ignoring: {icon_path}")

        command.append(str(entrypoint.relative_to(project_root)))

    run_command(command, cwd=project_root)

    dist_dir = project_root / "dist"

    onefile_exe = dist_dir / f"{APP_NAME}.exe"
    onedir_dir = dist_dir / APP_NAME

    if onefile_exe.exists():
        return onefile_exe

    if onedir_dir.exists():
        return onedir_dir

    # Fallback: find plausible output
    possible_outputs = list(dist_dir.glob(f"{APP_NAME}*"))
    if possible_outputs:
        return possible_outputs[0]

    raise FileNotFoundError("PyInstaller finished, but no dist output was found. Wunderbar nutzlos.")


def build_updater_with_pyinstaller(project_root: Path) -> Path | None:
    updater_spec = project_root / f"{UPDATER_NAME}.spec"
    updater_script = project_root / "scripts" / "portable_updater.py"

    if not updater_spec.exists() and not updater_script.exists():
        print_warn("No updater spec/script found. Release will not include the portable updater.")
        return None

    print_step("Building portable updater")

    if updater_spec.exists():
        command = [
            "pyinstaller",
            "--noconfirm",
            "--clean",
            str(updater_spec.relative_to(project_root)),
        ]
    else:
        command = [
            "pyinstaller",
            "--noconfirm",
            "--clean",
            "--onefile",
            "--windowed",
            "--name",
            UPDATER_NAME,
            str(updater_script.relative_to(project_root)),
        ]

    run_command(command, cwd=project_root)

    updater_exe = project_root / "dist" / f"{UPDATER_NAME}.exe"
    if updater_exe.exists():
        print_info(f"Updater output: {updater_exe}")
        return updater_exe

    updater_dir_exe = project_root / "dist" / UPDATER_NAME / f"{UPDATER_NAME}.exe"
    if updater_dir_exe.exists():
        print_info(f"Updater output: {updater_dir_exe}")
        return updater_dir_exe

    raise FileNotFoundError("PyInstaller finished, but no updater executable was found.")


def include_updater_in_build(build_output: Path, updater_exe: Path | None) -> None:
    if updater_exe is None:
        return

    if build_output.is_dir():
        target = build_output / updater_exe.name
    else:
        target = build_output.parent / updater_exe.name

    if updater_exe.resolve() == target.resolve():
        return

    shutil.copy2(updater_exe, target)
    print_info(f"Included updater in release payload: {target}")


def zip_directory(source_dir: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zipf:
        for file_path in source_dir.rglob("*"):
            if file_path.is_file():
                arcname = file_path.relative_to(source_dir.parent)
                zipf.write(file_path, arcname)


def zip_file(source_file: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zipf:
        zipf.write(source_file, source_file.name)


def create_release_zip(project_root: Path, build_output: Path, version: str) -> Path:
    print_step("Creating release ZIP")

    release_dir = project_root / "release"
    release_dir.mkdir(exist_ok=True)

    zip_path = release_dir / f"{APP_NAME}_{version}_win64.zip"

    if zip_path.exists():
        zip_path.unlink()

    if build_output.is_dir():
        zip_directory(build_output, zip_path)
    else:
        zip_file(build_output, zip_path)

    size_mb = zip_path.stat().st_size / (1024 * 1024)
    print_info(f"Created: {zip_path}")
    print_info(f"Size: {size_mb:.2f} MiB")

    if size_mb > 100:
        print_warn(
            "ZIP is larger than 100 MiB. Do NOT commit it to Git. "
            "Upload it as a GitHub Release asset. Ja, genau deswegen existiert dieses Script."
        )

    return zip_path


def get_current_branch(project_root: Path) -> str | None:
    completed = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=str(project_root),
        text=True,
        capture_output=True,
    )

    if completed.returncode != 0:
        return None

    branch = completed.stdout.strip()
    return branch or None


def create_git_tag(project_root: Path, version: str, allow_existing_tag: bool) -> str:
    tag = f"v{version}"

    completed = subprocess.run(
        ["git", "tag", "--list", tag],
        cwd=str(project_root),
        text=True,
        capture_output=True,
    )

    if completed.stdout.strip() == tag:
        if allow_existing_tag:
            print_warn(f"Tag already exists: {tag}")
            return tag
        raise RuntimeError(f"Git tag already exists: {tag}")

    run_command(["git", "tag", "-a", tag, "-m", f"Release {tag}"], cwd=project_root)
    print_info(f"Created Git tag: {tag}")

    return tag


def push_git(project_root: Path, tag: str, push_branch: bool) -> None:
    print_step("Pushing Git changes/tags")

    branch = get_current_branch(project_root)

    if push_branch and branch:
        run_command(["git", "push", "origin", branch], cwd=project_root)

    run_command(["git", "push", "origin", tag], cwd=project_root)


def create_github_release(
    project_root: Path,
    version: str,
    zip_path: Path,
    release_title: str,
    notes_file: str | None,
    draft: bool,
    prerelease: bool,
) -> None:
    if not command_exists("gh"):
        raise RuntimeError(
            "GitHub CLI `gh` was not found. Install it first or run without --publish."
        )

    print_step("Creating GitHub release")

    tag = f"v{version}"

    existing = subprocess.run(
        ["gh", "release", "view", tag],
        cwd=str(project_root),
        text=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    if existing.returncode == 0:
        print_warn(f"GitHub release already exists: {tag}")
        print_info("Uploading asset with --clobber.")
        run_command(
            [
                "gh",
                "release",
                "upload",
                tag,
                str(zip_path),
                "--clobber",
            ],
            cwd=project_root,
        )
        return

    command = [
        "gh",
        "release",
        "create",
        tag,
        str(zip_path),
        "--title",
        f"{release_title} {version}",
    ]

    if notes_file:
        notes_path = project_root / notes_file
        if notes_path.exists():
            command.extend(["--notes-file", str(notes_path)])
        else:
            print_warn(f"Notes file not found, using generated notes: {notes_path}")
            command.extend(["--notes", f"Release {version}"])
    else:
        command.extend(["--notes", f"Release {version}"])

    if draft:
        command.append("--draft")

    if prerelease:
        command.append("--prerelease")

    run_command(command, cwd=project_root)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build and optionally publish a Danbooru Download Manager release."
    )

    parser.add_argument(
        "--version",
        default=DEFAULT_VERSION,
        help=f"Release version. Default: {DEFAULT_VERSION}",
    )

    parser.add_argument(
        "--entrypoint",
        default=None,
        help="Python entrypoint if no .spec file is used, e.g. main.py",
    )

    parser.add_argument(
        "--spec",
        default=None,
        help="PyInstaller spec file, e.g. DanbooruManager.spec",
    )

    parser.add_argument(
        "--icon",
        default=None,
        help="Optional icon path for PyInstaller, e.g. assets/app.ico",
    )

    parser.add_argument(
        "--onefile",
        action="store_true",
        help="Build a single EXE instead of an application folder.",
    )

    parser.add_argument(
        "--console",
        action="store_true",
        help="Build with console window enabled.",
    )

    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="Do not delete build/dist before building.",
    )

    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Allow building with uncommitted Git changes.",
    )

    parser.add_argument(
        "--tag",
        action="store_true",
        help="Create a local Git tag vVERSION.",
    )

    parser.add_argument(
        "--allow-existing-tag",
        action="store_true",
        help="Do not fail if tag already exists.",
    )

    parser.add_argument(
        "--push",
        action="store_true",
        help="Push current branch and tag to origin.",
    )

    parser.add_argument(
        "--publish",
        action="store_true",
        help="Create or update GitHub release using gh CLI.",
    )

    parser.add_argument(
        "--draft",
        action="store_true",
        help="Create GitHub release as draft.",
    )

    parser.add_argument(
        "--prerelease",
        action="store_true",
        help="Mark GitHub release as prerelease.",
    )

    parser.add_argument(
        "--release-title",
        default=DEFAULT_RELEASE_NAME,
        help="GitHub release title prefix.",
    )

    parser.add_argument(
        "--notes-file",
        default="docs/CHANGELOG.md",
        help="Release notes file for GitHub release.",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_root = find_project_root()

    print_step("Release build started")
    print_info(f"Project root: {project_root}")
    print_info(f"Version: {args.version}")

    try:
        ensure_gitignore(project_root)
        check_git_status(project_root, allow_dirty=args.allow_dirty)

        if not args.no_clean:
            print_step("Cleaning build folders")
            remove_paths(
                [
                    project_root / "build",
                    project_root / "dist",
                ]
            )

        spec_file = find_spec_file(project_root, args.spec)

        if spec_file:
            print_info(f"Using PyInstaller spec file: {spec_file.relative_to(project_root)}")
            entrypoint = None
        else:
            entrypoint = find_entrypoint(project_root, args.entrypoint)
            print_info(f"Using entrypoint: {entrypoint.relative_to(project_root)}")

        build_output = build_with_pyinstaller(
            project_root=project_root,
            version=args.version,
            spec_file=spec_file,
            entrypoint=entrypoint,
            onefile=args.onefile,
            windowed=not args.console,
            icon=args.icon,
        )

        print_info(f"Build output: {build_output}")

        updater_output = build_updater_with_pyinstaller(project_root)
        include_updater_in_build(build_output, updater_output)

        zip_path = create_release_zip(project_root, build_output, args.version)

        tag = None
        if args.tag or args.push or args.publish:
            tag = create_git_tag(
                project_root,
                args.version,
                allow_existing_tag=args.allow_existing_tag,
            )

        if args.push:
            if tag is None:
                tag = f"v{args.version}"
            push_git(project_root, tag=tag, push_branch=True)

        if args.publish:
            create_github_release(
                project_root=project_root,
                version=args.version,
                zip_path=zip_path,
                release_title=args.release_title,
                notes_file=args.notes_file,
                draft=args.draft,
                prerelease=args.prerelease,
            )

        print_step("Release build finished")
        print_info(f"Release ZIP: {zip_path}")
        return 0

    except Exception as exc:
        print_error(str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

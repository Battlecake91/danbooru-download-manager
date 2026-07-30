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
- optionally build the portable updater
- package the dist output into release/*.zip
- optionally create/upload a GitHub release via gh CLI

Requirements:
- Python 3.10+
- PyInstaller installed in the active environment
- optional: GitHub CLI `gh` for publishing
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Iterable


APP_NAME = "DanbooruManager"
UPDATER_NAME = "DanbooruManagerUpdater"
DEFAULT_VERSION = "1.3.149"
DEFAULT_RELEASE_NAME = "Danbooru Download Manager"
DEFAULT_ENTRYPOINT_CANDIDATES = [
    "main.py",
    "app.py",
    "danbooru_manager.py",
    "src/main.py",
    "src/danbooru_manager/main.py",
]
DEFAULT_UPDATER_ENTRYPOINT_CANDIDATES = [
    "scripts/portable_updater.py",
    "portable_updater.py",
]
PYINSTALLER_HIDDEN_IMPORTS = [
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "PySide6.QtNetwork",
]
PYINSTALLER_EXCLUDES = [
    "pytest",
    "unittest",
    "tkinter",
    "PySide6.Qt3DAnimation",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DExtras",
    "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic",
    "PySide6.Qt3DRender",
    "PySide6.QtBluetooth",
    "PySide6.QtCharts",
    "PySide6.QtConcurrent",
    "PySide6.QtDataVisualization",
    "PySide6.QtDesigner",
    "PySide6.QtGraphs",
    "PySide6.QtGraphsWidgets",
    "PySide6.QtHelp",
    "PySide6.QtHttpServer",
    "PySide6.QtLocation",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtNetworkAuth",
    "PySide6.QtNfc",
    "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtPositioning",
    "PySide6.QtPrintSupport",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuick3D",
    "PySide6.QtQuickControls2",
    "PySide6.QtRemoteObjects",
    "PySide6.QtSvg",
    "PySide6.QtSvgWidgets",
    "PySide6.QtTest",
    "PySide6.QtTextToSpeech",
    "PySide6.QtUiTools",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebEngineWidgets",
    "PySide6.scripts",
    "PySide6.support",
]


def platform_release_suffix(platform: str | None = None) -> str:
    value = (platform or sys.platform).lower()
    machine = "x86_64"
    try:
        import platform as platform_module

        machine = platform_module.machine().lower() or machine
    except Exception:
        pass

    if value.startswith("win"):
        return "win64" if machine in {"amd64", "x86_64"} else "win32"
    if value.startswith("linux"):
        return "linux_x86_64" if machine in {"amd64", "x86_64"} else f"linux_{machine}"
    if value == "darwin":
        return "macos_arm64" if machine in {"arm64", "aarch64"} else "macos_x86_64"
    return value.replace(" ", "_")


def is_windows_platform(platform: str | None = None) -> bool:
    return (platform or sys.platform).lower().startswith("win")


def executable_name(base_name: str, platform: str | None = None) -> str:
    if is_windows_platform(platform):
        return f"{base_name}.exe"
    return base_name


def pyinstaller_data_separator(platform: str | None = None) -> str:
    return ";" if is_windows_platform(platform) else ":"


def pyinstaller_data_args(project_root: Path, platform: str | None = None) -> list[str]:
    separator = pyinstaller_data_separator(platform)
    data_pairs: list[tuple[Path, str]] = []
    locales_dir = project_root / "app" / "i18n" / "locales"
    if locales_dir.exists():
        data_pairs.append((locales_dir, "app/i18n/locales"))

    for asset_dir in (project_root / "assets", project_root / "app" / "assets"):
        if asset_dir.exists():
            data_pairs.append((asset_dir, str(asset_dir.relative_to(project_root)).replace("\\", "/")))

    args: list[str] = []
    for source, target in data_pairs:
        args.extend(["--add-data", f"{source}{separator}{target}"])
    return args


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


def pyinstaller_available() -> bool:
    completed = subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--version"],
        text=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return completed.returncode == 0


def pyinstaller_command(*args: str) -> list[str]:
    return [sys.executable, "-m", "PyInstaller", *args]


def find_project_root() -> Path:
    current = Path(__file__).resolve()

    for parent in [current.parent, *current.parents]:
        if (parent / ".git").exists():
            return parent

    return Path.cwd().resolve()


def read_project_version(project_root: Path) -> str:
    """Best-effort version detection used when --version is omitted."""
    candidates = [
        project_root / "app" / "version.py",
        project_root / "version.py",
    ]

    patterns = [
        re.compile(r'APP_VERSION\s*=\s*["\']([^"\']+)["\']'),
        re.compile(r'__version__\s*=\s*["\']([^"\']+)["\']'),
        re.compile(r'VERSION\s*=\s*["\']([^"\']+)["\']'),
    ]

    for candidate in candidates:
        if not candidate.exists():
            continue

        text = candidate.read_text(encoding="utf-8", errors="replace")
        for pattern in patterns:
            match = pattern.search(text)
            if match:
                return match.group(1)

    return DEFAULT_VERSION


def ensure_gitignore(project_root: Path) -> None:
    gitignore_path = project_root / ".gitignore"

    required_entries = [
        "release/",
        "dist/",
        "build/",
        "*.zip",
        "*.exe",
        "*.msi",
        "*.spec.build/",
        "danbooru_manager_data/",
        "*.db",
        "*.db-wal",
        "*.db-shm",
        "*.log",
    ]

    existing = gitignore_path.read_text(encoding="utf-8") if gitignore_path.exists() else ""

    missing_entries: list[str] = []

    for entry in required_entries:
        if entry not in existing:
            missing_entries.append(entry)

    if missing_entries:
        with gitignore_path.open("a", encoding="utf-8", newline="\n") as f:
            if existing and not existing.endswith("\n"):
                f.write("\n")
            f.write("\n# Release/build artifacts\n")
            for entry in missing_entries:
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

    spec_files = [
        spec
        for spec in sorted(project_root.glob("*.spec"))
        if spec.name != f"{UPDATER_NAME}.spec"
    ]

    if len(spec_files) == 1:
        return spec_files[0]

    return None


def find_updater_spec_file(project_root: Path, explicit_spec: str | None) -> Path | None:
    if explicit_spec:
        spec_path = project_root / explicit_spec
        if not spec_path.exists():
            raise FileNotFoundError(f"Updater spec file not found: {spec_path}")
        return spec_path

    candidate = project_root / f"{UPDATER_NAME}.spec"
    if candidate.exists():
        return candidate

    return None


def find_entrypoint(
    project_root: Path,
    explicit_entrypoint: str | None,
    candidates: list[str],
    label: str,
) -> Path:
    if explicit_entrypoint:
        entrypoint = project_root / explicit_entrypoint
        if not entrypoint.exists():
            raise FileNotFoundError(f"{label} entrypoint not found: {entrypoint}")
        return entrypoint

    for candidate in candidates:
        path = project_root / candidate
        if path.exists():
            return path

    raise FileNotFoundError(
        f"Could not auto-detect {label} entrypoint. "
        f"Use --entrypoint path/to/main.py or provide a .spec file."
    )


def find_pyinstaller_output(project_root: Path, expected_name: str) -> Path:
    """Find the exact PyInstaller output for a build target.

    Prefer exact EXE and exact onedir outputs. Avoid loose glob matches first,
    because dist/DanbooruManager* could otherwise accidentally match the main
    application when we are looking for DanbooruManagerUpdater. Git, PyInstaller
    and Windows already have enough ways to waste a human afternoon.
    """
    dist_dir = project_root / "dist"

    if sys.platform.startswith("win"):
        exact_exe = dist_dir / f"{expected_name}.exe"
    else:
        exact_exe = dist_dir / expected_name

    exact_onedir = dist_dir / expected_name

    if exact_exe.exists() and exact_exe.is_file():
        return exact_exe

    if exact_onedir.exists() and exact_onedir.is_dir():
        return exact_onedir

    possible_files = sorted(
        item for item in dist_dir.glob(f"{expected_name}*")
        if item.is_file()
    )
    if possible_files:
        return possible_files[0]

    possible_dirs = sorted(
        item for item in dist_dir.glob(f"{expected_name}*")
        if item.is_dir()
    )
    if possible_dirs:
        return possible_dirs[0]

    raise FileNotFoundError(
        f"PyInstaller finished, but no dist output was found for {expected_name}."
    )

def build_with_pyinstaller(
    project_root: Path,
    expected_name: str,
    spec_file: Path | None,
    entrypoint: Path | None,
    onefile: bool,
    windowed: bool,
    icon: str | None,
) -> Path:
    if not pyinstaller_available():
        raise RuntimeError(
            "PyInstaller was not found in the active Python environment. "
            f"Install it with: {sys.executable} -m pip install pyinstaller"
        )

    print_step(f"Building {expected_name} with PyInstaller")

    if spec_file:
        command = pyinstaller_command(
            "--noconfirm",
            "--clean",
            str(spec_file.relative_to(project_root)),
        )
    else:
        if entrypoint is None:
            raise RuntimeError("Internal error: entrypoint is missing.")

        spec_dir = project_root / "build" / "pyinstaller_specs"
        spec_dir.mkdir(parents=True, exist_ok=True)
        command = pyinstaller_command(
            "--noconfirm",
            "--clean",
            "--specpath",
            str(spec_dir),
            "--name",
            expected_name,
        )

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

        command.extend(pyinstaller_data_args(project_root))
        for hidden_import in PYINSTALLER_HIDDEN_IMPORTS:
            command.extend(["--hidden-import", hidden_import])
        for excluded_module in PYINSTALLER_EXCLUDES:
            command.extend(["--exclude-module", excluded_module])
        command.append(str(entrypoint.relative_to(project_root)))

    run_command(command, cwd=project_root)

    return find_pyinstaller_output(project_root, expected_name)


def build_main_application(
    project_root: Path,
    spec_file: Path | None,
    entrypoint: Path | None,
    onefile: bool,
    windowed: bool,
    icon: str | None,
) -> Path:
    return build_with_pyinstaller(
        project_root=project_root,
        expected_name=APP_NAME,
        spec_file=spec_file,
        entrypoint=entrypoint,
        onefile=onefile,
        windowed=windowed,
        icon=icon,
    )


def build_updater(
    project_root: Path,
    updater_spec_file: Path | None,
    updater_entrypoint: Path | None,
    icon: str | None,
) -> Path:
    # The updater should be a small console tool. It is started after the GUI exits,
    # so a short console window is acceptable and very useful when update replacement fails.
    return build_with_pyinstaller(
        project_root=project_root,
        expected_name=UPDATER_NAME,
        spec_file=updater_spec_file,
        entrypoint=updater_entrypoint,
        onefile=True,
        windowed=False,
        icon=icon,
    )


def copy_path_into_directory(source: Path, target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / source.name

    if target.exists():
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()

    if source.is_dir():
        shutil.copytree(source, target)
    else:
        shutil.copy2(source, target)

    print_info(f"Added to release payload: {source.name}")


def prepare_release_payload(
    project_root: Path,
    build_output: Path,
    updater_output: Path | None,
    require_updater: bool = True,
) -> Path:
    print_step("Preparing release payload")

    payload_root = project_root / "build" / "release_payload"
    payload_app_dir = payload_root / APP_NAME

    if payload_root.exists():
        shutil.rmtree(payload_root)

    payload_app_dir.mkdir(parents=True, exist_ok=True)

    if build_output.is_dir():
        for item in build_output.iterdir():
            copy_path_into_directory(item, payload_app_dir)
    else:
        copy_path_into_directory(build_output, payload_app_dir)

    if updater_output is not None:
        copy_path_into_directory(updater_output, payload_app_dir)
    else:
        if require_updater:
            raise RuntimeError(
                "Updater was not included in the release payload. "
                "Use --no-updater only if you intentionally want a release without updates."
            )
        print_warn("Updater was not included in the release payload because --no-updater was used.")

    if require_updater:
        expected_updater_names = [
            executable_name(UPDATER_NAME),
            executable_name("updater"),
        ]
        if not any((payload_app_dir / name).exists() for name in expected_updater_names):
            raise FileNotFoundError(
                "Updater executable is missing from release payload. "
                f"Expected one of: {', '.join(expected_updater_names)}"
            )

    return payload_app_dir


def zip_directory(source_dir: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zipf:
        for file_path in source_dir.rglob("*"):
            if file_path.is_file():
                arcname = file_path.relative_to(source_dir.parent)
                zipf.write(file_path, arcname)


def create_release_zip(
    project_root: Path,
    payload_dir: Path,
    version: str,
    *,
    onefile: bool = False,
    platform: str | None = None,
) -> Path:
    print_step("Creating release ZIP")

    release_dir = project_root / "release"
    release_dir.mkdir(exist_ok=True)

    bundle_suffix = "onefile" if onefile else "portable"
    zip_path = release_dir / f"{APP_NAME}_{version}_{platform_release_suffix(platform)}_{bundle_suffix}.zip"

    if zip_path.exists():
        zip_path.unlink()

    zip_directory(payload_dir, zip_path)

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


def resolve_release_notes_file(
    project_root: Path,
    version: str,
    notes_file: str | None,
) -> Path:
    """Resolve and validate the release notes file used for publishing."""
    if notes_file:
        notes_path = Path(notes_file)
        if not notes_path.is_absolute():
            notes_path = project_root / notes_path
    else:
        notes_path = project_root / "docs" / f"RELEASE_NOTES_{version}.md"

    if not notes_path.is_file():
        try:
            display_path = notes_path.relative_to(project_root)
        except ValueError:
            display_path = notes_path
        raise FileNotFoundError(
            f"Release notes file not found: {display_path}. "
            f"Create docs/RELEASE_NOTES_{version}.md or pass --notes-file explicitly."
        )

    return notes_path


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

    notes_path = resolve_release_notes_file(
        project_root=project_root,
        version=version,
        notes_file=notes_file,
    )
    print_info(f"Using release notes: {notes_path.relative_to(project_root)}")
    command.extend(["--notes-file", str(notes_path)])

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
        default=None,
        help=f"Release version. Default: detected from app/version.py or {DEFAULT_VERSION}",
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
        "--updater-entrypoint",
        default=None,
        help="Portable updater entrypoint if no updater .spec file is used, e.g. scripts/portable_updater.py",
    )

    parser.add_argument(
        "--updater-spec",
        default=None,
        help="Portable updater PyInstaller spec file, e.g. DanbooruManagerUpdater.spec",
    )

    parser.add_argument(
        "--no-updater",
        action="store_true",
        help="Do not build/include DanbooruManagerUpdater in the release ZIP.",
    )

    parser.add_argument(
        "--icon",
        default=None,
        help="Optional icon path for PyInstaller, e.g. assets/app.ico",
    )

    parser.add_argument(
        "--onefile",
        action="store_true",
        help="Build the main application as a single EXE instead of an application folder.",
    )

    parser.add_argument(
        "--console",
        action="store_true",
        help="Build the main application with console window enabled.",
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
        default=None,
        help=(
            "Release notes file for GitHub release. "
            "Default: docs/RELEASE_NOTES_<detected version>.md"
        ),
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_root = find_project_root()
    version = args.version or read_project_version(project_root)

    print_step("Release build started")
    print_info(f"Project root: {project_root}")
    print_info(f"Version: {version}")

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

        if args.onefile and args.spec is None:
            spec_file = None
            print_info("Onefile build requested; using PyInstaller CLI options instead of the default onedir spec.")
        elif not is_windows_platform() and args.spec is None:
            spec_file = None
            print_info("Non-Windows build detected; using PyInstaller CLI options instead of the Windows-oriented spec.")
        else:
            spec_file = find_spec_file(project_root, args.spec)

        if spec_file:
            print_info(f"Using PyInstaller spec file: {spec_file.relative_to(project_root)}")
            entrypoint = None
        else:
            entrypoint = find_entrypoint(
                project_root=project_root,
                explicit_entrypoint=args.entrypoint,
                candidates=DEFAULT_ENTRYPOINT_CANDIDATES,
                label="main application",
            )
            print_info(f"Using entrypoint: {entrypoint.relative_to(project_root)}")

        build_output = build_main_application(
            project_root=project_root,
            spec_file=spec_file,
            entrypoint=entrypoint,
            onefile=args.onefile,
            windowed=not args.console,
            icon=args.icon,
        )

        print_info(f"Main build output: {build_output}")

        updater_output: Path | None = None

        if args.no_updater:
            print_warn("Updater build disabled by --no-updater.")
        else:
            updater_spec_file = find_updater_spec_file(project_root, args.updater_spec)

            if updater_spec_file:
                print_info(f"Using updater spec file: {updater_spec_file.relative_to(project_root)}")
                updater_entrypoint = None
            else:
                updater_entrypoint = find_entrypoint(
                    project_root=project_root,
                    explicit_entrypoint=args.updater_entrypoint,
                    candidates=DEFAULT_UPDATER_ENTRYPOINT_CANDIDATES,
                    label="portable updater",
                )
                print_info(f"Using updater entrypoint: {updater_entrypoint.relative_to(project_root)}")

            updater_output = build_updater(
                project_root=project_root,
                updater_spec_file=updater_spec_file,
                updater_entrypoint=updater_entrypoint,
                icon=args.icon,
            )
            if not updater_output.exists():
                raise FileNotFoundError(f"Updater build output does not exist: {updater_output}")
            print_info(f"Updater build output: {updater_output}")

        payload_dir = prepare_release_payload(
            project_root=project_root,
            build_output=build_output,
            updater_output=updater_output,
            require_updater=not args.no_updater,
        )

        zip_path = create_release_zip(
            project_root,
            payload_dir,
            version,
            onefile=args.onefile,
        )

        tag = None
        if args.tag or args.push or args.publish:
            tag = create_git_tag(
                project_root,
                version,
                allow_existing_tag=args.allow_existing_tag,
            )

        if args.push:
            if tag is None:
                tag = f"v{version}"
            push_git(project_root, tag=tag, push_branch=True)

        if args.publish:
            create_github_release(
                project_root=project_root,
                version=version,
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

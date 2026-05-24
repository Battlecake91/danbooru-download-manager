# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
from PyInstaller.utils.hooks import collect_all

project_dir = Path.cwd()

pyside6_datas, pyside6_binaries, pyside6_hiddenimports = collect_all("PySide6")

datas = [
    (str(project_dir / "app" / "i18n" / "locales"), "app/i18n/locales"),
]
for asset_dir in (project_dir / "assets", project_dir / "app" / "assets"):
    if asset_dir.exists():
        datas.append((str(asset_dir), str(asset_dir.relative_to(project_dir)).replace("\\", "/")))

def first_existing_icon() -> str | None:
    for candidate in (
        project_dir / "assets" / "app_icon.ico",
        project_dir / "app" / "assets" / "app_icon.ico",
    ):
        if candidate.exists():
            return str(candidate)
    return None


a = Analysis(
    ["main.py"],
    pathex=[str(project_dir)],
    binaries=[*pyside6_binaries],
    datas=[*datas, *pyside6_datas],
    hiddenimports=[*pyside6_hiddenimports],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "tkinter"],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="DanbooruManager",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=first_existing_icon(),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="DanbooruManager",
)

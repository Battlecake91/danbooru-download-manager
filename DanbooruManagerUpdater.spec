# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

project_dir = Path.cwd()

a = Analysis(
    ["scripts/portable_updater.py"],
    pathex=[str(project_dir)],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "pytest",
        "unittest",
        "tkinter",
        "PySide6",
        "PyQt5",
        "PyQt6",
        "numpy",
        "PIL",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

# This is a real one-file build.
# Do NOT use exclude_binaries=True here without a matching COLLECT block.
# That setting belongs to one-folder builds and can make the updater disappear
# from the release pipeline in wonderfully annoying ways.
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="DanbooruManagerUpdater",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

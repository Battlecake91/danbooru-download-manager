# Patch 1.3.134 - GUI default for executable builds

## Why

A PyInstaller-built executable is usually launched by double-clicking it. In that case no command-line arguments are passed, so requiring `--gui` made the executable appear to do nothing.

## Changed

- `main.py` now starts the GUI by default when no CLI action is requested.
- `--gui` remains available for explicit GUI startup and for compatibility.
- CLI actions still work without starting Qt automatically:
  - `--init-db`
  - `--import-history`
  - `--fetch`
- Combining a CLI action with `--gui` still runs the action first and then opens the GUI.
- argparse help texts were moved to English.

## PyInstaller effect

`DanbooruManager.exe` can now be launched without arguments and opens the GUI directly.

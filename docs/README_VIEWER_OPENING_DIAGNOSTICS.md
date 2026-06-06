# Viewer opening diagnostics

Temporary diagnostics for the viewer hang that occurs with an older production database.

## Output

The viewer writes diagnostic information to:

```text
<work_dir>/logs/viewer_diagnostics.log
```

The log records:

- start and completion of `load_current_post()`
- the current post ID and selected legacy database values
- entry and exit of the relevant database, category, tag, image and UI stages
- reentrant viewer loads
- a Python thread dump if loading is still active after five seconds

Console lines use the prefix:

```text
[VIEWER-DIAG]
```

## Test

1. Start the application with the affected database.
2. Open the Previewer.
3. Open a post that causes the Viewer to hang.
4. Leave the application running for at least five seconds after the hang begins.
5. Collect `logs/viewer_diagnostics.log` and the console output beginning with `[VIEWER-DIAG]`.

This patch intentionally does not change database data, migrations or viewer behavior beyond diagnostic logging.

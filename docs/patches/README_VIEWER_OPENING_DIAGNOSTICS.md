# Viewer opening diagnostics

The viewer opening path is temporarily instrumented to locate a GUI-thread hang.

Current finding: `load_current_post()` reaches `update_category_controls()` and does not return.

The category update path now logs each potentially blocking step:

- category suggestion
- assigned category lookup
- category influence calculation
- category list loading
- combo box population and selection
- label update
- final path preview update

Relevant log file:

`<work_dir>/logs/viewer_diagnostics.log`

Relevant prefix:

`[VIEWER-DIAG]`

## Final-path preview tracing

The diagnostic branch now traces source-path lookup, filename generation, tag metadata lookup, output-directory resolution, and every relevant `unique_path()` probe. This is temporary instrumentation for locating the viewer-opening hang.

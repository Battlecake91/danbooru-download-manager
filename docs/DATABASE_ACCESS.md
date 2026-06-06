# Database access coordination

The application uses SQLite in WAL mode. WAL permits concurrent readers, but SQLite still allows only one writer at a time. The application therefore uses a process-wide FIFO write coordinator for every database file.

## Behaviour

- Read-only SQL is executed immediately on each thread-local database connection.
- The first mutating statement of a transaction requests the central write slot.
- Additional writers wait in FIFO order.
- The connection keeps its slot until `commit()`, `rollback()` or `close()`.
- Previewer reads remain available while Fetch, Importer or Configuration writes are running.
- Schema creation, maintenance checkpoints and `VACUUM` use the same write gate.

This means a settings save requested during Fetch is queued behind the active Fetch transaction instead of racing it at SQLite level. Once the current transaction commits, the settings write proceeds automatically.

## Connection model

Each worker still owns its own SQLite connection. Connections must not be shared across Qt threads. Coordination occurs above SQLite and is keyed by the resolved database path, so all `Database` instances inside the application participate automatically.

## External access

The coordinator only covers this application process. SQLite `busy_timeout` and retry handling remain enabled for external tools, antivirus scanners and other processes that may access the database file.

## Transaction guidance

Keep transactions short. Do not perform network requests or image processing between a mutating statement and its commit. A queued settings change should wait for a database transaction, not for an entire download batch.

## GUI write requests

GUI actions must not wait synchronously for the write coordinator. Configuration saves are submitted through a dedicated worker thread with its own SQLite connection. The worker may wait in the FIFO writer queue while Fetch is committing posts, but the Qt GUI thread remains free to process progress signals and user input. Runtime configuration is updated only after the queued transaction succeeds.

## GUI-thread write protection

Configuration changes can trigger Preview refreshes. While a Fetch is active,
those refreshes are deferred until the Fetch finishes. A synchronous mutating SQL
statement from the Python main thread is also rejected when another writer owns
the write queue. The rejection is logged with a Python caller stack in
`logs/database_trace.log` so remaining GUI write paths can be identified without
stalling the active Fetch.

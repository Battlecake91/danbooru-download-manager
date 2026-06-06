# Database Access Coordination

Danbooru Download Manager `1.3.189` uses SQLite in WAL mode. WAL allows concurrent readers, but SQLite still permits only one writer at a time.

The application therefore uses a process-wide FIFO write coordinator for each resolved database file.

---

## Connection model

- The main GUI and each background worker own separate SQLite connections.
- Connections are never shared across Qt threads.
- Read-only SQL executes directly on the owning connection.
- Mutating transactions enter the shared FIFO coordinator.
- The write slot is held until commit, rollback or connection close.

This lets Previewer reads continue while Fetch, Importer or Configuration writes are running.

---

## Coordinated writers

The coordinator covers application-owned writes from:

- Fetch,
- Importer,
- Configuration saves,
- Viewer and Tag actions,
- asynchronous UI-setting persistence,
- schema and maintenance operations.

Configuration saves run in a dedicated worker thread with their own connection. If Fetch is currently committing a post, the setting waits in the queue without blocking Qt's event loop.

---

## Transaction rules

Transactions must remain short:

- do not perform HTTP requests while holding the write slot,
- do not process images between a mutating statement and commit,
- always roll back after failed writes,
- always release the slot when a connection closes.

Failed `execute()`, `executemany()` and `executescript()` operations trigger rollback and gate cleanup.

Standalone GUI writes are committed immediately unless an explicit transaction was opened. This prevents a forgotten GUI commit from blocking later Fetch runs.

---

## Read-only Previewer behavior

The Previewer is intended to use read-only database operations for loading cards, tags, scores and filters.

Tag identity calculation is explicitly read-only. An earlier implementation wrote an unused identity cache through `executemany()` while opening the Previewer, leaving the write gate occupied and blocking the next Fetch. That side effect has been removed.

---

## Worker lifecycle

Fetch and Import workers open normal worker connections but do not run schema creation or migration. Schema initialization belongs to application startup.

A new Fetch cannot start until the previous worker has:

1. completed its result handling,
2. closed its database connection,
3. exited its Qt thread.

---

## External access

The coordinator only manages connections inside this application process. SQLite busy timeouts and retry behavior remain necessary for external tools, antivirus scanners or another program accessing the database file.

Avoid editing the live database with external tools during large imports or maintenance operations.

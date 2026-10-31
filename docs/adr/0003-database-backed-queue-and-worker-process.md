# ADR 0003: PostgreSQL-backed message queue and a separate worker process

- Status: accepted
- Date: 2026-10-31

## Context

Messages must be scheduled by date offsets, sent only inside a time window, throttled, retried, and
re-checked right before sending (BRD FR-04 to FR-08, AB-01 to AB-04). Sending must survive restarts
without losing or duplicating messages, and one failing message must not stop the rest (NFR-06).
Volume is at most a few thousand messages a day.

## Decision

- The queue is the `messages` table itself (`queued -> sending -> sent -> delivered -> read`, or
  `failed` / `cancelled`). It doubles as the send log (FR-07, BR-05).
- A separate process, `python -m app.cli run-worker`, runs an async loop every minute with two
  phases: **plan** (insert due messages; a unique key on invoice + rule makes this idempotent) and
  **send** (claim one message at a time, re-check, send through `WhatsAppProvider`, apply throttle,
  daily cap, retries and the circuit breaker).
- No new library: no APScheduler, Celery or Redis. Production runs it as a second PM2 process next to
  the API (`kampusping-worker`).

## Consequences

Good:

- State lives in PostgreSQL, so restarts are safe and the full history is queryable for the
  dashboard and reports.
- Few moving parts; every rule is plain, unit-testable Python driven by `FakeProvider`.

Costs and trade-offs:

- Claiming a message must be atomic (`UPDATE ... WHERE status = 'queued'` or `FOR UPDATE SKIP
  LOCKED` on PostgreSQL). On SQLite (tests only) the worker is single-process, so the simpler path
  is used.
- Running two worker processes at once is unsupported in the first release; the claim step prevents
  duplicate sends but throttling would be per process.
- Scheduling granularity is one minute, which is more than enough for daily reminders.

## Alternatives considered

- **APScheduler in the API process:** sending stops when the API restarts and duplicates appear when
  it scales to several workers. Rejected.
- **Celery + Redis:** sturdier at large scale, but adds two services for a few thousand messages a
  day. Rejected for now.

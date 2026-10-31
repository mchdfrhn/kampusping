# ADR 0002: Baileys WhatsApp gateway instead of the official Cloud API

- Status: accepted
- Date: 2026-10-31

## Context

The BRD (`docs/BRD-penagihan-uang-kuliah-whatsapp.md`, section 10, "Kanal WhatsApp") compares two
channels and **recommends option A**, the official WhatsApp Business Platform (Cloud API), because an
unofficial gateway (option B) "melanggar ketentuan WhatsApp, nomor berisiko diblokir permanen" and is
"tidak dianjurkan" for institutional bulk sending. NFR-04 also assumes approved message templates.

The team chose **Baileys** (unofficial WhatsApp Web library, Node.js) instead. This ADR records that
the choice deviates from the BRD recommendation and how the system limits the damage.

## Decision

- WhatsApp is reached through a separate **Node gateway service** (`kampusping-wa-gateway/`, own
  folder and git repo) that owns the Baileys session. It exposes a small HTTP API (send, status,
  pairing QR) protected by a shared secret and calls a webhook on the backend for delivery status
  and inbound messages.
- The backend depends only on a `WhatsAppProvider` interface with two implementations:
  `GatewayProvider` (HTTP to the gateway) and `FakeProvider` (development and tests). A
  `CloudApiProvider` can be added later without touching the queue, scheduler or UI.
- Safeguards that are part of the design, not optional:
  - use a dedicated number, not the main campus number;
  - random delay between messages (default 8-20 s) and a daily cap (default 200);
  - send window 08:00-17:00 WIB on working days (AB-04), one automatic message per student per
    day (AB-03);
  - opt-out keywords (`STOP`, `BERHENTI`, `UNSUBSCRIBE`) honoured immediately and a
    "Balas STOP untuk berhenti" footer on every message (NFR-03);
  - automatic pause when the session disconnects or after 5 consecutive failures, with a warning on
    the dashboard;
  - messages are re-checked (paid, opted out, exempt, phone valid) right before sending (FR-06).

## Consequences

Good:

- No Meta Business account, template approval or per-conversation fee is needed to start.
- The provider interface keeps a move to the official API a contained change.

Costs and risks:

- Baileys violates the WhatsApp terms of service. The number can be banned, possibly permanently,
  and Baileys can break whenever WhatsApp changes its protocol. The safeguards reduce the likelihood,
  they do not remove it. The BRD risk "Nomor WhatsApp terblokir karena spam" applies with higher
  probability than the BRD assumed.
- The session (credentials) is stored by the gateway and must be protected like a secret; it is not
  committed and lives outside the web root.
- A third long-running process (PM2 `kampusping-wa-gateway`) must be deployed and monitored.
- The real send path cannot be verified by automated tests; it needs a manual smoke test on a real
  phone before each release that touches the gateway.
- NFR-04 ("template pesan disetujui") does not apply as written, because no template approval exists
  on this channel.

## Gateway requirements

Binding for `kampusping-wa-gateway/` (recorded after the backend reviews; the gateway README has
the details):

1. **Durable dedupe by `client_ref`.** The worker retries a send after a lost answer or a crash.
   The gateway keeps `client_ref -> provider_message_id` in a file written atomically, retained
   for at least 14 days (`WA_DEDUPE_TTL_DAYS`, minimum 14). A repeated `client_ref` answers with
   the original id without sending again; concurrent requests with the same ref share one
   attempt; only successful sends are recorded. The record is written right after WhatsApp
   accepted the message and before the answer, so only a crash in that window can duplicate.
2. **Delayed and retried receipts.** The backend answers 202 for receipts of unknown message ids
   and drops them: it only knows an id after the worker committed the send, and it cannot ask the
   gateway to send a receipt again. So the gateway sends a `status` event no earlier than
   `WA_STATUS_DELAY_MS` (default 2 s) after the answer to the send, retries every webhook event on
   network errors and non-2xx answers with exponential backoff (default 5 retries: 1, 2, 4, 8,
   16 s) and keeps the receipts of one message in order (`read` never before `delivered`).
3. **Signature.** `X-Signature: sha256=<lowercase hex HMAC-SHA256>` over the exact body bytes
   sent, key `WA_WEBHOOK_SECRET`; the backend accepts lowercase hex only.

## Alternatives considered

- **Official Cloud API (BRD option A):** recommended by the BRD, stable and low ban risk, but needs a
  Meta Business account, approved templates and per-conversation cost. Kept as a future provider.
- **Baileys inside the Next.js server:** one fewer service, but the connection would restart on every
  deploy or reload and mixes a long-running worker with the UI process. Rejected.

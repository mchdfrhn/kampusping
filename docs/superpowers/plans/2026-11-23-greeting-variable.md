# Greeting Variable (`{{salam}}`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `{{salam}}` template variable that becomes "Selamat pagi/siang/sore/malam" according to the moment the message is actually sent.

**Architecture:** Planning and manual send leave `{{salam}}` untouched in `messages.body` (it is simply absent from the planning context, and `render_body` already leaves unknown keys alone). The sender fills it right before `provider.send`, from the step's injected `now` converted to `APP_TIMEZONE`, and stores the final text in `messages.body` together with the `sent` outcome.

**Tech Stack:** FastAPI backend (pytest, ruff, pyright), Next.js frontend (Vitest).

**Spec:** `docs/superpowers/specs/2026-11-23-greeting-variable-design.md`

## Global Constraints

- Texts exactly: `"Selamat pagi"`, `"Selamat siang"`, `"Selamat sore"`, `"Selamat malam"`.
- Boundaries on local (WIB) time: pagi `< 11:00`, siang `11:00–14:59`, sore `15:00–17:59`, malam `>= 18:00`.
- Preview sample value: `"Selamat pagi"`.
- Clock is injected; tests never read system time. Backend commands run with `DATABASE_ENGINE=sqlite` and a `DATABASE_URL` outside the repo.
- Work on branch `feat/greeting-variable` in `kampusping-backend` and `kampusping-frontend` (both branched from `master`).

## Review Focus

1. A message that is retried (failed attempt, back to `queued`) must still hold `{{salam}}` so the retry gets the greeting of its own send time: only the success write stores the filled body. Test in Task 2.
2. A message planned in the morning and sent in the afternoon gets "Selamat sore", not "Selamat pagi". Test in Task 2.
3. Bodies without `{{salam}}` are sent and stored byte-for-byte unchanged (existing sender tests cover this; keep them green).
4. Spaced placeholder `{{ salam }}` is filled like `{{salam}}` (same regex as other variables). Test in Task 1.
5. Length: the 4096 check in `send_rules.recheck` runs on the stored body; the greeting adds at most 4 characters and template bodies are capped at 2000, so no extra check is needed. No test.

---

### Task 1: Greeting rendering helpers (backend)

**Files:**
- Modify: `kampusping-backend/app/modules/templates/rendering.py`
- Test: `kampusping-backend/tests/test_templates_schedules.py`

**Interfaces:**
- Produces: `greeting_for(local: datetime) -> str` and `fill_greeting(body: str, local: datetime) -> str` in `app/modules/templates/rendering.py`; `"salam"` appended to `ALLOWED_VARIABLES`; `SAMPLE_CONTEXT["salam"] = "Selamat pagi"`. `build_context` does **not** get a `salam` key.

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.parametrize(
    ("hour", "minute", "expected"),
    [(0, 0, "Selamat pagi"), (10, 59, "Selamat pagi"), (11, 0, "Selamat siang"),
     (14, 59, "Selamat siang"), (15, 0, "Selamat sore"), (17, 59, "Selamat sore"),
     (18, 0, "Selamat malam"), (23, 59, "Selamat malam")],
)
def test_greeting_for_follows_local_hour(hour: int, minute: int, expected: str) -> None:
    assert greeting_for(datetime(2026, 11, 23, hour, minute)) == expected

def test_fill_greeting_replaces_every_salam_and_keeps_other_text() -> None:
    body = "{{salam}}, Budi. {{ salam }} lagi. {{nama}}"
    assert fill_greeting(body, datetime(2026, 11, 23, 15, 0)) == "Selamat sore, Budi. Selamat sore lagi. {{nama}}"

def test_build_message_body_leaves_salam_for_the_sender() -> None:
    # template body "{{salam}} {{nama}}" -> starts with "{{salam}} " and contains the student name

def test_salam_is_an_allowed_variable_with_a_morning_preview() -> None:
    assert "salam" in ALLOWED_VARIABLES
    assert render_body("{{salam}}", SAMPLE_CONTEXT) == "Selamat pagi"
```

- [ ] **Step 2: Run and see them fail** — `pytest tests/test_templates_schedules.py -k "greeting or salam" -v` → ImportError / assertion failures.
- [ ] **Step 3: Implement** — `greeting_for` compares `local.time()` with `time(11)`, `time(15)`, `time(18)`; `fill_greeting` uses a `\{\{\s*salam\s*\}\}` regex.
- [ ] **Step 4: Run** — same command → PASS; then `pytest tests/test_templates_schedules.py` → all pass.
- [ ] **Step 5: Commit** — `feat: add the salam template variable`

### Task 2: Fill the greeting at send time (backend)

**Files:**
- Modify: `kampusping-backend/app/modules/messages/sender.py` (`_deliver`, `_record_success`), `kampusping-backend/app/modules/messages/model.py` (docstring: body is rendered at planning except `{{salam}}`, filled at send), `kampusping-backend/docs/messaging.md` (body rendered at planning → note the greeting exception and the variable list)
- Test: `kampusping-backend/tests/test_sender.py`

**Interfaces:**
- Consumes: `fill_greeting(body, local)` from Task 1; `local_now(now, config.app_timezone)` from `app/shared/clock.py`.
- Produces: `_deliver` sends `fill_greeting(ready.body, local_now(now, ...))`; `_record_success` writes `body=<sent text>` in the same `record_outcome` call.

- [ ] **Step 1: Write the failing tests** (use the file's `at_wib(day, hour, minute)` and `add_message(body=...)` helpers)

```python
async def test_salam_is_filled_from_the_send_time_not_the_planning_time() -> None:
    # message queued with body "{{salam}}, Budi." ; clock at_wib(<working day>, 15, 30)
    # -> fake.sent[0].text == "Selamat sore, Budi." and stored body == "Selamat sore, Budi."

async def test_failed_attempt_keeps_the_salam_placeholder_for_the_retry() -> None:
    # provider raises a retryable error -> message back to queued, body still "{{salam}}, Budi."
```

- [ ] **Step 2: Run and see them fail** — `pytest tests/test_sender.py -k salam -v`.
- [ ] **Step 3: Implement** in `_deliver` / `_record_success` (pass the sent text through, e.g. a `text` argument to `_record_success`).
- [ ] **Step 4: Run** — `pytest tests/test_sender.py -v` → all pass; then the full gate `ruff check . && ruff format --check . && pyright && pytest`.
- [ ] **Step 5: Commit** — `feat: fill the salam greeting when the message is sent`

### Task 3: Offer `salam` in the template editor (frontend)

**Files:**
- Modify: `kampusping-frontend/src/modules/templates/constants.ts` (append `'salam'` to `TEMPLATE_VARIABLES`)
- Test: `kampusping-frontend/src/modules/templates/components/TemplateFormDialog.test.tsx` (its expected variable list gains `'salam'`)

- [ ] **Step 1:** Update the expected list in the test; run `npx vitest run src/modules/templates` → FAIL.
- [ ] **Step 2:** Add `'salam'` to `TEMPLATE_VARIABLES`; if the dialog shows a description per variable, describe it as "Selamat pagi/siang/sore sesuai jam kirim".
- [ ] **Step 3:** `npm run check` → all pass.
- [ ] **Step 4: Commit** — `feat: offer the salam variable in the template editor`

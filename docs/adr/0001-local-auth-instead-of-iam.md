# ADR 0001: Local JWT authentication instead of the Hino IAM

- Status: accepted
- Date: 2026-10-30

## Context

The template was the HIS standard starter for PT Hino Motors Sales Indonesia. Apps built from it had
no login page: users signed in at the HIS portal, an external IAM issued a token, and the app
verified it against the IAM and matched IAM role ids against a local `app_allowed_roles` table. That
couples every app to one company's identity system, ids, menus and brand, and makes the template
unusable anywhere else.

The goal is a universal, modern, professional starter that anyone can clone.

## Decision

Authentication, users, roles and permissions live in the application itself.

- Email + password, hashed with Argon2id.
- Short-lived JWT access tokens (15 minutes), kept in memory by the web app.
- Opaque refresh tokens, stored hashed, rotated on every use, delivered in an `HttpOnly` cookie
  scoped to `/api/v1/auth`. Reusing a rotated token revokes the whole chain.
- RBAC: `permissions` are code-defined `resource:action` strings synced by a seed command; `roles`
  are data that administrators compose; routes check permissions with `require_permissions(...)`.
- Lockout and rate limiting on login; production refuses unsafe configuration.

Details: `webapp-backend/docs/auth.md`.

## Consequences

Good:

- No dependency on an external identity provider; the template runs anywhere.
- Permissions are checked by name, so no numeric ids are hardcoded or copied between projects.
- The security-sensitive paths are covered by tests (lockout, rotation and reuse detection, RBAC).

Costs and trade-offs:

- The project now owns password storage and session security. Review changes to `core/security.py`
  and `modules/auth/` carefully.
- Single sign-on across several apps is not provided. Apps that need it can replace the login
  endpoint with an OIDC flow; the permission layer does not care how the user was authenticated.
- Frontend route protection is client-side, because the refresh cookie is scoped to the API path
  and Next.js middleware cannot see it. The API remains the authority.
- This supersedes RULES.md section 9 for projects started from this template. Hino HIS projects
  should keep using the `hino-final` tag.

## Alternatives considered

- **Pluggable provider (local + Hino IAM adapter):** more flexible, but doubles the surface area to
  maintain and test. Rejected for now; the permission layer leaves room to add it.
- **Generic OIDC only:** no local credentials to protect, but requires an external IdP before the
  template can be tried at all.

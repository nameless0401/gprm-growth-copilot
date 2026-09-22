# Audit v0.1.2

Base: user-provided v0.1.1.

## Validation
- `python -m compileall -q app tests`: PASS
- `pytest -q`: 9 passed
- No follow/unfollow implementation.
- No embedded Instagram/Telegram/OpenAI secret detected by static grep.

## Hardening applied
1. Production startup fails closed for SQLite, localhost/non-HTTPS base URL, missing Meta/Telegram credentials, missing operator allowlist, and default/short admin/webhook secrets.
2. Railway `postgresql://` URLs are normalized to `postgresql+psycopg://` for Psycopg 3.
3. Event deduplication is namespaced by `(source, external_id)`.
4. Empty approved drafts are blocked before any Instagram API call.
5. SQLite naive datetimes are normalized before expiry comparison.
6. Own-account comment webhooks are ignored to reduce reply-loop risk.
7. Invalid JSON webhooks return 400 cleanly.
8. Telegram HTML output is escaped for edited/opportunity text.
9. Draft notification delivery is tracked and transient failures are retried.
10. Daily pulse records success only when Telegram actually returns `ok=true`.

## Remaining deliberate V1 limits
- No OAuth onboarding UI; Meta token is supplied by environment variable.
- No automatic discovery or commenting on third-party Instagram posts.
- Growth attribution remains observational/correlational unless deeper analytics are added.
- Single application replica recommended for the lightweight in-process scheduler.

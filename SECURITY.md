# Security invariants

1. No follow/unfollow feature exists anywhere in this codebase.
2. No Instagram password is collected or stored. Authentication uses Meta access tokens supplied via environment variables.
3. `send_approved_draft()` is the single application-layer send gate. It refuses to send unless `status` is approved/edited AND `approved_by` and `approved_at` are present.
4. Editing clears previous approval. A second explicit approval click is mandatory.
5. Meta webhooks support `X-Hub-Signature-256` verification when `META_APP_SECRET` is configured. Production must configure it.
6. Telegram webhooks require `X-Telegram-Bot-Api-Secret-Token`, compared with `hmac.compare_digest`.
7. External-account growth comments are suggestions only. The application has no endpoint that posts them to third-party accounts.
8. Secrets belong in Railway/environment variables, never Git.
9. Only Telegram user IDs listed in `ALLOWED_OPERATOR_IDS` may approve/edit/reject/send a draft. `get_settings()` refuses to boot in production without this set (and without `META_APP_SECRET`). Admin token comparison also uses `hmac.compare_digest`.
10. `send_approved_draft()` re-fetches the draft with a row lock (`SELECT ... FOR UPDATE`) before sending, to prevent a double-click from triggering two sends. This lock is only effective on Postgres — SQLite ignores `FOR UPDATE`, another reason production must use Postgres.

11. Production startup fails closed if SQLite, default/short admin or webhook secrets, missing Meta credentials, missing operator allowlist, or a non-HTTPS public base URL is configured.
12. Failed Telegram draft notifications remain unnotified in the database and are retried by the scheduler; a transient notification failure does not silently lose a review item.

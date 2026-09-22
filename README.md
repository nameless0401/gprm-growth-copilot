# GPRM Growth Copilot

Private, human-in-the-loop Instagram growth copilot for `@d_gprm`.

## Goal

Move from the configured baseline (219 followers) toward 1,000 organically without paid acquisition, follow/unfollow automation, spam, or forced content production.

The bot does four things:

1. **Inbox copilot** — ingest Instagram comment/DM events, draft a reply, send it to Telegram for human approval.
2. **Hard approval gate** — nothing is sent until the operator explicitly clicks **Envoyer**. Editing invalidates the previous approval.
3. **Growth radar** — rotate through relevant Dakar/Gabon/medicine/running communities and surface 3 targets for manual inspection. It never posts to third-party accounts.
4. **1K pulse** — store follower snapshots and report progress against 1,000.

## Safety boundaries

- No follow/unfollow implementation.
- No Instagram password storage.
- No auto-DM and no auto-reply.
- No scraping/mobile-session emulation.
- No third-party-account commenting endpoint.
- Complete audit trail for receive → draft → approve/edit/reject → send/error.

See `SECURITY.md`.

## API mode

This project targets **Instagram API with Instagram Login** for professional accounts. Keep `META_API_VERSION` configurable; set it to the currently supported version in your Meta app rather than hard-coding a version forever.

Required permissions for the complete V1 are expected to include:

- `instagram_business_basic`
- `instagram_business_manage_comments`
- `instagram_business_manage_messages`

The messaging API can only reply to users/conversations that have initiated contact with the professional account. The bot does not cold-DM.

## Local start

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

Then open `http://localhost:8000/health`.

## Environment variables

Copy `.env.example`. The minimum to boot is none; the app will run in analysis-only mode. To actually draft/send:

- `OPENAI_API_KEY`, `OPENAI_MODEL` for draft generation.
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `TELEGRAM_WEBHOOK_SECRET` for operator approval.
- `META_ACCESS_TOKEN`, `META_IG_USER_ID`, `META_API_VERSION`, `META_VERIFY_TOKEN`, `META_APP_SECRET` for Meta.
- `ADMIN_TOKEN` protects setup/job endpoints. In production, admin/webhook secrets must be non-default and at least 20 characters.
- Production **must** use Railway Postgres via `DATABASE_URL`; the app refuses to boot with SQLite in production.

## Meta webhook

Configure your Meta app webhook callback to:

`https://YOUR_DOMAIN/webhooks/meta`

Use the exact value of `META_VERIFY_TOKEN` as verify token. Subscribe the Instagram object/events required for comment and messaging events according to the current Meta app configuration.

## Telegram setup

After deployment, register the webhook:

```bash
curl -X POST https://YOUR_DOMAIN/admin/setup/telegram-webhook \
  -H "X-Admin-Token: $ADMIN_TOKEN"
```

Commands:

- `/pulse` — current 1K progress.
- `/radar` — 3 accounts to inspect today.
- `/opportunity @handle context of the target post` — generate a public-comment suggestion to copy manually.

Inbound comment/DM cards include **Envoyer / Modifier / Ignorer**.

## Automatic daily cycle

A lightweight scheduler wakes every 15 minutes. Once the configured UTC hour is reached, it records at most one profile snapshot and sends at most one Telegram pulse per calendar day. For V1, deploy a single app replica.

## Metrics snapshot

```bash
curl -X POST https://YOUR_DOMAIN/admin/jobs/snapshot \
  -H "X-Admin-Token: $ADMIN_TOKEN"
```

The resulting follower count is stored in `metric_snapshots`.

## Railway

The repo contains `Dockerfile` and `railway.toml`.

Recommended production topology:

- App service: this repository
- Railway Postgres
- One replica for V1 (keeps scheduling/Telegram state simple)
- Variables from `.env.example` stored in Railway, never committed

Health check: `/health`.

## Seeded growth radar

`config/targets.json` starts with communities already identified as high-fit for this account: medicine/Dakar, running/Senegal, Gabon/Libreville, university/events, and local lifestyle. The radar is intentionally a recommendation layer, not an automation layer.

## Current V1 limits

- It does not discover arbitrary third-party Instagram posts automatically. This avoids scraping and unsupported mobile emulation. Use `/opportunity` after opening a target account/post.
- It stores profile snapshots through Meta. Deeper historical analytics can later be added through a server-side analytics provider or a dedicated warehouse sync.
- OAuth onboarding UI is not yet included; V1 expects a valid professional-account token in environment variables.

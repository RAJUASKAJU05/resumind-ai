# Resumind AI
Resume analyzer: FastAPI + SQLite backend, single-page frontend served by the same server.

## Run
    pip install -r requirements.txt
    export JWT_SECRET=change-me          # keeps logins valid across restarts
    export AI_API_KEY=your-gemini-key    # optional: enables AI review, improve, assistant (get a free key at aistudio.google.com)
    uvicorn app:app --reload             # open http://localhost:8000
    pytest                               # run tests

Env vars: JWT_SECRET, AI_API_KEY, AI_MODEL, DB_PATH, COOKIE_SECURE=1 (use behind HTTPS).
Without AI_API_KEY the scoring, ATS checks and job match still work; AI features return a clear "not configured" message.
AI_API_KEY is a Google Gemini key (aistudio.google.com > Get API key) — no credit card needed at signup, as of when this was written. AI_MODEL defaults to gemini-2.0-flash.

## Not built yet (updated)
Next.js, PostgreSQL, Redis, email sending, async job queue, admin dashboard, full marketing pages.

## Deploy (free) - gives a shareable link
1. Push this folder to a GitHub repo.
2. On render.com: New > Blueprint > pick the repo. It reads render.yaml and builds the Dockerfile (includes OCR).
3. In the service's Environment tab, paste your AI_API_KEY. Open the https://...onrender.com link and share it.
Free tier sleeps when idle (first load takes ~30s) and its disk is temporary, so accounts reset on redeploy; use a paid disk or Postgres for permanence.
Password reset uses RESET_CODE (shown in the Environment tab) because email sending isn't set up.

## Demo login for presentations
Free hosting wipes the database whenever the service restarts or wakes from sleep, so normal accounts disappear.
Set DEMO_EMAIL and DEMO_PASSWORD in the Environment tab; that login is re-created at every start.

## Supabase (permanent database)
The tables already exist in the Supabase project (see supabase_schema.sql). To use them, set DATABASE_URL on Render to the
Supabase **Session pooler** connection string (Supabase dashboard > Connect > Session pooler), with your database password filled in:
    postgresql://postgres.PROJECTREF:YOUR-PASSWORD@aws-0-ap-northeast-1.pooler.supabase.com:5432/postgres
Check https://YOUR-SITE.onrender.com/health : it should show "database":"supabase-postgres" and "database_ok":true.
Without DATABASE_URL the app falls back to local SQLite (data lost on restart on free hosting).
If you add a new table later (see supabase_schema.sql), run that new CREATE TABLE block directly in Supabase's
SQL Editor — the app does not create Postgres tables automatically, only the SQLite fallback does that for you.

## The flow
Upload Resume > Analyze > Match Job > Find Skill Gaps > Improve Resume > Practice Interview > Track Applications.
The dashboard stepper ticks each step from real activity. "Improve" is ticked after the AI line-improver is used (needs AI_API_KEY).

## Security hardening
What's implemented, and why:
- **Rate limiting** — login, register, password reset, resume upload, AI calls, job/match/interview/application
  creation are all capped per user (or per IP before login) to block abuse and brute-forcing.
- **Row-level security** — every Supabase table has RLS enabled, and the public API (anon/authenticated roles) has
  all table grants revoked. Only the backend's own database connection (DATABASE_URL) can read or write anything;
  there's no way to query user data directly through Supabase's REST/GraphQL API.
- **Every data route requires login** — enforced by FastAPI's Depends(user) on each endpoint, and locked in by an
  automated test (test_auth_required_on_every_protected_route) that fails if a future route is added without it.
- **Input sanitization** — every field has a length limit (Pydantic), and the frontend escapes all user- and
  AI-generated text before inserting it into the page, so stored or reflected XSS isn't possible through normal use.
- **CORS is locked down** — no cross-origin access is allowed by default (ALLOWED_ORIGINS env var opts in extra
  origins only if you ever split the frontend into its own domain).
- **No IDOR (insecure direct object reference)** — every resume/job/match/application/interview lookup checks that
  the record belongs to the logged-in user; a stranger gets 404, not someone else's data. Covered by an automated
  test (test_idor_blocked_everywhere) that tries to read, edit and delete another user's data and asserts it fails.
- **CAPTCHA on registration** — a self-hosted math question plus a hidden honeypot field, so bots can't mass-create
  accounts. No third-party key needed (deliberately, after how much trouble the Gemini key setup caused earlier).
- **Security log** — sensitive actions (register, login, failed login, password reset, resume/account deletion) are
  recorded with a timestamp and IP, visible to each user for their own account under Dashboard → Security log. This
  app has no admin role, so it's a personal audit trail rather than a site-wide admin log.

## Known gaps (said plainly, not hidden)
- **No file storage bucket to secure.** Uploaded resumes are parsed for their text and the original file is
  discarded — nothing is kept in cloud storage, so there's no bucket-privacy setting to make. If you want the
  original files retained later, that would need a private Supabase Storage bucket added on purpose.
- **No admin page exists yet**, so there's nothing to hide behind proper access control yet. If one gets built, it
  needs its own role check (not just "logged in") and should 404 rather than 403 for non-admins, so its existence
  isn't revealed to probing.
- **CAPTCHA is self-hosted, not Google reCAPTCHA** — a deliberate trade-off to avoid needing another external API
  key; it stops basic bots but not a determined attacker running a real browser.

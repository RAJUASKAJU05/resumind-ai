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

## The flow
Upload Resume > Analyze > Match Job > Find Skill Gaps > Improve Resume > Practice Interview > Track Applications.
The dashboard stepper ticks each step from real activity. "Improve" is ticked after the AI line-improver is used (needs AI_API_KEY).

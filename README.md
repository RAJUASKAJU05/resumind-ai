# Resumind AI
Resume analyzer: FastAPI + SQLite backend, single-page frontend served by the same server.

## Run
    pip install -r requirements.txt
    export JWT_SECRET=change-me          # keeps logins valid across restarts
    export AI_API_KEY=your-key           # optional: enables AI review, improve, assistant
    uvicorn app:app --reload             # open http://localhost:8000
    pytest                               # run tests

Env vars: JWT_SECRET, AI_API_KEY, AI_MODEL, DB_PATH, COOKIE_SECURE=1 (use behind HTTPS).
Without AI_API_KEY the scoring, ATS checks and job match still work; AI features return a clear "not configured" message.

## Not built yet (updated)
Next.js, PostgreSQL, Redis, email sending, async job queue, admin dashboard, full marketing pages.

## Deploy (free) - gives a shareable link
1. Push this folder to a GitHub repo.
2. On render.com: New > Blueprint > pick the repo. It reads render.yaml and builds the Dockerfile (includes OCR).
3. In the service's Environment tab, paste your AI_API_KEY. Open the https://...onrender.com link and share it.
Free tier sleeps when idle (first load takes ~30s) and its disk is temporary, so accounts reset on redeploy; use a paid disk or Postgres for permanence.
Password reset uses RESET_CODE (shown in the Environment tab) because email sending isn't set up.

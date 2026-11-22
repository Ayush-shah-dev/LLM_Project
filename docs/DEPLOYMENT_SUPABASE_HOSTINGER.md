# Deploy CiteGuard: Supabase + Render + Hostinger

This is the simplest production split for this repository:

```text
Browser -> Hostinger static React site -> Render FastAPI API -> Supabase Postgres
```

Supabase is used only as the application database. Do **not** put a Supabase service-role key,
database password, or Groq key in the frontend.

## 1. Create the Supabase database

1. Create a Supabase project and save its database password in a password manager.
2. In the project dashboard, select **Connect**, then choose **Session pooler**. This is the
   reliable choice for Render's IPv4 network. Copy the connection string.
3. Change its scheme from `postgresql://` to `postgresql+asyncpg://` and append
   `?sslmode=require` if it is not present. Percent-encode reserved characters in the password.

Example only (do not copy the host/user names literally):

```text
postgresql+asyncpg://postgres.PROJECT_REF:ENCODED_PASSWORD@POOLER_HOST:5432/postgres?sslmode=require
```

Do not enable or use the Supabase Data API for CiteGuard; the backend connects to Postgres
directly and owns its schema and authorization.

## 2. Deploy the API to Render

Create a **Web Service** from this Git repository.

| Render field | Value |
| --- | --- |
| Runtime | Docker |
| Dockerfile path | `backend/Dockerfile` |
| Docker context directory | `backend` |
| Health check path | `/healthz` |
| Docker command | Leave blank (the image runs migrations and starts the API itself) |

Set these environment variables in Render's **Environment** page:

```env
DATABASE_URL=postgresql+asyncpg://...                 # Supabase session-pooler URL
GROQ_API_KEY=...                                      # optional but recommended
CONTACT_EMAIL=you@example.com
OPENALEX_API_KEY=...                                  # recommended
S2_API_KEY=...                                        # optional
NCBI_API_KEY=...                                      # optional

AUTH_ENABLED=true
ADMIN_API_KEY=a-long-random-secret
CORS_ORIGINS=["https://your-domain.com","https://www.your-domain.com"]

JOB_BACKEND=inline
CACHE_BACKEND=memory
DB_AUTO_CREATE=false
LOG_JSON=true
```

`JOB_BACKEND=inline` avoids needing Redis and a separate worker. It is appropriate for an
initial low-traffic deployment. For higher throughput, use a Redis service and a second Render
worker before switching to `JOB_BACKEND=arq`.

After the first successful deployment, open `https://YOUR-API.onrender.com/docs`. The container
applies the Alembic migration before the API starts. Create an application API key once:

```bash
# Run in Render's service shell.
citeguard create-key --name "production-web" --rate-limit 30
```

Copy the displayed `cg_...` key immediately. It is shown only once. Visitors enter it in the
web app's Settings dialog; it is stored in their browser, not in the hosted frontend.

## 3. Build and upload the frontend to Hostinger

From the repository root on your computer:

```powershell
Copy-Item frontend\.env.production.example frontend\.env.production
# Edit frontend\.env.production and replace the URL with your Render API URL.
cd frontend
npm run build
```

Upload the **contents** of `frontend/dist/` (not the `dist` folder itself) to Hostinger's
`public_html/` directory. The build includes an `.htaccess` fallback for Apache/Hostinger, so
React Router URLs such as `/history` and `/checks/ID` work when refreshed.

If using Hostinger's Git/Web Apps workflow instead, configure the same build-time variable
`VITE_API_BASE_URL` before its Vite build. Do not upload `frontend/.env.production` to Git if it
contains a non-public value (this example contains only a public URL).

## 4. Final production checks

1. Visit the Hostinger URL and open Settings.
2. Paste the `cg_...` API key, then select **Save & test**.
3. Submit one known citation and confirm its progress events complete.
4. In the browser developer tools, confirm requests target the Render URL and have no CORS error.
5. Confirm `https://YOUR-API.onrender.com/readyz` returns HTTP 200.

## Updating

For an API change, push to the connected branch and let Render redeploy. For a frontend change,
set the same `VITE_API_BASE_URL`, run `npm run build`, then replace the contents of
`public_html/` with the new `frontend/dist/` contents. Purge Hostinger's cache/CDN if enabled.

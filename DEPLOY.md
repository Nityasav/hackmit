# Deploying Sherlock

The web app is on Vercel. The API is not, and cannot be: it is a long-lived process that keeps
SQLite on disk, with uploaded originals stored as bytes inside it. Vercel's serverless filesystem
does not survive between invocations, so the API needs a container host — Render, Railway or Fly.

Until the API is reachable, a deployed web app calls `http://localhost:8000`, which in a visitor's
browser means *their* laptop. That is why the site loads and nothing in it works.

## 1. Decide who may use it

The API refuses non-loopback traffic unless you opt in per hostname, and it refuses to serve at all
if you opt in without configuring accounts. That is deliberate: with `SCHOOLTRACE_USERS` unset,
every caller is treated as an admin over every workspace, so an open deployment would let anyone
upload, scan and delete.

Generate a password hash for each person:

```bash
cd api && uv run python -c "from app.security import password_hash; print(password_hash('CHOOSE-A-PASSWORD'))"
```

Build the JSON (one entry per person, roles: `admin`, `reviewer`, `analyst`, `viewer`):

```json
{"nitya": {"role": "admin", "workspaces": ["*"], "password_hash": "<salt>:<digest>"}}
```

## 2. Deploy the API

Any host that runs a container works. `api/Dockerfile` builds it and honours `$PORT`.

**Render** — New → Web Service → point at this repo, root directory `api`, runtime Docker. Add a
disk mounted at `/data` if you want uploads to survive a restart; without one the container still
runs and everything uploaded is lost on redeploy.

**Railway** — New Service → Deploy from repo, root directory `api`. Add a volume at `/data`.

**Fly** — `fly launch --dockerfile api/Dockerfile`, then `fly volumes create data` and mount it at
`/data`.

Set these environment variables on the API service:

| Variable | Value | Why |
| --- | --- | --- |
| `SCHOOLTRACE_PUBLIC_HOSTS` | `your-api.onrender.com` | Opts this hostname out of loopback-only. Without it every request is 403 |
| `SCHOOLTRACE_USERS` | the JSON from step 1 | Required in hosted mode; the API returns 503 until it is set |
| `SCHOOLTRACE_ALLOWED_ORIGINS` | `https://schooltrace.vercel.app` | Your production web origin, for CORS and the origin allowlist |
| `SCHOOLTRACE_ALLOWED_ORIGIN_REGEX` | `https://schooltrace-.*\.vercel\.app` | Vercel gives every preview deployment its own hostname |
| `SCHOOLTRACE_DATA_DIR` | `/data` | Already set in the image; point it at your mounted volume |
| `OPENAI_API_KEY` | your key | Only needed for agent runs, not for intake or the deterministic checks |

Check it: `curl https://your-api.onrender.com/api/health` should return `{"status":"ok"}`.

## 3. Point the web app at it

In the Vercel project, add `NEXT_PUBLIC_API_URL=https://your-api.onrender.com` for Production and
Preview, then **redeploy**.

The redeploy is not optional. `NEXT_PUBLIC_*` values are substituted into the browser bundle at
build time, so changing the variable without rebuilding leaves the old value — `localhost:8000` —
baked into the JavaScript already being served.

## 4. Sign in

Hosted, the web app and the API are separate sites, so the session cookie is issued with
`SameSite=None; Secure`. That requires HTTPS on both, which every host above terminates for you.
Locally nothing changes: with `SCHOOLTRACE_PUBLIC_HOSTS` unset the cookie stays `SameSite=Strict`
and no account is needed.

## What this setup is not

It is a demo deployment. Passwords are scrypt-hashed and sessions expire after eight hours, but
there is no rate limiting on the API itself, no audit trail of reads, and no tenancy beyond the
per-user workspace list. Upload synthetic and public records only. The reviewer header
(`X-SchoolTrace-Reviewer`) marks an intentional write; it is not authentication and never was.

If the volume is missing or the host restarts the container, uploaded records are gone. Say that
out loud before demoing on a hosted instance rather than discovering it in front of a judge.

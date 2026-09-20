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

**Railway** — the walkthrough below is the one that has been tested.

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

## 2a. Railway, step by step

`api/railway.json` already pins the Dockerfile builder, a `/api/health` healthcheck and one replica.
Keep it at one: SQLite takes a single writer per file, and a second replica would get its own
volume and its own half of your data.

**From the dashboard**

1. **New Project → Deploy from GitHub repo →** `Nityasav/hackmit`.
2. Open the service → **Settings → Root Directory** → `api`. Railway then finds `railway.json`
   and `Dockerfile` itself; leave the build and start commands empty, since the image sets both.
3. **Settings → Networking → Generate Domain.** Copy the hostname it gives you, e.g.
   `sherlock-api-production.up.railway.app`. You need it before the first successful boot, because
   the API refuses any hostname not in `SCHOOLTRACE_PUBLIC_HOSTS`.
4. **Add the volume from the command palette, not from Settings.** There is no Volumes section in
   the service settings. Press `⌘K`, or right-click the project canvas, and create a volume; pick
   this service when it asks, then set its **mount path to `/data`** in the service panel. Skip
   this and every upload disappears on the next deploy or restart.
5. **Variables** — add the table above, with `SCHOOLTRACE_PUBLIC_HOSTS` set to the hostname from
   step 3 and no `https://` prefix. `PORT` is injected by Railway; do not set it.
6. Redeploy. `curl https://<your-domain>/api/health` → `{"status":"ok"}`.

**From the CLI**

```bash
npm i -g @railway/cli && railway login
cd api && railway init && railway up          # builds the Dockerfile
railway domain                                 # prints the hostname for step 5
railway variables --set SCHOOLTRACE_PUBLIC_HOSTS=<your-domain> \
                  --set SCHOOLTRACE_USERS='<json from step 1>' \
                  --set SCHOOLTRACE_ALLOWED_ORIGINS=https://schooltrace.vercel.app \
                  --set 'SCHOOLTRACE_ALLOWED_ORIGIN_REGEX=https://schooltrace-.*\.vercel\.app'
```

Add the volume from the dashboard afterwards — the CLI browses and transfers files
(`railway volume browse /`, `railway volume files list /`) but does not create or attach one.

Two constraints worth knowing before you scale anything: a service can hold **only one volume**, and
**replicas cannot be used with volumes at all** — which is the same single-writer limit SQLite
already imposes, so `numReplicas: 1` in `railway.json` is not a preference. Volumes also mount at
container start, not during the build, so nothing written into `/data` at build time survives.

**What the image does on Railway, verified locally**

The same container was built and run with `PORT`, a mounted volume and hosted variables set:
it boots, binds `$PORT`, answers `/api/health` with 200, returns 401 without a session, answers the
CORS preflight with 200, writes `schooltrace.sqlite3` into `/data`, and keeps that file across a
restart. With `SCHOOLTRACE_PUBLIC_HOSTS` set and `SCHOOLTRACE_USERS` missing it returns 503 and
refuses to serve, which is the intended failure.

If a build fails on Railway, it will be in the dependency layer — `rapidocr-onnxruntime` pulls
OpenCV, which needs `libgl1` and `libglib2.0-0`. Both are installed in the Dockerfile; do not strip
them to slim the image.

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

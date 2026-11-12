# Local HTTPS development

This setup serves the Next.js app at `https://localhost:3000` and FastAPI at
`https://localhost:8000`. `mkcert` creates a certificate trusted by this Windows
user, so the browser can send the app's secure HttpOnly session cookies locally.

## 1. Generate a trusted localhost certificate

In PowerShell from the repository root:

```powershell
winget install FiloSottile.mkcert
```

Close and reopen PowerShell, then run:

```powershell
./scripts/setup-local-https.ps1
```

The script installs mkcert's local root certificate and creates
`certs/localhost.pem` and `certs/localhost-key.pem`. The `certs` directory is
git-ignored; do not commit or share the private key.

## 2. Configure the frontend

Set `frontend/.env.local` (copy `frontend/.env.example` if needed) to:

```env
NEXT_PUBLIC_API_URL=https://localhost:8000
```

## 3. Configure the backend

In `backend/.env`, set these values:

```env
ENVIRONMENT=local-https
FRONTEND_URL=https://localhost:3000
CORS_ORIGINS=https://localhost:3000
```

Keep the rest of your existing backend secrets and database settings. The
non-development environment value enables `Secure` on the HTTP-only auth
cookies.

## 4. Start both servers

Open two PowerShell terminals.

Terminal 1 — backend:

```powershell
Set-Location backend
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 `
  --ssl-keyfile ../certs/localhost-key.pem `
  --ssl-certfile ../certs/localhost.pem
```

Terminal 2 — frontend:

```powershell
Set-Location frontend
npm run dev:https
```

Open `https://localhost:3000`. The API docs are at `https://localhost:8000/docs`.
Use `localhost` consistently; do not mix it with `127.0.0.1`, because browser
cookie and origin rules treat those as different hosts.

For ordinary HTTP development, keep the existing `npm run dev` and regular
Uvicorn command, and set `ENVIRONMENT=development` with HTTP frontend/CORS/API
URLs. Do not use the local HTTPS cookie setting with an HTTP frontend.

# CareFlow frontend

Next.js App Router frontend for the CareFlow clinic platform.

## Run locally

1. Install Node.js 20.9 or later and npm.
2. Copy `.env.example` to `.env.local` and set `NEXT_PUBLIC_API_URL` to the FastAPI backend URL.
3. From this directory, run:

   ```powershell
   npm install
   npm run dev
   ```

The development server uses `http://localhost:3000`, matching the backend's
`CORS_ORIGINS` and `FRONTEND_URL` settings. Production uses `npm run build`
and `npm start`.

Sessions use the backend's HTTP-only cookies. The browser sends credentials on
API calls; access and refresh tokens are not kept in JavaScript storage.

## Routes

- `/` — sign-in and role-based clinic workspace
- `/auth/accept-invite` — accept a clinic invitation and set a password
- `/auth/reset-password` — finish password recovery

## Included workflows

- Clinic sign-in, password recovery, and invitation acceptance
- Clinic admin onboarding, setup, patient records, CSV imports, and team access
- Doctor visit documentation, consent, prescriptions, lab orders, and signatures
- Nurse vitals, receptionist appointment and waiting-room tools, and billing claims
- Patient appointments, health records, patient messaging, and staff conversations
- Platform owner clinic and user views

The UI follows the API roles and permissions. Some workflows are intentionally
available only to the role authorized by the backend.

# CareFlow database schema

CareFlow uses Supabase Auth for credentials and sessions. Application identity is
stored in `public.users`, linked one-to-one to `auth.users.id`. Passwords are
never stored in the CareFlow tables. The FastAPI backend is the only application
interface for profiles, memberships, and role changes; `users` and
`clinic_memberships` and all tenant data tables have RLS enabled and no grants
for `anon` or `authenticated`.

## Identity and tenant access

### `users`

| Column | Purpose |
| --- | --- |
| `id` | UUID primary key and foreign key to `auth.users.id` |
| `email` | Unique account email |
| `full_name` | User display name |
| `phone_number` | Optional phone number |
| `role` | Platform role (`user` or `super_admin`) |
| `is_super_admin` | Server-managed platform-admin flag |
| `is_active` | Account access switch |
| `email_verified_at` | Timestamp observed from verified Supabase Auth identity |
| `created_at`, `updated_at` | Record timestamps |

Clinic roles belong to memberships rather than the global profile. This permits
one login to have different roles in multiple clinic tenants.

### `clinic_memberships`

One row per user and clinic. `role` is one of `clinic_admin`, `doctor`, `nurse`,
`receptionist`, `billing_staff`, or `patient`. `status` is `invited`, `active`, or
`suspended`. A patient membership must point to that clinic's `patients.id`;
staff memberships have no patient link. Invitation and acceptance timestamps
and the inviting user are retained.

### `staff_members`

This remains the clinical/workflow staff record referenced by notes, orders,
visits, and audits. Account identity and tenant authorization live in
`users`/`clinic_memberships`; the staff row mirrors clinic staff for existing
domain foreign keys. The unique account constraint is now per clinic.

## Existing care data

The care schema creates `clinics`, `patients`, `appointments`, `visits`,
`clinical_notes`, `orders`, `medications`, `allergies`, `messages`,
`care_team_assignments`, `audit_events`, `outbox_events`, `claims`,
`ai_suggestions`, `patient_vitals`, and `medical_conditions`. Patient portal reads
are restricted to the linked patient row and signed notes; those reads write an
`audit_events` row with `actor_user_id`.

### Messaging

- Patient portal messages target either an active clinic receptionist or a
  doctor assigned to the patient. `assigned_staff_id` records the selected
  recipient, and staff replies remain in the patient-visible `portal` channel.
- Staff direct messages use the `staff_internal` channel with
  `sender_staff_id` and `recipient_staff_id`. They have no `patient_id` and are
  read or sent through the staff conversation APIs, independently of a patient
  message thread.

### Clinic setup and scheduling

- `clinic_business_hours` stores one clinic-local open/closed window per weekday.
- `clinic_rooms` stores named, soft-deactivated clinic rooms.
- `doctor_availability` stores recurring weekday windows with effective date
  ranges. Appointment slot generation intersects these rules with clinic hours
  and existing appointments.
- `appointments.room_id` optionally reserves a clinic room.
- `appointments.idempotency_key` and `request_fingerprint` prevent duplicate
  bookings when a client retries the same request.

### Patient imports

- `patient_import_jobs` stores clinic ownership, uploader, private object key,
  SHA-256, status, total and processed row counts, and the next CSV row cursor.
- `patient_import_errors` stores clinic-scoped row and field validation errors.
  Uploaded CSV bytes are stored in the private Supabase Storage bucket named by
  `SUPABASE_IMPORT_BUCKET`, not in Postgres.
- New tenant tables have RLS enabled and are revoked from Supabase `anon` and
  `authenticated`; the backend uses its server database connection.

## Migration

Apply Alembic migrations from the backend directory after configuring the
Supabase Postgres `DATABASE_URL` and Auth environment variables:

```powershell
uv run alembic upgrade head
```

The migration references Supabase's managed `auth.users` table and assumes the
database connection has permission to create a foreign key to it. Never expose
the Supabase secret key to the frontend.

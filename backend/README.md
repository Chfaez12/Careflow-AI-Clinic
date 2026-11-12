# CareFlow backend API

See [implementation-phases.md](../docs/implementation-phases.md) for the
project build sequence and completion gates.

## Authentication and roles

Supabase Auth manages email/password credentials, confirmation, refresh tokens,
password recovery, and invitations. The backend keeps a profile in
`public.users` and clinic-scoped permissions in `public.clinic_memberships`.
Role assignments are made by the backend, never accepted from public signup
metadata. Patient portal access is scoped to the patient's
linked record.

Login, registration, bootstrap, and refresh set `careflow_access_token` and
`careflow_refresh_token` as HttpOnly cookies; token values are not returned in
JSON. Authenticated frontend requests must use `credentials: "include"` (or
`withCredentials: true`). Cookies use `Secure` outside development, `SameSite=Lax`,
and `Path=/`. The refresh endpoint reads the refresh cookie, and logout clears
both cookies.

Configure `backend/.env` from `.env.example`. Set the Supabase project URL,
publishable key, secret key, and Postgres connection URL. The secret key is only
used by the backend for Admin API invitations and must never be sent to the
frontend. Supabase email templates and allowed redirect URLs must include
`/auth/accept-invite` and `/auth/reset-password` on the configured frontend.

Routes are grouped by purpose in `app/api/auth.py`,
`clinic_members.py`, `patient_portal.py`, and `platform_admin.py`. Shared
membership provisioning lives in `app/services/account_service.py`; request
schemas are split by domain under `app/schemas/`; SQLAlchemy reads and data
access methods are grouped under `app/repositories/`.

### Auth endpoints

| Method | Path | Access | Purpose |
| --- | --- | --- | --- |
| `POST` | `/auth/register` | Public | Create a clinic, generate its unique slug, and create the first clinic-admin profile/membership |
| `POST` | `/auth/bootstrap-super-admin` | One-time secret | Provision first platform admin |
| `POST` | `/auth/login` | Public | Sign in; returns profile, memberships, and session |
| `POST` | `/auth/refresh` | Refresh cookie | Rotate Supabase session and cookies |
| `POST` | `/auth/logout` | Cookie or bearer | Revoke current session and clear cookies |
| `POST` | `/auth/password/reset` | Public | Send recovery email |
| `PUT` | `/auth/password` | Bearer | Change password |
| `GET` | `/auth/me` | Bearer | Return profile and memberships |
| `PATCH` | `/auth/me` | Bearer | Update the signed-in user's name and phone |
| `GET` | `/auth/verify` | Bearer | Verify the current CareFlow identity |
| `POST` | `/auth/invitations/accept` | Bearer | Accept one pending membership after email verification (`clinic_id`) |

### Clinic and patient APIs

All paths below are prefixed with `/auth` and require a bearer access token.

| Method | Path | Required role | Purpose |
| --- | --- | --- | --- |
| `GET` | `/auth/clinics/{clinic_id}/membership` | Any clinic member | Read own clinic role and membership state |
| `GET` | `/auth/clinics/{clinic_id}/members` | Clinic admin | List tenant memberships and profiles |
| `POST` | `/auth/clinics/{clinic_id}/invitations` | Clinic admin | Invite doctor, nurse, receptionist, billing staff, or linked patient |
| `DELETE` | `/auth/clinics/{clinic_id}/members/{user_id}` | Clinic admin | Remove a user's access to this clinic; confirm with their email. Their global account and data remain |
| `POST` | `/auth/clinics/{clinic_id}/members/{user_id}/restore` | Clinic admin | Restore a soft-deleted member account; confirm with their email |
| `GET` | `/auth/clinics/{clinic_id}/patients` | Clinic admin, doctor, nurse, receptionist | Search and paginate patient records |
| `POST` | `/auth/clinics/{clinic_id}/patients` | Clinic admin, doctor, nurse, receptionist | Create a patient record |
| `GET` | `/auth/clinics/{clinic_id}/patients/{patient_id}` | Clinic admin, doctor, nurse, receptionist | Read one patient record |
| `PATCH` | `/auth/clinics/{clinic_id}/patients/{patient_id}` | Clinic admin, doctor, nurse, receptionist | Update patient demographics and emergency contact |
| `GET` | `/auth/clinics/{clinic_id}/setup/profile` | Clinic admin | Read clinic contact details and timezone |
| `PATCH` | `/auth/clinics/{clinic_id}/setup/profile` | Clinic admin | Update clinic name, phone, address, and IANA timezone |
| `GET` | `/auth/clinics/{clinic_id}/setup/onboarding` | Clinic admin | View setup checklist and completion counts |
| `GET` | `/auth/clinics/{clinic_id}/setup/business-hours` | Clinic admin | Read weekly clinic hours |
| `PUT` | `/auth/clinics/{clinic_id}/setup/business-hours` | Clinic admin | Replace all seven clinic-local weekday schedules |
| `GET` | `/auth/clinics/{clinic_id}/setup/rooms` | Clinic admin | List clinic rooms |
| `POST` | `/auth/clinics/{clinic_id}/setup/rooms` | Clinic admin | Add a room |
| `PATCH` | `/auth/clinics/{clinic_id}/setup/rooms/{room_id}` | Clinic admin | Rename, update, or deactivate a room |
| `GET` | `/auth/clinics/{clinic_id}/setup/doctors` | Clinic admin | List active clinic doctors for schedule setup |
| `GET` | `/auth/clinics/{clinic_id}/setup/doctor-availability` | Clinic admin, doctor | List availability rules; doctors see only their own |
| `POST` | `/auth/clinics/{clinic_id}/setup/doctor-availability` | Clinic admin | Add a weekly doctor availability rule with an effective date range |
| `DELETE` | `/auth/clinics/{clinic_id}/setup/doctor-availability/{availability_id}` | Clinic admin | Deactivate a doctor availability rule |
| `GET` | `/auth/clinics/{clinic_id}/scheduling/doctors` | Patient, clinic admin, receptionist | List active bookable doctors; patients see assigned doctors only |
| `GET` | `/auth/clinics/{clinic_id}/scheduling/rooms` | Patient, clinic admin, receptionist | List active rooms |
| `GET` | `/auth/clinics/{clinic_id}/scheduling/doctors/{staff_member_id}/slots` | Patient, clinic admin, receptionist | Find available clinic-local appointment slots and rooms for a day |
| `POST` | `/auth/clinics/{clinic_id}/imports/patients` | Clinic admin | Upload a CSV to a private Supabase Storage bucket |
| `GET` | `/auth/clinics/{clinic_id}/imports/patients` | Clinic admin | List import jobs |
| `GET` | `/auth/clinics/{clinic_id}/imports/patients/{job_id}` | Clinic admin | Read import status and batch cursor |
| `POST` | `/auth/clinics/{clinic_id}/imports/patients/{job_id}/preview` | Clinic admin | Validate CSV headers and rows without importing |
| `GET` | `/auth/clinics/{clinic_id}/imports/patients/{job_id}/errors` | Clinic admin | Page through row validation errors |
| `POST` | `/auth/clinics/{clinic_id}/imports/patients/{job_id}/run` | Clinic admin | Import the next resumable batch of validated patient rows |
| `GET` | `/auth/clinics/{clinic_id}/doctor/dashboard` | Doctor | View assigned appointments, active visits, and messages needing review |
| `GET` | `/auth/clinics/{clinic_id}/doctor/patients` | Doctor | Search and paginate patients assigned through care team, appointments, or visits |
| `GET` | `/auth/clinics/{clinic_id}/doctor/patients/{patient_id}/chart` | Doctor | Read assigned patient's demographics, appointments, visits, allergies, medications, vitals, notes, and orders |
| `POST` | `/auth/clinics/{clinic_id}/doctor/patients/{patient_id}/allergies` | Doctor | Record an active allergy for an assigned patient |
| `PATCH` | `/auth/clinics/{clinic_id}/doctor/allergies/{allergy_id}` | Doctor | Update allergy reaction, severity, or status |
| `POST` | `/auth/clinics/{clinic_id}/doctor/patients/{patient_id}/conditions` | Doctor | Add a diagnosis/medical condition to an assigned patient's chart |
| `PATCH` | `/auth/clinics/{clinic_id}/doctor/conditions/{condition_id}` | Doctor | Update condition status and resolution details |
| `GET` | `/auth/clinics/{clinic_id}/doctor/appointments` | Doctor | List the doctor's appointments for a clinic-local day |
| `GET` | `/auth/clinics/{clinic_id}/doctor/visits/{visit_id}` | Doctor | Read an assigned visit and its clinical context |
| `POST` | `/auth/clinics/{clinic_id}/doctor/visits/{visit_id}/start` | Doctor | Start an active visit assigned to the doctor |
| `PATCH` | `/auth/clinics/{clinic_id}/doctor/visits/{visit_id}` | Doctor | Update the visit chief complaint |
| `PUT` | `/auth/clinics/{clinic_id}/doctor/visits/{visit_id}/recording-consent` | Doctor | Record the patient's recording consent decision and timestamp |
| `GET` | `/auth/clinics/{clinic_id}/doctor/visits/{visit_id}/notes` | Doctor | List visit notes, including drafts and signed notes |
| `POST` | `/auth/clinics/{clinic_id}/doctor/visits/{visit_id}/notes` | Doctor | Create a DRAFT clinical note |
| `PATCH` | `/auth/clinics/{clinic_id}/doctor/notes/{note_id}` | Note author | Edit an unsigned draft note |
| `POST` | `/auth/clinics/{clinic_id}/doctor/notes/{note_id}/sign` | Note author | Sign and lock a draft note; queues a `clinical_note.signed` event |
| `POST` | `/auth/clinics/{clinic_id}/doctor/visits/{visit_id}/prescriptions` | Doctor | Create a draft prescription order |
| `POST` | `/auth/clinics/{clinic_id}/doctor/visits/{visit_id}/lab-orders` | Doctor | Create a draft lab order |
| `PATCH` | `/auth/clinics/{clinic_id}/doctor/orders/{order_id}` | Order author | Edit an unsigned draft order |
| `POST` | `/auth/clinics/{clinic_id}/doctor/orders/{order_id}/cancel` | Order author | Cancel an unsigned draft order |
| `POST` | `/auth/clinics/{clinic_id}/doctor/orders/{order_id}/sign` | Order author | Sign an order; prescriptions also create the active medication record |
| `POST` | `/auth/clinics/{clinic_id}/doctor/medications/{medication_id}/discontinue` | Doctor | Discontinue an active medication for an assigned patient |
| `GET` | `/auth/clinics/{clinic_id}/doctor/visits/{visit_id}/ai-suggestions` | Doctor | Review AI suggestions linked to an assigned visit |
| `POST` | `/auth/clinics/{clinic_id}/doctor/visits/{visit_id}/ai-suggestions/{suggestion_id}/decision` | Doctor | Accept or reject a pending suggestion; accepted note suggestions become DRAFT notes |
| `POST` | `/auth/clinics/{clinic_id}/doctor/visits/{visit_id}/complete` | Doctor | Complete a visit after signing a clinical note |
| `GET` | `/auth/clinics/{clinic_id}/portal/me` | Patient | Read own demographics, appointments, allergies, active medicines, signed notes and signed orders/results |
| `GET` | `/auth/clinics/{clinic_id}/portal/appointments` | Patient | List own appointments |
| `POST` | `/auth/clinics/{clinic_id}/portal/appointments` | Patient | Book an appointment in a future timezone-aware interval |
| `PATCH` | `/auth/clinics/{clinic_id}/portal/appointments/{appointment_id}/reschedule` | Patient | Reschedule own appointment |
| `POST` | `/auth/clinics/{clinic_id}/portal/appointments/{appointment_id}/cancel` | Patient | Cancel own appointment |
| `GET` | `/auth/clinics/{clinic_id}/portal/doctors` | Patient | List only active doctors assigned to the patient |
| `GET` | `/auth/clinics/{clinic_id}/portal/messages` | Patient | Read own portal conversation |
| `POST` | `/auth/clinics/{clinic_id}/portal/messages` | Patient | Message one assigned doctor; payload requires `target_doctor_id` |
| `GET` | `/auth/clinics/{clinic_id}/messages/inbox` | Clinic admin, doctor, nurse, receptionist | Review patient messages; emergency and urgent messages are listed first |
| `POST` | `/auth/clinics/{clinic_id}/messages/{message_id}/reply` | Assigned doctor or clinic admin | Send a patient-visible reply |
| `GET` | `/auth/clinics/{clinic_id}/messages/{message_id}/thread` | Assigned doctor, receptionist, clinic admin | Read patient message and staff-only coordination notes |
| `POST` | `/auth/clinics/{clinic_id}/messages/{message_id}/internal` | Assigned doctor, receptionist, clinic admin | Send a staff-only note to the receptionist or assigned doctor |
| `POST` | `/auth/clinics/{clinic_id}/care-team/assignments` | Clinic admin | Assign a doctor or nurse by `staff_member_id`; assignment role is read from that staff record |
| `DELETE` | `/auth/clinics/{clinic_id}/care-team/assignments/{assignment_id}` | Clinic admin | Remove a care-team assignment |
| `GET` | `/auth/clinics/{clinic_id}/nurse/dashboard` | Nurse | View assigned patients, visits, today's appointments, and messages for assigned patients |
| `POST` | `/auth/clinics/{clinic_id}/nurse/visits/{visit_id}/vitals` | Nurse | Record validated vital observations for an assigned patient during an active visit |
| `GET` | `/auth/clinics/{clinic_id}/nurse/patients/{patient_id}/vitals` | Nurse | Read vital history for an assigned patient |
| `GET` | `/auth/clinics/{clinic_id}/billing/dashboard` | Billing staff | View claim counts and total claim amounts |
| `GET` | `/auth/clinics/{clinic_id}/billing/claims` | Billing staff | Search and filter clinic claims |
| `POST` | `/auth/clinics/{clinic_id}/billing/claims` | Billing staff | Draft a claim for a visit with a signed note |
| `GET` | `/auth/clinics/{clinic_id}/billing/claims/{claim_id}` | Billing staff | Read one clinic claim |
| `PATCH` | `/auth/clinics/{clinic_id}/billing/claims/{claim_id}` | Billing staff | Edit a draft or rejected claim |
| `POST` | `/auth/clinics/{clinic_id}/billing/claims/{claim_id}/submit` | Billing staff | Queue a signed-visit claim for submission |
| `GET` | `/auth/clinics/{clinic_id}/reception/dashboard` | Receptionist | View the clinic-day appointment schedule and counts |
| `GET` | `/auth/clinics/{clinic_id}/reception/appointments` | Receptionist | Filter the daily appointment schedule |
| `POST` | `/auth/clinics/{clinic_id}/reception/appointments` | Receptionist | Book a patient appointment and optionally assign a doctor |
| `PATCH` | `/auth/clinics/{clinic_id}/reception/appointments/{appointment_id}/reschedule` | Receptionist | Reschedule or reassign a scheduled appointment |
| `POST` | `/auth/clinics/{clinic_id}/reception/appointments/{appointment_id}/cancel` | Receptionist | Cancel a scheduled appointment |
| `POST` | `/auth/clinics/{clinic_id}/reception/appointments/{appointment_id}/check-in` | Receptionist | Check in a patient and create the visit idempotently |
| `GET` | `/auth/clinics/{clinic_id}/reception/waiting-room` | Receptionist | View arrived and in-room patients |
| `POST` | `/auth/clinics/{clinic_id}/reception/visits/{visit_id}/move-to-room` | Receptionist | Move an arrived visit into a room |

Portal appointment booking requires an `Idempotency-Key`, a selected doctor,
and a future timezone-aware interval. Clinic hours, doctor availability, patient,
doctor, and optional room conflicts are checked in clinic-local time. A duplicate
key with the same request returns the existing appointment; reusing it for a
different request returns a conflict. Appointment and `appointment.booked`
outbox event are committed together. Patient messages are stored for in-app staff
review; fixed keyword rules assign a triage level, and incoming messages write
an outbox event for future notification workers. Signed orders are exposed from
the existing orders table; a separate lab-result/document model is not present.
Doctor access to charts is limited to patients assigned through the care team,
appointments, or visits. Visit edits, notes, and orders require an active visit
not assigned to another doctor. Signed notes and orders cannot be edited; order
drafts can be edited or cancelled. Signing a prescription creates its active
medication record, and the doctor can discontinue an active medication.
Recording consent is stored on the visit with the time the decision was
recorded. AI suggestion endpoints review suggestions already stored for a
visit; this backend currently has no Bedrock generation service configured.
Nurse access to patient records requires a clinic-admin care-team assignment.
Patients can message only an active doctor assigned through the care team.
Reception can coordinate with that doctor using staff-only notes; those notes
are stored on the internal message channel and are excluded from patient
conversation reads. Only the assigned doctor or a clinic admin can send a
patient-visible reply. Nurses can review clinic-wide patient messages.
Billing claim submission is queued as an outbox event for the free/demo workflow;
it does not transmit an X12 claim to a clearinghouse.

Patient imports accept UTF-8 CSV columns matching the `patients` fields
(`first_name` and `last_name` are required). Files are stored in the private
`SUPABASE_IMPORT_BUCKET`; the database stores the storage key, checksum, import
cursor, and row errors. Preview is a dry run. Each `/run` call commits one batch
of up to 1,000 rows, so retrying resumes from the saved row cursor. The backend
creates the bucket on first upload; the Supabase server-side secret key must have
Storage Admin access.

Receptionist-created appointments also require an `Idempotency-Key` header.
Patient and receptionist booking requests include `assigned_staff_id`; a patient
may select only a doctor already assigned through the care team. `room_id` is
optional. Configure seven business-hour entries and an effective availability
rule for each doctor before a slot can be booked.

### Platform APIs

All paths require a super-admin account.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/auth/platform/users` | Search/filter accounts with `search`, `is_active`, `limit`, and `offset` |
| `GET` | `/auth/platform/users/{user_id}` | Read an account and its clinic memberships |
| `GET` | `/auth/platform/clinics` | Search/filter clinic tenants with `search`, `is_active`, `limit`, and `offset` |
| `GET` | `/auth/platform/clinics/{clinic_id}` | Read clinic details and member count |
| `GET` | `/auth/platform/clinics/{clinic_id}/members` | List a clinic's users and membership roles |
| `DELETE` | `/auth/platform/clinics/{clinic_id}` | Soft-delete a clinic; confirm with its name |
| `POST` | `/auth/platform/clinics/{clinic_id}/restore` | Restore a clinic; confirm with its name |

Platform deletion preserves records: user and clinic rows are marked inactive
and carry deletion timestamps and the acting admin ID. Clinic clinical data is
retained. Deleted accounts and clinics cannot access APIs; use the explicit
restore routes to undo a deletion.

### Signup and bootstrap

The first clinic owner/admin registers through `/auth/register`; public callers
cannot choose their role. The registering owner is the clinic's initial admin.
There is no super-admin endpoint to invite additional clinic admins. Clinic
admins invite their clinic's doctors, nurses, receptionists, billing staff,
and patients. Patient invitations automatically match the invite email to an
existing patient record in that clinic. The invitation payload does not ask
for a patient ID. Duplicate email matches must be resolved in the patient data
before inviting. Existing users can be added to another clinic through an
invitation without creating a second login account.

For the first platform admin, set a long random `SUPER_ADMIN_BOOTSTRAP_KEY` in
the backend environment and call `POST /auth/bootstrap-super-admin` with the
desired email, password, and full name plus the key in `X-Bootstrap-Key`. The
bootstrap endpoint becomes unavailable once a super-admin profile exists.
Credentials are supplied during this one-time setup; do not commit a shared
super-admin password in source code.

Apply database migrations before starting the API:

```powershell
uv run alembic upgrade head
```

Interactive API documentation is available at `/docs`.

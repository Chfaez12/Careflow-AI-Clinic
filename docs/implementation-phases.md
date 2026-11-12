# CareFlow implementation phases

This plan translates the CareFlow SRS and the project flow discussed in this chat
into implementation work. The SRS is the requirements reference; the explicit
project constraint is to use Floci services only when the account confirms they
are available at no cost, and otherwise choose a free alternative. A service
shown in a dashboard is not considered usable until its API, quota, persistence,
and cost are verified.

Use synthetic patient data throughout the portfolio build. Do not connect paid
AWS services, paid messaging, or production patient data to the free baseline.

## Phase overview

| Phase | Goal | Completion gate |
| --- | --- | --- |
| 0. Free-stack verification | Confirm the runtime, database, storage, identity, and delivery options | Every selected service has a verified free path and a documented fallback |
| 1. Identity and tenant security | Complete sign-up, login, memberships, invitations, and tenant isolation | Each role can sign in and is limited to its clinic and permissions |
| 2. Clinic onboarding and patient import | Configure a clinic and safely import legacy patient data | Admin can validate, preview, and import a synthetic export with an error report |
| 3. Scheduling and appointment events | Build the appointment lifecycle and reliable event handoff | Appointment and `appointment.booked` persist atomically and retries do not duplicate bookings |
| 4. Voice and booking agent | Add phone or browser voice booking with safe fallback | The agent can book through the same API as staff; failure transfers to a human/manual flow |
| 5. Visit, consent, and clinical note | Capture consent and create editable, signed visit notes | No recording starts without logged consent; AI notes remain drafts until doctor sign-off |
| 6. Orders, medication safety, and messages | Add clinician-reviewed prescriptions, lab orders, and patient-message triage | Safety rules and staff approval prevent an AI draft from being sent or signed on its own |
| 7. Patient portal and operational reporting | Complete patient self-service and clinic dashboards | Patients see only linked records; clinic views are tenant-scoped and audited |
| 8. Security, quality, and release | Verify the system against SRS quality and operational requirements | Required tests, tenant-isolation checks, recovery steps, and deployment checks pass |

## Phase 0: verify the free stack

Before building integrations, create a small service inventory for the actual
Floci account. Verify supported APIs, quotas, data persistence, network access,
and whether each service is genuinely included at no cost.

- Confirm the application runtime and PostgreSQL option. Keep Docker Compose as
  the local fallback.
- Confirm Supabase Auth and Postgres configuration for the current login work.
- Check whether Floci provides usable, free object storage and email delivery.
  Otherwise select a free alternative or local demo implementation.
- Treat phone routing, transcription, LLM inference, and text-to-speech as
  optional integrations. If Chime, Transcribe, Bedrock, or Polly are unavailable
  without charge, use the browser voice demo with local/open-source components
  or deterministic mock responses.
- Record the selected implementation and fallback for every integration before
  the next phase depends on it.

**Deliverable:** a short service matrix with `verified`, `not available`, or
`needs local demo` for each component, plus a runnable local backend/database.

## Phase 1: identity and tenant security

Build the role-aware account foundation used by every later API.

- Apply the Supabase-linked `users` table and clinic-scoped membership
  migration. Keep credentials in Supabase Auth; keep CareFlow roles in trusted
  database records.
- Complete clinic-admin sign-up, login, refresh, logout, password recovery,
  staff invitations, invitation acceptance, and patient access invitations.
- Support platform super-admin, clinic admin, doctor, nurse, receptionist,
  billing staff, and patient roles. Do not accept privileged roles from public
  sign-up input.
- Enforce clinic membership in FastAPI and prevent direct public Data API access
  to tenant tables. Add audit records for sensitive reads and writes.

**Deliverable:** migrations applied; a documented sign-in and invitation flow;
role checks verified for cross-clinic access attempts.

**Current status:** the account models, role-aware routes, repositories, and
Alembic migration are in the codebase. The migration still needs to be applied
to the configured database, and the flows need integration testing before this
phase is complete.

## Phase 2: clinic onboarding and patient import

- Add clinic setup fields and an onboarding checklist for staff, rooms, schedule
  templates, and integrations.
- Add import-job and import-error records. Keep the actual export file in the
  verified free object store; store its object key, owner, status, and checksum
  in Postgres.
- Support CSV first: validate columns, preview matches and duplicates, run a
  dry-run, then import in batches with resumable status and an error report.
- Keep imported records scoped to the uploading clinic and log import actions.

**Deliverable:** a clinic admin can upload a synthetic legacy export, preview
the result, and import it without creating cross-tenant records.

## Phase 3: scheduling and appointment events

- Add doctor availability, rooms, and clinic scheduling rules. Enforce
  double-booking prevention in the database transaction.
- Implement create, view, reschedule, and cancel operations for receptionists,
  clinic admins, and patients according to role permissions.
- Save an appointment and its `appointment.booked` outbox event in one
  transaction. Add idempotency keys so a retry cannot create a second booking.
- Start with in-app notifications and local email capture. Add external delivery
  only if a verified free provider exists.

**Deliverable:** staff and patient booking use the same API; a failed event
consumer can retry without losing or duplicating the appointment.

## Phase 4: voice and booking agent

- First ship the browser voice demo and a deterministic fallback. Keep phone
  number setup behind a provider interface until Floci's free telephony support
  is proven.
- Connect the agent to the existing appointment APIs rather than allowing it to
  write directly to tables.
- Use the selected free speech/model path only after the Phase 0 verification.
  The fallback should route to staff, voicemail, or manual booking when a
  provider is unavailable.
- Restrict the agent to identity checks and appointment actions. It must not
  diagnose, recommend medicine or doses, or reveal clinical record contents.
- Add red-flag emergency guidance and human handoff rules.

**Deliverable:** a synthetic caller can book, reschedule, and cancel; a provider
failure still leaves a clear manual workflow.

## Phase 5: visit, consent, and clinical note

- Add the doctor visit screen and visit lifecycle.
- Capture the consent decision, time, actor, and recording purpose before any
  audio is captured. Store audio/transcript object references and retention
  metadata rather than putting large files in Postgres.
- Stream audio to the chosen free transcription path, or use a local/demo
  transcription implementation.
- Generate a clinic-template note as a versioned `DRAFT`; let the doctor edit it
  and record an authenticated sign-off. Keep signed versions immutable and
  corrections as amendments.
- Add audit events for audio access, transcription, note edits, and sign-off.

**Deliverable:** no audio starts without logged consent; failed AI processing
does not block the manual visit; no note is filed without doctor signature.

## Phase 6: orders, medication safety, and messages

- Draft prescriptions and lab orders from a signed visit context, but require
  clinician approval before sign, send, or submit actions.
- Implement deterministic allergy, interaction, duplicate-therapy, and dose
  checks. Do not make safety decisions with an LLM alone.
- Add patient messages with emergency, urgent, routine, and administrative
  triage, staff queues, assignment, approval, and response history.
- Treat a patient saying a medicine causes dizziness as a safety-relevant
  message: route it promptly to clinical staff and escalate immediately if
  emergency symptoms are reported. The AI should not advise the patient to
  change or stop a medication.
- Start with in-app messaging and simulated pharmacy/lab integrations unless a
  verified free sandbox/provider exists.

**Deliverable:** staff can review and respond to patient messages; unsigned AI
orders and unapproved replies cannot be sent.

## Phase 7: patient portal and operational reporting

- Expand the patient portal to appointment management, messages, signed results,
  and prescriptions linked to the patient's verified clinic membership.
- Add staff dashboards for scheduling, visit status, and work queues. Add
  owner-level reporting with aggregated clinic data only.
- Keep all portal and dashboard reads tenant-scoped and audited.
- Add claims and remittance as simulated workflows for the free portfolio
  version; do not connect a real clearinghouse without separate approval and
  funded access.

**Deliverable:** patients can access only their own linked data, and clinic
owners see aggregated metrics for their clinic.

## Phase 8: security, quality, and release

- Add automated tests for high-priority requirements, tenant isolation,
  invitations, audit events, idempotency, sign-off, and safe
  provider failure. Target the SRS coverage goal for backend domain logic.
- Run dependency and container scans; verify CORS, secrets, RLS, permissions,
  and logs do not expose credentials or patient data.
- Test backup and restore for the selected free database tier. Document its
  actual retention and availability limits rather than claiming unsupported
  production targets.
- Deploy only to a runtime verified in Phase 0. Keep synthetic data in the
  portfolio deployment and label simulated integrations clearly.

**Deliverable:** repeatable setup and deployment instructions, passing release
checks, and an explicit list of free-tier limitations.

## Dependency order

```text
0 Free-stack verification
  -> 1 Identity and tenant security
  -> 2 Clinic onboarding and import
  -> 3 Scheduling and appointment events
  -> 4 Voice booking agent
  -> 5 Visit and signed note
  -> 6 Orders, medication safety, and messages
  -> 7 Patient portal and reporting
  -> 8 Security and release gate
```

Phases 2 and 3 can be developed in parallel after Phase 1. The voice provider
work in Phase 4 must not block staff booking or the manual clinical workflow.

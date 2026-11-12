from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.audit_log import router as audit_log_router
from app.api.billing_portal import router as billing_portal_router
from app.api.care_team import router as care_team_router
from app.api.clinic_members import router as clinic_members_router
from app.api.clinic_messages import router as clinic_messages_router
from app.api.clinic_setup import router as clinic_setup_router
from app.api.doctor_portal import router as doctor_portal_router
from app.api.patient_imports import router as patient_imports_router
from app.api.patient_portal import router as patient_portal_router
from app.api.nurse_portal import router as nurse_portal_router
from app.api.patients import router as patients_router
from app.api.platform_admin import router as platform_admin_router
from app.api.receptionist_portal import router as receptionist_portal_router
from app.api.scheduling import router as scheduling_router
from app.core.config import settings

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Bootstrap-Key", "Idempotency-Key"],
)

app.include_router(auth_router)
app.include_router(audit_log_router)
app.include_router(clinic_members_router)
app.include_router(clinic_messages_router)
app.include_router(clinic_setup_router)
app.include_router(patient_imports_router)
app.include_router(scheduling_router)
app.include_router(doctor_portal_router)
app.include_router(care_team_router)
app.include_router(patient_portal_router)
app.include_router(patients_router)
app.include_router(nurse_portal_router)
app.include_router(billing_portal_router)
app.include_router(receptionist_portal_router)
app.include_router(platform_admin_router)



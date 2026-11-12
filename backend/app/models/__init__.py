from app.models.base import Base
from app.models.clinic import Clinic
from app.models.staff_member import StaffMember
from app.models.patient import Patient
from app.models.audit_event import AuditEvent
from app.models.appointment import Appointment
from app.models.care_team_assignment import CareTeamAssignment
from app.models.allergy import Allergy
from app.models.medication import Medication
from app.models.message import Message
from app.models.visit import Visit
from app.models.clinical_note import ClinicalNote
from app.models.order import Order
from app.models.claim import Claim
from app.models.ai_suggestion import AISuggestion
from app.models.outbox_event import OutboxEvent
# Register Supabase's Auth table stub before the public profile foreign key.
from app.models.auth_user_reference import auth_users_table
from app.models.user import UserProfile
from app.models.clinic_membership import ClinicMembership
from app.models.patient_vital import PatientVital
from app.models.medical_condition import MedicalCondition
from app.models.clinic_business_hour import ClinicBusinessHour
from app.models.clinic_room import ClinicRoom
from app.models.doctor_availability import DoctorAvailability
from app.models.patient_import_job import PatientImportJob
from app.models.patient_import_error import PatientImportError
from app.models.waitlist_entry import WaitlistEntry

__all__ = ["Base", "Clinic", "StaffMember", "Patient", "AuditEvent", "Appointment",
"CareTeamAssignment", "Allergy", "Medication", "Message", "Visit", "ClinicalNote",
"Order", "Claim", "AISuggestion", "OutboxEvent", "UserProfile", "ClinicMembership", "PatientVital", "MedicalCondition",
"ClinicBusinessHour", "ClinicRoom", "DoctorAvailability", "PatientImportJob", "PatientImportError", "WaitlistEntry"]

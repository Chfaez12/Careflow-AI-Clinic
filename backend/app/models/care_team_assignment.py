from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base
class CareTeamAssignment(Base):
    __tablename__="care_team_assignments"
    __table_args__=(UniqueConstraint("patient_id","staff_member_id",name="uq_care_team_patient_staff"),)
    id: Mapped[UUID]=mapped_column(PGUUID(as_uuid=True), default=uuid4, server_default=func.gen_random_uuid(), primary_key=True)
    clinic_id: Mapped[UUID]=mapped_column(PGUUID(as_uuid=True), ForeignKey("clinics.id",ondelete="CASCADE"),index=True,nullable=False)
    patient_id: Mapped[UUID]=mapped_column(PGUUID(as_uuid=True), ForeignKey("patients.id",ondelete="CASCADE"),index=True,nullable=False)
    staff_member_id: Mapped[UUID]=mapped_column(PGUUID(as_uuid=True), ForeignKey("staff_members.id",ondelete="CASCADE"),index=True,nullable=False)
    assignment_role: Mapped[str]=mapped_column(String(50),default="care_team",nullable=False)
    assigned_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now(),nullable=False)

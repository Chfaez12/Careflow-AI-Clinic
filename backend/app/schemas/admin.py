from pydantic import BaseModel, EmailStr, Field


class DeleteUserRequest(BaseModel):
    confirm_email: EmailStr


class DeleteClinicRequest(BaseModel):
    confirm_clinic_name: str = Field(min_length=2, max_length=150)

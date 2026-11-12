
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "CareFlow AI"
    environment: str = "development"

    database_url: str

    supabase_url: str
    supabase_publishable_key: str
    supabase_secret_key: SecretStr
    supabase_import_bucket: str = "careflow-patient-imports"
    super_admin_bootstrap_key: SecretStr | None = None

    floci_s3_endpoint_url: str
    floci_s3_region: str = "us-east-1"
    floci_s3_bucket: str = "patients"
    floci_s3_access_key_id: SecretStr
    floci_s3_secret_access_key: SecretStr
    floci_s3_session_token: SecretStr | None = None
    floci_s3_legacy_supabase_read: bool = True

    supabase_jwks_url: str | None = None

    frontend_url: str = "http://localhost:3000"
    cors_origins: str = "http://localhost:3000"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def jwt_jwks_url(self) -> str:
        if self.supabase_jwks_url:
            return self.supabase_jwks_url

        return (
            f"{self.supabase_url.rstrip('/')}"
            "/auth/v1/.well-known/jwks.json"
        )

def get_settings() -> Settings:
    return Settings()


settings = get_settings()

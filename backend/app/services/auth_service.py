import asyncio

import httpx
from fastapi import HTTPException, status
from supabase import create_client
from supabase.lib.client_options import SyncClientOptions

from app.core.config import settings


async def auth_request(path: str, *, method: str = "POST", payload: dict | None = None,access_token: str | None = None) -> dict:
    headers = {"apikey": settings.supabase_publishable_key,"Content-Type": "application/json"}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.request(
                method,
                f"{settings.supabase_url.rstrip('/')}/auth/v1/{path.lstrip('/')}",
                headers=headers,
                json=payload,
            )
    except httpx.RequestError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Authentication service is temporarily unavailable.") from exc

    try:
        data = response.json() if response.content else {}
    except ValueError:
        data = {}
    if not isinstance(data, dict):
        data = {}

    if not response.is_success:
        message = (data.get("msg") or data.get("message") or data.get("error_description")
                   or data.get("error") or "Authentication request failed.")
        mapped_status = response.status_code
        if mapped_status >= 500:
            mapped_status = status.HTTP_502_BAD_GATEWAY
            message = "Authentication service returned an error."
        raise HTTPException(status_code=mapped_status, detail=message)

    return data if isinstance(data, dict) else {}


async def get_supabase_user(access_token: str) -> dict:
    return await auth_request("user", method="GET", access_token=access_token)


def _admin_client():
    return create_client(
        settings.supabase_url,
        settings.supabase_secret_key.get_secret_value(),
        options=SyncClientOptions(auto_refresh_token=False, persist_session=False),
    )


def _extract_admin_user(result) -> dict:
    user = getattr(result, "user", None)
    if user is None:
        data = getattr(result, "data", None)
        user = getattr(data, "user", None)
    if user is None and isinstance(result, dict):
        user = result.get("user", result)
    if user is None:
        raise HTTPException(status_code=502, detail="Supabase Auth returned no user record.")
    if hasattr(user, "model_dump"):
        return user.model_dump(mode="json")
    if hasattr(user, "dict"):
        return user.dict()
    return dict(user)


async def invite_auth_user(email: str, *, full_name: str, redirect_to: str) -> dict:
    """Invite an account using Supabase's server-only Auth Admin API."""
    def invite():
        result = _admin_client().auth.admin.invite_user_by_email(
            email,
            options={"data": {"full_name": full_name}, "redirect_to": redirect_to},
        )
        return _extract_admin_user(result)

    try:
        return await asyncio.to_thread(invite)
    except HTTPException:
        raise
    except Exception as exc:
        message = getattr(exc, "message", None) or str(exc)
        message = str(message).strip()
        error_code = str(getattr(exc, "code", "") or "").strip()
        upstream_status = getattr(exc, "status", None)
        combined = f"{error_code} {message}".lower()

        if upstream_status == 429 or "rate limit" in combined or "too many requests" in combined:
            raise HTTPException(
                status_code=429,
                detail="Supabase email invitation limit reached. Wait before sending another invite.",
            ) from exc
        if "redirect" in combined and ("allow" in combined or "url" in combined):
            raise HTTPException(
                status_code=400,
                detail="Supabase rejected the invitation redirect URL. Add the configured frontend URL to Supabase Auth's allowed redirect URLs.",
            ) from exc
        if "already registered" in combined or "already exists" in combined or error_code == "email_exists":
            raise HTTPException(
                status_code=409,
                detail="This email already has a Supabase Auth account. Sign in with that account or resolve its existing CareFlow profile before inviting it.",
            ) from exc
        if upstream_status in {401, 403}:
            raise HTTPException(
                status_code=502,
                detail="Supabase rejected the Auth Admin request. Verify SUPABASE_SECRET_KEY is the project's server-side secret key.",
            ) from exc
        if message:
            # Supabase Auth error messages do not include the configured API key.
            safe_message = message[:300]
            raise HTTPException(
                status_code=502,
                detail=f"Supabase invitation failed: {safe_message}",
            ) from exc
        raise HTTPException(
            status_code=502,
            detail="Supabase invitation failed without an Auth error message. Check the backend's Supabase URL, server-side key, and email provider configuration.",
        ) from exc


async def delete_auth_user(user_id: str) -> None:
    """Best-effort cleanup if local account provisioning fails."""
    def delete():
        _admin_client().auth.admin.delete_user(user_id)

    try:
        await asyncio.to_thread(delete)
    except Exception:
        return

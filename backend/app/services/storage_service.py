"""Private Floci S3 storage for patient import files."""

import hashlib
import hmac
from datetime import datetime, timezone
from urllib.parse import quote, urlsplit

import httpx
from fastapi import HTTPException

from app.core.config import settings


class FlociS3StorageService:
    """Minimal S3 SigV4 client for private patient-import objects."""

    def __init__(self):
        self.endpoint = settings.floci_s3_endpoint_url.rstrip("/")
        self.bucket = settings.floci_s3_bucket
        self.region = settings.floci_s3_region
        self.access_key_id = settings.floci_s3_access_key_id.get_secret_value()
        self.secret_access_key = settings.floci_s3_secret_access_key.get_secret_value()
        self.session_token = (
            settings.floci_s3_session_token.get_secret_value()
            if settings.floci_s3_session_token else None
        )

    @staticmethod
    def _signing_key(secret: str, date_stamp: str, region: str) -> bytes:
        def sign(key: bytes, value: str) -> bytes:
            return hmac.new(key, value.encode("utf-8"), hashlib.sha256).digest()

        date_key = sign(("AWS4" + secret).encode("utf-8"), date_stamp)
        region_key = sign(date_key, region)
        service_key = sign(region_key, "s3")
        return sign(service_key, "aws4_request")

    def _signed_headers(self, method: str, key: str, body: bytes, content_type: str | None) -> tuple[str, dict[str, str]]:
        parsed = urlsplit(self.endpoint)
        host = parsed.netloc.lower()
        encoded_key = quote(key, safe="/")
        canonical_uri = f"{parsed.path.rstrip('/')}/{quote(self.bucket, safe='')}/{encoded_key}"
        if not canonical_uri.startswith("/"):
            canonical_uri = "/" + canonical_uri
        url = f"{self.endpoint}/{quote(self.bucket, safe='')}/{encoded_key}"

        now = datetime.now(timezone.utc)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")
        payload_hash = hashlib.sha256(body).hexdigest()
        headers = {
            "Host": host,
            "x-amz-content-sha256": payload_hash,
            "x-amz-date": amz_date,
        }
        if content_type:
            headers["Content-Type"] = content_type
        if self.session_token:
            headers["x-amz-security-token"] = self.session_token

        normalized = {name.lower(): " ".join(value.strip().split()) for name, value in headers.items()}
        signed_names = ";".join(sorted(normalized))
        canonical_headers = "".join(f"{name}:{normalized[name]}\n" for name in sorted(normalized))
        canonical_request = "\n".join((
            method,
            canonical_uri,
            "",
            canonical_headers,
            signed_names,
            payload_hash,
        ))
        scope = f"{date_stamp}/{self.region}/s3/aws4_request"
        string_to_sign = "\n".join((
            "AWS4-HMAC-SHA256",
            amz_date,
            scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ))
        signature = hmac.new(
            self._signing_key(self.secret_access_key, date_stamp, self.region),
            string_to_sign.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        headers["Authorization"] = (
            f"AWS4-HMAC-SHA256 Credential={self.access_key_id}/{scope}, "
            f"SignedHeaders={signed_names}, Signature={signature}"
        )
        return url, headers

    async def _request(self, method: str, storage_key: str, *, body: bytes = b"", content_type: str | None = None) -> httpx.Response:
        url, headers = self._signed_headers(method, storage_key, body, content_type)
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                return await client.request(method, url, headers=headers, content=body)
        except httpx.RequestError as exc:
            raise HTTPException(status_code=503, detail="Floci S3 is temporarily unavailable.") from exc

    async def upload_import(self, storage_key: str, data: bytes) -> None:
        response = await self._request("PUT", storage_key, body=data, content_type="text/csv")
        if not response.is_success:
            raise HTTPException(status_code=502, detail="Could not store the patient import file in Floci S3.")

    async def download_import(self, storage_key: str) -> bytes:
        response = await self._request("GET", storage_key)
        if response.status_code == 404:
            if settings.floci_s3_legacy_supabase_read:
                legacy = await self._download_legacy_supabase_import(storage_key)
                if legacy is not None:
                    return legacy
            raise HTTPException(status_code=410, detail="The stored import file is no longer available.")
        if not response.is_success:
            raise HTTPException(status_code=502, detail="Could not read the patient import file from Floci S3.")
        return response.content

    async def _download_legacy_supabase_import(self, storage_key: str) -> bytes | None:
        """Keep existing import jobs usable while their objects remain in Supabase Storage."""
        base_url = f"{settings.supabase_url.rstrip('/')}/storage/v1"
        encoded_key = quote(storage_key, safe="/")
        key = settings.supabase_secret_key.get_secret_value()
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.get(
                    f"{base_url}/object/authenticated/{quote(settings.supabase_import_bucket, safe='')}/{encoded_key}",
                    headers={"apikey": key, "Authorization": f"Bearer {key}"},
                )
            if response.status_code == 404:
                return None
            if not response.is_success:
                raise HTTPException(status_code=502, detail="Could not read a legacy patient import file.")
            return response.content
        except httpx.RequestError as exc:
            raise HTTPException(status_code=503, detail="Legacy Supabase Storage is temporarily unavailable.") from exc

    async def delete_import(self, storage_key: str) -> None:
        response = await self._request("DELETE", storage_key)
        if response.status_code not in {200, 204, 404}:
            raise HTTPException(status_code=502, detail="Could not remove the patient import file from Floci S3.")

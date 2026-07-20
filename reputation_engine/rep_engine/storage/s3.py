"""
S3-compatible object-storage backend (Phase G.3).
=================================================
ONE backend for every S3-API store the project targets:
  - Railway Buckets  (private, Tigris-backed, custom endpoint, path-style) -- the default target
  - Cloudflare R2    (custom endpoint; public via a bound domain -> set public_base_url)
  - AWS S3           (public via public_base_url/CloudFront, else presigned)
  - MinIO (self-host on Railway) -- same S3 API

Uses boto3 with s3v4 signing + PATH-STYLE addressing so it works against any custom endpoint (the
virtual-hosted style AWS default breaks on Railway/R2/MinIO endpoints). boto3 is imported lazily so
`rep_engine.storage.base` stays importable (and `configured()` works) even where boto3 isn't
installed / storage is unused. PRIVATE by default: Railway Buckets have no public object URLs, so
delivery is a presigned GET (bounded jobs) or the authenticated backend proxy; a permanent public
URL is produced only when public_base_url is configured.
"""

from __future__ import annotations

import logging

from .base import Storage, StorageError, register

log = logging.getLogger("rep_engine.storage.s3")

# Not-found codes across S3 implementations for a HEAD/GET miss.
_NOT_FOUND = {"404", "NoSuchKey", "NotFound", "NoSuchBucket"}


@register("s3")
@register("r2")
@register("railway")
@register("minio")
class S3CompatStorage(Storage):
    """boto3-backed S3-compatible storage. See module docstring for the providers it serves."""

    def __init__(self, config: dict):
        super().__init__(config)
        try:
            import boto3
            from botocore.config import Config as BotoConfig
        except ImportError as e:  # pragma: no cover -- surfaced only when storage is actually used
            raise StorageError(
                "object storage requires boto3 (add boto3 to requirements / pip install boto3)") from e
        access = config.get("access_key", "")
        secret = config.get("secret_key", "")
        if not (access and secret):
            raise StorageError("storage requires access_key and secret_key.")
        self.endpoint = (config.get("endpoint") or "").rstrip("/") or None
        self.region = config.get("region") or "us-east-1"
        self._client = boto3.client(
            "s3",
            endpoint_url=self.endpoint,
            aws_access_key_id=access,
            aws_secret_access_key=secret,
            region_name=self.region,
            config=BotoConfig(
                signature_version="s3v4",
                s3={"addressing_style": "path"},   # path-style: works on Railway/R2/MinIO endpoints
                retries={"max_attempts": 3, "mode": "standard"},
            ),
        )

    def _put(self, key: str, data: bytes, content_type: str) -> None:
        try:
            self._client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)
        except Exception as e:  # noqa: BLE001
            raise StorageError(f"put_object failed for {self.bucket}/{key}: {e}") from e

    def _head(self, key: str) -> dict | None:
        from botocore.exceptions import ClientError
        try:
            r = self._client.head_object(Bucket=self.bucket, Key=key)
            return {"size": r.get("ContentLength"), "content_type": r.get("ContentType"),
                    "etag": r.get("ETag")}
        except ClientError as e:
            code = str(e.response.get("Error", {}).get("Code", ""))
            status = e.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if code in _NOT_FOUND or status == 404:
                return None   # genuinely not there -- NOT an error
            raise StorageError(f"head_object failed for {self.bucket}/{key}: {e}") from e
        except Exception as e:  # noqa: BLE001
            raise StorageError(f"head_object failed for {self.bucket}/{key}: {e}") from e

    def _get(self, key: str) -> bytes:
        try:
            r = self._client.get_object(Bucket=self.bucket, Key=key)
            return r["Body"].read()
        except Exception as e:  # noqa: BLE001
            raise StorageError(f"get_object failed for {self.bucket}/{key}: {e}") from e

    def _delete(self, key: str) -> None:
        try:
            self._client.delete_object(Bucket=self.bucket, Key=key)
        except Exception as e:  # noqa: BLE001
            raise StorageError(f"delete_object failed for {self.bucket}/{key}: {e}") from e

    def presigned_get(self, key: str, expires_seconds: int = 3600) -> str:
        try:
            return self._client.generate_presigned_url(
                "get_object", Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=int(expires_seconds))
        except Exception as e:  # noqa: BLE001
            raise StorageError(f"could not presign {self.bucket}/{key}: {e}") from e

    def validate(self) -> tuple[bool, str]:
        """HEAD the bucket -- proves the endpoint + credentials + bucket are all reachable."""
        try:
            self._client.head_bucket(Bucket=self.bucket)
            return True, f"reached bucket {self.bucket} at {self.endpoint or 's3'}"
        except Exception as e:  # noqa: BLE001
            return False, f"could not reach bucket {self.bucket}: {e}"

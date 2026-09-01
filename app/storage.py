import logging
import mimetypes
import time
from pathlib import Path
from urllib.parse import urlsplit

import boto3
from botocore.config import Config

log = logging.getLogger(__name__)


class Storage:
    def __init__(
        self,
        endpoint: str,
        region: str,
        bucket: str,
        access_key: str,
        secret_key: str,
        ttl: int,
        public_base_url: str = "",
    ):
        if not bucket:
            raise ValueError("STORAGE_BUCKET is required")
        self.bucket = bucket
        self.ttl = ttl
        self.public_base_url = public_base_url.rstrip("/")
        self.endpoint = endpoint.rstrip("/")
        configured_region = (region or "eu-west-1").strip()
        endpoint_host = (urlsplit(self.endpoint).hostname or "").lower()

        # Filone's S3 endpoint uses a concrete regional gateway for signed
        # object requests. Keep existing STORAGE_REGION=auto deployments
        # compatible by signing those requests for the endpoint's region.
        if configured_region == "auto" and endpoint_host.endswith(".s3.filonecontent.com"):
            self.region = "eu-west-1"
            log.info(
                "storage:region_normalized configured=%s effective=%s reason=filone_s3_endpoint",
                configured_region,
                self.region,
            )
        else:
            self.region = configured_region

        self.client = boto3.client(
            "s3",
            endpoint_url=self.endpoint or None,
            region_name=self.region,
            aws_access_key_id=access_key or None,
            aws_secret_access_key=secret_key or None,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
            ),
        )
        log.info(
            "storage:init bucket=%s endpoint=%s region=%s presigned_ttl=%ss public_base_url=%s",
            self.bucket,
            self.endpoint or "default",
            self.region,
            self.ttl,
            bool(self.public_base_url),
        )

    def upload(self, path: Path, key: str) -> str:
        started = time.monotonic()
        size = path.stat().st_size
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        log.info(
            "storage:upload:start bucket=%s key=%s size=%d content_type=%s",
            self.bucket,
            key,
            size,
            content_type,
        )
        try:
            self.client.upload_file(
                str(path),
                self.bucket,
                key,
                ExtraArgs={
                    "ContentType": content_type,
                    "ContentDisposition": "inline",
                },
            )
            if self.public_base_url:
                link = f"{self.public_base_url}/{key}"
                link_type = "public"
            else:
                link = self.client.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": self.bucket, "Key": key},
                    ExpiresIn=self.ttl,
                )
                link_type = "presigned"
                # Never log the signed URL: it contains authentication data.
                log.info(
                    "storage:presigned:created bucket=%s key=%s ttl=%ss endpoint=%s region=%s",
                    self.bucket,
                    key,
                    self.ttl,
                    self.endpoint,
                    self.region,
                )
            log.info(
                "storage:upload:success bucket=%s key=%s link_type=%s content_type=%s elapsed=%.2fs",
                self.bucket,
                key,
                link_type,
                content_type,
                time.monotonic() - started,
            )
            return link
        except Exception:
            log.exception(
                "storage:upload:failed bucket=%s key=%s elapsed=%.2fs",
                self.bucket,
                key,
                time.monotonic() - started,
            )
            raise

    def delete(self, key: str) -> None:
        log.info("storage:delete:start bucket=%s key=%s", self.bucket, key)
        self.client.delete_object(Bucket=self.bucket, Key=key)
        log.info("storage:delete:success bucket=%s key=%s", self.bucket, key)

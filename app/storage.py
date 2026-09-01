import logging
import time
from pathlib import Path

import boto3

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
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint or None,
            region_name=region or None,
            aws_access_key_id=access_key or None,
            aws_secret_access_key=secret_key or None,
        )
        log.info(
            "storage:init bucket=%s region=%s presigned_ttl=%ss public_base_url=%s",
            self.bucket,
            region or "default",
            self.ttl,
            bool(self.public_base_url),
        )

    def upload(self, path: Path, key: str) -> str:
        started = time.monotonic()
        size = path.stat().st_size
        log.info("storage:upload:start bucket=%s key=%s size=%d", self.bucket, key, size)
        try:
            self.client.upload_file(str(path), self.bucket, key)
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
            log.info(
                "storage:upload:success bucket=%s key=%s link_type=%s elapsed=%.2fs",
                self.bucket,
                key,
                link_type,
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

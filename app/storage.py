from pathlib import Path
import boto3


class Storage:
    def __init__(self, endpoint: str, region: str, bucket: str, access_key: str, secret_key: str, ttl: int, public_base_url: str = ""):
        if not bucket:
            raise ValueError("STORAGE_BUCKET is required")
        self.bucket = bucket
        self.ttl = ttl
        self.public_base_url = public_base_url.rstrip("/")
        self.client = boto3.client("s3", endpoint_url=endpoint or None, region_name=region or None,
                                   aws_access_key_id=access_key or None, aws_secret_access_key=secret_key or None)

    def upload(self, path: Path, key: str) -> str:
        self.client.upload_file(str(path), self.bucket, key)
        if self.public_base_url:
            return f"{self.public_base_url}/{key}"
        return self.client.generate_presigned_url("get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=self.ttl)

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

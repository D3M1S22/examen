"""Build the EXAMEN release bundle and upload it to S3 (docs/17_aws_deployment_runbook.md §5.1).

The bundle holds the committed code (``git archive HEAD``), the built dashboard (``src/web_ui/out``)
and the Bee CLI for linux-x64 (``bin/bee``). It goes to ``s3://<bucket>/bundles/<sha>.tgz`` and is
copied to ``bundles/current.tgz``, which the instance installs (``deploy/aws/host.sh``).

    .venv/bin/python scripts/aws_bundle.py [--bucket examen-artifacts-<acct>-euc1] [--skip-ui]
"""

import argparse
import io
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.core.config import settings  # noqa: E402

BEE = ROOT / "resources" / "bee-cli" / "dist" / "platforms" / "linux-x64" / "bee"
REGION = "eu-central-1"


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def _session():
    import boto3

    creds = {}
    if settings.aws_access_key_id and settings.aws_secret_access_key:
        creds = {"aws_access_key_id": settings.aws_access_key_id,
                 "aws_secret_access_key": settings.aws_secret_access_key,
                 "aws_session_token": settings.aws_session_token}
    return boto3.session.Session(region_name=REGION, **creds)


def ensure_bucket(s3, bucket: str) -> None:
    try:
        s3.head_bucket(Bucket=bucket)
        return
    except Exception:
        pass
    s3.create_bucket(Bucket=bucket, CreateBucketConfiguration={"LocationConstraint": REGION})
    s3.put_public_access_block(Bucket=bucket, PublicAccessBlockConfiguration={
        "BlockPublicAcls": True, "IgnorePublicAcls": True, "BlockPublicPolicy": True, "RestrictPublicBuckets": True})
    s3.put_bucket_encryption(Bucket=bucket, ServerSideEncryptionConfiguration={
        "Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]})
    s3.put_bucket_lifecycle_configuration(Bucket=bucket, LifecycleConfiguration={"Rules": [{
        "ID": "old-bundles", "Status": "Enabled", "Filter": {"Prefix": "bundles/"},
        "Expiration": {"Days": 30}}]})
    s3.put_bucket_tagging(Bucket=bucket, Tagging={"TagSet": [{"Key": "project", "Value": "examen"}]})
    print(f"Created bucket {bucket}")


def build_bundle(sha: str, out: Path, skip_ui: bool) -> None:
    if not skip_ui:
        subprocess.check_call(["bash", "scripts/build_ui.sh"], cwd=ROOT)
    if not (ROOT / "src" / "web_ui" / "out" / "index.html").exists():
        raise SystemExit("Dashboard build missing (src/web_ui/out)")
    if not BEE.exists():
        raise SystemExit(f"Bee CLI missing: {BEE}")
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "code.tar"
        subprocess.check_call(["git", "archive", "--format=tar", "-o", str(archive), "HEAD"], cwd=ROOT)
        with tarfile.open(archive) as code, tarfile.open(out, "w:gz") as bundle:
            for member in code.getmembers():
                if member.name.startswith("resources/"):
                    continue
                bundle.addfile(member, code.extractfile(member) if member.isfile() else None)
            bundle.add(ROOT / "src" / "web_ui" / "out", arcname="src/web_ui/out")
            bundle.add(BEE, arcname="bin/bee")
            stamp = sha.encode()
            info = tarfile.TarInfo("BUNDLE_SHA")
            info.size = len(stamp)
            bundle.addfile(info, io.BytesIO(stamp))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--bucket", default=None)
    parser.add_argument("--skip-ui", action="store_true")
    args = parser.parse_args()
    session = _session()
    account = session.client("sts").get_caller_identity()["Account"]
    bucket = args.bucket or f"examen-artifacts-{account}-euc1"
    if _git("status", "--porcelain", "--untracked-files=no"):
        print("Warning: uncommitted changes are NOT in the bundle (it is built from HEAD)")
    sha = _git("rev-parse", "--short=12", "HEAD")
    s3 = session.client("s3")
    ensure_bucket(s3, bucket)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"{sha}.tgz"
        build_bundle(sha, path, args.skip_ui)
        size = os.path.getsize(path) / 1e6
        s3.upload_file(str(path), bucket, f"bundles/{sha}.tgz")
        s3.copy_object(Bucket=bucket, Key="bundles/current.tgz", CopySource={"Bucket": bucket, "Key": f"bundles/{sha}.tgz"})
    print(f"Uploaded s3://{bucket}/bundles/{sha}.tgz ({size:.1f} MB) -> bundles/current.tgz")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

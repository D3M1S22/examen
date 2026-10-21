"""Deploy the EXAMEN pipeline to AgentCore Runtime (docs/17_aws_deployment_runbook.md §5.4).

Direct code deployment, no container: the ARM64 dependencies (uv, aarch64-manylinux2014) plus ``src/``
and ``deploy/agentcore/main.py`` are zipped to ``s3://<bucket>/agentcore/<sha>.zip``. The runtime runs
``agent_invocation`` and writes to DynamoDB with tenant-scoped credentials.

    .venv/bin/python scripts/agentcore_deploy.py deploy          # data-stack policy, role stack, package, runtime
    .venv/bin/python scripts/agentcore_deploy.py enable-host     # PIPELINE_MODE=agentcore on the EC2 host
    .venv/bin/python scripts/agentcore_deploy.py disable-host    # back to the in-process pipeline
"""

import argparse
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.aws_bundle import _git, _session  # noqa: E402
from scripts.aws_deploy import deploy_stack, set_host_env  # noqa: E402

RUNTIME_NAME = "examen_pipeline"
REGION = "eu-central-1"


def runtime_env() -> dict:
    from src.core.config import settings

    return {
        "EXAMEN_REMOTE_RUNTIME": "1",
        "AUTH_ENABLED": "true",
        "STORAGE_BACKEND": "dynamo",
        "AUTH_STORE_BACKEND": "dynamo",
        "OPS_STORE_BACKEND": "dynamo",
        "DYNAMO_REGION": REGION,
        "DYNAMO_TABLE_PREFIX": "examen-",
        "DYNAMO_TENANT_ROLE_ARN": "arn:aws:iam::301356686376:role/examen-tenant-data",
        "BEDROCK_REGION": settings.aws_region,
        "GATEKEEPER_PROVIDER": "bedrock",
        "REASONER_PROVIDER": "bedrock",
        "BEDROCK_GATEKEEPER_MODEL": settings.gatekeeper_model_id,
        "BEDROCK_REASONER_MODEL": settings.reasoner_model_id,
        "BEDROCK_EMBEDDING_MODEL": settings.embedding_model_id,
        "EXAMEN_DATA_DIR": "/tmp/examen-data",
        "LOG_LEVEL": "INFO",
    }


def build_package(out: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "pkg"
        subprocess.check_call([
            "uv", "pip", "install", "-q", "--python-platform", "aarch64-manylinux2014", "--python-version", "3.12",
            "--only-binary=:all:", "--target", str(target), "-r", str(ROOT / "deploy" / "agentcore" / "requirements.txt"),
        ])
        shutil.copytree(ROOT / "src", target / "src",
                        ignore=shutil.ignore_patterns("__pycache__", "web_ui", "*.pyc"))
        shutil.copy(ROOT / "deploy" / "agentcore" / "main.py", target / "main.py")
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(target.rglob("*")):
                if path.is_file() and "__pycache__" not in path.parts:
                    zf.write(path, path.relative_to(target).as_posix())


def _find_runtime(control):
    token = None
    while True:
        page = control.list_agent_runtimes(**({"nextToken": token} if token else {}))
        for runtime in page.get("agentRuntimes", []):
            if runtime["agentRuntimeName"] == RUNTIME_NAME:
                return runtime
        token = page.get("nextToken")
        if not token:
            return None


def cmd_deploy(session, args) -> int:
    account = session.client("sts").get_caller_identity()["Account"]
    bucket = f"examen-artifacts-{account}-euc1"
    # 1. Shared ops partitions for the runtime (events, settings) live in the data stack's AgentCore policy
    deploy_stack(session, "examen-data", ROOT / "deploy" / "aws" / "dynamodb.yaml", {},
                 keep_previous=("Prefix", "RuntimeRoleName", "RuntimeUserName", "AgentCoreRoleName", "AlarmEmail"))
    # 2. Execution role
    role_arn = deploy_stack(session, "examen-agentcore", ROOT / "deploy" / "aws" / "agentcore.yaml",
                            {"ArtifactBucket": bucket})["ExecutionRoleArn"]
    # 3. Package
    sha = _git("rev-parse", "--short=12", "HEAD")
    key = f"agentcore/{sha}.zip"
    with tempfile.TemporaryDirectory() as tmp:
        zpath = Path(tmp) / "pipeline.zip"
        print("Building the ARM64 package...")
        build_package(zpath)
        print(f"Package {zpath.stat().st_size / 1e6:.1f} MB -> s3://{bucket}/{key}")
        session.client("s3").upload_file(str(zpath), bucket, key)
    # 4. Runtime (create or update), new version on every deploy
    control = session.client("bedrock-agentcore-control", region_name=REGION)
    spec = dict(
        agentRuntimeArtifact={"codeConfiguration": {
            "code": {"s3": {"bucket": bucket, "prefix": key}}, "runtime": "PYTHON_3_12", "entryPoint": ["main.py"]}},
        roleArn=role_arn,
        networkConfiguration={"networkMode": "PUBLIC"},
        protocolConfiguration={"serverProtocol": "HTTP"},
        environmentVariables=runtime_env(),
        description=f"EXAMEN pipeline {sha}",
    )
    existing = _find_runtime(control)
    for attempt in range(6):  # a role just created can take a few seconds to be assumable
        try:
            if existing:
                result = control.update_agent_runtime(agentRuntimeId=existing["agentRuntimeId"], **spec)
            else:
                result = control.create_agent_runtime(agentRuntimeName=RUNTIME_NAME, **spec)
            break
        except control.exceptions.ValidationException as e:
            if "role" not in str(e).lower() or attempt == 5:
                raise
            time.sleep(10)
    runtime_id = result["agentRuntimeId"]
    print(f"Runtime {runtime_id} version {result.get('agentRuntimeVersion')}: waiting for READY...")
    while True:
        status = control.get_agent_runtime(agentRuntimeId=runtime_id)
        if status["status"] not in ("CREATING", "UPDATING"):
            break
        time.sleep(10)
    print("Status:", status["status"], status.get("failureReason", ""))
    print("AGENTCORE_RUNTIME_ARN =", status["agentRuntimeArn"])
    return 0 if status["status"] == "READY" else 1


def cmd_enable_host(session, args) -> int:
    control = session.client("bedrock-agentcore-control", region_name=REGION)
    runtime = _find_runtime(control)
    if not runtime:
        print("No runtime: run deploy first")
        return 1
    return set_host_env(session, {"PIPELINE_MODE": "agentcore", "AGENTCORE_RUNTIME_ARN": runtime["agentRuntimeArn"]})


def cmd_disable_host(session, args) -> int:
    return set_host_env(session, {"PIPELINE_MODE": "local"})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("deploy").set_defaults(func=cmd_deploy)
    sub.add_parser("enable-host").set_defaults(func=cmd_enable_host)
    sub.add_parser("disable-host").set_defaults(func=cmd_disable_host)
    args = parser.parse_args()
    return args.func(_session(), args)


if __name__ == "__main__":
    raise SystemExit(main())

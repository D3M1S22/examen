"""Deploy or update the EXAMEN compute stack and roll out a bundle (docs/17_aws_deployment_runbook.md §5).

    .venv/bin/python scripts/aws_deploy.py params --admin-email admin@example.com   # once: SSM parameters
    .venv/bin/python scripts/aws_deploy.py stack                                     # create / update examen-compute
    .venv/bin/python scripts/aws_deploy.py update                                    # host.sh update via SSM
    .venv/bin/python scripts/aws_deploy.py logs                                      # bootstrap log + service status

Run scripts/aws_bundle.py first. The admin password is generated and stored only in SSM
(SecureString /examen/bootstrap-admin-password): read it from the Parameter Store console.
"""

import argparse
import secrets
import string
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.aws_bundle import _session  # noqa: E402

STACK = "examen-compute"
TEMPLATE = ROOT / "deploy" / "aws" / "compute.yaml"


def _password() -> str:
    alphabet = string.ascii_letters + string.digits
    core = "".join(secrets.choice(alphabet) for _ in range(20))
    return f"Ex-{core}-9!"


def cmd_params(session, args) -> int:
    ssm = session.client("ssm")
    ssm.put_parameter(Name="/examen/bootstrap-admin-email", Value=args.admin_email, Type="String", Overwrite=True)
    try:
        ssm.get_parameter(Name="/examen/bootstrap-admin-password")
        print("/examen/bootstrap-admin-password exists: kept")
    except ssm.exceptions.ParameterNotFound:
        ssm.put_parameter(Name="/examen/bootstrap-admin-password", Value=_password(), Type="SecureString")
        print("/examen/bootstrap-admin-password created (SecureString): read it in the Parameter Store console")
    print(f"/examen/bootstrap-admin-email = {args.admin_email}")
    return 0


def deploy_stack(session, stack_name: str, template: Path, params, keep_previous=()) -> dict:
    """Creates or updates a stack and waits; returns its outputs (raises on failure).

    ``keep_previous`` lists parameters an update must keep (UsePreviousValue)."""
    cfn = session.client("cloudformation")
    body = template.read_text()
    try:
        cfn.describe_stacks(StackName=stack_name)
        exists = True
    except cfn.exceptions.ClientError:
        exists = False
    parameters = [{"ParameterKey": k, "ParameterValue": v} for k, v in params.items()]
    if exists:
        parameters += [{"ParameterKey": k, "UsePreviousValue": True} for k in keep_previous if k not in params]
    kwargs = dict(StackName=stack_name, TemplateBody=body, Parameters=parameters, Capabilities=["CAPABILITY_NAMED_IAM"])
    if exists:
        try:
            cfn.update_stack(**kwargs)
        except cfn.exceptions.ClientError as e:
            if "No updates are to be performed" not in str(e):
                raise
            print(f"{stack_name}: up to date")
            return _outputs(cfn, stack_name)
    else:
        cfn.create_stack(**kwargs, Tags=[{"Key": "project", "Value": "examen"}])
    print(f"{'Updating' if exists else 'Creating'} {stack_name}...")
    while True:
        stack = cfn.describe_stacks(StackName=stack_name)["Stacks"][0]
        if not stack["StackStatus"].endswith("IN_PROGRESS"):
            break
        time.sleep(10)
    print(f"{stack_name}: {stack['StackStatus']}")
    if stack["StackStatus"] not in ("CREATE_COMPLETE", "UPDATE_COMPLETE"):
        for ev in cfn.describe_stack_events(StackName=stack_name)["StackEvents"][:20]:
            if "FAILED" in ev["ResourceStatus"]:
                print(" ", ev["LogicalResourceId"], ev["ResourceStatus"], ev.get("ResourceStatusReason", "")[:240])
        raise SystemExit(1)
    return _outputs(cfn, stack_name)


def cmd_stack(session, args) -> int:
    account = session.client("sts").get_caller_identity()["Account"]
    params = {"ArtifactBucket": f"examen-artifacts-{account}-euc1"}
    params.update(dict(p.split("=", 1) for p in args.param or []))
    for key, value in deploy_stack(session, STACK, TEMPLATE, params).items():
        print(f"{key}: {value}")
    return 0


def _outputs(cfn, stack_name: str = STACK) -> dict:
    stack = cfn.describe_stacks(StackName=stack_name)["Stacks"][0]
    return {o["OutputKey"]: o["OutputValue"] for o in stack.get("Outputs", [])}


def _instance_id(session) -> str:
    cfn = session.client("cloudformation")
    outputs = {o["OutputKey"]: o["OutputValue"] for o in cfn.describe_stacks(StackName=STACK)["Stacks"][0]["Outputs"]}
    return outputs["InstanceId"]


def run_on_host(session, commands, timeout: int = 900) -> int:
    ssm = session.client("ssm")
    instance = _instance_id(session)
    command = ssm.send_command(InstanceIds=[instance], DocumentName="AWS-RunShellScript",
                               Parameters={"commands": commands, "executionTimeout": [str(timeout)]})["Command"]
    deadline = time.time() + timeout + 60
    while time.time() < deadline:
        time.sleep(5)
        try:
            result = ssm.get_command_invocation(CommandId=command["CommandId"], InstanceId=instance)
        except ssm.exceptions.InvocationDoesNotExist:
            continue
        if result["Status"] in ("Success", "Failed", "Cancelled", "TimedOut"):
            print(result.get("StandardOutputContent", "")[-6000:])
            err = result.get("StandardErrorContent", "")
            if err.strip():
                print("--- stderr ---\n" + err[-3000:])
            print("Status:", result["Status"])
            return 0 if result["Status"] == "Success" else 1
    print("Timed out waiting for the command")
    return 1


def cmd_update(session, args) -> int:
    return run_on_host(session, ["/usr/local/sbin/examen-host update"])


def cmd_logs(session, args) -> int:
    return run_on_host(session, ["tail -n 60 /var/log/examen-bootstrap.log || true",
                          "systemctl is-active examen || true",
                          "journalctl -u examen -n 40 --no-pager || true"], timeout=120)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("params")
    p.add_argument("--admin-email", required=True)
    p.set_defaults(func=cmd_params)
    p = sub.add_parser("stack")
    p.add_argument("--param", action="append", help="Key=Value override of a template parameter")
    p.set_defaults(func=cmd_stack)
    sub.add_parser("update").set_defaults(func=cmd_update)
    sub.add_parser("logs").set_defaults(func=cmd_logs)
    args = parser.parse_args()
    return args.func(_session(), args)


if __name__ == "__main__":
    raise SystemExit(main())

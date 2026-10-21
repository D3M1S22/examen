"""deploy/aws/compute.yaml keeps the security baseline of docs/17_aws_deployment_runbook.md."""

import subprocess
from pathlib import Path

import pytest

from tests.test_dynamo_schema import _CfnLoader, yaml

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def resources():
    return yaml.load((ROOT / "deploy" / "aws" / "compute.yaml").read_text(), Loader=_CfnLoader)["Resources"]


def test_origin_is_reachable_from_cloudfront_only(resources):
    rules = resources["OriginSecurityGroup"]["Properties"]["SecurityGroupIngress"]
    assert [(r["FromPort"], r["ToPort"]) for r in rules] == [(8000, 8000)]
    assert all("SourcePrefixListId" in r and "CidrIp" not in r for r in rules)


def test_instance_hardening(resources):
    data = resources["LaunchTemplate"]["Properties"]["LaunchTemplateData"]
    assert data["MetadataOptions"]["HttpTokens"] == "required"
    assert all(b["Ebs"]["Encrypted"] is True for b in data["BlockDeviceMappings"])
    assert "KeyName" not in resources["Instance"]["Properties"]  # no SSH key: SSM only


def test_cloudfront_never_caches_and_forces_https(resources):
    behaviour = resources["Distribution"]["Properties"]["DistributionConfig"]["DefaultCacheBehavior"]
    assert behaviour["ViewerProtocolPolicy"] == "redirect-to-https"
    assert behaviour["CachePolicyId"] == "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"  # CachingDisabled
    assert behaviour["Compress"] is False  # SSE must not be buffered


def test_host_script_parses():
    subprocess.check_call(["bash", "-n", str(ROOT / "deploy" / "aws" / "host.sh")])

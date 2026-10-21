"""deploy/aws/dynamodb.yaml declares the key schema of src/core/storage/dynamo_schema.py (D13)."""

from pathlib import Path

import pytest
import yaml

from src.core.storage.dynamo_schema import AUTH, OPS, TABLE_SPECS, USER

TEMPLATE = Path(__file__).resolve().parents[1] / "deploy" / "aws" / "dynamodb.yaml"


class _CfnLoader(yaml.SafeLoader):
    pass


def _tag(loader, suffix, node):
    if isinstance(node, yaml.ScalarNode):
        return {suffix: loader.construct_scalar(node)}
    if isinstance(node, yaml.SequenceNode):
        return {suffix: loader.construct_sequence(node, deep=True)}
    return {suffix: loader.construct_mapping(node, deep=True)}


_CfnLoader.add_multi_constructor("!", _tag)


@pytest.fixture(scope="module")
def resources():
    return yaml.load(TEMPLATE.read_text(), Loader=_CfnLoader)["Resources"]


@pytest.mark.parametrize("kind,resource", [(USER, "UserTable"), (AUTH, "AuthTable"), (OPS, "OpsTable")])
def test_template_matches_table_specs(resources, kind, resource):
    props = resources[resource]["Properties"]
    spec = TABLE_SPECS[kind]
    assert props["KeySchema"] == spec["KeySchema"]
    assert sorted(props["AttributeDefinitions"], key=lambda a: a["AttributeName"]) == \
        sorted(spec["AttributeDefinitions"], key=lambda a: a["AttributeName"])
    assert props["GlobalSecondaryIndexes"] == spec["GlobalSecondaryIndexes"]
    assert props["BillingMode"] == "PAY_PER_REQUEST"
    assert props["TimeToLiveSpecification"] == {"AttributeName": "ttl", "Enabled": True}
    assert props["PointInTimeRecoverySpecification"] == {"PointInTimeRecoveryEnabled": True}
    assert props["DeletionProtectionEnabled"] is True


def test_tenant_role_is_limited_to_own_partition_without_scan(resources):
    statement = resources["TenantDataRole"]["Properties"]["Policies"][0]["PolicyDocument"]["Statement"][0]
    assert "dynamodb:Scan" not in statement["Action"]
    assert statement["Condition"]["ForAllValues:StringLike"]["dynamodb:LeadingKeys"] == [
        "${aws:PrincipalTag/user_id}", "${aws:PrincipalTag/user_id}#*"]
    runtime = resources["RuntimeDataPolicy"]["Properties"]["PolicyDocument"]["Statement"]
    user_table_actions = [s["Action"] for s in runtime if s.get("Sid") == "StartupCheck"]
    assert user_table_actions == ["dynamodb:DescribeTable"]

from unittest.mock import MagicMock

from awstui.models import TreeNode
from awstui.services.secrets_manager import SecretsManagerPlugin


def make_session():
    return MagicMock()


def test_secrets_manager_plugin_properties():
    plugin = SecretsManagerPlugin()
    assert plugin.name == "Secrets Manager"
    assert plugin.service_name == "secretsmanager"


def test_get_root_nodes_returns_secrets():
    session = make_session()
    client = session.client.return_value
    client.get_paginator.return_value.paginate.return_value = [
        {
            "SecretList": [
                {
                    "ARN": "arn:aws:secretsmanager:us-east-1:123:secret:alpha-AbCdEf",
                    "Name": "alpha",
                },
                {
                    "ARN": "arn:aws:secretsmanager:us-east-1:123:secret:beta-GhIjKl",
                    "Name": "beta",
                },
            ]
        }
    ]

    plugin = SecretsManagerPlugin()
    nodes = plugin.get_root_nodes(session)

    assert len(nodes) == 2
    assert nodes[0].label == "alpha"
    assert nodes[0].node_type == "secret"
    assert nodes[0].expandable is False
    assert (
        nodes[0].metadata["secret_id"]
        == "arn:aws:secretsmanager:us-east-1:123:secret:alpha-AbCdEf"
    )


def test_get_root_nodes_empty():
    session = make_session()
    client = session.client.return_value
    client.get_paginator.return_value.paginate.return_value = [{}]

    plugin = SecretsManagerPlugin()
    assert plugin.get_root_nodes(session) == []


def test_get_children_returns_empty():
    session = make_session()
    node = TreeNode(
        id="secretsmanager:secret:arn:aws:secretsmanager:us-east-1:123:secret:alpha-AbCdEf",
        label="alpha",
        node_type="secret",
        service="secretsmanager",
        expandable=False,
        metadata={
            "secret_id": "arn:aws:secretsmanager:us-east-1:123:secret:alpha-AbCdEf"
        },
    )

    plugin = SecretsManagerPlugin()
    assert plugin.get_children(session, node) == []


def test_get_details_with_rotation_and_kms():
    session = make_session()
    client = session.client.return_value
    client.describe_secret.return_value = {
        "ARN": "arn:aws:secretsmanager:us-east-1:123:secret:alpha-AbCdEf",
        "Name": "alpha",
        "Description": "test secret",
        "KmsKeyId": "arn:aws:kms:us-east-1:123:key/abcd",
        "RotationEnabled": True,
        "RotationLambdaARN": "arn:aws:lambda:us-east-1:123:function:rotator",
        "LastChangedDate": "2025-01-01T00:00:00Z",
        "LastAccessedDate": "2025-02-01T00:00:00Z",
        "LastRotatedDate": "2025-01-15T00:00:00Z",
        "Tags": [{"Key": "env", "Value": "prod"}],
    }

    node = TreeNode(
        id="secretsmanager:secret:arn:aws:secretsmanager:us-east-1:123:secret:alpha-AbCdEf",
        label="alpha",
        node_type="secret",
        service="secretsmanager",
        expandable=False,
        metadata={
            "secret_id": "arn:aws:secretsmanager:us-east-1:123:secret:alpha-AbCdEf"
        },
    )

    plugin = SecretsManagerPlugin()
    details = plugin.get_details(session, node)

    assert details.title == "Secret: alpha"
    assert (
        details.subtitle == "arn:aws:secretsmanager:us-east-1:123:secret:alpha-AbCdEf"
    )
    assert details.summary["Rotation Enabled"] == "Yes"
    assert (
        details.summary["Rotation Lambda"]
        == "arn:aws:lambda:us-east-1:123:function:rotator"
    )
    assert details.summary["KMS Key ID"] == "arn:aws:kms:us-east-1:123:key/abcd"
    assert details.summary["Tags"] == "1"

    client.get_secret_value.assert_not_called()


def test_get_details_without_rotation_or_kms():
    session = make_session()
    client = session.client.return_value
    client.describe_secret.return_value = {
        "ARN": "arn:aws:secretsmanager:us-east-1:123:secret:beta-GhIjKl",
        "Name": "beta",
        "Description": "",
    }

    node = TreeNode(
        id="secretsmanager:secret:arn:aws:secretsmanager:us-east-1:123:secret:beta-GhIjKl",
        label="beta",
        node_type="secret",
        service="secretsmanager",
        expandable=False,
        metadata={
            "secret_id": "arn:aws:secretsmanager:us-east-1:123:secret:beta-GhIjKl"
        },
    )

    plugin = SecretsManagerPlugin()
    details = plugin.get_details(session, node)

    assert details.summary["Rotation Enabled"] == "No"
    assert details.summary["Rotation Lambda"] == "None"
    assert details.summary["KMS Key ID"] == "aws/secretsmanager"
    assert details.summary["Tags"] == "None"

    client.get_secret_value.assert_not_called()

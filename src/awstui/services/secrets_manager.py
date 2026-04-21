from __future__ import annotations

import boto3

from awstui.models import ResourceDetails, TreeNode
from awstui.plugin import AWSServicePlugin


class SecretsManagerPlugin(AWSServicePlugin):
    @property
    def name(self) -> str:
        return "Secrets Manager"

    @property
    def service_name(self) -> str:
        return "secretsmanager"

    def get_root_nodes(self, session: boto3.Session) -> list[TreeNode]:
        client = session.client("secretsmanager")
        paginator = client.get_paginator("list_secrets")
        nodes: list[TreeNode] = []
        for page in paginator.paginate():
            for secret in page.get("SecretList", []):
                arn = secret["ARN"]
                name = secret["Name"]
                nodes.append(
                    TreeNode(
                        id=f"secretsmanager:secret:{arn}",
                        label=name,
                        node_type="secret",
                        service="secretsmanager",
                        expandable=False,
                        metadata={"secret_id": arn},
                    )
                )
        return nodes

    def get_children(self, session: boto3.Session, node: TreeNode) -> list[TreeNode]:
        return []

    def get_details(self, session: boto3.Session, node: TreeNode) -> ResourceDetails:
        client = session.client("secretsmanager")
        response = client.describe_secret(SecretId=node.metadata["secret_id"])

        rotation_enabled = response.get("RotationEnabled", False)
        rotation_lambda = response.get("RotationLambdaARN", "")
        tags = response.get("Tags", [])

        summary = {
            "Name": response.get("Name", ""),
            "ARN": response.get("ARN", ""),
            "Description": response.get("Description", ""),
            "KMS Key ID": response.get("KmsKeyId", "aws/secretsmanager"),
            "Rotation Enabled": "Yes" if rotation_enabled else "No",
            "Rotation Lambda": rotation_lambda or "None",
            "Last Changed": str(response.get("LastChangedDate", "")),
            "Last Accessed": str(response.get("LastAccessedDate", "")),
            "Last Rotated": str(response.get("LastRotatedDate", "")),
            "Tags": str(len(tags)) if tags else "None",
        }

        return ResourceDetails(
            title=f"Secret: {response.get('Name', node.label)}",
            subtitle=response.get("ARN", ""),
            summary=summary,
            raw=response,
        )


plugin = SecretsManagerPlugin()

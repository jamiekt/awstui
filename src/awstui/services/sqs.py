from __future__ import annotations

import json

import boto3

from awstui.models import ResourceDetails, TreeNode
from awstui.plugin import AWSServicePlugin


class SQSPlugin(AWSServicePlugin):
    @property
    def name(self) -> str:
        return "SQS"

    @property
    def service_name(self) -> str:
        return "sqs"

    def get_root_nodes(self, session: boto3.Session) -> list[TreeNode]:
        client = session.client("sqs")
        response = client.list_queues()
        urls = response.get("QueueUrls", [])
        return [
            TreeNode(
                id=f"sqs:queue:{url.rsplit('/', 1)[-1]}",
                label=url.rsplit("/", 1)[-1],
                node_type="queue",
                service="sqs",
                expandable=False,
                metadata={"queue_url": url},
            )
            for url in urls
        ]

    def get_children(self, session: boto3.Session, node: TreeNode) -> list[TreeNode]:
        return []

    def get_details(self, session: boto3.Session, node: TreeNode) -> ResourceDetails:
        client = session.client("sqs")
        queue_url = node.metadata["queue_url"]
        response = client.get_queue_attributes(
            QueueUrl=queue_url, AttributeNames=["All"]
        )
        attrs = response.get("Attributes", {})

        redrive = attrs.get("RedrivePolicy", "")
        dlq_info = ""
        if redrive:
            parsed = json.loads(redrive)
            dlq_arn = parsed.get("deadLetterTargetArn", "")
            max_receive = parsed.get("maxReceiveCount", "")
            dlq_info = f"{dlq_arn} (max receives: {max_receive})"

        return ResourceDetails(
            title=f"SQS Queue: {node.label}",
            subtitle=attrs.get("QueueArn", ""),
            summary={
                "Queue URL": queue_url,
                "ARN": attrs.get("QueueArn", ""),
                "Messages Available": attrs.get("ApproximateNumberOfMessages", "0"),
                "Messages In Flight": attrs.get(
                    "ApproximateNumberOfMessagesNotVisible", "0"
                ),
                "Messages Delayed": attrs.get(
                    "ApproximateNumberOfMessagesDelayed", "0"
                ),
                "Visibility Timeout": attrs.get("VisibilityTimeout", ""),
                "Dead Letter Queue": dlq_info or "None",
            },
            raw=attrs,
        )


plugin = SQSPlugin()

from __future__ import annotations

import boto3

from awstui.models import ResourceDetails, TreeNode
from awstui.plugin import AWSServicePlugin


class SNSPlugin(AWSServicePlugin):
    @property
    def name(self) -> str:
        return "SNS"

    @property
    def service_name(self) -> str:
        return "sns"

    def get_root_nodes(self, session: boto3.Session) -> list[TreeNode]:
        return [
            TreeNode(
                id="sns:category:topics",
                label="Topics",
                node_type="category",
                service="sns",
                expandable=True,
                metadata={"category": "topics"},
            ),
            TreeNode(
                id="sns:category:subscriptions",
                label="Subscriptions",
                node_type="category",
                service="sns",
                expandable=True,
                metadata={"category": "subscriptions"},
            ),
        ]

    def get_children(self, session: boto3.Session, node: TreeNode) -> list[TreeNode]:
        client = session.client("sns")

        if node.metadata.get("category") == "topics":
            paginator = client.get_paginator("list_topics")
            nodes: list[TreeNode] = []
            for page in paginator.paginate():
                for topic in page.get("Topics", []):
                    arn = topic["TopicArn"]
                    name = arn.rsplit(":", 1)[-1]
                    nodes.append(
                        TreeNode(
                            id=f"sns:topic:{name}",
                            label=name,
                            node_type="topic",
                            service="sns",
                            expandable=True,
                            metadata={"topic_arn": arn},
                        )
                    )
            return nodes

        if node.metadata.get("category") == "subscriptions":
            paginator = client.get_paginator("list_subscriptions")
            nodes = []
            for page in paginator.paginate():
                for sub in page.get("Subscriptions", []):
                    nodes.append(
                        TreeNode(
                            id=f"sns:sub:{sub['SubscriptionArn'].rsplit(':', 1)[-1]}",
                            label=f"{sub['Protocol']}: {sub['Endpoint']}",
                            node_type="subscription",
                            service="sns",
                            expandable=False,
                            metadata={"subscription_arn": sub["SubscriptionArn"]},
                        )
                    )
            return nodes

        if node.node_type == "topic":
            response = client.list_subscriptions_by_topic(
                TopicArn=node.metadata["topic_arn"]
            )
            return [
                TreeNode(
                    id=f"sns:sub:{sub['SubscriptionArn'].rsplit(':', 1)[-1]}",
                    label=f"{sub['Protocol']}: {sub['Endpoint']}",
                    node_type="subscription",
                    service="sns",
                    expandable=False,
                    metadata={"subscription_arn": sub["SubscriptionArn"]},
                )
                for sub in response.get("Subscriptions", [])
            ]

        return []

    def get_details(self, session: boto3.Session, node: TreeNode) -> ResourceDetails:
        client = session.client("sns")

        if node.node_type == "topic":
            response = client.get_topic_attributes(TopicArn=node.metadata["topic_arn"])
            attrs = response.get("Attributes", {})
            return ResourceDetails(
                title=f"SNS Topic: {node.label}",
                subtitle=attrs.get("TopicArn", ""),
                summary={
                    "Topic ARN": attrs.get("TopicArn", ""),
                    "Display Name": attrs.get("DisplayName", ""),
                    "Subscriptions Confirmed": attrs.get("SubscriptionsConfirmed", "0"),
                    "Subscriptions Pending": attrs.get("SubscriptionsPending", "0"),
                    "Subscriptions Deleted": attrs.get("SubscriptionsDeleted", "0"),
                },
                raw=attrs,
            )

        if node.node_type == "subscription":
            response = client.get_subscription_attributes(
                SubscriptionArn=node.metadata["subscription_arn"]
            )
            attrs = response.get("Attributes", {})
            return ResourceDetails(
                title="SNS Subscription",
                subtitle=attrs.get("SubscriptionArn", ""),
                summary={
                    "Subscription ARN": attrs.get("SubscriptionArn", ""),
                    "Protocol": attrs.get("Protocol", ""),
                    "Endpoint": attrs.get("Endpoint", ""),
                    "Topic ARN": attrs.get("TopicArn", ""),
                    "Owner": attrs.get("Owner", ""),
                },
                raw=attrs,
            )

        if node.node_type == "category":
            return ResourceDetails(
                title=node.label, subtitle="Expand to see resources", summary={}, raw={}
            )

        return ResourceDetails(title=node.label, subtitle="", summary={}, raw={})


plugin = SNSPlugin()

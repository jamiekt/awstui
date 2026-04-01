from unittest.mock import MagicMock

from awstui.services.sns import SNSPlugin


def make_session():
    return MagicMock()


def test_sns_plugin_properties():
    plugin = SNSPlugin()
    assert plugin.name == "SNS"
    assert plugin.service_name == "sns"


def test_get_root_nodes_returns_topics():
    session = make_session()
    client = session.client.return_value
    client.get_paginator.return_value.paginate.return_value = [
        {
            "Topics": [
                {"TopicArn": "arn:aws:sns:us-east-1:123:my-topic"},
                {"TopicArn": "arn:aws:sns:us-east-1:123:other-topic"},
            ]
        }
    ]

    plugin = SNSPlugin()
    nodes = plugin.get_root_nodes(session)

    assert len(nodes) == 2
    assert nodes[0].label == "my-topic"
    assert nodes[0].node_type == "topic"
    assert nodes[0].expandable is True


def test_get_children_of_topic_returns_subscriptions():
    session = make_session()
    client = session.client.return_value
    client.list_subscriptions_by_topic.return_value = {
        "Subscriptions": [
            {
                "SubscriptionArn": "arn:aws:sns:us-east-1:123:my-topic:sub1",
                "Protocol": "email",
                "Endpoint": "user@example.com",
            }
        ]
    }

    from awstui.models import TreeNode

    node = TreeNode(
        id="sns:topic:my-topic",
        label="my-topic",
        node_type="topic",
        service="sns",
        expandable=True,
        metadata={"topic_arn": "arn:aws:sns:us-east-1:123:my-topic"},
    )

    plugin = SNSPlugin()
    children = plugin.get_children(session, node)

    assert len(children) == 1
    assert children[0].label == "email: user@example.com"
    assert children[0].node_type == "subscription"
    assert children[0].expandable is False


def test_get_details_for_topic():
    session = make_session()
    client = session.client.return_value
    client.get_topic_attributes.return_value = {
        "Attributes": {
            "TopicArn": "arn:aws:sns:us-east-1:123:my-topic",
            "DisplayName": "My Topic",
            "SubscriptionsConfirmed": "3",
            "SubscriptionsPending": "1",
            "SubscriptionsDeleted": "0",
        }
    }

    from awstui.models import TreeNode

    node = TreeNode(
        id="sns:topic:my-topic",
        label="my-topic",
        node_type="topic",
        service="sns",
        expandable=True,
        metadata={"topic_arn": "arn:aws:sns:us-east-1:123:my-topic"},
    )

    plugin = SNSPlugin()
    details = plugin.get_details(session, node)

    assert details.title == "SNS Topic: my-topic"
    assert "Subscriptions Confirmed" in details.summary


def test_get_details_for_subscription():
    session = make_session()
    client = session.client.return_value
    client.get_subscription_attributes.return_value = {
        "Attributes": {
            "SubscriptionArn": "arn:aws:sns:us-east-1:123:my-topic:sub1",
            "Protocol": "email",
            "Endpoint": "user@example.com",
            "TopicArn": "arn:aws:sns:us-east-1:123:my-topic",
            "Owner": "123456789012",
        }
    }

    from awstui.models import TreeNode

    node = TreeNode(
        id="sns:sub:sub1",
        label="email: user@example.com",
        node_type="subscription",
        service="sns",
        expandable=False,
        metadata={"subscription_arn": "arn:aws:sns:us-east-1:123:my-topic:sub1"},
    )

    plugin = SNSPlugin()
    details = plugin.get_details(session, node)

    assert details.title == "SNS Subscription"
    assert "Protocol" in details.summary
    assert "Endpoint" in details.summary

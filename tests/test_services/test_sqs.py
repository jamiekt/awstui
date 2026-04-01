from unittest.mock import MagicMock

from awstui.services.sqs import SQSPlugin


def make_session():
    return MagicMock()


def test_sqs_plugin_properties():
    plugin = SQSPlugin()
    assert plugin.name == "SQS"
    assert plugin.service_name == "sqs"


def test_get_root_nodes_returns_queues():
    session = make_session()
    client = session.client.return_value
    client.list_queues.return_value = {
        "QueueUrls": [
            "https://sqs.us-east-1.amazonaws.com/123/my-queue",
            "https://sqs.us-east-1.amazonaws.com/123/other-queue",
        ]
    }

    plugin = SQSPlugin()
    nodes = plugin.get_root_nodes(session)

    assert len(nodes) == 2
    assert nodes[0].label == "my-queue"
    assert nodes[0].node_type == "queue"
    assert nodes[0].expandable is False


def test_get_root_nodes_empty():
    session = make_session()
    client = session.client.return_value
    client.list_queues.return_value = {}

    plugin = SQSPlugin()
    nodes = plugin.get_root_nodes(session)
    assert nodes == []


def test_get_children_returns_empty():
    session = make_session()
    from awstui.models import TreeNode

    node = TreeNode(
        id="sqs:queue:my-queue",
        label="my-queue",
        node_type="queue",
        service="sqs",
        expandable=False,
        metadata={"queue_url": "https://sqs.us-east-1.amazonaws.com/123/my-queue"},
    )

    plugin = SQSPlugin()
    assert plugin.get_children(session, node) == []


def test_get_details_for_queue():
    session = make_session()
    client = session.client.return_value
    client.get_queue_attributes.return_value = {
        "Attributes": {
            "QueueArn": "arn:aws:sqs:us-east-1:123:my-queue",
            "ApproximateNumberOfMessages": "5",
            "ApproximateNumberOfMessagesNotVisible": "2",
            "ApproximateNumberOfMessagesDelayed": "0",
            "VisibilityTimeout": "30",
            "CreatedTimestamp": "1700000000",
            "LastModifiedTimestamp": "1700000001",
            "RedrivePolicy": '{"deadLetterTargetArn":"arn:aws:sqs:us-east-1:123:my-dlq","maxReceiveCount":3}',
        }
    }

    from awstui.models import TreeNode

    node = TreeNode(
        id="sqs:queue:my-queue",
        label="my-queue",
        node_type="queue",
        service="sqs",
        expandable=False,
        metadata={"queue_url": "https://sqs.us-east-1.amazonaws.com/123/my-queue"},
    )

    plugin = SQSPlugin()
    details = plugin.get_details(session, node)

    assert details.title == "SQS Queue: my-queue"
    assert "Messages Available" in details.summary
    assert "Dead Letter Queue" in details.summary

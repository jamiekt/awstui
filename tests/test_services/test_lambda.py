from unittest.mock import MagicMock

from awstui.services.lambda_ import LambdaPlugin


def make_session():
    return MagicMock()


def test_lambda_plugin_properties():
    plugin = LambdaPlugin()
    assert plugin.name == "Lambda"
    assert plugin.service_name == "lambda"


def test_get_root_nodes_returns_functions():
    session = make_session()
    client = session.client.return_value
    client.get_paginator.return_value.paginate.return_value = [
        {
            "Functions": [
                {
                    "FunctionName": "my-func",
                    "FunctionArn": "arn:aws:lambda:us-east-1:123:function:my-func",
                    "Runtime": "python3.12",
                },
                {
                    "FunctionName": "other-func",
                    "FunctionArn": "arn:aws:lambda:us-east-1:123:function:other-func",
                    "Runtime": "nodejs20.x",
                },
            ]
        }
    ]

    plugin = LambdaPlugin()
    nodes = plugin.get_root_nodes(session)

    assert len(nodes) == 2
    assert nodes[0].label == "my-func"
    assert nodes[0].node_type == "function"
    assert nodes[0].expandable is False


def test_get_children_returns_empty():
    session = make_session()
    from awstui.models import TreeNode

    node = TreeNode(
        id="lambda:function:my-func",
        label="my-func",
        node_type="function",
        service="lambda",
        expandable=False,
    )

    plugin = LambdaPlugin()
    assert plugin.get_children(session, node) == []


def test_get_details_for_function():
    session = make_session()
    client = session.client.return_value
    func_config = {
        "FunctionName": "my-func",
        "FunctionArn": "arn:aws:lambda:us-east-1:123:function:my-func",
        "Runtime": "python3.12",
        "Handler": "index.handler",
        "CodeSize": 1234,
        "MemorySize": 128,
        "Timeout": 30,
        "LastModified": "2026-03-01T00:00:00Z",
        "Description": "My function",
    }
    client.get_function.return_value = {"Configuration": func_config}

    from awstui.models import TreeNode

    node = TreeNode(
        id="lambda:function:my-func",
        label="my-func",
        node_type="function",
        service="lambda",
        expandable=False,
        metadata={"function_name": "my-func"},
    )

    plugin = LambdaPlugin()
    details = plugin.get_details(session, node)

    assert details.title == "Lambda Function: my-func"
    assert "Runtime" in details.summary
    assert "Memory (MB)" in details.summary
    assert "Timeout (s)" in details.summary

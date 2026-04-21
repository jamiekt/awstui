from unittest.mock import MagicMock

from awstui.services.iam import IAMPlugin


def make_session():
    return MagicMock()


def test_iam_plugin_properties():
    plugin = IAMPlugin()
    assert plugin.name == "IAM"
    assert plugin.service_name == "iam"


def test_get_root_nodes_returns_categories():
    session = make_session()
    plugin = IAMPlugin()
    nodes = plugin.get_root_nodes(session)

    labels = [n.label for n in nodes]
    assert "Users" in labels
    assert "Roles" in labels
    assert "Policies" in labels
    assert "Groups" in labels
    assert all(n.node_type == "category" for n in nodes)


def test_get_children_of_users_category():
    session = make_session()
    client = session.client.return_value
    client.get_paginator.return_value.paginate.return_value = [
        {
            "Users": [
                {"UserName": "alice", "Arn": "arn:aws:iam::123:user/alice"},
                {"UserName": "bob", "Arn": "arn:aws:iam::123:user/bob"},
            ]
        }
    ]

    from awstui.models import TreeNode

    node = TreeNode(
        id="iam:category:users",
        label="Users",
        node_type="category",
        service="iam",
        expandable=True,
        metadata={"category": "users"},
    )

    plugin = IAMPlugin()
    children = plugin.get_children(session, node)

    assert len(children) == 2
    assert children[0].label == "alice"
    assert children[0].node_type == "user"
    assert children[0].expandable is True


def test_get_children_of_user_returns_subcategories():
    session = make_session()

    from awstui.models import TreeNode

    node = TreeNode(
        id="iam:user:alice",
        label="alice",
        node_type="user",
        service="iam",
        expandable=True,
        metadata={"user_name": "alice"},
    )

    plugin = IAMPlugin()
    children = plugin.get_children(session, node)

    labels = [c.label for c in children]
    assert "Attached Policies" in labels
    assert "Inline Policies" in labels
    assert "Access Keys" in labels


def test_get_children_of_user_attached_policies():
    session = make_session()
    client = session.client.return_value
    client.list_attached_user_policies.return_value = {
        "AttachedPolicies": [
            {
                "PolicyName": "ReadOnlyAccess",
                "PolicyArn": "arn:aws:iam::aws:policy/ReadOnlyAccess",
            }
        ]
    }

    from awstui.models import TreeNode

    node = TreeNode(
        id="iam:user:alice:attached_policies",
        label="Attached Policies",
        node_type="user_attached_policies",
        service="iam",
        expandable=True,
        metadata={"user_name": "alice"},
    )

    plugin = IAMPlugin()
    children = plugin.get_children(session, node)

    assert len(children) == 1
    assert children[0].label == "ReadOnlyAccess"
    assert children[0].expandable is False


def test_get_details_for_user():
    session = make_session()
    client = session.client.return_value
    user_data = {
        "UserName": "alice",
        "UserId": "AIDA123",
        "Arn": "arn:aws:iam::123:user/alice",
        "CreateDate": "2025-01-01T00:00:00Z",
    }
    client.get_user.return_value = {"User": user_data}

    from awstui.models import TreeNode

    node = TreeNode(
        id="iam:user:alice",
        label="alice",
        node_type="user",
        service="iam",
        expandable=True,
        metadata={"user_name": "alice"},
    )

    plugin = IAMPlugin()
    details = plugin.get_details(session, node)

    assert details.title == "IAM User: alice"
    assert "User Name" in details.summary

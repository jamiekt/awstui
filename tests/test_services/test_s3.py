from unittest.mock import MagicMock

from awstui.services.s3 import S3Plugin


def make_session():
    return MagicMock()


def test_s3_plugin_properties():
    plugin = S3Plugin()
    assert plugin.name == "S3"
    assert plugin.service_name == "s3"


def test_get_root_nodes_returns_categories():
    session = make_session()

    plugin = S3Plugin()
    nodes = plugin.get_root_nodes(session)

    assert len(nodes) == 5
    labels = [n.label for n in nodes]
    assert "General purpose buckets" in labels
    assert "Directory buckets" in labels
    assert "Table buckets" in labels
    assert "Access points" in labels
    assert "Vector buckets" in labels
    assert all(n.node_type == "category" for n in nodes)
    assert all(n.expandable for n in nodes)


def test_get_children_of_general_purpose_buckets_category():
    session = make_session()
    client = session.client.return_value
    client.list_buckets.return_value = {
        "Buckets": [
            {"Name": "bucket-a", "CreationDate": "2026-01-01T00:00:00Z"},
            {"Name": "bucket-b", "CreationDate": "2026-01-02T00:00:00Z"},
        ]
    }

    from awstui.models import TreeNode

    category_node = TreeNode(
        id="s3:category:general_purpose_buckets",
        label="General purpose buckets",
        node_type="category",
        service="s3",
        expandable=True,
        metadata={"category": "general_purpose_buckets"},
    )

    plugin = S3Plugin()
    children = plugin.get_children(session, category_node)

    assert len(children) == 2
    assert children[0].label == "bucket-a"
    assert children[0].node_type == "bucket"
    assert children[0].expandable is True
    assert children[0].metadata["bucket_name"] == "bucket-a"


def test_get_children_of_bucket_lists_prefixes_and_objects():
    session = make_session()
    client = session.client.return_value
    client.get_paginator.return_value.paginate.return_value = [
        {
            "CommonPrefixes": [{"Prefix": "logs/"}],
            "Contents": [{"Key": "readme.txt", "Size": 1024}],
        }
    ]

    from awstui.models import TreeNode

    bucket_node = TreeNode(
        id="s3:bucket:my-bucket",
        label="my-bucket",
        node_type="bucket",
        service="s3",
        expandable=True,
        metadata={"bucket_name": "my-bucket"},
    )

    plugin = S3Plugin()
    children = plugin.get_children(session, bucket_node)

    assert len(children) == 2
    prefixes = [c for c in children if c.node_type == "prefix"]
    objects = [c for c in children if c.node_type == "object"]
    assert len(prefixes) == 1
    assert prefixes[0].label == "logs/"
    assert prefixes[0].expandable is True
    assert len(objects) == 1
    assert objects[0].label == "readme.txt"
    assert objects[0].expandable is False


def test_get_children_of_prefix():
    session = make_session()
    client = session.client.return_value
    client.get_paginator.return_value.paginate.return_value = [
        {
            "CommonPrefixes": [],
            "Contents": [{"Key": "logs/app.log", "Size": 2048}],
        }
    ]

    from awstui.models import TreeNode

    prefix_node = TreeNode(
        id="s3:prefix:my-bucket:logs/",
        label="logs/",
        node_type="prefix",
        service="s3",
        expandable=True,
        metadata={"bucket_name": "my-bucket", "prefix": "logs/"},
    )

    plugin = S3Plugin()
    children = plugin.get_children(session, prefix_node)

    assert len(children) == 1
    assert children[0].label == "app.log"
    assert children[0].node_type == "object"


def test_get_children_of_prefix_pagination():
    """Children from multiple pages should all be returned."""
    session = make_session()
    client = session.client.return_value
    client.get_paginator.return_value.paginate.return_value = [
        {
            "CommonPrefixes": [],
            "Contents": [{"Key": f"logs/file-{i:04d}.log"} for i in range(1000)],
        },
        {
            "CommonPrefixes": [],
            "Contents": [{"Key": f"logs/file-{i:04d}.log"} for i in range(1000, 1500)],
        },
    ]

    from awstui.models import TreeNode

    prefix_node = TreeNode(
        id="s3:prefix:my-bucket:logs/",
        label="logs/",
        node_type="prefix",
        service="s3",
        expandable=True,
        metadata={"bucket_name": "my-bucket", "prefix": "logs/"},
    )

    plugin = S3Plugin()
    children = plugin.get_children(session, prefix_node)

    assert len(children) == 1500


def test_get_details_for_bucket():
    session = make_session()
    client = session.client.return_value
    client.get_bucket_location.return_value = {"LocationConstraint": "us-west-2"}

    from awstui.models import TreeNode

    bucket_node = TreeNode(
        id="s3:bucket:my-bucket",
        label="my-bucket",
        node_type="bucket",
        service="s3",
        expandable=True,
        metadata={"bucket_name": "my-bucket"},
    )

    plugin = S3Plugin()
    details = plugin.get_details(session, bucket_node)

    assert details.title == "S3 Bucket: my-bucket"
    assert "Name" in details.summary
    assert "Location" in details.summary


def test_get_details_for_object():
    session = make_session()
    client = session.client.return_value
    client.head_object.return_value = {
        "ContentLength": 1024,
        "ContentType": "text/plain",
        "LastModified": "2026-03-28T14:32:01Z",
        "ETag": '"abc123"',
        "StorageClass": "STANDARD",
    }

    from awstui.models import TreeNode

    obj_node = TreeNode(
        id="s3:object:my-bucket:readme.txt",
        label="readme.txt",
        node_type="object",
        service="s3",
        expandable=False,
        metadata={"bucket_name": "my-bucket", "key": "readme.txt"},
    )

    plugin = S3Plugin()
    details = plugin.get_details(session, obj_node)

    assert details.title == "S3 Object: readme.txt"
    assert "Size" in details.summary
    assert "Content Type" in details.summary

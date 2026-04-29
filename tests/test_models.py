from awstui.models import TreeNode, ResourceDetails


def test_tree_node_creation():
    node = TreeNode(
        id="bucket:my-bucket",
        label="my-bucket",
        node_type="bucket",
        service="s3",
        expandable=True,
        metadata={"bucket_name": "my-bucket"},
    )
    assert node.id == "bucket:my-bucket"
    assert node.label == "my-bucket"
    assert node.node_type == "bucket"
    assert node.service == "s3"
    assert node.expandable is True
    assert node.metadata == {"bucket_name": "my-bucket"}


def test_tree_node_default_metadata():
    node = TreeNode(
        id="func:my-func",
        label="my-func",
        node_type="function",
        service="lambda",
        expandable=False,
    )
    assert node.metadata == {}


def test_resource_details_creation():
    details = ResourceDetails(
        title="S3 Bucket: my-bucket",
        subtitle="arn:aws:s3:::my-bucket",
        summary={"Name": "my-bucket", "Region": "us-east-1"},
        raw={"BucketName": "my-bucket"},
    )
    assert details.title == "S3 Bucket: my-bucket"
    assert details.subtitle == "arn:aws:s3:::my-bucket"
    assert details.summary == {"Name": "my-bucket", "Region": "us-east-1"}
    assert details.raw == {"BucketName": "my-bucket"}
    # summary_groups defaults to empty so existing plugins don't need to set it
    assert details.summary_groups == []


def test_resource_details_with_summary_groups():
    details = ResourceDetails(
        title="t",
        subtitle="",
        summary={},
        raw={},
        summary_groups=[("Columns", {"id": "string"})],
    )
    assert details.summary_groups == [("Columns", {"id": "string"})]

from unittest.mock import MagicMock

from awstui.models import TreeNode
from awstui.services.ecr import ECRPlugin


def make_session():
    return MagicMock()


def test_ecr_plugin_properties():
    plugin = ECRPlugin()
    assert plugin.name == "ECR"
    assert plugin.service_name == "ecr"
    assert plugin.has_flat_root is False


def test_get_root_nodes_returns_categories():
    session = make_session()
    plugin = ECRPlugin()
    nodes = plugin.get_root_nodes(session)

    labels = [n.label for n in nodes]
    assert "Private registry" in labels
    assert "Public registry" in labels
    assert all(n.node_type == "category" for n in nodes)


def test_get_children_of_private_registry_lists_repositories():
    session = make_session()
    client = session.client.return_value
    client.get_paginator.return_value.paginate.return_value = [
        {
            "repositories": [
                {
                    "repositoryName": "my-app",
                    "repositoryArn": "arn:aws:ecr:us-east-1:123:repository/my-app",
                    "registryId": "123",
                    "repositoryUri": "123.dkr.ecr.us-east-1.amazonaws.com/my-app",
                },
                {
                    "repositoryName": "other-app",
                    "repositoryArn": "arn:aws:ecr:us-east-1:123:repository/other-app",
                    "registryId": "123",
                    "repositoryUri": "123.dkr.ecr.us-east-1.amazonaws.com/other-app",
                },
            ]
        }
    ]

    node = TreeNode(
        id="ecr:category:private",
        label="Private registry",
        node_type="category",
        service="ecr",
        expandable=True,
        metadata={"category": "private"},
    )

    plugin = ECRPlugin()
    children = plugin.get_children(session, node)

    assert len(children) == 2
    assert children[0].label == "my-app"
    assert children[0].node_type == "private_repo"
    assert children[0].expandable is True
    assert children[0].metadata["repository_name"] == "my-app"


def test_get_children_of_public_registry_lists_repositories():
    session = make_session()
    client = session.client.return_value
    client.get_paginator.return_value.paginate.return_value = [
        {
            "repositories": [
                {
                    "repositoryName": "public-app",
                    "repositoryArn": "arn:aws:ecr-public::123:repository/public-app",
                    "registryId": "123",
                    "repositoryUri": "public.ecr.aws/123/public-app",
                }
            ]
        }
    ]

    node = TreeNode(
        id="ecr:category:public",
        label="Public registry",
        node_type="category",
        service="ecr",
        expandable=True,
        metadata={"category": "public"},
    )

    plugin = ECRPlugin()
    children = plugin.get_children(session, node)

    assert len(children) == 1
    assert children[0].label == "public-app"
    assert children[0].node_type == "public_repo"
    # ECR Public requires us-east-1
    session.client.assert_any_call("ecr-public", region_name="us-east-1")


def test_get_children_of_private_repo_lists_images():
    session = make_session()
    client = session.client.return_value
    client.get_paginator.return_value.paginate.return_value = [
        {
            "imageDetails": [
                {
                    "imageDigest": "sha256:aaaabbbbccccddddeeeeffff00001111",
                    "imageTags": ["latest", "v1.0"],
                    "imageSizeInBytes": 12345,
                },
                {
                    "imageDigest": "sha256:1111222233334444555566667777",
                    "imageTags": [],
                    "imageSizeInBytes": 67890,
                },
            ]
        }
    ]

    node = TreeNode(
        id="ecr:private_repo:my-app",
        label="my-app",
        node_type="private_repo",
        service="ecr",
        expandable=True,
        metadata={"repository_name": "my-app"},
    )

    plugin = ECRPlugin()
    children = plugin.get_children(session, node)

    assert len(children) == 2
    # Tagged image uses tags for label
    assert children[0].label == "latest, v1.0"
    assert children[0].node_type == "private_image"
    assert children[0].expandable is False
    # Untagged image falls back to digest prefix
    assert children[1].label.startswith("sha256:")


def test_get_children_of_public_repo_lists_images():
    session = make_session()
    client = session.client.return_value
    client.get_paginator.return_value.paginate.return_value = [
        {
            "imageDetails": [
                {
                    "imageDigest": "sha256:pubpubpubpubpubpub",
                    "imageTags": ["v2"],
                    "imageSizeInBytes": 500,
                }
            ]
        }
    ]

    node = TreeNode(
        id="ecr:public_repo:public-app",
        label="public-app",
        node_type="public_repo",
        service="ecr",
        expandable=True,
        metadata={"repository_name": "public-app"},
    )

    plugin = ECRPlugin()
    children = plugin.get_children(session, node)

    assert len(children) == 1
    assert children[0].label == "v2"
    assert children[0].node_type == "public_image"


def test_get_details_for_private_repo():
    session = make_session()
    client = session.client.return_value
    repo = {
        "repositoryName": "my-app",
        "repositoryArn": "arn:aws:ecr:us-east-1:123:repository/my-app",
        "registryId": "123",
        "repositoryUri": "123.dkr.ecr.us-east-1.amazonaws.com/my-app",
        "imageTagMutability": "MUTABLE",
        "imageScanningConfiguration": {"scanOnPush": True},
        "createdAt": "2026-01-01T00:00:00Z",
    }
    client.describe_repositories.return_value = {"repositories": [repo]}

    node = TreeNode(
        id="ecr:private_repo:my-app",
        label="my-app",
        node_type="private_repo",
        service="ecr",
        expandable=True,
        metadata={"repository_name": "my-app"},
    )

    plugin = ECRPlugin()
    details = plugin.get_details(session, node)

    assert details.title == "ECR Repository: my-app"
    assert details.subtitle == "arn:aws:ecr:us-east-1:123:repository/my-app"
    assert details.summary["Scan on Push"] == "True"


def test_get_details_for_private_image():
    session = make_session()
    client = session.client.return_value
    image = {
        "imageDigest": "sha256:abc",
        "imageTags": ["latest"],
        "imageSizeInBytes": 1234,
        "imagePushedAt": "2026-03-01T00:00:00Z",
        "imageManifestMediaType": "application/vnd.oci.image.manifest.v1+json",
    }
    client.describe_images.return_value = {"imageDetails": [image]}

    node = TreeNode(
        id="ecr:private_image:my-app:sha256:abc",
        label="latest",
        node_type="private_image",
        service="ecr",
        expandable=False,
        metadata={
            "repository_name": "my-app",
            "image_digest": "sha256:abc",
            "image_tags": ["latest"],
        },
    )

    plugin = ECRPlugin()
    details = plugin.get_details(session, node)

    assert details.title == "ECR Image: latest"
    assert details.summary["Digest"] == "sha256:abc"
    assert details.summary["Tags"] == "latest"


def test_get_details_for_category():
    session = make_session()
    node = TreeNode(
        id="ecr:category:private",
        label="Private registry",
        node_type="category",
        service="ecr",
        expandable=True,
        metadata={"category": "private"},
    )

    plugin = ECRPlugin()
    details = plugin.get_details(session, node)

    # Category details have empty summary so the app shows a count
    assert details.title == "Private registry"
    assert details.summary == {}

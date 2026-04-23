from __future__ import annotations

import boto3

from awstui.models import ResourceDetails, TreeNode
from awstui.plugin import AWSServicePlugin


class ECRPlugin(AWSServicePlugin):
    @property
    def name(self) -> str:
        return "ECR"

    @property
    def service_name(self) -> str:
        return "ecr"

    @property
    def has_flat_root(self) -> bool:
        return False

    def get_root_nodes(self, session: boto3.Session) -> list[TreeNode]:
        return [
            TreeNode(
                id="ecr:category:private",
                label="Private registry",
                node_type="category",
                service="ecr",
                expandable=True,
                metadata={"category": "private"},
            ),
            TreeNode(
                id="ecr:category:public",
                label="Public registry",
                node_type="category",
                service="ecr",
                expandable=True,
                metadata={"category": "public"},
            ),
        ]

    def get_children(self, session: boto3.Session, node: TreeNode) -> list[TreeNode]:
        if node.metadata.get("category") == "private":
            client = session.client("ecr")
            paginator = client.get_paginator("describe_repositories")
            nodes: list[TreeNode] = []
            for page in paginator.paginate():
                for repo in page.get("repositories", []):
                    name = repo["repositoryName"]
                    nodes.append(
                        TreeNode(
                            id=f"ecr:private_repo:{name}",
                            label=name,
                            node_type="private_repo",
                            service="ecr",
                            expandable=True,
                            metadata={
                                "repository_name": name,
                                "repository_arn": repo.get("repositoryArn", ""),
                                "registry_id": repo.get("registryId", ""),
                                "repository_uri": repo.get("repositoryUri", ""),
                            },
                        )
                    )
            return nodes

        if node.metadata.get("category") == "public":
            # ECR Public is only available in us-east-1.
            client = session.client("ecr-public", region_name="us-east-1")
            paginator = client.get_paginator("describe_repositories")
            nodes = []
            for page in paginator.paginate():
                for repo in page.get("repositories", []):
                    name = repo["repositoryName"]
                    nodes.append(
                        TreeNode(
                            id=f"ecr:public_repo:{name}",
                            label=name,
                            node_type="public_repo",
                            service="ecr",
                            expandable=True,
                            metadata={
                                "repository_name": name,
                                "repository_arn": repo.get("repositoryArn", ""),
                                "registry_id": repo.get("registryId", ""),
                                "repository_uri": repo.get("repositoryUri", ""),
                            },
                        )
                    )
            return nodes

        if node.node_type == "private_repo":
            client = session.client("ecr")
            paginator = client.get_paginator("describe_images")
            nodes = []
            for page in paginator.paginate(
                repositoryName=node.metadata["repository_name"]
            ):
                for image in page.get("imageDetails", []):
                    digest = image.get("imageDigest", "")
                    tags = image.get("imageTags", [])
                    label = ", ".join(tags) if tags else (digest[:19] or "<untagged>")
                    nodes.append(
                        TreeNode(
                            id=f"ecr:private_image:{node.metadata['repository_name']}:{digest}",
                            label=label,
                            node_type="private_image",
                            service="ecr",
                            expandable=False,
                            metadata={
                                "repository_name": node.metadata["repository_name"],
                                "image_digest": digest,
                                "image_tags": tags,
                            },
                        )
                    )
            return nodes

        if node.node_type == "public_repo":
            client = session.client("ecr-public", region_name="us-east-1")
            paginator = client.get_paginator("describe_images")
            nodes = []
            for page in paginator.paginate(
                repositoryName=node.metadata["repository_name"]
            ):
                for image in page.get("imageDetails", []):
                    digest = image.get("imageDigest", "")
                    tags = image.get("imageTags", [])
                    label = ", ".join(tags) if tags else (digest[:19] or "<untagged>")
                    nodes.append(
                        TreeNode(
                            id=f"ecr:public_image:{node.metadata['repository_name']}:{digest}",
                            label=label,
                            node_type="public_image",
                            service="ecr",
                            expandable=False,
                            metadata={
                                "repository_name": node.metadata["repository_name"],
                                "image_digest": digest,
                                "image_tags": tags,
                            },
                        )
                    )
            return nodes

        return []

    def get_details(self, session: boto3.Session, node: TreeNode) -> ResourceDetails:
        if node.node_type == "private_repo":
            client = session.client("ecr")
            response = client.describe_repositories(
                repositoryNames=[node.metadata["repository_name"]]
            )
            repo = response["repositories"][0]
            return ResourceDetails(
                title=f"ECR Repository: {repo['repositoryName']}",
                subtitle=repo.get("repositoryArn", ""),
                summary={
                    "Repository Name": repo["repositoryName"],
                    "Registry ID": repo.get("registryId", ""),
                    "URI": repo.get("repositoryUri", ""),
                    "Tag Mutability": repo.get("imageTagMutability", ""),
                    "Scan on Push": str(
                        repo.get("imageScanningConfiguration", {}).get(
                            "scanOnPush", False
                        )
                    ),
                    "Created": str(repo.get("createdAt", "")),
                },
                raw=repo,
            )

        if node.node_type == "public_repo":
            client = session.client("ecr-public", region_name="us-east-1")
            response = client.describe_repositories(
                repositoryNames=[node.metadata["repository_name"]]
            )
            repo = response["repositories"][0]
            return ResourceDetails(
                title=f"ECR Public Repository: {repo['repositoryName']}",
                subtitle=repo.get("repositoryArn", ""),
                summary={
                    "Repository Name": repo["repositoryName"],
                    "Registry ID": repo.get("registryId", ""),
                    "URI": repo.get("repositoryUri", ""),
                    "Created": str(repo.get("createdAt", "")),
                },
                raw=repo,
            )

        if node.node_type == "private_image":
            client = session.client("ecr")
            response = client.describe_images(
                repositoryName=node.metadata["repository_name"],
                imageIds=[{"imageDigest": node.metadata["image_digest"]}],
            )
            image = response["imageDetails"][0]
            return ResourceDetails(
                title=f"ECR Image: {node.label}",
                subtitle=node.metadata["image_digest"],
                summary={
                    "Repository": node.metadata["repository_name"],
                    "Digest": node.metadata["image_digest"],
                    "Tags": ", ".join(image.get("imageTags", [])) or "<untagged>",
                    "Size (bytes)": str(image.get("imageSizeInBytes", "")),
                    "Pushed": str(image.get("imagePushedAt", "")),
                    "Manifest Media Type": image.get("imageManifestMediaType", ""),
                    "Artifact Media Type": image.get("artifactMediaType", ""),
                },
                raw=image,
            )

        if node.node_type == "public_image":
            client = session.client("ecr-public", region_name="us-east-1")
            response = client.describe_images(
                repositoryName=node.metadata["repository_name"],
                imageIds=[{"imageDigest": node.metadata["image_digest"]}],
            )
            image = response["imageDetails"][0]
            return ResourceDetails(
                title=f"ECR Public Image: {node.label}",
                subtitle=node.metadata["image_digest"],
                summary={
                    "Repository": node.metadata["repository_name"],
                    "Digest": node.metadata["image_digest"],
                    "Tags": ", ".join(image.get("imageTags", [])) or "<untagged>",
                    "Size (bytes)": str(image.get("imageSizeInBytes", "")),
                    "Pushed": str(image.get("imagePushedAt", "")),
                    "Manifest Media Type": image.get("imageManifestMediaType", ""),
                    "Artifact Media Type": image.get("artifactMediaType", ""),
                },
                raw=image,
            )

        if node.node_type == "category":
            return ResourceDetails(
                title=node.label, subtitle="Expand to see resources", summary={}, raw={}
            )

        return ResourceDetails(title=node.label, subtitle="", summary={}, raw={})


plugin = ECRPlugin()

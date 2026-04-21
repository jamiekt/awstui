from __future__ import annotations

import json

import boto3

from awstui.models import ResourceDetails, TreeNode
from awstui.plugin import AWSServicePlugin


class IAMPlugin(AWSServicePlugin):
    @property
    def name(self) -> str:
        return "IAM"

    @property
    def service_name(self) -> str:
        return "iam"

    @property
    def has_flat_root(self) -> bool:
        return False

    def get_root_nodes(self, session: boto3.Session) -> list[TreeNode]:
        return [
            TreeNode(
                id="iam:category:users",
                label="Users",
                node_type="category",
                service="iam",
                expandable=True,
                metadata={"category": "users"},
            ),
            TreeNode(
                id="iam:category:roles",
                label="Roles",
                node_type="category",
                service="iam",
                expandable=True,
                metadata={"category": "roles"},
            ),
            TreeNode(
                id="iam:category:policies",
                label="Policies",
                node_type="category",
                service="iam",
                expandable=True,
                metadata={"category": "policies"},
            ),
            TreeNode(
                id="iam:category:groups",
                label="Groups",
                node_type="category",
                service="iam",
                expandable=True,
                metadata={"category": "groups"},
            ),
        ]

    def get_children(self, session: boto3.Session, node: TreeNode) -> list[TreeNode]:
        client = session.client("iam", region_name="us-east-1")

        if node.node_type == "category":
            return self._get_category_children(client, node)
        if node.node_type == "user":
            return self._get_user_subcategories(node)
        if node.node_type == "role":
            return self._get_role_subcategories(node)
        if node.node_type == "user_attached_policies":
            return self._get_user_attached_policies(client, node)
        if node.node_type == "user_inline_policies":
            return self._get_user_inline_policies(client, node)
        if node.node_type == "user_access_keys":
            return self._get_user_access_keys(client, node)
        if node.node_type == "role_attached_policies":
            return self._get_role_attached_policies(client, node)
        if node.node_type == "role_inline_policies":
            return self._get_role_inline_policies(client, node)
        if node.node_type == "role_trust_policy":
            return []
        return []

    def _get_category_children(self, client, node: TreeNode) -> list[TreeNode]:
        category = node.metadata["category"]
        if category == "users":
            paginator = client.get_paginator("list_users")
            nodes: list[TreeNode] = []
            for page in paginator.paginate():
                for user in page.get("Users", []):
                    nodes.append(
                        TreeNode(
                            id=f"iam:user:{user['UserName']}",
                            label=user["UserName"],
                            node_type="user",
                            service="iam",
                            expandable=True,
                            metadata={"user_name": user["UserName"]},
                        )
                    )
            return nodes
        if category == "roles":
            paginator = client.get_paginator("list_roles")
            nodes = []
            for page in paginator.paginate():
                for role in page.get("Roles", []):
                    nodes.append(
                        TreeNode(
                            id=f"iam:role:{role['RoleName']}",
                            label=role["RoleName"],
                            node_type="role",
                            service="iam",
                            expandable=True,
                            metadata={"role_name": role["RoleName"]},
                        )
                    )
            return nodes
        if category == "policies":
            paginator = client.get_paginator("list_policies")
            nodes = []
            for page in paginator.paginate(Scope="Local"):
                for policy in page.get("Policies", []):
                    nodes.append(
                        TreeNode(
                            id=f"iam:policy:{policy['PolicyName']}",
                            label=policy["PolicyName"],
                            node_type="policy",
                            service="iam",
                            expandable=False,
                            metadata={"policy_arn": policy["Arn"]},
                        )
                    )
            return nodes
        if category == "groups":
            paginator = client.get_paginator("list_groups")
            nodes = []
            for page in paginator.paginate():
                for group in page.get("Groups", []):
                    nodes.append(
                        TreeNode(
                            id=f"iam:group:{group['GroupName']}",
                            label=group["GroupName"],
                            node_type="group",
                            service="iam",
                            expandable=False,
                            metadata={"group_name": group["GroupName"]},
                        )
                    )
            return nodes
        return []

    def _get_user_subcategories(self, node: TreeNode) -> list[TreeNode]:
        user = node.metadata["user_name"]
        return [
            TreeNode(
                id=f"iam:user:{user}:attached_policies",
                label="Attached Policies",
                node_type="user_attached_policies",
                service="iam",
                expandable=True,
                metadata={"user_name": user},
            ),
            TreeNode(
                id=f"iam:user:{user}:inline_policies",
                label="Inline Policies",
                node_type="user_inline_policies",
                service="iam",
                expandable=True,
                metadata={"user_name": user},
            ),
            TreeNode(
                id=f"iam:user:{user}:access_keys",
                label="Access Keys",
                node_type="user_access_keys",
                service="iam",
                expandable=True,
                metadata={"user_name": user},
            ),
        ]

    def _get_role_subcategories(self, node: TreeNode) -> list[TreeNode]:
        role = node.metadata["role_name"]
        return [
            TreeNode(
                id=f"iam:role:{role}:attached_policies",
                label="Attached Policies",
                node_type="role_attached_policies",
                service="iam",
                expandable=True,
                metadata={"role_name": role},
            ),
            TreeNode(
                id=f"iam:role:{role}:inline_policies",
                label="Inline Policies",
                node_type="role_inline_policies",
                service="iam",
                expandable=True,
                metadata={"role_name": role},
            ),
            TreeNode(
                id=f"iam:role:{role}:trust_policy",
                label="Trust Policy",
                node_type="role_trust_policy",
                service="iam",
                expandable=False,
                metadata={"role_name": role},
            ),
        ]

    def _get_user_attached_policies(self, client, node: TreeNode) -> list[TreeNode]:
        response = client.list_attached_user_policies(
            UserName=node.metadata["user_name"]
        )
        return [
            TreeNode(
                id=f"iam:attached_policy:{p['PolicyArn']}",
                label=p["PolicyName"],
                node_type="attached_policy",
                service="iam",
                expandable=False,
                metadata={"policy_arn": p["PolicyArn"]},
            )
            for p in response.get("AttachedPolicies", [])
        ]

    def _get_user_inline_policies(self, client, node: TreeNode) -> list[TreeNode]:
        response = client.list_user_policies(UserName=node.metadata["user_name"])
        return [
            TreeNode(
                id=f"iam:inline_policy:{node.metadata['user_name']}:{name}",
                label=name,
                node_type="user_inline_policy",
                service="iam",
                expandable=False,
                metadata={"user_name": node.metadata["user_name"], "policy_name": name},
            )
            for name in response.get("PolicyNames", [])
        ]

    def _get_user_access_keys(self, client, node: TreeNode) -> list[TreeNode]:
        response = client.list_access_keys(UserName=node.metadata["user_name"])
        return [
            TreeNode(
                id=f"iam:access_key:{key['AccessKeyId']}",
                label=key["AccessKeyId"],
                node_type="access_key",
                service="iam",
                expandable=False,
                metadata={
                    "user_name": node.metadata["user_name"],
                    "access_key_id": key["AccessKeyId"],
                },
            )
            for key in response.get("AccessKeyMetadata", [])
        ]

    def _get_role_attached_policies(self, client, node: TreeNode) -> list[TreeNode]:
        response = client.list_attached_role_policies(
            RoleName=node.metadata["role_name"]
        )
        return [
            TreeNode(
                id=f"iam:attached_policy:{p['PolicyArn']}",
                label=p["PolicyName"],
                node_type="attached_policy",
                service="iam",
                expandable=False,
                metadata={"policy_arn": p["PolicyArn"]},
            )
            for p in response.get("AttachedPolicies", [])
        ]

    def _get_role_inline_policies(self, client, node: TreeNode) -> list[TreeNode]:
        response = client.list_role_policies(RoleName=node.metadata["role_name"])
        return [
            TreeNode(
                id=f"iam:inline_policy:{node.metadata['role_name']}:{name}",
                label=name,
                node_type="role_inline_policy",
                service="iam",
                expandable=False,
                metadata={"role_name": node.metadata["role_name"], "policy_name": name},
            )
            for name in response.get("PolicyNames", [])
        ]

    def get_details(self, session: boto3.Session, node: TreeNode) -> ResourceDetails:
        client = session.client("iam", region_name="us-east-1")

        if node.node_type == "user":
            response = client.get_user(UserName=node.metadata["user_name"])
            user = response["User"]
            return ResourceDetails(
                title=f"IAM User: {user['UserName']}",
                subtitle=user.get("Arn", ""),
                summary={
                    "User Name": user["UserName"],
                    "User ID": user.get("UserId", ""),
                    "ARN": user.get("Arn", ""),
                    "Created": str(user.get("CreateDate", "")),
                },
                raw=user,
            )

        if node.node_type == "role":
            response = client.get_role(RoleName=node.metadata["role_name"])
            role = response["Role"]
            return ResourceDetails(
                title=f"IAM Role: {role['RoleName']}",
                subtitle=role.get("Arn", ""),
                summary={
                    "Role Name": role["RoleName"],
                    "Role ID": role.get("RoleId", ""),
                    "ARN": role.get("Arn", ""),
                    "Created": str(role.get("CreateDate", "")),
                    "Description": role.get("Description", ""),
                    "Max Session (s)": str(role.get("MaxSessionDuration", "")),
                },
                raw=role,
            )

        if node.node_type == "policy":
            response = client.get_policy(PolicyArn=node.metadata["policy_arn"])
            policy = response["Policy"]
            return ResourceDetails(
                title=f"IAM Policy: {policy['PolicyName']}",
                subtitle=policy.get("Arn", ""),
                summary={
                    "Policy Name": policy["PolicyName"],
                    "ARN": policy.get("Arn", ""),
                    "Description": policy.get("Description", ""),
                    "Attachment Count": str(policy.get("AttachmentCount", 0)),
                    "Default Version": policy.get("DefaultVersionId", ""),
                    "Created": str(policy.get("CreateDate", "")),
                },
                raw=policy,
            )

        if node.node_type == "group":
            response = client.get_group(GroupName=node.metadata["group_name"])
            group = response["Group"]
            users = response.get("Users", [])
            return ResourceDetails(
                title=f"IAM Group: {group['GroupName']}",
                subtitle=group.get("Arn", ""),
                summary={
                    "Group Name": group["GroupName"],
                    "Group ID": group.get("GroupId", ""),
                    "ARN": group.get("Arn", ""),
                    "Created": str(group.get("CreateDate", "")),
                    "Members": ", ".join(u["UserName"] for u in users) or "None",
                },
                raw=response,
            )

        if node.node_type == "role_trust_policy":
            response = client.get_role(RoleName=node.metadata["role_name"])
            doc = response["Role"].get("AssumeRolePolicyDocument", {})
            return ResourceDetails(
                title=f"Trust Policy: {node.metadata['role_name']}",
                subtitle=f"IAM Role: {node.metadata['role_name']}",
                summary={"Policy Document": json.dumps(doc, indent=2)},
                raw=doc,
            )

        if node.node_type == "attached_policy":
            response = client.get_policy(PolicyArn=node.metadata["policy_arn"])
            policy = response["Policy"]
            return ResourceDetails(
                title=f"IAM Policy: {policy['PolicyName']}",
                subtitle=policy.get("Arn", ""),
                summary={
                    "Policy Name": policy["PolicyName"],
                    "ARN": policy.get("Arn", ""),
                    "Description": policy.get("Description", ""),
                },
                raw=policy,
            )

        if node.node_type == "user_inline_policy":
            response = client.get_user_policy(
                UserName=node.metadata["user_name"],
                PolicyName=node.metadata["policy_name"],
            )
            doc = response.get("PolicyDocument", {})
            return ResourceDetails(
                title=f"Inline Policy: {node.metadata['policy_name']}",
                subtitle=f"User: {node.metadata['user_name']}",
                summary={"Policy Document": json.dumps(doc, indent=2)},
                raw=response,
            )

        if node.node_type == "role_inline_policy":
            response = client.get_role_policy(
                RoleName=node.metadata["role_name"],
                PolicyName=node.metadata["policy_name"],
            )
            doc = response.get("PolicyDocument", {})
            return ResourceDetails(
                title=f"Inline Policy: {node.metadata['policy_name']}",
                subtitle=f"Role: {node.metadata['role_name']}",
                summary={"Policy Document": json.dumps(doc, indent=2)},
                raw=response,
            )

        if node.node_type == "access_key":
            return ResourceDetails(
                title=f"Access Key: {node.metadata['access_key_id']}",
                subtitle=f"User: {node.metadata['user_name']}",
                summary={
                    "Access Key ID": node.metadata["access_key_id"],
                    "User": node.metadata["user_name"],
                },
                raw={"AccessKeyId": node.metadata["access_key_id"]},
            )

        if node.node_type == "category":
            return ResourceDetails(
                title=node.label, subtitle="Expand to see resources", summary={}, raw={}
            )

        return ResourceDetails(title=node.label, subtitle="", summary={}, raw={})


plugin = IAMPlugin()

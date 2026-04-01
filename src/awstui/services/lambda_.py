from __future__ import annotations

import boto3

from awstui.models import ResourceDetails, TreeNode
from awstui.plugin import AWSServicePlugin


class LambdaPlugin(AWSServicePlugin):
    @property
    def name(self) -> str:
        return "Lambda"

    @property
    def service_name(self) -> str:
        return "lambda"

    def get_root_nodes(self, session: boto3.Session) -> list[TreeNode]:
        client = session.client("lambda")
        paginator = client.get_paginator("list_functions")
        nodes: list[TreeNode] = []
        for page in paginator.paginate():
            for func in page.get("Functions", []):
                nodes.append(
                    TreeNode(
                        id=f"lambda:function:{func['FunctionName']}",
                        label=func["FunctionName"],
                        node_type="function",
                        service="lambda",
                        expandable=False,
                        metadata={"function_name": func["FunctionName"]},
                    )
                )
        return nodes

    def get_children(self, session: boto3.Session, node: TreeNode) -> list[TreeNode]:
        return []

    def get_details(self, session: boto3.Session, node: TreeNode) -> ResourceDetails:
        client = session.client("lambda")
        response = client.get_function(FunctionName=node.metadata["function_name"])
        config = response["Configuration"]
        return ResourceDetails(
            title=f"Lambda Function: {config['FunctionName']}",
            subtitle=config.get("FunctionArn", ""),
            summary={
                "Function Name": config["FunctionName"],
                "Runtime": config.get("Runtime", "N/A"),
                "Handler": config.get("Handler", ""),
                "Description": config.get("Description", ""),
                "Code Size": str(config.get("CodeSize", "")),
                "Memory (MB)": str(config.get("MemorySize", "")),
                "Timeout (s)": str(config.get("Timeout", "")),
                "Last Modified": config.get("LastModified", ""),
            },
            raw=response,
        )


plugin = LambdaPlugin()

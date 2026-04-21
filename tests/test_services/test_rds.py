from unittest.mock import MagicMock

from awstui.services.rds import RDSPlugin


def make_session():
    return MagicMock()


def test_rds_plugin_properties():
    plugin = RDSPlugin()
    assert plugin.name == "RDS"
    assert plugin.service_name == "rds"


def test_get_root_nodes_returns_categories():
    session = make_session()
    plugin = RDSPlugin()
    nodes = plugin.get_root_nodes(session)

    assert len(nodes) == 2
    labels = [n.label for n in nodes]
    assert "DB Instances" in labels
    assert "DB Clusters" in labels
    assert all(n.expandable for n in nodes)
    assert all(n.node_type == "category" for n in nodes)


def test_get_children_of_instances_category():
    session = make_session()
    client = session.client.return_value
    client.describe_db_instances.return_value = {
        "DBInstances": [
            {
                "DBInstanceIdentifier": "mydb",
                "DBInstanceClass": "db.t3.micro",
                "Engine": "postgres",
                "DBInstanceArn": "arn:aws:rds:us-east-1:123:db:mydb",
            }
        ]
    }

    from awstui.models import TreeNode

    category_node = TreeNode(
        id="rds:category:instances",
        label="DB Instances",
        node_type="category",
        service="rds",
        expandable=True,
        metadata={"category": "instances"},
    )

    plugin = RDSPlugin()
    children = plugin.get_children(session, category_node)

    assert len(children) == 1
    assert children[0].label == "mydb"
    assert children[0].node_type == "db_instance"
    assert children[0].expandable is False


def test_get_children_of_clusters_category():
    session = make_session()
    client = session.client.return_value
    client.describe_db_clusters.return_value = {
        "DBClusters": [
            {
                "DBClusterIdentifier": "mycluster",
                "Engine": "aurora-mysql",
                "DBClusterArn": "arn:aws:rds:us-east-1:123:cluster:mycluster",
            }
        ]
    }

    from awstui.models import TreeNode

    category_node = TreeNode(
        id="rds:category:clusters",
        label="DB Clusters",
        node_type="category",
        service="rds",
        expandable=True,
        metadata={"category": "clusters"},
    )

    plugin = RDSPlugin()
    children = plugin.get_children(session, category_node)

    assert len(children) == 1
    assert children[0].label == "mycluster"
    assert children[0].node_type == "db_cluster"


def test_get_details_for_instance():
    session = make_session()
    client = session.client.return_value
    instance_data = {
        "DBInstanceIdentifier": "mydb",
        "DBInstanceClass": "db.t3.micro",
        "Engine": "postgres",
        "EngineVersion": "15.4",
        "DBInstanceStatus": "available",
        "DBInstanceArn": "arn:aws:rds:us-east-1:123:db:mydb",
        "Endpoint": {"Address": "mydb.xxx.us-east-1.rds.amazonaws.com", "Port": 5432},
        "AllocatedStorage": 20,
    }
    client.describe_db_instances.return_value = {"DBInstances": [instance_data]}

    from awstui.models import TreeNode

    node = TreeNode(
        id="rds:instance:mydb",
        label="mydb",
        node_type="db_instance",
        service="rds",
        expandable=False,
        metadata={"db_instance_id": "mydb"},
    )

    plugin = RDSPlugin()
    details = plugin.get_details(session, node)

    assert details.title == "RDS Instance: mydb"
    assert "Engine" in details.summary
    assert "Status" in details.summary

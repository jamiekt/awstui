import pytest
from unittest.mock import patch, MagicMock
from botocore.exceptions import NoCredentialsError

from awstui.app import AWSBrowserApp


@pytest.mark.asyncio
async def test_app_starts():
    """Test that the app can be instantiated and composed."""
    # Mock boto3 to avoid AWS credential issues
    with patch('awstui.app.boto3') as mock_boto3:
        mock_session = MagicMock()
        mock_session.region_name = "us-east-1"
        mock_boto3.Session.side_effect = NoCredentialsError()

        app = AWSBrowserApp()
        async with app.run_test(size=(120, 40)) as pilot:
            # App should start without crashing
            assert app.title == "awstui"


def test_find_arn_top_level():
    app = AWSBrowserApp()
    assert app._find_arn({"Arn": "arn:aws:iam::123:user/alice"}) == "arn:aws:iam::123:user/alice"


def test_find_arn_service_specific_key():
    app = AWSBrowserApp()
    raw = {"QueueArn": "arn:aws:sqs:us-east-1:123:my-queue", "Other": "x"}
    assert app._find_arn(raw) == "arn:aws:sqs:us-east-1:123:my-queue"


def test_find_arn_nested():
    app = AWSBrowserApp()
    raw = {"Configuration": {"FunctionArn": "arn:aws:lambda:us-east-1:123:function:f"}}
    assert app._find_arn(raw) == "arn:aws:lambda:us-east-1:123:function:f"


def test_find_arn_uppercase_key():
    app = AWSBrowserApp()
    assert app._find_arn({"ARN": "arn:aws:secretsmanager:us-east-1:123:secret:s"}) == "arn:aws:secretsmanager:us-east-1:123:secret:s"


def test_find_arn_ignores_non_arn_value():
    app = AWSBrowserApp()
    assert app._find_arn({"Arn": "not-an-arn"}) == ""


def test_find_arn_returns_empty_when_missing():
    app = AWSBrowserApp()
    assert app._find_arn({"Name": "foo", "Size": 42}) == ""


def test_find_arn_empty_input():
    app = AWSBrowserApp()
    assert app._find_arn({}) == ""


def test_noun_for_single_word():
    assert AWSBrowserApp._noun_for("Users") == "users"


def test_noun_for_multi_word():
    assert AWSBrowserApp._noun_for("DB Instances") == "instances"
    assert AWSBrowserApp._noun_for("Attached Policies") == "policies"
    assert AWSBrowserApp._noun_for("Access Keys") == "keys"


def test_noun_for_empty_label():
    assert AWSBrowserApp._noun_for("") == "items"
    assert AWSBrowserApp._noun_for("   ") == "items"


def test_pluralize_simple():
    assert AWSBrowserApp._pluralize("bucket") == "buckets"
    assert AWSBrowserApp._pluralize("function") == "functions"
    assert AWSBrowserApp._pluralize("queue") == "queues"
    assert AWSBrowserApp._pluralize("topic") == "topics"
    assert AWSBrowserApp._pluralize("secret") == "secrets"


def test_pluralize_sibilants():
    # keeps 'es' suffix behavior for words ending in s/x/z/ch/sh
    assert AWSBrowserApp._pluralize("box") == "boxes"


def test_pluralize_empty():
    assert AWSBrowserApp._pluralize("") == "items"

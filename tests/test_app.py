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

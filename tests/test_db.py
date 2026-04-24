from unittest.mock import MagicMock, patch

import database.db as db


# Verifies that the same artifact_id if the same request is still running
def test_find_in_progress_artifact_returns_existing():
    with patch("database.db.get_conn") as mock_get_conn:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {"artifact_id": "existing-id-123"}
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        result = db.find_in_progress_artifact("case123", "mothershipsg")

        assert result == "existing-id-123"


# Return None when there is no matching job in progress
def test_find_in_progress_artifact_returns_none_when_not_found():
    with patch("database.db.get_conn") as mock_get_conn:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        result = db.find_in_progress_artifact("case123", "mothershipsg")

        assert result is None

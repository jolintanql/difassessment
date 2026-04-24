import asyncio
import json
from unittest.mock import MagicMock, patch

import function_app


# Verifies that bad JSON gives a 400 error.
def test_validate_input_returns_400_for_invalid_json():
    mock_req = MagicMock()
    mock_req.get_json.side_effect = ValueError("invalid json")

    is_valid, response, body = function_app.validate_input(
        mock_req,
        ["case_id", "identifier", "description"],
    )

    assert is_valid is False
    assert response.status_code == 400
    assert json.loads(response.get_body().decode()) == {
        "message": "Invalid request body"
    }
    assert body == {}


# Verifies that missing fields are rejected
def test_validate_input_returns_400_when_fields_are_missing():
    mock_req = MagicMock()
    mock_req.get_json.return_value = {
        "case_id": "123",
        "identifier": "mothershipsg",
    }

    is_valid, response, body = function_app.validate_input(
        mock_req,
        ["case_id", "identifier", "description"],
    )

    assert is_valid is False
    assert response.status_code == 400
    assert "missing 'description'" in json.loads(response.get_body().decode())["message"]
    assert body == {}



# Verifies that a missing artifact returns 404
def test_get_artifact_returns_404_when_not_found():
    mock_req = MagicMock()
    mock_req.route_params = {"id": "missing-id"}

    with patch("function_app.db.get_artifact_by_id", return_value=None):
        response = asyncio.run(function_app.get_artifact(mock_req))

    assert response.status_code == 404
    assert json.loads(response.get_body().decode()) == {
        "message": "Artifact not found."
    }


# Verifies that the health endpoint returns ok
def test_healthcheck_returns_ok():
    mock_req = MagicMock()

    response = asyncio.run(function_app.healthcheck(mock_req))

    assert response.status_code == 200
    assert json.loads(response.get_body().decode()) == {"status": "ok"}

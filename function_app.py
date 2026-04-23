import os
import azure.functions as func
import azure.durable_functions as df
import database.db as db
import json
import uuid
from api_blueprint import api_bp
import logging
from typing import Optional, Tuple

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)

formatter = logging.Formatter(
    '%(asctime)s.%(msecs)03d:%(name)s:%(levelname)s| %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
console_handler.setFormatter(formatter)

logging.getLogger().addHandler(console_handler)

app = df.DFApp()
db.init_db()

app.register_blueprint(api_bp)


def error_response(response, status_code):
    if type(response) == bytes:
        payload = response
    else:
        payload = json.dumps({"message": response})
    return func.HttpResponse(
        payload,
        status_code=status_code,
        mimetype="application/json"
    )


def validate_input(req, expectedFields) -> tuple[bool, Optional[func.HttpResponse], dict]:
    try:
        request_body = req.get_json()
    except ValueError:
        return False, error_response("Invalid request body", 400), {}

    req_body = {}

    for expectedField in expectedFields:
        value = request_body.get(expectedField, -1)
        if value == -1:
            return False, error_response(f"Invalid request body, missing '{expectedField}'.", 400), {}
        else:
            req_body[expectedField] = value
    return True, None, req_body


@app.route(route="artifacts", auth_level=func.AuthLevel.ANONYMOUS, methods=["POST"])
@app.durable_client_input(client_name="client")
async def trigger_download(req: func.HttpRequest, client: df.DurableOrchestrationClient) -> func.HttpResponse:
    logging.info("Python HTTP artifact function processed a request.")
    try:
        try:
            request_body = req.get_json()
        except ValueError:
            return error_response("Invalid request body", 400)

        is_initial = all(k in request_body for k in [
                         "case_id", "identifier", "description"])
        is_pagination = all(k in request_body for k in [
                            "case_id", "artifact_id", "content_type"])

        if not is_initial and not is_pagination:
            return error_response(
                "Invalid request body. Expected either "
                "['case_id', 'identifier', 'description'] or "
                "['case_id', 'artifact_id', 'content_type'].",
                400
            )

        if is_initial:
            case_id = request_body["case_id"]
            identifier = request_body["identifier"]
            description = request_body["description"]

            existing_artifact_id = db.find_in_progress_artifact(
                case_id, identifier)
            if existing_artifact_id:
                return func.HttpResponse(
                    json.dumps({"artifact_id": existing_artifact_id}),
                    status_code=200,
                    mimetype="application/json"
                )

            artifact_id = uuid.uuid4().hex
            db.create_artifact_metadata(
                artifact_id, case_id, identifier, description)
            await client.start_new(
                "polling_orchestrator",
                None,
                json.dumps({
                    "artifact_id": artifact_id,
                    "case_id": case_id,
                    "identifier": identifier,
                    "description": description,
                })
            )
            return func.HttpResponse(
                json.dumps({"artifact_id": artifact_id}),
                status_code=200,
                mimetype="application/json"
            )

        # pagination request
        case_id = request_body["case_id"]
        artifact_id = request_body["artifact_id"]
        content_type = request_body["content_type"]

        if content_type not in ("post", "reel"):
            return error_response("content_type must be 'post' or 'reel'.", 400)

        ctx = db.get_pagination_context(artifact_id, content_type)
        if not ctx:
            return error_response("Artifact not found.", 404)

        await client.start_new(
            "polling_orchestrator",
            None,
            json.dumps({
                "artifact_id": artifact_id,
                "case_id": case_id,
                "identifier": ctx["identifier"],
                "content_type": content_type,
                "cursor": ctx["cursor"],
                "instagram_user_id": ctx["instagram_user_id"],
            })
        )
        return func.HttpResponse(
            json.dumps({"artifact_id": artifact_id}),
            status_code=200,
            mimetype="application/json"
        )

    except Exception as e:
        logging.error(e)
        return error_response("Internal server error.", 500)


@app.route(route="artifacts", auth_level=func.AuthLevel.ANONYMOUS, methods=["GET"])
async def list_all_artifacts(req: func.HttpRequest) -> func.HttpResponse:
    try:
        results = db.list_artifacts()
        return func.HttpResponse(
            json.dumps(results),
            status_code=200,
            mimetype="application/json"
        )
    except Exception as e:
        logging.error(e)
        return error_response("Internal server error.", 500)


@app.route(route="artifacts/{id}", auth_level=func.AuthLevel.ANONYMOUS, methods=["GET"])
async def get_artifact(req: func.HttpRequest) -> func.HttpResponse:
    try:
        artifact_id = req.route_params.get("id")
        result = db.get_artifact_by_id(artifact_id)

        if not result:
            return error_response("Artifact not found.", 404)

        return func.HttpResponse(
            json.dumps(result),
            status_code=200,
            mimetype="application/json"
        )
    except Exception as e:
        logging.error(e)
        return error_response("Internal server error.", 500)


@app.route(route="health", auth_level=func.AuthLevel.ANONYMOUS, methods=["GET"])
async def healthcheck(req: func.HttpRequest) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps({"status": "ok"}),
        status_code=200,
        mimetype="application/json"
    )


@app.route(route="blob/{blob_id}", auth_level=func.AuthLevel.ANONYMOUS, methods=["GET"])
async def serve_blob(req: func.HttpRequest) -> func.HttpResponse:
    try:
        blob_id = req.route_params.get("blob_id")
        blob = db.get_blob(blob_id)

        if not blob:
            return error_response("Blob not found.", 404)

        local_path = blob["local_path"]
        if not os.path.exists(local_path):
            return error_response("File not found on disk.", 404)

        with open(local_path, "rb") as f:
            data = f.read()

        return func.HttpResponse(
            body=data,
            status_code=200,
            mimetype=blob["mime_type"]
        )
    except Exception as e:
        logging.error(e)
        return error_response("Internal server error.", 500)

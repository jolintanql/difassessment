"""
This module defines the API blueprint for Azure Durable Functions, including orchestrator and activity functions.
It handles the orchestration of long-running processes, including triggering external API call and updating results and status in the database.
"""
import traceback
import azure.durable_functions as df
import json
import logging
from apis import external_api
from exceptions import APIException
import database.db as db

api_bp = df.Blueprint()


def activity_result_output(success, error_message, results=None):
    return {
        "success": success,
        "error_message": str(error_message),
        "results": results,
    } if results else {
        "success": success,
        "error_message": str(error_message)
    }

def invalid_execution(results):
    success = results["success"]
    if not success:
        return results["error_message"]
    return None


@api_bp.orchestration_trigger(context_name="context")
def polling_orchestrator(context: df.DurableOrchestrationContext):
    job = json.loads(context.get_input())

    case_info = {
        "artifact_id": job.get("artifact_id"),
        "case_id": job.get("case_id"),
        "identifier": job.get("identifier")
    }

    
    results = yield context.call_activity("startJob", job)

    if error := invalid_execution(results):
        job_status = case_info | {"status": "failed"}
        yield context.call_activity("updateStatus", job_status)
        return error

    job_status = case_info | {"status": "success"}
    yield context.call_activity("updateStatus", job_status)

    return "All tasks completed."

@api_bp.activity_trigger(input_name="jobInfo")
def startJob(jobInfo):
    artifact_id = jobInfo.get("artifact_id")
    case_id = jobInfo.get("case_id")
    identifier = jobInfo.get("identifier")
    content_type = jobInfo.get("content_type")
    cursor = jobInfo.get("cursor")
    instagram_user_id = jobInfo.get("instagram_user_id")

    logging.info(f"{artifact_id}:startJob")

    if content_type and not cursor:
        pagination_ctx = db.get_pagination_context(artifact_id, content_type)
        if pagination_ctx:
            cursor = pagination_ctx.get("cursor")
            instagram_user_id = pagination_ctx.get("instagram_user_id")
            identifier = pagination_ctx.get("identifier") or identifier

    try:
        resp = external_api.trigger_external(
            identifier=identifier,
            case_id=case_id,
            artifact_id=artifact_id,
            content_type=content_type,
            cursor=cursor,
            instagram_user_id=instagram_user_id,
        )

        if resp["status"] == "success":
            append = bool(content_type)
            results = db.update_results(artifact_id, resp["results"], append=append)
            return activity_result_output(True, "", results)

        raise APIException("API call failed.", 500, resp["status"], resp.get("error_message", ""))

    except Exception as e:
        logging.error(f"{artifact_id}: startJobError: {e}", exc_info=True)  # ✅ replaces traceback.print_exception
        return activity_result_output(False, str(e), None)

@api_bp.activity_trigger(input_name="jobStatus")
def updateStatus(jobStatus):
    artifact_id = jobStatus.get("artifact_id")
    case_id = jobStatus.get("case_id")
    status = jobStatus.get("status")
    try:
        db.update_metadata_status(artifact_id, case_id, status)
        return activity_result_output(True, f"{artifact_id}: updateStatus: Success")
    except Exception as e:
        logging.error(f"{artifact_id}: updateStatus: {e}")
        return activity_result_output(False, f"{artifact_id}: updateStatus: {e}")

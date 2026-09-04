"""
Media Pipeline: Ephemeral Serverless Transcode Dispatcher.

Offloads heavy video transformations (HDR->SDR tone-mapping, format conversion,
aspect auto-fitting) to serverless ephemeral containers (AWS ECS Fargate or Modal)
so the core VPS never runs out of CPU or disk (/tmp ENOSPC) during bulk uploads.

Falls back gracefully to local Celery FFmpeg processing when cloud credentials
are not configured (e.g. local dev, test environments).
"""
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

TRANSCODE_RUNNER = os.environ.get("TRANSCODE_RUNNER", "local").strip().lower()
AWS_ECS_CLUSTER = os.environ.get("AWS_ECS_CLUSTER", "")
AWS_ECS_TASK_DEFINITION = os.environ.get("AWS_ECS_TASK_DEFINITION", "unravler-transcoder")
AWS_ECS_SUBNETS = [s.strip() for s in os.environ.get("AWS_ECS_SUBNETS", "").split(",") if s.strip()]
AWS_ECS_SECURITY_GROUPS = [s.strip() for s in os.environ.get("AWS_ECS_SECURITY_GROUPS", "").split(",") if s.strip()]


def is_serverless_transcode_available() -> bool:
    """Return True if an ephemeral cloud transcode runner is configured."""
    if TRANSCODE_RUNNER == "fargate":
        return bool(AWS_ECS_CLUSTER and AWS_ECS_TASK_DEFINITION and AWS_ECS_SUBNETS)
    if TRANSCODE_RUNNER in {"modal", "cloud"}:
        return bool(os.environ.get("MODAL_TOKEN_ID") or os.environ.get("TRANSCODE_WEBHOOK_URL"))
    return False


async def dispatch_serverless_transcode(
    *,
    media_id: str,
    user_id: str,
    input_storage_key: str,
    output_storage_key: str,
    metadata: dict[str, Any],
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Dispatch an ephemeral transcoding container.
    Returns metadata dict containing job_id and runner status.
    """
    options = options or {}
    logger.info(
        "Dispatching serverless transcode: media_id=%s runner=%s input=%s output=%s",
        media_id,
        TRANSCODE_RUNNER,
        input_storage_key,
        output_storage_key,
    )

    if TRANSCODE_RUNNER == "fargate":
        return await _dispatch_ecs_fargate(
            media_id=media_id,
            user_id=user_id,
            input_storage_key=input_storage_key,
            output_storage_key=output_storage_key,
            metadata=metadata,
            options=options,
        )

    if TRANSCODE_RUNNER in {"modal", "cloud"}:
        return await _dispatch_modal_or_webhook(
            media_id=media_id,
            user_id=user_id,
            input_storage_key=input_storage_key,
            output_storage_key=output_storage_key,
            metadata=metadata,
            options=options,
        )

    raise RuntimeError(f"Serverless transcode runner '{TRANSCODE_RUNNER}' is not available or configured")


async def _dispatch_ecs_fargate(
    *,
    media_id: str,
    user_id: str,
    input_storage_key: str,
    output_storage_key: str,
    metadata: dict[str, Any],
    options: dict[str, Any],
) -> dict[str, Any]:
    """Trigger an AWS ECS Fargate task with 4-8 vCPUs for rapid parallel video transcoding."""
    import asyncio
    import boto3

    loop = asyncio.get_event_loop()

    def _run_task():
        ecs = boto3.client("ecs", region_name=os.environ.get("AWS_REGION", "us-east-1"))
        env_overrides = [
            {"name": "MEDIA_ID", "value": media_id},
            {"name": "USER_ID", "value": user_id},
            {"name": "INPUT_STORAGE_KEY", "value": input_storage_key},
            {"name": "OUTPUT_STORAGE_KEY", "value": output_storage_key},
            {"name": "NEEDS_HDR", "value": str(metadata.get("needs_hdr_conversion", False)).lower()},
            {"name": "TARGET_WIDTH", "value": str(options.get("width", 1080))},
            {"name": "TARGET_HEIGHT", "value": str(options.get("height", 1920))},
        ]
        response = ecs.run_task(
            cluster=AWS_ECS_CLUSTER,
            taskDefinition=AWS_ECS_TASK_DEFINITION,
            launchType="FARGATE",
            networkConfiguration={
                "awsvpcConfiguration": {
                    "subnets": AWS_ECS_SUBNETS,
                    "securityGroups": AWS_ECS_SECURITY_GROUPS,
                    "assignPublicIp": "ENABLED",
                }
            },
            overrides={
                "containerOverrides": [
                    {
                        "name": "transcoder",
                        "environment": env_overrides,
                    }
                ]
            },
        )
        tasks = response.get("tasks", [])
        if not tasks:
            failures = response.get("failures", [])
            raise RuntimeError(f"ECS run_task failed: {failures}")
        task_arn = tasks[0]["taskArn"]
        return task_arn

    task_arn = await loop.run_in_executor(None, _run_task)
    return {
        "job_id": task_arn,
        "runner": "fargate",
        "status": "dispatched",
        "media_id": media_id,
    }


async def _dispatch_modal_or_webhook(
    *,
    media_id: str,
    user_id: str,
    input_storage_key: str,
    output_storage_key: str,
    metadata: dict[str, Any],
    options: dict[str, Any],
) -> dict[str, Any]:
    """Trigger a serverless webhook (e.g. Modal Labs or custom worker) via HTTP POST."""
    import httpx

    webhook_url = os.environ.get("TRANSCODE_WEBHOOK_URL", "")
    if not webhook_url:
        raise RuntimeError("TRANSCODE_WEBHOOK_URL is not set for modal/cloud runner")

    payload = {
        "media_id": media_id,
        "user_id": user_id,
        "input_storage_key": input_storage_key,
        "output_storage_key": output_storage_key,
        "metadata": metadata,
        "options": options,
    }
    headers = {}
    auth_secret = os.environ.get("TRANSCODE_WEBHOOK_SECRET", "")
    if auth_secret:
        headers["Authorization"] = f"Bearer {auth_secret}"

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(webhook_url, json=payload, headers=headers)
        if resp.status_code not in (200, 201, 202):
            raise RuntimeError(f"Cloud transcode webhook failed ({resp.status_code}): {resp.text[:300]}")
        res_json = resp.json() if resp.content else {}

    return {
        "job_id": res_json.get("job_id", media_id),
        "runner": "cloud_webhook",
        "status": "dispatched",
        "media_id": media_id,
    }

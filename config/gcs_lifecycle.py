"""
Phase 10 -- Google Cloud Storage Lifecycle Policies.

Defines per-plan lifecycle rules for media storage, generates GCS-compatible
lifecycle JSON, and provides helpers for applying rules and detecting
orphaned files.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Plan Definitions
# ---------------------------------------------------------------------------

class SubscriptionPlan(str, Enum):
    FREE = "free"
    STARTER = "starter"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"


@dataclass(frozen=True)
class LifecyclePolicy:
    """Immutable lifecycle policy for a subscription plan."""

    plan: SubscriptionPlan
    description: str
    delete_after_days: int | None       # None = never auto-delete
    nearline_after_days: int | None     # None = no transition to Nearline
    coldline_after_days: int | None     # None = no transition to Coldline
    archive_after_days: int | None      # None = no transition to Archive


PLAN_POLICIES: dict[SubscriptionPlan, LifecyclePolicy] = {
    SubscriptionPlan.FREE: LifecyclePolicy(
        plan=SubscriptionPlan.FREE,
        description="Delete media 30 days after publishing",
        delete_after_days=30,
        nearline_after_days=None,
        coldline_after_days=None,
        archive_after_days=None,
    ),
    SubscriptionPlan.STARTER: LifecyclePolicy(
        plan=SubscriptionPlan.STARTER,
        description="Move to Nearline storage after 90 days",
        delete_after_days=None,
        nearline_after_days=90,
        coldline_after_days=None,
        archive_after_days=None,
    ),
    SubscriptionPlan.PROFESSIONAL: LifecyclePolicy(
        plan=SubscriptionPlan.PROFESSIONAL,
        description="Move to Coldline storage after 180 days",
        delete_after_days=None,
        nearline_after_days=None,
        coldline_after_days=180,
        archive_after_days=None,
    ),
    SubscriptionPlan.ENTERPRISE: LifecyclePolicy(
        plan=SubscriptionPlan.ENTERPRISE,
        description="No auto-deletion; archive after 365 days",
        delete_after_days=None,
        nearline_after_days=None,
        coldline_after_days=None,
        archive_after_days=365,
    ),
}


# ---------------------------------------------------------------------------
# Lifecycle Rule Generation
# ---------------------------------------------------------------------------

def generate_lifecycle_rules(plan: str) -> dict[str, Any]:
    """
    Generate GCS-compatible lifecycle JSON for the given subscription plan.

    Returns a dict matching the GCS Bucket.lifecycle_rules format:
    https://cloud.google.com/storage/docs/lifecycle

    Raises ValueError if the plan is unknown.
    """
    try:
        plan_enum = SubscriptionPlan(plan.lower())
    except ValueError:
        raise ValueError(
            f"Unknown plan '{plan}'. Valid plans: {[p.value for p in SubscriptionPlan]}"
        )

    policy = PLAN_POLICIES[plan_enum]
    rules: list[dict[str, Any]] = []

    # Delete rule
    if policy.delete_after_days is not None:
        rules.append({
            "action": {"type": "Delete"},
            "condition": {
                "age": policy.delete_after_days,
                "matchesPrefix": ["media/published/"],
            },
        })

    # Nearline transition
    if policy.nearline_after_days is not None:
        rules.append({
            "action": {
                "type": "SetStorageClass",
                "storageClass": "NEARLINE",
            },
            "condition": {
                "age": policy.nearline_after_days,
                "matchesStorageClass": ["STANDARD"],
            },
        })

    # Coldline transition
    if policy.coldline_after_days is not None:
        rules.append({
            "action": {
                "type": "SetStorageClass",
                "storageClass": "COLDLINE",
            },
            "condition": {
                "age": policy.coldline_after_days,
                "matchesStorageClass": ["STANDARD", "NEARLINE"],
            },
        })

    # Archive transition
    if policy.archive_after_days is not None:
        rules.append({
            "action": {
                "type": "SetStorageClass",
                "storageClass": "ARCHIVE",
            },
            "condition": {
                "age": policy.archive_after_days,
                "matchesStorageClass": ["STANDARD", "NEARLINE", "COLDLINE"],
            },
        })

    # Common: delete incomplete multipart uploads after 7 days
    rules.append({
        "action": {"type": "AbortIncompleteMultipartUpload"},
        "condition": {"age": 7},
    })

    # Common: delete temporary processing files after 1 day
    rules.append({
        "action": {"type": "Delete"},
        "condition": {
            "age": 1,
            "matchesPrefix": ["media/tmp/"],
        },
    })

    return {
        "lifecycle": {
            "rule": rules,
        },
        "plan": plan_enum.value,
        "description": policy.description,
    }


# ---------------------------------------------------------------------------
# Apply Lifecycle Rules
# ---------------------------------------------------------------------------

def apply_lifecycle_rules(bucket_name: str, plan: str) -> dict[str, Any]:
    """
    Apply lifecycle rules to a GCS bucket via the google-cloud-storage SDK.

    Returns a summary of applied rules.
    """
    from google.cloud import storage as gcs_storage

    rules_config = generate_lifecycle_rules(plan)
    rules = rules_config["lifecycle"]["rule"]

    client = gcs_storage.Client()
    bucket = client.get_bucket(bucket_name)

    # Clear existing rules and apply new ones
    bucket.lifecycle_rules = []

    for rule in rules:
        action = rule["action"]
        condition = rule["condition"]

        lifecycle_rule = {
            "action": action,
            "condition": condition,
        }
        bucket.add_lifecycle_rule(**_convert_to_sdk_format(action, condition))

    bucket.patch()

    logger.info(
        "Applied %d lifecycle rules to bucket '%s' (plan: %s)",
        len(rules), bucket_name, plan,
    )

    return {
        "bucket": bucket_name,
        "plan": plan,
        "rules_applied": len(rules),
        "applied_at": datetime.now(timezone.utc).isoformat(),
    }


def _convert_to_sdk_format(
    action: dict[str, Any],
    condition: dict[str, Any],
) -> dict[str, Any]:
    """
    Convert our rule format to google-cloud-storage SDK add_lifecycle_rule kwargs.
    """
    sdk_action = {"type": action["type"]}
    if "storageClass" in action:
        sdk_action["storageClass"] = action["storageClass"]

    sdk_condition = {}
    if "age" in condition:
        sdk_condition["age"] = condition["age"]
    if "matchesStorageClass" in condition:
        sdk_condition["matchesStorageClass"] = condition["matchesStorageClass"]
    if "matchesPrefix" in condition:
        sdk_condition["matchesPrefix"] = condition["matchesPrefix"]

    return {"action": sdk_action, "condition": sdk_condition}


# ---------------------------------------------------------------------------
# Orphaned File Detection
# ---------------------------------------------------------------------------

async def detect_orphaned_files(
    db,
    bucket_name: str,
    prefix: str = "media/",
    dry_run: bool = True,
) -> dict[str, Any]:
    """
    Cross-reference GCS objects with MongoDB post records to find orphaned files.

    An orphaned file is one that exists in GCS but has no corresponding post
    record in MongoDB (the post was deleted but the media was not cleaned up).

    Args:
        db: MongoDB database instance
        bucket_name: GCS bucket to scan
        prefix: Object prefix to scan (default: "media/")
        dry_run: If True, only report; if False, delete orphaned files

    Returns a summary of findings and actions taken.
    """
    from google.cloud import storage as gcs_storage

    client = gcs_storage.Client()
    bucket = client.bucket(bucket_name)

    # Collect all GCS object names under prefix
    gcs_objects: list[str] = []
    blobs = client.list_blobs(bucket, prefix=prefix)
    for blob in blobs:
        gcs_objects.append(blob.name)

    if not gcs_objects:
        return {
            "bucket": bucket_name,
            "prefix": prefix,
            "total_objects": 0,
            "orphaned": 0,
            "dry_run": dry_run,
        }

    # Get all media URLs referenced by posts
    referenced_paths: set[str] = set()
    cursor = db.posts.find(
        {"media_urls": {"$exists": True, "$ne": []}},
        {"media_urls": 1},
    )
    async for post in cursor:
        for url in post.get("media_urls", []):
            # Extract GCS path from full URL or store path directly
            if bucket_name in url:
                path = url.split(f"{bucket_name}/", 1)[-1]
                referenced_paths.add(path)
            elif url.startswith(prefix):
                referenced_paths.add(url)

    # Find orphans
    orphaned = [obj for obj in gcs_objects if obj not in referenced_paths]

    deleted_count = 0
    if not dry_run and orphaned:
        for obj_name in orphaned:
            try:
                bucket.blob(obj_name).delete()
                deleted_count += 1
            except Exception as exc:
                logger.warning("Failed to delete orphaned file %s: %s", obj_name, exc)

    if orphaned:
        logger.info(
            "Found %d orphaned files in gs://%s/%s (deleted: %d, dry_run: %s)",
            len(orphaned), bucket_name, prefix, deleted_count, dry_run,
        )

    return {
        "bucket": bucket_name,
        "prefix": prefix,
        "total_objects": len(gcs_objects),
        "referenced": len(referenced_paths),
        "orphaned": len(orphaned),
        "orphaned_files": orphaned[:50],  # Limit sample to 50
        "deleted": deleted_count,
        "dry_run": dry_run,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }

"""Start-up checks of the storage backends (docs/next_steps/dynamodb_storage/05 §2)."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from src.core.config import dynamo_region, settings

logger = logging.getLogger("examen.storage.startup")


def dynamo_kinds() -> List[str]:
    from src.core.storage.dynamo_schema import AUTH, OPS, USER

    kinds = []
    if settings.storage_backend == "dynamo":
        kinds.append(USER)
    if settings.auth_store_backend == "dynamo":
        kinds.append(AUTH)
    if settings.ops_store_backend == "dynamo":
        kinds.append(OPS)
    return kinds


def storage_summary() -> Dict[str, Any]:
    """Backend of each store and whether IAM tenant isolation is on (Health view; no user data)."""
    kinds = dynamo_kinds()
    return {
        "user": settings.storage_backend,
        "auth": settings.auth_store_backend,
        "ops": settings.ops_store_backend,
        "region": dynamo_region() if kinds else None,
        "tenant_isolation": bool(settings.dynamo_tenant_role_arn) if settings.storage_backend == "dynamo" else None,
    }


def check_storage() -> List[str]:
    """Problems that must stop the start-up; empty when every store is usable."""
    kinds = dynamo_kinds()
    if not kinds:
        return []
    problems: List[str] = []
    if not dynamo_region():
        problems.append("DYNAMO_REGION (or AWS_REGION) is not set")
        return problems
    if settings.dynamo_tenant_role_arn and not settings.auth_enabled:
        problems.append("DYNAMO_TENANT_ROLE_ARN requires AUTH_ENABLED=true (single-user mode has no tenant)")
    from src.core.storage.dynamo_client import service_client
    from src.core.storage.dynamo_schema import check_tables

    try:
        problems += check_tables(service_client(), kinds=kinds)
    except Exception as e:
        problems.append(f"DynamoDB unreachable: {type(e).__name__}")
    if settings.storage_backend == "dynamo" and settings.dynamo_tenant_role_arn and not problems:
        from src.core.storage.dynamo_client import _assume

        try:
            _assume("usr_" + "0" * 32)
        except Exception as e:
            problems.append(f"Tenant role cannot be assumed: {type(e).__name__}")
    return problems


def report_storage_startup() -> None:
    """Logs the storage configuration; raises RuntimeError when DynamoDB is misconfigured."""
    from src.core.service_log import report_event

    problems = check_storage()
    if problems:
        for problem in problems:
            report_event("storage.misconfigured", "critical", f"Storage misconfigured: {problem}",
                         component="storage", user_id=None)
        raise RuntimeError("Storage misconfigured: " + "; ".join(problems))
    backends = storage_summary()
    if backends["user"] == "dynamo" and not backends["tenant_isolation"]:
        report_event("storage.tenant_isolation_off", "warning",
                     "DynamoDB user store without IAM tenant isolation (DYNAMO_TENANT_ROLE_ARN not set)",
                     component="storage", user_id=None)
    if dynamo_kinds():
        logger.info(f"Storage backends: user={backends['user']} auth={backends['auth']} ops={backends['ops']} "
                    f"region={backends['region']} tenant_isolation={backends['tenant_isolation']}")

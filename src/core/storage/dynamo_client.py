"""DynamoDB clients: the service client and per-tenant scoped clients (docs/next_steps/dynamodb_storage/04 §3).

With ``DYNAMO_TENANT_ROLE_ARN`` set, a user's store gets a client whose credentials come from
``sts:AssumeRole`` with the session tag ``user_id``: the ``LeadingKeys`` policy of that role lets it
touch only that user's partition. Without it (local, tests, homelab) every store shares the service
client and isolation is application-only, as with SQLite.

botocore clients are thread-safe; one per tenant is cached and refreshed before its credentials expire.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("examen.storage.dynamo")

_REFRESH_MARGIN_S = 300
_lock = threading.Lock()
_service: Dict[Tuple[str, Optional[str]], Any] = {}
_tenants: Dict[str, Tuple[Any, float]] = {}
_tenant_locks: Dict[str, threading.Lock] = {}


def _config():
    from botocore.config import Config

    return Config(retries={"mode": "standard", "max_attempts": 8}, connect_timeout=5, read_timeout=20,
                  max_pool_connections=32)


def _session(**credentials: Any):
    import boto3

    from src.core.config import settings

    if not credentials and settings.aws_access_key_id and settings.aws_secret_access_key:
        credentials = {
            "aws_access_key_id": settings.aws_access_key_id,
            "aws_secret_access_key": settings.aws_secret_access_key,
            "aws_session_token": settings.aws_session_token,
        }
    return boto3.session.Session(**credentials)


def service_client() -> Any:
    """Client with the process credentials: auth, ops, and tenant data when no tenant role is set."""
    from src.core.config import dynamo_region, settings

    key = (dynamo_region(), settings.dynamo_endpoint_url or None)
    with _lock:
        client = _service.get(key)
        if client is None:
            client = _session().client("dynamodb", region_name=key[0], endpoint_url=key[1], config=_config())
            _service[key] = client
        return client


def tenant_isolation_enabled() -> bool:
    from src.core.config import settings

    return bool(settings.dynamo_tenant_role_arn)


def _assume(user_id: str) -> Tuple[Any, float]:
    from src.core.config import dynamo_region, settings

    sts = _session().client("sts", region_name=dynamo_region(), config=_config())
    response = sts.assume_role(
        RoleArn=settings.dynamo_tenant_role_arn,
        RoleSessionName=f"examen-{user_id[:24]}",
        Tags=[{"Key": "user_id", "Value": user_id}],
        DurationSeconds=3600,
    )
    creds = response["Credentials"]
    session = _session(aws_access_key_id=creds["AccessKeyId"], aws_secret_access_key=creds["SecretAccessKey"],
                       aws_session_token=creds["SessionToken"])
    client = session.client("dynamodb", region_name=dynamo_region(),
                            endpoint_url=settings.dynamo_endpoint_url or None, config=_config())
    expires = creds["Expiration"]
    expires_at = expires.timestamp() if hasattr(expires, "timestamp") else time.time() + 3600
    return client, expires_at


def tenant_client(user_id: str) -> Any:
    """The client a user's store uses: scoped to that user's partition when isolation is on."""
    if not tenant_isolation_enabled():
        return service_client()
    with _lock:
        cached = _tenants.get(user_id)
        if cached and cached[1] - time.time() > _REFRESH_MARGIN_S:
            return cached[0]
        user_lock = _tenant_locks.setdefault(user_id, threading.Lock())
    with user_lock:
        with _lock:
            cached = _tenants.get(user_id)
            if cached and cached[1] - time.time() > _REFRESH_MARGIN_S:
                return cached[0]
        client, expires_at = _assume(user_id)
        with _lock:
            _tenants[user_id] = (client, expires_at)
        logger.info(f"Scoped DynamoDB credentials issued for tenant {user_id}")
        return client


def drop_tenant_client(user_id: str) -> None:
    with _lock:
        _tenants.pop(user_id, None)
        _tenant_locks.pop(user_id, None)


def reset_clients() -> None:
    """Test seam: forget every cached client."""
    with _lock:
        _service.clear()
        _tenants.clear()
        _tenant_locks.clear()

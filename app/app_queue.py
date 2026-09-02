"""Redis queue boundary for long-running Ansible and Kubernetes Job work."""
from __future__ import annotations

import json
import os
import uuid

from redis.asyncio import Redis

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
redis = Redis.from_url(REDIS_URL, decode_responses=True)


async def enqueue_job(kind: str, payload: dict) -> str:
    job_id = str(uuid.uuid4())
    await redis.rpush("devops-ai:jobs", json.dumps({"id": job_id, "kind": kind, "payload": payload}))
    return job_id

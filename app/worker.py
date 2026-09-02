"""Queue worker entry point; run as a separate deployment/process."""
import asyncio
import json

from app_queue import redis


async def main() -> None:
    while True:
        item = await redis.blpop("devops-ai:jobs", timeout=30)
        if item:
            _, raw = item
            job = json.loads(raw)
            # Dispatch approved jobs to Kubernetes Jobs or Ansible Runner here.
            print(json.dumps({"event": "job_received", "job_id": job["id"], "kind": job["kind"]}))


if __name__ == "__main__":
    asyncio.run(main())

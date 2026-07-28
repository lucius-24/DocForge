import os
import shutil
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class Job:
    id: str
    created_at: float
    status: str = "queued"  # queued|running|succeeded|failed
    error: Optional[str] = None
    outputs: Dict[str, str] = field(default_factory=dict)  # format -> abs path
    cancel_requested: bool = False


class JobStore:
    def __init__(self, base_dir: str):
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)
        self._lock = threading.Lock()
        self._jobs: Dict[str, Job] = {}

    def create(self) -> Job:
        job_id = uuid.uuid4().hex
        job = Job(id=job_id, created_at=time.time())
        with self._lock:
            self._jobs[job_id] = job
        os.makedirs(self.job_dir(job_id), exist_ok=True)
        return job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def update(self, job_id: str, **kwargs) -> Optional[Job]:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            for k, v in kwargs.items():
                setattr(job, k, v)
            return job

    def job_dir(self, job_id: str) -> str:
        return os.path.join(self.base_dir, job_id)

    def cleanup_older_than(self, seconds: int) -> int:
        now = time.time()
        to_delete = []
        with self._lock:
            for job_id, job in list(self._jobs.items()):
                if now - job.created_at > seconds:
                    to_delete.append(job_id)
                    self._jobs.pop(job_id, None)
        for job_id in to_delete:
            try:
                shutil.rmtree(self.job_dir(job_id), ignore_errors=True)
            except Exception:
                pass
        return len(to_delete)

    def cleanup_with_policy(
        self,
        success_ttl_seconds: int,
        failed_ttl_seconds: int,
        max_job_dirs: int,
        max_total_bytes: int,
    ) -> Dict[str, int]:
        now = time.time()
        with self._lock:
            jobs_snapshot = dict(self._jobs)

        deleted_ids = set()
        expired_deleted = 0

        for job_id, job in jobs_snapshot.items():
            age = now - float(job.created_at or now)
            if job.status == "succeeded" and age > max(0, int(success_ttl_seconds)):
                deleted_ids.add(job_id)
            elif job.status == "failed" and age > max(0, int(failed_ttl_seconds)):
                deleted_ids.add(job_id)

        for job_id in list(deleted_ids):
            try:
                shutil.rmtree(self.job_dir(job_id), ignore_errors=True)
            except Exception:
                pass
            expired_deleted += 1

        dir_infos = []
        try:
            entries = os.listdir(self.base_dir)
        except Exception:
            entries = []

        for name in entries:
            path = self.job_dir(name)
            if not os.path.isdir(path):
                continue
            if name in deleted_ids:
                continue
            job = jobs_snapshot.get(name)
            status = job.status if job else "orphan"
            if status in ("queued", "running"):
                continue
            if job:
                created_at = float(job.created_at or now)
            else:
                try:
                    created_at = os.path.getmtime(path)
                except Exception:
                    created_at = now
            total_size = 0
            try:
                for root, _, files in os.walk(path):
                    for fn in files:
                        fp = os.path.join(root, fn)
                        try:
                            total_size += os.path.getsize(fp)
                        except Exception:
                            pass
            except Exception:
                pass
            dir_infos.append(
                {
                    "job_id": name,
                    "path": path,
                    "created_at": created_at,
                    "size": total_size,
                }
            )

        dir_infos.sort(key=lambda x: x["created_at"])

        limit_deleted = 0
        current_count = len(dir_infos)
        current_size = sum(x["size"] for x in dir_infos)
        must_delete_ids = set()
        for info in dir_infos:
            over_count = current_count > max(0, int(max_job_dirs))
            over_size = current_size > max(0, int(max_total_bytes))
            if not over_count and not over_size:
                break
            must_delete_ids.add(info["job_id"])
            current_count -= 1
            current_size -= info["size"]

        for info in dir_infos:
            if info["job_id"] not in must_delete_ids:
                continue
            try:
                shutil.rmtree(info["path"], ignore_errors=True)
            except Exception:
                pass
            deleted_ids.add(info["job_id"])
            limit_deleted += 1

        if deleted_ids:
            with self._lock:
                for job_id in deleted_ids:
                    self._jobs.pop(job_id, None)

        return {
            "deleted_expired": expired_deleted,
            "deleted_limited": limit_deleted,
            "deleted_total": expired_deleted + limit_deleted,
        }


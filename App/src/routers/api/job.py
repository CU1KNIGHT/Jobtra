from fastapi import APIRouter, HTTPException

import db
from util import Job, JobInput

router = APIRouter(tags=["job","api"])

@router.get("/api/jobs", response_model=list[Job])
def list_jobs():
    return db.list_jobs()


@router.get("/api/jobs/{job_id}", response_model=Job)
def get_job(job_id: int):
    job = db.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/api/jobs", response_model=Job, status_code=201)
def create_job(payload: JobInput):
    return db.create_job(payload.model_dump())


@router.put("/api/jobs/{job_id}", response_model=Job)
def update_job(job_id: int, payload: JobInput):
    if db.get_job(job_id) is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return db.update_job(job_id, payload.model_dump())


@router.delete("/api/jobs/{job_id}")
def delete_job(job_id: int):
    if not db.delete_job(job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    return {"deleted": True}


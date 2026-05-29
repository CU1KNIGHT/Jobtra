import hashlib
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, Query, APIRouter, UploadFile, File
from fastapi.responses import StreamingResponse

import db
from config import DOCS_DIR

# ── Document library ──────────────────────────────────────────────────────────
router = APIRouter(tags=["document"])

@router.get("/api/documents")
def list_documents(job_id: Optional[int] = Query(None)):
    return db.list_documents(job_id=job_id)


@router.post("/api/documents", status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    doc_type: str = "other",
    notes: str = "",
):
    file_bytes = await file.read()
    file_hash = hashlib.sha256(file_bytes).hexdigest()
    ext = Path(file.filename).suffix
    existing = db.get_document_by_hash(file_hash)
    if existing:
        return existing
    file_path = DOCS_DIR / f"{file_hash}{ext}"
    file_path.write_bytes(file_bytes)
    return db.create_document({
        "filename": file.filename,
        "doc_type": doc_type,
        "file_path": str(file_path),
        "file_hash": file_hash,
        "file_size": len(file_bytes),
        "notes": notes,
    })


@router.get("/api/documents/{doc_id}/download")
def download_document(doc_id: int):
    doc = db.get_document(doc_id)
    if doc is None:
        raise HTTPException(404, "Document not found")
    file_path = Path(doc["file_path"])
    if not file_path.exists():
        raise HTTPException(404, "File not found on disk")
    filename = doc["filename"].encode("ascii", "replace").decode("ascii")
    return StreamingResponse(
        open(file_path, "rb"),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/api/documents/{doc_id}", status_code=204)
def delete_document(doc_id: int):
    doc = db.get_document(doc_id)
    if doc is None:
        raise HTTPException(404, "Document not found")
    count = db.count_job_documents(doc_id)
    if count > 0:
        jobs = db.get_jobs_for_document(doc_id)
        raise HTTPException(409, {"error": "Document still attached to jobs", "jobs": jobs})
    file_path = Path(doc["file_path"])
    if file_path.exists():
        file_path.unlink()
    db.delete_document(doc_id)


@router.get("/api/jobs/{job_id}/documents")
def list_job_documents(job_id: int):
    if db.get_job(job_id) is None:
        raise HTTPException(404, "Job not found")
    return db.get_job_documents(job_id)


@router.post("/api/jobs/{job_id}/documents", status_code=201)
async def attach_document(
    job_id: int,
    file: Optional[UploadFile] = File(None),
    doc_type: str = "other",
    notes: str = "",
    document_id: Optional[int] = None,
):
    if db.get_job(job_id) is None:
        raise HTTPException(404, "Job not found")

    if document_id is not None:
        doc = db.get_document(document_id)
        if doc is None:
            raise HTTPException(404, "Document not found")
    elif file is not None:
        file_bytes = await file.read()
        file_hash = hashlib.sha256(file_bytes).hexdigest()
        ext = Path(file.filename).suffix
        existing = db.get_document_by_hash(file_hash)
        if existing:
            doc = existing
        else:
            file_path = DOCS_DIR / f"{file_hash}{ext}"
            file_path.write_bytes(file_bytes)
            doc = db.create_document({
                "filename": file.filename,
                "doc_type": doc_type,
                "file_path": str(file_path),
                "file_hash": file_hash,
                "file_size": len(file_bytes),
                "notes": notes,
            })
        document_id = doc["id"]
    else:
        raise HTTPException(400, "Provide a file or document_id")

    link = db.attach_document_to_job(job_id, document_id)
    return {"document": db.get_document(document_id), "link": link}


@router.delete("/api/jobs/{job_id}/documents/{doc_id}", status_code=204)
def detach_document(job_id: int, doc_id: int):
    if not db.detach_document_from_job(job_id, doc_id):
        raise HTTPException(404, "Link not found")



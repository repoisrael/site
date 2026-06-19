from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
import zipfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

APP_DIR = Path(__file__).resolve().parent
ROOT_DIR = APP_DIR.parent
STATIC_DIR = APP_DIR / "static"
WORK_DIR = Path(os.getenv("STEMRIP_WORKDIR", ROOT_DIR / "data")).resolve()
UPLOAD_DIR = WORK_DIR / "uploads"
JOB_DIR = WORK_DIR / "jobs"
MAX_UPLOAD_MB = int(os.getenv("STEMRIP_MAX_UPLOAD_MB", "500"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024

ALLOWED_EXTENSIONS = {".wav", ".mp3", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".aiff", ".aif", ".wma"}
AUDIO_OUTPUT_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg"}
VALID_MODES = {"vocals", "four_stems", "six_stems"}
VALID_MODELS = {"htdemucs", "htdemucs_ft", "htdemucs_6s", "mdx", "mdx_extra", "mdx_q", "mdx_extra_q"}

for folder in (UPLOAD_DIR, JOB_DIR):
    folder.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="StemRip Local", version="1.0.0")
_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = threading.Lock()


def now_ts() -> float:
    return time.time()


def sanitize_filename(filename: str | None) -> str:
    if not filename:
        return "audio"
    name = Path(filename).name
    name = re.sub(r"[^A-Za-z0-9._ -]+", "_", name).strip(" .")
    return name or "audio"


def job_update(job_id: str, **updates: Any) -> None:
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id].update(updates)
            _jobs[job_id]["updated_at"] = now_ts()


def job_log(job_id: str, line: str) -> None:
    clean = line.rstrip()
    if not clean:
        return
    with _jobs_lock:
        if job_id not in _jobs:
            return
        logs = _jobs[job_id].setdefault("logs", [])
        logs.append(clean)
        if len(logs) > 250:
            del logs[: len(logs) - 250]
        _jobs[job_id]["updated_at"] = now_ts()


def public_job(job_id: str) -> dict[str, Any]:
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        result = dict(job)
        result["logs"] = list(job.get("logs", []))[-120:]
        result["files"] = [
            {"index": i, "name": Path(p).name, "download_url": f"/api/jobs/{job_id}/download/{i}"}
            for i, p in enumerate(job.get("files", []))
        ]
        if job.get("zip_path"):
            result["zip_url"] = f"/api/jobs/{job_id}/download.zip"
        return result


def build_demucs_command(upload_path: Path, output_dir: Path, mode: str, model: str, shifts: int) -> list[str]:
    if mode == "six_stems":
        model = "htdemucs_6s"

    command = [
        sys.executable,
        "-m",
        "demucs",
        "-n",
        model,
        "-o",
        str(output_dir),
        "--shifts",
        str(shifts),
    ]

    if mode == "vocals":
        command.extend(["--two-stems", "vocals"])

    command.append(str(upload_path))
    return command


def collect_audio_files(output_dir: Path) -> list[Path]:
    files = [p for p in output_dir.rglob("*") if p.is_file() and p.suffix.lower() in AUDIO_OUTPUT_EXTENSIONS]
    order = {"vocals": 0, "drums": 1, "bass": 2, "guitar": 3, "piano": 4, "other": 5, "no_vocals": 6}
    return sorted(files, key=lambda p: (order.get(p.stem.lower(), 99), p.name.lower()))


def make_zip(job_id: str, files: list[Path]) -> Path:
    zip_path = JOB_DIR / job_id / "stems.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        used_names: set[str] = set()
        for file_path in files:
            arcname = file_path.name
            if arcname in used_names:
                arcname = f"{file_path.parent.name}_{file_path.name}"
            used_names.add(arcname)
            archive.write(file_path, arcname=arcname)
    return zip_path


def run_separation(job_id: str, upload_path: Path, mode: str, model: str, shifts: int) -> None:
    job_root = JOB_DIR / job_id
    separated_dir = job_root / "separated"
    separated_dir.mkdir(parents=True, exist_ok=True)

    job_update(job_id, status="running", stage="separating", started_at=now_ts())
    command = build_demucs_command(upload_path, separated_dir, mode, model, shifts)
    job_log(job_id, "Running: " + " ".join(command))

    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    except Exception as exc:
        job_update(job_id, status="failed", stage="error", error=f"Could not start Demucs: {exc}", finished_at=now_ts())
        return

    assert process.stdout is not None
    for line in process.stdout:
        job_log(job_id, line)

    return_code = process.wait()
    if return_code != 0:
        job_update(
            job_id,
            status="failed",
            stage="error",
            error=f"Demucs exited with code {return_code}. Check logs. FFmpeg may be missing for compressed formats.",
            finished_at=now_ts(),
        )
        return

    files = collect_audio_files(separated_dir)
    if not files:
        job_update(job_id, status="failed", stage="error", error="Demucs finished, but no stem files were found.", finished_at=now_ts())
        return

    zip_path = make_zip(job_id, files)
    job_update(job_id, status="complete", stage="done", files=[str(p) for p in files], zip_path=str(zip_path), finished_at=now_ts())
    job_log(job_id, f"Done. Created {len(files)} stem files.")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/jobs")
async def create_job(file: UploadFile = File(...), mode: str = Form("four_stems"), model: str = Form("htdemucs"), shifts: int = Form(1)) -> dict[str, Any]:
    if mode not in VALID_MODES:
        raise HTTPException(status_code=400, detail=f"Invalid mode. Use one of: {', '.join(sorted(VALID_MODES))}")
    if model not in VALID_MODELS:
        raise HTTPException(status_code=400, detail=f"Invalid model. Use one of: {', '.join(sorted(VALID_MODELS))}")
    if shifts < 1 or shifts > 10:
        raise HTTPException(status_code=400, detail="shifts must be between 1 and 10")

    original_name = sanitize_filename(file.filename)
    extension = Path(original_name).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {extension or 'none'}")

    job_id = uuid.uuid4().hex
    upload_path = UPLOAD_DIR / f"{job_id}{extension}"

    total = 0
    try:
        with upload_path.open("wb") as out:
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    out.close()
                    upload_path.unlink(missing_ok=True)
                    raise HTTPException(status_code=413, detail=f"File too large. Max upload is {MAX_UPLOAD_MB} MB.")
                out.write(chunk)
    finally:
        await file.close()

    if total == 0:
        upload_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    actual_model = "htdemucs_6s" if mode == "six_stems" else model
    with _jobs_lock:
        _jobs[job_id] = {
            "id": job_id,
            "status": "queued",
            "stage": "queued",
            "original_name": original_name,
            "mode": mode,
            "model": actual_model,
            "shifts": shifts,
            "upload_bytes": total,
            "created_at": now_ts(),
            "updated_at": now_ts(),
            "logs": ["Job queued."],
            "files": [],
            "zip_path": None,
            "error": None,
        }

    thread = threading.Thread(target=run_separation, args=(job_id, upload_path, mode, actual_model, shifts), daemon=True)
    thread.start()
    return public_job(job_id)


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    return public_job(job_id)


@app.get("/api/jobs/{job_id}/download/{file_index}")
def download_stem(job_id: str, file_index: int) -> FileResponse:
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        if job.get("status") != "complete":
            raise HTTPException(status_code=409, detail="Job is not complete")
        files = [Path(p) for p in job.get("files", [])]

    if file_index < 0 or file_index >= len(files):
        raise HTTPException(status_code=404, detail="File not found")

    file_path = files[file_index].resolve()
    if not file_path.exists() or JOB_DIR not in file_path.parents:
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path, filename=file_path.name, media_type="audio/wav")


@app.get("/api/jobs/{job_id}/download.zip")
def download_zip(job_id: str) -> FileResponse:
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        if job.get("status") != "complete" or not job.get("zip_path"):
            raise HTTPException(status_code=409, detail="Job is not complete")
        zip_path = Path(job["zip_path"]).resolve()

    if not zip_path.exists() or JOB_DIR not in zip_path.parents:
        raise HTTPException(status_code=404, detail="ZIP not found")
    stem_name = Path(job.get("original_name") or "stems").stem
    return FileResponse(zip_path, filename=f"{stem_name}_stems.zip", media_type="application/zip")


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: str) -> dict[str, str]:
    with _jobs_lock:
        job = _jobs.pop(job_id, None)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    shutil.rmtree(JOB_DIR / job_id, ignore_errors=True)
    for uploaded in UPLOAD_DIR.glob(f"{job_id}.*"):
        uploaded.unlink(missing_ok=True)
    return {"status": "deleted"}


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

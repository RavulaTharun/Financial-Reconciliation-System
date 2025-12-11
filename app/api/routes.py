import os
import json
import zipfile
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from app.core.config import config
from app.core.storage import run_storage
from app.core.utils import get_agent_logger

logger = get_agent_logger("api")

router = APIRouter()

class StartResponse(BaseModel):
    run_id: str
    status: str
    message: str

class StatusResponse(BaseModel):
    run_id: str
    status: str
    progress: int
    current_step: str
    steps_completed: List[str]
    errors: List[str]
    output_files: List[str]

def run_reconciliation_async(run_id: str):
    from app.agents.orchestrator import orchestrator
    try:
        orchestrator.run(run_id)
    except Exception as e:
        logger.error(f"[API] Reconciliation failed for run_id={run_id}: {str(e)}")
        run_storage.update_run(run_id, status="failed", errors=[str(e)])

@router.post("/start", response_model=StartResponse)
async def start_reconciliation(background_tasks: BackgroundTasks):
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    logger.info(f"[API] Starting reconciliation run_id={run_id}")
    
    run_storage.create_run(run_id)
    
    background_tasks.add_task(run_reconciliation_async, run_id)
    
    return StartResponse(
        run_id=run_id,
        status="started",
        message=f"Reconciliation started with run_id: {run_id}"
    )

@router.get("/status/{run_id}", response_model=StatusResponse)
async def get_status(run_id: str):
    run_data = run_storage.get_run(run_id)
    
    if not run_data:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    
    return StatusResponse(
        run_id=run_id,
        status=run_data.get("status", "unknown"),
        progress=run_data.get("progress", 0),
        current_step=run_data.get("current_step", ""),
        steps_completed=run_data.get("steps_completed", []),
        errors=run_data.get("errors", []),
        output_files=run_data.get("output_files", [])
    )

@router.get("/logs/{run_id}")
async def get_logs(run_id: str):
    logs_dir = config.LOGS_DIR
    
    all_logs = []
    
    if os.path.exists(logs_dir):
        for filename in os.listdir(logs_dir):
            if filename.startswith(run_id) and filename.endswith(".json"):
                filepath = os.path.join(logs_dir, filename)
                try:
                    with open(filepath, "r") as f:
                        logs = json.load(f)
                        if isinstance(logs, list):
                            all_logs.extend(logs)
                        else:
                            all_logs.append(logs)
                except (json.JSONDecodeError, IOError) as e:
                    logger.warning(f"[API] Could not read log file {filename}: {str(e)}")
    
    all_logs.sort(key=lambda x: x.get("timestamp", ""), reverse=False)
    
    return JSONResponse(content={
        "run_id": run_id,
        "total_logs": len(all_logs),
        "logs": all_logs[-200:]
    })

@router.get("/download/{run_id}")
async def download_results(run_id: str):
    run_data = run_storage.get_run(run_id)
    
    if not run_data:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    
    if run_data.get("status") != "completed":
        raise HTTPException(
            status_code=400, 
            detail=f"Run {run_id} is not completed yet. Status: {run_data.get('status')}"
        )
    
    zip_path = f"{config.RESULTS_DIR}/reconciliation_{run_id}.zip"
    
    output_files = run_data.get("output_files", [])
    
    results_dir = config.RESULTS_DIR
    if os.path.exists(results_dir):
        for filename in os.listdir(results_dir):
            if run_id in filename and not filename.endswith(".zip"):
                filepath = os.path.join(results_dir, filename)
                if filepath not in output_files:
                    output_files.append(filepath)
    
    logs_dir = config.LOGS_DIR
    log_files = []
    if os.path.exists(logs_dir):
        for filename in os.listdir(logs_dir):
            if run_id in filename:
                log_files.append(os.path.join(logs_dir, filename))
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for filepath in output_files:
            if os.path.exists(filepath):
                arcname = os.path.basename(filepath)
                zipf.write(filepath, f"results/{arcname}")
        
        for filepath in log_files:
            if os.path.exists(filepath):
                arcname = os.path.basename(filepath)
                zipf.write(filepath, f"logs/{arcname}")
    
    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=f"reconciliation_{run_id}.zip"
    )

@router.get("/runs")
async def list_runs():
    runs = run_storage.get_all_runs()
    return JSONResponse(content={
        "total_runs": len(runs),
        "runs": runs
    })

@router.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

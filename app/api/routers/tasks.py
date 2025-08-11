from fastapi import APIRouter
from app.services.jobs import task_results, has_inflight_task, start_job
from app.schemas.tasks import AutomationRequest

router = APIRouter(prefix="/tasks", tags=["tasks"])

@router.post("/expired-check")
async def expired_codes():
    inflight, tid = has_inflight_task()
    if inflight:
        return {"error": "A task is already in progress.", "task_id": tid}
    tid = start_job()
    return {"task_id": tid, "status": "Processing", "progress": 0}

@router.post("/automate-all")
async def automate_all(req: AutomationRequest):
    inflight, tid = has_inflight_task()
    if inflight:
        return {"error": "A task is already in progress.", "task_id": tid}
    n = 20 if req.n == "all" else int(req.n)
    tid = start_job(n=n)
    return {"task_id": tid, "status": "Processing", "progress": 0}

@router.get("/{task_id}")
async def get_task_status(task_id: str):
    return task_results.get(task_id, {"status": "Not Found", "progress": 0})

@router.get("/inprogress")
async def get_task_inprogress():
    inflight, tid = has_inflight_task()
    return {"result": inflight, "task_id": tid}

@router.post("/reset")
def reset():
    task_results.clear()
    return {"status": "cleared"}

from fastapi import APIRouter

router = APIRouter()

@router.get("/logs/backlog")
def backlog_logs():
    # 로그 백로그 로직
    return {"message": "logs backlog"}

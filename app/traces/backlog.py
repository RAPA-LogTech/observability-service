from fastapi import APIRouter

router = APIRouter()

@router.get("/traces/backlog")
def backlog_traces():
    # 트레이스 백로그 로직
    return {"message": "traces backlog"}

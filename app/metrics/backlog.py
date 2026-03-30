from fastapi import APIRouter

router = APIRouter()

@router.get("/backlog")
def backlog_metrics():
    # 메트릭 백로그 로직
    return {"message": "metrics backlog"}

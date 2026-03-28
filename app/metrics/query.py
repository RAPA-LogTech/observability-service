from fastapi import APIRouter

router = APIRouter()

@router.get("/metrics")
def query_metrics():
    # 메트릭 쿼리 로직
    return {"message": "metrics query"}

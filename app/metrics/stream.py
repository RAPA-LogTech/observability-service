from fastapi import APIRouter

router = APIRouter()

@router.get("/metrics/stream")
def stream_metrics():
    # 메트릭 스트림 로직
    return {"message": "metrics stream"}

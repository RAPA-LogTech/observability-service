from fastapi import APIRouter

router = APIRouter()

@router.get("/traces/stream")
def stream_traces():
    # 트레이스 스트림 로직
    return {"message": "traces stream"}

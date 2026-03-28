from fastapi import APIRouter

router = APIRouter()

@router.get("/logs/stream")
def stream_logs():
    # 로그 스트림 로직
    return {"message": "logs stream"}

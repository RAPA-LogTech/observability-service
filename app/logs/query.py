from fastapi import APIRouter

router = APIRouter()

@router.get("/logs")
def query_logs():
    # 로그 쿼리 로직
    return {"message": "logs query"}

from fastapi import APIRouter

router = APIRouter()

@router.get("/traces")
def query_traces():
    # 트레이스 쿼리 로직
    return {"message": "traces query"}

from fastapi import APIRouter

router = APIRouter()

@router.get("/traces/{trace_id}")
def trace_detail(trace_id: str):
    # 트레이스 상세 로직
    return {"message": f"trace detail {trace_id}"}

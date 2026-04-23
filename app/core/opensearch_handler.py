"""
OpenSearch 로그 핸들러 - 애플리케이션 로그를 OpenSearch에 전송
"""

import logging
from datetime import datetime
from typing import Optional

import requests
from requests.auth import HTTPBasicAuth


class OpenSearchHandler(logging.Handler):
    """로그를 OpenSearch로 전송하는 핸들러"""

    def __init__(
        self,
        opensearch_url: str,
        opensearch_user: str,
        opensearch_password: str,
        service_name: str,
        environment: str = "development",
        index_prefix: str = "logs",
    ):
        super().__init__()
        self.opensearch_url = opensearch_url.rstrip("/")
        self.opensearch_user = opensearch_user
        self.opensearch_password = opensearch_password
        self.service_name = service_name
        self.environment = environment
        self.index_prefix = index_prefix
        self.auth = HTTPBasicAuth(opensearch_user, opensearch_password) if opensearch_user else None
        self._buffer = []
        self._max_buffer = 10  # 버퍼에 모아서 배치 전송 가능

    def emit(self, record: logging.LogRecord):
        """로그 레코드를 OpenSearch로 전송"""
        try:
            # 로그 데이터 구성
            log_data = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "service": {"name": self.service_name},
                "environment": self.environment,
                "level": record.levelname,
                "message": self.format(record),
                "logger_name": record.name,
                "file": record.filename,
                "line": record.lineno,
                "function": record.funcName,
            }

            # 예외 정보가 있으면 추가
            if record.exc_info:
                log_data["exception"] = self.format(record)

            # 인덱스명 (날짜별 분할)
            index_date = datetime.utcnow().strftime("%Y.%m.%d")
            index_name = f"{self.index_prefix}-{index_date}"

            # OpenSearch로 전송 (재시도 없이 단순 전송)
            url = f"{self.opensearch_url}/{index_name}/_doc"
            try:
                response = requests.post(
                    url,
                    json=log_data,
                    auth=self.auth,
                    timeout=2,
                    verify=False,  # 로컬 개발용
                )
                # 성공 응답이 아니어도 에러를 띄우지 않음 (로깅이 메인 기능을 방해하면 안 됨)
                if response.status_code not in [200, 201]:
                    # 조용히 실패 (stderr로 전송했으므로 무한루프 방지)
                    pass
            except (requests.ConnectionError, requests.Timeout):
                # OpenSearch 연결 불가 - 조용히 무시
                pass

        except Exception:
            # 로그 기록 실패 - logging.Handler로 비권장 handleError 호출 가능
            self.handleError(record)


def setup_opensearch_logging(
    opensearch_url: str,
    opensearch_user: str,
    opensearch_password: str,
    service_name: str,
    environment: str = "development",
) -> Optional[OpenSearchHandler]:
    """
    OpenSearch 로깅을 설정

    Args:
        opensearch_url: OpenSearch URL (예: http://localhost:9200)
        opensearch_user: OpenSearch 사용자명
        opensearch_password: OpenSearch 비밀번호
        service_name: 서비스명
        environment: 환경 (development, production 등)

    Returns:
        OpenSearchHandler 또는 None (URL이 없으면)
    """
    if not opensearch_url:
        return None

    handler = OpenSearchHandler(
        opensearch_url=opensearch_url,
        opensearch_user=opensearch_user,
        opensearch_password=opensearch_password,
        service_name=service_name,
        environment=environment,
    )

    # 포맷 설정
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    handler.setFormatter(formatter)

    # 루트 로거에 핸들러 추가
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)

    return handler

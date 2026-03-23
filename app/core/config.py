from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    service_name: str = "observability-service"
    environment: str = "local"
    data_source_mode: str = "auto"

    # If set, backend can query actual AWS services.
    opensearch_url: str | None = None
    opensearch_logs_index: str = "logs-*"  # logs-app, logs-host, logs-* 등 상황에 따라 사용
    opensearch_app_logs_index: str = "logs-app"  # logs-app만 명확히 조회할 때
    opensearch_host_logs_index: str = "logs-host"  # logs-host만 명확히 조회할 때
    opensearch_traces_index: str | None = "traces-*"
    opensearch_timeout_seconds: float = 8.0
    opensearch_verify_tls: bool = True
    opensearch_username: str | None = None
    opensearch_password: str | None = None
    opensearch_api_key: str | None = None

    amp_endpoint: str | None = None
    amp_timeout_seconds: float = 8.0
    amp_step_seconds: int = 60
    amp_error_rate_query: str = 'sum(app_http_server_error_ratio_5m{job=~".+/$service"}) by (job)'
    amp_latency_p95_query: str = 'sum(app_http_server_latency_p95_5m{job=~".+/$service"}) by (job) * 1000'
    amp_throughput_query: str = 'sum(app_http_server_requests_5m{job=~".+/$service"}) by (job)'
    amp_cpu_query: str = 'sum(app_container_cpu_utilization_avg_5m{job=~".+/$service"}) by (job) * 100'
    amp_memory_query: str = 'sum(app_container_memory_utilization_avg_5m{job=~".+/$service"}) by (job) * 100'

    # Comma-separated origins in .env
    allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    model_config = SettingsConfigDict(
        # Resolve env files from repository root regardless of current working directory.
        env_file=(
            str(Path(__file__).resolve().parents[2] / ".env"),
            str(Path(__file__).resolve().parents[2] / ".env.example"),
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def allowed_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

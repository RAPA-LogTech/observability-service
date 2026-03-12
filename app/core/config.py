from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    service_name: str = "observability-service"
    environment: str = "local"
    data_source_mode: str = "auto"

    # If set, backend can query actual AWS services.
    opensearch_url: str | None = None
    opensearch_logs_index: str = "logs-*"
    opensearch_traces_index: str | None = None
    opensearch_timeout_seconds: float = 8.0
    opensearch_verify_tls: bool = True
    opensearch_username: str | None = None
    opensearch_password: str | None = None
    opensearch_api_key: str | None = None

    amp_endpoint: str | None = None
    amp_timeout_seconds: float = 8.0
    amp_step_seconds: int = 60
    amp_default_service: str = "checkout"
    amp_error_rate_query: str = (
        "(sum(rate(http_requests_total{service=\"$service\",status=~\"5..\"}[5m])) "
        "/ clamp_min(sum(rate(http_requests_total{service=\"$service\"}[5m])), 1)) * 100"
    )
    amp_latency_p95_query: str = (
        "histogram_quantile(0.95, "
        "sum(rate(http_request_duration_seconds_bucket{service=\"$service\"}[5m])) by (le)) * 1000"
    )
    amp_throughput_query: str = "sum(rate(http_requests_total{service=\"$service\"}[1m]))"

    # Comma-separated origins in .env
    allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def allowed_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

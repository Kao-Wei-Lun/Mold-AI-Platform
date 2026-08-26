from dataclasses import asdict, dataclass
from urllib.error import URLError
from urllib.request import urlopen

from django.conf import settings
from django.db import connection
from redis import Redis


@dataclass(frozen=True)
class ServiceCheck:
    name: str
    status: str
    detail: str | None = None


def check_database() -> ServiceCheck:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return ServiceCheck(name="database", status="ok")
    except Exception as exc:  # pragma: no cover - exercised through readiness mocks
        return ServiceCheck(name="database", status="error", detail=type(exc).__name__)


def check_redis() -> ServiceCheck:
    try:
        client = Redis.from_url(settings.REDIS_URL, socket_connect_timeout=1, socket_timeout=1)
        client.ping()
        return ServiceCheck(name="redis", status="ok")
    except Exception as exc:  # pragma: no cover - exercised through readiness mocks
        return ServiceCheck(name="redis", status="error", detail=type(exc).__name__)


def check_qdrant() -> ServiceCheck:
    try:
        with urlopen(f"{settings.QDRANT_URL.rstrip('/')}/readyz", timeout=1) as response:
            if response.status == 200:
                return ServiceCheck(name="qdrant", status="ok")
            return ServiceCheck(name="qdrant", status="error", detail=f"HTTP {response.status}")
    except (OSError, URLError) as exc:  # pragma: no cover - readiness integration path
        return ServiceCheck(name="qdrant", status="error", detail=type(exc).__name__)


def collect_readiness() -> dict[str, object]:
    checks = [check_database(), check_redis(), check_qdrant()]
    return {
        "status": "ok" if all(check.status == "ok" for check in checks) else "degraded",
        "services": [asdict(check) for check in checks],
    }

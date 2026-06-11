from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _dockerfile_text(name: str) -> str:
    return (ROOT / "docker" / name).read_text(encoding="utf-8")


def _assert_copies_required_packages(name: str, required: set[str]) -> None:
    text = _dockerfile_text(name)
    missing = sorted(
        package
        for package in required
        if f"COPY {package}/ {package}/" not in text
    )
    assert not missing, f"{name} is missing required package copies: {', '.join(missing)}"


def test_worker_dockerfile_copies_celery_runtime_packages() -> None:
    _assert_copies_required_packages(
        "Dockerfile.worker",
        {"api", "backend/app", "celery_workers", "db", "media_pipeline", "platform_adapters", "utils"},
    )


def test_media_dockerfile_copies_celery_runtime_packages() -> None:
    _assert_copies_required_packages(
        "Dockerfile.media",
        {"api", "backend/app", "celery_workers", "db", "media_pipeline", "platform_adapters", "utils"},
    )


def test_beat_dockerfile_copies_celery_runtime_packages() -> None:
    _assert_copies_required_packages(
        "Dockerfile.beat",
        {"api", "backend/app", "celery_workers", "db", "media_pipeline", "platform_adapters", "utils"},
    )

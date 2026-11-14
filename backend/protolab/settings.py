"""Local backend credentials. Never serialize these into reports or responses."""
import os
from pathlib import Path


def _local_key(key: str) -> str | None:
    value = os.environ.get(key)
    if value:
        return value
    path = Path(__file__).resolve().parents[1] / ".env"
    if path.is_file():
        for line in path.read_text().splitlines():
            name, separator, value = line.partition("=")
            if separator and name.strip() == key:
                return value.strip() or None
    return None


def boltz_api_key() -> str | None:
    """Prefer the environment, then the ignored backend/.env file."""
    return _local_key("BOLTZ_API_KEY")


def tamarind_api_key() -> str | None:
    """Load the Tamarind credential only on the backend."""
    return _local_key("TAMARIND_API_KEY")

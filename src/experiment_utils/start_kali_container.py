import subprocess
from pathlib import Path
from typing import Final

_DEFAULT_CONTAINER_NAME: Final[str] = "CHAP-kali-linux"
_PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]


def start_kali_container(container_name: str = _DEFAULT_CONTAINER_NAME) -> bool:
    """Start Kali Linux container for a fresh environment."""
    try:
        print(f"🔄 Starting {container_name}...")
        subprocess.run(
            ["docker", "compose", "up", "-d", container_name],
            cwd=_PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        print(f"✅ {container_name} started")
        return True
    except subprocess.CalledProcessError as err:
        print(f"❌ Failed to start {container_name}: {err}")
        return False

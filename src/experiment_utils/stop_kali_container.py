import subprocess
from pathlib import Path
from typing import Final

_DEFAULT_CONTAINER_NAME: Final[str] = "CHAP-kali-linux"
_PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]


def stop_kali_container(container_name: str = _DEFAULT_CONTAINER_NAME) -> bool:
    """Stop and remove the Kali Linux container."""
    try:
        print(f"🔄 Stopping {container_name}...")
        subprocess.run(
            ["docker", "compose", "down", container_name],
            cwd=_PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        print(f"✅ {container_name} stopped")
        return True
    except subprocess.CalledProcessError as err:
        print(f"❌ Failed to stop {container_name}: {err}")
        return False

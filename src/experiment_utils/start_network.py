import subprocess
from typing import Final


_NETWORK_NAME: Final[str] = "autopenbench_net"
_SUBNET: Final[str] = "192.168.0.0/16"

def start_network(network_name: str = _NETWORK_NAME, subnet: str = _SUBNET) -> None:
    """Create the Docker network if it does not already exist."""
    exists = subprocess.run(
        ["docker", "network", "inspect", network_name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if exists.returncode == 0:
        return

    try:
        subprocess.run(
            ["docker", "network", "create", f"--subnet={subnet}", network_name],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as err:
        message = (err.stderr or "").lower()
        if "already exists" in message:
            return
        raise

if __name__ == "__main__":
    start_network()

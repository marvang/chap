import subprocess
from typing import Final


_NETWORK_NAME: Final[str] = "autopenbench_net"


def stop_network(network_name: str = _NETWORK_NAME) -> None:
    """Remove the Docker network if it exists."""
    if subprocess.run(
        ["docker", "network", "inspect", network_name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode != 0:
        return

    remove = subprocess.run(
        ["docker", "network", "rm", network_name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    if remove.returncode == 0:
        return

    if remove.stderr and "No such network" in remove.stderr:
        return

    if remove.stderr and (
        "has active endpoints" in remove.stderr or "in use" in remove.stderr
    ):
        containers = subprocess.run(
            [
                "docker",
                "network",
                "inspect",
                network_name,
                "--format",
                "{{range $id, $_ := .Containers}}{{$id}}\\n{{end}}",
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        for container_id in containers:
            if container_id:
                subprocess.run(
                    ["docker", "network", "disconnect", "-f", network_name, container_id],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
        subprocess.run(
            ["docker", "network", "rm", network_name],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return

    raise RuntimeError(
        f"Failed to remove network {network_name}: {(remove.stderr or '').strip()}"
    )

if __name__ == "__main__":
    stop_network()

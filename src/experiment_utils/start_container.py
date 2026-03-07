import os
import re
import subprocess

def start_container(vm_name: str, compose_file: str = "benchmark/machines/real-world/cve/docker-compose.yml") -> str:
    container_name = f"real-world_cve_{vm_name}"
    # Read compose file and extract IP
    with open(compose_file) as f:
        content = f.read()
    
    pattern = rf"{re.escape(container_name)}:.*?ipv4_address:\s*(\d+\.\d+\.\d+\.\d+)"
    match = re.search(pattern, content, re.DOTALL)
    if not match:
        raise ValueError(f"IP not found for {vm_name}")
    
    ip = match.group(1)
    
    # check first if container exists in compose file
    if f"{container_name}:" not in content:
        raise ValueError(f"Container {container_name} not found in compose file.")
    
    # Start container
    subprocess.run(
        ["docker", "compose", "up", "-d", container_name],
        cwd="benchmark/machines/real-world/cve",
        check=True
    )
    
    return ip

if __name__ == "__main__":
    import sys
    ip = start_container(sys.argv[1])
    print(f"IP: {ip}")

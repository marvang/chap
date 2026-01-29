import subprocess

def stop_container(vm_name: str):
    """Stop container using docker compose down."""
    
    if vm_name == "dummy_ftp_server":
        container_name = vm_name
    else:
        container_name = f"real-world_cve_{vm_name}"
    subprocess.run(
        ["docker", "compose", "down", container_name],
        cwd="benchmark/machines/real-world/cve",
        check=True
    )
    
    return f"real-world_cve_{vm_name} stopped"

if __name__ == "__main__":
    import sys
    result = stop_container(sys.argv[1])
    print(result)

"""Ansible Runner entry point for explicitly approved server jobs."""
from pathlib import Path
import ansible_runner


def run_playbook(private_data_dir: Path, playbook: str, inventory: str, extravars: dict) -> dict:
    result = ansible_runner.run(private_data_dir=str(private_data_dir), playbook=playbook, inventory=inventory, extravars=extravars)
    return {"status": result.status, "rc": result.rc}

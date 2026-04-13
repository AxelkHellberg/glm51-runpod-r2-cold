from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "config"
STATE_DIR = REPO_ROOT / ".state"
SCRIPTS_DIR = REPO_ROOT / "scripts"
DOCKER_DIR = REPO_ROOT / "docker"


def ensure_state_dir() -> Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    return STATE_DIR


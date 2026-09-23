from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PUBLIC_DIR = PROJECT_ROOT / "public"
IMAGE_OUTPUT_DIR = PUBLIC_DIR / "images"
AUDIO_OUTPUT_DIR = PUBLIC_DIR / "audio"


def initialize_runtime_directories() -> None:
    """Create directories required while the application is running."""

    IMAGE_OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )
    AUDIO_OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )
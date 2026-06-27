from __future__ import annotations

from pathlib import Path
from time import time


class ScreenCaptureService:
    """Captures screen frames to a local-only directory."""

    def __init__(self, screenshots_dir: str | Path) -> None:
        self.screenshots_dir = Path(screenshots_dir)
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)

    def capture_frame(self, session_id: str) -> Path:
        try:
            import mss
            from PIL import Image
        except ImportError as exc:
            raise RuntimeError("mss and pillow are required for screen capture") from exc

        session_dir = self.screenshots_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        output_path = session_dir / f"{int(time() * 1000)}.png"

        with mss.mss() as sct:
            monitor = sct.monitors[0]
            shot = sct.grab(monitor)
            image = Image.frombytes("RGB", shot.size, shot.rgb)
            image.save(output_path)

        return output_path

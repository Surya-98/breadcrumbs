from __future__ import annotations

from pathlib import Path

from breadcrumbs.privacy import redacted_snippet


def summarize_ocr_text(text: str | None, max_chars: int = 360) -> str:
    if not text:
        return "No readable on-screen text detected."
    return redacted_snippet(text, max_chars)


class LocalOcrEngine:
    """Local macOS Vision OCR wrapper.

    The method returns an empty string when PyObjC Vision is unavailable, which
    keeps the app runnable on machines before dependencies are installed.
    """

    def recognize_file(self, image_path: str | Path) -> str:
        try:
            import Foundation
            import Vision
        except ImportError:
            return ""

        path = str(Path(image_path).resolve())
        url = Foundation.NSURL.fileURLWithPath_(path)
        recognized: list[str] = []

        def completion_handler(request, error) -> None:  # type: ignore[no-untyped-def]
            if error is not None:
                return
            for observation in request.results() or []:
                candidates = observation.topCandidates_(1)
                if candidates:
                    recognized.append(str(candidates[0].string()))

        request = Vision.VNRecognizeTextRequest.alloc().initWithCompletionHandler_(completion_handler)
        request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
        request.setUsesLanguageCorrection_(True)
        handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(url, {})
        handler.performRequests_error_([request], None)
        return "\n".join(recognized)

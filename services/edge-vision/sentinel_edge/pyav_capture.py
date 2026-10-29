"""Optional PyAV RTSP decoder for authorized, local-only Hikvision preview.

This is an in-memory alternative to OpenCV VideoCapture. It intentionally
exposes the same minimal read/isOpened/get/release interface. No credentials,
headers, video, URLs, or native decoder exceptions are logged.
"""
from typing import Any


class PyAVCapture:
    def __init__(self, url: str):
        # Caller must already have validated a private RTSP URL and signed
        # local camera approval. Import cv2 first for local GUI compatibility.
        container = None
        try:
            import av
            container = av.open(
                url, mode="r", format="rtsp",
                options={"rtsp_transport": "tcp", "rw_timeout": "4000000"},
                timeout=(8.0, 4.0),
            )
            video = next((s for s in container.streams if s.type == "video"), None)
            if video is None:
                raise ValueError("No authorized video track")
            self._container: Any = container
            self._decoder = iter(container.decode(video=0))
            try:
                self._fps = float(video.average_rate)
            except (ValueError, TypeError, ZeroDivisionError, OverflowError):
                self._fps = 0.0
        except Exception:
            if container is not None:
                try:
                    container.close()
                except Exception:
                    pass
            # PyAV/FFmpeg native exception strings can include RTSP credentials.
            raise RuntimeError("Local RTSP decoder could not open") from None

    def isOpened(self) -> bool:
        return self._container is not None

    def get(self, _property: Any) -> float:
        return self._fps

    def read(self):
        if self._container is None:
            return False, None
        try:
            frame = next(self._decoder)
            return True, frame.to_ndarray(format="bgr24")
        except StopIteration:
            return False, None
        except Exception:
            raise RuntimeError("Local RTSP frame decoding interrupted") from None

    def release(self) -> None:
        container = self._container
        self._container = None
        self._decoder = None
        if container is not None:
            try:
                container.close()
            except Exception:
                pass


def open_pyav_capture(_cv2: Any, url: str) -> PyAVCapture:
    """Open authorized stream only; cv2 was imported by the caller first."""
    return PyAVCapture(url)

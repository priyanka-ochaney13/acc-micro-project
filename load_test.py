import sys
import io
import time
import threading
import requests
from PIL import Image

BACKEND_URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"

SHORTEN_THREADS = 40
RESIZE_THREADS = 20   # fewer, since each resize call is already heavier
DURATION = 240  # seconds

stop_time = time.time() + DURATION
successful = 0
failed = 0
counter_lock = threading.Lock()

# Build one small test image once, reused for every resize request.
_img = Image.new("RGB", (1600, 1200), color=(120, 180, 200))
_buf = io.BytesIO()
_img.save(_buf, format="JPEG")
TEST_IMAGE_BYTES = _buf.getvalue()


def record(ok: bool):
    global successful, failed
    with counter_lock:
        if ok:
            successful += 1
        else:
            failed += 1


def hammer_shorten():
    while time.time() < stop_time:
        try:
            resp = requests.post(
                f"{BACKEND_URL}/shorten",
                json={"url": "https://example.com"},
                timeout=5,
            )
            record(resp.status_code == 200)
        except requests.RequestException:
            record(False)


def hammer_resize():
    while time.time() < stop_time:
        try:
            files = {"file": ("test.jpg", TEST_IMAGE_BYTES, "image/jpeg")}
            resp = requests.post(f"{BACKEND_URL}/resize", files=files, timeout=10)
            record(resp.status_code == 200)
        except requests.RequestException:
            record(False)


threads = (
    [threading.Thread(target=hammer_shorten) for _ in range(SHORTEN_THREADS)]
    + [threading.Thread(target=hammer_resize) for _ in range(RESIZE_THREADS)]
)

for t in threads:
    t.start()

print(
    f"Load test running for {DURATION}s against {BACKEND_URL} — "
    f"{SHORTEN_THREADS} threads hitting /shorten, {RESIZE_THREADS} hitting /resize..."
)

for t in threads:
    t.join()

print(f"Load test complete. Successful: {successful}, Failed: {failed}")
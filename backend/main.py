import os
import string
import hashlib
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from PIL import Image, ImageFilter
import redis
import io
import base64
import uuid

app = FastAPI(title="URL Shortener + Image Resizer")

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

CODE_LENGTH = 6
ALPHABET = string.ascii_letters + string.digits  # a-z, A-Z, 0-9

SIZES = {
    "thumbnail": (150, 150),
    "medium": (500, 500),
    "large": (1200, 1200),
}

@app.get("/health")
def health():
    return {"status": "ok"}

class URLRequest(BaseModel):
    url: str

def generate_code(url: str) -> str:
    # Deliberately CPU-heavy so we have real load to autoscale against.
    salt = os.urandom(8)
    digest = hashlib.pbkdf2_hmac("sha256", url.encode(), salt, 50000)
    return digest.hex()[:8]

@app.post("/shorten")
def shorten_url(request: URLRequest):
    code = generate_code(request.url)
    while r.exists(code):
        code = generate_code(request.url)
    r.set(code, request.url)
    return {"short_code": code, "short_url": f"/r/{code}"}

@app.get("/lookup/{code}")
def lookup(code: str):
    original = r.get(code)
    if not original:
        raise HTTPException(status_code=404, detail="Code not found")
    return {"code": code, "url": original}


@app.get("/r/{code}")
def redirect_url(code: str):
    original = r.get(code)
    if not original:
        raise HTTPException(status_code=404, detail="Code not found")
    return RedirectResponse(url=original)

# ---------- Image Resizer ----------

def process_image(image_bytes: bytes) -> dict:
    original = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    original_size = original.size
    results = {}

    for label, max_size in SIZES.items():
        resized = original.copy()
        resized.thumbnail(max_size, Image.Resampling.LANCZOS)
        resized = resized.filter(ImageFilter.SHARPEN)

        buf = io.BytesIO()
        resized.save(buf, format="JPEG", quality=85)
        results[label] = {
            "image_base64": base64.b64encode(buf.getvalue()).decode("utf-8"),
            "original_width": original_size[0],
            "original_height": original_size[1],
            "resized_width": resized.width,
            "resized_height": resized.height,
        }

    return results

@app.post("/resize")
async def resize_image(file: UploadFile = File(...)):
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    image_bytes = await file.read()

    try:
        resized_versions = process_image(image_bytes)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not process image: {e}")

    job_id = str(uuid.uuid4())[:8]
    for label, result in resized_versions.items():
        r.set(
            f"{job_id}:{label}",
            result["image_base64"],
            ex=3600,
        )
        r.set(
            f"{job_id}:{label}:dimensions",
            f"{result['original_width']}x{result['original_height']} -> "
            f"{result['resized_width']}x{result['resized_height']}",
            ex=3600,
        )

    return {
        "job_id": job_id,
        "sizes": list(resized_versions.keys()),
        "dimensions": {
            label: {
                "original": (
                    resized["original_width"],
                    resized["original_height"],
                ),
                "resized": (
                    resized["resized_width"],
                    resized["resized_height"],
                ),
            }
            for label, resized in resized_versions.items()
        },
}

@app.get("/result/{job_id}/{size}")
def get_result(job_id: str, size: str):
    data = r.get(f"{job_id}:{size}")
    if not data:
        raise HTTPException(status_code=404, detail="Result not found or expired")
    dimensions = r.get(f"{job_id}:{size}:dimensions")
    return {"job_id": job_id, "size": size, "image_base64": data, "dimensions": dimensions,}
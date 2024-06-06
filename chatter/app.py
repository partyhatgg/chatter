from faster_whisper import WhisperModel
from sanic import Request, Sanic, text, json
from sanic.log import logger
import os
from io import BytesIO
import requests
import re
from sanic_ext import validate
from chatter.models.transcription import TranscriptionRequest
from dotenv import load_dotenv
from cachetools import TTLCache
from uuid import UUID

load_dotenv()

URL_REGEX = re.compile(r"https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()!@:%_\+.~#?&\/\/=]*)")

app = Sanic("Chatter")
app.config.OAS = False  # OpenAPI Spec is enabled by default by sanic_ext. This way is more effective than the documented OAS_AUTODOC setting.

jobs = TTLCache(maxsize=100, ttl=60)


@app.on_request
async def require_auth(request: Request):
    if not request.headers.get("Authorization") == os.getenv("API_KEY"):
        return json({"error": "Unauthorized"}, status=401)


@app.get("/")
async def index(request: Request):
    return text("Hello World")


@app.get("/dev")
async def jobs_req(request: Request):
    return text(str(jobs))


@app.get("/job/<id:uuid>")
async def job(request: Request, id: UUID):
    job = jobs.get(str(id))

    if not job or not jobs:
        return json({"error": "Job not found"}, status=404)

    return json({
        "id": str(id), 
        "status": job["status"], 
        "output": {
            "detected_language": job["output"]["detected_language"], 
            "device": job["output"]["device"], 
            "model": "medium", 
            "transcription": job["output"]["transcription"]
        }
    })


@app.post("/transcribe")
@validate(json=TranscriptionRequest)
async def transcribe(request: Request, body: TranscriptionRequest):
    if not URL_REGEX.match(body.url):
        return json({"error": "Invalid URL"}, status=400)

    r = requests.get(body.url)
    r.raise_for_status()

    content = BytesIO(r.content)

    model = WhisperModel("medium", device="cpu", compute_type="auto")

    failed = False
    try:
        segments, info = model.transcribe(
            content,
            best_of=5,  # default
            beam_size=5,  # default
            patience=1,  # default
        )
    except:  # noqa: E722
        failed = True

    id = str(request.generate_id())
    jobs[id] = {
        "status": "COMPLETED" if not failed else "FAILED",
        "output": {
            "detected_language": info.language,
            "device": "cpu",
            "transcription": " ".join([segment.text.lstrip() for segment in segments]),
        },
    }

    return json({"id": id})


def start():
    IS_DEV = True if os.getenv("DEBUG") == "1" else False
    app.run(
        host="0.0.0.0",
        port=8000,
        access_log=IS_DEV,
        debug=IS_DEV,
        auto_reload=True,
    )

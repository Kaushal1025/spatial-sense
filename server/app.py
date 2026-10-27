"""Modal web endpoint for Spatial Sense (CPU only).

Segmentation runs on Meta's hosted SAM 3.1 and the spoken instruction comes
from Muse Spark, so this container just forwards requests and doesn't need a
GPU.

Dev server:  modal serve server/app.py
Deploy:      modal deploy server/app.py

The "spatial-sense" Modal secret must hold CLIENT_TOKEN (the shared token the
web app sends as X-Client-Token) and, outside mock mode, MODEL_API_KEY:
    modal secret create spatial-sense CLIENT_TOKEN=... MODEL_API_KEY=...

ALLOWED_ORIGIN is the web app's origin for CORS, read locally at deploy time
(comma-separate several). It defaults to the local dev server.

Mock mode is on by default and returns fake boxes and a fake instruction
without calling the API. To use the real API, deploy with SAM_MOCK=0:
    SAM_MOCK=0 ALLOWED_ORIGIN=https://your-app.example modal deploy server/app.py
"""

import os

import modal

app = modal.App("spatial-sense")

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("fastapi[standard]", "openai")
    .add_local_python_source("sam", "prompts", "muse")
)

# SAM_MOCK and ALLOWED_ORIGIN are read locally at deploy time and forwarded to
# the container, so the deployed app matches how it was deployed.
_mock = os.environ.get("SAM_MOCK", "1") != "0"
_allowed_origin = os.environ.get("ALLOWED_ORIGIN", "http://localhost:8000")
secrets = [
    modal.Secret.from_dict(
        {"SAM_MOCK": "1" if _mock else "0", "ALLOWED_ORIGIN": _allowed_origin}
    ),
    modal.Secret.from_name("spatial-sense"),
]


@app.function(image=image, secrets=secrets)
@modal.asgi_app()
def web():
    # Imported here so FastAPI only needs to be installed in the container.
    import hmac

    from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
    from fastapi.middleware.cors import CORSMiddleware

    import muse
    import prompts
    import sam

    client_token = os.environ.get("CLIENT_TOKEN", "")
    allowed_origins = [o.strip() for o in os.environ["ALLOWED_ORIGIN"].split(",") if o.strip()]

    def require_client_token(x_client_token: str | None = Header(default=None)):
        # Fail closed: with no CLIENT_TOKEN configured, every request is rejected.
        if not client_token or not hmac.compare_digest(
            (x_client_token or "").encode(), client_token.encode()
        ):
            raise HTTPException(status_code=401, detail="Invalid or missing client token")

    web_app = FastAPI()
    web_app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_methods=["POST"],
        allow_headers=["X-Client-Token"],
    )

    @web_app.post("/segment", dependencies=[Depends(require_client_token)])
    async def segment(image: UploadFile = File(...), goal: str | None = None):
        """Segment an uploaded image and return a spoken instruction for it."""
        image_bytes = await image.read()
        regions = await sam.segment(image_bytes, image.content_type or "image/jpeg")
        prompt = prompts.build_instruction_prompt(regions, goal)
        return {
            "mock": sam.is_mock(),
            "regions": regions,
            "spoken_instruction": await muse.spoken_instruction(prompt),
        }

    return web_app

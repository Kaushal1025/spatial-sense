"""FastAPI app for Spatial Sense, without any Modal dependency.

app.py serves this on Modal. For a local mock server (no Modal, no API calls):
    cd server && CLIENT_TOKEN=dev uvicorn api:create_app --factory --port 8001
"""

import hmac
import os

from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware

import geometry
import muse
import prompts
import sam


def create_app() -> FastAPI:
    client_token = os.environ.get("CLIENT_TOKEN", "")
    allowed_origins = [
        o.strip() for o in os.environ.get("ALLOWED_ORIGIN", "http://localhost:8000").split(",") if o.strip()
    ]

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
    async def segment(
        image: UploadFile = File(...),
        goal: str | None = None,
        height_m: float | None = Query(default=None, ge=0.5, le=2.5),
        targets: list[str] = Query(default=[]),
    ):
        """Segment an uploaded image and return guidance for it.

        guidance holds up to 2 short estimated messages from geometry.py;
        spoken_instruction is the Muse Spark reply, used when guidance is empty.
        With height_m, each region also gets distance_m, steps, and angle_deg.
        """
        image_bytes = await image.read()
        targets = sam.normalize_targets(targets)
        regions = await sam.segment(
            image_bytes, image.content_type or "image/jpeg", sam.merge_phrases(targets)
        )
        size = geometry.image_size(image_bytes)

        if not goal and targets:
            goal = "find the " + " and the ".join(targets)
        prompt = prompts.build_instruction_prompt(regions, goal)

        return {
            "mock": sam.is_mock(),
            "regions": geometry.annotate(regions, size, height_m) if height_m else regions,
            "targets": targets,
            "guidance": geometry.build_guidance(regions, targets, size, height_m),
            "spoken_instruction": await muse.spoken_instruction(prompt),
        }

    return web_app

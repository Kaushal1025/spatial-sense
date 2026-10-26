"""Modal web endpoint for Spatial Sense (CPU only).

Segmentation runs on Meta's hosted SAM 3.1, so this container just forwards
requests and doesn't need a GPU.

Dev server:  modal serve server/app.py
Deploy:      modal deploy server/app.py

Mock mode is on by default and returns fake boxes without calling the API.
To use the real API, create the secret once and deploy with SAM_MOCK=0:
    modal secret create spatial-sense MODEL_API_KEY=...
    SAM_MOCK=0 modal deploy server/app.py
"""

import os

import modal

app = modal.App("spatial-sense")

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("fastapi[standard]", "openai")
    .add_local_python_source("sam", "prompts")
)

# SAM_MOCK is read locally at deploy time and forwarded to the container, so
# the deployed app runs in the same mode. The API key secret is only attached
# when mock mode is off.
_mock = os.environ.get("SAM_MOCK", "1") != "0"
secrets = [modal.Secret.from_dict({"SAM_MOCK": "1" if _mock else "0"})]
if not _mock:
    secrets.append(modal.Secret.from_name("spatial-sense"))


@app.function(image=image, secrets=secrets)
@modal.asgi_app()
def web():
    # Imported here so FastAPI only needs to be installed in the container.
    from fastapi import FastAPI, File, UploadFile

    import prompts
    import sam

    web_app = FastAPI()

    @web_app.post("/segment")
    async def segment(image: UploadFile = File(...), goal: str | None = None):
        """Segment an uploaded image and build the spoken-instruction prompt."""
        image_bytes = await image.read()
        regions = await sam.segment(image_bytes, image.content_type or "image/jpeg")
        return {
            "mock": sam.is_mock(),
            "regions": regions,
            "prompt": prompts.build_instruction_prompt(regions, goal),
        }

    return web_app

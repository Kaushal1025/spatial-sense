"""SAM 3.1 segmentation through the Meta Model API.

SAM 3.1 takes one noun phrase per request, so we send one request per phrase
in PHRASES, in parallel, and merge the results into labeled regions.

Docs: https://dev.meta.ai/docs/sam/segmenting
      https://dev.meta.ai/docs/sam/reading-segmentation
"""

import asyncio
import base64
import logging
import os
import re

log = logging.getLogger(__name__)

BASE_URL = "https://api.meta.ai/v1"
MODEL = "sam-3.1"

PHRASES = [
    "person",
    "chair",
    "table",
    "door",
    "stairs",
    "car",
    "bicycle",
    "pole",
    "curb",
    "step",
]

# Matches "<object id><|box;x1=..;y1=..;x2=..;y2=..;w=..;h=..[;c=..]|>".
# We only read boxes; masks are skipped. Box fields are plain numbers, so this
# is safe even though mask payloads are base85 and can contain any delimiter.
_BOX_RE = re.compile(r"(\d+)<\|box;([^|]*)\|>")


def is_mock() -> bool:
    """Mock mode is on unless SAM_MOCK is set to "0"."""
    return os.environ.get("SAM_MOCK", "1") != "0"


def parse_output(output_text: str, label: str) -> list[dict]:
    """Turn SAM 3.1 output_text into regions for one phrase.

    Regions look like {"label", "score", "bbox": [x_min, y_min, x_max, y_max]},
    with bbox normalized to 0..1 using the w/h SAM reports on each box.
    Empty output means no matches.
    """
    regions = []
    for _object_id, fields in _BOX_RE.findall(output_text):
        # Fields are keyed by name; don't rely on their order.
        box = dict(field.split("=", 1) for field in fields.split(";") if "=" in field)
        w, h = float(box["w"]), float(box["h"])
        regions.append(
            {
                "label": label,
                "score": float(box.get("c", 1.0)),
                "bbox": [
                    float(box["x1"]) / w,
                    float(box["y1"]) / h,
                    float(box["x2"]) / w,
                    float(box["y2"]) / h,
                ],
            }
        )
    return regions


# Fake SAM output per phrase, in the real token format, so mock mode exercises
# the same parser as the real API. Masks are placeholders.
_MOCK_OUTPUT = {
    "person": "<0f>0<|box;x1=560;y1=180;x2=760;y2=700;w=1280;h=720;c=0.93|><|mask;x=0;y=0;data=1,1,~0|>",
    "chair": "<0f>0<|box;x1=60;y1=380;x2=360;y2=710;w=1280;h=720;c=0.88|><|mask;x=0;y=0;data=1,1,~0|>",
    "door": "<0f>0<|box;x1=1000;y1=60;x2=1180;y2=560;w=1280;h=720;c=0.81|><|mask;x=0;y=0;data=1,1,~0|>",
    "step": "<0f>0<|box;x1=400;y1=640;x2=900;y2=715;w=1280;h=720;c=0.42|><|mask;x=0;y=0;data=1,1,~0|>",
}


async def _segment_phrase(client, data_url: str, phrase: str) -> list[dict]:
    if client is None:
        output_text = _MOCK_OUTPUT.get(phrase, "")
    else:
        response = await client.responses.create(
            model=MODEL,
            input=[
                {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": phrase},
                        {"type": "input_image", "image_url": data_url},
                    ],
                }
            ],
            metadata={"include_confidence": "true"},
        )
        output_text = response.output_text
    return parse_output(output_text, phrase)


async def segment(
    image_bytes: bytes,
    content_type: str = "image/jpeg",
    phrases: list[str] = PHRASES,
) -> list[dict]:
    """Segment an image, one SAM 3.1 request per phrase, run in parallel.

    A phrase whose request fails is logged and skipped so one bad request
    doesn't drop the whole frame.
    """
    data_url = f"data:{content_type};base64,{base64.b64encode(image_bytes).decode()}"

    client = None
    if not is_mock():
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=os.environ["MODEL_API_KEY"], base_url=BASE_URL)

    results = await asyncio.gather(
        *(_segment_phrase(client, data_url, phrase) for phrase in phrases),
        return_exceptions=True,
    )

    regions = []
    for phrase, result in zip(phrases, results):
        if isinstance(result, BaseException):
            log.warning("SAM request for %r failed: %s", phrase, result)
            continue
        regions.extend(result)
    return regions

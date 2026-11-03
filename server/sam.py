"""SAM 3.1 segmentation through the Meta Model API.

SAM 3.1 takes one noun phrase per request, so we send one request per phrase,
in parallel, and merge the results into labeled regions. Each frame searches
the user's targets (plus "hand") first, then PHRASES, up to MAX_PHRASES.

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

# Ordered by priority: only the first ones fit when targets are added.
PHRASES = [
    "person",
    "chair",
    "table",
    "door",
    "stairs",
    "step",
    "curb",
    "pole",
    "car",
    "bicycle",
    "bottle",
    "can",
]

# Each phrase is one SAM request, so this caps cost per frame.
MAX_PHRASES = 8
MAX_TARGETS = 3
MAX_TARGET_WORDS = 3

# Matches "<object id><|box;x1=..;y1=..;x2=..;y2=..;w=..;h=..[;c=..]|>".
# We only read boxes; masks are skipped. Box fields are plain numbers, so this
# is safe even though mask payloads are base85 and can contain any delimiter.
_BOX_RE = re.compile(r"(\d+)<\|box;([^|]*)\|>")


def is_mock() -> bool:
    """Mock mode is on unless SAM_MOCK is set to "0"."""
    return os.environ.get("SAM_MOCK", "1") != "0"


def normalize_targets(raw: list[str]) -> list[str]:
    """Lowercase, trim, and dedupe targets; keep at most 3 of up to 3 words."""
    targets = []
    for text in raw:
        words = re.sub(r"[^a-z0-9' -]", " ", text.lower()).split()[:MAX_TARGET_WORDS]
        target = " ".join(words)
        if target and target not in targets:
            targets.append(target)
    return targets[:MAX_TARGETS]


def merge_phrases(targets: list[str]) -> list[str]:
    """Phrases to search this frame: targets, then "hand" if there are any
    targets, then PHRASES. Deduped and capped at MAX_PHRASES."""
    phrases = []
    for phrase in [*targets, *(["hand"] if targets else []), *PHRASES]:
        if phrase not in phrases:
            phrases.append(phrase)
    return phrases[:MAX_PHRASES]


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
    # Only searched when asked for, so mock mode can show target and hand guidance.
    "bottle": "<0f>0<|box;x1=840;y1=400;x2=920;y2=640;w=1280;h=720;c=0.86|><|mask;x=0;y=0;data=1,1,~0|>",
    "hand": "<0f>0<|box;x1=500;y1=560;x2=620;y2=700;w=1280;h=720;c=0.79|><|mask;x=0;y=0;data=1,1,~0|>",
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
    phrases: list[str] | None = None,
) -> list[dict]:
    """Segment an image, one SAM 3.1 request per phrase, run in parallel.

    phrases defaults to merge_phrases([]). A phrase whose request fails is
    logged and skipped so one bad request doesn't drop the whole frame.
    """
    if phrases is None:
        phrases = merge_phrases([])
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

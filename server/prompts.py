"""Prompt building for short spoken navigation instructions.

Regions use the shape returned by `segment` in sam.py:
    {"label": str, "score": float, "bbox": [x_min, y_min, x_max, y_max]}
with bbox coordinates normalized to 0..1.
"""

MAX_REGIONS = 8
MIN_SCORE = 0.3

SYSTEM_PROMPT = (
    "You are a navigation assistant for a blind or low-vision person. "
    "You receive a list of objects detected in the camera view, with their "
    "rough direction and distance. Reply with ONE short spoken instruction "
    "(at most 20 words) that helps them move safely. Mention the most "
    "important obstacle or target first. Use clock directions or "
    "left/right/ahead, never visual-only terms like 'the red one'. "
    "Do not mention confidence scores or that you are looking at a list."
)


def _direction(bbox: list[float]) -> str:
    x_center = (bbox[0] + bbox[2]) / 2
    if x_center < 0.33:
        return "left"
    if x_center > 0.67:
        return "right"
    return "ahead"


def _distance(bbox: list[float]) -> str:
    # Rough proxy: bigger in frame and lower in frame means closer.
    area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
    bottom = bbox[3]
    if area > 0.25 or bottom > 0.9:
        return "very close"
    if area > 0.08:
        return "nearby"
    return "farther away"


def _describe(region: dict) -> str:
    bbox = region["bbox"]
    return f"- {region['label']}: {_direction(bbox)}, {_distance(bbox)}"


def build_instruction_prompt(regions: list[dict], goal: str | None = None) -> dict:
    """Build the prompt for a short spoken instruction.

    Args:
        regions: labeled regions from segmentation.
        goal: optional user intent, e.g. "find the door".

    Returns:
        {"system": str, "user": str}, ready to send to the language model.
    """
    kept = [r for r in regions if r.get("score", 1.0) >= MIN_SCORE]
    # Largest (likely closest) first, so the model sees what matters most.
    kept.sort(
        key=lambda r: (r["bbox"][2] - r["bbox"][0]) * (r["bbox"][3] - r["bbox"][1]),
        reverse=True,
    )
    kept = kept[:MAX_REGIONS]

    if kept:
        scene = "\n".join(_describe(r) for r in kept)
    else:
        scene = "- nothing detected"

    lines = ["Objects in view:", scene]
    if goal:
        lines += ["", f"The user wants to: {goal}"]
    lines += ["", "Give the spoken instruction now."]

    return {"system": SYSTEM_PROMPT, "user": "\n".join(lines)}

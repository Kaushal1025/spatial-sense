"""Rough distance, step, and direction estimates from bounding boxes.

Everything here is an estimate from a single camera frame. It assumes a
65 degree horizontal field of view and an average real-world height per
object label, so real distances can be off by a lot. The guidance strings
always say "about" and are meant to supplement a cane or guide dog.

Regions use the shape returned by `segment` in sam.py:
    {"label": str, "score": float, "bbox": [x_min, y_min, x_max, y_max]}
with bbox coordinates normalized to 0..1.

This module is pure standard library so it can be unit tested anywhere.
"""

import math
import struct

# Average step length as a fraction of body height. This is a commonly used
# average for walking, not a measurement of the user.
STEP_LENGTH_RATIO = 0.415

# Assumed horizontal field of view of a phone or laptop camera.
HORIZONTAL_FOV_DEG = 65.0

# Rough real-world heights, in meters, used to turn box height into distance.
REAL_HEIGHTS_M = {
    "person": 1.7,
    "chair": 0.9,
    "table": 0.75,
    "door": 2.0,
    "bottle": 0.25,
    "can": 0.12,
    "car": 1.5,
    "bicycle": 1.1,
    "pole": 2.5,
    "curb": 0.15,
    "step": 0.18,
    "stairs": 1.0,
    "hand": 0.18,
    "frying pan": 0.05,
}

MIN_SCORE = 0.3
MAX_MESSAGES = 2

OBSTACLE_LABELS = {"person", "door", "chair"}
OBSTACLE_MAX_STEPS = 2
OBSTACLE_MAX_ANGLE_DEG = 20

# Hand offsets smaller than this (as a fraction of the frame) are "a little".
HAND_NEAR_THRESHOLD = 0.05
# Hand guidance only makes sense once the target is roughly within arm's reach.
REACH_M = 1.0

POINT_AT_HANDS = "Point the camera down toward your hands."


def _round_half_up(x: float) -> int:
    return int(math.floor(x + 0.5))


def _round_to(x: float, base: int) -> int:
    """Round to the nearest multiple of base, halves away from zero."""
    return int(math.copysign(math.floor(abs(x) / base + 0.5) * base, x))


def step_length_m(height_m: float) -> float:
    return STEP_LENGTH_RATIO * height_m


def focal_px(image_width_px: float) -> float:
    return (image_width_px / 2) / math.tan(math.radians(HORIZONTAL_FOV_DEG / 2))


def distance_m(box_height_px: float, real_height_m: float, image_width_px: float) -> float | None:
    """Pinhole estimate of distance to an object. None for an empty box."""
    if box_height_px <= 0:
        return None
    return focal_px(image_width_px) * real_height_m / box_height_px


def steps(distance: float, height_m: float) -> int:
    return _round_half_up(distance / step_length_m(height_m))


def angle_deg(box_center_x: float) -> int:
    """Horizontal angle to a box center, rounded to 5. Negative is left."""
    return _round_to((box_center_x - 0.5) * HORIZONTAL_FOV_DEG, 5)


def direction_words(angle: int) -> str:
    side = "left" if angle < 0 else "right"
    if abs(angle) < 10:
        return "straight ahead"
    if abs(angle) <= 30:
        return f"slightly {side}"
    return f"turn {side} about {abs(angle)} degrees"


def _center(bbox: list[float]) -> tuple[float, float]:
    return (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2


def hand_guidance(hand_bbox: list[float], target_bbox: list[float]) -> str:
    """Spoken hint for moving the hand toward the target, e.g.
    "Move your hand up and to the right." Image y grows downward."""
    hx, hy = _center(hand_bbox)
    tx, ty = _center(target_bbox)
    dx, dy = tx - hx, ty - hy

    parts = []
    if dy:
        parts.append(("a little " if abs(dy) < HAND_NEAR_THRESHOLD else "") + ("up" if dy < 0 else "down"))
    if dx:
        parts.append(("a little " if abs(dx) < HAND_NEAR_THRESHOLD else "") + ("to the left" if dx < 0 else "to the right"))
    if not parts:
        return "Your hand is on it."
    return f"Move your hand {' and '.join(parts)}."


def image_size(data: bytes) -> tuple[int, int] | None:
    """(width, height) of a JPEG or PNG from its header, or None."""
    if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24:
        return struct.unpack(">II", data[16:24])
    if data[:2] != b"\xff\xd8":
        return None
    i = 2
    while i + 4 <= len(data):
        if data[i] != 0xFF:
            return None
        marker = data[i + 1]
        if marker == 0xFF:  # fill byte
            i += 1
            continue
        if marker in (0x01, *range(0xD0, 0xDA)):  # markers with no length
            i += 2
            continue
        # Start-of-frame markers hold the size: C0-CF except C4, C8, CC.
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            if i + 9 > len(data):
                return None
            height, width = struct.unpack(">HH", data[i + 5 : i + 9])
            return width, height
        (length,) = struct.unpack(">H", data[i + 2 : i + 4])
        i += 2 + length
    return None


def measure(region: dict, size: tuple[int, int] | None, height_m: float | None) -> dict:
    """Estimated distance_m, steps, and angle_deg for one region.

    distance_m is None when the label has no known height or the image size
    is unknown; steps is None without a distance or the user's height.
    """
    bbox = region["bbox"]
    dist = None
    real = REAL_HEIGHTS_M.get(region["label"])
    if real is not None and size is not None:
        width_px, height_px = size
        dist = distance_m((bbox[3] - bbox[1]) * height_px, real, width_px)
    return {
        "distance_m": dist,
        "steps": steps(dist, height_m) if dist is not None and height_m else None,
        "angle_deg": angle_deg(_center(bbox)[0]),
    }


def annotate(regions: list[dict], size: tuple[int, int] | None, height_m: float) -> list[dict]:
    """Copies of regions with distance_m, steps, and angle_deg added."""
    out = []
    for region in regions:
        m = measure(region, size, height_m)
        if m["distance_m"] is not None:
            m["distance_m"] = round(m["distance_m"], 2)
        out.append({**region, **m})
    return out


def _spoken_label(label: str) -> str:
    return label[:1].upper() + label[1:]


def describe(label: str, m: dict) -> str:
    """e.g. "Chair, about 3 steps, slightly left." """
    direction = direction_words(m["angle_deg"])
    n = m["steps"]
    if n is None:
        return f"{_spoken_label(label)}, {direction}."
    if n == 0:
        return f"{_spoken_label(label)}, less than a step away, {direction}."
    return f"{_spoken_label(label)}, about {n} step{'' if n == 1 else 's'}, {direction}."


def not_in_view(target: str) -> str:
    return f"{_spoken_label(target)} not in view. Turn slowly left or right."


def _nearest(items: list[tuple[dict, dict]]) -> tuple[dict, dict]:
    # Known distance first, closest first; fall back to the tallest box.
    def key(item):
        region, m = item
        dist = m["distance_m"]
        return (dist is None, dist or 0.0, -(region["bbox"][3] - region["bbox"][1]))

    return min(items, key=key)


def obstacle_warning(items: list[tuple[dict, dict]]) -> tuple[str, dict] | None:
    """Warn about a person, door, or chair within 2 steps and roughly ahead.

    Suggests the side with fewer other detected objects; on a tie, the side
    away from the obstacle (left when it is dead ahead). Returns the message
    and the obstacle region, or None.
    """
    obstacles = [
        (r, m)
        for r, m in items
        if r["label"] in OBSTACLE_LABELS
        and m["steps"] is not None
        and m["steps"] <= OBSTACLE_MAX_STEPS
        and abs(m["angle_deg"]) < OBSTACLE_MAX_ANGLE_DEG
    ]
    if not obstacles:
        return None
    obstacle, om = _nearest(obstacles)
    others = [r for r, _ in items if r is not obstacle and r["label"] != "hand"]
    left = sum(1 for r in others if _center(r["bbox"])[0] < 0.5)
    right = sum(1 for r in others if _center(r["bbox"])[0] > 0.5)
    if left != right:
        side = "left" if left < right else "right"
    else:
        side = "right" if om["angle_deg"] < 0 else "left"
    return f"Obstacle ahead. Move {side}.", obstacle


def build_guidance(
    regions: list[dict],
    targets: list[str],
    size: tuple[int, int] | None,
    height_m: float | None,
) -> list[str]:
    """Short spoken messages for one frame, most important first.

    Order: obstacle warning, then target answers (with hand guidance once a
    target is within reach), then the nearest other object. At most
    MAX_MESSAGES are returned.
    """
    items = [(r, measure(r, size, height_m)) for r in regions if r.get("score", 1.0) >= MIN_SCORE]
    messages = []

    used = set()
    warning = obstacle_warning(items)
    if warning:
        messages.append(warning[0])
        used.add(id(warning[1]))

    hands = [(r, m) for r, m in items if r["label"] == "hand"]
    for target in targets:
        found = [(r, m) for r, m in items if r["label"] == target]
        if not found:
            messages.append(not_in_view(target))
            continue
        region, m = _nearest(found)
        used.add(id(region))
        messages.append(describe(target, m))
        if m["distance_m"] is None or m["distance_m"] <= REACH_M:
            if hands:
                hand = max(hands, key=lambda item: item[0].get("score", 1.0))[0]
                messages.append(hand_guidance(hand["bbox"], region["bbox"]))
            else:
                messages.append(POINT_AT_HANDS)

    others = [(r, m) for r, m in items if id(r) not in used and r["label"] not in targets and r["label"] != "hand"]
    if others:
        region, m = _nearest(others)
        messages.append(describe(region["label"], m))

    return messages[:MAX_MESSAGES]

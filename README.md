# Spatial Sense

A phone or laptop web app for blind and low-vision users. Tap Start once and the camera runs. About every 2 seconds the app speaks one short piece of guidance: what known object is nearest, roughly how many steps away it is, which way to turn, which way to move a hand toward something, and when to step around an obstacle. You can ask by voice, for example "where is the frying pan."

**Spatial Sense gives assistive estimates. It does not replace a white cane or guide dog, and it should not be relied on for safety-critical navigation.** Every distance, step count, and angle comes from a single camera frame and rough assumptions (see [Estimates](#estimates)). None of them have been checked against measured distances.

## Status

| Part | State |
| --- | --- |
| Mock mode, end to end | Working. Verified locally with unit tests and a headless Chrome run (fake camera, stubbed speech) against the local mock server. |
| Real SAM 3.1 and Muse Spark | Implemented behind `SAM_MOCK=0`. The SAM output parser is tested on a real SAM 3.1 response. Full live runs, latency, and cost are not verified. |
| Distance, steps, angle | Estimates only. The formulas are unit tested; their accuracy on real scenes is untested. |
| Real phones | Not yet tested on a physical iPhone or Android device. Speech recognition, motion permission, and step detection on hardware are untested. |

## Using it

1. Open the page. It shows one large Start button and tries to say "Tap Start. Then tell me your height in feet and inches, or centimeters." (Most browsers block speech until the first tap, so the same text is on screen.)
2. Tap Start. The camera opens right away. On iOS the same tap asks for motion-sensor permission.
3. Say or type your height: "5 10", "5 ft 10 in", or "178 cm". The app says "Height set to 1.78 meters." and remembers it on this device.
4. The app speaks guidance, for example "Chair, about 3 steps, slightly left." The latest message is also shown on screen.
5. Tap Ask and say "where is the frying pan", "find my bottle", or "where's the can". The target is kept until you ask for something else or say "stop". You can also type into the Find box.
   - Not in view: "Frying pan not in view. Turn slowly left or right."
   - Within about 1 meter and your hand is visible: "Move your hand up and to the right."
   - Within about 1 meter but no hand visible: "Point the camera down toward your hands."
6. Ask "how many steps have I taken" to hear the step count.

Guidance rules:

- Only the first guidance message is spoken. The same message isn't repeated within 5 seconds unless it changes. Obstacle warnings interrupt other speech.
- Obstacle warnings come first: if a person, door, or chair is estimated within 2 steps and within 20 degrees of straight ahead, the app says "Obstacle ahead. Move left." (or right), picking the side with fewer other detected objects. On a tie it picks the side away from the obstacle, or left if it is dead ahead. This is a rough rule, not reliable obstacle avoidance.
- If nothing is detected for 3 frames in a row: "Nothing recognized. Slowly turn left or right."
- If the server returns no guidance, the app speaks the Muse Spark instruction instead.

## Estimates

All of these live in `server/geometry.py`.

- **Step length** = 0.415 × height (`STEP_LENGTH_RATIO`). This is a commonly used average ratio of walking step length to body height, not a measurement of the user. Real step length varies with speed, age, and gait.
- **Distance** = focal_px × real_height_m / box_height_px, where focal_px = (image_width_px / 2) / tan(65° / 2). This assumes a 65° horizontal field of view (real cameras differ, and phones held upright have a narrower one) and an average real-world height per object: person 1.7 m, chair 0.9, table 0.75, door 2.0, bottle 0.25, can 0.12, car 1.5, bicycle 1.1, pole 2.5, curb 0.15, step 0.18, stairs 1.0, hand 0.18, frying pan 0.05. Objects cut off by the frame edge, partly hidden, or unusually sized give wrong distances. Labels without a known height (most custom targets) get a direction but no distance.
- **Steps** = round(distance / step length).
- **Angle** = (box center x − 0.5) × 65°, rounded to the nearest 5°. Negative is left. Under 10° is "straight ahead", 10° to 30° is "slightly left/right", over 30° is "turn left/right about N degrees".
- **Hand direction** uses the vector from the hand box center to the target box center. An offset under 5% of the frame on an axis is "a little".
- **Steps taken** uses peaks in phone acceleration magnitude (threshold 1.5 m/s², at least 0.3 s apart). The threshold is untuned and untested on a real phone.

## What's not built

- Turn-by-turn navigation or routes.
- Reliable obstacle avoidance. The obstacle rule only covers people, doors, and chairs SAM detects in the current frame.
- Distance accuracy. Nothing has been calibrated or measured.
- Tracking objects between frames, depth sensing, or floor and drop-off detection.

## Browser support

The camera needs HTTPS (or `localhost`).

- **Speech output** (`speechSynthesis`): current Chrome, Edge, Safari, and Firefox.
- **Speech recognition** (Ask button, spoken height): browser dependent. Chrome and Edge (which send audio to the browser vendor's speech service) and Safari provide it; Firefox doesn't. Without it, the Ask button is hidden and you type into the Find and height boxes instead.
- **Motion sensors** (step count): iOS Safari asks for permission on the Start tap. Android Chrome provides motion events over HTTPS. Laptops usually have no motion sensor, so after 2 seconds without motion data the app shows an "I took a step" button instead. No step count is shown unless it comes from the sensor or the button.

## Project layout

- `server/api.py`: FastAPI app (auth, CORS, `/segment`), runnable locally without Modal
- `server/app.py`: Modal wrapper that serves `api.py`
- `server/sam.py`: SAM 3.1 client, one request per phrase, output parsing, target normalization
- `server/geometry.py`: distance, steps, angle, hand and obstacle rules, guidance text
- `server/muse.py`: Muse Spark instruction call and mock response
- `server/prompts.py`: builds the Muse Spark prompt from detected regions
- `web/`: installable PWA (camera, speech, voice questions, step counting); `web/parse.js` holds the pure parsing helpers
- `scripts/write-config.js`: writes `web/config.js` from environment variables for Vercel
- `tests/`: node tests for `web/parse.js`

## API

`POST /segment` with a multipart `image` and header `X-Client-Token`. Optional query parameters:

- `height_m`: the user's height in meters (0.5 to 2.5).
- `targets`: repeatable, for example `?targets=frying%20pan`. Lowercased, trimmed, at most 3 words each, at most 3 targets.
- `goal`: free-text goal passed to Muse Spark.

Each frame searches the targets first, then "hand" (only when there are targets), then the built-in phrases, deduped and capped at 8 SAM requests per frame. With targets, some lower-priority built-in phrases (such as bottle and can) are skipped that frame.

Response:

```json
{
  "mock": true,
  "regions": [{"label": "chair", "score": 0.88, "bbox": [0.05, 0.53, 0.28, 0.99],
               "distance_m": 2.05, "steps": 3, "angle_deg": -20}],
  "targets": ["bottle"],
  "guidance": ["Move your hand up and to the right.", "Bottle, about 1 step, slightly right."],
  "spoken_instruction": "Chair close on your left. Person ahead. Door to your right."
}
```

`distance_m`, `steps`, and `angle_deg` are only added when `height_m` is sent. `guidance` has at most 2 messages: obstacle warnings, then target answers, then the nearest other object.

## Tests

Run from the repo root:

```bash
python3 -m unittest discover -s server -p "test_*.py"
node --test tests/
```

The Python tests need only the standard library and never call the real API.

## Run it locally

Requirements: Python 3.10+. Mock mode is the default and makes no API calls.

**Local mock server, no Modal:**

```bash
python3 -m venv .venv && .venv/bin/pip install "fastapi[standard]"
SAM_MOCK=1 CLIENT_TOKEN=dev PYTHONPATH=server .venv/bin/python -m uvicorn api:app --port 8001
```

Then create `web/config.js` (git-ignored, never commit it) from `web/config.example.js` with `endpoint: "http://localhost:8001/segment"` and `clientToken: "dev"`, and in a second terminal:

```bash
cd web && python3 -m http.server 8000
```

Open `http://localhost:8000` and tap Start.

**On Modal (dev server):**

1. Create the Modal secret once: `modal secret create spatial-sense CLIENT_TOKEN="<your token>"`
2. `modal serve server/app.py`
3. Point `web/config.js` at the Modal URL and serve `web/` as above.

## Real API mode

```bash
modal secret create spatial-sense CLIENT_TOKEN="<token>" MODEL_API_KEY="<meta key>"
SAM_MOCK=0 ALLOWED_ORIGIN="https://your-app.vercel.app,http://localhost:8000" modal deploy server/app.py
```

Each frame makes one SAM call per phrase (up to 8) plus one Muse Spark call, about every 2 seconds while running. Set a spend limit on the Meta billing page before enabling this.

## Deploy the web app on Vercel

`vercel.json` serves `web/` as a static site. Its build step runs `scripts/write-config.js`, which writes `config.js` from two project environment variables:

- `SPATIAL_SENSE_ENDPOINT`: the Modal `/segment` URL
- `SPATIAL_SENSE_CLIENT_TOKEN`: the same value as `CLIENT_TOKEN` in the Modal secret

The client token is visible to anyone who loads the page. It keeps casual traffic off the endpoint but is not a real secret. The Vercel origin must be in `ALLOWED_ORIGIN` when deploying Modal, or the browser blocks requests. `.vercelignore` keeps a local `web/config.js` and `.env` out of CLI uploads.

## Built during the hackathon

Building period: October 27 to November 4, 2026.

- Started before the building period (October 26, 2026): the initial commit (`375479c`) and the first SAM 3.1 client, prompt builder, and Modal CPU endpoint skeleton with mock mode (`320cc6e`). These were refined during the hackathon.
- Built during the hackathon: the web PWA, token authentication, CORS, the Muse Spark instruction step, the SAM parser tests, the geometry estimates and guidance rules, target and hand guidance, voice questions, the height and start flow, step counting, the Vercel build, and this README.

## Models

- SAM 3.1 via the Meta Model API (segmentation)
- Muse Spark via the Meta Model API (fallback spoken instruction)

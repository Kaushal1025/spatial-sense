# Spatial Sense

A live scene navigator for blind and low-vision users. A phone or laptop camera streams frames to a server, which uses SAM 3.1 to find nearby objects and Muse Spark to turn them into a short spoken instruction, such as "chair close on your left, door ahead."

**Status:** Working end to end in mock mode. Real SAM 3.1 and Muse Spark calls are implemented behind `SAM_MOCK=0` but not yet verified against the live API.

Spatial Sense supplements a white cane or guide dog. It does not replace them and should not be relied on for safety-critical navigation.

## How it works

1. The web app (`web/`) captures a camera frame every 2 seconds.
2. It POSTs the frame to a Modal endpoint (`server/app.py`) with a client token.
3. The server sends one SAM 3.1 request per phrase (for example "chair", "door"), in parallel.
4. The server returns labeled regions with bounding boxes and a spoken instruction from Muse Spark.
5. The browser speaks the instruction and lists the detections.

## Project layout

- `server/app.py`: Modal web endpoint, auth check, CORS, and request routing
- `server/sam.py`: SAM 3.1 client, one request per phrase, output parsing
- `server/muse.py`: Muse Spark instruction call and mock response
- `server/prompts.py`: builds the prompt from detected regions
- `web/`: installable PWA (camera capture, speech, status UI)

## Run it locally

Requirements: Python 3.10+, the Modal CLI (`pip install modal`), and a Modal account.

1. Create the Modal secret (run once, in a terminal):
   ```bash
   modal secret create spatial-sense CLIENT_TOKEN="<your token>"
   ```
2. Create the web config from the example and fill in the endpoint and token:
   ```bash
   cp web/config.example.js web/config.js
   ```
   `web/config.js` is git-ignored. Never commit it.
3. Start the backend (mock mode is on by default):
   ```bash
   modal serve server/app.py
   ```
4. In a second terminal, serve the web app:
   ```bash
   cd web && python3 -m http.server 8000
   ```
5. Open `http://localhost:8000`, allow camera access, and click Start.

## Real API mode

Mock mode returns fixed results and makes no API calls. To use the real SAM 3.1 and Muse Spark APIs:

```bash
modal secret create spatial-sense CLIENT_TOKEN="<token>" MODEL_API_KEY="<meta key>"
SAM_MOCK=0 modal deploy server/app.py
```

Each frame makes one SAM call per phrase, so cost scales with the phrase list. Set a spend limit on the Meta billing page before enabling this.

## Built during the hackathon

Building period: October 27 to November 4, 2026.

Built during the hackathon:
- All code under `server/` and `web/`
- The SAM 3.1 client, the Muse Spark instruction step, the token check, and the PWA

Before the hackathon:
- The repository was created on October 26 with a template README and `.gitignore`. No application code was committed before October 27.

## Models

- SAM 3.1 via the Meta Model API (segmentation)
- Muse Spark via the Meta Model API (spoken instruction)
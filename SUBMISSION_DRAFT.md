# Spatial Sense: submission draft

## What it is

Spatial Sense is a web app for blind and low-vision users that turns a phone or laptop camera into short spoken guidance. Tap Start once, say your height, and about every 2 seconds the app says what's nearby, roughly how many steps away it is, and which way to turn. Ask "where is the frying pan" and it looks for that object, then guides your hand toward it once it's within reach. It warns when a person, door, or chair seems to be directly ahead and close.

It uses SAM 3.1 to find objects in each frame and simple, deterministic geometry to turn box sizes and positions into steps and directions. Muse Spark writes a fallback instruction when the geometry has nothing to say.

Spatial Sense is an assistive estimate. It does not replace a white cane or guide dog.

## What works

Verified in **mock mode** (fixed SAM and Muse Spark outputs, no API calls), with unit tests and a headless Chrome run that used a fake camera and stubbed speech against the local mock server:

- The start flow: one Start tap opens the camera, asks for the user's height by voice or text, confirms it aloud, and remembers it.
- A continuous loop that sends a frame every 2 seconds and speaks one message, without repeating it within 5 seconds.
- Spoken and typed questions ("where is the bottle", "stop", "how many steps have I taken").
- Target answers, "not in view" hints, hand guidance ("Move your hand up and to the right"), and the "Point the camera down toward your hands" prompt.
- An "I took a step" button when no motion sensor is available.
- The server API: `height_m` and `targets` parameters, and per-object `distance_m`, `steps`, and `angle_deg`, plus a `guidance` list.

**Real API mode** (`SAM_MOCK=0`): the SAM 3.1 and Muse Spark calls are implemented, and the SAM output parser is tested against a real SAM 3.1 response. A full live run, its latency, and its cost per minute are not yet verified.

**Not yet tested on a physical phone**: speech recognition, iOS motion permission, and accelerometer step counting on real hardware.

## What's estimated

- Distance comes from a pinhole-camera estimate with an assumed 65° field of view and an average height per object type (for example, a chair is assumed to be 0.9 m tall).
- Steps use an average step length of 0.415 × the user's height.
- Directions come from where an object sits horizontally in the frame, rounded to 5°.
- Step counting uses a fixed acceleration threshold that hasn't been tuned on real walking data.

None of these have been checked against measured distances. Every spoken estimate says "about".

## What's next

- Test on real iPhone and Android devices, and tune the step detector on recorded walks.
- Measure distance error against a tape measure for each object type, and calibrate the field of view per device.
- Run live SAM 3.1 and Muse Spark and measure latency and cost per minute.
- Track objects across frames so guidance is steadier and repeats less.
- Add floor, drop-off, and stair-edge detection.
- Work with blind and low-vision testers on wording, pacing, and which objects matter most.

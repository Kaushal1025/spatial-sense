// Endpoint and client token come from config.js (see config.example.js).
const { endpoint: ENDPOINT, clientToken: CLIENT_TOKEN } = window.SPATIAL_SENSE_CONFIG ?? {};
const { parseHeight, parseQuestion, shouldSpeak, motionMagnitude, StepCounter } = window.SpatialParse;

const INTERVAL_MS = 2000;
// Frames are downscaled before upload to keep requests small and fast.
const MAX_WIDTH = 640;
const JPEG_QUALITY = 0.7;
const EMPTY_FRAMES_LIMIT = 3;
// How long to wait for a motion event before falling back to the step button.
const MOTION_WAIT_MS = 2000;
const HEIGHT_KEY = "spatial-sense-height-m";

const WELCOME = "Tap Start. Then tell me your height in feet and inches, or centimeters.";
const NOTHING_RECOGNIZED = "Nothing recognized. Slowly turn left or right.";

const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;

const $ = (id) => document.getElementById(id);
const video = $("camera");
const canvas = $("frame");
const toggle = $("toggle");
const controls = $("controls");
const messageEl = $("message");
const askButton = $("ask");
const targetEl = $("target");
const stepsEl = $("steps");
const stepButton = $("step");
const statusEl = $("status");
const regionsEl = $("regions");
const heightCurrentEl = $("height-current");

let stream = null;
let timer = null;
let inFlight = false;
let listening = false;
let emptyFrames = 0;
let lastSpoken = { text: "", time: 0 };
let heightM = loadHeight();
let target = null;
// "sensor" or "button" once step counting is available; no count is shown before.
let stepSource = null;
const stepCounter = new StepCounter();

function loadHeight() {
  try {
    const value = parseFloat(localStorage.getItem(HEIGHT_KEY));
    return value >= 0.9 && value <= 2.5 ? value : null;
  } catch {
    return null;
  }
}

function saveHeight(meters) {
  try {
    localStorage.setItem(HEIGHT_KEY, String(meters));
  } catch {
    // Storage can be blocked (private mode); the height still applies this session.
  }
}

function setStatus(text) {
  statusEl.textContent = text;
}

function showMessage(text) {
  messageEl.textContent = text;
}

// Speak now, cutting off anything in progress. Resolves when done.
function say(text) {
  return new Promise((resolve) => {
    speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.onend = utterance.onerror = () => resolve();
    showMessage(text);
    speechSynthesis.speak(utterance);
    // Some browsers never fire onend; don't hang the caller.
    setTimeout(resolve, 8000);
  });
}

// Guidance from the loop: skip repeats within 5 s, don't talk over the user
// or over ourselves, except that obstacle warnings interrupt.
function guide(text) {
  if (!text) return;
  showMessage(text);
  const now = Date.now();
  if (listening || !shouldSpeak(text, lastSpoken, now)) return;
  const urgent = text.startsWith("Obstacle");
  if (speechSynthesis.speaking && !urgent) return;
  if (urgent) speechSynthesis.cancel();
  speechSynthesis.speak(new SpeechSynthesisUtterance(text));
  lastSpoken = { text, time: now };
}

function listenOnce() {
  return new Promise((resolve, reject) => {
    const recognition = new Recognition();
    recognition.lang = "en-US";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    recognition.onresult = (event) => resolve(event.results[0][0].transcript);
    recognition.onerror = (event) => reject(new Error(event.error));
    recognition.onend = () => resolve("");
    speechSynthesis.cancel();
    listening = true;
    setStatus("Listening.");
    recognition.start();
  }).finally(() => {
    listening = false;
  });
}

function renderHeight() {
  heightCurrentEl.textContent = heightM
    ? `Height: ${heightM.toFixed(2)} m. Steps are estimated from it.`
    : "Height not set. Distances are shown without steps.";
}

function renderTarget() {
  targetEl.textContent = target ? `Looking for: ${target}.` : 'Not looking for anything. Ask "where is the bottle".';
}

function renderSteps() {
  if (!stepSource) return;
  stepsEl.hidden = false;
  stepsEl.textContent = `Steps taken: ${stepCounter.count} (${stepSource === "sensor" ? "motion sensor, estimate" : "button"})`;
}

function setHeight(meters) {
  heightM = meters;
  saveHeight(meters);
  renderHeight();
  return say(`Height set to ${meters.toFixed(2)} meters.`);
}

function handleHeightText(text) {
  const meters = parseHeight(text);
  if (meters) return setHeight(meters);
  return say("Sorry, I didn't get a height. Try 5 10, or 178 centimeters.");
}

function handleQuestion(text) {
  const action = parseQuestion(text);
  // Let the next guidance message speak right away.
  lastSpoken = { text: "", time: 0 };
  switch (action?.type) {
    case "stop": {
      const was = target;
      target = null;
      renderTarget();
      return say(was ? `Stopped looking for ${was}.` : "Stopped.");
    }
    case "steps":
      return say(stepSource ? `Steps taken: ${stepCounter.count}.` : "Step counting is not available yet.");
    case "height":
      return setHeight(action.meters);
    case "target":
      target = action.target;
      renderTarget();
      return say(`Looking for ${target}.`);
    default:
      return say('Sorry, I didn\'t catch that. Try "where is the bottle".');
  }
}

function describeRegion({ label, score, distance_m, steps, angle_deg }) {
  const parts = [`${label} (${Math.round(score * 100)}%)`];
  if (distance_m != null) parts.push(`about ${distance_m.toFixed(1)} m`);
  if (steps != null) parts.push(`${steps} steps`);
  if (angle_deg != null) parts.push(angle_deg === 0 ? "ahead" : `${Math.abs(angle_deg)}° ${angle_deg < 0 ? "left" : "right"}`);
  return parts.join(", ");
}

function renderRegions(regions) {
  regionsEl.replaceChildren();
  if (!regions.length) {
    regionsEl.append(Object.assign(document.createElement("li"), { textContent: "Nothing detected." }));
    return;
  }
  for (const region of regions) {
    regionsEl.append(Object.assign(document.createElement("li"), { textContent: describeRegion(region) }));
  }
}

function captureFrame() {
  const scale = Math.min(1, MAX_WIDTH / video.videoWidth);
  canvas.width = Math.round(video.videoWidth * scale);
  canvas.height = Math.round(video.videoHeight * scale);
  canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
  return new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", JPEG_QUALITY));
}

async function tick() {
  // Skip this tick if the previous request hasn't come back yet.
  if (inFlight || !video.videoWidth) return;
  inFlight = true;
  try {
    const blob = await captureFrame();
    const form = new FormData();
    form.append("image", blob, "frame.jpg");

    const url = new URL(ENDPOINT);
    if (heightM) url.searchParams.set("height_m", heightM.toFixed(2));
    if (target) url.searchParams.append("targets", target);

    const response = await fetch(url, {
      method: "POST",
      headers: { "X-Client-Token": CLIENT_TOKEN },
      body: form,
    });
    if (response.status === 401) throw new Error("Client token rejected. Check config.js.");
    if (!response.ok) throw new Error(`Server returned ${response.status}`);
    const data = await response.json();

    renderRegions(data.regions);
    emptyFrames = data.regions.length ? 0 : emptyFrames + 1;

    // Deterministic guidance first; Muse Spark only when there is none.
    let message = data.guidance?.[0];
    if (!message && emptyFrames >= EMPTY_FRAMES_LIMIT) message = NOTHING_RECOGNIZED;
    if (!message) message = data.spoken_instruction;
    guide(message);

    setStatus(`Running${data.mock ? " (mock data)" : ""}. Last update ${new Date().toLocaleTimeString()}.`);
  } catch (err) {
    console.error(err);
    setStatus(`Request failed: ${err.message}`);
    guide("Connection problem.");
  } finally {
    inFlight = false;
  }
}

// iOS only allows the motion permission prompt inside a tap, so this must be
// called synchronously from the Start click.
function requestMotionPermission() {
  if (typeof DeviceMotionEvent === "undefined") return Promise.resolve(false);
  if (typeof DeviceMotionEvent.requestPermission === "function") {
    return DeviceMotionEvent.requestPermission()
      .then((state) => state === "granted")
      .catch(() => false);
  }
  return Promise.resolve(true);
}

function onMotion(event) {
  const magnitude = motionMagnitude(event);
  if (magnitude == null) return;
  if (!stepSource) {
    stepSource = "sensor";
    stepButton.hidden = true;
  }
  if (stepCounter.update(magnitude, event.timeStamp) || stepsEl.hidden) renderSteps();
}

function useStepButton() {
  if (stepSource) return;
  window.removeEventListener("devicemotion", onMotion);
  stepSource = "button";
  stepButton.hidden = false;
  renderSteps();
}

function setupMotion(granted) {
  if (stepSource) return;
  if (!granted) return useStepButton();
  window.addEventListener("devicemotion", onMotion);
  // Laptops often define DeviceMotionEvent but never fire it.
  setTimeout(() => stepSource || useStepButton(), MOTION_WAIT_MS);
}

async function askHeight() {
  if (!Recognition) {
    await say("Type your height in the height box.");
    $("height").focus();
    return;
  }
  await say("Tell me your height in feet and inches, or centimeters.");
  try {
    const heard = await listenOnce();
    if (heard) await handleHeightText(heard);
    else await say("I didn't hear a height. You can type it in the height box.");
  } catch (err) {
    console.warn("Speech recognition failed:", err);
    await say("I couldn't listen. You can type your height in the height box.");
  }
}

async function start() {
  const motionPermission = requestMotionPermission();
  // Speaking inside the tap unlocks speech synthesis on iOS.
  speechSynthesis.cancel();
  speechSynthesis.speak(new SpeechSynthesisUtterance("Starting."));

  if (!ENDPOINT || !CLIENT_TOKEN) {
    setStatus("Missing endpoint or client token. Copy config.example.js to config.js and fill it in.");
    say("Not configured.");
    return;
  }
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "environment" },
      audio: false,
    });
  } catch (err) {
    setStatus(`Camera unavailable: ${err.message}`);
    say("Camera unavailable.");
    return;
  }
  video.srcObject = stream;
  controls.hidden = false;
  lastSpoken = { text: "", time: 0 };
  emptyFrames = 0;
  toggle.textContent = "Stop";
  toggle.setAttribute("aria-pressed", "true");
  setStatus("Running.");
  timer = setInterval(tick, INTERVAL_MS);
  motionPermission.then(setupMotion);

  if (heightM) say(`Camera on. Height ${heightM.toFixed(2)} meters.`);
  else askHeight();
}

function stop() {
  clearInterval(timer);
  timer = null;
  stream?.getTracks().forEach((track) => track.stop());
  stream = null;
  video.srcObject = null;
  speechSynthesis.cancel();
  toggle.textContent = "Start";
  toggle.setAttribute("aria-pressed", "false");
  setStatus("Stopped.");
}

toggle.addEventListener("click", () => (timer ? stop() : start()));

if (Recognition) {
  askButton.hidden = false;
  askButton.addEventListener("click", async () => {
    try {
      const heard = await listenOnce();
      await (heard ? handleQuestion(heard) : say("I didn't hear anything."));
    } catch (err) {
      console.warn("Speech recognition failed:", err);
      await say("I couldn't listen. You can type in the find box.");
    }
  });
}

$("find-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const input = $("find");
  handleQuestion(input.value);
  input.value = "";
});

$("height-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const input = $("height");
  handleHeightText(input.value);
  input.value = "";
});

stepButton.addEventListener("click", () => {
  stepCounter.count += 1;
  renderSteps();
});

renderHeight();
renderTarget();
showMessage(WELCOME);
// Most browsers block speech before the first tap; try anyway.
try {
  speechSynthesis.speak(new SpeechSynthesisUtterance(WELCOME));
} catch {
  // Ignored: the Start button and the text above say the same thing.
}

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("sw.js").catch((err) => console.warn("Service worker failed:", err));
}

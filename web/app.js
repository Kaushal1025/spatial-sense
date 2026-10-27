// Endpoint and client token come from config.js (see config.example.js).
const { endpoint: ENDPOINT, clientToken: CLIENT_TOKEN } = window.SPATIAL_SENSE_CONFIG ?? {};
const INTERVAL_MS = 2000;
// Frames are downscaled before upload to keep requests small and fast.
const MAX_WIDTH = 640;
const JPEG_QUALITY = 0.7;

const video = document.getElementById("camera");
const canvas = document.getElementById("frame");
const goalInput = document.getElementById("goal");
const toggle = document.getElementById("toggle");
const statusEl = document.getElementById("status");
const regionsEl = document.getElementById("regions");

let stream = null;
let timer = null;
let inFlight = false;
let lastSpoken = "";

function setStatus(text) {
  statusEl.textContent = text;
}

function speak(text) {
  // Don't stack utterances: if we're still talking, skip this one. Also skip
  // repeats so an unchanged scene isn't read out every 2 seconds.
  if (!text || speechSynthesis.speaking || text === lastSpoken) return;
  lastSpoken = text;
  speechSynthesis.speak(new SpeechSynthesisUtterance(text));
}

function renderRegions(regions) {
  regionsEl.replaceChildren();
  if (!regions.length) {
    regionsEl.append(Object.assign(document.createElement("li"), { textContent: "Nothing detected." }));
    return;
  }
  for (const { label, score, bbox } of regions) {
    const [x0, y0, x1, y1] = bbox.map((v) => v.toFixed(2));
    const li = document.createElement("li");
    li.textContent = `${label} (${Math.round(score * 100)}%) at [${x0}, ${y0}, ${x1}, ${y1}]`;
    regionsEl.append(li);
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
    const goal = goalInput.value.trim();
    if (goal) url.searchParams.set("goal", goal);

    const response = await fetch(url, {
      method: "POST",
      headers: { "X-Client-Token": CLIENT_TOKEN },
      body: form,
    });
    if (response.status === 401) throw new Error("Client token rejected. Check config.js.");
    if (!response.ok) throw new Error(`Server returned ${response.status}`);
    const data = await response.json();

    renderRegions(data.regions);
    speak(data.spoken_instruction);
    setStatus(`Running${data.mock ? " (mock data)" : ""}. Last update ${new Date().toLocaleTimeString()}.`);
  } catch (err) {
    console.error(err);
    setStatus(`Request failed: ${err.message}`);
  } finally {
    inFlight = false;
  }
}

async function start() {
  if (!ENDPOINT || !CLIENT_TOKEN) {
    setStatus("Missing endpoint or client token. Copy config.example.js to config.js and fill it in.");
    speak("Not configured.");
    return;
  }
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "environment" },
      audio: false,
    });
  } catch (err) {
    setStatus(`Camera unavailable: ${err.message}`);
    speak("Camera unavailable.");
    return;
  }
  video.srcObject = stream;
  lastSpoken = "";
  // Speaking inside the tap unlocks speech synthesis on iOS.
  speak("Starting.");
  toggle.textContent = "Stop";
  toggle.setAttribute("aria-pressed", "true");
  setStatus("Running.");
  timer = setInterval(tick, INTERVAL_MS);
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

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("sw.js").catch((err) => console.warn("Service worker failed:", err));
}

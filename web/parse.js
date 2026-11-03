// Pure helpers for app.js: height and question parsing, step peak detection,
// and repeat suppression. No DOM access, so they can be tested with node:
//   node --test tests/
(function (root) {
  const MIN_HEIGHT_M = 0.9;
  const MAX_HEIGHT_M = 2.5;
  const MAX_TARGET_WORDS = 3;
  const REPEAT_MS = 5000;

  const NUMBER_WORDS = {
    one: 1, two: 2, three: 3, four: 4, five: 5, six: 6,
    seven: 7, eight: 8, nine: 9, ten: 10, eleven: 11, twelve: 12,
  };

  function checkHeight(meters) {
    if (!Number.isFinite(meters) || meters < MIN_HEIGHT_M || meters > MAX_HEIGHT_M) return null;
    return Math.round(meters * 100) / 100;
  }

  // "5 10", "5 ft 10 in", "5'10\"", "five foot ten", "178 cm", "1.78 m" -> meters, or null.
  function parseHeight(text) {
    let s = String(text ?? "").toLowerCase()
      .replace(/[’′']/g, " ft ")
      .replace(/[”″"]/g, " in ")
      .replace(/\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\b/g, (w) => NUMBER_WORDS[w]);

    let m = s.match(/(\d+(?:\.\d+)?)\s*(?:cm|centimet(?:er|re)s?)\b/);
    if (m) return checkHeight(parseFloat(m[1]) / 100);
    m = s.match(/(\d+(?:\.\d+)?)\s*(?:m|met(?:er|re)s?)\b/);
    if (m) return checkHeight(parseFloat(m[1]));

    const nums = (s.match(/\d+(?:\.\d+)?/g) || []).map(Number);
    if (!nums.length) return null;
    const saidFeet = /\b(?:ft|feet|foot)\b/.test(s);
    if (nums.length === 1 && !saidFeet) {
      const n = nums[0];
      if (n >= 100) return checkHeight(n / 100); // centimeters
      if (n >= MIN_HEIGHT_M && n <= MAX_HEIGHT_M) return checkHeight(n); // meters
    }
    const [feet, inches = 0] = nums;
    if (inches >= 12) return null;
    return checkHeight((feet * 12 + inches) * 0.0254);
  }

  const QUESTION_LEAD =
    /^(?:(?:hey|ok|okay|please|can you|could you|help me|i need to|i want to)\s+)*(?:where is|where's|wheres|where are|find|look for|search for|locate|show me)\b\s*/;
  const FILLER = new Set(["the", "my", "a", "an", "please", "me", "for", "some", "is", "are", "of", "that", "this", "your", "now"]);

  // Turn a spoken or typed question into an action:
  //   {type: "stop"} | {type: "steps"} | {type: "height", meters} | {type: "target", target} | null
  function parseQuestion(text) {
    const s = String(text ?? "").toLowerCase().replace(/’/g, "'").replace(/[^a-z0-9' .-]/g, " ").replace(/\s+/g, " ").trim();
    if (!s) return null;
    if (/^(?:stop|cancel|never ?mind|clear)\b/.test(s)) return { type: "stop" };
    if (/\bsteps?\b/.test(s) && /\b(?:how many|count|taken|walked)\b/.test(s)) return { type: "steps" };
    if (/\b(?:height|tall|cm|centimet\w*|feet|foot|ft|inch(?:es)?|met(?:er|re)s?)\b/.test(s)) {
      const meters = parseHeight(s);
      if (meters) return { type: "height", meters };
    }
    const words = s.replace(QUESTION_LEAD, "").replace(/[.']/g, "").split(" ").filter((w) => w && !FILLER.has(w));
    if (!words.length) return null;
    return { type: "target", target: words.slice(0, MAX_TARGET_WORDS).join(" ") };
  }

  // Speak a message unless it is the same one we said less than REPEAT_MS ago.
  function shouldSpeak(text, last, now) {
    if (!text) return false;
    return text !== last.text || now - last.time >= REPEAT_MS;
  }

  // Acceleration magnitude without gravity, in m/s^2, from a DeviceMotionEvent.
  function motionMagnitude(event) {
    const a = event.acceleration;
    if (a && a.x != null && a.y != null && a.z != null) return Math.hypot(a.x, a.y, a.z);
    const g = event.accelerationIncludingGravity;
    if (g && g.x != null && g.y != null && g.z != null) return Math.abs(Math.hypot(g.x, g.y, g.z) - 9.81);
    return null;
  }

  // Counts a step each time the magnitude rises above threshold, at least
  // minIntervalMs after the last counted peak. It must fall below half the
  // threshold before the next peak can count. Untuned: an estimate only.
  class StepCounter {
    constructor({ threshold = 1.5, minIntervalMs = 300 } = {}) {
      this.threshold = threshold;
      this.minIntervalMs = minIntervalMs;
      this.count = 0;
      this.lastPeakMs = -Infinity;
      this.above = false;
    }

    update(magnitude, timeMs) {
      if (magnitude >= this.threshold) {
        if (this.above) return false;
        this.above = true;
        if (timeMs - this.lastPeakMs < this.minIntervalMs) return false;
        this.lastPeakMs = timeMs;
        this.count += 1;
        return true;
      }
      if (magnitude < this.threshold / 2) this.above = false;
      return false;
    }
  }

  const api = { parseHeight, parseQuestion, shouldSpeak, motionMagnitude, StepCounter, REPEAT_MS };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.SpatialParse = api;
})(this);

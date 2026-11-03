// Tests for web/parse.js. Run from the repo root: node --test tests/
const test = require("node:test");
const assert = require("node:assert/strict");

const { parseHeight, parseQuestion, shouldSpeak, motionMagnitude, StepCounter } = require("../web/parse.js");

test("parseHeight: feet and inches", () => {
  assert.equal(parseHeight("5 10"), 1.78);
  assert.equal(parseHeight("5 ft 10 in"), 1.78);
  assert.equal(parseHeight("5 feet 10 inches"), 1.78);
  assert.equal(parseHeight("5'10\""), 1.78);
  assert.equal(parseHeight("five foot ten"), 1.78);
  assert.equal(parseHeight("6 ft"), 1.83);
  assert.equal(parseHeight("5"), 1.52);
});

test("parseHeight: metric", () => {
  assert.equal(parseHeight("178 cm"), 1.78);
  assert.equal(parseHeight("178 centimeters"), 1.78);
  assert.equal(parseHeight("178"), 1.78);
  assert.equal(parseHeight("1.78 m"), 1.78);
  assert.equal(parseHeight("1.78"), 1.78);
});

test("parseHeight: rejects nonsense", () => {
  assert.equal(parseHeight(""), null);
  assert.equal(parseHeight("hello"), null);
  assert.equal(parseHeight("5 14"), null);
  assert.equal(parseHeight("400 cm"), null);
  assert.equal(parseHeight("20"), null);
});

test("parseQuestion: targets", () => {
  assert.deepEqual(parseQuestion("where is the frying pan"), { type: "target", target: "frying pan" });
  assert.deepEqual(parseQuestion("Find my bottle."), { type: "target", target: "bottle" });
  assert.deepEqual(parseQuestion("where's the can"), { type: "target", target: "can" });
  assert.deepEqual(parseQuestion("Where’s the can?"), { type: "target", target: "can" });
  assert.deepEqual(parseQuestion("can you find my keys please"), { type: "target", target: "keys" });
  assert.deepEqual(parseQuestion("bottle"), { type: "target", target: "bottle" });
  assert.deepEqual(parseQuestion("find the big red coffee mug"), { type: "target", target: "big red coffee" });
});

test("parseQuestion: stop, steps, height, empty", () => {
  assert.deepEqual(parseQuestion("stop"), { type: "stop" });
  assert.deepEqual(parseQuestion("Stop looking"), { type: "stop" });
  assert.deepEqual(parseQuestion("how many steps have I taken"), { type: "steps" });
  assert.deepEqual(parseQuestion("my height is 5 foot 10"), { type: "height", meters: 1.78 });
  assert.deepEqual(parseQuestion("I am 178 cm"), { type: "height", meters: 1.78 });
  assert.equal(parseQuestion("where is the"), null);
  assert.equal(parseQuestion("  "), null);
});

test("shouldSpeak: suppresses repeats within 5 seconds", () => {
  const last = { text: "Chair, slightly left.", time: 1000 };
  assert.equal(shouldSpeak("Chair, slightly left.", last, 5999), false);
  assert.equal(shouldSpeak("Chair, slightly left.", last, 6000), true);
  assert.equal(shouldSpeak("Door, slightly right.", last, 1500), true);
  assert.equal(shouldSpeak("", last, 99999), false);
});

test("motionMagnitude: prefers acceleration without gravity", () => {
  assert.equal(motionMagnitude({ acceleration: { x: 3, y: 4, z: 0 } }), 5);
  const g = motionMagnitude({ acceleration: { x: null, y: null, z: null }, accelerationIncludingGravity: { x: 0, y: 0, z: 11.81 } });
  assert.ok(Math.abs(g - 2) < 1e-9);
  assert.equal(motionMagnitude({}), null);
});

test("StepCounter: threshold, hysteresis, and 0.3 s minimum gap", () => {
  const counter = new StepCounter({ threshold: 1.5, minIntervalMs: 300 });
  // Walking-like peaks every 500 ms.
  for (let t = 0; t < 2000; t += 50) counter.update(t % 500 === 0 ? 2.5 : 0.2, t);
  assert.equal(counter.count, 4);

  // Staying above threshold counts once.
  const held = new StepCounter();
  for (let t = 0; t < 1000; t += 50) held.update(2.5, t);
  assert.equal(held.count, 1);

  // Peaks closer than 300 ms apart count once.
  const fast = new StepCounter();
  [[2.5, 0], [0.1, 100], [2.5, 200], [0.1, 250], [2.5, 400]].forEach(([m, t]) => fast.update(m, t));
  assert.equal(fast.count, 2);
});

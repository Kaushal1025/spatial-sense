// Writes web/config.js from environment variables, for static hosts like
// Vercel where the git-ignored config.js doesn't exist:
//   SPATIAL_SENSE_ENDPOINT=https://...modal.run/segment \
//   SPATIAL_SENSE_CLIENT_TOKEN=... node scripts/write-config.js [output path]
// The client token ships to every visitor's browser. It only keeps casual
// traffic off the endpoint; it is not a secret.
const fs = require("fs");
const path = require("path");

const endpoint = process.env.SPATIAL_SENSE_ENDPOINT;
const clientToken = process.env.SPATIAL_SENSE_CLIENT_TOKEN;
const out = process.argv[2] || path.join(__dirname, "..", "web", "config.js");

if (!endpoint || !clientToken) {
  console.error("Set SPATIAL_SENSE_ENDPOINT and SPATIAL_SENSE_CLIENT_TOKEN.");
  process.exit(1);
}
// Don't clobber a hand-written local config outside a Vercel build.
if (fs.existsSync(out) && !process.env.VERCEL) {
  console.error(`${out} already exists. Not overwriting.`);
  process.exit(1);
}
fs.writeFileSync(out, `window.SPATIAL_SENSE_CONFIG = ${JSON.stringify({ endpoint, clientToken }, null, 2)};\n`);
console.log(`Wrote ${out}`);

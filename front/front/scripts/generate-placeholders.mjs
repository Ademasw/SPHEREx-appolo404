/**
 * generate-placeholders.mjs
 * -------------------------------------------------------------------------
 * Creates simple placeholder PNGs inside `src/assets/` so the project runs
 * immediately after `npm install` — before real artwork exists.
 *
 * - Zero dependencies: it writes PNG files by hand (zlib + CRC32).
 * - SAFE: existing files are NEVER overwritten, so once you drop your own
 *   PNGs into `src/assets/` you can re-run this script without fear.
 * - Use `npm run placeholders:force` to regenerate everything anyway.
 *
 * Usage:
 *   npm run placeholders
 *   npm run placeholders:force
 * -------------------------------------------------------------------------
 */
import { writeFileSync, mkdirSync, existsSync } from 'node:fs';
import { deflateSync } from 'node:zlib';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const OUT_DIR = join(dirname(fileURLToPath(import.meta.url)), '..', 'src', 'assets');
const FORCE = process.argv.includes('--force');

/* ----------------------------- PNG encoder ----------------------------- */

const CRC_TABLE = new Uint32Array(256).map((_, n) => {
  let c = n;
  for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
  return c >>> 0;
});

function crc32(buf) {
  let c = 0xffffffff;
  for (const b of buf) c = CRC_TABLE[(c ^ b) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

function chunk(type, data) {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length);
  const body = Buffer.concat([Buffer.from(type, 'ascii'), data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(body));
  return Buffer.concat([len, body, crc]);
}

function encodePNG(canvas) {
  const { w, h, d } = canvas;
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(w, 0);
  ihdr.writeUInt32BE(h, 4);
  ihdr[8] = 8; // bit depth
  ihdr[9] = 6; // color type RGBA
  const raw = Buffer.alloc((w * 4 + 1) * h);
  for (let y = 0; y < h; y++) {
    raw[y * (w * 4 + 1)] = 0; // filter: none
    for (let x = 0; x < w * 4; x++) {
      const v = d[y * w * 4 + x];
      raw[y * (w * 4 + 1) + 1 + x] = Math.round(Math.min(1, Math.max(0, v)) * 255);
    }
  }
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', ihdr),
    chunk('IDAT', deflateSync(raw, { level: 9 })),
    chunk('IEND', Buffer.alloc(0)),
  ]);
}

/* ------------------------- Tiny drawing toolkit ------------------------ */

const rgb = (r, g, b) => [r / 255, g / 255, b / 255];

class Canvas {
  constructor(w, h, bg = null) {
    this.w = w;
    this.h = h;
    this.d = new Float32Array(w * h * 4);
    if (bg) for (let i = 0; i < w * h; i++) this.d.set([...bg, 1], i * 4);
  }

  /** Straight-alpha "source over" blend of one pixel. */
  blend(x, y, [r, g, b], a) {
    if (x < 0 || y < 0 || x >= this.w || y >= this.h || a <= 0) return;
    a = Math.min(1, a);
    const i = (y * this.w + x) * 4;
    const d = this.d;
    const da = d[i + 3];
    const oa = a + da * (1 - a);
    d[i] = (r * a + d[i] * da * (1 - a)) / oa;
    d[i + 1] = (g * a + d[i + 1] * da * (1 - a)) / oa;
    d[i + 2] = (b * a + d[i + 2] * da * (1 - a)) / oa;
    d[i + 3] = oa;
  }

  forBox(cx, cy, r, fn) {
    for (let y = Math.floor(cy - r); y <= Math.ceil(cy + r); y++)
      for (let x = Math.floor(cx - r); x <= Math.ceil(cx + r); x++) fn(x, y, x + 0.5 - cx, y + 0.5 - cy);
  }

  /** Soft radial glow. */
  glow(cx, cy, radius, color, intensity = 1, falloff = 2.2) {
    this.forBox(cx, cy, radius, (x, y, dx, dy) => {
      const t = 1 - Math.hypot(dx, dy) / radius;
      if (t > 0) this.blend(x, y, color, intensity * t ** falloff);
    });
  }

  /** Four-pointed sparkle (cross-shaped light rays). */
  sparkle(cx, cy, len, thick, color, intensity = 1) {
    this.forBox(cx, cy, len, (x, y, dx, dy) => {
      const h = Math.max(0, 1 - Math.abs(dx) / len) ** 2 * Math.exp(-((dy / thick) ** 2));
      const v = Math.max(0, 1 - Math.abs(dy) / len) ** 2 * Math.exp(-((dx / thick) ** 2));
      this.blend(x, y, color, intensity * Math.max(h, v));
    });
  }

  /** Shaded sphere with optional horizontal bands (gas-giant look). */
  sphere(cx, cy, r, base, { bands = 0, bandStrength = 0.15 } = {}) {
    const L = [-0.55, -0.55, 0.63];
    this.forBox(cx, cy, r + 1, (x, y, dx, dy) => {
      const dist = Math.hypot(dx, dy);
      const edge = Math.min(1, Math.max(0, r - dist + 0.5));
      if (edge <= 0) return;
      const nx = dx / r;
      const ny = dy / r;
      const nz = Math.sqrt(Math.max(0, 1 - nx * nx - ny * ny));
      const diff = Math.max(0, nx * L[0] + ny * L[1] + nz * L[2]);
      const band = bands ? 1 + bandStrength * Math.sin(ny * bands * Math.PI) : 1;
      const spec = Math.max(0, diff) ** 18 * 0.5;
      const k = (0.18 + 0.9 * diff) * band;
      this.blend(x, y, base.map((c) => Math.min(1, c * k + spec)), edge);
    });
  }

  /** Anti-aliased ring (annulus). */
  ring(cx, cy, r, thickness, color, intensity = 1) {
    this.forBox(cx, cy, r + thickness, (x, y, dx, dy) => {
      const a = Math.min(1, Math.max(0, thickness / 2 - Math.abs(Math.hypot(dx, dy) - r) + 0.5));
      this.blend(x, y, color, a * intensity);
    });
  }
}

/** Deterministic random generator so placeholders look the same every run. */
function mulberry32(seed) {
  return () => {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/* ------------------------------ Assets -------------------------------- */

const WHITE = rgb(255, 255, 255);
const LAVENDER = rgb(214, 190, 255);

function skyScene(objectPos, seed = 7) {
  const W = 512;
  const H = 384;
  const c = new Canvas(W, H, rgb(5, 2, 14));
  c.glow(150, 120, 320, rgb(90, 30, 160), 0.35, 1.6);
  c.glow(420, 300, 220, rgb(30, 40, 140), 0.25, 1.6);
  const rand = mulberry32(seed);
  for (let i = 0; i < 160; i++) {
    const r = 1.2 + rand() ** 3 * 4;
    c.glow(rand() * W, rand() * H, r, rand() > 0.8 ? rgb(190, 210, 255) : WHITE, 0.5 + rand() * 0.5, 1.4);
  }
  // The "moving object" (our mock Planet X candidate).
  c.glow(objectPos[0], objectPos[1], 14, rgb(255, 150, 90), 0.5);
  c.glow(objectPos[0], objectPos[1], 4, rgb(255, 230, 200), 1, 1);
  return c;
}

const ASSETS = {
  'logo.png': () => {
    const c = new Canvas(128, 128);
    c.glow(64, 64, 62, rgb(140, 70, 255), 0.35);
    c.ring(64, 64, 48, 3, LAVENDER);
    c.sphere(64, 64, 24, rgb(150, 90, 255), { bands: 5 });
    c.sphere(98, 30, 8, rgb(255, 160, 110));
    return c;
  },
  'star-particle.png': () => {
    const c = new Canvas(64, 64);
    c.glow(32, 32, 30, LAVENDER, 0.5);
    c.sparkle(32, 32, 30, 1.6, WHITE);
    c.glow(32, 32, 6, WHITE, 1, 1);
    return c;
  },
  'star-particle-2.png': () => {
    const c = new Canvas(64, 64);
    c.glow(32, 32, 28, rgb(150, 190, 255), 0.8);
    c.glow(32, 32, 9, WHITE, 1, 1);
    return c;
  },
  'star-particle-3.png': () => {
    const c = new Canvas(64, 64);
    c.glow(32, 32, 26, rgb(255, 150, 235), 0.45);
    c.sparkle(32, 32, 26, 1.3, rgb(255, 200, 245));
    c.glow(32, 32, 5, WHITE, 1, 1);
    return c;
  },
  'star1.png': () => {
    const c = new Canvas(16, 16);
    c.glow(8, 8, 8, WHITE, 1, 1.8);
    return c;
  },
  'star2.png': () => {
    const c = new Canvas(32, 32);
    c.glow(16, 16, 14, LAVENDER, 0.6);
    c.sparkle(16, 16, 15, 1, WHITE);
    return c;
  },
  'planet1.png': () => {
    const c = new Canvas(128, 128);
    c.glow(64, 64, 62, rgb(140, 90, 255), 0.4);
    c.sphere(64, 64, 42, rgb(130, 90, 255), { bands: 7, bandStrength: 0.2 });
    return c;
  },
  'planet2.png': () => {
    const c = new Canvas(128, 128);
    c.glow(64, 64, 62, rgb(255, 120, 80), 0.35);
    c.sphere(64, 64, 42, rgb(255, 130, 85), { bands: 4 });
    return c;
  },
  'planet3.png': () => {
    const c = new Canvas(128, 128);
    c.glow(64, 64, 62, rgb(80, 220, 210), 0.35);
    c.sphere(64, 64, 42, rgb(70, 210, 200));
    return c;
  },
  'planet4.png': () => {
    const c = new Canvas(128, 128);
    c.glow(64, 64, 62, rgb(230, 210, 255), 0.3);
    c.sphere(64, 64, 42, rgb(230, 215, 255), { bands: 10, bandStrength: 0.08 });
    return c;
  },
  // Image sequence for the dashboard player (object drifts across the field).
  ...Object.fromEntries(
    Array.from({ length: 6 }, (_, i) => [
      `frame-0${i + 1}.png`,
      () => skyScene([130 + i * 48, 270 - i * 24]),
    ]),
  ),
  // Two "epochs" for the side-by-side comparison view.
  'epoch-a.png': () => skyScene([180, 230], 11),
  'epoch-b.png': () => skyScene([300, 170], 11),
};

mkdirSync(OUT_DIR, { recursive: true });
let created = 0;
for (const [name, draw] of Object.entries(ASSETS)) {
  const file = join(OUT_DIR, name);
  if (existsSync(file) && !FORCE) {
    console.log(`  skip   ${name} (already exists)`);
    continue;
  }
  writeFileSync(file, encodePNG(draw()));
  console.log(`  create ${name}`);
  created++;
}
console.log(`\nDone — ${created} placeholder(s) written to src/assets/`);


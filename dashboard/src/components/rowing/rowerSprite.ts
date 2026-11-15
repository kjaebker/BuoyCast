/**
 * Procedural pixel-art sculler.
 *
 * The rower is drawn in code rather than from a sprite sheet so the stroke is
 * anatomically correct and continuous:
 *
 *   - He faces the stern (left); the boat travels toward the bow (right).
 *   - Drive  (catch → finish, ~1/3 of the stroke): legs, then body, then arms.
 *   - Recovery (finish → catch, ~2/3): arms, then body, then the slide.
 *   - The oar is a straight lever from the hands to the blade. The blade is
 *     buried on the drive, lifts and feathers on the recovery, and squares
 *     just before the catch. It is always drawn, so it can never "disappear".
 *
 * `rowerPose(phase)` is pure (phase 0 = catch, DRIVE_FRACTION = finish) and
 * `renderRowerFrame` rasterises a pose into a small canvas at 1 logical pixel
 * per pixel; the scene scales it up with nearest-neighbour filtering.
 */

export const SPRITE_W = 128;
export const SPRITE_H = 48;
/** Logical y of the waterline in the sprite (the scene aligns this with its water). */
export const WATERLINE_Y = 37;
/**
 * The near oar reaches out toward the viewer, so (with a slightly raised
 * camera) its blade appears below the hull on screen. This is the water
 * surface level for things on the near side of the boat.
 */
const NEAR_SURFACE_Y = WATERLINE_Y + 3;
/** Fraction of the stroke cycle spent on the drive (real rowing is ~1:2). */
export const DRIVE_FRACTION = 0.34;

type Pt = { x: number; y: number };

export type RowerPose = {
  ankle: Pt;
  knee: Pt;
  hip: Pt;
  shoulder: Pt;
  head: Pt;
  elbow: Pt;
  hand: Pt;
  /** Blade centre. */
  blade: Pt;
  /** 0 = squared and buried, 1 = clear of the water. */
  bladeLift: number;
  feathered: boolean;
  /** Seconds-agnostic splash intensity 0..1 (catch). */
  splash: number;
  /** Body lean in radians, positive = toward the stern. */
  lean: number;
};

// ── Geometry (logical pixels) ────────────────────────────────────────────
const ANKLE: Pt = { x: 45, y: 32 };
const HIP_Y = 31;
const HIP_X_CATCH = 56; // shins vertical at the catch
const HIP_X_FINISH = 66;
const THIGH = 11.5;
const SHIN = 11.5;
const TORSO = 12;
const UPPER_ARM = 7;
const FOREARM = 7.5;
const LEAN_CATCH = (28 * Math.PI) / 180;
const LEAN_FINISH = (-22 * Math.PI) / 180;
const REACH_CATCH = 13; // hands ahead of shoulders at the catch
const REACH_FINISH = 4; // hands drawn into the body at the finish
const PIVOT_X = 50; // oarlock (rigger pin)
const BLADE_LEVER = 0.8; // horizontal outboard/inboard ratio in projection

const clamp01 = (v: number) => Math.min(1, Math.max(0, v));
const ease = (v: number) => {
  const t = clamp01(v);
  return t * t * (3 - 2 * t);
};
const lerp = (a: number, b: number, t: number) => a + (b - a) * t;

/** Two-bone IK. `bendSign` picks which side the middle joint bends toward. */
function solveJoint(a: Pt, b: Pt, l1: number, l2: number, bendSign: 1 | -1): Pt {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const d = Math.min(Math.hypot(dx, dy), l1 + l2 - 0.01);
  const ux = dx / (Math.hypot(dx, dy) || 1);
  const uy = dy / (Math.hypot(dx, dy) || 1);
  const along = (l1 * l1 - l2 * l2 + d * d) / (2 * d);
  const h = Math.sqrt(Math.max(0, l1 * l1 - along * along));
  // Perpendicular (rotated 90°); bendSign chooses the side.
  return {
    x: a.x + ux * along + -uy * h * bendSign,
    y: a.y + uy * along + ux * h * bendSign,
  };
}

/** Pose at a point in the stroke. phase ∈ [0, 1): 0 = catch. */
export function rowerPose(phase: number): RowerPose {
  const s = ((phase % 1) + 1) % 1;
  let legs: number; // 0 = compressed (catch), 1 = extended
  let body: number; // 0 = leaning to stern, 1 = layback
  let arms: number; // 1 = straight reach, 0 = drawn in
  let bladeLift: number;
  let feathered: boolean;
  let splash = 0;

  if (s < DRIVE_FRACTION) {
    const t = s / DRIVE_FRACTION;
    legs = ease(t / 0.6);
    body = ease((t - 0.25) / 0.6);
    arms = 1 - ease((t - 0.55) / 0.45);
    bladeLift = 0.35 * (1 - ease(t / 0.08)); // blade drops in at the catch
    feathered = false;
    splash = 1 - clamp01(t / 0.25);
  } else {
    const r = (s - DRIVE_FRACTION) / (1 - DRIVE_FRACTION);
    arms = ease(r / 0.25);
    body = 1 - ease((r - 0.12) / 0.3);
    legs = 1 - ease((r - 0.3) / 0.7);
    // Tap down out of the water, carry clear, then square and lower to the catch.
    bladeLift = ease(r / 0.08) * (1 - 0.65 * ease((r - 0.9) / 0.1));
    feathered = r > 0.05 && r < 0.86;
  }

  return buildPose(legs, body, arms, bladeLift, feathered, splash);
}

/** "Easy oar": sitting at the finish, blades resting flat on the water. */
export function restPose(): RowerPose {
  return buildPose(1, 0.55, 0.35, 0.15, true, 0);
}

function buildPose(
  legs: number,
  body: number,
  arms: number,
  bladeLift: number,
  feathered: boolean,
  splash: number,
): RowerPose {
  const hip: Pt = { x: lerp(HIP_X_CATCH, HIP_X_FINISH, legs), y: HIP_Y };
  const knee = solveJoint(ANKLE, hip, SHIN, THIGH, -1); // knees up
  const lean = lerp(LEAN_CATCH, LEAN_FINISH, body);
  const shoulder: Pt = {
    x: hip.x - Math.sin(lean) * TORSO,
    y: hip.y - Math.cos(lean) * TORSO,
  };
  const head: Pt = {
    x: shoulder.x - Math.sin(lean) * 4.5 - 0.5,
    y: shoulder.y - Math.cos(lean) * 4.5,
  };

  // Hands: in front of the shoulders, lower when the blade is lifted (lever).
  const reach = lerp(REACH_FINISH, REACH_CATCH, arms);
  let hand: Pt = { x: shoulder.x - reach, y: 24 + 2 * bladeLift };
  const armLen = UPPER_ARM + FOREARM - 0.2;
  const dist = Math.hypot(hand.x - shoulder.x, hand.y - shoulder.y);
  if (dist > armLen) {
    const k = armLen / dist;
    hand = {
      x: shoulder.x + (hand.x - shoulder.x) * k,
      y: shoulder.y + (hand.y - shoulder.y) * k,
    };
  }
  const elbow = solveJoint(shoulder, hand, UPPER_ARM, FOREARM, -1); // elbows drop

  const blade: Pt = {
    x: PIVOT_X + (PIVOT_X - hand.x) * BLADE_LEVER,
    y: NEAR_SURFACE_Y + 2 - 4 * bladeLift,
  };

  return { ankle: ANKLE, knee, hip, shoulder, head, elbow, hand, blade, bladeLift, feathered, splash, lean };
}

// ── Rasteriser ────────────────────────────────────────────────────────────

const C = {
  outline: "#1d130c",
  woodDark: "#5a3518",
  wood: "#8a5529",
  woodLight: "#b47838",
  deck: "#d2a466",
  rigger: "#3a3f47",
  oar: "#d9b27a",
  oarDark: "#8c6233",
  bladeTip: "#e8e2d4",
  bladeWet: "#5d7e9e",
  jacket: "#2f56a3",
  jacketDark: "#1f3a72",
  jacketLight: "#4572c4",
  pants: "#56504a",
  pantsDark: "#433e39",
  shoe: "#1a1716",
  skin: "#e7a779",
  skinDark: "#c47f56",
  hair: "#5b3a22",
  hat: "#5a606a",
  hatDark: "#3d424a",
  feather: "#f2f2f2",
  splash: "#e9f4ff",
  splashDim: "#a9c9e6",
  shadow: "#24405f",
} as const;

class Raster {
  private ctx: CanvasRenderingContext2D;
  constructor(ctx: CanvasRenderingContext2D) {
    this.ctx = ctx;
  }
  px(x: number, y: number, c: string) {
    const ix = Math.round(x);
    const iy = Math.round(y);
    if (ix < 0 || iy < 0 || ix >= SPRITE_W || iy >= SPRITE_H) return;
    this.ctx.fillStyle = c;
    this.ctx.fillRect(ix, iy, 1, 1);
  }
  rect(x: number, y: number, w: number, h: number, c: string) {
    this.ctx.fillStyle = c;
    this.ctx.fillRect(Math.round(x), Math.round(y), w, h);
  }
  /** Line with a square brush of the given size (pixel-perfect, no AA). */
  line(a: Pt, b: Pt, c: string, size = 1, colorAt?: (p: Pt) => string) {
    const steps = Math.max(1, Math.ceil(Math.max(Math.abs(b.x - a.x), Math.abs(b.y - a.y)) * 2));
    const off = (size - 1) / 2;
    for (let i = 0; i <= steps; i++) {
      const t = i / steps;
      const p = { x: lerp(a.x, b.x, t), y: lerp(a.y, b.y, t) };
      const col = colorAt ? colorAt(p) : c;
      for (let dx = 0; dx < size; dx++) {
        for (let dy = 0; dy < size; dy++) this.px(p.x - off + dx, p.y - off + dy, col);
      }
    }
  }
}

function drawHull(r: Raster) {
  // Long, narrow single scull: bow (right) and stern (left) both pointed.
  const sternX = 4;
  const bowX = 124;
  const deckY = 33;
  for (let x = sternX; x <= bowX; x++) {
    const fromEnd = Math.min(x - sternX, bowX - x);
    const taper = Math.min(1, fromEnd / 14);
    const top = deckY + Math.round((1 - taper) * 1.5);
    const bottom = WATERLINE_Y - Math.round((1 - taper) * 2);
    for (let y = top; y <= bottom; y++) {
      let c: string = C.wood;
      if (y === top) c = C.woodLight;
      else if (y === bottom) c = C.woodDark;
      r.px(x, y, c);
    }
    r.px(x, bottom + 1, C.outline);
    if (fromEnd <= 1) for (let y = top; y <= bottom; y++) r.px(x, y, C.outline);
  }
  // Reflection/shadow on the water under the hull seats it in the water.
  r.rect(sternX + 6, WATERLINE_Y + 2, bowX - sternX - 12, 1, "rgba(8, 16, 34, 0.55)");
  r.rect(sternX + 16, WATERLINE_Y + 3, bowX - sternX - 32, 1, "rgba(8, 16, 34, 0.3)");
  // Covered decks fore and aft, with a small splash-board at the bow.
  r.line({ x: 8, y: 32 }, { x: 34, y: 32 }, C.deck);
  r.line({ x: 80, y: 32 }, { x: 120, y: 32 }, C.deck);
  r.line({ x: 84, y: 31 }, { x: 88, y: 29 }, C.deck);
  r.line({ x: 84, y: 31 }, { x: 88, y: 32 }, C.deck);
  // Seat track
  r.line({ x: 50, y: 32 }, { x: 70, y: 32 }, C.woodDark);
}

function drawOar(r: Raster, p: RowerPose) {
  const { hand, blade } = p;
  const wet = (q: Pt) => (q.y > NEAR_SURFACE_Y ? C.bladeWet : C.oar);
  // Handle sticks out slightly past the hands toward the rower.
  const dir = { x: blade.x - hand.x, y: blade.y - hand.y };
  const len = Math.hypot(dir.x, dir.y) || 1;
  const handleEnd = { x: hand.x - (dir.x / len) * 2, y: hand.y - (dir.y / len) * 2 };
  r.line(handleEnd, blade, C.oar, 1, wet);

  const bx = Math.round(blade.x);
  const by = Math.round(blade.y);
  const bladePx = (x: number, y: number) =>
    r.px(x, y, y > NEAR_SURFACE_Y ? C.bladeWet : C.bladeTip);
  if (p.feathered) {
    // Flat blade skimming clear of the water, with its shadow on the surface.
    for (let x = bx - 3; x <= bx + 3; x++) bladePx(x, by);
    for (let x = bx - 2; x <= bx + 3; x++) r.px(x, NEAR_SURFACE_Y + 2, C.shadow);
  } else {
    for (let x = bx - 2; x <= bx + 2; x++) for (let y = by - 2; y <= by + 1; y++) bladePx(x, y);
  }

  // Rigger: from the gunwale out to where the shaft crosses the pin.
  const t = (PIVOT_X - hand.x) / (blade.x - hand.x || 1);
  const pin =
    t > 0 && t < 1
      ? { x: PIVOT_X, y: Math.round(lerp(hand.y, blade.y, t)) }
      : { x: PIVOT_X, y: 31 };
  r.line({ x: PIVOT_X - 4, y: 34 }, pin, C.rigger);
  r.line({ x: PIVOT_X + 4, y: 34 }, pin, C.rigger);
}

function drawSplash(r: Raster, p: RowerPose, frame: number) {
  const bx = Math.round(p.blade.x);
  const y = NEAR_SURFACE_Y;
  if (p.splash > 0.05) {
    const n = Math.max(1, Math.round(p.splash * 4));
    for (let i = 0; i < n; i++) {
      r.px(bx - 3 + i * 2, y - 1 - ((i + frame) % 3), C.splash);
      r.px(bx - 2 + i * 2, y - (i % 2), C.splashDim);
    }
  }
  if (p.bladeLift < 0.2) {
    // Puddle where the blade works the water.
    for (const dx of [-4, -3, 3, 4]) r.px(bx + dx, y, C.splashDim);
  } else if (p.feathered && frame % 3 === 0) {
    r.px(bx + 1, Math.round(p.blade.y) + 1, C.splashDim); // drip off the blade
  }
}

function drawRower(r: Raster, p: RowerPose) {
  // Torso first: the near leg and arm are drawn over it.
  r.line(p.hip, p.shoulder, C.outline, 6);
  r.line(p.hip, p.shoulder, C.jacket, 5);
  r.line(
    { x: p.hip.x - 2, y: p.hip.y - 1 },
    { x: p.shoulder.x - 2, y: p.shoulder.y + 1 },
    C.jacketLight,
    1,
  );

  // Far arm (behind the body), darker.
  r.line({ x: p.shoulder.x + 1, y: p.shoulder.y }, { x: p.elbow.x + 1, y: p.elbow.y - 1 }, C.jacketDark, 2);
  r.line({ x: p.elbow.x + 1, y: p.elbow.y - 1 }, { x: p.hand.x + 1, y: p.hand.y - 1 }, C.jacketDark, 2);

  // Legs: shin + thigh, shoe at the footstretcher.
  r.line(p.ankle, p.knee, C.outline, 3);
  r.line(p.knee, p.hip, C.outline, 4);
  r.line(p.ankle, p.knee, C.pantsDark, 2);
  r.line(p.knee, p.hip, C.pants, 3);
  r.rect(p.ankle.x - 3, p.ankle.y - 1, 3, 2, C.shoe);

  r.rect(p.hip.x - 2, p.hip.y - 1, 5, 2, C.pants); // seat

  // Head (faces the stern, i.e. left) with hat and feather.
  const hx = Math.round(p.head.x);
  const hy = Math.round(p.head.y);
  r.rect(hx - 3, hy - 3, 7, 7, C.outline);
  r.rect(hx - 2, hy - 2, 5, 5, C.skin);
  r.rect(hx + 1, hy - 2, 2, 4, C.hair); // back of the head
  r.px(hx - 3, hy, C.skinDark); // nose
  r.px(hx - 1, hy - 1, C.outline); // eye
  r.rect(hx - 4, hy - 3, 9, 1, C.hatDark); // brim
  r.rect(hx - 2, hy - 5, 5, 2, C.hat); // crown
  r.line({ x: hx + 2, y: hy - 4 }, { x: hx + 5, y: hy - 7 }, C.feather);
  r.px(hx + 4, hy - 7, C.feather);

  // Near arm on top: upper arm, forearm, hands on the handle.
  r.line(p.shoulder, p.elbow, C.outline, 3);
  r.line(p.elbow, p.hand, C.outline, 3);
  r.line(p.shoulder, p.elbow, C.jacket, 2);
  r.line(p.elbow, p.hand, C.jacketLight, 2);
  r.rect(p.hand.x - 1, p.hand.y - 1, 2, 2, C.skin);
}

/** Draw one frame. `frame` only varies small water details. */
export function renderRowerFrame(ctx: CanvasRenderingContext2D, pose: RowerPose, frame = 0) {
  ctx.clearRect(0, 0, SPRITE_W, SPRITE_H);
  const r = new Raster(ctx);
  drawHull(r);
  drawRower(r, pose);
  drawOar(r, pose);
  drawSplash(r, pose, frame);
}

export const FRAME_COUNT = 48;

/** Pre-render a full stroke cycle plus a final "rest" frame. */
export function buildRowerFrames(): HTMLCanvasElement[] {
  const frames: HTMLCanvasElement[] = [];
  for (let i = 0; i <= FRAME_COUNT; i++) {
    const canvas = document.createElement("canvas");
    canvas.width = SPRITE_W;
    canvas.height = SPRITE_H;
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("2D canvas unavailable");
    ctx.imageSmoothingEnabled = false;
    const pose = i === FRAME_COUNT ? restPose() : rowerPose(i / FRAME_COUNT);
    renderRowerFrame(ctx, pose, i);
    frames.push(canvas);
  }
  return frames;
}

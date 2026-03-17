/**
 * RowingScene — Pixi.js pixel-art parallax rowing scene.
 *
 * Drop-in replacement for the SVG version; same props interface.
 * Uses GPU-accelerated TilingSprites for parallax background layers
 * and an AnimatedSprite synced to the current stroke rate.
 *
 * Assets (pre-extracted to dashboard/public/assets/rowing/):
 *   sky.png, mountains.png, treeline.png, water.png, rower-spritesheet.png
 */

import { useRef, useEffect } from "react";
import {
  Application,
  Assets,
  TilingSprite,
  Texture,
  Rectangle,
  AnimatedSprite,
  TextureSource,
} from "pixi.js";
import "./RowingScene.css";

type RowingSceneProps = {
  strokeRate: number | null;
  pace: number | null;
  isActive: boolean;
  isPaused: boolean;
};

const ASSET_BASE = "/assets/rowing/";

// Spritesheet layout: 5 columns × 4 rows = 20 frames
const NUM_COLS = 5;
const NUM_ROWS = 4;
const NUM_FRAMES = NUM_COLS * NUM_ROWS;

function paceToSpeed(pace: number | null): number {
  if (!pace || pace <= 0) return 0;
  return 3600 / pace;
}

function sceneHeight(): number {
  return window.innerWidth >= 768 ? 240 : 200;
}

export function RowingScene({
  strokeRate,
  pace,
  isActive,
  isPaused,
}: RowingSceneProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const rowerRef = useRef<AnimatedSprite | null>(null);
  const targetSpeedRef = useRef(0);
  const currentSpeedRef = useRef(0);

  // Keep derived state in refs so async init can read current values
  const isRowingRef = useRef(false);
  const strokeRateRef = useRef<number | null>(strokeRate);

  const isRowing = isActive && !isPaused && (strokeRate ?? 0) > 0;

  // Sync refs on every render
  isRowingRef.current = isRowing;
  strokeRateRef.current = strokeRate;
  targetSpeedRef.current = isRowing ? paceToSpeed(pace) : 0;

  // Update rower animation whenever stroke rate / active state changes
  useEffect(() => {
    const rower = rowerRef.current;
    if (!rower) return;
    if (!isRowing || !strokeRate) {
      rower.stop();
      rower.currentFrame = 0;
    } else {
      rower.animationSpeed = (NUM_FRAMES * strokeRate) / 3600;
      if (!rower.playing) rower.play();
    }
  }, [isRowing, strokeRate]);

  // One-time Pixi initialisation
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    let destroyed = false;
    let app: Application | null = null;
    let ro: ResizeObserver | null = null;

    (async () => {
      // Nearest-neighbour for crisp pixel art — must set before any texture load
      TextureSource.defaultOptions.scaleMode = "nearest";

      const H = sceneHeight();
      const W = container.clientWidth || 375;

      app = new Application();
      await app.init({
        width: W,
        height: H,
        backgroundAlpha: 0,
        antialias: false,
        resolution: window.devicePixelRatio ?? 1,
        autoDensity: true,
      });

      if (destroyed) {
        app.destroy(true);
        return;
      }

      container.appendChild(app.canvas);

      // Load all assets in parallel
      const [skyTex, mtnTex, treeTex, waterTex, rowerSheetTex] =
        await Promise.all([
          Assets.load(ASSET_BASE + "sky.png"),
          Assets.load(ASSET_BASE + "mountains.png"),
          Assets.load(ASSET_BASE + "treeline.png"),
          Assets.load(ASSET_BASE + "water.png"),
          Assets.load(ASSET_BASE + "rower-spritesheet.png"),
        ]);

      if (destroyed) return;

      // ── Build scene ──────────────────────────────────────────────

      function buildScene(W: number, H: number) {
        // Vertical layout constants (as fractions of scene height)
        const waterY = Math.round(H * 0.58);
        const waterH = H - waterY;

        // Sky: stretches to fill full scene
        const skyScale = H / skyTex.height;
        const sky = new TilingSprite({
          texture: skyTex,
          width: W,
          height: H,
        });
        sky.tileScale.set(skyScale);

        // Mountains: positioned so bottom aligns with upper waterline area
        const mtnScale = (H * 0.52) / mtnTex.height;
        const mtnH = Math.round(mtnTex.height * mtnScale);
        const mtn = new TilingSprite({
          texture: mtnTex,
          width: W,
          height: mtnH,
        });
        mtn.y = waterY - mtnH;
        mtn.tileScale.set(mtnScale);

        // Treeline: bottom aligns with waterline
        const treeScale = (H * 0.42) / treeTex.height;
        const treeH = Math.round(treeTex.height * treeScale);
        const tree = new TilingSprite({
          texture: treeTex,
          width: W,
          height: treeH,
        });
        tree.y = waterY - treeH;
        tree.tileScale.set(treeScale);

        // Water: fills bottom of scene
        const waterScale = waterH / waterTex.height;
        const water = new TilingSprite({
          texture: waterTex,
          width: W,
          height: waterH,
        });
        water.y = waterY;
        water.tileScale.set(waterScale);

        return { sky, mtn, tree, water };
      }

      const { sky, mtn, tree, water } = buildScene(W, H);
      app!.stage.addChild(sky);
      app!.stage.addChild(mtn);
      app!.stage.addChild(tree);
      app!.stage.addChild(water);

      // ── Rower AnimatedSprite ──────────────────────────────────────

      const fw = Math.floor(rowerSheetTex.width / NUM_COLS);
      const fh = Math.floor(rowerSheetTex.height / NUM_ROWS);

      const frames: Texture[] = [];
      for (let row = 0; row < NUM_ROWS; row++) {
        for (let col = 0; col < NUM_COLS; col++) {
          frames.push(
            new Texture({
              source: rowerSheetTex.source,
              frame: new Rectangle(col * fw, row * fh, fw, fh),
            }),
          );
        }
      }

      function makeRower(W: number, H: number): AnimatedSprite {
        const waterY = Math.round(H * 0.58);
        const rowerScale = (H * 0.50) / fh;
        const rowerW = fw * rowerScale;
        const rowerH = fh * rowerScale;
        const rower = new AnimatedSprite(frames);
        rower.scale.set(rowerScale);
        rower.x = Math.round((W - rowerW) / 2);
        // Position rower so boat hull sits at waterline
        rower.y = waterY - Math.round(rowerH * 0.88);
        rower.animationSpeed = 0;
        rower.currentFrame = 0;
        return rower;
      }

      const rower = makeRower(W, H);
      rowerRef.current = rower;
      app!.stage.addChild(rower);

      // Apply current animation state (might have changed while assets loaded)
      if (isRowingRef.current && strokeRateRef.current) {
        rower.animationSpeed = (NUM_FRAMES * strokeRateRef.current) / 3600;
        rower.play();
      }

      // ── Ticker: parallax scroll ──────────────────────────────────

      app!.ticker.add((ticker) => {
        const dt = ticker.deltaTime;

        // Smooth lerp toward target speed (~2 s to reach target at 60fps)
        const diff = targetSpeedRef.current - currentSpeedRef.current;
        currentSpeedRef.current += diff * Math.min(dt * 0.033, 1);

        const spd = currentSpeedRef.current;
        sky.tilePosition.x -= spd * 0.02 * dt;
        mtn.tilePosition.x -= spd * 0.06 * dt;
        tree.tilePosition.x -= spd * 0.18 * dt;
        water.tilePosition.x -= spd * 0.40 * dt;
      });

      // ── ResizeObserver ───────────────────────────────────────────

      ro = new ResizeObserver(([entry]) => {
        if (!app) return;
        const W2 = Math.round(entry.contentRect.width);
        const H2 = sceneHeight();
        if (W2 === 0) return;

        app.renderer.resize(W2, H2);

        const waterY2 = Math.round(H2 * 0.58);
        const waterH2 = H2 - waterY2;

        sky.width = W2;
        sky.height = H2;
        sky.tileScale.set(H2 / skyTex.height);

        const mtnScale2 = (H2 * 0.52) / mtnTex.height;
        const mtnH2 = Math.round(mtnTex.height * mtnScale2);
        mtn.width = W2;
        mtn.height = mtnH2;
        mtn.y = waterY2 - mtnH2;
        mtn.tileScale.set(mtnScale2);

        const treeScale2 = (H2 * 0.42) / treeTex.height;
        const treeH2 = Math.round(treeTex.height * treeScale2);
        tree.width = W2;
        tree.height = treeH2;
        tree.y = waterY2 - treeH2;
        tree.tileScale.set(treeScale2);

        water.width = W2;
        water.height = waterH2;
        water.y = waterY2;
        water.tileScale.set(waterH2 / waterTex.height);

        const rowerScale2 = (H2 * 0.50) / fh;
        const rowerW2 = fw * rowerScale2;
        const rowerH2 = fh * rowerScale2;
        rower.scale.set(rowerScale2);
        rower.x = Math.round((W2 - rowerW2) / 2);
        rower.y = waterY2 - Math.round(rowerH2 * 0.88);
      });

      ro.observe(container);
    })();

    return () => {
      destroyed = true;
      ro?.disconnect();
      rowerRef.current = null;
      if (app) {
        app.destroy(true, { children: true });
        app = null;
      }
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return <div className="rowing-scene" ref={containerRef} />;
}

/**
 * RowingScene — Pixi.js pixel-art parallax rowing scene.
 *
 * Layer stack (back → front):
 *   far-background  — mountains + sunset sky
 *   mid-background  — forest treeline
 *   gameplay        — water surface with shoreline
 *   foreground      — cattail/marsh silhouette
 *   rower           — procedural sculler (see rowing/rowerSprite.ts), in
 *                     front so the near oar is never hidden
 *
 * The rower's pose follows a continuous stroke phase advanced at the live
 * stroke rate, and the scroll speed surges on the drive and glides on the
 * recovery, so the scene reads like real rowing rather than a frame loop.
 */

import { useEffect, useRef } from "react";
import { Application, Assets, Sprite, Texture, TextureSource, TilingSprite } from "pixi.js";
import {
  DRIVE_FRACTION,
  FRAME_COUNT,
  SPRITE_H,
  SPRITE_W,
  WATERLINE_Y,
  buildRowerFrames,
} from "@/components/rowing/rowerSprite";
import "./RowingScene.css";

type RowingSceneProps = {
  strokeRate: number | null;
  pace: number | null;
  isActive: boolean;
  isPaused: boolean;
};

const ASSET_BASE = "/assets/rowing/";
/** Global scroll speed scale. */
const SCROLL_SCALE = 0.45;
/** Phase just after the finish, where the rower settles when stopping. */
const REST_PHASE = DRIVE_FRACTION + 0.04;
/** Fraction of the scene height where the water surface sits. */
const WATER_FRAC = 0.835;
// Measured from the source images.
const GAMEPLAY_SHORELINE_FRAC = 480 / 864;
const FG_CONTENT_END_FRAC = 641 / 864;

type Live = { isRowing: boolean; strokeRate: number; boatSpeed: number };

function paceToSpeed(pace: number | null): number {
  if (!pace || pace <= 0) return 0;
  return 3600 / pace;
}

function sceneHeight(): number {
  const w = window.innerWidth;
  const h = window.innerHeight;
  if (w >= 768 && h <= 820) return 160; // iPad landscape
  if (w >= 768) return 240; // iPad portrait
  return 200; // iPhone
}

/** Speed multiplier through the stroke: surge on the drive, glide on the recovery. */
function surge(phase: number): number {
  if (phase < DRIVE_FRACTION) return 1 + 0.2 * Math.sin((Math.PI * phase) / DRIVE_FRACTION);
  return 1 - 0.1 * Math.sin((Math.PI * (phase - DRIVE_FRACTION)) / (1 - DRIVE_FRACTION));
}

export function RowingScene({ strokeRate, pace, isActive, isPaused }: RowingSceneProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const liveRef = useRef<Live>({ isRowing: false, strokeRate: 0, boatSpeed: 0 });

  const isRowing = isActive && !isPaused && (strokeRate ?? 0) > 0;

  // Hand the latest values to the Pixi ticker without re-running init.
  useEffect(() => {
    liveRef.current = {
      isRowing,
      strokeRate: isRowing ? (strokeRate ?? 0) : 0,
      boatSpeed: isRowing ? paceToSpeed(pace) : 0,
    };
  }, [isRowing, strokeRate, pace]);

  // One-time Pixi initialisation
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    let destroyed = false;
    let app: Application | null = null;
    let ro: ResizeObserver | null = null;
    let onVisibilityChange: (() => void) | null = null;

    void (async () => {
      // Nearest-neighbour for crisp pixel art — must be set before textures load.
      TextureSource.defaultOptions.scaleMode = "nearest";

      const dpr = window.devicePixelRatio ?? 1;
      app = new Application();
      await app.init({
        width: container.clientWidth || 375,
        height: sceneHeight(),
        background: 0x0a1428, // shows through transparent sky areas
        antialias: false,
        hello: false,
        resolution: dpr,
        autoDensity: true,
      });

      if (destroyed) {
        try {
          app.destroy(true);
        } catch {
          // ignore
        }
        return;
      }

      container.appendChild(app.canvas);
      app.stage.eventMode = "none"; // nothing is interactive; skip hit-testing

      const [farBgTex, midBgTex, gameplayTex, fgTex] = await Promise.all([
        Assets.load<Texture>(ASSET_BASE + "far-background-2.png"),
        Assets.load<Texture>(ASSET_BASE + "mid-background-1.png"),
        Assets.load<Texture>(ASSET_BASE + "gameplay.png"),
        Assets.load<Texture>(ASSET_BASE + "foreground.png"),
      ]);
      if (destroyed || !app) return;

      const farBg = new TilingSprite({ texture: farBgTex });
      const midBg = new TilingSprite({ texture: midBgTex });
      const gameplay = new TilingSprite({ texture: gameplayTex });
      const fg = new TilingSprite({ texture: fgTex });

      const rowerFrames = buildRowerFrames().map((canvas) => Texture.from(canvas));
      const rower = new Sprite(rowerFrames[FRAME_COUNT]); // rest pose
      rower.anchor.set(0.5, (WATERLINE_Y + 1) / SPRITE_H);

      // The rower sits in front of the cattails so the near oar is never hidden.
      app.stage.addChild(farBg, midBg, gameplay, fg, rower);

      let rowerBaseY = 0;

      function layout(W: number, H: number) {
        const shorelineY = Math.round(H * 0.83);

        farBg.width = W;
        farBg.height = H;
        farBg.tileScale.set((H * 1.2) / farBgTex.height);

        const midScale = (H * 0.62) / midBgTex.height;
        midBg.width = W;
        midBg.height = Math.round(midBgTex.height * midScale);
        midBg.y = shorelineY - midBg.height;
        midBg.tileScale.set(midScale);

        gameplay.width = W;
        gameplay.height = H - shorelineY * 0.45;
        gameplay.y = shorelineY * 0.85;
        gameplay.tileScale.set(H / gameplayTex.height);
        gameplay.tilePosition.y = -Math.round(H * GAMEPLAY_SHORELINE_FRAC);

        const fgScale = (H * 0.5) / fgTex.height;
        fg.width = W;
        fg.height = Math.round(fgTex.height * fgScale);
        fg.y = H - Math.round(fg.height * FG_CONTENT_END_FRAC);
        fg.tileScale.set(fgScale);

        // Snap the rower's scale to whole device pixels so its pixels stay even.
        const scale = Math.max(1, Math.round((H / 100) * dpr)) / dpr;
        rower.scale.set(Math.min(scale, (W * 0.8) / SPRITE_W));
        rower.x = Math.round(W / 2);
        rowerBaseY = Math.round(H * WATER_FRAC);
        rower.y = rowerBaseY;
      }

      layout(container.clientWidth || 375, sceneHeight());

      // ── Ticker ───────────────────────────────────────────────────
      let phase = REST_PHASE;
      let atRest = true;
      let strokeRateNow = 0; // smoothed SPM
      let speedNow = 0; // smoothed boat speed
      let bobTime = 0;

      app.ticker.add((ticker) => {
        const dt = Math.min(ticker.deltaMS, 100) / 1000; // seconds, clamped after tab switches
        const live = liveRef.current;
        const smoothing = Math.min(dt * 2, 1); // ~0.5 s time constant

        if (live.isRowing) {
          atRest = false;
          strokeRateNow += (live.strokeRate - strokeRateNow) * smoothing;
        }

        if (!atRest) {
          // Keep at least a gentle rate so a stopping rower finishes the stroke.
          const spm = live.isRowing ? strokeRateNow : Math.max(strokeRateNow, 16);
          const prev = phase;
          phase = (phase + (spm / 60) * dt) % 1;
          const crossedRest =
            (prev < REST_PHASE && phase >= REST_PHASE) || (prev > phase && phase >= REST_PHASE);
          if (!live.isRowing && crossedRest) {
            atRest = true;
            phase = REST_PHASE;
          }
        }

        rower.texture = atRest ? rowerFrames[FRAME_COUNT] : rowerFrames[Math.floor(phase * FRAME_COUNT) % FRAME_COUNT];

        speedNow += (live.boatSpeed - speedNow) * Math.min(dt * 1.2, 1);
        const spd = speedNow * (atRest ? 1 : surge(phase));

        // Idle bob that fades out as the boat gets moving.
        bobTime += dt * 1.8;
        rower.y = Math.round(rowerBaseY + 2 * Math.max(0, 1 - spd / 3) * Math.sin(bobTime));

        if (spd < 0.01) return;
        const step = spd * SCROLL_SCALE * dt * 60;
        farBg.tilePosition.x -= step * 0.01;
        midBg.tilePosition.x -= step * 0.1;
        gameplay.tilePosition.x -= step * 0.2;
        fg.tilePosition.x -= step * 0.6;
      });

      // Pause rendering while the tab is hidden to save battery.
      onVisibilityChange = () => {
        if (!app) return;
        if (document.hidden) app.ticker.stop();
        else app.ticker.start();
      };
      document.addEventListener("visibilitychange", onVisibilityChange);

      ro = new ResizeObserver(([entry]) => {
        if (!app) return;
        const W = Math.round(entry.contentRect.width);
        if (W === 0) return;
        const H = sceneHeight();
        app.renderer.resize(W, H);
        layout(W, H);
      });
      ro.observe(container);
    })();

    return () => {
      destroyed = true;
      ro?.disconnect();
      if (onVisibilityChange) document.removeEventListener("visibilitychange", onVisibilityChange);
      if (app) {
        try {
          app.destroy(true, { children: true });
        } catch {
          // Pixi may throw if destroyed before fully initialised (StrictMode double-invoke)
        }
        app = null;
      }
    };
  }, []);

  return <div className="rowing-scene" ref={containerRef} />;
}

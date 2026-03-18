/**
 * RowingScene — Pixi.js pixel-art parallax rowing scene.
 *
 * Drop-in replacement for the SVG version; same props interface.
 * Uses GPU-accelerated TilingSprites for parallax background layers
 * and an AnimatedSprite synced to the current stroke rate.
 *
 * Assets (pre-extracted to dashboard/public/assets/rowing/):
 *   far-background.png, mid-background.png, gameplay.png,
 *   foreground.png, rower-spritesheet.png
 *
 * Layer stack (back → front):
 *   bgFill          — solid dark-navy fill behind all layers
 *   far-background  — mountains + sunset sky (0.03x scroll)
 *   mid-background  — forest treeline (0.12x scroll)
 *   gameplay        — water surface with shoreline (0.30x scroll)
 *   rower           — animated sprite on the water
 *   foreground      — cattail/marsh silhouette (0.60x scroll)
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
    let onVisibilityChange: (() => void) | null = null;

    (async () => {
      // Nearest-neighbour for crisp pixel art — must set before any texture load
      TextureSource.defaultOptions.scaleMode = "nearest";

      const H = sceneHeight();
      const W = container.clientWidth || 375;

      app = new Application();
      await app.init({
        width: W,
        height: H,
        background: 0x0a1428, // dark navy — shows through transparent sky areas in assets
        backgroundAlpha: 1,
        antialias: false,
        hello: false, // suppress console banner
        resolution: window.devicePixelRatio ?? 1,
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

      // Nothing in the scene is interactive; skip hit-testing entirely
      app.stage.eventMode = "none";

      // Load all assets in parallel
      const [farBgTex, midBgTex, gameplayTex, fgTex, rowerSheetTex] =
        await Promise.all([
          Assets.load(ASSET_BASE + "far-background.png"),
          Assets.load(ASSET_BASE + "mid-background.png"),
          Assets.load(ASSET_BASE + "gameplay.png"),
          Assets.load(ASSET_BASE + "foreground.png"),
          Assets.load(ASSET_BASE + "rower-spritesheet.png"),
        ]);

      if (destroyed) return;

      // ── Build scene ──────────────────────────────────────────────

      // Fraction of gameplay image where water content starts (measured from top)
      const GAMEPLAY_SHORELINE_FRAC = 480 / 864;
      // Fraction of foreground image where cattail content ends (measured from top)
      const FG_CONTENT_END_FRAC = 641 / 864;

      function buildScene(W: number, H: number) {
        // shorelineY: trees bottom; gameplay.y is offset slightly above this
        // rowerHullY: boat hull in the open water area
        const shorelineY = Math.round(H * 0.83);
        const rowerHullY = Math.round(H * 0.73);

        // Far background: 1.2× height-based scale so mountains appear fuller/taller
        const farBgScale = (H * 1.2) / farBgTex.height;
        const farBg = new TilingSprite({
          texture: farBgTex,
          width: W,
          height: H,
        });
        farBg.tileScale.set(farBgScale);

        // Mid background: trees (0.62), bottom at shorelineY
        const midBgScale = (H * 0.62) / midBgTex.height;
        const midBgH = Math.round(midBgTex.height * midBgScale);
        const midBg = new TilingSprite({
          texture: midBgTex,
          width: W,
          height: midBgH,
        });
        midBg.y = shorelineY - midBgH;
        midBg.tileScale.set(midBgScale);

        // Gameplay layer: tilePosition.y aligns water content to top of sprite
        const gameplayScale = H / gameplayTex.height;
        const gameplayH = H - shorelineY * 0.45;
        const gameplay = new TilingSprite({
          texture: gameplayTex,
          width: W,
          height: gameplayH,
        });
        gameplay.y = shorelineY * 0.85;
        gameplay.tileScale.set(gameplayScale);
        gameplay.tilePosition.y = -Math.round(H * GAMEPLAY_SHORELINE_FRAC);

        // Foreground: cattail silhouette — align content bottom with scene bottom
        const fgScale = (H * 0.5) / fgTex.height;
        const fgH = Math.round(fgTex.height * fgScale);
        const fg = new TilingSprite({
          texture: fgTex,
          width: W,
          height: fgH,
        });
        fg.y = H - Math.round(fgH * FG_CONTENT_END_FRAC);
        fg.tileScale.set(fgScale);

        return { farBg, midBg, gameplay, fg, shorelineY, rowerHullY };
      }

      const { farBg, midBg, gameplay, fg, rowerHullY } = buildScene(W, H);
      app!.stage.addChild(farBg);
      app!.stage.addChild(midBg);
      app!.stage.addChild(gameplay);

      // ── Rower AnimatedSprite ──────────────────────────────────────

      const fw = Math.floor(rowerSheetTex.width / NUM_COLS);
      const fh = Math.floor(rowerSheetTex.height / NUM_ROWS);
      // Skip 1px at top of each row to exclude dark border at y=0 of spritesheet
      const SPRITE_Y_OFFSET = 1;
      const effectiveFh = fh - SPRITE_Y_OFFSET;

      const frames: Texture[] = [];
      for (let row = 0; row < NUM_ROWS; row++) {
        for (let col = 0; col < NUM_COLS; col++) {
          frames.push(
            new Texture({
              source: rowerSheetTex.source,
              frame: new Rectangle(col * fw + 25, row * fh + SPRITE_Y_OFFSET, fw, effectiveFh),
            }),
          );
        }
      }

      function makeRower(W: number, hullY: number): AnimatedSprite {
        const rowerScale = (H * 0.30) / effectiveFh;
        const rowerW = fw * rowerScale;
        const rowerH = effectiveFh * rowerScale;
        const rower = new AnimatedSprite(frames);
        rower.scale.set(rowerScale);
        rower.x = Math.round((W - rowerW) / 2);
        // Position rower so boat hull sits at hullY
        rower.y = hullY - Math.round(rowerH * 0.38);
        rower.animationSpeed = 0;
        rower.currentFrame = 0;
        return rower;
      }

      const rower = makeRower(W, rowerHullY);
      let rowerBaseY = rower.y;
      rowerRef.current = rower;
      app!.stage.addChild(rower);

      // Foreground renders in front of the rower for depth
      app!.stage.addChild(fg);

      // Apply current animation state (might have changed while assets loaded)
      if (isRowingRef.current && strokeRateRef.current) {
        rower.animationSpeed = (NUM_FRAMES * strokeRateRef.current) / 3600;
        rower.play();
      }

      // ── Ticker: parallax scroll ──────────────────────────────────

      let bobTime = 0;

      app!.ticker.add((ticker) => {
        const dt = ticker.deltaTime;

        // Smooth lerp toward target speed (~2 s to reach target at 60fps)
        const diff = targetSpeedRef.current - currentSpeedRef.current;
        currentSpeedRef.current += diff * Math.min(dt * 0.033, 1);

        const spd = currentSpeedRef.current;

        // Idle bob: gentle sine wave, fades out as the boat accelerates
        bobTime += dt * 0.03; // ~3.5 s per cycle at 60 fps
        const bobStrength = Math.max(0, 1 - spd / 3);
        rower.y = Math.round(rowerBaseY + 3 * bobStrength * Math.sin(bobTime));

        // Skip scroll writes when effectively stationary
        if (Math.abs(spd) < 0.01) return;

        farBg.tilePosition.x -= spd * 0.03 * dt;
        midBg.tilePosition.x -= spd * 0.12 * dt;
        gameplay.tilePosition.x -= spd * 0.30 * dt;
        fg.tilePosition.x -= spd * 0.60 * dt;
      });

      // Pause rendering when the tab is hidden to save battery on mobile
      onVisibilityChange = () => {
        if (!app) return;
        if (document.hidden) app.ticker.stop();
        else app.ticker.start();
      };
      document.addEventListener("visibilitychange", onVisibilityChange);

      // ── ResizeObserver ───────────────────────────────────────────

      ro = new ResizeObserver(([entry]) => {
        if (!app) return;
        const W2 = Math.round(entry.contentRect.width);
        const H2 = sceneHeight();
        if (W2 === 0) return;

        app.renderer.resize(W2, H2);

        const shorelineY2 = Math.round(H2 * 0.83);
        const rowerHullY2 = Math.round(H2 * 0.73);

        farBg.width = W2;
        farBg.height = H2;
        farBg.tileScale.set((H2 * 1.2) / farBgTex.height);

        const midBgScale2 = (H2 * 0.62) / midBgTex.height;
        const midBgH2 = Math.round(midBgTex.height * midBgScale2);
        midBg.width = W2;
        midBg.height = midBgH2;
        midBg.y = shorelineY2 - midBgH2;
        midBg.tileScale.set(midBgScale2);

        gameplay.width = W2;
        gameplay.height = H2 - (shorelineY2 * 0.45);
        gameplay.y = (shorelineY2 * 0.85);
        gameplay.tileScale.set(H2 / gameplayTex.height);
        gameplay.tilePosition.y = -Math.round(H2 * GAMEPLAY_SHORELINE_FRAC);

        const fgScale2 = (H2 * 0.5) / fgTex.height;
        const fgH2 = Math.round(fgTex.height * fgScale2);
        fg.width = W2;
        fg.height = fgH2;
        fg.y = H2 - Math.round(fgH2 * FG_CONTENT_END_FRAC);
        fg.tileScale.set(fgScale2);

        const rowerScale2 = (H2 * 0.30) / effectiveFh;
        const rowerW2 = fw * rowerScale2;
        const rowerH2 = effectiveFh * rowerScale2;
        rower.scale.set(rowerScale2);
        rower.x = Math.round((W2 - rowerW2) / 2);
        rowerBaseY = rowerHullY2 - Math.round(rowerH2 * 0.38);
        rower.y = rowerBaseY;
      });

      ro.observe(container);
    })();

    return () => {
      destroyed = true;
      ro?.disconnect();
      if (onVisibilityChange) {
        document.removeEventListener("visibilitychange", onVisibilityChange);
      }
      rowerRef.current = null;
      if (app) {
        try {
          app.destroy(true, { children: true });
        } catch {
          // Pixi may throw if destroyed before fully initialized (React StrictMode double-invoke)
        }
        app = null;
      }
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return <div className="rowing-scene" ref={containerRef} />;
}

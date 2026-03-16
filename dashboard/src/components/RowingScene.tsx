/**
 * RowingScene — parallax rowing animation.
 *
 * Layers (back to front):
 *   5. Sky gradient + clouds
 *   4. Distant mountains (SVG silhouette, tiling)
 *   3. Treeline (SVG silhouette, tiling)
 *   2. Water surface + wake
 *   1. Rower + boat (centered)
 *
 * Parallax scroll speed scales with rowing pace.
 * Rower bobs when idle, rows at stroke-rate cadence when active.
 */

import { useRef, useEffect, useCallback } from "react";
import "./RowingScene.css";

type RowingSceneProps = {
  strokeRate: number | null;
  pace: number | null;
  isActive: boolean;
  isPaused: boolean;
};

/* ── SVG Assets (inline, no fetches) ── */

/** Distant mountain range — repeating tile */
function MountainsSVG() {
  return (
    <svg viewBox="0 0 800 120" preserveAspectRatio="none" fill="oklch(0.30 0.03 250)">
      <path d="M0,120 L0,80 L40,45 L70,65 L110,25 L150,60 L180,40 L220,70 L250,20 L290,55 L320,35 L360,65 L400,15 L440,55 L470,30 L510,60 L540,40 L580,70 L610,25 L650,55 L690,45 L720,65 L760,30 L800,60 L800,120 Z" />
      {/* Snow caps */}
      <g fill="oklch(0.65 0.015 250)" opacity="0.5">
        <polygon points="110,25 120,35 100,35" />
        <polygon points="250,20 262,32 238,32" />
        <polygon points="400,15 413,28 387,28" />
        <polygon points="610,25 622,37 598,37" />
        <polygon points="760,30 772,42 748,42" />
      </g>
    </svg>
  );
}

/** Treeline — repeating tile */
function TreelineSVG() {
  return (
    <svg viewBox="0 0 800 80" preserveAspectRatio="none">
      {/* Dark forest fill */}
      <path
        fill="oklch(0.22 0.04 160)"
        d="M0,80 L0,50 L15,25 L30,45 L40,20 L50,42 L65,15 L80,40 L95,22 L110,38 L120,10 L135,35 L150,20 L165,42 L175,18 L190,40 L205,12 L220,38 L235,25 L250,45 L260,18 L275,40 L290,8 L305,35 L320,22 L335,42 L345,15 L360,38 L375,20 L390,45 L400,14 L415,38 L430,22 L445,42 L455,16 L470,40 L485,10 L500,35 L515,25 L530,45 L540,18 L555,42 L570,12 L585,38 L600,20 L615,44 L625,16 L640,40 L655,22 L670,45 L680,14 L695,38 L710,8 L725,35 L740,25 L755,42 L770,18 L785,40 L800,22 L800,80 Z"
      />
      {/* Slightly lighter layer for depth */}
      <path
        fill="oklch(0.25 0.035 155)"
        opacity="0.6"
        d="M0,80 L0,55 L20,35 L45,50 L60,30 L85,48 L100,28 L125,46 L140,32 L165,50 L180,26 L205,48 L220,34 L245,52 L260,28 L285,46 L300,32 L325,50 L340,24 L365,46 L380,34 L405,52 L420,28 L445,48 L460,30 L485,50 L500,26 L525,48 L540,34 L565,52 L580,28 L605,46 L620,32 L645,50 L660,24 L685,48 L700,30 L725,50 L740,28 L765,46 L780,32 L800,48 L800,80 Z"
      />
    </svg>
  );
}

/** Water ripple pattern — repeating tile */
function WaterRippleSVG() {
  return (
    <svg viewBox="0 0 800 40" preserveAspectRatio="none">
      <g stroke="oklch(0.45 0.06 220)" strokeWidth="0.5" fill="none" opacity="0.5">
        <path d="M0,8 Q50,4 100,8 T200,8 T300,8 T400,8 T500,8 T600,8 T700,8 T800,8" />
        <path d="M0,18 Q50,14 100,18 T200,18 T300,18 T400,18 T500,18 T600,18 T700,18 T800,18" />
        <path d="M0,28 Q50,24 100,28 T200,28 T300,28 T400,28 T500,28 T600,28 T700,28 T800,28" />
      </g>
    </svg>
  );
}

/** Rower in a boat — simple side-view silhouette */
function RowerSVG({ isRowing }: { isRowing: boolean }) {
  return (
    <svg viewBox="0 0 96 56" fill="none" xmlns="http://www.w3.org/2000/svg" style={{ width: "100%", height: "100%" }}>
      {/* Boat hull */}
      <path
        d="M12,38 Q14,44 30,46 L70,46 Q86,44 88,38 L82,36 Q78,40 48,40 Q18,40 14,36 Z"
        fill="oklch(0.38 0.06 45)"
        stroke="oklch(0.30 0.05 40)"
        strokeWidth="0.5"
      />
      {/* Boat gunwale line */}
      <path
        d="M14,36 Q18,39 48,39 Q78,39 82,36"
        fill="none"
        stroke="oklch(0.45 0.07 48)"
        strokeWidth="0.8"
      />

      {/* Rower body group */}
      <g>
        {/* Torso */}
        <path
          d="M50,18 L48,32 L54,32 L52,18 Z"
          fill="oklch(0.45 0.10 220)"
          stroke="oklch(0.35 0.08 225)"
          strokeWidth="0.4"
        />
        {/* Head */}
        <circle cx="51" cy="14" r="4.5" fill="oklch(0.62 0.06 60)" />
        {/* Hat */}
        <path
          d="M46,13 Q51,8 56,13"
          fill="oklch(0.40 0.06 240)"
          stroke="oklch(0.32 0.05 240)"
          strokeWidth="0.4"
        />
        {/* Arms */}
        <path
          d="M48,22 L38,28"
          stroke="oklch(0.55 0.05 60)"
          strokeWidth="1.8"
          strokeLinecap="round"
        />
        <path
          d="M54,22 L62,28"
          stroke="oklch(0.55 0.05 60)"
          strokeWidth="1.8"
          strokeLinecap="round"
        />
        {/* Legs (on the slide) */}
        <path
          d="M48,32 L42,38"
          stroke="oklch(0.35 0.06 250)"
          strokeWidth="2"
          strokeLinecap="round"
        />
        <path
          d="M54,32 L58,38"
          stroke="oklch(0.35 0.06 250)"
          strokeWidth="2"
          strokeLinecap="round"
        />
      </g>

      {/* Oar */}
      <g className={isRowing ? "rowing-oar--active" : "rowing-oar--idle"}>
        <line
          x1="38" y1="28" x2="18" y2="42"
          stroke="oklch(0.48 0.04 55)"
          strokeWidth="1.2"
          strokeLinecap="round"
        />
        {/* Oar blade */}
        <ellipse cx="16" cy="43" rx="4" ry="1.5" fill="oklch(0.42 0.05 50)" transform="rotate(-15 16 43)" />
      </g>
    </svg>
  );
}

/* ── Parallax speeds for each layer ── */
const PARALLAX = {
  clouds: 0.05,
  mountains: 0.15,
  trees: 0.35,
  water: 0.7,
} as const;

/** Convert pace (s/500m) to pixels-per-second scroll speed */
function paceToSpeed(pace: number | null): number {
  if (pace == null || pace <= 0) return 0;
  // Faster pace (lower number) = faster scroll.
  // At 2:00/500m (120s) → ~30px/s base speed. At 1:30 (90s) → 40px/s.
  return 3600 / pace;
}

export function RowingScene({ strokeRate, pace, isActive, isPaused }: RowingSceneProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const offsetRef = useRef(0);
  const currentSpeedRef = useRef(0);
  const rafRef = useRef<number>(0);
  const lastTimeRef = useRef<number>(0);

  const isRowing = isActive && !isPaused && (strokeRate ?? 0) > 0;
  const targetSpeed = isRowing ? paceToSpeed(pace) : 0;

  const animate = useCallback((time: number) => {
    if (lastTimeRef.current === 0) {
      lastTimeRef.current = time;
      rafRef.current = requestAnimationFrame(animate);
      return;
    }

    const dt = Math.min((time - lastTimeRef.current) / 1000, 0.1); // cap delta
    lastTimeRef.current = time;

    // Smooth speed transition (ease toward target)
    const speed = currentSpeedRef.current;
    const diff = targetSpeed - speed;
    currentSpeedRef.current += diff * Math.min(dt * 2, 1); // ~0.5s ease

    // Advance offset
    if (Math.abs(currentSpeedRef.current) > 0.1) {
      offsetRef.current += currentSpeedRef.current * dt;
    }

    // Apply transforms to layers
    const container = containerRef.current;
    if (container) {
      const offset = offsetRef.current;
      const layers = container.querySelectorAll<HTMLElement>("[data-parallax]");
      for (const layer of layers) {
        const factor = parseFloat(layer.dataset.parallax ?? "0");
        const tx = -(offset * factor) % (layer.scrollWidth / 2 || 1);
        layer.style.transform = `translateX(${tx}px)`;
      }
    }

    rafRef.current = requestAnimationFrame(animate);
  }, [targetSpeed]);

  useEffect(() => {
    rafRef.current = requestAnimationFrame(animate);
    return () => {
      cancelAnimationFrame(rafRef.current);
      lastTimeRef.current = 0;
    };
  }, [animate]);

  // Rowing animation duration from stroke rate
  const strokeDuration = (strokeRate ?? 0) > 0 ? (60 / strokeRate!).toFixed(2) : "2";

  return (
    <div className="rowing-scene" ref={containerRef}>
      {/* Layer 5: Sky */}
      <div className="rowing-layer rowing-sky">
        {/* Clouds */}
        <div className="rowing-cloud" style={{ top: "12%", left: "15%", width: 40, height: 8 }} />
        <div className="rowing-cloud" style={{ top: "18%", left: "60%", width: 55, height: 10 }} />
        <div className="rowing-cloud" style={{ top: "8%", left: "82%", width: 30, height: 6 }} />
      </div>

      {/* Layer 4: Mountains */}
      <div className="rowing-layer rowing-mountains" data-parallax={PARALLAX.mountains}>
        <MountainsSVG />
      </div>

      {/* Layer 3: Treeline */}
      <div className="rowing-layer rowing-trees" data-parallax={PARALLAX.trees}>
        <TreelineSVG />
      </div>

      {/* Layer 2: Water */}
      <div className="rowing-layer rowing-water">
        <div className="rowing-water-ripple" data-parallax={PARALLAX.water}>
          <WaterRippleSVG />
        </div>
      </div>

      {/* Water shimmer overlay */}
      <div className="rowing-shimmer" />

      {/* Wake splash (visible when rowing) */}
      <div
        className="rowing-wake"
        style={{
          left: "calc(50% - 56px)",
          opacity: isRowing ? 1 : 0,
        }}
      >
        <div className="rowing-wake-line" style={{ width: 16, bottom: 2 }} />
        <div className="rowing-wake-line" style={{ width: 12, bottom: 0, left: -4 }} />
        <div className="rowing-wake-line" style={{ width: 10, bottom: -2, left: -8 }} />
      </div>

      {/* Layer 1: Rower */}
      <div
        className={`rowing-rower ${isRowing ? "rowing-rower--active" : "rowing-rower--idle"}`}
        style={isRowing ? { animationDuration: `${strokeDuration}s` } : undefined}
      >
        <RowerSVG isRowing={isRowing} />
      </div>
    </div>
  );
}

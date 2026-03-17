/**
 * RowingScene — parallax rowing animation (v2).
 *
 * Night-time lake scene with moonlit mountains, forest treeline,
 * reflective water, and a properly proportioned sculling rower.
 *
 * Layers (back → front):
 *   5. Night sky + moon + stars
 *   4. Distant mountain range (layered silhouettes)
 *   3. Forest treeline (two-depth silhouette)
 *   2. Water + ripples + moon reflection
 *   1. Rowing shell + rower + oars
 */

import { useRef, useEffect, useCallback } from "react";
import "./RowingScene.css";

type RowingSceneProps = {
  strokeRate: number | null;
  pace: number | null;
  isActive: boolean;
  isPaused: boolean;
};

/* ═══════════════════════════════════════════
   SVG Assets — all inline, zero network fetches
   ═══════════════════════════════════════════ */

/** Mountain range — two-layer silhouette with subtle gradient */
function MountainsSVG() {
  return (
    <svg viewBox="0 0 1200 200" preserveAspectRatio="xMidYMax slice">
      <defs>
        <linearGradient id="mtn-far" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#1e3050" />
          <stop offset="100%" stopColor="#182845" />
        </linearGradient>
        <linearGradient id="mtn-near" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#162540" />
          <stop offset="100%" stopColor="#122035" />
        </linearGradient>
      </defs>

      {/* Far range — taller, lighter */}
      <path
        fill="url(#mtn-far)"
        d="M0,200 L0,110 L30,95 L55,105 L80,70 L105,90 L130,55 L160,80
           L185,45 L210,75 L240,60 L265,85 L290,40 L320,70 L350,50
           L380,80 L405,35 L435,65 L460,45 L490,75 L515,30 L545,60
           L575,50 L600,25 L630,55 L655,40 L685,70 L710,35 L740,60
           L770,45 L795,75 L820,30 L850,65 L880,50 L905,80 L930,38
           L960,65 L990,48 L1015,78 L1040,42 L1070,68 L1095,52
           L1120,82 L1145,55 L1170,90 L1200,70 L1200,200 Z"
      />

      {/* Near range — shorter, darker */}
      <path
        fill="url(#mtn-near)"
        d="M0,200 L0,140 L35,120 L65,135 L95,105 L125,125 L155,95
           L185,118 L210,88 L240,110 L275,85 L300,108 L335,78 L360,100
           L395,75 L420,98 L455,72 L480,95 L510,80 L545,100 L570,75
           L600,95 L635,70 L660,92 L695,68 L720,90 L755,72 L780,95
           L810,78 L840,100 L870,75 L900,98 L930,80 L960,102 L990,76
           L1020,95 L1050,82 L1080,105 L1110,85 L1140,108 L1170,92
           L1200,115 L1200,200 Z"
      />

      {/* Snow highlights on tallest peaks */}
      <g fill="#3a4a68" opacity="0.6">
        <polygon points="185,45 195,58 175,58" />
        <polygon points="290,40 302,55 278,55" />
        <polygon points="515,30 528,46 502,46" />
        <polygon points="600,25 614,42 586,42" />
        <polygon points="820,30 833,46 807,46" />
      </g>
    </svg>
  );
}

/** Forest treeline — layered depth with varied tree shapes */
function TreelineSVG() {
  return (
    <svg viewBox="0 0 1200 120" preserveAspectRatio="xMidYMax slice">
      <defs>
        <linearGradient id="tree-back" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#0c1a18" />
          <stop offset="100%" stopColor="#0c2240" />
        </linearGradient>
        <linearGradient id="tree-front" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#091510" />
          <stop offset="100%" stopColor="#0c2240" />
        </linearGradient>
      </defs>

      {/* Back tree layer — lighter, taller */}
      <path
        fill="url(#tree-back)"
        d="M0,120 L0,65 L8,55 L12,62 L18,40 L24,58 L30,48 L36,60
           L42,35 L48,55 L54,42 L60,58 L68,30 L76,52 L82,38 L88,56
           L96,28 L104,50 L110,36 L116,54 L124,25 L132,48 L138,34
           L144,52 L152,22 L160,46 L168,32 L174,50 L182,20 L190,44
           L198,30 L204,48 L212,18 L220,42 L228,28 L234,46 L242,15
           L250,40 L258,26 L264,44 L272,20 L280,42 L288,28 L294,46
           L302,22 L310,44 L318,30 L324,48 L332,18 L340,42 L348,28
           L354,46 L362,15 L370,40 L378,26 L384,44 L392,20 L400,42
           L408,28 L414,46 L422,22 L430,44 L438,30 L444,48 L452,18
           L460,42 L468,28 L474,46 L482,15 L490,40 L498,26 L504,44
           L512,20 L520,42 L528,28 L534,46 L542,22 L550,44 L558,30
           L564,48 L572,18 L580,42 L588,28 L594,46 L602,22 L610,44
           L618,30 L624,48 L632,18 L640,42 L648,28 L654,46 L662,15
           L670,40 L678,26 L684,44 L692,20 L700,42 L708,28 L714,46
           L722,22 L730,44 L738,30 L744,48 L752,18 L760,42 L768,28
           L774,46 L782,15 L790,40 L798,26 L804,44 L812,20 L820,42
           L828,28 L834,46 L842,22 L850,44 L858,30 L864,48 L872,18
           L880,42 L888,28 L894,46 L902,22 L910,44 L918,30 L924,48
           L932,18 L940,42 L948,28 L954,46 L962,15 L970,40 L978,26
           L984,44 L992,20 L1000,42 L1008,28 L1014,46 L1022,22
           L1030,44 L1038,30 L1044,48 L1052,18 L1060,42 L1068,28
           L1074,46 L1082,22 L1090,44 L1098,30 L1104,48 L1112,18
           L1120,42 L1128,28 L1134,46 L1142,15 L1150,40 L1158,26
           L1164,44 L1172,20 L1180,42 L1188,28 L1194,46 L1200,35
           L1200,120 Z"
      />

      {/* Front tree layer — darker, shorter, offset */}
      <path
        fill="url(#tree-front)"
        d="M0,120 L0,72 L10,58 L18,68 L26,48 L34,64 L42,42 L50,60
           L58,50 L66,65 L74,38 L82,58 L90,45 L98,62 L106,35 L114,55
           L122,42 L130,58 L138,32 L146,52 L154,40 L162,56 L170,30
           L178,50 L186,38 L194,54 L202,28 L210,48 L218,36 L226,52
           L234,25 L242,46 L250,34 L258,50 L266,28 L274,48 L282,36
           L290,52 L298,30 L306,50 L314,38 L322,54 L330,28 L338,48
           L346,36 L354,52 L362,25 L370,46 L378,34 L386,50 L394,28
           L402,48 L410,36 L418,52 L426,30 L434,50 L442,38 L450,54
           L458,28 L466,48 L474,36 L482,52 L490,25 L498,46 L506,34
           L514,50 L522,28 L530,48 L538,36 L546,52 L554,30 L562,50
           L570,38 L578,54 L586,28 L594,48 L602,36 L610,52 L618,25
           L626,46 L634,34 L642,50 L650,28 L658,48 L666,36 L674,52
           L682,30 L690,50 L698,38 L706,54 L714,28 L722,48 L730,36
           L738,52 L746,25 L754,46 L762,34 L770,50 L778,28 L786,48
           L794,36 L802,52 L810,30 L818,50 L826,38 L834,54 L842,28
           L850,48 L858,36 L866,52 L874,25 L882,46 L890,34 L898,50
           L906,28 L914,48 L922,36 L930,52 L938,30 L946,50 L954,38
           L962,54 L970,28 L978,48 L986,36 L994,52 L1002,25 L1010,46
           L1018,34 L1026,50 L1034,28 L1042,48 L1050,36 L1058,52
           L1066,30 L1074,50 L1082,38 L1090,54 L1098,28 L1106,48
           L1114,36 L1122,52 L1130,25 L1138,46 L1146,34 L1154,50
           L1162,28 L1170,48 L1178,36 L1186,52 L1194,30 L1200,45
           L1200,120 Z"
      />
    </svg>
  );
}

/** Water ripple lines */
function WaterRipplesSVG() {
  return (
    <svg viewBox="0 0 1200 80" preserveAspectRatio="xMidYMid slice">
      <g fill="none" opacity="0.35">
        <path d="M0,12 Q30,8 60,12 T120,12 T180,12 T240,12 T300,12 T360,12 T420,12 T480,12 T540,12 T600,12 T660,12 T720,12 T780,12 T840,12 T900,12 T960,12 T1020,12 T1080,12 T1140,12 T1200,12" stroke="rgba(80,140,210,0.4)" strokeWidth="0.6" />
        <path d="M0,26 Q35,22 70,26 T140,26 T210,26 T280,26 T350,26 T420,26 T490,26 T560,26 T630,26 T700,26 T770,26 T840,26 T910,26 T980,26 T1050,26 T1120,26 T1200,26" stroke="rgba(60,120,190,0.3)" strokeWidth="0.5" />
        <path d="M0,40 Q40,36 80,40 T160,40 T240,40 T320,40 T400,40 T480,40 T560,40 T640,40 T720,40 T800,40 T880,40 T960,40 T1040,40 T1120,40 T1200,40" stroke="rgba(50,100,170,0.25)" strokeWidth="0.4" />
        <path d="M0,54 Q45,50 90,54 T180,54 T270,54 T360,54 T450,54 T540,54 T630,54 T720,54 T810,54 T900,54 T990,54 T1080,54 T1200,54" stroke="rgba(40,80,150,0.2)" strokeWidth="0.4" />
        <path d="M0,68 Q50,64 100,68 T200,68 T300,68 T400,68 T500,68 T600,68 T700,68 T800,68 T900,68 T1000,68 T1100,68 T1200,68" stroke="rgba(30,60,120,0.15)" strokeWidth="0.3" />
      </g>
    </svg>
  );
}

/** Cloud shape — rounded SVG blob */
function CloudSVG({ width, opacity }: { width: number; opacity: number }) {
  return (
    <svg
      viewBox="0 0 120 40"
      style={{ width, height: width * 0.33, opacity }}
      fill="rgba(160,180,210,0.6)"
    >
      <ellipse cx="40" cy="26" rx="30" ry="12" />
      <ellipse cx="65" cy="20" rx="22" ry="14" />
      <ellipse cx="85" cy="26" rx="18" ry="10" />
      <ellipse cx="28" cy="22" rx="16" ry="10" />
      <ellipse cx="55" cy="14" rx="18" ry="10" />
    </svg>
  );
}

/**
 * Rowing shell with rower — proper side-view sculling proportions.
 * The shell is long and narrow, rower is seated with proper posture.
 * Two oars (sculling) extend from oarlocks.
 */
function RowerSVG({ isRowing }: { isRowing: boolean }) {
  const oarLeftClass = isRowing ? "rowing-oar-left--active" : "rowing-oar-left--idle";
  const oarRightClass = isRowing ? "rowing-oar-right--active" : "rowing-oar-right--idle";
  const bodyClass = isRowing ? "rowing-body--active" : "rowing-body--idle";

  return (
    <svg
      viewBox="0 0 140 70"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      style={{ width: "100%", height: "100%", overflow: "visible" }}
    >
      <defs>
        <linearGradient id="hull-grad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#5a4030" />
          <stop offset="100%" stopColor="#3d2a1e" />
        </linearGradient>
        <linearGradient id="water-line" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="transparent" />
          <stop offset="20%" stopColor="rgba(80,140,210,0.2)" />
          <stop offset="80%" stopColor="rgba(80,140,210,0.2)" />
          <stop offset="100%" stopColor="transparent" />
        </linearGradient>
      </defs>

      {/* Water line reflection under hull */}
      <ellipse cx="70" cy="48" rx="52" ry="3" fill="rgba(40,90,160,0.15)" />

      {/* Left oar (extends left from oarlock) */}
      <g className={oarLeftClass}>
        <line
          x1="58" y1="40" x2="10" y2="52"
          stroke="#8a7560" strokeWidth="1.2" strokeLinecap="round"
        />
        {/* Blade */}
        <path d="M10,52 L4,56 L8,58 L14,54 Z" fill="#6a5545" />
      </g>

      {/* Right oar (extends right from oarlock) */}
      <g className={oarRightClass}>
        <line
          x1="82" y1="40" x2="130" y2="52"
          stroke="#8a7560" strokeWidth="1.2" strokeLinecap="round"
        />
        {/* Blade */}
        <path d="M130,52 L136,56 L132,58 L126,54 Z" fill="#6a5545" />
      </g>

      {/* Shell / hull */}
      <path
        d="M18,44 Q20,47 40,48 L100,48 Q120,47 122,44 L118,42 Q110,45 70,45 Q30,45 22,42 Z"
        fill="url(#hull-grad)"
        stroke="#4a3525"
        strokeWidth="0.5"
      />
      {/* Gunwale highlight */}
      <path
        d="M22,42 Q30,44.5 70,44.5 Q110,44.5 118,42"
        fill="none"
        stroke="#7a6050"
        strokeWidth="0.6"
      />

      {/* Rower body group — leans forward/back */}
      <g className={bodyClass}>
        {/* Seat (sliding) */}
        <rect x="65" y="40" width="10" height="2.5" rx="1" fill="#555" />

        {/* Legs (thigh → knee → shin, seated on slide) */}
        <path
          d="M68,41 L60,38 L54,42"
          stroke="#2a4060"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          fill="none"
        />

        {/* Torso */}
        <path
          d="M70,40 L68,28"
          stroke="#2855a0"
          strokeWidth="3.5"
          strokeLinecap="round"
        />

        {/* Shoulders */}
        <path
          d="M63,29 L73,29"
          stroke="#2855a0"
          strokeWidth="2.5"
          strokeLinecap="round"
        />

        {/* Arms — reaching to oarlocks */}
        <path
          d="M63,29 L58,35 L58,40"
          stroke="#d4a574"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
          fill="none"
        />
        <path
          d="M73,29 L78,35 L82,40"
          stroke="#d4a574"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
          fill="none"
        />

        {/* Head */}
        <circle cx="68" cy="23" r="4" fill="#d4a574" />

        {/* Cap/visor */}
        <path
          d="M64,22 Q68,18 72,22"
          fill="#1e3a6a"
          stroke="#162d55"
          strokeWidth="0.4"
        />
        <line x1="63" y1="22.5" x2="73" y2="22.5" stroke="#1e3a6a" strokeWidth="1.2" strokeLinecap="round" />
      </g>

      {/* Bow point */}
      <circle cx="122" cy="43" r="0.8" fill="#aa8866" />
    </svg>
  );
}

/* ═══════════════════════════════════════
   Parallax speeds per layer
   ═══════════════════════════════════════ */

const PARALLAX = {
  clouds: 0.04,
  mountains: 0.12,
  trees: 0.3,
  water: 0.6,
} as const;

/** Convert pace (s/500m) → pixels/second scroll speed */
function paceToSpeed(pace: number | null): number {
  if (pace == null || pace <= 0) return 0;
  return 3600 / pace;
}

/* ═══════════════════════════════════════
   Main component
   ═══════════════════════════════════════ */

export function RowingScene({ strokeRate, pace, isActive, isPaused }: RowingSceneProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const offsetRef = useRef(0);
  const currentSpeedRef = useRef(0);
  const rafRef = useRef<number>(0);
  const lastTimeRef = useRef<number>(0);

  const isRowing = isActive && !isPaused && (strokeRate ?? 0) > 0;
  const targetSpeed = isRowing ? paceToSpeed(pace) : 0;

  const animate = useCallback(
    (time: number) => {
      if (lastTimeRef.current === 0) {
        lastTimeRef.current = time;
        rafRef.current = requestAnimationFrame(animate);
        return;
      }

      const dt = Math.min((time - lastTimeRef.current) / 1000, 0.1);
      lastTimeRef.current = time;

      // Smooth speed lerp
      const diff = targetSpeed - currentSpeedRef.current;
      currentSpeedRef.current += diff * Math.min(dt * 2, 1);

      if (Math.abs(currentSpeedRef.current) > 0.05) {
        offsetRef.current += currentSpeedRef.current * dt;
      }

      // Apply parallax transforms
      const container = containerRef.current;
      if (container) {
        const offset = offsetRef.current;
        const layers = container.querySelectorAll<HTMLElement>("[data-parallax]");
        for (const layer of layers) {
          const factor = parseFloat(layer.dataset.parallax ?? "0");
          const scrollW = layer.scrollWidth;
          const halfW = scrollW > 0 ? scrollW / 2 : 1;
          const tx = -(offset * factor) % halfW;
          layer.style.transform = `translateX(${tx}px)`;
        }
      }

      rafRef.current = requestAnimationFrame(animate);
    },
    [targetSpeed],
  );

  useEffect(() => {
    rafRef.current = requestAnimationFrame(animate);
    return () => {
      cancelAnimationFrame(rafRef.current);
      lastTimeRef.current = 0;
    };
  }, [animate]);

  // Sync stroke animation duration to actual stroke rate
  const strokeDuration = (strokeRate ?? 0) > 0 ? 60 / strokeRate! : 2;
  const durationStyle = isRowing
    ? ({ "--stroke-dur": `${strokeDuration.toFixed(2)}s` } as React.CSSProperties)
    : undefined;

  // Apply duration to all animated elements via inline style
  const rowerStyle: React.CSSProperties = isRowing
    ? { animationDuration: `${strokeDuration.toFixed(2)}s` }
    : {};

  return (
    <div className="rowing-scene" ref={containerRef} style={durationStyle}>
      {/* Sky */}
      <div className="rowing-sky">
        {/* Stars */}
        {[
          { top: "8%", left: "5%", size: 1.5 },
          { top: "12%", left: "22%", size: 1 },
          { top: "5%", left: "38%", size: 1.5 },
          { top: "18%", left: "55%", size: 1 },
          { top: "6%", left: "70%", size: 2 },
          { top: "14%", left: "85%", size: 1 },
          { top: "20%", left: "92%", size: 1.5 },
          { top: "10%", left: "48%", size: 1 },
          { top: "3%", left: "62%", size: 1 },
          { top: "22%", left: "15%", size: 1 },
        ].map((s, i) => (
          <div
            key={i}
            className="rowing-star"
            style={{ top: s.top, left: s.left, width: s.size, height: s.size }}
          />
        ))}

        {/* Moon */}
        <div
          className="rowing-moon"
          style={{ top: "8%", right: "18%", width: 22, height: 22 }}
        />
      </div>

      {/* Clouds */}
      <div className="rowing-clouds" data-parallax={PARALLAX.clouds}>
        <div className="rowing-cloud-shape" style={{ top: "10%", left: "8%" }}>
          <CloudSVG width={80} opacity={0.12} />
        </div>
        <div className="rowing-cloud-shape" style={{ top: "20%", left: "35%" }}>
          <CloudSVG width={110} opacity={0.08} />
        </div>
        <div className="rowing-cloud-shape" style={{ top: "5%", left: "65%" }}>
          <CloudSVG width={70} opacity={0.10} />
        </div>
        <div className="rowing-cloud-shape" style={{ top: "15%", left: "85%" }}>
          <CloudSVG width={90} opacity={0.07} />
        </div>
      </div>

      {/* Mountains */}
      <div className="rowing-mountains" data-parallax={PARALLAX.mountains}>
        <MountainsSVG />
      </div>

      {/* Treeline */}
      <div className="rowing-trees" data-parallax={PARALLAX.trees}>
        <TreelineSVG />
      </div>

      {/* Horizon glow */}
      <div className="rowing-horizon-glow" />

      {/* Water */}
      <div className="rowing-water">
        <div className="rowing-water-ripples" data-parallax={PARALLAX.water}>
          <WaterRipplesSVG />
        </div>

        {/* Moon reflection column */}
        <div
          className="rowing-moon-reflection"
          style={{ top: 0, right: "16%", width: 12, height: "80%" }}
        />
      </div>

      {/* Shimmer */}
      <div className="rowing-shimmer" />

      {/* Wake */}
      <div
        className="rowing-wake"
        style={{ left: "calc(50% - 48px)", opacity: isRowing ? 1 : 0 }}
      >
        <div className="rowing-wake-line" style={{ width: 20, bottom: 3 }} />
        <div className="rowing-wake-line" style={{ width: 15, bottom: 0, left: -6 }} />
        <div className="rowing-wake-line" style={{ width: 12, bottom: -3, left: -10 }} />
      </div>

      {/* Rower */}
      <div
        className={`rowing-rower ${isRowing ? "rowing-rower--active" : "rowing-rower--idle"}`}
        style={rowerStyle}
      >
        <RowerSVG isRowing={isRowing} />
      </div>
    </div>
  );
}

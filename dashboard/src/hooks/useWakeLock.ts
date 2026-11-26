/**
 * Keep the screen awake while a workout is in progress (ACTIVE or PAUSED).
 *
 * The Screen Wake Lock API only exists in secure contexts (HTTPS or
 * localhost). The Pi serves the dashboard over plain HTTP, so on a phone
 * `navigator.wakeLock` is undefined. In that case we fall back to looping a
 * tiny silent video: iOS and Android keep the display on while media plays.
 *
 * iOS only lets a media element play after a user gesture, and a workout often
 * starts on its own (from the S4). So the video is "primed" on the first tap
 * anywhere on the page: played and paused once inside the gesture, which
 * unlocks later programmatic play() calls on that same element.
 */

import { useEffect, useRef } from "react";
import type { WorkoutState } from "@/types";

const VIDEO_SRC = "/assets/keep-awake.mp4";

function hasNativeWakeLock(): boolean {
  return window.isSecureContext && "wakeLock" in navigator;
}

function createKeepAwakeVideo(): HTMLVideoElement {
  const video = document.createElement("video");
  video.src = VIDEO_SRC;
  video.loop = true;
  video.muted = true;
  video.playsInline = true;
  video.setAttribute("playsinline", "");
  video.setAttribute("muted", "");
  video.setAttribute("aria-hidden", "true");
  video.style.cssText =
    "position:fixed;width:1px;height:1px;opacity:0;pointer-events:none;left:0;top:0;";
  document.body.appendChild(video);
  return video;
}

export function useWakeLock(workoutState: WorkoutState): void {
  const shouldHold = workoutState === "ACTIVE" || workoutState === "PAUSED";
  const shouldHoldRef = useRef(shouldHold);
  const sentinelRef = useRef<WakeLockSentinel | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);

  // Fallback path: create the video once and prime it on the first gesture.
  useEffect(() => {
    if (hasNativeWakeLock()) return;
    const video = createKeepAwakeVideo();
    videoRef.current = video;

    const prime = () => {
      video
        .play()
        .then(() => {
          if (!shouldHoldRef.current) video.pause();
        })
        .catch(() => {
          // Not allowed yet; try again on the next gesture.
          return;
        })
        .finally(() => {
          if (!video.paused || video.played.length > 0) {
            document.removeEventListener("pointerdown", prime, true);
            document.removeEventListener("touchend", prime, true);
          }
        });
    };
    document.addEventListener("pointerdown", prime, true);
    document.addEventListener("touchend", prime, true);

    return () => {
      document.removeEventListener("pointerdown", prime, true);
      document.removeEventListener("touchend", prime, true);
      video.pause();
      video.remove();
      videoRef.current = null;
    };
  }, []);

  useEffect(() => {
    shouldHoldRef.current = shouldHold;

    const acquire = async () => {
      if (hasNativeWakeLock()) {
        if (sentinelRef.current && !sentinelRef.current.released) return;
        try {
          sentinelRef.current = await navigator.wakeLock.request("screen");
        } catch {
          // Refused (low power mode, hidden tab); retried on visibilitychange.
        }
      } else {
        videoRef.current?.play().catch(() => {
          // Not primed by a gesture yet; the prime handler starts it.
        });
      }
    };

    const release = () => {
      const sentinel = sentinelRef.current;
      sentinelRef.current = null;
      sentinel?.release().catch(() => {});
      videoRef.current?.pause();
    };

    // The OS drops both the lock and media playback when the page is hidden.
    const handleVisibility = () => {
      if (document.visibilityState === "visible" && shouldHoldRef.current) acquire();
    };

    if (shouldHold) acquire();
    else release();

    document.addEventListener("visibilitychange", handleVisibility);
    return () => {
      document.removeEventListener("visibilitychange", handleVisibility);
      release();
    };
  }, [shouldHold]);
}

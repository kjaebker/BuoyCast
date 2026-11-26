/** Which live visual is shown above the metric tiles, remembered per device. */

import { useState } from "react";
import { GraphMetric } from "@/components/LiveGraph";

export const LiveView = { SCENE: "scene", ...GraphMetric } as const;
export type LiveView = (typeof LiveView)[keyof typeof LiveView];

const STORAGE_KEY = "buoycast.liveView";
const VIEWS: readonly string[] = Object.values(LiveView);

function isLiveView(value: unknown): value is LiveView {
  return typeof value === "string" && VIEWS.includes(value);
}

export function useLiveView(): [LiveView, (view: LiveView) => void] {
  const [view, setView] = useState<LiveView>(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      return isLiveView(stored) ? stored : LiveView.SCENE;
    } catch {
      return LiveView.SCENE;
    }
  });
  const choose = (next: LiveView) => {
    setView(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // Private mode or storage full: the choice just won't persist.
    }
  };
  return [view, choose];
}


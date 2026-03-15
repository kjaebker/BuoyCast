/**
 * SettingsScreen - device control, Strava, and system management.
 * Follows BuoyCast design language: dark mode, athletic, high-contrast.
 */

import { useState, useEffect } from "react";
import { ArrowLeft, Wifi, WifiOff, Heart, HeartOff, UploadCloud, Upload, RefreshCw, RotateCcw, Download, CheckCircle2, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import type { SystemStatus, StravaStatus, AppSettings, UpdateInfo } from "@/types";

type SettingsScreenProps = {
  onBack: () => void;
};

type SettingCardProps = {
  icon: React.ReactNode;
  iconTone: "teal" | "rose" | "primary" | "muted";
  title: string;
  subtitle: string;
  action?: React.ReactNode;
  onClick?: () => void;
};

const iconBgClasses = {
  teal: "bg-[color-mix(in_oklch,var(--color-secondary)_22%,transparent)] text-secondary-foreground",
  rose: "bg-[color-mix(in_oklch,var(--color-destructive)_18%,transparent)] text-[color-mix(in_oklch,var(--color-destructive)_80%,white)]",
  primary: "bg-[color-mix(in_oklch,var(--color-primary)_18%,transparent)] text-primary",
  muted: "bg-muted/60 text-muted-foreground",
};

function SettingCard({ icon, iconTone, title, subtitle, action, onClick }: SettingCardProps) {
  return (
    <div
      className={cn(
        "flex items-center gap-4 rounded-2xl border border-border/80 bg-card/75 px-4 py-4 shadow-[0_12px_32px_-20px_rgba(0,0,0,0.8)] backdrop-blur-sm",
        onClick && "cursor-pointer hover:bg-card/90 transition-colors",
      )}
      onClick={onClick}
    >
      <div className={cn("flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl", iconBgClasses[iconTone])}>
        {icon}
      </div>
      <div className="flex-1 min-w-0">
        <div className="font-semibold text-foreground">{title}</div>
        <div className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">{subtitle}</div>
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}

export function SettingsScreen({ onBack }: SettingsScreenProps) {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [strava, setStrava] = useState<StravaStatus | null>(null);
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [logs, setLogs] = useState("");
  const [logsLoading, setLogsLoading] = useState(false);
  const [updateInfo, setUpdateInfo] = useState<UpdateInfo | null>(null);
  const [updateChecking, setUpdateChecking] = useState(false);
  const [updateInstalling, setUpdateInstalling] = useState(false);

  useEffect(() => {
    fetch("/api/status").then(r => r.json()).then(setStatus);
    fetch("/api/strava/status").then(r => r.json()).then(setStrava);
    fetch("/api/settings").then(r => r.json()).then(setSettings);
  }, []);

  const handleS4Reset = async () => {
    if (!confirm("Reset S4 monitor? This clears all rowing data from memory.")) return;
    await fetch("/api/s4/reset", { method: "POST" });
    alert("S4 reset command sent");
  };

  const handleHrToggle = async () => {
    const endpoint = status?.tickr_connected ? "/api/hr/disconnect" : "/api/hr/connect";
    await fetch(endpoint, { method: "POST" });
    const newStatus = await fetch("/api/status").then(r => r.json());
    setStatus(newStatus);
  };

  const handleRestart = async () => {
    if (!confirm("Restart Raspberry Pi? Connection will be lost for ~30 seconds.")) return;
    await fetch("/api/system/restart", { method: "POST" });
    alert("Restarting in 3 seconds...");
  };

  const handleServiceRestart = async () => {
    if (!confirm("Restart BuoyCast service? Dashboard will reconnect automatically.")) return;
    await fetch("/api/system/restart-service", { method: "POST" });
    alert("Restarting service in 2 seconds...");
  };

  const handleHrDefaultToggle = async () => {
    const newValue = !settings?.include_hr_in_strava_upload;
    await fetch("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ include_hr_in_strava_upload: newValue }),
    });
    const updated = await fetch("/api/settings").then(r => r.json());
    setSettings(updated);
  };

  const fetchLogs = async () => {
    setLogsLoading(true);
    const data = await fetch("/api/logs?lines=200").then(r => r.json());
    setLogs(data.logs);
    setLogsLoading(false);
  };

  const handleCheckUpdate = async () => {
    setUpdateChecking(true);
    try {
      const data = await fetch("/api/system/update/check").then(r => r.json());
      setUpdateInfo(data);
    } catch {
      setUpdateInfo({
        current_version: "unknown",
        latest_version: null,
        update_available: false,
        release_notes: null,
        error: "Failed to reach update server",
      });
    } finally {
      setUpdateChecking(false);
    }
  };

  const handleInstallUpdate = async () => {
    if (!confirm("Install update? The service will restart and the dashboard will briefly disconnect.")) return;
    setUpdateInstalling(true);
    try {
      await fetch("/api/system/update", { method: "POST" });
    } catch {
      alert("Failed to start update");
      setUpdateInstalling(false);
    }
  };

  const handleStravaAuth = async () => {
    const { auth_url } = await fetch("/api/strava/auth").then(r => r.json());
    window.location.href = auth_url;
  };

  return (
    <div className="relative isolate flex min-h-dvh flex-col overflow-hidden bg-background text-foreground">
      {/* Background gradients matching App.tsx */}
      <div className="pointer-events-none absolute inset-x-0 top-0 h-72 bg-[radial-gradient(ellipse_at_top,color-mix(in_oklch,var(--color-primary)_22%,transparent)_0%,color-mix(in_oklch,var(--color-primary)_12%,transparent)_28%,transparent_74%)] opacity-80 blur-[2px]" />

      {/* Header */}
      <div className="relative z-10 border-b border-border/70 bg-[color-mix(in_oklch,var(--color-card)_82%,transparent)] px-4 py-4 backdrop-blur-xl">
        <div className="flex items-center gap-3">
          <button
            onClick={onBack}
            className="flex h-10 w-10 items-center justify-center rounded-full border border-border/80 bg-card/70 text-foreground hover:bg-accent hover:text-accent-foreground transition-colors"
            aria-label="Back"
          >
            <ArrowLeft className="h-4 w-4" />
          </button>
          <h1 className="text-xl font-bold tracking-tight">Settings</h1>
        </div>
      </div>

      <div className="relative z-10 flex-1 overflow-auto px-4 pb-8 pt-6">
        <div className="mx-auto max-w-2xl space-y-7">
          {/* S4 Monitor */}
          <section>
            <h2 className="mb-3 text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
              S4 Monitor
            </h2>
            <div className="space-y-3">
              <SettingCard
                icon={status?.s4_connected ? <Wifi className="h-5 w-5" /> : <WifiOff className="h-5 w-5" />}
                iconTone={status?.s4_connected ? "teal" : "muted"}
                title={status?.s4_connected ? "S4 Connected" : "S4 Disconnected"}
                subtitle={status?.s4_paused ? "Polling paused" : "Polling active"}
                action={
                  <button
                    onClick={handleS4Reset}
                    className="rounded-full border border-border/80 bg-card/70 px-4 py-2 text-sm font-medium text-foreground hover:bg-accent transition-colors"
                  >
                    <RotateCcw className="mr-1.5 inline h-3.5 w-3.5" />
                    Reset
                  </button>
                }
              />
            </div>
          </section>

          {/* Heart Rate */}
          <section>
            <h2 className="mb-3 text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
              Heart Rate
            </h2>
            <div className="space-y-3">
              <SettingCard
                icon={status?.tickr_connected ? <Heart className="h-5 w-5 fill-current" /> : <HeartOff className="h-5 w-5" />}
                iconTone={status?.tickr_connected ? "rose" : "muted"}
                title={status?.tickr_connected ? "TICKR Connected" : "TICKR Disconnected"}
                subtitle="Wahoo TICKR monitor"
                action={
                  <button
                    onClick={handleHrToggle}
                    className="rounded-full border border-border/80 bg-card/70 px-4 py-2 text-sm font-medium text-foreground hover:bg-accent transition-colors"
                  >
                    {status?.tickr_connected ? "Disconnect" : "Connect"}
                  </button>
                }
              />

              <label className="flex cursor-pointer items-center gap-4 rounded-2xl border border-border/80 bg-card/75 px-4 py-4 shadow-[0_12px_32px_-20px_rgba(0,0,0,0.8)] backdrop-blur-sm hover:bg-card/90 transition-colors">
                <div className="flex-1">
                  <div className="font-semibold text-foreground">Include HR in Strava</div>
                  <div className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">
                    Default (override per upload)
                  </div>
                </div>
                <input
                  type="checkbox"
                  checked={settings?.include_hr_in_strava_upload ?? true}
                  onChange={handleHrDefaultToggle}
                  className="h-6 w-6 rounded-md border-border accent-primary"
                />
              </label>
            </div>
          </section>

          {/* Strava */}
          <section>
            <h2 className="mb-3 text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
              Strava Integration
            </h2>
            <div className="rounded-2xl border border-border/80 bg-card/75 px-4 py-4 shadow-[0_12px_32px_-20px_rgba(0,0,0,0.8)] backdrop-blur-sm">
              {strava?.connected ? (
                <div className="space-y-4">
                  <div className="flex items-center gap-4">
                    <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-[color-mix(in_oklch,var(--color-primary)_18%,transparent)] text-primary">
                      <UploadCloud className="h-5 w-5" />
                    </div>
                    <div className="flex-1">
                      <div className="font-semibold text-foreground">{strava.athlete_name ?? "Connected"}</div>
                      <div className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">
                        Athlete ID: {strava.athlete_id}
                      </div>
                    </div>
                  </div>
                  <button
                    onClick={handleStravaAuth}
                    className="w-full rounded-full border border-border/80 bg-card/70 py-2.5 text-sm font-medium text-foreground hover:bg-accent transition-colors"
                  >
                    Reconnect Account
                  </button>
                </div>
              ) : (
                <div className="space-y-4">
                  <div className="flex items-center gap-4">
                    <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-muted/60 text-muted-foreground">
                      <Upload className="h-5 w-5" />
                    </div>
                    <div className="flex-1">
                      <div className="font-semibold text-foreground">Not Connected</div>
                      <div className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">
                        Connect to upload workouts
                      </div>
                    </div>
                  </div>
                  <button
                    onClick={handleStravaAuth}
                    className="w-full rounded-full bg-primary py-2.5 text-sm font-semibold text-primary-foreground hover:bg-primary/90 transition-colors"
                  >
                    Connect Strava
                  </button>
                </div>
              )}
            </div>
          </section>

          {/* System */}
          <section>
            <h2 className="mb-3 text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
              System
            </h2>
            <div className="space-y-3">
              <div className="rounded-2xl border border-border/80 bg-card/75 px-4 py-4 shadow-[0_12px_32px_-20px_rgba(0,0,0,0.8)] backdrop-blur-sm">
                <div className="mb-3 flex items-center justify-between">
                  <div>
                    <div className="font-semibold text-foreground">Restart Service</div>
                    <div className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">
                      BuoyCast service only
                    </div>
                  </div>
                </div>
                <button
                  onClick={handleServiceRestart}
                  className="w-full rounded-full border border-primary/50 bg-primary/10 py-2.5 text-sm font-semibold text-primary hover:bg-primary/20 transition-colors"
                >
                  <RefreshCw className="mr-2 inline h-3.5 w-3.5" />
                  Restart Service
                </button>
              </div>

              <div className="rounded-2xl border border-border/80 bg-card/75 px-4 py-4 shadow-[0_12px_32px_-20px_rgba(0,0,0,0.8)] backdrop-blur-sm">
                <div className="mb-3 flex items-center justify-between">
                  <div>
                    <div className="font-semibold text-foreground">Restart Device</div>
                    <div className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">
                      Raspberry Pi reboot
                    </div>
                  </div>
                </div>
                <button
                  onClick={handleRestart}
                  className="w-full rounded-full border border-destructive/50 bg-destructive/10 py-2.5 text-sm font-semibold text-destructive hover:bg-destructive/20 transition-colors"
                >
                  <RefreshCw className="mr-2 inline h-3.5 w-3.5" />
                  Restart Pi
                </button>
              </div>
            </div>
          </section>

          {/* Software Update */}
          <section>
            <h2 className="mb-3 text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
              Software Update
            </h2>
            <div className="rounded-2xl border border-border/80 bg-card/75 px-4 py-4 shadow-[0_12px_32px_-20px_rgba(0,0,0,0.8)] backdrop-blur-sm">
              <div className="space-y-4">
                {/* Version info */}
                <div className="flex items-center gap-4">
                  <div className={cn(
                    "flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl",
                    updateInfo?.update_available
                      ? "bg-[color-mix(in_oklch,var(--color-primary)_18%,transparent)] text-primary"
                      : "bg-muted/60 text-muted-foreground",
                  )}>
                    {updateInfo?.update_available ? (
                      <Download className="h-5 w-5" />
                    ) : updateInfo && !updateInfo.error && !updateInfo.update_available ? (
                      <CheckCircle2 className="h-5 w-5" />
                    ) : updateInfo?.error ? (
                      <AlertCircle className="h-5 w-5" />
                    ) : (
                      <Download className="h-5 w-5" />
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="font-semibold text-foreground">
                      {updateInfo?.update_available
                        ? `${updateInfo.commits_behind} update${updateInfo.commits_behind !== 1 ? "s" : ""} available`
                        : updateInfo && !updateInfo.error
                          ? "Up to date"
                          : updateInfo?.error
                            ? "Check failed"
                            : "BuoyCast"}
                    </div>
                    <div className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">
                      {updateInfo?.current_sha
                        ? `Running: ${updateInfo.current_sha}`
                        : "Check for available updates"}
                    </div>
                  </div>
                </div>

                {/* Latest commit message (if update available) */}
                {updateInfo?.update_available && updateInfo.latest_commit_message && (
                  <div className="rounded-xl border border-border/60 bg-black/30 px-3 py-2">
                    <p className="text-sm text-foreground/80">
                      Latest: {updateInfo.latest_commit_message}
                    </p>
                  </div>
                )}

                {/* Error message */}
                {updateInfo?.error && (
                  <p className="text-sm text-destructive">{updateInfo.error}</p>
                )}

                {/* Action buttons */}
                <div className="flex gap-3">
                  {updateInfo?.update_available && !updateInstalling ? (
                    <button
                      onClick={handleInstallUpdate}
                      className="flex-1 rounded-full bg-primary py-2.5 text-sm font-semibold text-primary-foreground hover:bg-primary/90 transition-colors"
                    >
                      <Download className="mr-2 inline h-3.5 w-3.5" />
                      Install Update
                    </button>
                  ) : updateInstalling ? (
                    <div className="flex-1 rounded-full border border-primary/50 bg-primary/10 py-2.5 text-center text-sm font-semibold text-primary">
                      <RefreshCw className="mr-2 inline h-3.5 w-3.5 animate-spin" />
                      Updating — service will restart...
                    </div>
                  ) : null}
                  {!updateInstalling && (
                    <button
                      onClick={handleCheckUpdate}
                      disabled={updateChecking}
                      className={cn(
                        "rounded-full border border-border/80 bg-card/70 px-4 py-2.5 text-sm font-medium text-foreground hover:bg-accent transition-colors disabled:opacity-50",
                        !updateInfo?.update_available && "flex-1",
                      )}
                    >
                      {updateChecking ? (
                        <>
                          <RefreshCw className="mr-2 inline h-3.5 w-3.5 animate-spin" />
                          Checking...
                        </>
                      ) : (
                        <>
                          <RefreshCw className="mr-2 inline h-3.5 w-3.5" />
                          Check for Updates
                        </>
                      )}
                    </button>
                  )}
                </div>
              </div>
            </div>
          </section>

          {/* Logs */}
          <section>
            <h2 className="mb-3 text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
              System Logs
            </h2>
            <div className="rounded-2xl border border-border/80 bg-card/75 p-4 shadow-[0_12px_32px_-20px_rgba(0,0,0,0.8)] backdrop-blur-sm">
              <div className="mb-3 flex items-center justify-between">
                <h3 className="text-sm font-semibold text-foreground">Recent Activity</h3>
                <button
                  onClick={fetchLogs}
                  disabled={logsLoading}
                  className="rounded-full border border-border/80 bg-card/70 px-4 py-2 text-sm font-medium text-foreground hover:bg-accent transition-colors disabled:opacity-50"
                >
                  {logsLoading ? "Loading..." : "Refresh"}
                </button>
              </div>
              <pre className="h-64 overflow-auto rounded-xl border border-border/60 bg-black/30 p-3 font-mono text-[0.7rem] leading-relaxed text-foreground/90 backdrop-blur-sm">
                {logs || "Click Refresh to load system logs"}
              </pre>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

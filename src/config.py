"""Application configuration via pydantic-settings, loaded from config.toml."""

from pathlib import Path
from typing import Any, ClassVar

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict, TomlConfigSettingsSource


class ServerSettings(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8080
    mdns_name: str = "waterrower"


class S4Settings(BaseModel):
    port: str = "/dev/ttyACM0"
    baud_rate: int = 19200
    poll_interval_hz: float = 4.0
    reconnect_delay_s: int = 5


class HeartRateSettings(BaseModel):
    enabled: bool = True
    device_mac: str = ""
    device_name: str = ""
    required: bool = False
    # Set to True for Wahoo TICKR (original) units that report BPM at 2x the
    # actual rate due to a firmware bug that counts both the P-wave and R-wave.
    # When True, the BPM field is halved; this is used as a fallback when RR
    # interval data is unavailable or all intervals are flagged as outliers.
    bpm_field_doubled: bool = False
    debug_capture: bool = False
    debug_capture_dir: str = "data/hr_debug"


class WorkoutSettings(BaseModel):
    auto_pause_idle_s: int = 30
    auto_end_idle_s: int = 300
    min_workout_distance_m: float = 100.0


class StravaSettings(BaseModel):
    client_id: str = ""
    client_secret: str = ""


class StorageSettings(BaseModel):
    db_path: str = "data/buoycast.db"
    fit_dir: str = "data/fit"


class UpdateSettings(BaseModel):
    # GitHub "owner/name" whose Releases the Pi installs from. Change this if
    # you run a fork.
    repo: str = "kjaebker/BuoyCast"


class LoggingSettings(BaseModel):
    level: str = "INFO"
    log_dir: str = "logs"
    json_logs: bool = False


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        toml_file="config.toml",
    )

    # Class-level override for toml path (used by load_settings)
    _toml_path: ClassVar[str | None] = None

    server: ServerSettings = ServerSettings()
    s4: S4Settings = S4Settings()
    heart_rate: HeartRateSettings = HeartRateSettings()
    workout: WorkoutSettings = WorkoutSettings()
    strava: StravaSettings = StravaSettings()
    storage: StorageSettings = StorageSettings()
    logging: LoggingSettings = LoggingSettings()
    updates: UpdateSettings = UpdateSettings()

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        **kwargs: Any,
    ) -> tuple[Any, ...]:
        toml_file = cls._toml_path or "config.toml"
        return (
            TomlConfigSettingsSource(settings_cls, toml_file=Path(toml_file)),
        )


def load_settings(toml_path: str | Path | None = None) -> Settings:
    """Load settings, optionally from a specific TOML file path."""
    Settings._toml_path = str(toml_path) if toml_path else None
    try:
        return Settings()
    finally:
        Settings._toml_path = None

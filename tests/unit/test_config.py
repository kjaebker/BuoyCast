"""Tests for configuration loading."""

import tempfile
from pathlib import Path

from src.config import (
    HeartRateSettings,
    S4Settings,
    ServerSettings,
    Settings,
    StorageSettings,
    StravaSettings,
    WorkoutSettings,
    load_settings,
)


class TestSubSettings:
    def test_server_defaults(self):
        s = ServerSettings()
        assert s.host == "0.0.0.0"
        assert s.port == 8080
        assert s.mdns_name == "waterrower"

    def test_s4_defaults(self):
        s = S4Settings()
        assert s.baud_rate == 19200
        assert s.poll_interval_hz == 1.0
        assert s.reconnect_delay_s == 5

    def test_heart_rate_defaults(self):
        s = HeartRateSettings()
        assert s.enabled is True
        assert s.device_mac == ""
        assert s.required is False

    def test_workout_defaults(self):
        s = WorkoutSettings()
        assert s.auto_pause_idle_s == 30
        assert s.auto_end_idle_s == 300
        assert s.min_workout_distance_m == 100.0

    def test_strava_defaults(self):
        s = StravaSettings()
        assert s.client_id == ""
        assert s.client_secret == ""

    def test_storage_defaults(self):
        s = StorageSettings()
        assert s.db_path == "data/buoycast.db"
        assert s.fit_dir == "data/fit"


class TestSettings:
    def test_defaults_without_toml(self):
        s = Settings()
        assert s.server.port == 8080
        assert s.s4.baud_rate == 19200
        assert s.workout.auto_pause_idle_s == 30

    def test_all_sections_present(self):
        s = Settings()
        assert isinstance(s.server, ServerSettings)
        assert isinstance(s.s4, S4Settings)
        assert isinstance(s.heart_rate, HeartRateSettings)
        assert isinstance(s.workout, WorkoutSettings)
        assert isinstance(s.strava, StravaSettings)
        assert isinstance(s.storage, StorageSettings)


class TestLoadSettings:
    def _write_toml(self, content: str) -> Path:
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".toml", delete=False
        )
        f.write(content)
        f.close()
        return Path(f.name)

    def test_load_from_toml(self, tmp_path):
        toml = tmp_path / "test.toml"
        toml.write_text(
            '[server]\nport = 9090\n\n[s4]\nbaud_rate = 9600\n'
        )
        s = load_settings(toml)
        assert s.server.port == 9090
        assert s.s4.baud_rate == 9600

    def test_toml_overrides_preserve_other_defaults(self, tmp_path):
        toml = tmp_path / "test.toml"
        toml.write_text('[server]\nport = 3000\n')
        s = load_settings(toml)
        assert s.server.port == 3000
        # Other sections should keep defaults
        assert s.s4.baud_rate == 19200
        assert s.workout.auto_pause_idle_s == 30
        assert s.heart_rate.enabled is True

    def test_heart_rate_config(self, tmp_path):
        toml = tmp_path / "test.toml"
        toml.write_text(
            '[heart_rate]\ndevice_mac = "AA:BB:CC:DD:EE:FF"\n'
            'device_name = "TICKR 1234"\nrequired = true\n'
        )
        s = load_settings(toml)
        assert s.heart_rate.device_mac == "AA:BB:CC:DD:EE:FF"
        assert s.heart_rate.device_name == "TICKR 1234"
        assert s.heart_rate.required is True

    def test_strava_config(self, tmp_path):
        toml = tmp_path / "test.toml"
        toml.write_text(
            '[strava]\nclient_id = "12345"\nclient_secret = "secret"\n'
        )
        s = load_settings(toml)
        assert s.strava.client_id == "12345"
        assert s.strava.client_secret == "secret"

    def test_storage_config(self, tmp_path):
        toml = tmp_path / "test.toml"
        toml.write_text(
            '[storage]\ndb_path = "/tmp/test.db"\nfit_dir = "/tmp/fit"\n'
        )
        s = load_settings(toml)
        assert s.storage.db_path == "/tmp/test.db"
        assert s.storage.fit_dir == "/tmp/fit"

    def test_load_none_uses_defaults(self):
        s = load_settings(None)
        assert s.server.port == 8080

    def test_empty_toml(self, tmp_path):
        toml = tmp_path / "empty.toml"
        toml.write_text("")
        s = load_settings(toml)
        assert s.server.port == 8080
        assert s.s4.baud_rate == 19200

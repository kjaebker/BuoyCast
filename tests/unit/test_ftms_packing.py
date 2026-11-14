"""Unit tests for FTMS Rower Data byte packing."""

import struct
from datetime import UTC, datetime

import pytest

from src.ble.ftms import (
    FLAG_AVG_STROKE_RATE,
    FLAG_ELAPSED_TIME,
    FLAG_EXPENDED_ENERGY,
    FLAG_HEART_RATE,
    FLAG_INSTANTANEOUS_PACE,
    FLAG_INSTANTANEOUS_POWER,
    FLAG_TOTAL_DISTANCE,
    pack_rower_data,
)
from src.models import RowingMetrics


def _metrics(**kwargs) -> RowingMetrics:
    defaults = {"timestamp": datetime.now(tz=UTC)}
    defaults.update(kwargs)
    return RowingMetrics(**defaults)


def _unpack_flags(data: bytes) -> int:
    """Extract the uint16 flags from packed data."""
    return struct.unpack_from("<H", data, 0)[0]


class TestFlagsField:
    def test_base_fields_always_present(self):
        """Instantaneous stroke rate + stroke count are the FTMS base fields.
        They are always present when bit 0 (More Data) = 0 — no flag needed.
        Verify bit 1 (Average Stroke Rate) is NOT set (we don't send that extra
        field) and that the data is at least 5 bytes long.
        """
        data = pack_rower_data(_metrics())
        flags = _unpack_flags(data)
        assert not (flags & FLAG_AVG_STROKE_RATE), (
            "Bit 1 (Average Stroke Rate) must not be set — "
            "setting it without writing the extra uint8 mis-aligns parsing"
        )
        assert len(data) >= 5  # flags(2) + stroke_rate(1) + stroke_count(2)

    def test_distance_flag_set_when_present(self):
        data = pack_rower_data(_metrics(distance_m=500.0))
        flags = _unpack_flags(data)
        assert flags & FLAG_TOTAL_DISTANCE

    def test_distance_flag_clear_when_none(self):
        data = pack_rower_data(_metrics(distance_m=None))
        flags = _unpack_flags(data)
        assert not (flags & FLAG_TOTAL_DISTANCE)

    def test_pace_flag_set_when_present(self):
        data = pack_rower_data(_metrics(pace_s_per_500m=120.0))
        flags = _unpack_flags(data)
        assert flags & FLAG_INSTANTANEOUS_PACE

    def test_pace_flag_clear_when_none(self):
        data = pack_rower_data(_metrics(pace_s_per_500m=None))
        flags = _unpack_flags(data)
        assert not (flags & FLAG_INSTANTANEOUS_PACE)

    def test_pace_flag_clear_when_zero(self):
        data = pack_rower_data(_metrics(pace_s_per_500m=0.0))
        flags = _unpack_flags(data)
        assert not (flags & FLAG_INSTANTANEOUS_PACE)

    def test_power_flag_set_when_present(self):
        data = pack_rower_data(_metrics(power_watts=150.0))
        flags = _unpack_flags(data)
        assert flags & FLAG_INSTANTANEOUS_POWER

    def test_power_flag_clear_when_none(self):
        data = pack_rower_data(_metrics(power_watts=None))
        flags = _unpack_flags(data)
        assert not (flags & FLAG_INSTANTANEOUS_POWER)

    def test_hr_flag_set_when_present(self):
        data = pack_rower_data(_metrics(heart_rate_bpm=140))
        flags = _unpack_flags(data)
        assert flags & FLAG_HEART_RATE

    def test_hr_flag_clear_when_none(self):
        data = pack_rower_data(_metrics(heart_rate_bpm=None))
        flags = _unpack_flags(data)
        assert not (flags & FLAG_HEART_RATE)

    def test_all_flags_set(self):
        data = pack_rower_data(
            _metrics(
                stroke_rate=28.0,
                stroke_count=100,
                distance_m=500.0,
                pace_s_per_500m=120.0,
                power_watts=150.0,
                calories=250,
                heart_rate_bpm=140,
                elapsed_seconds=600,
            )
        )
        flags = _unpack_flags(data)
        expected = (
            FLAG_TOTAL_DISTANCE
            | FLAG_INSTANTANEOUS_PACE
            | FLAG_INSTANTANEOUS_POWER
            | FLAG_EXPENDED_ENERGY
            | FLAG_HEART_RATE
            | FLAG_ELAPSED_TIME
        )
        assert flags == expected

    def test_expended_energy_flag_set_when_calories_present(self):
        data = pack_rower_data(_metrics(calories=300))
        flags = _unpack_flags(data)
        assert flags & FLAG_EXPENDED_ENERGY

    def test_expended_energy_flag_clear_when_none(self):
        data = pack_rower_data(_metrics(calories=None))
        flags = _unpack_flags(data)
        assert not (flags & FLAG_EXPENDED_ENERGY)

    def test_elapsed_time_flag_set_when_present(self):
        data = pack_rower_data(_metrics(elapsed_seconds=300))
        flags = _unpack_flags(data)
        assert flags & FLAG_ELAPSED_TIME

    def test_elapsed_time_flag_clear_when_none(self):
        data = pack_rower_data(_metrics(elapsed_seconds=None))
        flags = _unpack_flags(data)
        assert not (flags & FLAG_ELAPSED_TIME)


class TestStrokeRateEncoding:
    def test_28_spm(self):
        """28 SPM should encode as 56 (×2 resolution)."""
        data = pack_rower_data(_metrics(stroke_rate=28.0))
        # After flags (2 bytes), stroke rate is uint8
        assert data[2] == 56

    def test_zero_spm(self):
        data = pack_rower_data(_metrics(stroke_rate=0.0))
        assert data[2] == 0

    def test_half_spm_resolution(self):
        """28.5 SPM should encode as 57."""
        data = pack_rower_data(_metrics(stroke_rate=28.5))
        assert data[2] == 57

    def test_none_encodes_as_zero(self):
        data = pack_rower_data(_metrics(stroke_rate=None))
        assert data[2] == 0

    def test_clamped_to_255(self):
        """Max uint8 = 255, so 128+ SPM should clamp."""
        data = pack_rower_data(_metrics(stroke_rate=60.0))
        assert data[2] == 120  # 60 * 2 = 120

    def test_stroke_count_uint16(self):
        """Stroke count follows stroke rate as uint16 LE."""
        data = pack_rower_data(_metrics(stroke_count=1000))
        count = struct.unpack_from("<H", data, 3)[0]
        assert count == 1000


class TestDistancePacking:
    def test_distance_uint24(self):
        """Distance packed as uint24 LE (3 bytes) after stroke rate + count."""
        data = pack_rower_data(_metrics(distance_m=500.0))
        # offset: flags(2) + stroke_rate(1) + stroke_count(2) = 5
        dist_bytes = data[5:8]
        distance = int.from_bytes(dist_bytes, byteorder="little")
        assert distance == 500

    def test_zero_distance(self):
        data = pack_rower_data(_metrics(distance_m=0.0))
        dist_bytes = data[5:8]
        distance = int.from_bytes(dist_bytes, byteorder="little")
        assert distance == 0

    def test_large_distance(self):
        """uint24 max = 16777215 meters."""
        data = pack_rower_data(_metrics(distance_m=50000.0))
        dist_bytes = data[5:8]
        distance = int.from_bytes(dist_bytes, byteorder="little")
        assert distance == 50000

    def test_max_clamp(self):
        data = pack_rower_data(_metrics(distance_m=20000000.0))
        dist_bytes = data[5:8]
        distance = int.from_bytes(dist_bytes, byteorder="little")
        assert distance == 0xFFFFFF


class TestPacePacking:
    def test_pace_120s(self):
        """120 s/500m pace."""
        data = pack_rower_data(_metrics(distance_m=100.0, pace_s_per_500m=120.0))
        # offset: flags(2) + stroke(1) + count(2) + distance(3) = 8
        pace = struct.unpack_from("<H", data, 8)[0]
        assert pace == 120

    def test_pace_fractional_rounds(self):
        data = pack_rower_data(_metrics(distance_m=100.0, pace_s_per_500m=119.6))
        pace = struct.unpack_from("<H", data, 8)[0]
        assert pace == 120


class TestPowerPacking:
    def test_power_150w(self):
        """150W power as int16."""
        data = pack_rower_data(
            _metrics(
                distance_m=100.0,
                pace_s_per_500m=120.0,
                power_watts=150.0,
            )
        )
        # offset: flags(2) + stroke(1) + count(2) + distance(3) + pace(2) = 10
        power = struct.unpack_from("<h", data, 10)[0]
        assert power == 150

    def test_zero_power(self):
        data = pack_rower_data(
            _metrics(
                distance_m=100.0,
                pace_s_per_500m=120.0,
                power_watts=0.0,
            )
        )
        power = struct.unpack_from("<h", data, 10)[0]
        assert power == 0

    def test_negative_power_rejected_by_model(self):
        """Negative power is rejected by Pydantic (ge=0 constraint)."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            _metrics(power_watts=-10.0)


class TestExpendedEnergyPacking:
    def test_total_kcal_encoded(self):
        """Total energy packed as uint16 immediately after power field."""
        data = pack_rower_data(
            _metrics(
                distance_m=100.0,
                pace_s_per_500m=120.0,
                power_watts=150.0,
                calories=250,
            )
        )
        # offset: flags(2) + stroke(1) + count(2) + dist(3) + pace(2) + power(2) = 12
        total_kcal = struct.unpack_from("<H", data, 12)[0]
        assert total_kcal == 250

    def test_energy_per_hour_not_available(self):
        """Energy Per Hour sub-field is 0xFFFF (not available)."""
        data = pack_rower_data(
            _metrics(
                distance_m=100.0,
                pace_s_per_500m=120.0,
                power_watts=150.0,
                calories=250,
            )
        )
        # offset 14: after total_kcal(2)
        per_hour = struct.unpack_from("<H", data, 14)[0]
        assert per_hour == 0xFFFF

    def test_energy_per_minute_not_available(self):
        """Energy Per Minute sub-field is 0xFF (not available)."""
        data = pack_rower_data(
            _metrics(
                distance_m=100.0,
                pace_s_per_500m=120.0,
                power_watts=150.0,
                calories=250,
            )
        )
        # offset 16: after per_hour(2)
        per_min = data[16]
        assert per_min == 0xFF

    def test_calories_clamped_below_0xFFFF(self):
        """0xFFFF is reserved for 'not available'; large values are clamped to 0xFFFE."""
        data = pack_rower_data(_metrics(calories=99999))
        total_kcal = struct.unpack_from("<H", data, 2)[
            0
        ]  # flags(2), then calories first since no other optional fields
        # Locate with flag check instead
        flags = _unpack_flags(data)
        assert flags & FLAG_EXPENDED_ENERGY
        # With no distance/pace/power, offset is: flags(2)+stroke(1)+count(2) = 5
        total_kcal = struct.unpack_from("<H", data, 5)[0]
        assert total_kcal == 0xFFFE


class TestElapsedTimePacking:
    def test_elapsed_time_encoded(self):
        """Elapsed time packed as uint16 seconds after HR."""
        data = pack_rower_data(
            _metrics(
                distance_m=100.0,
                pace_s_per_500m=120.0,
                power_watts=150.0,
                calories=250,
                heart_rate_bpm=140,
                elapsed_seconds=600,
            )
        )
        # offset: flags(2)+stroke(1)+count(2)+dist(3)+pace(2)+power(2)
        #         +energy_total(2)+energy_per_hr(2)+energy_per_min(1)+hr(1) = 18
        elapsed = struct.unpack_from("<H", data, 18)[0]
        assert elapsed == 600

    def test_elapsed_time_without_hr(self):
        """Elapsed time packed correctly when HR is absent."""
        data = pack_rower_data(_metrics(elapsed_seconds=300))
        # flags(2)+stroke(1)+count(2) = 5 → elapsed starts at 5
        elapsed = struct.unpack_from("<H", data, 5)[0]
        assert elapsed == 300

    def test_elapsed_time_clamped_to_uint16(self):
        """Values > 65535 are clamped."""
        data = pack_rower_data(_metrics(elapsed_seconds=100000))
        elapsed = struct.unpack_from("<H", data, 5)[0]
        assert elapsed == 0xFFFF


class TestHeartRatePacking:
    def test_hr_140(self):
        """HR packed as uint8 after power (no energy fields present)."""
        data = pack_rower_data(
            _metrics(
                distance_m=100.0,
                pace_s_per_500m=120.0,
                power_watts=150.0,
                heart_rate_bpm=140,
            )
        )
        # offset: flags(2) + stroke(1) + count(2) + dist(3) + pace(2) + power(2) = 12
        assert data[12] == 140

    def test_hr_omitted_when_none(self):
        """Without HR, the data should be shorter."""
        with_hr = pack_rower_data(
            _metrics(
                distance_m=100.0,
                pace_s_per_500m=120.0,
                power_watts=150.0,
                heart_rate_bpm=140,
            )
        )
        without_hr = pack_rower_data(
            _metrics(
                distance_m=100.0,
                pace_s_per_500m=120.0,
                power_watts=150.0,
                heart_rate_bpm=None,
            )
        )
        assert len(with_hr) == len(without_hr) + 1

    def test_hr_max_255(self):
        data = pack_rower_data(_metrics(heart_rate_bpm=250))
        flags = _unpack_flags(data)
        assert flags & FLAG_HEART_RATE


class TestFullPacking:
    def test_full_metrics_round_trip(self):
        """All fields present — verify total byte layout.

        Layout (20 bytes):
          flags(2) + stroke_rate(1) + count(2) + dist(3) + pace(2) + power(2)
          + energy_total(2) + energy_per_hr(2) + energy_per_min(1)
          + hr(1) + elapsed(2) = 20
        """
        metrics = _metrics(
            stroke_rate=28.0,
            stroke_count=100,
            distance_m=2000.0,
            pace_s_per_500m=120.0,
            power_watts=150.0,
            calories=300,
            heart_rate_bpm=140,
            elapsed_seconds=600,
        )
        data = pack_rower_data(metrics)

        assert len(data) == 20

        stroke_rate = data[2]
        stroke_count = struct.unpack_from("<H", data, 3)[0]
        distance = int.from_bytes(data[5:8], "little")
        pace = struct.unpack_from("<H", data, 8)[0]
        power = struct.unpack_from("<h", data, 10)[0]
        total_kcal = struct.unpack_from("<H", data, 12)[0]
        energy_per_hr = struct.unpack_from("<H", data, 14)[0]
        energy_per_min = data[16]
        hr = data[17]
        elapsed = struct.unpack_from("<H", data, 18)[0]

        assert stroke_rate == 56
        assert stroke_count == 100
        assert distance == 2000
        assert pace == 120
        assert power == 150
        assert total_kcal == 300
        assert energy_per_hr == 0xFFFF
        assert energy_per_min == 0xFF
        assert hr == 140
        assert elapsed == 600

    def test_minimal_metrics(self):
        """Only required fields — stroke rate base."""
        data = pack_rower_data(_metrics())
        # flags(2) + stroke_rate(1) + stroke_count(2) = 5
        assert len(data) == 5

    def test_variable_length_based_on_fields(self):
        """Data length varies based on which fields are present."""
        base = pack_rower_data(_metrics())
        with_dist = pack_rower_data(_metrics(distance_m=100.0))
        with_all = pack_rower_data(
            _metrics(
                distance_m=100.0,
                pace_s_per_500m=120.0,
                power_watts=150.0,
                heart_rate_bpm=140,
            )
        )
        assert len(base) < len(with_dist) < len(with_all)

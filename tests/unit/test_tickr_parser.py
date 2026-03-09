"""Tests for TICKR HR measurement parser."""

import pytest

from src.ble.tickr import parse_hr_measurement


class TestParseUint8BPM:
    def test_basic_hr(self):
        # flags=0x00 (uint8, no RR), BPM=140
        data = bytearray([0x00, 140])
        bpm, rr = parse_hr_measurement(data)
        assert bpm == 140
        assert rr == []

    def test_low_hr(self):
        data = bytearray([0x00, 60])
        bpm, rr = parse_hr_measurement(data)
        assert bpm == 60

    def test_high_hr(self):
        data = bytearray([0x00, 200])
        bpm, rr = parse_hr_measurement(data)
        assert bpm == 200


class TestParseUint16BPM:
    def test_uint16_format(self):
        # flags=0x01 (uint16), BPM=140 as uint16 LE
        data = bytearray([0x01, 140, 0])
        bpm, rr = parse_hr_measurement(data)
        assert bpm == 140

    def test_uint16_high_value(self):
        # BPM=200 as uint16 LE
        data = bytearray([0x01, 200, 0])
        bpm, rr = parse_hr_measurement(data)
        assert bpm == 200

    def test_uint16_too_short(self):
        data = bytearray([0x01, 140])
        with pytest.raises(ValueError, match="too short"):
            parse_hr_measurement(data)


class TestParseSingleRRInterval:
    def test_single_rr(self):
        # flags=0x10 (uint8 BPM, RR present), BPM=140, RR=700ms
        # 700ms in 1/1024s = 700 * 1024 / 1000 ≈ 717
        rr_raw = round(700 * 1024 / 1000)
        data = bytearray([0x10, 140])
        data.extend(rr_raw.to_bytes(2, byteorder="little"))
        bpm, rr = parse_hr_measurement(data)
        assert bpm == 140
        assert len(rr) == 1
        assert abs(rr[0] - 700) <= 1  # Allow 1ms rounding


class TestParseMultipleRRIntervals:
    def test_two_rr_intervals(self):
        # flags=0x10, BPM=120, two RR intervals: 800ms and 750ms
        rr1_raw = round(800 * 1024 / 1000)
        rr2_raw = round(750 * 1024 / 1000)
        data = bytearray([0x10, 120])
        data.extend(rr1_raw.to_bytes(2, byteorder="little"))
        data.extend(rr2_raw.to_bytes(2, byteorder="little"))
        bpm, rr = parse_hr_measurement(data)
        assert bpm == 120
        assert len(rr) == 2
        assert abs(rr[0] - 800) <= 1
        assert abs(rr[1] - 750) <= 1

    def test_three_rr_intervals(self):
        rr_values = [600, 700, 800]
        data = bytearray([0x10, 100])
        for rr_ms in rr_values:
            rr_raw = round(rr_ms * 1024 / 1000)
            data.extend(rr_raw.to_bytes(2, byteorder="little"))
        bpm, rr = parse_hr_measurement(data)
        assert len(rr) == 3


class TestRejectOutOfRange:
    def test_bpm_too_low(self):
        data = bytearray([0x00, 10])
        with pytest.raises(ValueError, match="out of range"):
            parse_hr_measurement(data)

    def test_bpm_too_high(self):
        # uint16 format, BPM=300
        data = bytearray([0x01])
        data.extend((300).to_bytes(2, byteorder="little"))
        with pytest.raises(ValueError, match="out of range"):
            parse_hr_measurement(data)

    def test_bpm_zero(self):
        data = bytearray([0x00, 0])
        with pytest.raises(ValueError, match="out of range"):
            parse_hr_measurement(data)

    def test_rr_too_low(self):
        # RR interval of 100ms (too low, min 200ms)
        rr_raw = round(100 * 1024 / 1000)
        data = bytearray([0x10, 140])
        data.extend(rr_raw.to_bytes(2, byteorder="little"))
        with pytest.raises(ValueError, match="RR interval out of range"):
            parse_hr_measurement(data)

    def test_rr_too_high(self):
        # RR interval of 2500ms (too high, max 2000ms)
        rr_raw = round(2500 * 1024 / 1000)
        data = bytearray([0x10, 140])
        data.extend(rr_raw.to_bytes(2, byteorder="little"))
        with pytest.raises(ValueError, match="RR interval out of range"):
            parse_hr_measurement(data)


class TestEdgeCases:
    def test_data_too_short(self):
        with pytest.raises(ValueError, match="too short"):
            parse_hr_measurement(bytearray([0x00]))

    def test_empty_data(self):
        with pytest.raises(ValueError, match="too short"):
            parse_hr_measurement(bytearray())

    def test_no_rr_flag_ignores_trailing_bytes(self):
        # flags=0x00 (no RR), but extra bytes present — should ignore
        data = bytearray([0x00, 140, 0xFF, 0xFF])
        bpm, rr = parse_hr_measurement(data)
        assert bpm == 140
        assert rr == []

    def test_rr_flag_but_no_rr_data(self):
        # flags=0x10 (RR present) but no RR bytes after BPM
        data = bytearray([0x10, 140])
        bpm, rr = parse_hr_measurement(data)
        assert bpm == 140
        assert rr == []

    def test_odd_trailing_byte_ignored(self):
        # RR present flag, one valid RR + one trailing byte (incomplete)
        rr_raw = round(700 * 1024 / 1000)
        data = bytearray([0x10, 140])
        data.extend(rr_raw.to_bytes(2, byteorder="little"))
        data.append(0xFF)  # Odd trailing byte
        bpm, rr = parse_hr_measurement(data)
        assert len(rr) == 1

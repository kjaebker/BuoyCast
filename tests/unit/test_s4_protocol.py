"""Tests for S4 protocol constants, command builders, and parsers."""

import pytest

from src.s4.protocol import (
    ADDR_AVG_SPEED,
    ADDR_CALORIES,
    ADDR_DISTANCE_M,
    ADDR_ELAPSED_HOURS,
    ADDR_ELAPSED_MINS,
    ADDR_ELAPSED_SECS,
    ADDR_POWER,
    ADDR_STROKE_COUNT,
    ADDR_STROKE_RATE,
    RESP_IDD,
    RESP_IDS,
    RESP_IDT,
    RESP_PING,
    RESP_SE,
    RESP_SS,
    RESP_WR,
    ProtocolError,
    ReadSize,
    avg_speed_to_pace,
    bcd_decode,
    build_exit,
    build_handshake,
    build_iv_query,
    build_read_command,
    build_reset,
    elapsed_time_to_seconds,
    parse_response,
    stroke_rate_raw_to_spm,
)


class TestCommandBuilders:
    def test_handshake(self):
        assert build_handshake() == "USB"

    def test_reset(self):
        assert build_reset() == "RESET"

    def test_iv_query(self):
        assert build_iv_query() == "IV?"

    def test_exit(self):
        assert build_exit() == "EXIT"

    def test_read_single_byte(self):
        # ADDR_STROKE_RATE is "1A9" SINGLE → IRS1A9
        cmd = build_read_command(ADDR_STROKE_RATE)
        assert cmd == "IRS1A9"

    def test_read_double_byte(self):
        # ADDR_DISTANCE_M is "055" DOUBLE → IRD055
        cmd = build_read_command(ADDR_DISTANCE_M)
        assert cmd == "IRD055"

    def test_read_triple_byte(self):
        # ADDR_CALORIES is "08A" TRIPLE → IRT08A
        cmd = build_read_command(ADDR_CALORIES)
        assert cmd == "IRT08A"

    def test_read_elapsed_secs(self):
        # ADDR_ELAPSED_SECS is "1E1" SINGLE
        cmd = build_read_command(ADDR_ELAPSED_SECS)
        assert cmd == "IRS1E1"


class TestParseResponse:
    def test_single_byte_response(self):
        resp_type, addr, value = parse_response("IDS1E100")
        assert resp_type == RESP_IDS
        assert addr == "1E1"
        assert value == 0x00

    def test_single_byte_nonzero(self):
        resp_type, addr, value = parse_response("IDS1E10A")
        assert resp_type == RESP_IDS
        assert addr == "1E1"
        assert value == 10

    def test_double_byte_response(self):
        resp_type, addr, value = parse_response("IDD05500FF")
        assert resp_type == RESP_IDD
        assert addr == "055"
        assert value == 0xFF

    def test_double_byte_distance(self):
        # 500 meters = 0x01F4
        resp_type, addr, value = parse_response("IDD05501F4")
        assert resp_type == RESP_IDD
        assert addr == "055"
        assert value == 500

    def test_triple_byte_response(self):
        resp_type, addr, value = parse_response("IDT08A000032")
        assert resp_type == RESP_IDT
        assert addr == "08A"
        assert value == 50

    def test_triple_byte_large_value(self):
        resp_type, addr, value = parse_response("IDT08AFFFFFF")
        assert resp_type == RESP_IDT
        assert addr == "08A"
        assert value == 0xFFFFFF

    def test_wr_response(self):
        resp_type, addr, value = parse_response("_WR_")
        assert resp_type == RESP_WR
        assert addr is None
        assert value is None

    def test_stroke_start(self):
        resp_type, addr, value = parse_response("SS")
        assert resp_type == RESP_SS
        assert addr is None

    def test_stroke_end(self):
        resp_type, addr, value = parse_response("SE")
        assert resp_type == RESP_SE
        assert addr is None

    def test_ping(self):
        resp_type, addr, value = parse_response("PING")
        assert resp_type == RESP_PING
        assert addr is None

    def test_iv_response(self):
        resp_type, addr, value = parse_response("IV40210")
        assert resp_type == "IV"
        assert addr is None

    def test_empty_line_raises(self):
        with pytest.raises(ProtocolError, match="Empty"):
            parse_response("")

    def test_whitespace_only_raises(self):
        with pytest.raises(ProtocolError, match="Empty"):
            parse_response("   \r\n")

    def test_malformed_single_too_short(self):
        with pytest.raises(ProtocolError, match="Malformed"):
            parse_response("IDS1E1")

    def test_malformed_double_too_short(self):
        with pytest.raises(ProtocolError, match="Malformed"):
            parse_response("IDD05500")

    def test_malformed_triple_too_short(self):
        with pytest.raises(ProtocolError, match="Malformed"):
            parse_response("IDT08A00001")

    def test_invalid_hex_in_value(self):
        with pytest.raises(ProtocolError, match="Invalid hex"):
            parse_response("IDS1E1GG")

    def test_strips_whitespace(self):
        resp_type, addr, value = parse_response("  IDS1E10A  \r\n")
        assert value == 10

    def test_unknown_response_not_crash(self):
        resp_type, addr, value = parse_response("UNKNOWN_MSG")
        assert resp_type == "UNKNOWN_MSG"
        assert addr is None


class TestStrokeRateConversion:
    def test_28_spm_direct(self):
        # Address 1A9 stores SPM directly — raw 28 = 28 SPM
        assert stroke_rate_raw_to_spm(28) == 28.0

    def test_zero(self):
        assert stroke_rate_raw_to_spm(0) == 0.0

    def test_max_reasonable(self):
        assert stroke_rate_raw_to_spm(40) == 40.0


class TestAvgSpeedToPace:
    def test_2min_pace(self):
        # 500m in 120s → speed = 500m/120s = 416.67 cm/s
        cmps = int(50000 / 120.0)
        pace = avg_speed_to_pace(cmps)
        assert abs(pace - 120.0) < 1.0  # within 1 second

    def test_zero_speed_returns_zero(self):
        assert avg_speed_to_pace(0) == 0.0

    def test_known_value(self):
        # 250 cm/s → pace = 50000/250 = 200 s/500m
        assert avg_speed_to_pace(250) == 200.0


class TestBcdDecode:
    def test_30_seconds(self):
        # S4 sends 0x30 for 30 — int("30", 16) = 48; bcd_decode(48) = 30
        assert bcd_decode(0x30) == 30

    def test_zero(self):
        assert bcd_decode(0) == 0

    def test_59(self):
        assert bcd_decode(0x59) == 59

    def test_10(self):
        assert bcd_decode(0x10) == 10


class TestElapsedTime:
    def test_ten_minutes(self):
        assert elapsed_time_to_seconds(0, 10, 0) == 600

    def test_one_hour(self):
        assert elapsed_time_to_seconds(1, 0, 0) == 3600

    def test_mixed(self):
        assert elapsed_time_to_seconds(1, 30, 45) == 5445

    def test_zero(self):
        assert elapsed_time_to_seconds(0, 0, 0) == 0


class TestMemoryLocations:
    def test_stroke_rate_address(self):
        assert ADDR_STROKE_RATE.address == "1A9"
        assert ADDR_STROKE_RATE.size == ReadSize.SINGLE

    def test_stroke_count_address(self):
        assert ADDR_STROKE_COUNT.address == "140"
        assert ADDR_STROKE_COUNT.size == ReadSize.DOUBLE

    def test_distance_address(self):
        assert ADDR_DISTANCE_M.address == "055"
        assert ADDR_DISTANCE_M.size == ReadSize.DOUBLE

    def test_avg_speed_address(self):
        assert ADDR_AVG_SPEED.address == "14A"
        assert ADDR_AVG_SPEED.size == ReadSize.DOUBLE

    def test_power_address(self):
        assert ADDR_POWER.address == "088"
        assert ADDR_POWER.size == ReadSize.DOUBLE

    def test_calories_address(self):
        assert ADDR_CALORIES.address == "08A"
        assert ADDR_CALORIES.size == ReadSize.TRIPLE

    def test_elapsed_time_addresses(self):
        assert ADDR_ELAPSED_SECS.address == "1E1"
        assert ADDR_ELAPSED_MINS.address == "1E2"
        assert ADDR_ELAPSED_HOURS.address == "1E3"
        assert ADDR_ELAPSED_HOURS.size == ReadSize.SINGLE
        assert ADDR_ELAPSED_MINS.size == ReadSize.SINGLE
        assert ADDR_ELAPSED_SECS.size == ReadSize.SINGLE

"""Tests for S4 protocol constants, command builders, and parsers."""

import pytest

from src.s4.protocol import (
    ADDR_CALORIES,
    ADDR_DISTANCE_M,
    ADDR_ELAPSED_HOURS,
    ADDR_ELAPSED_MINS,
    ADDR_ELAPSED_SECS,
    ADDR_PACE,
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
    assemble_distance,
    build_handshake,
    build_read_command,
    build_reset,
    elapsed_time_to_seconds,
    pace_raw_to_seconds_per_500m,
    parse_double_byte,
    parse_response,
    parse_single_byte,
    parse_triple_byte,
    stroke_rate_raw_to_spm,
)


class TestCommandBuilders:
    def test_handshake(self):
        assert build_handshake() == "USB"

    def test_reset(self):
        assert build_reset() == "RESET"

    def test_read_single_byte(self):
        cmd = build_read_command(ADDR_ELAPSED_HOURS)
        assert cmd == "IRDS1E1"

    def test_read_double_byte(self):
        cmd = build_read_command(ADDR_STROKE_RATE)
        assert cmd == "IRDD140"

    def test_read_triple_byte(self):
        cmd = build_read_command(ADDR_CALORIES)
        assert cmd == "IRDT088"


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
        resp_type, addr, value = parse_response("IDD14000FF")
        assert resp_type == RESP_IDD
        assert addr == "140"
        assert value == 0xFF

    def test_double_byte_stroke_rate(self):
        # 28 SPM * 2 = 56 = 0x0038
        resp_type, addr, value = parse_response("IDD1400038")
        assert resp_type == RESP_IDD
        assert addr == "140"
        assert value == 56

    def test_triple_byte_response(self):
        resp_type, addr, value = parse_response("IDT088000032")
        assert resp_type == RESP_IDT
        assert addr == "088"
        assert value == 50

    def test_triple_byte_large_value(self):
        resp_type, addr, value = parse_response("IDT088FFFFFF")
        assert resp_type == RESP_IDT
        assert addr == "088"
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
            parse_response("IDD14000")

    def test_malformed_triple_too_short(self):
        with pytest.raises(ProtocolError, match="Malformed"):
            parse_response("IDT08800001")

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


class TestParseSingleByte:
    def test_zero(self):
        assert parse_single_byte(0) == 0

    def test_max(self):
        assert parse_single_byte(255) == 255

    def test_mid(self):
        assert parse_single_byte(128) == 128

    def test_negative_raises(self):
        with pytest.raises(ProtocolError):
            parse_single_byte(-1)

    def test_overflow_raises(self):
        with pytest.raises(ProtocolError):
            parse_single_byte(256)


class TestParseDoubleByte:
    def test_zero(self):
        assert parse_double_byte(0) == 0

    def test_max(self):
        assert parse_double_byte(65535) == 65535

    def test_negative_raises(self):
        with pytest.raises(ProtocolError):
            parse_double_byte(-1)

    def test_overflow_raises(self):
        with pytest.raises(ProtocolError):
            parse_double_byte(65536)


class TestParseTripleByte:
    def test_zero(self):
        assert parse_triple_byte(0) == 0

    def test_max(self):
        assert parse_triple_byte(0xFFFFFF) == 16777215

    def test_negative_raises(self):
        with pytest.raises(ProtocolError):
            parse_triple_byte(-1)

    def test_overflow_raises(self):
        with pytest.raises(ProtocolError):
            parse_triple_byte(0x1000000)


class TestStrokeRateConversion:
    def test_28_spm(self):
        assert stroke_rate_raw_to_spm(56) == 28.0

    def test_zero(self):
        assert stroke_rate_raw_to_spm(0) == 0.0

    def test_half_spm_resolution(self):
        assert stroke_rate_raw_to_spm(55) == 27.5

    def test_max_reasonable(self):
        assert stroke_rate_raw_to_spm(120) == 60.0


class TestPaceConversion:
    def test_120s_per_500m(self):
        # 120.0 seconds/500m → raw = 1200
        assert pace_raw_to_seconds_per_500m(1200) == 120.0

    def test_zero_means_no_pace(self):
        assert pace_raw_to_seconds_per_500m(0) == 0.0

    def test_subsecond_resolution(self):
        # 95.3 seconds/500m → raw = 953
        assert pace_raw_to_seconds_per_500m(953) == 95.3


class TestAssembleDistance:
    def test_meters_only(self):
        assert assemble_distance(500) == 500.0

    def test_meters_and_cm(self):
        assert assemble_distance(500, 50) == 500.5

    def test_zero(self):
        assert assemble_distance(0, 0) == 0.0


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
        assert ADDR_STROKE_RATE.address == "140"
        assert ADDR_STROKE_RATE.size == ReadSize.DOUBLE

    def test_distance_address(self):
        assert ADDR_DISTANCE_M.address == "057"
        assert ADDR_DISTANCE_M.size == ReadSize.DOUBLE

    def test_pace_address(self):
        assert ADDR_PACE.address == "1A5"
        assert ADDR_PACE.size == ReadSize.DOUBLE

    def test_power_address(self):
        assert ADDR_POWER.address == "148"
        assert ADDR_POWER.size == ReadSize.DOUBLE

    def test_calories_address(self):
        assert ADDR_CALORIES.address == "088"
        assert ADDR_CALORIES.size == ReadSize.TRIPLE

    def test_elapsed_time_addresses(self):
        assert ADDR_ELAPSED_HOURS.size == ReadSize.SINGLE
        assert ADDR_ELAPSED_MINS.size == ReadSize.SINGLE
        assert ADDR_ELAPSED_SECS.size == ReadSize.SINGLE

    def test_stroke_count_address(self):
        assert ADDR_STROKE_COUNT.address == "142"
        assert ADDR_STROKE_COUNT.size == ReadSize.DOUBLE

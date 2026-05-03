"""Tests for core/timing.py"""
import pytest
from core.timing import (
    bars_to_beats, beats_to_bars, bars_to_seconds, seconds_to_bars,
    beats_per_bar, cue_duration_master_beats, format_position,
    parse_speed_ratio, parse_time_signature, sec_per_bar, sec_per_beat,
)


class TestParseTimeSignature:
    def test_4_4(self):
        assert parse_time_signature("4/4") == (4, 4)

    def test_3_4(self):
        assert parse_time_signature("3/4") == (3, 4)

    def test_6_8(self):
        assert parse_time_signature("6/8") == (6, 8)

    def test_7_8(self):
        assert parse_time_signature("7/8") == (7, 8)

    def test_invalid(self):
        with pytest.raises(ValueError):
            parse_time_signature("4-4")


class TestBeatsPerBar:
    def test_4_4(self):
        assert beats_per_bar("4/4") == 4

    def test_3_4(self):
        assert beats_per_bar("3/4") == 3

    def test_6_8(self):
        assert beats_per_bar("6/8") == 6


class TestSecPerBeat:
    def test_120_bpm(self):
        assert sec_per_beat(120.0) == pytest.approx(0.5)

    def test_60_bpm(self):
        assert sec_per_beat(60.0) == pytest.approx(1.0)

    def test_zero_bpm_raises(self):
        with pytest.raises(ValueError):
            sec_per_beat(0.0)


class TestSecPerBar:
    def test_120_bpm_4_4(self):
        # 4 beats × 0.5 sec/beat = 2.0 sec/bar
        assert sec_per_bar(120.0, "4/4") == pytest.approx(2.0)

    def test_60_bpm_3_4(self):
        # 3 beats × 1.0 sec/beat = 3.0 sec/bar
        assert sec_per_bar(60.0, "3/4") == pytest.approx(3.0)


class TestBarsToBeats:
    def test_2_bars_4_4(self):
        assert bars_to_beats(2.0, "4/4") == pytest.approx(8.0)

    def test_half_bar_6_8(self):
        assert bars_to_beats(0.5, "6/8") == pytest.approx(3.0)


class TestBeatsToSeconds:
    def test_roundtrip(self):
        for ts in ("4/4", "3/4", "6/8"):
            bars = 4.0
            beats = bars_to_beats(bars, ts)
            back = beats_to_bars(beats, ts)
            assert back == pytest.approx(bars)


class TestParseSpeedRatio:
    def test_1_1(self):
        assert parse_speed_ratio("1:1") == pytest.approx(1.0)

    def test_2_1(self):
        assert parse_speed_ratio("2:1") == pytest.approx(2.0)

    def test_1_2(self):
        assert parse_speed_ratio("1:2") == pytest.approx(0.5)

    def test_4_1(self):
        assert parse_speed_ratio("4:1") == pytest.approx(4.0)

    def test_invalid(self):
        with pytest.raises(ValueError):
            parse_speed_ratio("bad")


class TestCueDurationMasterBeats:
    def test_1_1_ratio(self):
        # 4 bars @ 1:1, 4/4 → 4×4=16 master beats
        assert cue_duration_master_beats(4.0, "1:1", "4/4") == pytest.approx(16.0)

    def test_2_1_ratio(self):
        # 4 lane bars @ 2:1, 4/4 → lane_beats=16, master_beats=16/2=8
        assert cue_duration_master_beats(4.0, "2:1", "4/4") == pytest.approx(8.0)

    def test_1_2_ratio(self):
        # 4 lane bars @ 1:2, 4/4 → lane_beats=16, master_beats=16/0.5=32
        assert cue_duration_master_beats(4.0, "1:2", "4/4") == pytest.approx(32.0)

    def test_zero_bars(self):
        assert cue_duration_master_beats(0.0, "1:1", "4/4") == pytest.approx(0.0)


class TestFormatPosition:
    def test_start(self):
        assert format_position(0.0, "4/4") == "1:1"

    def test_second_bar(self):
        # beat_position=4.0 in 4/4 → bar 2, beat 1
        assert format_position(4.0, "4/4") == "2:1"

    def test_mid_bar(self):
        # beat_position=6.0 in 4/4 → bar 2 (beats 4-7), beat 3 → "2:3"
        assert format_position(6.0, "4/4") == "2:3"

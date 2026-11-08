import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from calc import Layer, parallel_resistance, solve_air, solve_surface  # noqa: E402


def example_layers():
    """정리본 02강 p.29~30 예제: 콘크리트 | 단열재 | 목재."""
    return [
        Layer("콘크리트", 0.4, 1.0),
        Layer("단열재", 0.05, 0.02),
        Layer("목재", 0.15, 0.1),
    ]


# 1) 정리본 예제 (02강 p.29~30)
def test_textbook_example_surface_mode():
    res = solve_surface(example_layers(), T_os=40, T_is=10)
    assert res["R_t"] == pytest.approx(4.4)
    assert round(res["q_abs"], 2) == 6.82
    assert res["q_t"] > 0
    assert res["direction"] == "외부 → 내부"

    temps = [b["T"] for b in res["boundaries"]]
    # [T_os, T_ci(T_1), T_iw(T_2), T_is]
    assert temps[0] == 40
    assert round(temps[1], 1) == 37.3
    assert round(temps[2], 1) == 20.2
    assert temps[3] == 10
    assert res["boundaries"][1]["label"] == "콘크리트|단열재"
    assert res["boundaries"][2]["label"] == "단열재|목재"

    # 층별 R, 비율, 온도 강하
    Rs = [e["R"] for e in res["elements"]]
    assert Rs == pytest.approx([0.4, 2.5, 1.5])
    assert sum(e["share_pct"] for e in res["elements"]) == pytest.approx(100.0)
    assert res["elements"][1]["share_pct"] == pytest.approx(2.5 / 4.4 * 100)
    assert sum(e["dT"] for e in res["elements"]) == pytest.approx(40 - 10)
    # 마지막 층 끝 온도가 T_is 와 일치 (누적 계산 검증)
    assert res["elements"][-1]["T_end"] == pytest.approx(10)
    assert res["total_thickness"] == pytest.approx(0.6)
    assert res["U"] is None  # 표면 모드의 K_t 는 U-value 가 아님


# 2) 직렬 예 (02강 p.21)
def test_series_example_p21():
    layers = [
        Layer("콘크리트", 0.12, 1.5),
        Layer("단열재", 0.06, 0.03),
        Layer("콘크리트", 0.12, 1.5),
    ]
    res = solve_surface(layers, T_os=0, T_is=20)
    assert res["R_t"] == pytest.approx(2.16)
    assert res["K_t"] == pytest.approx(1 / 2.16)


# 3-a) 병렬 기본 케이스 (02강 p.25)
def test_parallel_basic():
    assert parallel_resistance([2.0, 2.0]) == pytest.approx(1.0)
    # 단열재(2.0) 와 콘크리트(0.08) 병렬 -> 1/(0.5 + 12.5)
    assert parallel_resistance([2.0, 0.08]) == pytest.approx(1 / 13)


# 3-b) 공기온도 모드 (02강 p.57~59)
def test_air_mode_monotonic_and_u_value():
    res = solve_air(example_layers(), T_oa=-5, T_ia=20, h_to=25, h_ti=7.7)
    expected_R_t = 1 / 25 + 4.4 + 1 / 7.7
    assert res["R_t"] == pytest.approx(expected_R_t)
    assert res["U"] == pytest.approx(1 / expected_R_t)
    assert res["q_t"] < 0
    assert res["direction"] == "내부 → 외부"

    temps = [b["T"] for b in res["boundaries"]]
    symbols = [b["symbol"] for b in res["boundaries"]]
    assert symbols == ["T_oa", "T_os", "T_1", "T_2", "T_is", "T_ia"]
    assert temps[0] == -5 and temps[-1] == 20
    # T_oa 와 T_ia 사이에서 단조 증가
    assert all(a < b for a, b in zip(temps, temps[1:]))
    assert all(-5 <= t <= 20 for t in temps)
    # 표면저항에서 온도 점프: T_os = T_oa - q_t / h_to
    assert temps[1] == pytest.approx(-5 - res["q_t"] / 25)
    # 표면저항은 두께 0 -> 외표면 x = 0
    assert res["boundaries"][1]["x"] == 0.0


# 부호 규약: 겨울(내부가 더 따뜻함)에도 경계 온도가 올바른지
def test_winter_surface_mode_sign_convention():
    res = solve_surface(example_layers(), T_os=0, T_is=20)
    assert res["q_t"] == pytest.approx(-20 / 4.4)
    assert res["q_abs"] == pytest.approx(20 / 4.4)
    temps = [b["T"] for b in res["boundaries"]]
    assert all(a < b for a, b in zip(temps, temps[1:]))
    assert temps[1] == pytest.approx(0 + 20 / 4.4 * 0.4)
    assert all(e["dT"] < 0 for e in res["elements"])


def test_zero_temperature_difference():
    res = solve_surface(example_layers(), T_os=20, T_is=20)
    assert res["q_t"] == 0
    assert res["direction"] == "없음 (온도차 0)"


@pytest.mark.parametrize("layers", [
    [],
    [Layer("x", 0, 1.0)],
    [Layer("x", -0.1, 1.0)],
    [Layer("x", 0.1, 0)],
    [Layer("x", 0.1, float("nan"))],
])
def test_invalid_layers(layers):
    with pytest.raises(ValueError):
        solve_surface(layers, 10, 20)


def test_invalid_h_and_parallel():
    with pytest.raises(ValueError):
        solve_air(example_layers(), 0, 20, h_to=0, h_ti=7.7)
    with pytest.raises(ValueError):
        solve_air(example_layers(), 0, 20, h_to=25, h_ti=-1)
    with pytest.raises(ValueError):
        parallel_resistance([1.0, 0])
    with pytest.raises(ValueError):
        parallel_resistance([])

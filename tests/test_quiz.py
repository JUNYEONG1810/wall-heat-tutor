import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from calc import Layer, solve_surface  # noqa: E402
from materials import MATERIAL_PRESETS  # noqa: E402
from quiz import (CONCEPT_QUESTIONS, DEMO_T_PROBLEM, FINISH, INSULATION, NUMERIC_KINDS, STRUCTURE,  # noqa: E402
                  is_correct, make_numeric_problem, make_round)

RANGES = {k: (lo, hi) for k, lo, hi, _ in STRUCTURE + INSULATION + FINISH}


@pytest.mark.parametrize("kind", NUMERIC_KINDS)
def test_problems_are_deterministic_realistic_and_match_calc(kind):
    for seed in range(200):
        p = make_numeric_problem(kind, seed)
        assert p == make_numeric_problem(kind, seed)
        assert 2 <= len(p["layers"]) <= 3
        for key, d in p["layers"]:
            lo, hi = RANGES[key]
            assert lo - 1e-9 <= d <= hi + 1e-9
            assert key in MATERIAL_PRESETS
        assert p["T_os"] != p["T_is"]
        layers = [Layer(MATERIAL_PRESETS[k]["name"], d, MATERIAL_PRESETS[k]["k"]) for k, d in p["layers"]]
        res = solve_surface(layers, p["T_os"], p["T_is"])
        if kind == "R_t":
            assert p["answer"] == pytest.approx(res["R_t"])
        elif kind == "q_t":
            assert p["answer"] == pytest.approx(res["q_abs"])
            assert 0.5 < p["answer"] < 200  # 비현실적인 열류 없음
        elif kind == "T":
            temps = [b["T"] for b in res["boundaries"]]
            assert p["answer"] in temps[1:-1]
            assert min(p["T_os"], p["T_is"]) < p["answer"] < max(p["T_os"], p["T_is"])
        else:
            assert p["answer"] in [e["R"] for e in res["elements"]]
        assert 0.01 < (res["R_t"]) < 10


def test_demo_mode_fixes_boundary_problem_only():
    a, b = make_round(111, demo=True), make_round(999, demo=True)
    assert a[3] == b[3] and a[3]["demo"] and a[3]["kind"] == "T"
    assert a[0] != b[0]
    assert not any(p["demo"] for p in make_round(111, demo=False))
    assert [p["kind"] for p in a] == ["R", "R_t", "q_t", "T"]
    # 구조층|단열재 경계 T_1 을 묻고, 그 뒤 단열재층에서 온도 강하가 가장 크다
    demo = a[3]
    assert demo["target"] == "T_1" and "콘크리트|단열재" in demo["question"]
    for key, d in DEMO_T_PROBLEM["layers"]:
        lo, hi = RANGES[key]
        assert lo <= d <= hi
    layers = [Layer(MATERIAL_PRESETS[k]["name"], d, MATERIAL_PRESETS[k]["k"]) for k, d in demo["layers"]]
    res = solve_surface(layers, demo["T_os"], demo["T_is"])
    drops = [abs(e["dT"]) for e in res["elements"]]
    assert drops.index(max(drops)) == 1
    assert demo["answer"] == pytest.approx(res["boundaries"][1]["T"])


def test_is_correct_tolerance():
    p = {"answer": 10.0, "unit": "W/m²"}
    assert is_correct(10.19, p) and is_correct(9.81, p)
    assert not is_correct(10.25, p) and not is_correct(None, p)
    t = {"answer": 1.0, "unit": "°C"}  # 0 °C 근처: 최소 ±0.1 °C
    assert is_correct(1.09, t) and not is_correct(1.2, t)


def test_concept_questions_are_complete():
    ids = {q["id"] for q in CONCEPT_QUESTIONS}
    assert {"k_vs_K", "series", "parallel", "steady_flux", "u_value", "thermal_bridge",
            "stefan_boltzmann"} <= ids
    assert 6 <= len(CONCEPT_QUESTIONS) <= 8
    for q in CONCEPT_QUESTIONS:
        assert len(q["options"]) == len(q["why"]) >= 3
        assert 0 <= q["answer"] < len(q["options"])
        assert q["source"].startswith("02강 p.")
    assert len({q["answer"] for q in CONCEPT_QUESTIONS}) > 1  # 정답 위치가 한쪽에 몰리지 않음

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from challenge import (CONCRETE, D_MAX, D_MIN, GYPSUM, INSULATIONS, LEVELS, LV3_PRESETS, LV4_ANSWER,  # noqa: E402
                       LV4_CHOICES, LV4_INNER, LV4_OUTER, STEP, design_summary, evaluate, hints,
                       inner_surface_temp, lv4_results, solve)

THICKNESSES = [round(D_MIN + i * STEP, 2) for i in range(round((D_MAX - D_MIN) / STEP) + 1)]
K03 = "단열재 (p.21, k=0.03)"


def with_insulation(level, key, d):
    spec = list(LEVELS[level]["start"])
    spec[LEVELS[level]["edit_index"]] = (key, d)
    return spec


def test_lv1_solvable_and_threshold_exact():
    assert not evaluate(1, LEVELS[1]["start"])["passed"]
    passing = [d for d in THICKNESSES if evaluate(1, with_insulation(1, K03, d))["passed"]]
    assert passing and min(passing) == pytest.approx(0.09)
    ev8, ev9 = evaluate(1, with_insulation(1, K03, 0.08)), evaluate(1, with_insulation(1, K03, 0.09))
    assert ev8["res"]["U"] > 0.30 >= ev9["res"]["U"]
    assert not ev8["passed"] and ev9["passed"]


def test_lv2_type_choice_matters():
    assert not evaluate(2, LEVELS[2]["start"])["passed"]
    solvable = {key: any(evaluate(2, with_insulation(2, key, d))["passed"] for d in THICKNESSES)
                for key in INSULATIONS}
    assert solvable == {INSULATIONS[0]: True, INSULATIONS[1]: True, INSULATIONS[2]: False}
    # k=0.04 는 U 는 맞출 수 있어도 두께 조건에서 떨어진다
    ev = evaluate(2, with_insulation(2, INSULATIONS[2], 0.19))
    u_check, t_check = ev["checks"]
    assert u_check["passed"] and not t_check["passed"]
    assert evaluate(2, with_insulation(2, K03, 0.14))["passed"]


def test_lv3_solution_and_each_condition():
    assert not evaluate(3, LEVELS[3]["start"])["passed"]
    outer = [(K03, 0.20), (CONCRETE, 0.20), (GYPSUM, 0.015)]   # 외단열
    inner = [(CONCRETE, 0.20), (K03, 0.20), (GYPSUM, 0.015)]   # 내단열
    ev_o, ev_i = evaluate(3, outer), evaluate(3, inner)
    assert ev_o["passed"]
    labels = {c["label"]: c["passed"] for c in ev_i["checks"]}
    assert labels == {"U-value": True, "총 두께": True, "구조층 포함": True, "구조층 최저 온도": False}
    # 구조층 없으면 실패, 너무 두꺼우면 실패
    no_struct = evaluate(3, [(K03, 0.25)])
    assert not {c["label"]: c["passed"] for c in no_struct["checks"]}["구조층 포함"]
    thick = evaluate(3, [(K03, 0.20), (CONCRETE, 0.30), (GYPSUM, 0.015)])
    assert not {c["label"]: c["passed"] for c in thick["checks"]}["총 두께"]
    # 실내 표면 온도는 배치와 무관 (U 로만 결정) -> 독립 조건이 될 수 없음을 확인
    assert ev_o["inner_surface_temp"] == pytest.approx(ev_i["inner_surface_temp"])


def test_lv3_presets_exclude_custom_and_progress_range():
    assert "직접 입력" not in LV3_PRESETS
    for c in evaluate(3, LEVELS[3]["start"])["checks"]:
        assert 0.0 <= c["progress"] <= 1.0


def test_hints_point_to_best_layer_without_answer():
    h = hints(LEVELS[1]["start"])
    assert sum(s["share_pct"] for s in h["shares"]) == pytest.approx(100)
    assert h["best_name"] == "단열재" and h["best_drop"] > 0
    h3 = hints([(CONCRETE, 0.20), (GYPSUM, 0.015)])
    assert h3["best_name"] == "석고보드"  # k 가 더 작은 층이 1 cm 당 효과가 크다


def test_lv4_same_u_different_temperatures():
    r = lv4_results()
    assert r["inner"]["U"] == pytest.approx(r["outer"]["U"])
    assert inner_surface_temp(r["inner"]) == pytest.approx(inner_surface_temp(r["outer"]))
    assert r["outer_struct"] - r["inner_struct"] > 20  # 구조층 온도는 크게 다르다
    assert "그대로" in LV4_CHOICES[LV4_ANSWER]
    assert sorted(LV4_INNER) == sorted(LV4_OUTER)


def test_design_summary_is_json():
    spec = LEVELS[3]["start"]
    s = design_summary(3, spec, evaluate(3, spec))
    json.dumps(s, ensure_ascii=False)
    assert s["현재 설계 (실외→실내)"][0]["재료"] == "콘크리트"
    assert solve(spec)["U"] > 0

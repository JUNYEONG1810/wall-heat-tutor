"""설계 챌린지: 목표 조건을 만족하는 벽을 직접 설계한다.

새 계산 로직은 없다. 모든 수치는 calc.solve_air 결과를 그대로 읽는다.
공기온도 모드, h_to = 25, h_ti = 7.7 W/(m²K) (대표값), 판정 조건은 겨울 T_oa = -10 °C, T_ia = 20 °C.

레벨 수치는 tests/test_challenge.py 에서 프리셋으로 풀 수 있는지 검증한다.
- Lv.1 단열재(k=0.03) 9 cm 부터 통과 (시작 5 cm: U = 0.487)
- Lv.2 총 두께 0.40 m 제한 때문에 k=0.04 단열재로는 통과 불가 (19 cm 필요 → 0.405 m) → 재료 선택이 의미 있음
- Lv.3 실내 표면 온도는 1차원 정상상태에서 U 로만 정해진다 (T_is = T_ia - U·ΔT/h_ti).
  그래서 독립 조건이 될 수 없어 참고값으로만 보여 주고, 대신 배치에 따라 크게 달라지는
  '구조층 최저 온도 ≥ 0 °C' (외단열 -> 18.5 °C, 내단열 -> -9.8 °C) 를 조건으로 쓴다.
"""

from __future__ import annotations

from calc import DEFAULT_H_TI, DEFAULT_H_TO, Layer, solve_air
from materials import CUSTOM, MATERIAL_PRESETS

H_TO, H_TI = DEFAULT_H_TO, DEFAULT_H_TI
T_OA, T_IA = -10.0, 20.0
STEP = 0.01  # 두께 조절 단위 [m] (1 cm)
D_MIN, D_MAX = 0.01, 0.30

CONCRETE = "콘크리트 (p.21, k=1.5)"
GYPSUM = "석고보드 (대표값, k=0.18)"
INSULATIONS = ["단열재 (예제 p.29, k=0.02)", "단열재 (p.21, k=0.03)", "단열재 (일반값 p.14, k=0.04)"]
STRUCTURAL_NAMES = {"콘크리트", "벽돌"}
LV3_PRESETS = [k for k in MATERIAL_PRESETS if k != CUSTOM]

LEVELS = {
    1: {
        "title": "Lv.1 단열재 두께 맞추기",
        "goal": "단열재(k = 0.03) 두께만 조절해서 U-value ≤ 0.30 W/(m²K) 를 달성하세요.",
        "editable": "thickness",
        "start": [(CONCRETE, 0.20), ("단열재 (p.21, k=0.03)", 0.05), (GYPSUM, 0.015)],
        "edit_index": 1,
        "u_max": 0.30,
    },
    2: {
        "title": "Lv.2 단열재 고르기",
        "goal": "단열재 종류와 두께를 골라 U-value ≤ 0.20 W/(m²K) 이면서 벽 총 두께 ≤ 0.40 m 를 달성하세요.",
        "editable": "type_thickness",
        "start": [(CONCRETE, 0.20), ("단열재 (일반값 p.14, k=0.04)", 0.10), (GYPSUM, 0.015)],
        "edit_index": 1,
        "u_max": 0.20,
        "thickness_max": 0.40,
    },
    3: {
        "title": "Lv.3 자유 설계",
        "goal": ("층을 추가·삭제하고 재료와 두께를 자유롭게 골라 U-value ≤ 0.15 W/(m²K), 총 두께 ≤ 0.45 m, "
                 "구조층(콘크리트 또는 벽돌) 포함, 겨울(-10 / 20 °C) 구조층 최저 온도 ≥ 0 °C 를 모두 만족하세요."),
        "editable": "free",
        "start": [(CONCRETE, 0.20), ("단열재 (일반값 p.14, k=0.04)", 0.10), (GYPSUM, 0.015)],
        "u_max": 0.15,
        "thickness_max": 0.45,
        "need_structure": True,
        "structure_min_temp": 0.0,
    },
}

# Lv.4 발견 레벨: 같은 재료, 순서만 다름
LV4_INNER = [(CONCRETE, 0.20), ("단열재 (p.21, k=0.03)", 0.10), (GYPSUM, 0.015)]   # 내단열
LV4_OUTER = [("단열재 (p.21, k=0.03)", 0.10), (CONCRETE, 0.20), (GYPSUM, 0.015)]   # 외단열
LV4_CHOICES = ["U-value 가 커진다 (열이 더 잘 샌다)", "U-value 가 작아진다 (단열이 좋아진다)", "U-value 는 그대로다"]
LV4_ANSWER = 2


def to_layers(spec: list[tuple[str, float]]) -> list[Layer]:
    return [Layer(MATERIAL_PRESETS[k]["name"], d, MATERIAL_PRESETS[k]["k"]) for k, d in spec]


def solve(spec: list[tuple[str, float]]) -> dict:
    return solve_air(to_layers(spec), T_OA, T_IA, H_TO, H_TI)


def structure_min_temp(res: dict) -> float | None:
    temps = [min(e["T_start"], e["T_end"]) for e in res["elements"]
             if e["kind"] == "layer" and e["name"] in STRUCTURAL_NAMES]
    return min(temps) if temps else None


def inner_surface_temp(res: dict) -> float:
    return next(b["T"] for b in res["boundaries"] if b["symbol"] == "T_is")


def evaluate(level: int, spec: list[tuple[str, float]]) -> dict:
    """조건별 판정. progress 는 0~1 (1 이면 통과선 도달)."""
    goal = LEVELS[level]
    res = solve(spec)
    checks = []
    u = res["U"]
    checks.append({"label": "U-value", "value": u, "target": goal["u_max"], "unit": "W/(m²K)",
                   "passed": u <= goal["u_max"] + 1e-9, "progress": min(1.0, goal["u_max"] / u),
                   "text": f"현재 U = {u:.3f}  /  목표 ≤ {goal['u_max']:.2f} W/(m²K)"})
    if "thickness_max" in goal:
        t = res["total_thickness"]
        lim = goal["thickness_max"]
        checks.append({"label": "총 두께", "value": t, "target": lim, "unit": "m",
                       "passed": t <= lim + 1e-9, "progress": min(1.0, lim / t),
                       "text": f"현재 {t:.3f} m  /  목표 ≤ {lim:.2f} m"})
    if goal.get("need_structure"):
        smin = structure_min_temp(res)
        has = smin is not None
        checks.append({"label": "구조층 포함", "value": has, "target": True, "unit": "",
                       "passed": has, "progress": 1.0 if has else 0.0,
                       "text": "콘크리트 또는 벽돌 층이 있음" if has else "콘크리트 또는 벽돌 층을 1개 이상 넣으세요"})
        if "structure_min_temp" in goal:
            lim = goal["structure_min_temp"]
            if has:
                # -10 °C(외기)에서 0 °C(목표)까지 얼마나 올라왔는지
                prog = max(0.0, min(1.0, (smin - T_OA) / (lim - T_OA)))
                text = f"겨울 구조층 최저 온도 {smin:.1f} °C  /  목표 ≥ {lim:.0f} °C"
            else:
                prog, text = 0.0, "구조층이 없어 판정할 수 없음"
            checks.append({"label": "구조층 최저 온도", "value": smin, "target": lim, "unit": "°C",
                           "passed": has and smin >= lim, "progress": prog, "text": text})
    return {"res": res, "checks": checks, "passed": all(c["passed"] for c in checks),
            "inner_surface_temp": inner_surface_temp(res)}


def hints(spec: list[tuple[str, float]]) -> dict:
    """규칙 기반 힌트: 층별 저항 비율, 1 cm 늘릴 때 U 가 가장 많이 줄어드는 층 (calc 로 다시 풀어 비교)."""
    base = solve(spec)
    shares = [{"name": e["name"], "R": e["R"], "share_pct": e["share_pct"]} for e in base["elements"]]
    best, best_drop = None, -1.0
    for i, (key, d) in enumerate(spec):
        trial = list(spec)
        trial[i] = (key, round(d + STEP, 4))
        drop = base["U"] - solve(trial)["U"]
        if drop > best_drop:
            best, best_drop = i, drop
    key = spec[best][0]
    return {"shares": shares, "best_index": best, "best_name": MATERIAL_PRESETS[key]["name"],
            "best_k": MATERIAL_PRESETS[key]["k"], "best_drop": best_drop}


def lv4_results() -> dict:
    inner, outer = solve(LV4_INNER), solve(LV4_OUTER)
    return {"inner": inner, "outer": outer,
            "inner_struct": structure_min_temp(inner), "outer_struct": structure_min_temp(outer)}


def design_summary(level: int, spec: list[tuple[str, float]], ev: dict) -> dict:
    """AI 평가용 JSON (현재 설계 + 목표 + 판정)."""
    return {
        "레벨": LEVELS[level]["title"],
        "목표": LEVELS[level]["goal"],
        "조건": {"모드": "공기온도", "h_to": H_TO, "h_ti": H_TI, "겨울 T_oa": T_OA, "T_ia": T_IA},
        "현재 설계 (실외→실내)": [{"재료": MATERIAL_PRESETS[k]["name"], "k": MATERIAL_PRESETS[k]["k"], "d [m]": d}
                            for k, d in spec],
        "판정": [{"항목": c["label"], "현재": c["text"], "통과": c["passed"]} for c in ev["checks"]],
    }

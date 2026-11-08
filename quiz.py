"""개념 점검 퀴즈 (M4): 랜덤 계산 문제 + 오개념 객관식.

계산 문제의 정답은 calc.py 가 계산한다. 조건은 재료 프리셋과 현실적인 두께 범위 안에서만 뽑는다.
"""

from __future__ import annotations

import random

from calc import Layer, solve_surface
from materials import MATERIAL_PRESETS

TOLERANCE = 0.02     # ±2 %
TEMP_ABS_FLOOR = 0.1  # 온도는 0 °C 근처에서 2 %가 너무 빡빡해지므로 최소 ±0.1 °C 허용
DEMO_SEED = 2041      # 시연 모드 문제의 seed (과목 코드 ARC2041)

# 시연 모드: 4번(경계 온도) 문제를 항상 이 조건으로. 겨울철, 구조층|단열재 경계 T_1 을 묻는다.
# 그래프에서 이 경계 바로 뒤 단열재층의 큰 온도 강하가 잘 보인다.
DEMO_T_PROBLEM = {
    "layers": [("콘크리트 (p.21, k=1.5)", 0.20), ("단열재 (p.21, k=0.03)", 0.10), ("석고보드 (대표값, k=0.18)", 0.015)],
    "T_os": -5.0, "T_is": 20.0, "boundary": 1,
}

# 벽 구성 (실외 → 실내): 구조층 | 단열층 | 마감층. (프리셋 키, 최소 두께, 최대 두께, 간격) [m]
STRUCTURE = [("콘크리트 (예제 p.29, k=1.0)", 0.15, 0.30, 0.01),
             ("콘크리트 (p.21, k=1.5)", 0.15, 0.30, 0.01),
             ("벽돌 (대표값, k=0.6)", 0.09, 0.19, 0.01)]
INSULATION = [("단열재 (예제 p.29, k=0.02)", 0.03, 0.10, 0.01),
              ("단열재 (p.21, k=0.03)", 0.05, 0.15, 0.01),
              ("단열재 (일반값 p.14, k=0.04)", 0.05, 0.15, 0.01)]
FINISH = [("목재 (예제 p.29, k=0.1)", 0.02, 0.05, 0.01),
          ("석고보드 (대표값, k=0.18)", 0.01, 0.025, 0.005),
          ("합판 (대표값, k=0.15)", 0.01, 0.02, 0.005),
          ("시멘트 모르타르 (대표값, k=1.4)", 0.01, 0.03, 0.01)]

NUMERIC_KINDS = ["R", "R_t", "q_t", "T"]
KIND_TITLES = {"R": "한 층의 열저항 R", "R_t": "총 열저항 R_t", "q_t": "열류의 크기 |q_t|", "T": "경계 온도"}


def _pick_thickness(rng: random.Random, lo: float, hi: float, step: float) -> float:
    n = round((hi - lo) / step)
    return round(lo + step * rng.randint(0, n), 4)


def make_numeric_problem(kind: str, seed: int, fixed: dict | None = None) -> dict:
    """kind: R | R_t | q_t | T. 같은 seed 면 항상 같은 문제. fixed 를 주면 그 조건을 그대로 쓴다 (시연 모드)."""
    rng = random.Random(seed)
    if fixed:
        layers, T_os, T_is = list(fixed["layers"]), fixed["T_os"], fixed["T_is"]
    else:
        groups = [STRUCTURE, INSULATION] + ([FINISH] if rng.random() < 0.7 or kind == "T" else [])
        layers = []
        for group in groups:
            key, lo, hi, step = rng.choice(group)
            layers.append((key, _pick_thickness(rng, lo, hi, step)))
        if rng.random() < 0.5:   # 겨울: 실내가 따뜻함
            T_os, T_is = float(rng.randint(-10, 5)), float(rng.randint(15, 20))
        else:                    # 여름: 실외가 뜨거움
            T_os, T_is = float(rng.randint(32, 45)), float(rng.randint(24, 27))

    calc_layers = [Layer(MATERIAL_PRESETS[k]["name"], d, MATERIAL_PRESETS[k]["k"]) for k, d in layers]
    res = solve_surface(calc_layers, T_os, T_is)
    names = [l.name for l in calc_layers]
    R = [e["R"] for e in res["elements"]]
    sum_expr = " + ".join(f"{r:.3f}" for r in R)

    steps = [rf"$R_{{{i + 1}}} = d/k = {l.d:g}/{l.k:g} = {r:.3f}$ m²K/W ({l.name})"
             for i, (l, r) in enumerate(zip(calc_layers, R))]
    if kind == "R":
        j = rng.randrange(len(layers))
        l = calc_layers[j]
        question = f"{j + 1}번째 층({l.name}, d = {l.d:g} m, k = {l.k:g} W/(m·K))의 열저항 R 을 구하세요."
        answer, unit = R[j], "m²K/W"
        steps = [steps[j]]
        target = f"{j + 1}번째 층"
    elif kind == "R_t":
        question = "이 벽의 총 열저항 R_t 를 구하세요 (표면저항 제외, 재료층만)."
        answer, unit = res["R_t"], "m²K/W"
        steps += [rf"$R_t = {sum_expr} = {res['R_t']:.3f}$ m²K/W  (직렬 → 저항의 합, 02강 p.20)"]
        target = "R_t"
    elif kind == "q_t":
        question = (f"외표면 온도 T_os = {T_os:g} °C, 내표면 온도 T_is = {T_is:g} °C 일 때 "
                    "벽을 지나는 열류의 크기 |q_t| 를 구하세요.")
        answer, unit = res["q_abs"], "W/m²"
        steps += [rf"$R_t = {sum_expr} = {res['R_t']:.3f}$ m²K/W",
                  rf"$|q_t| = |T_{{os}} - T_{{is}}| / R_t = |{T_os:g} - ({T_is:g})| / {res['R_t']:.3f}"
                  rf" = {res['q_abs']:.2f}$ W/m²  — 방향: {_flow_ko(res)} (02강 p.26)"]
        target = "|q_t|"
    else:  # T: 내부 경계 하나
        j = (fixed or {}).get("boundary") or rng.randrange(1, len(layers))  # 경계 T_j (j번째|j+1번째 층 사이)
        b = res["boundaries"][j]
        question = (f"외표면 온도 T_os = {T_os:g} °C, 내표면 온도 T_is = {T_is:g} °C 일 때 "
                    f"{names[j - 1]}|{names[j]} 경계 온도 {b['symbol']} 를 구하세요.")
        answer, unit = b["T"], "°C"
        R_cum = sum(R[:j])
        steps += [rf"$R_t = {sum_expr} = {res['R_t']:.3f}$ m²K/W",
                  rf"$q_t = (T_{{os}} - T_{{is}}) / R_t = ({T_os:g} - ({T_is:g})) / {res['R_t']:.3f}"
                  rf" = {res['q_t']:+.2f}$ W/m² ({_flow_ko(res)})",
                  rf"${_tex(b['symbol'])} = T_{{os}} - q_t \times ({' + '.join(f'R_{i + 1}' for i in range(j))})"
                  rf" = {T_os:g} - ({res['q_t']:+.2f})({R_cum:.3f}) = {b['T']:.2f}$ °C  (02강 p.27–28)"]
        target = b["symbol"]
    return {"kind": kind, "seed": seed, "title": KIND_TITLES[kind], "layers": layers,
            "T_os": T_os, "T_is": T_is, "question": question, "answer": answer, "unit": unit,
            "steps": steps, "target": target, "direction": _flow_ko(res), "demo": bool(fixed)}


def _flow_ko(res: dict) -> str:
    return {"외부 → 내부": "실외 → 실내", "내부 → 외부": "실내 → 실외"}.get(res["direction"], "열 흐름 없음")


def _tex(symbol: str) -> str:
    a, b = symbol.split("_", 1)
    return f"{a}_{{{b}}}"


def make_round(base_seed: int, demo: bool) -> list[dict]:
    """계산 문제 4개 (R → R_t → q_t → 경계 온도). demo 면 4번(경계 온도)이 항상 DEMO_T_PROBLEM."""
    seeds = [base_seed + i * 7919 for i in range(len(NUMERIC_KINDS))]
    problems = [make_numeric_problem(kind, s) for kind, s in zip(NUMERIC_KINDS, seeds)]
    if demo:
        problems[3] = make_numeric_problem("T", DEMO_SEED, fixed=DEMO_T_PROBLEM)
    return problems


def is_correct(value: float | None, problem: dict) -> bool:
    if value is None:
        return False
    tol = TOLERANCE * abs(problem["answer"])
    if problem["unit"] == "°C":
        tol = max(tol, TEMP_ABS_FLOOR)
    return abs(value - problem["answer"]) <= tol


# ---------------------------------------------------------------- 개념형 객관식
# why: 보기별 "왜 틀렸는지" (정답 보기는 왜 맞는지)
CONCEPT_QUESTIONS = [
    {
        "id": "k_vs_K",
        "topic": "열전도율 k vs 열컨덕턴스 K",
        "question": "열전도율 k 와 열컨덕턴스 K 에 대한 설명으로 옳은 것은?",
        "options": [
            "k 는 두께를 반영한 값이고, 단위는 W/(m²K) 이다.",
            "k 는 재료 고유의 물성 [W/(m·K)] 이고, K = k/d = 1/R 은 두께를 반영한 값 [W/(m²K)] 이다.",
            "같은 재료라면 두께를 두 배로 늘려도 K 는 변하지 않는다.",
            "K 가 클수록 단열 성능이 좋다.",
        ],
        "answer": 1,
        "why": [
            "두께를 반영한 값은 K 입니다. k 는 두께와 무관한 재료 고유값이고 단위는 W/(m·K) 입니다.",
            "k 는 재료 자체의 성질, K 는 '그 두께의 층'이 열을 통과시키는 능력입니다. K = k/d 이므로 역수가 R = d/k 입니다.",
            "변하지 않는 것은 k 입니다. K = k/d 이므로 두께가 두 배면 K 는 절반이 됩니다 (R 은 두 배).",
            "K 가 크다는 것은 열이 잘 통과한다는 뜻이라 단열에는 불리합니다. 단열 성능은 R(= 1/K)이 클수록 좋습니다.",
        ],
        "source": "02강 p.14, p.18",
    },
    {
        "id": "series",
        "topic": "직렬 = 저항의 합",
        "question": "콘크리트층(R = 0.08 m²K/W)과 단열재층(R = 2.0 m²K/W)을 겹쳐(직렬) 만든 벽의 총 열저항은?",
        "options": ["0.077 m²K/W", "2.0 m²K/W", "2.08 m²K/W", "0.16 m²K/W"],
        "answer": 2,
        "why": [
            "1/(1/0.08 + 1/2.0) 은 병렬 공식입니다. 층을 겹친 벽은 열이 모든 층을 차례로 지나므로 직렬입니다.",
            "가장 큰 저항만 고른 값입니다. 직렬에서는 작은 저항도 모두 더해집니다.",
            "직렬로 연결된 저항은 더합니다: R_t = 0.08 + 2.0 = 2.08 m²K/W. 전기회로의 직렬 저항과 같습니다.",
            "콘크리트 저항만 두 번 더한 값입니다. 단열재 2.0 이 빠졌습니다.",
        ],
        "source": "02강 p.20–21",
    },
    {
        "id": "parallel",
        "topic": "병렬 = 컨덕턴스의 합",
        "question": "단열재(R_i)와 콘크리트(R_c)가 같은 두께로 나란히(병렬) 놓인 구간의 총 열저항 R_t 를 구하는 식은?",
        "options": [
            "R_t = R_i + R_c",
            "1/R_t = 1/R_i + 1/R_c",
            "R_t = (R_i + R_c) / 2",
            "R_t = max(R_i, R_c)",
        ],
        "answer": 1,
        "why": [
            "저항을 더하는 것은 직렬입니다. 병렬에서는 열이 두 경로로 나뉘어 동시에 흐릅니다.",
            "병렬은 각 경로의 열류가 더해지므로 컨덕턴스(1/R)를 더합니다. 그래서 R_t 는 작은 쪽 저항(콘크리트)보다도 작아집니다.",
            "단순 평균이 아닙니다. 열은 저항이 작은 경로로 더 많이 빠져나가므로 작은 저항 쪽이 결과를 지배합니다.",
            "병렬에서 큰 저항이 전체를 결정하지 않습니다. 오히려 작은 저항(콘크리트) 쪽으로 열이 새어 나갑니다 — 열교의 원리입니다.",
        ],
        "source": "02강 p.25",
    },
    {
        "id": "steady_flux",
        "topic": "정상상태: 모든 층의 열류가 같다",
        "question": "정상상태의 3층 벽(콘크리트 | 단열재 | 목재)에서 각 층을 지나는 열류 q 에 대한 설명으로 옳은 것은?",
        "options": [
            "단열재층에서 열류가 가장 작다.",
            "바깥쪽 층일수록 열류가 크다.",
            "모든 층에서 열류가 같다.",
            "열류는 각 층의 두께에 비례한다.",
        ],
        "answer": 2,
        "why": [
            "단열재층에서 큰 것은 열류가 아니라 '온도 강하'입니다 (ΔT = q_t × R). 열류 자체는 모든 층에서 같습니다.",
            "정상상태에서는 어느 층에도 열이 쌓이거나 빠지지 않으므로 바깥층·안쪽층의 열류가 같습니다.",
            "정상상태에서는 열이 중간에 쌓이지 않으므로 같은 q_t 가 모든 층을 관통합니다. 그래서 내부 경계 온도를 층별로 계산할 수 있습니다.",
            "두께에 비례하는 것은 각 층의 저항(R = d/k)과 온도 강하입니다. 열류는 층마다 같습니다.",
        ],
        "source": "02강 p.26",
    },
    {
        "id": "u_value",
        "topic": "U-value 의 구성",
        "question": "U-value(열관류율)에 대한 설명으로 옳은 것은?",
        "options": [
            "재료층의 전도만 고려한 값으로, U = 1 / Σ(d/k) 이다.",
            "U-value 가 클수록 단열 성능이 우수하다.",
            "U-value 의 단위는 m²K/W 이다.",
            "전도·대류·복사를 모두 포함하며, 역수가 총 열저항 R_t = 1/h_to + Σ d/k + 1/h_ti 이다.",
        ],
        "answer": 3,
        "why": [
            "Σd/k 의 역수는 표면→표면 컨덕턴스 K_t 입니다. U-value 는 실내·외 표면저항(1/h_to, 1/h_ti)까지 포함해야 합니다.",
            "U 는 열이 통과하는 정도이므로 작을수록 단열이 좋습니다.",
            "m²K/W 는 열저항 R 의 단위입니다. U-value 의 단위는 W/(m²K) 입니다.",
            "U-value 는 공기→표면(대류+복사, h_t)과 재료층(전도)을 모두 합친 총 열저항의 역수입니다.",
        ],
        "source": "02강 p.56–57",
    },
    {
        "id": "thermal_bridge",
        "topic": "열교",
        "question": ("벽 단열재를 두 배로 두껍게 했지만, 철근콘크리트 발코니 슬래브가 단열층을 그대로 관통하고 있다. "
                     "가장 적절한 판단은?"),
        "options": [
            "단열재가 두 배이므로 벽 전체 열손실도 거의 절반으로 줄어든다.",
            "열교는 여름에만 문제가 되므로 겨울 난방에는 영향이 없다.",
            "열교 부위는 온도가 높아지므로 결로 걱정은 줄어든다.",
            "관통한 슬래브가 열교가 되어 열이 그쪽으로 빠지므로, 두꺼운 단열의 효과가 크게 줄어든다.",
        ],
        "answer": 3,
        "why": [
            "열은 저항이 작은 경로로 빠집니다. 슬래브가 단열층을 관통하면 그 경로가 열교가 되어 단열 강화 효과가 기대만큼 나오지 않습니다.",
            "열교는 계절과 관계없이 생깁니다. 특히 열부하가 작은 패시브 건물에서 겨울 열손실을 키웁니다.",
            "반대입니다. 겨울에 열교 부위의 실내 표면 온도가 낮아져 결로와 곰팡이가 생기기 쉽습니다 (02강 p.70).",
            "열교가 있으면 두꺼운 단열은 무의미해질 수 있습니다. 해결책은 슬래브 돌출부 단열이나 단열 특수 부재(예: Schöck Isokorb)입니다 (02강 p.73).",
        ],
        "source": "02강 p.68, p.70, p.73",
    },
    {
        "id": "stefan_boltzmann",
        "topic": "스테판-볼츠만 식의 온도는 K",
        "question": "표면 온도가 20 °C 인 흑체의 방사 열류를 q = σT⁴ 로 계산할 때, T 에 넣어야 하는 값은?",
        "options": ["20", "20 을 넣고 결과에 273.15 를 더한다", "293.15", "−253.15"],
        "answer": 2,
        "why": [
            "섭씨를 그대로 넣으면 q = 5.67×10⁻⁸ × 20⁴ ≈ 0.009 W/m² 로 말이 안 되는 값이 나옵니다. σ 의 단위가 W/(m²K⁴) 이므로 절대온도가 필요합니다.",
            "4제곱한 뒤에 273.15 를 더해도 의미가 없습니다. 온도를 먼저 K 로 바꾼 뒤 4제곱해야 합니다.",
            "T = 20 + 273.15 = 293.15 K 를 넣습니다. q ≈ 5.67×10⁻⁸ × 293.15⁴ ≈ 419 W/m² 입니다.",
            "273.15 를 빼는 방향이 반대입니다. K = °C + 273.15 입니다.",
        ],
        "source": "02강 p.52 (핵심 공식 D)",
    },
    {
        "id": "gradient",
        "topic": "온도 기울기가 급한 층",
        "question": "직렬 다층벽의 단면 온도 그래프에서 온도 기울기(ΔT/d)가 가장 급한 층은?",
        "options": [
            "가장 두꺼운 층",
            "열전도율 k 가 가장 작은 층",
            "가장 바깥쪽 층",
            "열전도율 k 가 가장 큰 층",
        ],
        "answer": 1,
        "why": [
            "두께가 두꺼우면 온도 강하량은 커질 수 있지만, 단위 두께당 기울기(ΔT/d = q_t/k)는 두께와 무관합니다.",
            "기울기 ΔT/d = q_t/k 이고 q_t 는 모든 층이 같으므로, k 가 작은 층(단열재)에서 기울기가 가장 급합니다.",
            "위치와는 관계없습니다. 기울기는 그 층의 k 로 결정됩니다.",
            "k 가 크면 열이 잘 통해서 같은 열류에도 온도가 조금만 떨어집니다. 기울기가 가장 완만합니다.",
        ],
        "source": "02강 p.20",
    },
]

"""정상상태 다층벽 열전달 계산 엔진 (건축환경조절 02강).

부호 규약 (정리본 2.8, 2.11, 2.14절):
  - x = 0 은 외측(외표면 또는 외기), 실내 방향이 +x.
  - q_t = -K (T_내 - T_외) = (T_외 - T_내) / R_t
    q_t > 0 : 외부 -> 내부로 열이 흐름 (여름 등)
    q_t < 0 : 내부 -> 외부로 열이 흐름 (겨울 등)
  - 경계 온도: T_경계 = T_외 - q_t * (지금까지 누적된 R)   <- 부호 있는 q_t 를 사용
  - 층별 온도 강하: dT_j = q_t * R_j  (외측 -> 내측으로 갈 때 떨어지는 양, 겨울엔 음수)

모든 수치 계산은 이 모듈이 결정적으로 수행한다. LLM 은 결과를 설명만 한다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# 대표값 (정리본에는 h_to, h_ti 기본값이 없음 -> 일반적으로 쓰이는 값, UI 에서 "대표값" 표시)
DEFAULT_H_TO = 25.0  # 외부 총 열전달계수 [W/(m²K)]
DEFAULT_H_TI = 7.7   # 내부 총 열전달계수 [W/(m²K)]


@dataclass
class Layer:
    name: str
    d: float  # 두께 [m]
    k: float  # 열전도율 [W/(m·K)]

    @property
    def R(self) -> float:
        return self.d / self.k


def _check_positive(value: float, label: str) -> None:
    if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{label} 값은 0보다 큰 숫자여야 합니다 (입력값: {value!r}).")


def _check_finite(value: float, label: str) -> None:
    if not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{label} 값이 올바른 숫자가 아닙니다 (입력값: {value!r}).")


def _validate_layers(layers: list[Layer]) -> None:
    if not layers:
        raise ValueError("레이어가 최소 1개 이상 필요합니다.")
    for i, layer in enumerate(layers, start=1):
        _check_positive(layer.d, f"{i}번째 층({layer.name}) 두께 d")
        _check_positive(layer.k, f"{i}번째 층({layer.name}) 열전도율 k")


def _direction(q_t: float) -> str:
    if abs(q_t) < 1e-12:
        return "없음 (온도차 0)"
    return "외부 → 내부" if q_t > 0 else "내부 → 외부"


def _solve(elements: list[dict], T_out: float, T_in: float,
           out_symbol: str, in_symbol: str, inner_end_symbols: tuple[str, str] | None) -> dict:
    """elements: 외측 -> 내측 순서. 각 요소 {name, kind, R, d, k, h}.

    inner_end_symbols: 공기온도 모드에서 첫/마지막 '재료 경계'의 기호 (T_os, T_is).
    """
    R_t = sum(e["R"] for e in elements)
    q_t = (T_out - T_in) / R_t  # = -K (T_in - T_out)

    # 경계 온도: 요소 수 + 1 개
    boundaries = []
    x = 0.0
    R_cum = 0.0
    T = T_out
    end_labels = ("외표면", "내표면") if inner_end_symbols is None else ("외기", "실내 공기")
    boundaries.append({"symbol": out_symbol, "label": end_labels[0], "x": 0.0, "T": T_out})

    n_layers = sum(1 for e in elements if e["kind"] == "layer")
    layer_idx = 0
    interior_no = 0
    result_elements = []
    for idx, e in enumerate(elements):
        x_start, T_start = x, T
        R_cum += e["R"]
        T = T_out - q_t * R_cum
        if e["kind"] == "layer":
            x += e["d"]
            layer_idx += 1
        dT = q_t * e["R"]
        result_elements.append({
            **e,
            "x_start": x_start, "x_end": x,
            "T_start": T_start, "T_end": T,
            "dT": dT,
            "share_pct": e["R"] / R_t * 100.0,  # 저항 비율 = 온도 강하 비율
        })

        if idx == len(elements) - 1:
            continue  # 마지막 경계는 아래에서 내측 끝으로 추가
        nxt = elements[idx + 1]
        if e["kind"] == "surface":  # 외부 표면저항 다음 -> 외표면
            symbol, label = inner_end_symbols[0], "외표면"
        elif nxt["kind"] == "surface":  # 마지막 재료층 다음 -> 내표면
            symbol, label = inner_end_symbols[1], "내표면"
        else:
            interior_no += 1
            symbol, label = f"T_{interior_no}", f"{e['name']}|{nxt['name']}"
        boundaries.append({"symbol": symbol, "label": label, "x": x, "T": T})

    boundaries.append({"symbol": in_symbol, "label": end_labels[1], "x": x, "T": T_in})

    return {
        "R_t": R_t,
        "K_t": 1.0 / R_t,
        "q_t": q_t,
        "q_abs": abs(q_t),
        "direction": _direction(q_t),
        "total_thickness": x,
        "n_layers": n_layers,
        "elements": result_elements,
        "boundaries": boundaries,
    }


def solve_surface(layers: list[Layer], T_os: float, T_is: float) -> dict:
    """(a) 표면온도 모드 (02강 p.26~30): R_t = Σ d/k, q_t = -K(T_is - T_os)."""
    _validate_layers(layers)
    _check_finite(T_os, "T_os")
    _check_finite(T_is, "T_is")
    elements = [{"name": l.name, "kind": "layer", "d": l.d, "k": l.k, "h": None, "R": l.R}
                for l in layers]
    res = _solve(elements, T_os, T_is, "T_os", "T_is", None)
    res.update({"mode": "surface", "T_out": T_os, "T_in": T_is, "U": None})
    return res


def solve_air(layers: list[Layer], T_oa: float, T_ia: float,
              h_to: float = DEFAULT_H_TO, h_ti: float = DEFAULT_H_TI) -> dict:
    """(b) 공기온도 모드 (02강 p.57~59): R_t = 1/h_to + Σ d/k + 1/h_ti, U = 1/R_t."""
    _validate_layers(layers)
    _check_finite(T_oa, "T_oa")
    _check_finite(T_ia, "T_ia")
    _check_positive(h_to, "h_to")
    _check_positive(h_ti, "h_ti")
    elements = (
        [{"name": "외부 표면저항 R_to", "kind": "surface", "d": 0.0, "k": None, "h": h_to, "R": 1.0 / h_to}]
        + [{"name": l.name, "kind": "layer", "d": l.d, "k": l.k, "h": None, "R": l.R} for l in layers]
        + [{"name": "내부 표면저항 R_ti", "kind": "surface", "d": 0.0, "k": None, "h": h_ti, "R": 1.0 / h_ti}]
    )
    res = _solve(elements, T_oa, T_ia, "T_oa", "T_ia", ("T_os", "T_is"))
    res.update({"mode": "air", "T_out": T_oa, "T_in": T_ia, "U": res["K_t"],
                "h_to": h_to, "h_ti": h_ti})
    return res


def parallel_resistance(resistances: list[float]) -> float:
    """병렬 구성 (02강 p.25): 1/R_t = 1/R_1 + 1/R_2 + ...

    슬라이드 식 그대로, 각 경로를 같은 단위 면적으로 보고 컨덕턴스를 더한다 (면적 가중 없음).
    """
    if not resistances:
        raise ValueError("병렬 저항이 최소 1개 이상 필요합니다.")
    for i, R in enumerate(resistances, start=1):
        _check_positive(R, f"{i}번째 저항 R")
    return 1.0 / sum(1.0 / R for R in resistances)

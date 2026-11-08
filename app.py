"""다층벽 열전달 AI 튜터 (건축환경조절 ARC2041, 02강).

실행: streamlit run app.py
계산은 calc.py 가 수행하고, 이 파일은 화면만 담당한다.
"""

import json
import random
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

from calc import DEFAULT_H_TI, DEFAULT_H_TO, Layer, solve_air, solve_surface
from challenge import (H_TI as CH_H_TI, H_TO as CH_H_TO, INSULATIONS, LEVELS, LV3_PRESETS, LV4_ANSWER, LV4_CHOICES,
                       T_IA as CH_T_IA, T_OA as CH_T_OA, design_summary, evaluate, hints, lv4_results)
from materials import CUSTOM, MATERIAL_PRESETS, TEXTBOOK_EXAMPLE, tutor_reference
from quiz import CONCEPT_QUESTIONS, is_correct, make_round
from viz3d import MODE_MATERIAL, MODE_TEMPERATURE, MODES, NOTE, wall_figure
from tutor import TutorError, ask, calc_context, load_config

st.set_page_config(page_title="다층벽 열전달 AI 튜터", page_icon="🧱", layout="wide")

SURFACE_MODE = "표면온도 모드 (T_os, T_is)"
AIR_MODE = "공기온도 모드 (T_oa, T_ia, U-value)"
LAYER_COLORS = ["#d9d9d9", "#ffe08a", "#d9b38c", "#f4a6a6", "#b5d99c", "#a8c8f0", "#d7b5f0", "#f7c59f"]
D_MIN, D_MAX = 0.001, 1.0

ss = st.session_state


# ---------------------------------------------------------------- 상태 관리
def _add_layer(preset_key: str, d: float) -> None:
    lid = ss.next_id
    ss.next_id += 1
    p = MATERIAL_PRESETS[preset_key]
    ss.layers[lid] = {"preset": preset_key, "name": p["name"], "d": d, "k": p["k"]}
    ss.layer_ids.append(lid)


def load_condition(layers: list[tuple[str, float]], T_os: float, T_is: float) -> None:
    """표면온도 모드로 레이어·온도를 통째로 바꾼다 (정리본 예제, 퀴즈 조건 열기)."""
    ss.layers, ss.layer_ids = {}, []
    for preset_key, d in layers:
        _add_layer(preset_key, d)
    ss.mode = SURFACE_MODE
    ss.cond["T_os"], ss.cond["T_is"] = T_os, T_is
    ss.cond_ver += 1


def load_example() -> None:
    load_condition(TEXTBOOK_EXAMPLE["layers"], TEXTBOOK_EXAMPLE["T_os"], TEXTBOOK_EXAMPLE["T_is"])


def set_season(season: str) -> None:
    out_T, in_T = (-5.0, 20.0) if season == "winter" else (33.0, 26.0)
    if ss.mode == SURFACE_MODE:
        ss.cond["T_os"], ss.cond["T_is"] = out_T, in_T
    else:
        ss.cond["T_oa"], ss.cond["T_ia"] = out_T, in_T
    ss.cond_ver += 1


def on_preset(lid: int) -> None:
    key = ss[f"preset_{lid}"]
    layer = ss.layers[lid]
    layer["preset"] = key
    if key != CUSTOM:
        layer["name"] = MATERIAL_PRESETS[key]["name"]
        layer["k"] = MATERIAL_PRESETS[key]["k"]
        ss[f"k_{lid}"] = layer["k"]


def on_d(lid: int, source: str) -> None:
    d = ss[f"d_{source}_{lid}"]
    ss.layers[lid]["d"] = d
    other = "num" if source == "slider" else "slider"
    ss[f"d_{other}_{lid}"] = d


def on_field(lid: int, field: str) -> None:
    ss.layers[lid][field] = ss[f"{field}_{lid}"]


def move_layer(lid: int, step: int) -> None:
    i = ss.layer_ids.index(lid)
    j = i + step
    if 0 <= j < len(ss.layer_ids):
        ss.layer_ids[i], ss.layer_ids[j] = ss.layer_ids[j], ss.layer_ids[i]


def delete_layer(lid: int) -> None:
    ss.layer_ids.remove(lid)
    ss.layers.pop(lid, None)


if "layers" not in ss:
    # 조건값 원본. 위젯 키는 cond_ver 를 붙여 버튼으로 값을 바꿀 때 새 위젯으로 다시 그린다
    # (위젯이 숨겨졌다 다시 나타날 때 화면 값과 상태가 어긋나는 문제 방지)
    ss.cond = {"T_os": 40.0, "T_is": 10.0, "T_oa": -5.0, "T_ia": 20.0,
               "h_to": DEFAULT_H_TO, "h_ti": DEFAULT_H_TI}
    ss.cond_ver = 0
    ss.next_id = 0
    ss.layers, ss.layer_ids = {}, []
    ss.mode = SURFACE_MODE
    load_example()


def cond_input(label: str, name: str, **kwargs) -> None:
    ss.cond[name] = st.number_input(label, value=float(ss.cond[name]),
                                    key=f"w_{name}_{ss.cond_ver}", **kwargs)


# ---------------------------------------------------------------- 표시 도우미
def tex(symbol: str) -> str:
    """'T_os' -> 'T_{os}'"""
    if "_" not in symbol:
        return symbol
    a, b = symbol.split("_", 1)
    return f"{a}_{{{b}}}"


def num(v: float, digits: int = 2) -> str:
    """LaTeX 대입식용 숫자: 음수는 괄호."""
    s = f"{v:.{digits}f}"
    return f"({s})" if v < 0 else s


def flow_text(res: dict) -> str:
    if res["q_abs"] < 1e-12:
        return "열 흐름 없음"
    return "열 흐름: 실외 → 실내" if res["q_t"] > 0 else "열 흐름: 실내 → 실외"


# ---------------------------------------------------------------- 그래프
def build_figure(res: dict) -> go.Figure:
    fig = go.Figure()
    L = res["total_thickness"]
    air = res["mode"] == "air"
    a = 0.12 * L if air else 0.0  # 공기 구간 표시 폭 (실제 두께 아님)

    layers = [e for e in res["elements"] if e["kind"] == "layer"]
    for i, e in enumerate(layers):
        fig.add_vrect(x0=e["x_start"], x1=e["x_end"], fillcolor=LAYER_COLORS[i % len(LAYER_COLORS)],
                      opacity=0.55, line_width=0.5, layer="below")
        fig.add_annotation(x=(e["x_start"] + e["x_end"]) / 2, y=0, yref="paper", yanchor="bottom",
                           text=f"{e['name']}<br>R={e['R']:.3f}", showarrow=False, font=dict(size=11))

    b = res["boundaries"]
    if air:
        for x0, x1 in ((-a, 0), (L, L + a)):
            fig.add_vrect(x0=x0, x1=x1, fillcolor="#e8f1fb", opacity=0.6, line_width=0, layer="below")
        # 외기 -> 외표면, 내표면 -> 실내공기 (표면저항 구간)
        fig.add_trace(go.Scatter(x=[-a, 0], y=[b[0]["T"], b[1]["T"]], mode="lines+markers",
                                 line=dict(color="#4a90d9", dash="dot", width=2), name="표면저항 구간"))
        fig.add_trace(go.Scatter(x=[L, L + a], y=[b[-2]["T"], b[-1]["T"]], mode="lines+markers",
                                 line=dict(color="#4a90d9", dash="dot", width=2), showlegend=False))
        wall_pts = b[1:-1]
        for x_air, bt_air, bt_wall, name in ((-a, b[0], b[1], "외기"), (L + a, b[-1], b[-2], "실내 공기")):
            fig.add_annotation(x=x_air, y=bt_air["T"], text=f"{tex_plain(bt_air['symbol'])}<br>{bt_air['T']:.1f}°C",
                               showarrow=False, yshift=18, font=dict(color="#2a6ab0"))
            jump = abs(bt_wall["T"] - bt_air["T"])
            fig.add_annotation(x=(x_air + (0 if x_air < 0 else L)) / 2, y=(bt_air["T"] + bt_wall["T"]) / 2,
                               text=f"표면저항<br>ΔT {jump:.2f}°C", showarrow=False, xshift=0, yshift=-22,
                               font=dict(size=10, color="#2a6ab0"))
    else:
        wall_pts = b

    fig.add_trace(go.Scatter(
        x=[p["x"] for p in wall_pts], y=[p["T"] for p in wall_pts], mode="lines+markers+text",
        text=[f"{tex_plain(p['symbol'])} {p['T']:.1f}°C" for p in wall_pts], textposition=["top right"] + ["top center"] * (len(wall_pts) - 2) + ["top left"],
        line=dict(color="#c0392b", width=3), marker=dict(size=9), name="벽체 내부 온도"))

    temps = [p["T"] for p in b]
    lo, hi = min(temps), max(temps)
    span = max(hi - lo, 1.0)
    y_top = hi + 0.35 * span
    fig.update_yaxes(range=[lo - 0.25 * span, hi + 0.5 * span], title="온도 [°C]")
    fig.update_xaxes(range=[-a - 0.04 * L, L + a + 0.04 * L], title="위치 x [m]  (0 = 외측)")

    # 열 흐름 화살표 (고온측 -> 저온측)
    if res["q_abs"] > 1e-12:
        x_hot, x_cold = (-a, L + a) if res["q_t"] > 0 else (L + a, -a)
        fig.add_annotation(x=x_cold, y=y_top, ax=x_hot, ay=y_top, xref="x", yref="y", axref="x", ayref="y",
                           showarrow=True, arrowhead=3, arrowsize=1.6, arrowwidth=3, arrowcolor="#e67e22", text="")
    fig.update_layout(title=dict(text=f"<b>{flow_text(res)}</b>  (|q_t| = {res['q_abs']:.2f} W/m²)",
                                 x=0.5, xanchor="center", font=dict(size=15, color="#d35400")))
    fig.add_annotation(x=0, y=1, xref="paper", yref="paper", text="◀ 실외 측", showarrow=False,
                       xanchor="left", yanchor="bottom", font=dict(size=12))
    fig.add_annotation(x=1, y=1, xref="paper", yref="paper", text="실내 측 ▶", showarrow=False,
                       xanchor="right", yanchor="bottom", font=dict(size=12))
    fig.update_layout(height=480, margin=dict(l=10, r=10, t=70, b=10),
                      legend=dict(orientation="h", y=-0.18), plot_bgcolor="white")
    return fig


def tex_plain(symbol: str) -> str:
    return symbol  # 그래프 라벨은 'T_os' 그대로 (Plotly 텍스트)


# ---------------------------------------------------------------- 풀이·인사이트
def circuit_text(res: dict) -> str:
    b = res["boundaries"]
    parts = [f"{b[0]['symbol']}({b[0]['T']:.1f}°C)"]
    li = 0
    for i, e in enumerate(res["elements"]):
        if e["kind"] == "surface":
            label = "R_to" if "외부" in e["name"] else "R_ti"
        else:
            li += 1
            label = f"R_{li} {e['name']}"
        parts.append(f"─[ {label} = {e['R']:.3f} ]─")
        parts.append(f"{b[i + 1]['symbol']}({b[i + 1]['T']:.1f}°C)")
    arrow = {"열 흐름: 실외 → 실내": "  ──────▶  열 흐름 (실외 → 실내)",
             "열 흐름: 실내 → 실외": "  ◀──────  열 흐름 (실내 → 실외)"}.get(flow_text(res), "  (열 흐름 없음)")
    return " ".join(parts) + "\n" + arrow


def show_steps(res: dict) -> None:
    air = res["mode"] == "air"
    out_s, in_s = ("T_{oa}", "T_{ia}") if air else ("T_{os}", "T_{is}")

    st.markdown("**① 각 층의 열저항** $R = d/k$ (02강 p.18)" + ("  ·  표면저항 $R = 1/h$ (02강 p.57)" if air else ""))
    li = 0
    for e in res["elements"]:
        if e["kind"] == "surface":
            sym = "R_{to}" if "외부" in e["name"] else "R_{ti}"
            hsym = "h_{to}" if "외부" in e["name"] else "h_{ti}"
            st.latex(rf"{sym} = \frac{{1}}{{{hsym}}} = \frac{{1}}{{{e['h']:g}}} = {e['R']:.3f}\ \mathrm{{m^2K/W}}")
        else:
            li += 1
            st.caption(f"{li}층: {e['name']}")
            st.latex(rf"R_{{{li}}} = \frac{{d_{{{li}}}}}{{k_{{{li}}}}} = \frac{{{e['d']:g}}}{{{e['k']:g}}}"
                     rf" = {e['R']:.3f}\ \mathrm{{m^2K/W}}")

    syms, vals = [], []
    li = 0
    for e in res["elements"]:
        if e["kind"] == "surface":
            syms.append("R_{to}" if "외부" in e["name"] else "R_{ti}")
        else:
            li += 1
            syms.append(f"R_{{{li}}}")
        vals.append(f"{e['R']:.3f}")
    st.markdown("**② 총 열저항 (직렬 → 저항의 합)** (02강 p.20" + (", p.57)" if air else ")"))
    st.latex(rf"R_t = {' + '.join(syms)} = {' + '.join(vals)} = {res['R_t']:.3f}\ \mathrm{{m^2K/W}}")
    if air:
        st.latex(rf"U = \frac{{1}}{{R_t}} = \frac{{1}}{{{res['R_t']:.3f}}} = {res['U']:.3f}\ \mathrm{{W/(m^2K)}}")
    else:
        st.latex(rf"K_t = \frac{{1}}{{R_t}} = {res['K_t']:.3f}\ \mathrm{{W/(m^2K)}}")
        st.caption("표면→표면 열컨덕턴스입니다. 표면저항(1/h)이 빠져 있어 U-value가 아닙니다 (02강 p.56–57).")

    st.markdown("**③ 열류** (02강 p.26" + (", p.57)" if air else ")"))
    st.latex(rf"q_t = -\frac{{1}}{{R_t}}({in_s} - {out_s}) = -\frac{{1}}{{{res['R_t']:.3f}}}"
             rf"({num(res['T_in'], 1)} - {num(res['T_out'], 1)}) = {res['q_t']:+.2f}\ \mathrm{{W/m^2}}")
    sign_note = ("양수(+) → 실외에서 실내로" if res["q_t"] > 0 else
                 "음수(−) → 실내에서 실외로" if res["q_t"] < 0 else "0 → 열 흐름 없음")
    st.caption(f"부호 규약: x=0이 외측, 실내 방향이 +.  q_t {sign_note} 흐릅니다.  크기 |q_t| = {res['q_abs']:.2f} W/m²")

    st.markdown("**④ 경계 온도 (외측부터 누적)**  $T = T_{외측} - q_t \\times \\sum R$  (02강 p.27–28, p.58–59)")
    cum_syms = []
    for i, bnd in enumerate(res["boundaries"][1:-1], start=1):
        cum_syms.append(syms[i - 1])
        R_cum = sum(e["R"] for e in res["elements"][:i])
        st.caption(bnd["label"])
        st.latex(rf"{tex(bnd['symbol'])} = {out_s} - q_t({' + '.join(cum_syms)}) = {num(res['T_out'], 1)}"
                 rf" - ({res['q_t']:+.2f})({R_cum:.3f}) = {bnd['T']:.2f}\ ^\circ\mathrm{{C}}")
    st.caption(f"검산: 마지막 경계에서 다시 {res['T_in']:.1f}°C({in_s.replace('{', '').replace('}', '')})로 돌아오면 정상.")


def insights(res: dict) -> list[str]:
    if res["q_abs"] < 1e-12:
        return ["실외와 실내 온도가 같아 열이 흐르지 않습니다. 열 흐름의 구동력은 **온도차(포텐셜 차이)** 입니다 (02강 p.11)."]
    layers = [e for e in res["elements"] if e["kind"] == "layer"]
    top = max(layers, key=lambda e: e["share_pct"])
    steep = min(layers, key=lambda e: e["k"])
    msgs = [f"온도 강하의 **{top['share_pct']:.1f}%** 가 **{top['name']}** 층에서 일어납니다. "
            f"저항이 큰 층에서 온도 기울기가 급해집니다 (02강 p.20)."]
    if steep is not top:
        msgs.append(f"단위 두께당 기울기(ΔT/d = q_t/k)는 k가 가장 작은 **{steep['name']}** 층에서 가장 큽니다. "
                    f"전체 강하량은 R = d/k 이므로 두께도 함께 봐야 합니다.")
    msgs.append("정상상태에서는 모든 층을 지나는 열류 q_t 가 같습니다 (02강 p.26). "
                "그래서 층별 온도 강하는 저항에 비례합니다: ΔT_j = q_t × R_j.")
    if res["mode"] == "air":
        surf = sum(e["share_pct"] for e in res["elements"] if e["kind"] == "surface")
        msgs.append(f"표면저항(R_to + R_ti)이 전체 저항의 **{surf:.1f}%** 를 차지합니다. "
                    f"U = {res['U']:.3f} W/(m²K) 이고, 그 역수가 총 열저항입니다 (02강 p.56).")
    return msgs


# ---------------------------------------------------------------- 화면
st.title("🧱 다층벽 열전달 AI 튜터")
st.caption("건축환경조절(ARC2041) 02강 · 정상상태 다층벽 열전달 — 계산은 코드가, 설명은 AI가")

# ---------------------------------------------------------------- 퀴즈 상태
TAB_LAB, TAB_TUTOR, TAB_QUIZ = "🔬 벽체 실험실", "💬 AI 튜터에게 질문", "✅ 개념 점검"


def reset_quiz() -> None:
    ss.quiz = {"round": ss.get("quiz", {}).get("round", 0) + 1,
               "numeric": make_round(random.randrange(1_000_000), demo=ss.get("demo_mode", False)),
               "num_answers": {}, "mcq_answers": {}}


def grade_numeric(i: int) -> None:
    p = ss.quiz["numeric"][i]
    value = ss.get(f"qn_{ss.quiz['round']}_{i}")
    ss.quiz["num_answers"][i] = {"value": value, "correct": is_correct(value, p)}


def grade_mcq(qid: str) -> None:
    q = next(q for q in CONCEPT_QUESTIONS if q["id"] == qid)
    choice = ss.get(f"qm_{ss.quiz['round']}_{qid}")
    if choice is None:
        return
    idx = q["options"].index(choice)
    ss.quiz["mcq_answers"][qid] = {"choice": idx, "correct": idx == q["answer"]}


def open_in_lab(i: int) -> None:
    p = ss.quiz["numeric"][i]
    load_condition(p["layers"], p["T_os"], p["T_is"])
    ss.main_tab = TAB_LAB
    ss.lab_notice = (f"✅ 개념 점검 계산 {i + 1}번 조건을 불러왔습니다 "
                     f"(T_os = {p['T_os']:g} °C, T_is = {p['T_is']:g} °C). 그래프와 단계별 풀이로 확인해 보세요.")


def ask_ai_about(question: str, numeric_index: int | None = None) -> None:
    if numeric_index is not None:  # 계산 문제는 실험실에 조건을 넣어 튜터가 같은 계산 결과를 보게 한다
        p = ss.quiz["numeric"][numeric_index]
        load_condition(p["layers"], p["T_os"], p["T_is"])
    ss.pending_question = question
    ss.main_tab = TAB_TUTOR


if "quiz" not in ss:
    reset_quiz()


# ---------------------------------------------------------------- 설계 챌린지 상태
TAB_CHALLENGE = "🏗️ 설계 챌린지"


def reset_challenge() -> None:
    ss.ch = {"specs": {lv: list(LEVELS[lv]["start"]) for lv in LEVELS},
             "fails": {lv: 0 for lv in LEVELS}, "cleared": {lv: False for lv in (1, 2, 3, 4)},
             "judged": {lv: None for lv in LEVELS}, "lv4": {"prediction": None, "revealed": False},
             "ver": ss.get("ch", {}).get("ver", 0) + 1}
    ss.ch_level = 1  # 처음부터 다시 하면 Lv.1 로


def ch_key(name: str) -> str:
    return f"ch_{name}_{ss.ch['ver']}"


def ch_set_thickness(level: int, index: int) -> None:
    key, _ = ss.ch["specs"][level][index]
    ss.ch["specs"][level][index] = (key, round(ss[ch_key(f"d{level}_{index}")], 3))
    ss.ch["judged"][level] = None


def ch_set_material(level: int, index: int) -> None:
    _, d = ss.ch["specs"][level][index]
    ss.ch["specs"][level][index] = (ss[ch_key(f"m{level}_{index}")], d)
    ss.ch["judged"][level] = None


def ch_edit_layers(action: str, index: int = -1) -> None:
    """Lv.3 층 추가/삭제/이동. 위젯을 새로 그리도록 ver 를 올린다."""
    spec = ss.ch["specs"][3]
    if action == "add":
        spec.append((ss[ch_key("new3")], 0.05))
    elif action == "delete" and len(spec) > 1:
        spec.pop(index)
    elif action in ("up", "down"):
        j = index - 1 if action == "up" else index + 1
        if 0 <= j < len(spec):
            spec[index], spec[j] = spec[j], spec[index]
    ss.ch["judged"][3] = None
    ss.ch["ver"] += 1


def ch_judge(level: int) -> None:
    passed = evaluate(level, ss.ch["specs"][level])["passed"]
    ss.ch["judged"][level] = passed
    if passed:
        ss.ch["cleared"][level] = True
    else:
        ss.ch["fails"][level] += 1


def ch_reveal_lv4() -> None:
    ss.ch["lv4"]["prediction"] = LV4_CHOICES.index(ss[ch_key("lv4_pred")])
    ss.ch["lv4"]["revealed"] = True
    ss.ch["cleared"][4] = True
    set_view_mode(MODE_TEMPERATURE)  # 공개하는 순간 두 3D 모형을 온도 보기로


# 3D 보기 모드: 학생이 고른 값(view_mode)은 레벨 이동·두께 변경에도 유지된다.
# 위젯 키에 버전을 붙여, 코드가 모드를 바꿀 때(Lv.4 공개) 새 위젯이 그 값으로 그려지게 한다.
if "view_mode" not in ss:
    ss.view_mode, ss.view_ver = MODE_MATERIAL, 0


def set_view_mode(mode: str) -> None:
    ss.view_mode = mode
    ss.view_ver += 1


def on_view_toggle(key: str) -> None:
    if ss.get(key):
        ss.view_mode = ss[key]


def load_condition_air(layers: list[tuple[str, float]], T_oa: float, T_ia: float, h_to: float, h_ti: float) -> None:
    load_condition(layers, T_oa, T_ia)
    ss.mode = AIR_MODE
    ss.cond.update({"T_oa": T_oa, "T_ia": T_ia, "h_to": h_to, "h_ti": h_ti})


def ask_ai_design(level: int) -> None:
    spec = ss.ch["specs"][level]
    ev = evaluate(level, spec)
    load_condition_air(spec, CH_T_OA, CH_T_IA, CH_H_TO, CH_H_TI)  # 튜터가 같은 계산 결과(JSON)를 보도록
    ss.pending_question = (
        "[설계 챌린지] 내 벽 설계를 평가해줘. 정답 조합이나 두께를 알려주지 말고, 내 설계 판단이 어떤지 짚은 뒤 "
        "다음에 무엇을 고민해 보면 좋을지 질문 1~2개로 이끌어줘.\n"
        + json.dumps(design_summary(level, spec, ev), ensure_ascii=False, indent=1))
    ss.main_tab = TAB_TUTOR


if "ch" not in ss:
    reset_challenge()


with st.sidebar:
    st.header("조건 설정")
    st.radio("계산 모드", [SURFACE_MODE, AIR_MODE], key="mode")
    if ss.mode == SURFACE_MODE:
        cond_input("외표면 온도 T_os [°C]", "T_os", step=1.0, format="%.1f")
        cond_input("내표면 온도 T_is [°C]", "T_is", step=1.0, format="%.1f")
        st.caption("02강 p.26–30: 벽 양쪽 **표면** 온도를 알고 있을 때")
    else:
        cond_input("외기 온도 T_oa [°C]", "T_oa", step=1.0, format="%.1f")
        cond_input("실내 공기 온도 T_ia [°C]", "T_ia", step=1.0, format="%.1f")
        cond_input("외부 총 열전달계수 h_to [W/(m²K)]", "h_to", min_value=0.1, step=1.0, format="%.2f")
        cond_input("내부 총 열전달계수 h_ti [W/(m²K)]", "h_ti", min_value=0.1, step=0.1, format="%.2f")
        st.caption(f"02강 p.57–59. h 기본값({DEFAULT_H_TO:g}, {DEFAULT_H_TI:g})은 **대표값**입니다 (정리본에 기본값 없음). "
                   "참고: h_c 범위 — 내표면 2–25, 외표면 25–250 (02강 p.40)")
    st.divider()
    st.markdown("**계절 예시**")
    c1, c2 = st.columns(2)
    c1.button("❄️ 겨울", on_click=set_season, args=("winter",), width="stretch",
              help="실외 -5°C, 실내 20°C")
    c2.button("☀️ 여름", on_click=set_season, args=("summer",), width="stretch",
              help="실외 33°C, 실내 26°C")
    st.divider()
    st.checkbox("🎬 시연 모드", key="demo_mode", on_change=lambda: reset_quiz(),
                help="개념 점검의 계산 4번(경계 온도)이 항상 같은 문제로 나옵니다 (켜고 끄면 퀴즈가 새로 시작됩니다).")

tab_lab, tab_tutor, tab_quiz, tab_challenge = st.tabs([TAB_LAB, TAB_TUTOR, TAB_QUIZ, TAB_CHALLENGE],
                                                       key="main_tab", on_change="rerun")

if ss.get("lab_notice"):
    tab_lab.success(ss.pop("lab_notice"))

with tab_lab:
    top_l, top_r = st.columns([3, 1])
    top_l.subheader("레이어 구성 (실외 → 실내 순서)")
    top_r.button("📘 정리본 예제 불러오기 (p.29)", on_click=load_example, width="stretch")

    preset_keys = list(MATERIAL_PRESETS.keys())
    hdr = st.columns([0.4, 2.6, 2.4, 1.1, 1.1, 0.9, 1.3])
    for col, label in zip(hdr, ["#", "재료", "두께 d [m]", "", "k [W/(m·K)]", "R", "순서 / 삭제"]):
        col.markdown(f"<small><b>{label}</b></small>", unsafe_allow_html=True)

    for pos, lid in enumerate(ss.layer_ids):
        layer = ss.layers[lid]
        # 위젯 키가 정리됐을 수 있으므로 원본 데이터에서 복원
        ss.setdefault(f"preset_{lid}", layer["preset"])
        ss.setdefault(f"d_slider_{lid}", layer["d"])
        ss.setdefault(f"d_num_{lid}", layer["d"])
        ss.setdefault(f"k_{lid}", layer["k"])
        ss.setdefault(f"name_{lid}", layer["name"])

        c = st.columns([0.4, 2.6, 2.4, 1.1, 1.1, 0.9, 1.3], vertical_alignment="center")
        c[0].markdown(f"**{pos + 1}**")
        c[1].selectbox("재료", preset_keys, key=f"preset_{lid}", on_change=on_preset, args=(lid,),
                       label_visibility="collapsed")
        if layer["preset"] == CUSTOM:
            c[1].text_input("재료 이름", key=f"name_{lid}", on_change=on_field, args=(lid, "name"),
                            label_visibility="collapsed", placeholder="재료 이름")
        else:
            src = MATERIAL_PRESETS[layer["preset"]]["source"]
            c[1].caption("⚠️ 대표값 (정리본 외)" if src == "대표값" else f"출처: {src}")
        c[2].slider("두께", D_MIN, D_MAX, step=0.005, key=f"d_slider_{lid}", on_change=on_d,
                    args=(lid, "slider"), label_visibility="collapsed", format="%.3f")
        c[3].number_input("두께 입력", D_MIN, D_MAX, step=0.001, key=f"d_num_{lid}", on_change=on_d,
                          args=(lid, "num"), label_visibility="collapsed", format="%.3f")
        c[4].number_input("k", min_value=0.001, step=0.01, key=f"k_{lid}", on_change=on_field,
                          args=(lid, "k"), label_visibility="collapsed", format="%.3f",
                          disabled=layer["preset"] != CUSTOM)
        c[5].markdown(f"`{layer['d'] / layer['k']:.3f}`")
        b1, b2, b3 = c[6].columns(3)
        b1.button("↑", key=f"up_{lid}", on_click=move_layer, args=(lid, -1), disabled=pos == 0)
        b2.button("↓", key=f"down_{lid}", on_click=move_layer, args=(lid, 1),
                  disabled=pos == len(ss.layer_ids) - 1)
        b3.button("✕", key=f"del_{lid}", on_click=delete_layer, args=(lid,),
                  disabled=len(ss.layer_ids) == 1)

    add_c1, add_c2 = st.columns([3, 1])
    new_preset = add_c1.selectbox("추가할 재료", preset_keys, key="new_preset", label_visibility="collapsed")
    add_c2.button("➕ 레이어 추가 (실내 쪽 끝)", on_click=_add_layer, args=(new_preset, 0.1),
                  width="stretch")

    # ---- 계산 (calc.py)
    layers = [Layer(ss.layers[lid]["name"], ss.layers[lid]["d"], ss.layers[lid]["k"]) for lid in ss.layer_ids]
    res = None
    try:
        if ss.mode == SURFACE_MODE:
            res = solve_surface(layers, ss.cond["T_os"], ss.cond["T_is"])
        else:
            res = solve_air(layers, ss.cond["T_oa"], ss.cond["T_ia"], ss.cond["h_to"], ss.cond["h_ti"])
    except ValueError as err:
        st.error(f"입력값을 확인해 주세요: {err}")
    ss.last_result = res
    ss.last_inputs = {"mode": "surface" if ss.mode == SURFACE_MODE else "air",
                      "layers": [{"name": l.name, "d": l.d, "k": l.k} for l in layers]}

if res is not None:
    with tab_lab:
        st.divider()
        # ---- 열 흐름 배너
        if res["q_t"] > 0:
            st.warning(f"☀️ **열 흐름: 실외 → 실내**  —  실외 쪽이 더 뜨거워 열이 안으로 들어옵니다 "
                       f"(여름철 냉방 상황). |q_t| = {res['q_abs']:.2f} W/m², 부호 규약상 q_t = {res['q_t']:+.2f}")
        elif res["q_t"] < 0:
            st.info(f"❄️ **열 흐름: 실내 → 실외**  —  실내 쪽이 더 따뜻해 열이 밖으로 빠져나갑니다 "
                    f"(겨울철 난방 상황). |q_t| = {res['q_abs']:.2f} W/m², 부호 규약상 q_t = {res['q_t']:+.2f}")
        else:
            st.success("열 흐름 없음 — 양쪽 온도가 같습니다.")

        m = st.columns(4)
        m[0].metric("총 열저항 R_t [m²K/W]", f"{res['R_t']:.3f}")
        if res["mode"] == "air":
            m[1].metric("U-value [W/(m²K)]", f"{res['U']:.3f}")
        else:
            m[1].metric("K_t [W/(m²K)] (U 아님)", f"{res['K_t']:.3f}")
        m[2].metric("열류 |q_t| [W/m²]", f"{res['q_abs']:.2f}")
        m[3].metric("벽 두께 [m]", f"{res['total_thickness']:.3f}")

        g_col, i_col = st.columns([3, 2])
        with g_col:
            st.markdown("#### 벽 단면 온도 분포")
            st.plotly_chart(build_figure(res), width="stretch")
            if res["mode"] == "air":
                st.caption("파란 구간은 표면저항(경계층)을 보이기 위한 표시용 폭이며 실제 두께가 아닙니다.")
        with i_col:
            st.markdown("#### 💡 핵심 인사이트")
            for msg in insights(res):
                st.markdown(f"- {msg}")
            with st.expander("층별 상세 표"):
                st.dataframe([{
                    "요소": e["name"], "d [m]": round(e["d"], 4) if e["kind"] == "layer" else None,
                    "k 또는 h": e["k"] if e["kind"] == "layer" else e["h"],
                    "R [m²K/W]": round(e["R"], 4), "ΔT [°C]": round(e["dT"], 2),
                    "비율 [%]": round(e["share_pct"], 1),
                    "시작 T [°C]": round(e["T_start"], 2), "끝 T [°C]": round(e["T_end"], 2),
                } for e in res["elements"]], width="stretch", hide_index=True)

        st.markdown("#### 🔌 저항 회로 (02강 p.18: 온도차 = 전압, 열류 = 전류, 열저항 = 저항)")
        st.code(circuit_text(res), language=None)

        st.markdown("#### 📝 단계별 풀이")
        show_steps(res)

SHORTCUTS = ["지금 그래프를 설명해줘", "왜 단열재에서 온도가 급하게 떨어져?",
             "conductivity와 conductance 차이가 뭐야?", "U-value가 뭐야?"]
SCREENSHOT_DIR = Path(__file__).parent / "docs" / "screenshots"


def queue_question(q: str) -> None:
    ss.pending_question = q


def clear_chat() -> None:
    ss.chat = []


def render_tutor_unavailable(reason: str) -> None:
    st.info("🔒 이 기능은 API 키를 설정하면 활성화됩니다.")
    st.caption(reason)
    st.markdown(
        "**AI 튜터가 하는 일**\n"
        "- 벽체 실험실의 현재 조건과 계산 결과(JSON)를 받아 그래프와 풀이를 설명합니다. "
        "숫자는 계산 엔진 결과만 인용하고 직접 계산하지 않습니다.\n"
        "- 풀이를 물으면 바로 답하지 않고 힌트 질문부터 던집니다. \"답 보여줘\"라고 하면 풀이를 보여줍니다.\n"
        "- 정리본 02강을 근거로 답하고 \"(02강 p.57)\"처럼 출처 페이지를 표시합니다.\n"
        "- 온도차 = 전압, 열류 = 전류, 열저항 = 저항이라는 전기회로 비유로 설명합니다.\n"
        "- 02강 범위 밖의 질문에는 범위 밖임을 밝히고 짧게만 답합니다.\n\n"
        "설정 방법은 README의 **AI 튜터 설정** 절을 참고하세요. 계산기·그래프·퀴즈는 키 없이도 그대로 쓸 수 있습니다.")
    shots = sorted(p for p in SCREENSHOT_DIR.glob("*") if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif", ".webp"))
    if shots:
        st.markdown("**AI 튜터 사용 예시 (캡처)**")
        for shot in shots:
            caption = shot.stem.split("_", 1)[-1].replace("_", " ") if shot.stem[:2].isdigit() else shot.stem
            st.image(str(shot), caption=caption, width="stretch")


with tab_tutor:
    cfg, reason = load_config()
    if cfg is None:
        render_tutor_unavailable(reason)
    else:
        ss.setdefault("chat", [])
        head_l, head_r = st.columns([4, 1])
        head_l.caption(f"AI 제공자: {cfg.label} · 숫자는 벽체 실험실 계산 결과만 인용합니다 · 최근 10턴까지 기억")
        head_r.button("대화 초기화", on_click=clear_chat, width="stretch")
        if tutor_reference() is None:
            st.warning("📄 강의 정리본(data/건축환경조절_정리본.md)이 없어 근거 자료 없이 답변합니다. "
                       "이 경우 튜터는 강의 페이지 출처를 표기하지 않습니다.")
        sc = st.columns(len(SHORTCUTS))
        for col, q in zip(sc, SHORTCUTS):
            col.button(q, on_click=queue_question, args=(q,), width="stretch")

        chat_box = st.container()  # 기록과 새 답변을 입력창 위에 표시
        with chat_box:
            for m in ss.chat:
                with st.chat_message(m["role"]):
                    st.markdown(m["content"])

        typed = st.chat_input("02강 열전달에 대해 질문해 보세요 (예: 단열재 두께를 두 배로 하면?)")
        question = typed or ss.pop("pending_question", None)
        if question:
            with chat_box:
                with st.chat_message("user"):
                    st.markdown(question)
                if ss.get("last_result") is None:
                    st.warning("벽체 실험실의 입력값 오류를 먼저 고쳐 주세요. 계산 결과가 있어야 튜터가 설명할 수 있습니다.")
                else:
                    with st.chat_message("assistant"):
                        with st.spinner("튜터가 생각하는 중..."):
                            try:
                                answer = ask(cfg, ss.chat, question, calc_context(ss.last_inputs, ss.last_result))
                            except TutorError as err:
                                answer = None
                                st.error(str(err))
                        if answer:
                            st.markdown(answer)
                            ss.chat += [{"role": "user", "content": question},
                                        {"role": "assistant", "content": answer}]

def fmt_answer(v: float) -> str:
    return f"{v:.4f}" if abs(v) < 1 else f"{v:.3f}" if abs(v) < 100 else f"{v:.1f}"


def score_text() -> str:
    answers = list(ss.quiz["num_answers"].values()) + list(ss.quiz["mcq_answers"].values())
    return f"현재 점수 {sum(a['correct'] for a in answers)} / {len(answers)}"


def render_numeric(i: int, p: dict, ai_on: bool) -> None:
    rnd = ss.quiz["round"]
    result = ss.quiz["num_answers"].get(i)
    with st.container(border=True):
        demo_tag = "  🎬 시연 문제" if p.get("demo") else ""
        st.markdown(f"**계산 {i + 1}. {p['title']}**{demo_tag}")
        layer_txt = " | ".join(f"{MATERIAL_PRESETS[k]['name']} d={d:g} m, k={MATERIAL_PRESETS[k]['k']:g}"
                               for k, d in p["layers"])
        st.caption(f"벽 구성 (실외 → 실내, 표면온도 모드): {layer_txt}  ·  T_os = {p['T_os']:g} °C, T_is = {p['T_is']:g} °C")
        st.markdown(p["question"])
        c_in, c_btn = st.columns([3, 1], vertical_alignment="bottom")
        c_in.number_input(f"답 [{p['unit']}]", key=f"qn_{rnd}_{i}", value=None, step=0.01, format="%.4f",
                          disabled=result is not None, placeholder="숫자를 입력하세요")
        c_btn.button("채점", key=f"qn_btn_{rnd}_{i}", on_click=grade_numeric, args=(i,),
                     disabled=result is not None, width="stretch")
        if result is None:
            return
        if result["correct"]:
            st.success(f"✅ 정답! 정답 {fmt_answer(p['answer'])} {p['unit']} (허용 오차 ±2%)")
        else:
            given = "입력 없음" if result["value"] is None else f"{result['value']:.4g}"
            st.error(f"❌ 오답 — 입력 {given}, 정답 {fmt_answer(p['answer'])} {p['unit']} (허용 오차 ±2%)")
        st.caption(score_text())
        with st.expander("풀이 보기", expanded=not result["correct"]):
            for step in p["steps"]:
                st.markdown(f"- {step}")
        b1, b2 = st.columns(2)
        b1.button("🔬 벽체 실험실에서 이 조건 열어보기", key=f"open_{rnd}_{i}", on_click=open_in_lab, args=(i,),
                  width="stretch")
        if ai_on:
            mine = "입력 없음" if result["value"] is None else f"{result['value']:.4g}"
            q = (f"[개념 점검 계산 {i + 1}번] {p['question']} 내 답은 {mine} {p['unit']}, "
                 f"정답은 {fmt_answer(p['answer'])} {p['unit']}였어. 어디서 틀렸는지(또는 왜 맞는지) 짚어줘.")
            b2.button("🤖 AI에게 더 물어보기", key=f"ai_n_{rnd}_{i}", on_click=ask_ai_about, args=(q, i),
                      width="stretch")


def render_mcq(n: int, q: dict, ai_on: bool) -> None:
    rnd = ss.quiz["round"]
    result = ss.quiz["mcq_answers"].get(q["id"])
    with st.container(border=True):
        st.markdown(f"**개념 {n}. {q['question']}**")
        st.radio("보기", q["options"], index=None, key=f"qm_{rnd}_{q['id']}", label_visibility="collapsed",
                 disabled=result is not None)
        if result is None:
            st.button("제출", key=f"qm_btn_{rnd}_{q['id']}", on_click=grade_mcq, args=(q["id"],))
            st.caption(f"출처: {q['source']}")
            return
        right = q["options"][q["answer"]]
        if result["correct"]:
            st.success(f"✅ 정답! {q['why'][q['answer']]}")
        else:
            st.error(f"❌ 오답 — 고른 답이 틀린 이유: {q['why'][result['choice']]}")
            st.info(f"정답: **{right}**  \n{q['why'][q['answer']]}")
        st.caption(f"출처: {q['source']}  ·  주제: {q['topic']}  ·  {score_text()}")
        if ai_on:
            mine = q["options"][result["choice"]]
            ask_q = (f"[개념 점검: {q['topic']}] 문제: {q['question']} 내가 고른 답: '{mine}', 정답: '{right}'. "
                     "이 개념을 다른 예로 한 번 더 설명해줘.")
            st.button("🤖 AI에게 더 물어보기", key=f"ai_m_{rnd}_{q['id']}", on_click=ask_ai_about, args=(ask_q,))


with tab_quiz:
    ai_on = cfg is not None  # 키가 없으면 "AI에게 더 물어보기" 버튼을 숨긴다
    total = len(ss.quiz["numeric"]) + len(CONCEPT_QUESTIONS)
    answers = list(ss.quiz["num_answers"].values()) + list(ss.quiz["mcq_answers"].values())
    solved, correct = len(answers), sum(a["correct"] for a in answers)

    s1, s2, s3 = st.columns([2, 3, 1], vertical_alignment="center")
    s1.metric("점수 (맞힌 개수 / 푼 개수)", f"{correct} / {solved}", help=f"전체 {total}문항")
    s2.progress(solved / total, text=f"진행 {solved} / {total}문항")
    s3.button("🔄 다시 풀기", on_click=reset_quiz, width="stretch", help="새 계산 문제로 처음부터 다시 풉니다.")
    if solved == total:
        st.success(f"🎉 모두 풀었습니다! {correct} / {total} 정답. 틀린 문제는 풀이와 실험실 그래프로 다시 확인해 보세요.")

    st.subheader("① 계산 문제")
    st.caption("조건은 매번 랜덤입니다 (재료 프리셋과 현실적인 두께 범위 안에서). 정답 판정 허용 오차 ±2% "
               "(온도는 최소 ±0.1 °C). 정답은 계산 엔진(calc.py)이 계산합니다.")
    for i, p in enumerate(ss.quiz["numeric"]):
        render_numeric(i, p, ai_on)

    st.subheader("② 개념 문제 (자주 하는 오개념)")
    for n, q in enumerate(CONCEPT_QUESTIONS, start=1):
        render_mcq(n, q, ai_on)


# ---------------------------------------------------------------- 설계 챌린지 탭
EXTRA_CHALLENGE = {
    1: "💪 추가 도전: 더 얇게 통과할 수 있을까요? 단열재를 1 cm 씩 줄여 보며 통과선이 몇 cm 인지 찾아보세요.",
    2: "💪 추가 도전: 다른 단열재로도 통과할 수 있나요? k = 0.04 단열재로는 왜 안 되는지 두께 조건과 함께 설명해 보세요.",
    3: "💪 추가 도전: 총 두께를 더 줄일 수 있을까요? 단열재를 구조층 안쪽(실내 쪽)으로 옮기면 어떤 조건이 깨지는지도 확인해 보세요.",
}


def render_checks(ev: dict) -> None:
    for c in ev["checks"]:
        mark = "✅" if c["passed"] else "⬜"
        st.progress(c["progress"], text=f"{mark} **{c['label']}** — {c['text']}")


def render_feedback(level: int, ev: dict, ai_on: bool) -> None:
    judged = ss.ch["judged"][level]
    b1, b2 = st.columns([1, 1])
    b1.button("🧪 판정하기", key=ch_key(f"judge{level}"), on_click=ch_judge, args=(level,), type="primary",
              width="stretch")
    if ai_on:
        b2.button("🤖 AI에게 내 설계 평가받기", key=ch_key(f"ai{level}"), on_click=ask_ai_design, args=(level,),
                  width="stretch", help="현재 설계와 목표를 AI 튜터에게 보내고, 정답 대신 설계 판단을 질문으로 이끌어 줍니다.")
    if judged is True:
        st.success(f"🎉 {LEVELS[level]['title']} 클리어! 모든 조건을 만족했습니다 "
                   f"(U = {ev['res']['U']:.3f} W/(m²K), 총 두께 {ev['res']['total_thickness']:.3f} m).")
        st.info(EXTRA_CHALLENGE[level])
    elif judged is False:
        failed = [c["label"] for c in ev["checks"] if not c["passed"]]
        st.error(f"아직 통과하지 못했습니다 — 미통과 조건: {', '.join(failed)}  (실패 {ss.ch['fails'][level]}회)")
    if ss.ch["fails"][level] >= 3 and judged is not True:
        h = hints(ss.ch["specs"][level])
        with st.expander("💡 힌트 (3번 이상 실패해서 열렸어요)", expanded=True):
            st.markdown("**각 층이 전체 저항에서 차지하는 비율** — 저항이 큰 층이 U 를 결정합니다 (02강 p.20, p.57).")
            st.dataframe([{"요소": s["name"], "R [m²K/W]": round(s["R"], 3), "비율 [%]": round(s["share_pct"], 1)}
                          for s in h["shares"]], hide_index=True, width="stretch")
            st.markdown(f"지금 벽에서 **1 cm 늘렸을 때 U 가 가장 많이 줄어드는 층은 '{h['best_name']}'**"
                        f"(k = {h['best_k']:g}) 입니다 (U {h['best_drop']:.3f} 감소). "
                        "왜 그 층일까요? R = d/k 를 떠올려 보세요.")
            if any(not c["passed"] and c["label"] == "구조층 최저 온도" for c in ev["checks"]):
                st.markdown("구조층 온도 조건이 남았다면 그래프에서 **구조층이 따뜻한 쪽(실내)과 차가운 쪽(실외) 중 어디에 "
                            "놓여 있는지** 보세요. 층의 순서를 바꿔 보면 어떻게 될까요?")


def render_view_toggle() -> str:
    key = f"view3d_{ss.view_ver}"
    st.segmented_control("3D 보기", MODES, default=ss.view_mode, required=True, key=key,
                         on_change=on_view_toggle, args=(key,), label_visibility="collapsed")
    return ss.view_mode


def render_3d(res: dict, key: str, mode: str, note: bool = True, height: int = 400) -> None:
    """calc 결과로 그린 3D 벽체 (두께 비율 실제, 1 m × 1 m).
    uirevision 덕분에 그림이 그대로인 재실행(판정하기 등)에서는 돌려 놓은 시점이 유지된다.
    단, 그림 자체가 바뀌면(보기 모드·두께 변경) Streamlit 이 3D 요소를 새로 그려 기본 시점으로 돌아간다."""
    fig = wall_figure(res, (CH_T_OA, CH_T_IA), mode=mode, height=height)
    fig.update_layout(uirevision="wall3d")
    st.plotly_chart(fig, width="stretch", key=ch_key(key))
    if note:
        what = "색 = 재료 (아래 범례)" if mode == MODE_MATERIAL else "색 = 경계 온도"
        st.caption(f"🧊 3D 벽체 (1 m × 1 m, 두께는 실제 비율, {what}). {NOTE} "
                   "마우스로 돌려 보고, 층에 올리면 정보가 보입니다.")


def render_design_view(level: int, ev: dict) -> None:
    g, s = st.columns([3, 2])
    with g:
        st.plotly_chart(build_figure(ev["res"]), width="stretch", key=ch_key(f"fig{level}"))
        st.caption("겨울 조건 T_oa = -10 °C, T_ia = 20 °C, h_to = 25, h_ti = 7.7 W/(m²K) (대표값). "
                   "파란 구간은 표면저항 표시용 폭입니다.")
        mode = render_view_toggle()
        render_3d(ev["res"], f"3d{level}", mode)
    with s:
        st.markdown("**목표 조건**")
        render_checks(ev)
        m1, m2 = st.columns(2)
        m1.metric("U-value [W/(m²K)]", f"{ev['res']['U']:.3f}")
        m2.metric("총 두께 [m]", f"{ev['res']['total_thickness']:.3f}")
        st.caption(f"참고: 겨울 실내 표면 온도 T_is = {ev['inner_surface_temp']:.2f} °C. 1차원 정상상태에서 T_is 는 "
                   "U 로만 정해집니다 (T_is = T_ia − U·ΔT/h_ti). 층 순서를 바꿔도 같습니다.")


def render_level_fixed(level: int) -> None:
    spec = ss.ch["specs"][level]
    idx = LEVELS[level]["edit_index"]
    st.markdown(f"**목표:** {LEVELS[level]['goal']}")
    cols = st.columns(len(spec))
    for i, (key, d) in enumerate(spec):
        with cols[i]:
            with st.container(border=True):
                st.caption(f"{i + 1}층 (실외 → 실내)")
                if i != idx:
                    st.markdown(f"**{MATERIAL_PRESETS[key]['name']}** k = {MATERIAL_PRESETS[key]['k']:g}")
                    st.markdown(f"d = {d:g} m  🔒")
                    continue
                if level == 2:
                    st.selectbox("단열재 종류", INSULATIONS, index=INSULATIONS.index(key), key=ch_key(f"m{level}_{i}"),
                                 on_change=ch_set_material, args=(level, i))
                else:
                    st.markdown(f"**{MATERIAL_PRESETS[key]['name']}** k = {MATERIAL_PRESETS[key]['k']:g}")
                st.slider("두께 d [m]", 0.01, 0.30, value=float(d), step=0.01, key=ch_key(f"d{level}_{i}"),
                          on_change=ch_set_thickness, args=(level, i), format="%.2f")


def render_level_free() -> None:
    spec = ss.ch["specs"][3]
    st.markdown(f"**목표:** {LEVELS[3]['goal']}")
    st.info("**왜 '구조층 최저 온도 ≥ 0 °C' 인가요?** 구조체가 0 °C 아래로 내려가면 내부 수분이 얼어 손상될 위험이 "
            "커집니다. 외단열은 구조체를 실내 쪽 온도로 따뜻하게 유지합니다 (열교 해결책으로서의 외부 단열: 02강 p.73, "
            "습기에 의한 기계적 응력: 03강).  \n"
            "_학습용으로 단순화한 설계 기준이며, 실제 설계 법규 기준은 아닙니다._")
    for i, (key, d) in enumerate(spec):
        c = st.columns([0.4, 3, 2, 0.5, 0.5, 0.5], vertical_alignment="center")
        c[0].markdown(f"**{i + 1}**")
        c[1].selectbox("재료", LV3_PRESETS, index=LV3_PRESETS.index(key), key=ch_key(f"m3_{i}"),
                       on_change=ch_set_material, args=(3, i), label_visibility="collapsed")
        c[2].number_input("두께 d [m]", 0.005, 0.50, value=float(d), step=0.01, key=ch_key(f"d3_{i}"),
                          on_change=ch_set_thickness, args=(3, i), format="%.3f", label_visibility="collapsed")
        c[3].button("↑", key=ch_key(f"up3_{i}"), on_click=ch_edit_layers, args=("up", i), disabled=i == 0)
        c[4].button("↓", key=ch_key(f"dn3_{i}"), on_click=ch_edit_layers, args=("down", i),
                    disabled=i == len(spec) - 1)
        c[5].button("✕", key=ch_key(f"del3_{i}"), on_click=ch_edit_layers, args=("delete", i),
                    disabled=len(spec) == 1)
    a1, a2 = st.columns([3, 1])
    a1.selectbox("추가할 재료", LV3_PRESETS, key=ch_key("new3"), label_visibility="collapsed")
    a2.button("➕ 층 추가 (실내 쪽 끝)", key=ch_key("add3"), on_click=ch_edit_layers, args=("add",), width="stretch")
    st.caption("1번 층이 실외 쪽입니다. 두께는 0.005–0.50 m 범위에서 입력하세요.")


def render_lv4() -> None:
    st.markdown("**발견 레벨:** 아래 벽(콘크리트 | 단열재 | 석고보드, 내단열)에서 **콘크리트와 단열재의 순서를 바꾸면** "
                "(단열재 | 콘크리트 | 석고보드, 외단열) U-value 는 어떻게 될까요? 먼저 예측하세요.")
    r = lv4_results()
    lv4 = ss.ch["lv4"]
    if not lv4["revealed"]:
        g, v = st.columns([3, 2])
        g.plotly_chart(build_figure(r["inner"]), width="stretch", key=ch_key("lv4_inner_only"))
        with v:
            render_3d(r["inner"], "lv4_pre_3d", MODE_MATERIAL, note=False, height=360)
            st.caption("🧱 결과 공개 전에는 재료 보기로만 보여 줍니다. 순서를 바꾸면 무엇이 달라질지 먼저 예측해 보세요.")
        st.radio("예측", LV4_CHOICES, index=None, key=ch_key("lv4_pred"), label_visibility="collapsed")
        st.button("🔄 예측 확정하고 순서 바꿔보기", key=ch_key("lv4_btn"), on_click=ch_reveal_lv4, type="primary",
                  disabled=ss.get(ch_key("lv4_pred")) is None)
        return
    right = lv4["prediction"] == LV4_ANSWER
    (st.success if right else st.warning)(
        f"{'✅ 예측 성공!' if right else '🤔 예측과 달랐어요.'} 내 예측: \"{LV4_CHOICES[lv4['prediction']]}\" → "
        f"정답: **{LV4_CHOICES[LV4_ANSWER]}**")
    c1, c2 = st.columns(2)
    for col, res, title, smin in ((c1, r["inner"], "내단열: 콘크리트 | 단열재 | 석고보드", r["inner_struct"]),
                                  (c2, r["outer"], "외단열: 단열재 | 콘크리트 | 석고보드", r["outer_struct"])):
        with col:
            st.markdown(f"**{title}**")
            st.plotly_chart(build_figure(res), width="stretch", key=ch_key(f"lv4_{title[:3]}"))
            m1, m2 = st.columns(2)
            m1.metric("U-value [W/(m²K)]", f"{res['U']:.3f}")
            m2.metric("콘크리트 최저 온도 [°C]", f"{smin:.1f}")
    st.markdown("**3D 모형 비교**")
    mode = render_view_toggle()
    d1, d2 = st.columns(2)
    for col, res, tag in ((d1, r["inner"], "inner"), (d2, r["outer"], "outer")):
        with col:
            render_3d(res, f"lv4_3d_{tag}", mode, note=False, height=380)
    same_range = " 두 모형은 같은 색 범위(-10 ~ 20 °C)를 씁니다." if mode == MODE_TEMPERATURE else ""
    st.caption(f"3D 모형 (왼쪽 내단열, 오른쪽 외단열): {NOTE}{same_range}")
    st.info("**해설** — 정상상태 1차원 열전달에서 직렬 저항은 더하기만 하므로(R_t = ΣR, 02강 p.20, p.57) "
            "순서를 바꿔도 R_t 와 U-value 는 같습니다. 하지만 **벽 내부 온도 분포는 달라집니다.** "
            f"외단열은 콘크리트가 따뜻한 쪽에 있어 최저 {r['outer_struct']:.1f} °C 로 유지되고, "
            f"내단열은 콘크리트가 외기 쪽에서 최저 {r['inner_struct']:.1f} °C 까지 내려갑니다. "
            "이 차이는 내부 결로와 열용량(축열) 문제로 이어지는데, 이는 03강(습기 이동) 범위입니다.")


with tab_challenge:
    ai_on = cfg is not None
    status = st.columns(5, vertical_alignment="center")
    for lv, col in zip((1, 2, 3, 4), status):
        col.metric(f"Lv.{lv}", "✅ 클리어" if ss.ch["cleared"][lv] else "⬜ 도전 중")
    status[4].button("↺ 처음부터 다시 하기", on_click=reset_challenge, width="stretch")

    # 보기 이름은 고정 (클리어 표시를 이름에 붙이면 위젯이 바뀐 것으로 처리돼 선택이 Lv.1 로 초기화됨).
    # 클리어 여부는 위 상태 줄에서 보여 준다.
    level = st.radio("레벨 선택", [1, 2, 3, 4], horizontal=True, key="ch_level",
                     format_func=lambda lv: LEVELS[lv]["title"] if lv in LEVELS else "Lv.4 순서 바꾸기 (발견)")
    st.caption("공기온도 모드 기준 (h_to = 25, h_ti = 7.7 W/(m²K) 대표값). 판정은 겨울 -10 / 20 °C 조건. "
               "모든 수치는 벽체 실험실과 같은 계산 엔진(calc.py)으로 계산합니다.")
    st.divider()
    if level == 4:
        render_lv4()
    else:
        if level == 3:
            render_level_free()
        else:
            render_level_fixed(level)
        ev = evaluate(level, ss.ch["specs"][level])
        render_design_view(level, ev)
        render_feedback(level, ev, ai_on)

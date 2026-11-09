"""2D 벽 단면 온도 그래프 (Plotly). 계산 없이 calc.py 결과만 그린다.

층 배경색은 3D 재료 보기(viz3d.material_color)와 같은 재료 색을 쓴다.
같은 재료면 2D·3D 가 같은 색이고, 단열재는 k 값별로 명도만 다르다.
"""

from __future__ import annotations

import plotly.graph_objects as go

from viz3d import EDGE_COLOR, material_color

# 층 배경은 3D 와 같은 재료 색(같은 색상)을 반투명으로: 위에 그리는 온도선(빨강)과 이름표가 읽히도록
LAYER_OPACITY = 0.5


def flow_text(res: dict) -> str:
    if res["q_abs"] < 1e-12:
        return "열 흐름 없음"
    return "열 흐름: 실외 → 실내" if res["q_t"] > 0 else "열 흐름: 실내 → 실외"


def build_figure(res: dict) -> go.Figure:
    fig = go.Figure()
    L = res["total_thickness"]
    air = res["mode"] == "air"
    a = 0.12 * L if air else 0.0  # 공기 구간 표시 폭 (실제 두께 아님)

    layers = [e for e in res["elements"] if e["kind"] == "layer"]
    for e in layers:
        fig.add_vrect(x0=e["x_start"], x1=e["x_end"], fillcolor=material_color(e["name"], e["k"]),
                      opacity=LAYER_OPACITY, line=dict(color=EDGE_COLOR, width=1), layer="below")
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

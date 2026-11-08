"""3D 벽체 미리보기 (Plotly Mesh3d). 새 계산 없이 calc.py 결과(층 두께·R·경계 온도)만 그린다.

- x: 실제 두께 [m] (실외 → 실내), y·z: 1 m × 1 m 고정 (단위 면적 벽)
- 두 가지 보기
  · 재료 보기 (MODE_MATERIAL): 재료별 대표 단색 + 재료 범례, 벽돌은 가로 줄눈 선
  · 온도 보기 (MODE_TEMPERATURE): 각 층 양 끝 경계 온도(T_start, T_end)를 꼭짓점 값으로 주어
    두께 방향 그라데이션 + 공통 컬러바 (정상상태 1차원에서 층 안의 온도는 직선 분포)
- hover 정보는 두 보기에서 동일
- 1차원 정상상태 해석의 시각화이며 다차원 열흐름(열교 등)은 반영하지 않는다
"""

from __future__ import annotations

import plotly.graph_objects as go

MODE_MATERIAL = "🧱 재료 보기"
MODE_TEMPERATURE = "🌡️ 온도 보기"
MODES = [MODE_MATERIAL, MODE_TEMPERATURE]

COLORSCALE = "RdBu_r"  # 저온 파랑 → 고온 빨강
NOTE = "1차원 정상상태 해석의 시각화이며 다차원 열흐름(열교 등)은 반영하지 않습니다."

# 재료 보기 색 (라이트 모드에서 서로 구분되게). 단열재는 같은 연노랑 계열에서 k 값별로 명도만 다르게.
MATERIAL_COLORS = {
    "콘크리트": "#9a9a9a",
    "석고보드": "#ebebeb",
    "목재": "#9c6a3c",
    "벽돌": "#a6472f",
    "모르타르": "#cbbba3",
    "합판": "#d6ad74",
    "사용자 재료": "#a99ad6",
}
INSULATION_COLORS = {0.02: "#f6d55c", 0.03: "#fae38f", 0.04: "#fdf0c0"}
INSULATION_DEFAULT = "#fae38f"
EDGE_COLOR = "#4a4a4a"
JOINT_COLOR = "#efe6d8"   # 벽돌 줄눈 (밝은 모르타르 색)
BRICK_COURSE = 0.0667     # 벽돌 1단 높이 ≈ 57 mm + 줄눈 10 mm
LABEL_MIN_D = 0.04        # 이보다 얇은 층은 위쪽 이름표 생략 (범례·hover 로 확인)

# 직육면체 12개 삼각형 (꼭짓점 0~3: x0 면, 4~7: x1 면)
_I = [0, 0, 4, 4, 0, 0, 3, 3, 0, 0, 1, 1]
_J = [1, 2, 5, 6, 1, 5, 2, 6, 3, 7, 2, 6]
_K = [2, 3, 6, 7, 5, 4, 6, 7, 7, 4, 6, 5]


def material_color(name: str, k: float) -> str:
    if name == "단열재":
        return INSULATION_COLORS.get(round(k, 3), INSULATION_DEFAULT)
    return MATERIAL_COLORS.get(name, MATERIAL_COLORS["사용자 재료"])


def material_label(name: str, k: float) -> str:
    return f"{name} (k={k:g})" if name == "단열재" else name


def _layers(res: dict) -> list[dict]:
    return [e for e in res["elements"] if e["kind"] == "layer"]


def _box(x0: float, x1: float) -> tuple[list[float], list[float], list[float]]:
    return [x0] * 4 + [x1] * 4, [0, 1, 1, 0] * 2, [0, 0, 1, 1] * 2


def _hover(e: dict) -> str:
    return (f"<b>{e['name']}</b><br>두께 d = {e['d']:.3f} m<br>k = {e['k']:g} W/(m·K)<br>"
            f"R = {e['R']:.3f} m²K/W<br>실외 쪽 경계 {e['T_start']:.2f} °C<br>실내 쪽 경계 {e['T_end']:.2f} °C"
            "<extra></extra>")


def _box_edges(x0: float, x1: float) -> tuple[list, list, list]:
    """직육면체 12개 모서리 (None 으로 끊은 선)."""
    xs, ys, zs = [], [], []
    for x in (x0, x1):  # 두 x 면의 사각형
        xs += [x] * 5 + [None]
        ys += [0, 1, 1, 0, 0, None]
        zs += [0, 0, 1, 1, 0, None]
    for y, z in ((0, 0), (1, 0), (1, 1), (0, 1)):  # x 방향 모서리 4개
        xs += [x0, x1, None]
        ys += [y, y, None]
        zs += [z, z, None]
    return xs, ys, zs


def _brick_joints(x0: float, x1: float) -> tuple[list, list, list]:
    """벽돌 층의 가로 줄눈: 보이는 면(y=0 단면, x 양쪽 면)에 일정 간격의 수평선."""
    xs, ys, zs = [], [], []
    n = int(1 / BRICK_COURSE)
    for c in range(1, n + 1):
        z = round(c * BRICK_COURSE, 4)
        if z >= 1:
            break
        xs += [x0, x1, None, x0, x0, None, x1, x1, None]
        ys += [0, 0, None, 0, 1, None, 0, 1, None]
        zs += [z, z, None, z, z, None, z, z, None]
    return xs, ys, zs


def _labels(res: dict) -> list[dict]:
    """위쪽 이름표: 얇은 층은 생략, 이웃한 이름표는 높이를 번갈아 배치해 겹치지 않게."""
    L = res["total_thickness"]
    out = [dict(x=0, y=0, z=1.25, text="◀ 실외", showarrow=False, font=dict(size=13), xanchor="right"),
           dict(x=L, y=0, z=1.25, text="실내 ▶", showarrow=False, font=dict(size=13), xanchor="left")]
    shown = [e for e in _layers(res) if e["d"] >= LABEL_MIN_D]
    for n, e in enumerate(shown):
        out.append(dict(x=(e["x_start"] + e["x_end"]) / 2, y=0, z=1.05 if n % 2 == 0 else 1.15,
                        text=e["name"], showarrow=False, font=dict(size=11, color="#222"),
                        bgcolor="rgba(255,255,255,0.85)", borderpad=2))
    return out


def wall_traces(res: dict, t_range: tuple[float, float], mode: str = MODE_MATERIAL) -> list:
    traces = []
    edges = ([], [], [])
    joints = ([], [], [])
    legend_seen = set()
    for n, e in enumerate(_layers(res)):
        xs, ys, zs = _box(e["x_start"], e["x_end"])
        common = dict(x=xs, y=ys, z=zs, i=_I, j=_J, k=_K, name=e["name"], hovertemplate=_hover(e),
                      flatshading=True, showlegend=False)
        if mode == MODE_TEMPERATURE:
            traces.append(go.Mesh3d(
                **common, intensity=[e["T_start"]] * 4 + [e["T_end"]] * 4, intensitymode="vertex",
                colorscale=COLORSCALE, cmin=t_range[0], cmax=t_range[1], showscale=n == 0,
                colorbar=dict(title=dict(text="온도 [°C]"), thickness=14, len=0.75),
                lighting=dict(ambient=0.85, diffuse=0.4, specular=0.05)))
        else:
            color = material_color(e["name"], e["k"])
            traces.append(go.Mesh3d(**common, color=color, opacity=1.0,
                                    lighting=dict(ambient=0.95, diffuse=0.25, specular=0.0)))  # 재료 고유색이 어둡게 변하지 않게
            label = material_label(e["name"], e["k"])
            if label not in legend_seen:  # 범례: 재료마다 한 번 (색 + 이름)
                legend_seen.add(label)
                traces.append(go.Scatter3d(x=[None], y=[None], z=[None], mode="markers", name=label,
                                           marker=dict(size=10, color=color, symbol="square",
                                                       line=dict(color=EDGE_COLOR, width=1)),
                                           showlegend=True, hoverinfo="skip"))
            if e["name"] == "벽돌":
                for acc, part in zip(joints, _brick_joints(e["x_start"], e["x_end"])):
                    acc += part
        for acc, part in zip(edges, _box_edges(e["x_start"], e["x_end"])):
            acc += part
    if joints[0]:
        traces.append(go.Scatter3d(x=joints[0], y=joints[1], z=joints[2], mode="lines", name="벽돌 줄눈",
                                   line=dict(color=JOINT_COLOR, width=2), hoverinfo="skip", showlegend=False))
    traces.append(go.Scatter3d(x=edges[0], y=edges[1], z=edges[2], mode="lines", name="층 경계",
                               line=dict(color=EDGE_COLOR, width=2), hoverinfo="skip", showlegend=False))
    return traces


def wall_figure(res: dict, t_range: tuple[float, float] | None = None, mode: str = MODE_MATERIAL,
                title: str = "", height: int = 420) -> go.Figure:
    if t_range is None:
        temps = [res["T_out"], res["T_in"]]
        t_range = (min(temps), max(temps))
    fig = go.Figure(wall_traces(res, t_range, mode))
    L = res["total_thickness"]
    fig.update_layout(
        height=height, margin=dict(l=0, r=0, t=36 if title else 8, b=0),
        showlegend=mode == MODE_MATERIAL,
        legend=dict(orientation="h", yanchor="bottom", y=0.0, xanchor="center", x=0.5, title=dict(text="재료 ")),
        scene=dict(
            xaxis=dict(title=dict(text="두께 x [m] (실외 → 실내)"), range=[-0.02, L + 0.02]),
            yaxis=dict(title=dict(text=""), range=[0, 1], showticklabels=False),
            zaxis=dict(title=dict(text="1 m"), range=[0, 1.3], showticklabels=False),
            aspectmode="data", annotations=_labels(res),
            # 벽 단면(y = 0 면)을 정면에서 약간 위·옆으로: 층이 왼쪽(실외) → 오른쪽(실내) 띠로 보인다
            camera=dict(eye=dict(x=0.45, y=-2.4, z=0.95), center=dict(x=0, y=0, z=-0.05))))
    if title:
        fig.update_layout(title=dict(text=title, x=0.5, xanchor="center", font=dict(size=14)))
    return fig

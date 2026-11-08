import sys
from pathlib import Path

import plotly.graph_objects as go
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from challenge import CONCRETE, GYPSUM, LV4_INNER, LV4_OUTER, solve  # noqa: E402
from materials import MATERIAL_PRESETS  # noqa: E402
from viz3d import (INSULATION_COLORS, LABEL_MIN_D, MATERIAL_COLORS, MODE_MATERIAL, MODE_TEMPERATURE,  # noqa: E402
                   NOTE, material_color, wall_figure)

T_RANGE = (-10, 20)
BRICK = "벽돌 (대표값, k=0.6)"


def meshes(fig):
    return [t for t in fig.data if isinstance(t, go.Mesh3d)]


def lines(fig, name):
    return [t for t in fig.data if isinstance(t, go.Scatter3d) and t.name == name]


def legend_items(fig):
    return [t for t in fig.data if isinstance(t, go.Scatter3d) and t.showlegend]


def test_temperature_mode_boxes_thickness_colors_and_colorbar():
    res = solve(LV4_INNER)
    fig = wall_figure(res, T_RANGE, mode=MODE_TEMPERATURE)
    ms = meshes(fig)
    layers = [e for e in res["elements"] if e["kind"] == "layer"]
    assert len(ms) == len(layers) == 3
    for m, e in zip(ms, layers):
        assert min(m.x) == pytest.approx(e["x_start"]) and max(m.x) == pytest.approx(e["x_end"])
        assert set(m.y) == {0, 1} and set(m.z) == {0, 1}                       # 1 m × 1 m
        assert list(m.intensity) == [e["T_start"]] * 4 + [e["T_end"]] * 4      # 계산 결과 그대로
        assert (m.cmin, m.cmax) == T_RANGE and m.color is None
    assert [m.showscale for m in ms] == [True, False, False]                     # 공통 컬러바 1개
    assert not legend_items(fig) and fig.layout.showlegend is False
    assert fig.layout.scene.aspectmode == "data"


def test_material_mode_solid_colors_and_legend():
    res = solve(LV4_INNER)  # 콘크리트 | 단열재(k=0.03) | 석고보드
    fig = wall_figure(res, T_RANGE, mode=MODE_MATERIAL)
    ms = meshes(fig)
    assert [m.color for m in ms] == [MATERIAL_COLORS["콘크리트"], INSULATION_COLORS[0.03], MATERIAL_COLORS["석고보드"]]
    assert all(m.intensity is None and not m.showscale for m in ms)              # 컬러바 없음
    legend = legend_items(fig)
    assert [t.name for t in legend] == ["콘크리트", "단열재 (k=0.03)", "석고보드"]
    assert [t.marker.color for t in legend] == [m.color for m in ms]
    assert fig.layout.showlegend is True
    assert lines(fig, "층 경계")                                                  # 층 테두리 선


def test_material_colors_distinct_and_insulation_same_family():
    colors = list(MATERIAL_COLORS.values()) + list(INSULATION_COLORS.values())
    assert len(colors) == len(set(colors))
    names = {p["name"] for p in MATERIAL_PRESETS.values()}
    for p in MATERIAL_PRESETS.values():
        assert material_color(p["name"], p["k"]).startswith("#")
    assert names - {"단열재"} <= set(MATERIAL_COLORS)

    def hue_lum(hex_color):
        r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
        return (r > b and g > b), (r + g + b) / 3
    hues = [hue_lum(INSULATION_COLORS[k]) for k in (0.02, 0.03, 0.04)]
    assert all(h for h, _ in hues)                                               # 모두 노랑 계열
    assert hues[0][1] < hues[1][1] < hues[2][1]                                  # 명도만 단계적으로


def test_hover_identical_between_modes():
    res = solve(LV4_OUTER)
    a, b = wall_figure(res, T_RANGE, MODE_MATERIAL), wall_figure(res, T_RANGE, MODE_TEMPERATURE)
    assert [m.hovertemplate for m in meshes(a)] == [m.hovertemplate for m in meshes(b)]
    for m in meshes(a):
        for word in ("두께", "k =", "R =", "경계"):
            assert word in m.hovertemplate
    assert a.layout.scene.camera == b.layout.scene.camera                       # 같은 시점 설정


def test_brick_joints_only_for_brick():
    with_brick = solve([(BRICK, 0.19), ("단열재 (p.21, k=0.03)", 0.10), (GYPSUM, 0.015)])
    fig = wall_figure(with_brick, T_RANGE, MODE_MATERIAL)
    joints = lines(fig, "벽돌 줄눈")
    assert joints and max(x for x in joints[0].x if x is not None) <= 0.19 + 1e-9
    assert not lines(wall_figure(solve(LV4_INNER), T_RANGE, MODE_MATERIAL), "벽돌 줄눈")
    assert not lines(wall_figure(with_brick, T_RANGE, MODE_TEMPERATURE), "벽돌 줄눈")


def test_labels_do_not_collide():
    res = solve([(CONCRETE, 0.20), ("단열재 (p.21, k=0.03)", 0.05), (GYPSUM, 0.015), (CONCRETE, 0.04)])
    ann = [a for a in wall_figure(res, T_RANGE).layout.scene.annotations if "실외" not in a.text and "실내" not in a.text]
    assert [a.text for a in ann] == ["콘크리트", "단열재", "콘크리트"]           # 1.5 cm 석고보드는 생략
    zs = [a.z for a in ann]
    assert all(z1 != z2 for z1, z2 in zip(zs, zs[1:]))                           # 이웃 이름표는 높이가 다름
    assert LABEL_MIN_D == 0.04


def test_lv4_orders_differ_in_temperature_colors():
    fa = wall_figure(solve(LV4_INNER), T_RANGE, MODE_TEMPERATURE)
    fb = wall_figure(solve(LV4_OUTER), T_RANGE, MODE_TEMPERATURE)
    conc_a = next(m for m in meshes(fa) if m.name == "콘크리트")
    conc_b = next(m for m in meshes(fb) if m.name == "콘크리트")
    assert max(conc_a.intensity) < 0 < min(conc_b.intensity)


def test_note_mentions_1d_limit():
    assert "1차원 정상상태" in NOTE and "열교" in NOTE

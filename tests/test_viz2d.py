import sys
from pathlib import Path

import plotly.graph_objects as go

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from calc import Layer, solve_surface  # noqa: E402
from challenge import CONCRETE, GYPSUM, INSULATIONS, LEVELS, LV4_INNER, LV4_OUTER, solve  # noqa: E402
from viz2d import LAYER_OPACITY, build_figure, flow_text  # noqa: E402
from viz3d import INSULATION_COLORS, MATERIAL_COLORS, MODE_MATERIAL, wall_figure  # noqa: E402

AIR_FILL = "#e8f1fb"


def layer_fills(fig):
    """2D 그림의 층 배경(vrect) 색, 표면저항 구간(공기)은 제외."""
    return [sh.fillcolor for sh in fig.layout.shapes if sh.type == "rect" and sh.fillcolor != AIR_FILL]


def mesh_colors(fig):
    return [t.color for t in fig.data if isinstance(t, go.Mesh3d)]


def test_lab_example_uses_material_colors():
    layers = [Layer("콘크리트", 0.4, 1.0), Layer("단열재", 0.05, 0.02), Layer("목재", 0.15, 0.1)]
    fig = build_figure(solve_surface(layers, 40, 10))
    assert layer_fills(fig) == [MATERIAL_COLORS["콘크리트"], INSULATION_COLORS[0.02], MATERIAL_COLORS["목재"]]
    assert all(sh.opacity == LAYER_OPACITY for sh in fig.layout.shapes if sh.fillcolor != AIR_FILL)


def test_2d_matches_3d_material_view_for_every_level():
    outer = [("단열재 (p.21, k=0.03)", 0.20), (CONCRETE, 0.20), (GYPSUM, 0.015)]   # Lv.3 외단열 통과 설계
    specs = [LEVELS[1]["start"], LEVELS[2]["start"], LEVELS[3]["start"], outer, LV4_INNER, LV4_OUTER]
    for spec in specs:
        res = solve(spec)
        assert layer_fills(build_figure(res)) == mesh_colors(wall_figure(res, (-10, 20), MODE_MATERIAL)), spec


def test_insulation_color_follows_material_not_position():
    inner, outer = solve(LV4_INNER), solve(LV4_OUTER)
    assert layer_fills(build_figure(inner))[1] == layer_fills(build_figure(outer))[0] == INSULATION_COLORS[0.03]
    assert layer_fills(build_figure(inner))[0] == layer_fills(build_figure(outer))[1] == MATERIAL_COLORS["콘크리트"]


def test_insulation_k_variants_differ_in_2d():
    fills = {layer_fills(build_figure(solve([(CONCRETE, 0.2), (key, 0.1), (GYPSUM, 0.015)])))[1]
             for key in INSULATIONS}
    assert fills == {INSULATION_COLORS[0.02], INSULATION_COLORS[0.03], INSULATION_COLORS[0.04]}


def test_air_mode_keeps_surface_zones_and_flow_text():
    res = solve(LEVELS[1]["start"])
    fig = build_figure(res)
    assert sum(1 for sh in fig.layout.shapes if sh.fillcolor == AIR_FILL) == 2
    assert flow_text(res) == "열 흐름: 실내 → 실외"

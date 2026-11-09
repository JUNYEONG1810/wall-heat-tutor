"""AI 튜터 공통 함수 테스트 (API 호출 없음)."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from calc import Layer, solve_air, solve_surface  # noqa: E402
from materials import NOTES_PATH, tutor_reference  # noqa: E402
from tutor import MAX_TURNS, build_messages, build_system_prompt, calc_context, load_config  # noqa: E402

LAYERS = [Layer("콘크리트", 0.4, 1.0), Layer("단열재", 0.05, 0.02), Layer("목재", 0.15, 0.1)]
INPUTS = {"layers": [{"name": l.name, "d": l.d, "k": l.k} for l in LAYERS]}


needs_notes = pytest.mark.skipif(not NOTES_PATH.is_file(),
                                 reason="강의 정리본은 저장소에 없음 (저작권) — data/ 에 넣으면 실행")


@needs_notes
def test_reference_contains_only_chapter2_sections():
    ref = tutor_reference()
    assert "### 2.8 열저항" in ref and "### 2.14" in ref and "### 2.17 열교" in ref
    assert "### E. 종합 열전달" in ref
    assert "### 2.15" not in ref and "## 03." not in ref and "### F." not in ref


@needs_notes
def test_system_prompt_has_rules_and_reference():
    sp = build_system_prompt()
    assert "힌트 질문 1개" in sp and "(02강 p.57)" in sp and "범위 밖" in sp
    assert "<정리본>" in sp and "### 2.11" in sp


def test_calc_context_is_json_and_matches_calc():
    ctx = calc_context(INPUTS, solve_surface(LAYERS, 40, 10))
    json.dumps(ctx, ensure_ascii=False)
    assert ctx["R_t [m²K/W]"] == 4.4
    assert ctx["|q_t| [W/m²]"] == round(30 / 4.4, 4)
    assert ctx["U [W/(m²K)]"].startswith("해당 없음")
    temps = [b["T [°C]"] for b in ctx["경계 온도 (외측→내측)"]]
    assert round(temps[1], 1) == 37.3 and round(temps[2], 1) == 20.2

    air = calc_context(INPUTS, solve_air(LAYERS, -5, 20, 25, 7.7))
    assert isinstance(air["U [W/(m²K)]"], float)
    assert air["열 흐름 방향"] == "내부 → 외부"


def test_build_messages_limits_history_and_attaches_json():
    history = []
    for i in range(15):
        history += [{"role": "user", "content": f"q{i}"}, {"role": "assistant", "content": f"a{i}"}]
    ctx = calc_context(INPUTS, solve_surface(LAYERS, 40, 10))
    msgs = build_messages(history, "새 질문", ctx)
    assert len(msgs) == 2 * MAX_TURNS + 1
    assert msgs[0] == {"role": "user", "content": "q5"}
    assert msgs[-1]["role"] == "user"
    assert "<계산결과>" in msgs[-1]["content"] and "새 질문" in msgs[-1]["content"]
    assert '"R_t [m²K/W]": 4.4' in msgs[-1]["content"]


def test_load_config_variants(tmp_path):
    env = tmp_path / ".env"
    cfg, reason = load_config(env)
    assert cfg is None and ".env 파일이 없습니다" in reason

    env.write_text("AI_PROVIDER=gemini\nGEMINI_API_KEY=\n", encoding="utf-8")
    cfg, reason = load_config(env)
    assert cfg is None and "GEMINI_API_KEY" in reason

    env.write_text("AI_PROVIDER=gemini\nGEMINI_API_KEY=test-value\n", encoding="utf-8")
    cfg, _ = load_config(env)
    assert cfg.provider == "gemini" and cfg.model == "gemini-3.6-flash"

    env.write_text("AI_PROVIDER=anthropic\nANTHROPIC_API_KEY=test-value\nANTHROPIC_MODEL=claude-x\n",
                   encoding="utf-8")
    cfg, _ = load_config(env)
    assert cfg.provider == "anthropic" and cfg.model == "claude-x"

    env.write_text("AI_PROVIDER=openai\n", encoding="utf-8")
    cfg, reason = load_config(env)
    assert cfg is None and "openai" in reason


def test_missing_notes_is_handled(tmp_path):
    assert tutor_reference(tmp_path / "없는파일.md") is None
    other = tmp_path / "다른형식.md"
    other.write_text("# 내 노트\n\n열저항은 R = d/k 이다.\n", encoding="utf-8")
    assert tutor_reference(other) is None  # 찾을 절이 없으면 None (오류 없음)

    sp = build_system_prompt(use_notes=False)
    assert "<정리본>" not in sp and "페이지 번호" in sp
    assert "힌트 질문 1개" in sp and "범위 밖" in sp


def test_partial_notes_use_found_sections(tmp_path):
    notes = tmp_path / "notes.md"
    notes.write_text("## 02. 열전달\n\n### 2.8 열저항 (p.18)\nR = d/k\n\n### 2.99 기타\n무시\n\n## 03. 습기\n",
                     encoding="utf-8")
    ref = tutor_reference(notes)
    assert ref.startswith("### 2.8 열저항") and "2.99" not in ref
    assert "<정리본>" in build_system_prompt(reference=ref)


def test_request_display_and_payload_are_separate():
    from tutor import make_request, request_parts
    req = make_request("📐 Lv.3 내 설계를 평가해줘", '[설계 챌린지] ... {"레벨": "Lv.3"}')
    display, payload = request_parts(req)
    assert display == "📐 Lv.3 내 설계를 평가해줘" and "{" not in display
    assert payload.startswith("[설계 챌린지]") and '"레벨"' in payload
    assert request_parts("U-value가 뭐야?") == ("U-value가 뭐야?", "U-value가 뭐야?")   # 바로가기 버튼

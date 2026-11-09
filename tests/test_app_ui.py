"""앱 화면 동작 테스트 (Streamlit AppTest, 브라우저 없이 실행). AI 는 호출하지 않는다."""
from pathlib import Path

import pytest

AppTest = pytest.importorskip("streamlit.testing.v1").AppTest
APP = str(Path(__file__).resolve().parents[1] / "app.py")


def run_app():
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def layer_buttons(at, prefix):
    return [b for b in at.button if b.key and b.key.startswith(prefix)]


def test_layer_buttons_are_icons_not_text():
    at = run_app()
    btns = layer_buttons(at, "up_") + layer_buttons(at, "down_") + layer_buttons(at, "del_")
    assert len(btns) == 9                                   # 정리본 예제 3층 × (위, 아래, 삭제)
    for b in btns:
        assert b.label == ""                                # 잘릴 수 있는 글자(↑ ↓ ✕) 없음
        assert b.proto.icon.startswith(":material/")        # 내장 아이콘
        assert b.help                                       # 마우스를 올리면 설명
    assert layer_buttons(at, "up_")[0].disabled             # 맨 위 층은 위로 이동 불가


def test_delete_and_move_still_work():
    at = run_app()
    first, second = at.session_state["layer_ids"][:2]
    layer_buttons(at, "del_")[0].click().run()
    assert not at.exception
    assert at.session_state["layer_ids"][0] == second and len(at.session_state["layer_ids"]) == 2
    layer_buttons(at, "up_")[1].click().run()               # 두 번째 층을 위로
    assert not at.exception
    assert len(at.session_state["layer_ids"]) == 2

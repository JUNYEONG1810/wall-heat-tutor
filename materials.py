"""학습 자료: 재료 프리셋, AI 튜터용 정리본 02강 발췌."""

import re
from pathlib import Path

NOTES_PATH = Path(__file__).parent / "data" / "건축환경조절_정리본.md"

# AI 튜터 근거 자료로 쓸 절 (정리본 02강). 2.1~2.5(부하·패시브), 2.15(일사·로이유리)는 범위가 넓어 제외
TUTOR_SECTIONS = ["2.6", "2.7", "2.8", "2.9", "2.10", "2.11", "2.12", "2.13", "2.14", "2.16", "2.17"]
TUTOR_FORMULA_BLOCKS = ["B", "C", "D", "E"]


def _split_by_heading(text: str, level: str) -> list[str]:
    """'### ' 같은 heading 기준으로 자른 블록 목록 (각 블록은 heading 줄로 시작)."""
    pattern = rf"(?m)^(?={re.escape(level)} )"
    return [b for b in re.split(pattern, text) if b.startswith(level + " ")]


def _between(text: str, start: str, end: str) -> str:
    """start 제목부터 end 제목 전까지. 제목이 없으면 빈 문자열 (형식이 다른 정리본도 오류 없이)."""
    i = text.find(start)
    if i < 0:
        return ""
    j = text.find(end, i + len(start))
    return text[i:j if j >= 0 else len(text)]


def tutor_reference(path: Path | None = None) -> str | None:
    """정리본에서 02강 관련 절과 핵심 공식 B~E 만 잘라 하나의 문자열로 반환.

    정리본 파일이 없거나(공개 저장소 버전) 해당 절을 하나도 찾지 못하면 None.
    강의자료 저작권 때문에 정리본은 저장소에 포함하지 않는다 (.gitignore).
    """
    path = path or NOTES_PATH
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")

    parts = []
    for block in _split_by_heading(_between(text, "## 02.", "## 03."), "###"):
        if block.split()[1] in TUTOR_SECTIONS:
            parts.append(block.strip())
    for block in _split_by_heading(_between(text, "## 핵심 공식 모음", "## 핵심 개념"), "###"):
        if block.split()[1].rstrip(".") in TUTOR_FORMULA_BLOCKS:
            parts.append(block.strip())
    if not parts:
        return None
    return "\n\n".join(parts).replace("\n---", "")


CUSTOM = "직접 입력"

# source: 정리본에 값이 있으면 페이지, 없으면 "대표값" (일반적으로 쓰이는 값, 정리본 외)
MATERIAL_PRESETS = {
    "콘크리트 (예제 p.29, k=1.0)": {"name": "콘크리트", "k": 1.0, "source": "정리본 02강 p.29"},
    "콘크리트 (p.21, k=1.5)": {"name": "콘크리트", "k": 1.5, "source": "정리본 02강 p.21"},
    "단열재 (예제 p.29, k=0.02)": {"name": "단열재", "k": 0.02, "source": "정리본 02강 p.29"},
    "단열재 (p.21, k=0.03)": {"name": "단열재", "k": 0.03, "source": "정리본 02강 p.21"},
    "단열재 (일반값 p.14, k=0.04)": {"name": "단열재", "k": 0.04, "source": "정리본 02강 p.14 수업 메모"},
    "목재 (예제 p.29, k=0.1)": {"name": "목재", "k": 0.1, "source": "정리본 02강 p.29"},
    "벽돌 (대표값, k=0.6)": {"name": "벽돌", "k": 0.6, "source": "대표값"},
    "석고보드 (대표값, k=0.18)": {"name": "석고보드", "k": 0.18, "source": "대표값"},
    "시멘트 모르타르 (대표값, k=1.4)": {"name": "모르타르", "k": 1.4, "source": "대표값"},
    "합판 (대표값, k=0.15)": {"name": "합판", "k": 0.15, "source": "대표값"},
    CUSTOM: {"name": "사용자 재료", "k": 0.5, "source": "사용자 입력"},
}

# "정리본 예제 불러오기" (02강 p.29~30): 표면온도 모드, T_os=40, T_is=10
TEXTBOOK_EXAMPLE = {
    "T_os": 40.0,
    "T_is": 10.0,
    "layers": [
        ("콘크리트 (예제 p.29, k=1.0)", 0.40),
        ("단열재 (예제 p.29, k=0.02)", 0.05),
        ("목재 (예제 p.29, k=0.1)", 0.15),
    ],
}

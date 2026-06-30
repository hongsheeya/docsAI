#!/usr/bin/env python3
"""Generate a side-by-side code/explanation browser for non-technical review."""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "docs" / "code-explorer"
OUTPUT_HTML = OUTPUT_DIR / "index.html"

INCLUDE_ROOT_FILES = {
    "README.md",
    "manual.md",
    "PROJECT_OVERVIEW.md",
    "package.json",
}
INCLUDE_DIRS = ["config", "src", "scripts"]
TEXT_EXTENSIONS = {
    ".py",
    ".ts",
    ".js",
    ".pug",
    ".scss",
    ".css",
    ".html",
    ".json",
    ".md",
    ".sh",
    ".svg",
}
SKIP_DIR_PARTS = {
    ".git",
    "__pycache__",
    "node_modules",
    "build",
    "bundle",
    "dist",
    "outputs",
    "storage",
    "data",
    "_appdata",
    ".pytest_cache",
}
SKIP_PATH_PREFIXES = {
    "src/assets/font/",
    "src/assets/pres/",
    "src/portal/season/libs/ckeditor/",
    "src/portal/season/libs/ngx-sortablejs/",
}
SKIP_SUFFIXES = {
    ".pyc",
    ".pt",
    ".pth",
    ".pkl",
    ".joblib",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".ico",
    ".woff2",
    ".otf",
    ".pptx",
    ".pdf",
    ".db",
    ".sqlite",
    ".mp4",
    ".webm",
    ".zip",
    ".tar",
    ".gz",
}
SKIP_FILE_NAMES = {
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
}


@dataclass
class CodeFile:
    path: str
    content: str
    line_count: int
    size: int
    role: str
    explanation: str
    bullets: list[str]
    symbols: list[tuple[int, str, str]]


ROLE_RULES = [
    ("src/app/page.dashboard/", "메인 분석 화면", "영상 업로드, 웹캠 분석, 스켈레톤 표시, 다중 인원 결과, 학습 등록을 담당합니다."),
    ("src/app/page.models/", "모델 관리 화면", "운영 모델 버전, 성능 수치, 백그라운드 학습 상태, 모델 등록/삭제, 감도 조절을 담당합니다."),
    ("src/app/page.pipeline/", "파이프라인 설명 화면", "AI가 영상을 어떤 순서로 처리하는지, 프레임/RTT/4카메라 검증을 설명합니다."),
    ("src/app/page.admin.analysis/", "관리자 분석 설정", "보호자 알림, 분석 정책, 학습 데이터 등록 같은 관리자 기능을 담당합니다."),
    ("src/app/page.admin.llm/", "LLM 설정", "AI 설명 문장 생성 관련 설정과 상태를 관리합니다."),
    ("src/app/page.access/", "로그인 화면", "사용자의 이메일과 비밀번호를 확인해 세션을 만듭니다."),
    ("src/app/page.members/", "멤버 관리", "사용자 목록, 초대, 역할 관리를 담당합니다."),
    ("src/app/page.mypage/", "마이페이지", "내 프로필과 비밀번호 변경 기능을 담당합니다."),
    ("src/app/page.posts", "게시판 연결 화면", "게시판 목록과 상세 화면으로 연결하는 화면입니다."),
    ("src/app/page.manual/", "사용 설명서 화면", "사이트 안에서 사용 방법과 기능 설명을 보여줍니다."),
    ("src/app/component.nav.sidebar/", "사이드바 메뉴", "사용자가 각 화면으로 이동할 수 있는 왼쪽 메뉴입니다."),
    ("src/app/layout.sidebar/", "기본 레이아웃", "사이드바와 본문 영역이 있는 전체 화면 틀입니다."),
    ("src/app/layout.empty/", "빈 레이아웃", "로그인처럼 별도 메뉴가 필요 없는 화면 틀입니다."),
    ("src/model/struct/video_analysis.py", "AI 분석 핵심 로직", "영상을 받아 사람을 찾고, 자세/낙상/표정/상태 결과와 학습 상태를 묶어 화면에 돌려주는 중심 코드입니다."),
    ("src/model/libs/video_baseline.py", "낙상 모델 학습 보조", "낙상/비낙상 feature를 만들고 RandomForest 계열 모델을 학습·평가합니다."),
    ("src/model/libs/action_behavior_model.py", "행동/자세 라벨 정의", "서기, 걷기, 뛰기, 앉기, 눕기, 낙상 같은 행동 이름과 기준을 정리합니다."),
    ("src/model/struct/user.py", "사용자 기능", "로그인, 사용자 조회, 초대, 비밀번호 변경 같은 회원 기능을 처리합니다."),
    ("src/model/db/", "데이터베이스 테이블", "사용자나 게시글처럼 저장할 데이터의 모양을 정의합니다."),
    ("src/model/struct.py", "프로젝트 중앙 연결부", "사용자 기능, 영상 분석 기능, 포털 패키지를 한곳에서 연결합니다."),
    ("src/controller/", "접근 권한 확인", "로그인 여부와 관리자 권한을 확인하는 출입문 역할입니다."),
    ("src/portal/post/", "게시판 패키지", "게시글 목록, 상세, 댓글, 저장/삭제 기능을 제공합니다."),
    ("src/portal/season/", "공통 기반 패키지", "세션, ORM, 공통 UI, 인증 등 여러 화면에서 쓰는 기반 기능입니다."),
    ("src/angular/", "Angular/WIZ 실행 엔진", "WIZ 페이지를 브라우저 앱으로 묶어 실행하는 Angular 설정과 시작점입니다."),
    ("scripts/train_facial_emotion_aihub82.py", "표정 모델 학습", "AI-Hub 82 표정 데이터를 읽어 표정 보조 모델을 학습하고 성능을 계산합니다."),
    ("scripts/continuous_aihub82_training_supervisor.py", "표정 모델 상시 학습 감독", "학습 실험을 반복 실행하고 좋아진 후보만 승격하며 진행률과 병목을 기록합니다."),
    ("scripts/simulate_four_camera_tracking.py", "4카메라 시뮬레이션", "한 영상을 네 코너 카메라처럼 변환해 추적 성능과 RTT를 측정합니다."),
    ("scripts/benchmark_multiperson_frame_processing.py", "다중 인원 성능 측정", "여러 사람이 있을 때 프레임 처리 속도와 병목을 측정합니다."),
    ("scripts/", "운영/학습 도구", "모델 학습, 평가, 복구, 발표자료 생성, 데이터 점검을 실행하는 보조 스크립트입니다."),
    ("config/", "프로젝트 설정", "WIZ/PWA 같은 프로젝트 기본 설정입니다."),
]

EXT_HINTS = {
    ".py": "Python 서버/AI/학습 코드입니다. 함수가 실제 처리를 수행합니다.",
    ".ts": "TypeScript 화면 동작 코드입니다. 버튼 클릭, API 호출, 화면 상태 변경을 담당합니다.",
    ".pug": "화면 구조 템플릿입니다. 버튼, 카드, 표가 어디에 놓일지 정합니다.",
    ".scss": "해당 화면의 디자인 규칙입니다. 색상, 간격, 스크롤, 반응형 배치를 정합니다.",
    ".html": "문서형 화면 또는 정적 HTML입니다.",
    ".json": "주소, 레이아웃, 설정, 데이터 구조를 정해진 형식으로 저장한 파일입니다.",
    ".md": "사람이 읽는 설명 문서입니다.",
    ".sh": "서버에서 실행하는 쉘 작업 스크립트입니다.",
    ".svg": "확대해도 깨지지 않는 벡터 이미지입니다.",
}


def should_include(path: Path) -> bool:
    rel = path.relative_to(PROJECT_ROOT).as_posix()
    rel_parts = Path(rel).parts
    if path.name in SKIP_FILE_NAMES:
        return False
    if any(part in SKIP_DIR_PARTS for part in rel_parts):
        return False
    if any(rel.startswith(prefix) for prefix in SKIP_PATH_PREFIXES):
        return False
    if rel in INCLUDE_ROOT_FILES:
        return True
    if not any(rel == root or rel.startswith(f"{root}/") for root in INCLUDE_DIRS):
        return False
    suffix = path.suffix.lower()
    if suffix in SKIP_SUFFIXES:
        return False
    if suffix not in TEXT_EXTENSIONS:
        return False
    try:
        if path.stat().st_size > 900_000:
            return False
    except OSError:
        return False
    return True


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def role_for(rel: str) -> tuple[str, str]:
    for prefix, role, explanation in ROLE_RULES:
        if rel == prefix.rstrip("/") or rel.startswith(prefix):
            return role, explanation
    if rel in INCLUDE_ROOT_FILES:
        return "프로젝트 대표 문서", "프로젝트 목적, 실행 방법, 구조를 설명하는 입구 문서입니다."
    return "보조 코드", "프로젝트의 특정 설정이나 보조 기능을 담당합니다."


def file_bullets(rel: str, content: str) -> list[str]:
    suffix = Path(rel).suffix.lower()
    bullets = [EXT_HINTS.get(suffix, "프로젝트에서 사용하는 텍스트 기반 파일입니다.")]
    if rel.endswith("app.json"):
        bullets.append("이 화면의 주소, 레이아웃, 접근 권한을 WIZ에 알려주는 설정 파일입니다.")
    if rel.endswith("api.py"):
        bullets.append("브라우저 화면에서 보낸 요청을 받아 Python 분석/저장 로직으로 넘기는 서버 접수창구입니다.")
    if rel.endswith("view.ts"):
        bullets.append("사용자 클릭, 입력, API 응답을 화면 상태로 바꾸는 동작 코드입니다.")
    if rel.endswith("view.pug"):
        bullets.append("실제 사용자가 보는 화면의 구조를 만드는 파일입니다.")
    if rel.endswith("view.scss"):
        bullets.append("해당 화면 전용 디자인을 조정하는 파일입니다.")
    if "wiz.call" in content or "fetch(" in content:
        bullets.append("화면에서 서버 API를 호출하는 코드가 포함되어 있습니다.")
    if "wiz.response.status" in content:
        bullets.append("서버가 브라우저로 JSON 응답을 돌려주는 코드가 포함되어 있습니다.")
    if "RandomForest" in content or "XGB" in content or "YOLO" in content or "torch" in content:
        bullets.append("AI 모델 학습 또는 추론과 직접 관련된 코드가 포함되어 있습니다.")
    if "ngFor" in content or "*ngFor" in content:
        bullets.append("목록 데이터를 반복해서 카드나 표로 보여주는 화면 코드가 포함되어 있습니다.")
    if "session" in content.lower():
        bullets.append("로그인 상태 또는 사용자 세션과 관련된 처리가 포함되어 있습니다.")
    return bullets


def extract_symbols(content: str, suffix: str) -> list[tuple[int, str, str]]:
    symbols: list[tuple[int, str, str]] = []
    lines = content.splitlines()
    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()
        if suffix == ".py":
            match = re.match(r"(class|def)\s+([A-Za-z_][A-Za-z0-9_]*)", stripped)
            if match:
                kind, name = match.groups()
                label = "클래스" if kind == "class" else "함수"
                symbols.append((idx, f"{label} `{name}`", explain_symbol(name, kind)))
        elif suffix in {".ts", ".js"}:
            match = re.match(r"(export\s+)?(class|function)\s+([A-Za-z_][A-Za-z0-9_]*)", stripped)
            if match:
                _, kind, name = match.groups()
                label = "클래스" if kind == "class" else "함수"
                symbols.append((idx, f"{label} `{name}`", explain_symbol(name, kind)))
            match = re.match(r"(const|let|var)\s+([A-Za-z_][A-Za-z0-9_]*)", stripped)
            if match and len(symbols) < 80:
                _, name = match.groups()
                symbols.append((idx, f"값 `{name}`", explain_symbol(name, "value")))
        elif suffix == ".json":
            if stripped.startswith('"id"') or stripped.startswith('"viewuri"') or stripped.startswith('"controller"') or stripped.startswith('"layout"'):
                key = stripped.split(":", 1)[0].strip('"')
                symbols.append((idx, f"설정 `{key}`", explain_symbol(key, "config")))
    return symbols[:120]


def explain_symbol(name: str, kind: str) -> str:
    lower = name.lower()
    hints = [
        ("analyze", "영상을 분석하거나 분석 결과를 만드는 부분입니다."),
        ("training", "학습 데이터나 학습 진행 상태를 다루는 부분입니다."),
        ("model", "AI 모델 파일, 모델 목록, 모델 선택과 관련된 부분입니다."),
        ("registry", "등록된 모델과 버전 정보를 모아 보여주는 부분입니다."),
        ("upload", "사용자가 올린 파일을 받거나 저장하는 부분입니다."),
        ("status", "현재 상태를 화면에 알려주는 부분입니다."),
        ("user", "사용자 계정이나 권한과 관련된 부분입니다."),
        ("session", "로그인 유지 상태를 다루는 부분입니다."),
        ("render", "화면을 다시 그리거나 상태를 반영하는 부분입니다."),
        ("save", "설정이나 데이터를 저장하는 부분입니다."),
        ("delete", "데이터나 모델을 삭제 또는 삭제 대기 처리하는 부분입니다."),
        ("evaluate", "성능을 평가하고 수치를 계산하는 부분입니다."),
        ("simulate", "실제 환경을 가정한 실험을 실행하는 부분입니다."),
        ("report", "결과를 사람이 읽는 보고서로 정리하는 부분입니다."),
    ]
    for needle, text in hints:
        if needle in lower:
            return text
    if kind == "class":
        return "관련 기능과 상태를 하나로 묶어 관리하는 큰 단위입니다."
    if kind == "config":
        return "WIZ가 화면을 연결할 때 사용하는 설정값입니다."
    return "해당 파일 안에서 반복해서 쓰는 처리 단위입니다."


def build_code_lines(content: str) -> str:
    rows = []
    for idx, line in enumerate(content.splitlines(), start=1):
        rows.append(
            f'<tr><td class="line-no">{idx}</td><td class="code-line"><code>{html.escape(line) or " "}</code></td></tr>'
        )
    if not rows:
        rows.append('<tr><td class="line-no">1</td><td class="code-line"><code> </code></td></tr>')
    return "\n".join(rows)


def line_note_for(rel: str, line: str) -> str:
    """Create a short non-technical note for a source line in the generated guide."""
    suffix = Path(rel).suffix.lower()
    stripped = line.strip()
    if not stripped:
        return ""

    comment_prefixes = ("#", "//", "//-", "/*", "*", "<!--")
    if stripped.startswith(comment_prefixes):
        return "개발자가 사람에게 남긴 설명 또는 구분 표시입니다."
    if stripped.startswith(("import ", "from ")) or re.match(r"import\s+.+\s+from\s+", stripped):
        return "다른 파일이나 외부 라이브러리의 기능을 가져옵니다."
    if stripped.startswith(("@", "@@")):
        return "바로 아래 코드에 적용되는 설정 또는 장식입니다."
    if stripped.startswith(("class ", "export class ")):
        return "관련 데이터와 동작을 하나로 묶는 큰 코드 단위입니다."
    if re.match(r"(async\s+)?def\s+[A-Za-z_][A-Za-z0-9_]*", stripped):
        return "반복해서 호출되는 서버/AI 처리 절차입니다."
    if re.match(r"(public|private|protected)?\s*(async\s+)?[A-Za-z_][A-Za-z0-9_]*\s*\(", stripped):
        return "화면 안에서 반복해서 호출되는 동작 함수입니다."
    if stripped.startswith(("if ", "if (", "*ngIf")) or "*ngIf" in stripped:
        return "조건이 맞을 때만 다음 처리를 하거나 화면에 보여줍니다."
    if stripped.startswith(("elif ", "else if", "else:")):
        return "앞 조건이 맞지 않을 때의 다른 경우를 처리합니다."
    if stripped.startswith(("for ", "while ", "*ngFor")) or "*ngFor" in stripped:
        return "목록이나 반복 작업을 한 항목씩 처리합니다."
    if stripped.startswith(("try:", "try {")):
        return "실패할 수 있는 작업을 안전하게 시도합니다."
    if stripped.startswith(("except", "catch")):
        return "오류가 나도 화면이나 서버가 멈추지 않도록 처리합니다."
    if stripped.startswith(("return ", "return;")):
        return "계산하거나 만든 결과를 호출한 쪽으로 돌려줍니다."
    if stripped.startswith(("raise ", "throw ")):
        return "문제가 생겼음을 위쪽 처리 흐름에 알립니다."

    if "wiz.call" in stripped or "fetch(" in stripped:
        return "브라우저 화면에서 서버 API를 호출합니다."
    if "wiz.response.status" in stripped or "wiz.response" in stripped:
        return "서버 처리 결과를 브라우저로 돌려줍니다."
    if "wiz.model" in stripped:
        return "WIZ 모델 계층의 기능을 불러와 사용합니다."
    if "routerLink" in stripped:
        return "사용자가 클릭하면 이동할 사이트 안 주소입니다."
    if "MediaRecorder" in stripped or "getUserMedia" in stripped:
        return "브라우저 카메라/녹화 기능을 사용합니다."
    if "localStorage" in stripped or "sessionStorage" in stripped:
        return "브라우저 안에 최근 상태를 임시 저장합니다."
    if "RandomForest" in stripped or "XGB" in stripped or "YOLO" in stripped or "torch" in stripped:
        return "AI 모델 학습 또는 추론과 연결되는 부분입니다."
    if "os.environ" in stripped:
        return "서버 환경변수로 기능을 켜고 끄거나 값을 조정합니다."
    if "json" in stripped.lower():
        return "정해진 JSON 형식으로 데이터를 읽거나 씁니다."
    if "Path(" in stripped or ".open(" in stripped or "read_text" in stripped or "write_text" in stripped:
        return "서버 파일을 읽거나 저장하는 처리입니다."
    if "subprocess" in stripped or "Popen" in stripped:
        return "학습/평가 같은 별도 실행 작업을 시작합니다."
    if "setInterval" in stripped or "setTimeout" in stripped:
        return "일정 시간 뒤 또는 주기적으로 실행합니다."

    if suffix == ".json" and stripped.startswith('"'):
        return "WIZ나 앱이 읽는 설정값입니다."
    if suffix == ".pug":
        if stripped.startswith(("div", "section", "nav", "button", "a(", "span", "p(", "h1", "h2", "h3", "input", "video", "canvas")):
            return "사용자 화면에 보이는 요소를 배치합니다."
    if suffix == ".scss":
        if stripped.endswith("{"):
            return "아래 디자인 규칙이 적용될 화면 영역을 고릅니다."
        if ":" in stripped and stripped.endswith(";"):
            return "색상, 간격, 크기 같은 화면 스타일 값을 정합니다."
    if suffix in {".ts", ".js", ".py"} and re.match(r"^[A-Za-z_][A-Za-z0-9_.$\[\]'\"-]*\s*[:=]", stripped):
        return "나중에 쓰기 위해 값을 이름에 담아 둡니다."
    return ""


def collect_files() -> list[CodeFile]:
    paths = [p for p in PROJECT_ROOT.rglob("*") if p.is_file() and should_include(p)]
    files: list[CodeFile] = []
    for path in sorted(paths, key=lambda p: p.relative_to(PROJECT_ROOT).as_posix()):
        rel = path.relative_to(PROJECT_ROOT).as_posix()
        content = read_text(path)
        role, explanation = role_for(rel)
        files.append(
            CodeFile(
                path=rel,
                content=content,
                line_count=max(1, len(content.splitlines())),
                size=path.stat().st_size,
                role=role,
                explanation=explanation,
                bullets=file_bullets(rel, content),
                symbols=extract_symbols(content, path.suffix.lower()),
            )
        )
    return files


def render_file_section(file: CodeFile, index: int) -> str:
    file_id = f"file-{index}"
    bullets = "\n".join(f"<li>{html.escape(item)}</li>" for item in file.bullets)
    if file.symbols:
        symbols = "\n".join(
            f'<li><a href="#{file_id}-L{line}">L{line}</a> <strong>{label}</strong><span>{html.escape(desc)}</span></li>'
            for line, label, desc in file.symbols
        )
    else:
        symbols = "<li>자동으로 잡힌 함수/클래스는 없지만, 파일 전체가 설정 또는 화면 구조로 사용됩니다.</li>"
    code_rows = []
    for line_no, line in enumerate(file.content.splitlines(), start=1):
        note = line_note_for(file.path, line)
        code_rows.append(
            f'<tr id="{file_id}-L{line_no}"><td class="line-no">{line_no}</td><td class="code-line"><code>{html.escape(line) or " "}</code></td><td class="line-note">{html.escape(note) or " "}</td></tr>'
        )
    if not code_rows:
        code_rows.append(f'<tr id="{file_id}-L1"><td class="line-no">1</td><td class="code-line"><code> </code></td><td class="line-note"> </td></tr>')
    return f"""
<section class="file-card" id="{file_id}" data-path="{html.escape(file.path.lower())}" data-role="{html.escape(file.role.lower())}">
  <header class="file-head">
    <div>
      <p class="file-role">{html.escape(file.role)}</p>
      <h2>{html.escape(file.path)}</h2>
    </div>
    <div class="file-meta">{file.line_count:,} lines · {file.size:,} bytes</div>
  </header>
  <div class="file-grid">
    <div class="code-pane" aria-label="{html.escape(file.path)} 원본 코드">
      <table class="code-table"><tbody>
        {"".join(code_rows)}
      </tbody></table>
    </div>
    <aside class="explain-pane" aria-label="{html.escape(file.path)} 쉬운 설명">
      <h3>이 파일이 하는 일</h3>
      <p>{html.escape(file.explanation)}</p>
      <h3>읽을 때 볼 포인트</h3>
      <ul>{bullets}</ul>
      <h3>주요 코드 위치</h3>
      <ul class="symbol-list">{symbols}</ul>
    </aside>
  </div>
</section>
"""


def render(files: list[CodeFile]) -> str:
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    total_lines = sum(file.line_count for file in files)
    nav = "\n".join(
        f'<a href="#file-{idx}"><span>{html.escape(file.path)}</span><small>{html.escape(file.role)}</small></a>'
        for idx, file in enumerate(files)
    )
    sections = "\n".join(render_file_section(file, idx) for idx, file in enumerate(files))
    manifest = {
        "generated_at": generated,
        "file_count": len(files),
        "total_lines": total_lines,
        "excluded": [
            "node_modules, build, bundle, storage, outputs, data",
            "AI-Hub 원본 데이터, 업로드 영상, 모델 가중치, 이미지/폰트/대용량 바이너리",
            "외부 CKEditor/ngx-sortablejs vendor 코드",
        ],
    }
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>FallAI 전체 코드 + 비전공자 설명</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --line: #d9dee8;
      --ink: #1f2328;
      --muted: #69707d;
      --accent: #0f766e;
      --soft: #e8f5f2;
      --code: #0f172a;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: var(--bg); color: var(--ink); }}
    a {{ color: inherit; }}
    .layout {{ display: grid; grid-template-columns: 320px minmax(0, 1fr); min-height: 100vh; }}
    .sidebar {{ position: sticky; top: 0; height: 100vh; overflow: auto; padding: 20px; border-right: 1px solid var(--line); background: #111827; color: #f9fafb; }}
    .sidebar h1 {{ margin: 0 0 8px; font-size: 20px; line-height: 1.3; }}
    .sidebar p {{ margin: 0 0 16px; color: #cbd5e1; font-size: 13px; line-height: 1.6; }}
    .stats {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin: 16px 0; }}
    .stat {{ border: 1px solid rgba(255,255,255,.12); border-radius: 8px; padding: 10px; background: rgba(255,255,255,.05); }}
    .stat strong {{ display: block; font-size: 18px; }}
    .stat span {{ color: #cbd5e1; font-size: 11px; }}
    .search {{ width: 100%; border: 1px solid rgba(255,255,255,.16); border-radius: 8px; background: rgba(255,255,255,.08); color: #fff; padding: 10px 12px; outline: none; }}
    .nav-list {{ display: grid; gap: 6px; margin-top: 14px; }}
    .nav-list a {{ display: block; padding: 9px 10px; border-radius: 8px; text-decoration: none; background: rgba(255,255,255,.05); }}
    .nav-list a:hover {{ background: rgba(45,212,191,.18); }}
    .nav-list span {{ display: block; font-size: 12px; word-break: break-all; }}
    .nav-list small {{ display: block; margin-top: 3px; color: #9ca3af; font-size: 11px; }}
    main {{ padding: 28px; }}
    .hero {{ max-width: 1200px; margin: 0 auto 20px; padding: 24px; border: 1px solid var(--line); border-radius: 10px; background: var(--panel); }}
    .hero h1 {{ margin: 0 0 10px; font-size: 28px; }}
    .hero p {{ margin: 0; color: var(--muted); line-height: 1.7; }}
    .notice {{ margin-top: 14px; padding: 12px 14px; border-radius: 8px; background: #fff7ed; border: 1px solid #fed7aa; color: #9a3412; font-size: 13px; line-height: 1.6; }}
    .file-card {{ max-width: 1200px; margin: 0 auto 22px; border: 1px solid var(--line); border-radius: 10px; background: var(--panel); overflow: hidden; }}
    .file-head {{ display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; padding: 18px 20px; border-bottom: 1px solid var(--line); }}
    .file-role {{ margin: 0 0 4px; color: var(--accent); font-size: 12px; font-weight: 700; }}
    .file-head h2 {{ margin: 0; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 16px; word-break: break-all; }}
    .file-meta {{ color: var(--muted); font-size: 12px; white-space: nowrap; }}
    .file-grid {{ display: grid; grid-template-columns: minmax(0, 1.45fr) minmax(280px, .75fr); min-height: 260px; }}
    .code-pane {{ overflow: auto; max-height: 720px; background: #0b1020; color: #dbeafe; }}
    .code-table {{ border-collapse: collapse; width: 100%; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; line-height: 1.55; }}
    .code-table tr:target {{ background: rgba(45,212,191,.18); }}
    .line-no {{ width: 58px; min-width: 58px; padding: 0 10px; text-align: right; color: #64748b; border-right: 1px solid rgba(255,255,255,.08); user-select: none; vertical-align: top; }}
    .code-line {{ padding: 0 14px; white-space: pre; vertical-align: top; }}
    .code-line code {{ font-family: inherit; }}
    .line-note {{ width: 280px; min-width: 280px; padding: 0 12px; border-left: 1px solid rgba(255,255,255,.08); color: #93c5fd; white-space: normal; vertical-align: top; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    .explain-pane {{ border-left: 1px solid var(--line); padding: 18px; background: #fbfcfd; }}
    .explain-pane h3 {{ margin: 0 0 8px; font-size: 14px; }}
    .explain-pane p, .explain-pane li {{ color: #4b5563; font-size: 13px; line-height: 1.65; }}
    .explain-pane ul {{ margin: 0 0 18px; padding-left: 18px; }}
    .symbol-list li {{ margin-bottom: 8px; }}
    .symbol-list a {{ display: inline-block; margin-right: 6px; color: var(--accent); font-weight: 700; text-decoration: none; }}
    .symbol-list strong {{ display: inline-block; margin-right: 4px; color: #111827; }}
    .symbol-list span {{ display: block; margin-top: 2px; }}
    .hidden {{ display: none !important; }}
    @media (max-width: 980px) {{
      .layout {{ display: block; }}
      .sidebar {{ position: relative; width: auto; height: auto; max-height: 420px; }}
      main {{ padding: 16px; }}
      .file-grid {{ grid-template-columns: 1fr; }}
      .explain-pane {{ border-left: 0; border-top: 1px solid var(--line); }}
    }}
  </style>
</head>
<body>
  <div class="layout">
    <aside class="sidebar">
      <h1>FallAI 전체 코드 탐색</h1>
      <p>왼쪽 목록에서 파일을 고르면 원본 코드 전체와 쉬운 설명을 함께 볼 수 있습니다.</p>
      <div class="stats">
        <div class="stat"><strong>{len(files):,}</strong><span>included files</span></div>
        <div class="stat"><strong>{total_lines:,}</strong><span>source lines</span></div>
      </div>
      <input class="search" id="search" type="search" placeholder="파일명/역할 검색">
      <nav class="nav-list" id="navList">{nav}</nav>
    </aside>
    <main>
      <section class="hero">
        <h1>FallAI 전체 코드 + 비전공자용 설명</h1>
        <p>생성 시각: {generated}. 이 문서는 교수님이 GitHub에서 실제 코드를 보면서 줄별 쉬운 해석, 파일 설명, 주요 함수 위치를 함께 확인할 수 있게 만든 코드 탐색 페이지입니다.</p>
        <div class="notice">보안과 용량 문제 때문에 `node_modules`, `build`, `storage`, `outputs`, AI-Hub 원본 데이터, 업로드 영상, 모델 가중치, 이미지/폰트/대용량 바이너리, 외부 vendor 코드는 제외했습니다. 직접 작성한 서비스 코드, 서버 코드, AI/학습 스크립트, 설정 파일은 포함했습니다.</div>
      </section>
      {sections}
    </main>
  </div>
  <script type="application/json" id="manifest">{html.escape(json.dumps(manifest, ensure_ascii=False, indent=2))}</script>
  <script>
    const search = document.getElementById('search');
    const cards = Array.from(document.querySelectorAll('.file-card'));
    const links = Array.from(document.querySelectorAll('.nav-list a'));
    search.addEventListener('input', () => {{
      const q = search.value.trim().toLowerCase();
      cards.forEach(card => {{
        const match = !q || card.dataset.path.includes(q) || card.dataset.role.includes(q);
        card.classList.toggle('hidden', !match);
      }});
      links.forEach(link => {{
        const text = link.innerText.toLowerCase();
        link.classList.toggle('hidden', q && !text.includes(q));
      }});
    }});
  </script>
</body>
</html>
"""


def main() -> int:
    files = collect_files()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_HTML.write_text(render(files), encoding="utf-8")
    print(f"generated {OUTPUT_HTML}")
    print(f"files={len(files)} lines={sum(file.line_count for file in files)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

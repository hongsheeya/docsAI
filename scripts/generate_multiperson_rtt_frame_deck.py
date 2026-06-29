#!/usr/bin/env python3
from pathlib import Path

from pptx import Presentation
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor


OUT_DIR = Path("/opt/app/project/main/docs/presentation")
PPTX_PATH = OUT_DIR / "2026-06-22-fallai-multiperson-rtt-frame-guide.pptx"
MD_PATH = OUT_DIR / "2026-06-22-fallai-multiperson-rtt-frame-guide.md"


NAVY = RGBColor(24, 49, 79)
BLUE = RGBColor(36, 71, 107)
TEAL = RGBColor(17, 128, 106)
GOLD = RGBColor(168, 121, 22)
MUTED = RGBColor(91, 102, 120)
LINE = RGBColor(217, 226, 236)
SOFT = RGBColor(245, 248, 251)
WHITE = RGBColor(255, 255, 255)
RED = RGBColor(182, 58, 58)


def set_fill(shape, color):
    shape.fill.solid()
    shape.fill.fore_color.rgb = color


def set_line(shape, color=LINE, width=1):
    shape.line.color.rgb = color
    shape.line.width = Pt(width)


def add_textbox(slide, x, y, w, h, text="", font_size=18, color=NAVY, bold=False, align=None):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.clear()
    p = tf.paragraphs[0]
    p.text = text
    p.font.size = Pt(font_size)
    p.font.bold = bold
    p.font.color.rgb = color
    p.font.name = "Malgun Gothic"
    if align:
        p.alignment = align
    return box


def add_title(slide, title, kicker=None):
    if kicker:
        add_textbox(slide, 0.62, 0.35, 11.2, 0.3, kicker, 11, TEAL, True)
    add_textbox(slide, 0.62, 0.72, 11.4, 0.62, title, 25, NAVY, True)
    line = slide.shapes.add_shape(1, Inches(0.62), Inches(1.45), Inches(11.1), Inches(0.01))
    set_fill(line, LINE)
    set_line(line, LINE, 0)


def add_bullets(slide, x, y, w, h, bullets, font_size=15, color=RGBColor(51, 65, 85)):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.clear()
    tf.word_wrap = True
    for idx, text in enumerate(bullets):
        p = tf.paragraphs[0] if idx == 0 else tf.add_paragraph()
        p.text = text
        p.level = 0
        p.font.size = Pt(font_size)
        p.font.name = "Malgun Gothic"
        p.font.color.rgb = color
        p.space_after = Pt(8)
    return box


def add_card(slide, x, y, w, h, title, body, accent=TEAL):
    shape = slide.shapes.add_shape(1, Inches(x), Inches(y), Inches(w), Inches(h))
    set_fill(shape, WHITE)
    set_line(shape, LINE)
    bar = slide.shapes.add_shape(1, Inches(x), Inches(y), Inches(0.08), Inches(h))
    set_fill(bar, accent)
    set_line(bar, accent, 0)
    add_textbox(slide, x + 0.18, y + 0.16, w - 0.35, 0.28, title, 12, accent, True)
    add_textbox(slide, x + 0.18, y + 0.52, w - 0.35, h - 0.62, body, 14, RGBColor(51, 65, 85), False)


def add_table(slide, x, y, w, h, headers, rows, font_size=10):
    table = slide.shapes.add_table(len(rows) + 1, len(headers), Inches(x), Inches(y), Inches(w), Inches(h)).table
    for col_idx, header in enumerate(headers):
        cell = table.cell(0, col_idx)
        cell.text = header
        set_fill(cell, NAVY)
        for p in cell.text_frame.paragraphs:
            p.font.name = "Malgun Gothic"
            p.font.size = Pt(font_size)
            p.font.bold = True
            p.font.color.rgb = WHITE
    for row_idx, row in enumerate(rows, start=1):
        for col_idx, value in enumerate(row):
            cell = table.cell(row_idx, col_idx)
            cell.text = str(value)
            set_fill(cell, SOFT if row_idx % 2 == 0 else WHITE)
            for p in cell.text_frame.paragraphs:
                p.font.name = "Malgun Gothic"
                p.font.size = Pt(font_size)
                p.font.color.rgb = RGBColor(51, 65, 85)
    return table


def add_bar_chart(slide, x, y, w, h, labels, values, max_value, title, unit="", color=TEAL):
    add_textbox(slide, x, y, w, 0.28, title, 13, NAVY, True)
    base_y = y + 0.5
    row_h = (h - 0.5) / len(labels)
    for idx, (label, value) in enumerate(zip(labels, values)):
        cy = base_y + idx * row_h
        add_textbox(slide, x, cy, 1.0, 0.25, str(label), 10, MUTED, True)
        track = slide.shapes.add_shape(1, Inches(x + 1.05), Inches(cy + 0.03), Inches(w - 2.05), Inches(0.16))
        set_fill(track, RGBColor(232, 238, 245))
        set_line(track, RGBColor(232, 238, 245), 0)
        bw = max(0.03, (w - 2.05) * min(float(value) / max_value, 1.0))
        bar = slide.shapes.add_shape(1, Inches(x + 1.05), Inches(cy + 0.03), Inches(bw), Inches(0.16))
        set_fill(bar, color)
        set_line(bar, color, 0)
        add_textbox(slide, x + w - 0.85, cy - 0.01, 0.85, 0.25, f"{value}{unit}", 10, NAVY, True, PP_ALIGN.RIGHT)


def add_footer(slide, page):
    add_textbox(slide, 0.62, 7.08, 5.0, 0.2, "FallAI 다중 인원 RTT/프레임 처리 발표자료", 8, MUTED)
    add_textbox(slide, 11.5, 7.08, 0.8, 0.2, f"{page:02d}", 8, MUTED, False, PP_ALIGN.RIGHT)


def build_deck():
    prs = Presentation()
    prs.slide_width = Inches(12.8)
    prs.slide_height = Inches(7.2)
    blank = prs.slide_layouts[6]
    page = 1

    def slide(title=None, kicker=None):
        nonlocal page
        s = prs.slides.add_slide(blank)
        bg = s.background
        bg.fill.solid()
        bg.fill.fore_color.rgb = WHITE
        if title:
            add_title(s, title, kicker)
        add_footer(s, page)
        page += 1
        return s

    s = slide()
    set_fill(s.shapes.add_shape(1, Inches(0), Inches(0), Inches(12.8), Inches(7.2)), SOFT)
    add_textbox(s, 0.72, 0.8, 10.6, 0.35, "FallAI Commercial Readiness", 13, TEAL, True)
    add_textbox(s, 0.72, 1.28, 10.9, 1.2, "인원수별 RTT와 프레임 처리 전략", 34, NAVY, True)
    add_textbox(s, 0.76, 2.48, 9.9, 0.65, "다중 인원 표시, 서버 프레임 샘플링, 대표 인물 판정 한계, 운영 가이드까지 한 번에 설명하는 새 발표자료", 18, RGBColor(51, 65, 85))
    add_card(s, 0.78, 4.0, 3.45, 1.15, "운영 보증", "현재 낙상 판정은 대표 1명 중심\n1~2명 통제 환경 권장", TEAL)
    add_card(s, 4.55, 4.0, 3.45, 1.15, "무저하 테스트", "실시간 320px 기준\nRTT+검출 안정 3명", BLUE)
    add_card(s, 8.32, 4.0, 3.45, 1.15, "표시/한계", "5명 표시 가능, 판정 보수\n20명은 처리량 한계 테스트", GOLD)

    s = slide("이번 발표의 결론", "Executive Summary")
    add_card(s, 0.7, 1.75, 3.5, 1.35, "무저하 상한", "실시간 320px 기준 3명까지\nRTT+검출 안정성 유지", TEAL)
    add_card(s, 4.55, 1.75, 3.5, 1.35, "표시 가능", "4~5명은 RTT 유지\n과검출 증가로 판정 보수", GOLD)
    add_card(s, 8.4, 1.75, 3.5, 1.35, "운영 보증", "현재 보증은 대표 1명, 통제 환경 2명.\nperson별 판정 통합 후 5명 목표.", BLUE)
    add_bullets(s, 0.85, 3.45, 11.2, 2.2, [
        "화면에는 여러 사람 skeleton/bbox를 보여줄 수 있지만 RF-Fall/XG-Posture 입력은 아직 대표 인물 timeseries 중심이다.",
        "RTT만 보면 1~5명은 0.140~0.165초로 거의 유지되지만, 4~5명부터 검출 수가 33~38% 과하게 잡힌다.",
        "6명 이상은 320px 실시간 타일 조건에서 검출이 무너졌다. 발표 메시지는 '3명 무저하, 5명 표시 가능, 20명 한계 테스트'로 자른다.",
    ], 17)

    s = slide("실시간 프레임 처리 경로", "Frame Pipeline")
    add_bullets(s, 0.78, 1.8, 5.2, 4.6, [
        "웹캠 video element",
        "브라우저 MediaPipe skeleton 표시",
        "MediaRecorder WebM chunk 생성",
        "서버 OpenCV 프레임 샘플링",
        "YOLOv8n-pose 추론",
        "대표 인물 timeseries 생성",
        "RF-Fall / XG-Posture / 보조모델 evidence 결합",
    ], 15)
    steps = ["Webcam", "Skeleton", "WebM chunk", "4fps sample", "YOLO pose", "RF/XG + Aux", "Result"]
    for i, label in enumerate(steps):
        x = 6.25 + (i % 2) * 2.55
        y = 1.75 + (i // 2) * 1.15
        add_card(s, x, y, 2.2, 0.72, f"{i+1}. {label}", "", TEAL if i < 2 else BLUE)
    add_textbox(s, 6.25, 6.0, 4.9, 0.45, "기본값: 4초 chunk · 2초 overlap · 서버 4fps · 약 16 pose frame", 14, NAVY, True)

    s = slide("브라우저 표시와 서버 판정은 다르다", "Display vs Decision")
    add_table(s, 0.7, 1.8, 11.4, 3.0, ["구분", "현재 값", "역할", "주의점"], [
        ["브라우저 skeleton", "약 15fps", "프라이버시 화면 표시", "체감용이며 서버 판정 입력과 분리"],
        ["실시간 chunk", "4초 / 2초 overlap", "경계 낙상 맥락 보존", "서버 응답 지연 시 RTT 표시"],
        ["서버 샘플링", "4fps 중심", "RF/XG feature 생성", "16프레임이 기본 균형점"],
        ["업로드 balanced/full", "최대 8fps / imgsz 640", "정밀 분석", "실시간보다 무거움"],
    ], 10)
    add_bullets(s, 1.0, 5.25, 10.7, 0.8, [
        "실시간 UX는 브라우저 skeleton 15fps로 부드럽게 유지하고, 판정 입력은 서버 4fps로 안정화한다.",
        "SHAP/무거운 해석은 실시간 전 청크에 붙이지 않고, 오류 분석/보고서 또는 제한된 UI 근거로 사용한다.",
    ], 14)

    labels_5 = ["1명", "2명", "3명", "4명", "5명"]
    fps_5 = [170.88, 171.89, 145.30, 145.97, 169.98]
    rtt_5 = [0.140, 0.140, 0.165, 0.164, 0.141]
    s = slide("1~5명 pose 처리량 벤치마크", "RTT Benchmark")
    add_table(s, 0.7, 1.7, 5.4, 2.35, ["인원", "pose FPS", "4초 chunk RTT", "평균 검출"], [
        ["1", "170.88", "0.140s", "1.50"],
        ["2", "171.89", "0.140s", "1.92"],
        ["3", "145.30", "0.165s", "2.38"],
        ["4", "145.97", "0.164s", "5.50"],
        ["5", "169.98", "0.141s", "6.67"],
    ], 10)
    add_bar_chart(s, 6.55, 1.65, 5.2, 2.2, labels_5, fps_5, 190, "pose FPS", "", TEAL)
    add_bar_chart(s, 6.55, 4.25, 5.2, 1.7, labels_5, [round(v * 1000) for v in rtt_5], 180, "RTT 추정(ms)", "ms", GOLD)
    add_textbox(s, 0.85, 5.0, 5.2, 0.92, "해석: RTT는 5명까지 유지되지만 검출 안정성은 3명까지가 상한이다. 4~5명은 과검출이 33~38%로 늘고, 6명부터는 320px 실시간 설정에서 검출이 무너졌다.", 12, RGBColor(51, 65, 85))

    labels_20 = ["1", "3", "5", "10", "14", "20"]
    rtt_20 = [730, 667, 718, 778, 714, 740]
    fps_20 = [32.89, 35.97, 33.45, 30.85, 33.59, 32.43]
    s = slide("640px 정밀 확장 테스트", "Capacity Check")
    add_table(s, 0.7, 1.65, 5.65, 2.65, ["인원", "처리 FPS", "프레임 RTT", "운영 해석"], [
        ["1", "32.9", "0.730s", "정밀 기준 처리 가능"],
        ["3", "36.0", "0.667s", "검출 안정"],
        ["5", "33.5", "0.718s", "과검출 주의"],
        ["10", "30.9", "0.778s", "처리량 가능, 최소 검출 흔들림"],
        ["14", "33.6", "0.714s", "정밀 표시 한계 후보"],
        ["20", "32.4", "0.740s", "과검출 급증, 한계 테스트"],
    ], 9)
    add_bar_chart(s, 6.7, 1.65, 4.95, 1.9, labels_20, fps_20, 45, "처리 FPS", "", TEAL)
    add_bar_chart(s, 6.7, 4.05, 4.95, 1.9, labels_20, rtt_20, 900, "프레임 RTT(ms)", "ms", GOLD)

    s = slide("인원수별 운영 가이드", "Operation Guide")
    add_table(s, 0.7, 1.7, 11.4, 3.35, ["단계", "권장 인원", "근거", "발표 표현"], [
        ["현재 운영판", "1명", "대표 인물 1명 시계열 기준", "낙상 판정 보증"],
        ["통제 환경", "2명", "대상자+보호자까지 대표 유지 가능", "운영 가능, 확인 필요"],
        ["무저하 테스트", "3명", "320px 실시간 RTT+검출 안정 상한", "성능 저하 없음 설명 가능"],
        ["화면 표시", "5명", "브라우저/서버 overlay 기본 제한", "표시 가능"],
        ["추적 통합 후 목표", "5명", "person별 timeseries 필요", "개발 목표"],
        ["한계 테스트", "20명", "처리량 확인용", "상용 판정 보증 아님"],
    ], 10)
    add_bullets(s, 0.9, 5.45, 10.9, 0.7, [
        "5명 초과는 카메라 분리 또는 ROI 구역 분리가 현실적이다.",
        "person별 독립 판정 전에는 '다중 인원 표시'와 '다중 인원 판정'을 반드시 분리해 설명한다.",
    ], 14)

    s = slide("최적 프레임 예산", "Frame Budget")
    add_table(s, 0.75, 1.75, 11.2, 3.1, ["운영 모드", "권장 설정", "설명"], [
        ["기본 실시간", "4초 x 4fps = 16프레임", "정확도와 지연의 균형"],
        ["CPU 부족 / 4~5명 밀집", "4초 x 3fps = 12프레임", "RTT 안정화 우선"],
        ["낙상 위험 구역", "4초 x 5fps = 20프레임", "움직임 변화 포착 강화"],
        ["GPU/엣지 여유 장비", "4초 x 6fps = 24프레임", "상한 권장"],
        ["24프레임 초과", "비권장", "지연 증가 대비 이득 불확실"],
    ], 11)
    add_card(s, 1.0, 5.35, 10.8, 0.95, "핵심 원칙", "화면은 15fps로 부드럽게, 서버 판정은 4fps 중심으로 안정화한다. 체감 실시간성과 모델 입력 예산을 분리한다.", TEAL)

    s = slide("현재 다중 인원 구조의 한계", "Risk")
    add_bullets(s, 0.85, 1.85, 5.4, 3.7, [
        "RF-Fall/XG-Posture 입력 timeseries는 아직 대표 인물 1명 기준이다.",
        "프레임마다 bbox가 큰 사람을 다시 고르므로 사람이 교차하면 대표가 바뀔 수 있다.",
        "낙상자가 뒤쪽에 작게 잡히면 FN 위험이 커진다.",
        "20명 표시는 한계 테스트이지 상용 판정 보증이 아니다.",
    ], 16)
    add_card(s, 6.75, 1.85, 4.8, 0.95, "정확도 검증 필요", "person_id별 fall label이 있는 실제 다중 인원 영상 필요", RED)
    add_card(s, 6.75, 3.1, 4.8, 0.95, "ID switch 검증 필요", "track continuity, ID switch count, MOTA/IDF1 또는 단순 유지율", GOLD)
    add_card(s, 6.75, 4.35, 4.8, 0.95, "RTT 검증 필요", "브라우저 인코딩, 네트워크, 서버 큐, person별 추론 포함 p50/p95", BLUE)

    s = slide("다음 구조: person별 timeseries", "Roadmap")
    add_bullets(s, 0.75, 1.8, 11.1, 3.2, [
        "YOLO detections per frame -> lightweight IoU/center tracker",
        "track_id별 timeseries 생성 -> track별 RF-Fall/XG-Posture 추론",
        "person_results[] 응답 추가: person_id, fall_score, posture_state, occlusion_state, emotion_state",
        "최고 위험 person_id를 기존 fall_detected/risk_score에 연결",
        "실시간 chunk 간 1~2초 tail cache로 짧은 누락 보정",
    ], 17)
    add_table(s, 0.9, 5.25, 10.9, 0.95, ["우선순위", "구현 항목", "검증 지표"], [
        ["1", "chunk-local tracker + person_results[]", "RTT p50/p95, ID switch"],
        ["2", "track별 RF/XG 입력", "person별 Recall/F1"],
    ], 10)

    s = slide("모델 상태와 버전 표시", "Model Status")
    add_table(s, 0.7, 1.65, 11.4, 3.55, ["모델", "active", "현재 성능", "상태/해석"], [
        ["RF-Fall 운영", "active v15", "F1 98.08%", "목표 충족"],
        ["XG-Posture", "active v1", "F1 94.31%", "AI-Hub71461 포함 기본 재학습 시작"],
        ["XG-Posture 가림 보조", "가림 보조 v20260617030130", "Sequence F1 95.96%", "목표 달성, 버전 표시 유지"],
        ["AI-Hub 82 표정", "active #0092", "Macro F1 88.37%", "고정 seed 반복 제거, threshold calibration 추가"],
        ["AI-Hub 173 상태", "v4-best-recorded", "Macro F1 93.24%", "95% 목표 재학습 진행"],
    ], 10)
    add_bullets(s, 0.9, 5.45, 10.9, 0.7, [
        "가림 보조 버전은 삭제 대상이 아니라 완료 evidence다. 기본 XG와 별도 카드/버전으로 표시한다.",
        "82번 병목은 validation label noise와 distress/non-distress 경계. 다음 후보부터 threshold sweep까지 포함한다.",
    ], 13)

    s = slide("발표에서 말해야 하는 것과 말하면 안 되는 것", "Message Guide")
    add_table(s, 0.7, 1.7, 11.4, 3.2, ["구분", "권장 표현", "피해야 할 표현"], [
        ["다중 인원", "여러 사람 표시와 5명 overlay는 가능", "각 사람별 낙상 판정이 완성됨"],
        ["성능저하", "실시간 기본은 3명까지 무저하, 4~5명은 표시 가능", "인원 증가에도 성능 저하 없음"],
        ["RTT", "pose-only RTT는 5명까지 예산 내, E2E p95는 추가 측정 필요", "RTT 문제가 완전히 해결됨"],
        ["정확도", "person별 라벨 영상으로 검증 필요", "합성 벤치마크로 정확도 보증"],
        ["프레임", "기본 16프레임, 상황별 12~24프레임", "무조건 프레임을 늘리면 정확도 상승"],
    ], 10)
    add_card(s, 1.0, 5.35, 10.8, 0.8, "한 문장 결론", "실시간 기본 설정에서 성능 저하 없음으로 말할 수 있는 선은 3명이다. 5명은 표시 가능하지만 판정은 보수적이며, 다음 단계는 person별 추적 판정과 실제 다중 인원 라벨 검증이다.", TEAL)

    s = slide("실행 계획", "Next Actions")
    add_bullets(s, 0.9, 1.8, 10.9, 4.2, [
        "1. 가림 보조: 완료 모델 버전과 sequence/window F1을 계속 표시",
        "2. AI-Hub82: #0094 완료 후 threshold-tuned 후보부터 승격 기준에 반영",
        "3. XG-Posture: AI-Hub71461 기반 기본 재학습 후보 생성 후 v1 대비 비교",
        "4. 다중 인원: chunk-local tracker와 person_results[] 응답 설계",
        "5. 검증: 1~5명 실제 라벨 영상으로 Recall/F1, RTT p50/p95, ID switch 재측정",
    ], 17)

    prs.save(PPTX_PATH)


def build_markdown():
    content = """# FallAI 인원수별 RTT와 프레임 처리 전략 발표자료

생성일: 2026-06-22

## 핵심 메시지

- 현재 낙상 판정 보증은 대표 1명 중심이며, 통제 환경에서는 2명까지 운영 가능하다고 설명한다.
- 2026-06-25 재측정 기준, 실시간 기본 설정에서 성능 저하 없음으로 말할 수 있는 선은 3명까지다.
- 4~5명은 RTT는 유지되지만 과검출이 33~38%로 늘어 “표시 가능, 판정 보수”로 설명한다.
- 브라우저 skeleton 및 서버 overlay는 5명 표시를 기준으로 하고, 20명은 처리량/정밀모드 한계 테스트다.
- 실시간 판정 입력은 4초 chunk, 2초 overlap, 서버 4fps, 약 16프레임을 기본으로 한다.
- 1~5명 합성 pose-only 벤치마크는 4fps 실시간 요구를 넘겼지만, 실제 성능 저하 여부는 정확도·ID 유지율·E2E p95까지 다시 봐야 한다.
- 다음 개발은 person별 timeseries, person_results[], chunk tail cache, 실제 다중 인원 RTT/F1 재검증이다.

## 산출물

- PPTX: `docs/presentation/2026-06-22-fallai-multiperson-rtt-frame-guide.pptx`
- 백업: `docs/presentation/archive/backup_20260622T065911Z`
"""
    MD_PATH.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    build_deck()
    build_markdown()
    print(PPTX_PATH)
    print(MD_PATH)

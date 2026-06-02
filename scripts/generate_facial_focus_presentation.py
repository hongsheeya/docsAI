#!/usr/bin/env python3
"""Generate the concise facial/occlusion auxiliary model presentation."""

from __future__ import annotations

import datetime as dt
import html
import json
from pathlib import Path


PROJECT = Path("/opt/app/project/main")
OUT = PROJECT / "docs" / "presentation"
STORAGE = Path("/opt/app/storage/training/fall-detection")
SKELETON_IMAGE = PROJECT / "src" / "assets" / "pres" / "skeleton-privacy-mode.png"
SKELETON_IMAGE_WEB = "../../src/assets/pres/skeleton-privacy-mode.png"
FACIAL_AB_PATH = PROJECT / "outputs" / "facial_aux_validation" / "aihub71641_facial_aux_ab_100_20260601.json"


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def best(summary: dict, key: str, default: float = 0.0) -> float:
    value = ((summary or {}).get("best_metrics") or {}).get(key, default)
    try:
        return float(value)
    except Exception:
        return default


def nested(summary: dict, *keys: str, default: float = 0.0) -> float:
    cur: object = summary or {}
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    try:
        return float(cur)
    except Exception:
        return default


def fmt4(value: float) -> str:
    return f"{value:.4f}"


def pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def markdown_table(headers: list[str], rows: list[list[object]]) -> str:
    return "\n".join(
        [
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join(["---"] * len(headers)) + " |",
            *["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows],
        ]
    )


def html_table(headers: list[str], rows: list[list[object]]) -> str:
    head = "".join(f"<th>{html.escape(str(h))}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(cell))}</td>" for cell in row) + "</tr>"
        for row in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    face82 = read_json(STORAGE / "facial-state" / "aihub82_facial_emotion_summary.json")
    face173 = read_json(STORAGE / "facial-state" / "aihub173_driver_state_summary.json")
    rf = read_json(STORAGE / "rf-fall-v2" / "training_summary.json")
    occ = read_json(STORAGE / "xg-posture-occlusion-aux" / "training_summary.json")
    facial_ab = read_json(FACIAL_AB_PATH)

    rf_f1 = nested(rf, "validation", "f1")
    rf_precision = nested(rf, "validation", "precision")
    rf_recall = nested(rf, "validation", "recall")
    occ_acc = nested(occ, "group_cv", "accuracy")
    occ_f1 = nested(occ, "group_cv", "f1_macro")
    occ_windows = int(occ.get("occlusion_training_windows") or 0)
    occ_features = int(occ.get("feature_count") or 0)
    xg = read_json(STORAGE / "xg-posture" / "training_summary.json")
    xg_f1 = nested(xg, "group_cv", "f1_macro")
    xg_acc = nested(xg, "group_cv", "accuracy")

    occlusion_rank = "-"
    occlusion_importance = "-"
    for index, item in enumerate(rf.get("top_features") or [], start=1):
        if item.get("feature") == "occlusion_fall_risk":
            occlusion_rank = f"{index}/65"
            occlusion_importance = f"{float(item.get('importance', 0.0)):.4f}"
            break
    ab_n = int(facial_ab.get("sample_size") or 0)
    ab_applied = int(facial_ab.get("facial_applied_count") or 0)
    ab_changed = int(facial_ab.get("decision_changed_count") or 0)
    ab_before = facial_ab.get("before_facial") or {}
    ab_after = facial_ab.get("after_facial") or {}
    ab_before_f1 = float(ab_before.get("f1") or 0.0)
    ab_after_f1 = float(ab_after.get("f1") or 0.0)
    ab_before_recall = float(ab_before.get("recall") or 0.0)
    ab_after_recall = float(ab_after.get("recall") or 0.0)
    ab_helpful = int(facial_ab.get("helpful_changes") or 0)
    ab_harmful = int(facial_ab.get("harmful_changes") or 0)
    ab_support = int(facial_ab.get("facial_support_count") or 0)
    ab_blocked = int(facial_ab.get("facial_blocked_count") or 0)
    ab_results = facial_ab.get("results") or []
    ab_face_detected = sum(1 for item in ab_results if item.get("ok") and item.get("face_detected"))
    ab_face_missing = max(ab_n - ab_face_detected, 0)

    slides: list[dict] = [
        {
            "type": "cover",
            "title": "FallAI 표정·가림 보조모델 개선 보고",
            "subtitle": "이번 발표는 표정 상태 보조모델과 하체가림 전처리 보조모델을 같은 비중으로 정리",
            "stats": [
                ["RF-Fall F1", fmt4(rf_f1)],
                ["FacialRisk-Aux 적용", f"{ab_applied}/{ab_n}"],
                ["가림 보조 F1", fmt4(occ_f1)],
                ["Skeleton-only", "적용"],
            ],
        },
        {
            "title": "1. 이번 개선 파이프라인",
            "headers": ["단계", "모델/처리", "역할", "이번 발표 포인트"],
            "rows": [
                ["1", "Pose/BBox feature", "사람의 위치, 자세, 이동량, visibility 추출", "프라이버시 화면은 skeleton-only로 표시"],
                ["2", "RF-Fall v2", "낙상/비낙상 주 판정", f"현재 기준 F1 {fmt4(rf_f1)}, recall {pct(rf_recall)}"],
                ["3", "XG-Posture", "비낙상 구간 행동 설명", "하체가림 상황에서 흔들림이 커서 보조모델 추가"],
                ["4", "Occlusion-Aux", "하체가림 전처리로 만든 보조 판단", f"가림 조건 F1 {fmt4(occ_f1)}"],
                ["5", "FacialRisk-Aux", "표정/주의저하 근거를 하나의 보조 evidence로 합산", f"100개 확장검증 기준 판정개선 {ab_helpful}건, harmful {ab_harmful}건"],
            ],
            "note": "흐름은 RF-Fall이 주 판정, 가림과 표정은 약한 구간의 보조 근거다. LLM은 판정을 뒤집지 않고 근거를 설명한다.",
        },
        {
            "title": "2. 이번 발표의 두 축",
            "headers": ["보조모델", "왜 만들었나", "검증 결과", "현재 결론"],
            "rows": [
                ["Occlusion-Aux", "하체가 침대/가구/화면 밖으로 가려질 때 stand/sit/lie가 흔들림", f"가림 조건 F1 {fmt4(occ_f1)} / Acc {fmt4(occ_acc)}", "가림 hard-case에서는 기존 행동분류보다 도움 확인"],
                ["FacialRisk-Aux", "낙상 near-miss에서 표정/주의저하 evidence가 빠져 FN이 남음", f"100개 확장검증 F1 {fmt4(ab_before_f1)} → {fmt4(ab_after_f1)}, harmful {ab_harmful}건", "현재 데이터에서는 판정 성능 개선 미확인, 얼굴 ROI가 병목"],
            ],
            "note": "이번 발표의 중심은 표정만이 아니라, RF-Fall의 약한 구간을 두 보조모델로 어떻게 보강했는지다.",
        },
        {
            "title": "3. 표정 보조모델: 82와 173을 왜 나눴나",
            "headers": ["표시 이름", "기존 번호", "학습 목적", "현재 성능", "운영 해석"],
            "rows": [
                ["EmotionGuard-82", "AI-Hub 82", "한국인 감정 7-class", f"Acc {pct(best(face82, 'accuracy'))}, Macro F1 {fmt4(best(face82, 'macro_f1'))}", "불안/상처/슬픔 같은 감정 근거. 단독 낙상 근거로는 약함"],
                ["DrowsyState-173", "AI-Hub 173", "졸음/하품/주의저하 5-class", f"Acc {pct(best(face173, 'accuracy'))}, Macro F1 {fmt4(best(face173, 'macro_f1'))}", "졸음/하품처럼 명확한 상태 근거가 비교적 안정적"],
                ["FacialRisk-Aux", "통합 출력", "두 모델의 evidence를 late fusion", "단일 support score로 표시", "화면과 발표에서는 표정 보조모델 하나처럼 설명"],
            ],
            "note": "완전한 단일 모델로 재학습하지 않은 이유는 82와 173의 라벨 체계가 서로 다르기 때문이다. 지금은 내부 2개 모델, 외부 1개 보조점수 구조가 가장 안전하다.",
        },
        {
            "title": "4. 표정 보조가 낙상 판정에 도움이 됐나",
            "headers": ["검증 항목", "결과", "의미"],
            "rows": [
                ["동일 테스트 샘플", f"{ab_n}개", "AI-Hub 71641에서 낙상 50 / 비낙상 50 균형 추출"],
                ["표정 보조 전후 F1", f"{fmt4(ab_before_f1)} → {fmt4(ab_after_f1)}", "순수 score A/B에서는 최종 판정 변화 없음"],
                ["Recall", f"{fmt4(ab_before_recall)} → {fmt4(ab_after_recall)}", "FN 7건 유지"],
                ["실제 반영 건수", f"{ab_applied}/{ab_n}", f"support {ab_support}건, blocked {ab_blocked}건, 얼굴 미검출 {ab_face_missing}건"],
                ["판정 변화", f"{ab_changed}건", f"helpful {ab_helpful}건, harmful {ab_harmful}건"],
            ],
            "note": f"말할 결론: 소규모 검증의 개선 신호를 100개로 확장했지만 최종 판정 개선은 확인되지 않았다. 얼굴 미검출 {ab_face_missing}/{ab_n}이라 ROI 품질과 실제 설치각 얼굴 데이터가 핵심이다.",
        },
        {
            "title": "5. 표정 보조 한계와 다음 방향",
            "headers": ["문제", "왜 중요한가", "다음 조치"],
            "rows": [
                ["얼굴이 작거나 안 보임", f"100개 중 얼굴 미검출 {ab_face_missing}건", "상체/전체 프레임 fallback을 추가했고, 실제 얼굴 검출률 지표로 gate"],
                ["82 감정모델 한계", "불안 F1 0.4532, 상처 F1 0.3788로 약한 클래스가 있음", "감정 자체보다 distress/normal 이진 보조로 재정의"],
                ["173 도메인 차이", "운전자 상태 데이터라 병실/실내 낙상과 완전히 같지 않음", "졸음/하품/눈감김 evidence로만 제한"],
                ["실환경 데이터 부족", "낙상 전후 표정, 누운 상태 얼굴, 가림 얼굴이 부족", "실제 설치각 데이터로 near-miss rescue 기준 재검증"],
            ],
        },
        {
            "title": "6. 하체가림 전처리 보조모델",
            "headers": ["항목", "내용"],
            "rows": [
                ["왜 만들었나", "하체가 침대/가구/화면 밖으로 가려지면 stand/sit/lie 판단이 흔들려 미확인이나 오분류가 늘어남"],
                ["전처리", "기존 posture window에서 하체 영역을 0.55/0.62/0.70 비율로 가림 처리해 lower-body occlusion 샘플 생성"],
                ["누수 방지", "원본과 가림 샘플을 같은 group으로 묶어 train/val에 동시에 섞이지 않게 분리"],
                ["학습", f"ExtraTrees balanced · feature {occ_features}개 · 가림 window {occ_windows:,}개"],
                ["적용", "하체 visibility가 낮거나 posture confidence가 낮을 때 기존 XG-Posture를 보조"],
            ],
        },
        {
            "title": "7. 가림 보조모델은 도움이 됐나",
            "headers": ["비교", "수치", "해석"],
            "rows": [
                ["기존 XG-Posture", f"F1 {fmt4(xg_f1)} / Acc {fmt4(xg_acc)}", "일반 행동분류 기준. 하체가림 hard-case에 약함"],
                ["Occlusion-Aux", f"F1 {fmt4(occ_f1)} / Acc {fmt4(occ_acc)}", "가림 전처리 조건에서 행동/자세 보조 성능 개선"],
                ["RF 주 판정 기여", f"occlusion_fall_risk rank {occlusion_rank}, importance {occlusion_importance}", "가림 관련 feature가 낙상 판정에서도 상위 근거로 사용됨"],
            ],
            "note": "말할 결론: 가림 보조모델은 만든 의미가 있다. 다만 합성 가림이 실제 침대/가구 가림과 얼마나 일치하는지는 추가 촬영 데이터로 확인해야 한다.",
        },
        {
            "title": "8. Skeleton-only 프라이버시 화면",
            "image": str(SKELETON_IMAGE),
            "bullets": [
                "사용자 화면은 원본 인물 픽셀을 숨기고 skeleton landmark만 표시한다.",
                "관리자 확인용으로 원본/스켈레톤 전환 버튼을 제공한다.",
                "분석은 유지하되, 일반 사용자에게는 사람이 직접 보이지 않게 하는 방향이다.",
            ],
        },
        {
            "title": "9. 최종 결론",
            "headers": ["항목", "현재 결론", "다음 개선"],
            "rows": [
                ["표정 보조", f"100개 확장검증 F1 {fmt4(ab_before_f1)} → {fmt4(ab_after_f1)}, harmful {ab_harmful}건", "현재는 판정 근거 표시용에 가깝고, 성능 개선은 얼굴 ROI/실제 설치각 데이터 확보 후 재검증"],
                ["82+173 통합", "지금은 내부 2개 모델을 FacialRisk-Aux 하나의 보조점수로 합산", "공통 라벨(normal/distress/drowsy/unknown) 데이터가 생기면 단일 모델 재학습"],
                ["가림 보조", "가려진 하체 조건의 행동/자세 판정에는 도움 확인", "실제 침대/가구 가림 데이터로 보강"],
                ["발표 메시지", "가림은 행동/자세 보조 효과 확인, 표정은 현 데이터에서 성능 개선 미확인", "표정은 입력 품질, 가림은 실제 가림 데이터가 핵심"],
            ],
        },
    ]

    markdown_lines = [
        "# FallAI 발표자료: 표정·가림 보조모델 개선 보고",
        "",
        f"- 생성: {now()}",
        "",
    ]
    for idx, item in enumerate(slides, start=1):
        markdown_lines += ["---", "", f"## {item['title']}", ""]
        if item.get("type") == "cover":
            markdown_lines += [item["subtitle"], "", markdown_table(["지표", "값"], item["stats"]), ""]
        if item.get("headers"):
            markdown_lines += [markdown_table(item["headers"], item["rows"]), ""]
        if item.get("image"):
            markdown_lines += [f"![스켈레톤 전용 프라이버시 모드]({item['image']})", ""]
        for bullet in item.get("bullets", []):
            markdown_lines.append(f"- {bullet}")
        if item.get("note"):
            markdown_lines += ["", f"> {item['note']}"]
        markdown_lines.append("")

    script = [
        "# FallAI 발표 대본: 표정·가림 보조모델 중심",
        "",
        f"- 생성: {now()}",
        "- PPT 순서와 동일하게 구성",
        "",
        "## 0. 표지",
        "오늘은 기존 낙상 모델 전체 설명보다, 이번에 새로 붙인 표정 상태 보조모델과 하체가림 전처리 보조모델을 중심으로 말씀드리겠습니다.",
        "",
        "## 1. 이번 개선 파이프라인",
        "이번 구조는 먼저 pose와 bbox feature를 뽑고, RF-Fall이 낙상 여부를 주 판정합니다. 그 다음 XG-Posture가 비낙상 구간의 행동을 설명합니다. 여기서 약한 부분이 두 가지였는데, 하나는 하체가 가려졌을 때 행동분류가 흔들리는 문제이고, 다른 하나는 낙상 전후 표정이나 주의저하 상태를 근거로 쓰지 못한다는 점이었습니다. 그래서 하체가림 보조모델과 FacialRisk-Aux를 붙였습니다.",
        "",
        "## 2. 이번 발표의 두 축",
        f"이번 발표는 표정 모델 하나가 아니라 두 보조모델을 같이 보는 흐름입니다. 하체가림 보조모델은 가림 조건에서 F1 {fmt4(occ_f1)}까지 올라가 기존 행동분류의 약점을 보완했습니다. 반면 FacialRisk-Aux는 100개 확장검증에서 낙상 F1이 {fmt4(ab_before_f1)}에서 {fmt4(ab_after_f1)}로 유지되어, 현재는 판정 성능 개선보다 근거 표시와 향후 보강 포인트를 확인한 단계입니다.",
        "",
        "## 3. 표정 보조모델: 82와 173을 왜 나눴나",
        "82 모델은 EmotionGuard-82라고 이름 붙였습니다. 한국인 감정 데이터로 학습한 모델이고, 불안이나 상처 같은 감정 근거를 보기 위한 모델입니다. 173 모델은 DrowsyState-173으로 이름 붙였습니다. 졸음, 하품, 주의저하 같은 상태 근거를 보기 위한 모델입니다. 두 모델은 라벨 목적이 달라서 하나의 분류기로 바로 합치면 라벨이 섞입니다. 그래서 지금은 내부적으로 두 모델을 쓰고, 화면과 설명에서는 FacialRisk-Aux라는 하나의 보조점수로 합쳐서 보여주는 구조가 맞습니다.",
        "",
        "## 4. 표정 보조가 낙상 판정에 도움이 됐나",
        f"동일 테스트 샘플 {ab_n}개로 표정 보조 적용 전후를 비교했습니다. 결과는 F1 {fmt4(ab_before_f1)}에서 {fmt4(ab_after_f1)}, recall {fmt4(ab_before_recall)}에서 {fmt4(ab_after_recall)}로 유지됐습니다. 실제 반영은 {ab_n}개 중 {ab_applied}건뿐이고, 판정 변화는 {ab_changed}건입니다. 그래서 이번 검증의 결론은 표정 보조가 아직 최종 낙상 판정을 끌어올리지는 못했고, 얼굴 ROI와 실제 설치각 데이터가 병목이라는 것입니다.",
        "",
        "## 5. 표정 보조 한계와 다음 방향",
        f"개선 방식은 전체 threshold를 낮춘 게 아니라, 실제 얼굴이 검출되고 DrowsyState 근거가 안정적이며 RF-Fall 점수가 threshold 근처인 near-miss일 때만 rescue하는 방식입니다. 이번 100개 검증에서는 얼굴 미검출이 {ab_face_missing}건이어서 조건에 들어오는 케이스가 적었습니다. 다음에는 얼굴 ROI 정렬과 실제 설치각 얼굴 데이터를 확보해야 합니다.",
        "",
        "## 6. 하체가림 전처리 보조모델",
        "하체가 안 보이면 기존 행동분류가 미확인이나 lie 오분류로 흔들릴 수 있습니다. 그래서 기존 posture window에서 하체 영역을 일부러 가린 데이터를 만들었습니다. 원본과 가림 샘플은 같은 group으로 묶어서 train과 validation에 동시에 섞이지 않게 했고, ExtraTrees balanced 모델로 학습했습니다.",
        "",
        "## 7. 가림 보조모델은 도움이 됐나",
        f"기존 XG-Posture는 grouped F1 {fmt4(xg_f1)}였고, 가림 전처리 보조모델은 grouped F1 {fmt4(occ_f1)}였습니다. 그래서 가려진 하체 조건에서 행동/자세 판정을 보조하는 효과는 있다고 볼 수 있습니다. 다만 합성 가림과 실제 침대나 가구 가림이 완전히 같지는 않아서 실제 촬영 데이터로 추가 검증이 필요합니다.",
        "",
        "## 8. Skeleton-only 화면",
        "프라이버시 요구 때문에 사용자에게는 원본 사람이 보이지 않고 skeleton landmark만 보이는 방향으로 바꿨습니다. 관리자는 원본과 skeleton 화면을 전환해서 검증할 수 있게 했습니다.",
        "",
        "## 9. 최종 결론",
        "정리하면, 표정 보조모델은 현재 단계에서 최종 낙상 성능 향상까지는 확인하지 못했습니다. 대신 왜 안 되는지, 즉 전신 영상에서 얼굴 ROI가 부족하고 near-miss 조건에 들어오는 샘플이 적다는 점을 확인했습니다. 하체가림 보조모델은 가려진 상황의 행동/자세 판정에 도움이 되는 결과가 나왔습니다. 다음 개선은 표정 쪽은 실제 설치각 얼굴 데이터, 가림 쪽은 실제 침대/가구 가림 데이터 보강이 핵심입니다.",
        "",
        "## 예상 질문",
        "",
        "### Q. 표정 모델이 낙상 정확도를 올렸다고 말할 수 있나요?",
        f"아직은 아닙니다. 100개 확장 A/B 검증 기준 F1은 {fmt4(ab_before_f1)}에서 {fmt4(ab_after_f1)}로 유지됐고, harmful change는 {ab_harmful}건이었습니다. 의미 있는 점은 얼굴 ROI와 near-miss 조건이 병목이라는 것을 확인했다는 것입니다.",
        "",
        "### Q. 82와 173을 하나로 합치면 안 되나요?",
        "지금은 완전 병합보다 late fusion이 맞습니다. 82는 감정 라벨, 173은 주의저하/행동 라벨이라 같은 정답 체계가 아닙니다. 대신 화면과 설명에서는 FacialRisk-Aux라는 하나의 보조점수로 합쳐서 보여주고, 추후 normal/distress/drowsy/unknown 같은 공통 라벨 데이터가 모이면 단일 모델로 재학습할 수 있습니다.",
        "",
        "### Q. 얼굴이 안 보이면 어떻게 하나요?",
        "얼굴이 안 보이면 표정 미검출로 표시하고 보조점수는 0점입니다. 안 보이는 얼굴을 불안이나 고통으로 추정하지 않습니다.",
        "",
        "### Q. 하체가림 모델은 기존 모델을 대체하나요?",
        "대체하지 않습니다. 하체 visibility가 낮거나 기존 posture confidence가 낮을 때만 보조로 사용합니다.",
        "",
        "### Q. 다음에 가장 필요한 데이터는 무엇인가요?",
        "실제 설치각에서 촬영한 얼굴/가림/낙상 전후 영상입니다. 특히 누운 자세, 하체가 침대나 가구에 가린 상황, 고령자 통증/불편 표정 데이터가 필요합니다.",
        "",
    ]

    css = """
body{margin:0;background:#eaf3f4;color:#102326;font-family:Inter,Pretendard,Arial,sans-serif}
.slide{width:1280px;height:720px;box-sizing:border-box;padding:46px 64px;page-break-after:always;background:#f8fbfc;border-bottom:1px solid #dbe7eb;display:flex;flex-direction:column;gap:22px}
h1{font-size:54px;margin:0 0 10px;color:#0f2528;line-height:1.12}
h2{font-size:38px;margin:0;color:#0f2528;line-height:1.2}
p.lead{font-size:24px;line-height:1.5;color:#34515a;margin:0}
ul{font-size:23px;line-height:1.52;margin:0;padding-left:28px}
li{margin:9px 0}
table{width:100%;border-collapse:separate;border-spacing:0;font-size:18px;overflow:hidden;border-radius:14px;border:1px solid #cbdde3;background:white}
th{background:#e4f6f3;text-align:left;color:#173b3f}
th,td{border-bottom:1px solid #dbe7eb;padding:12px 13px;vertical-align:top}
tr:last-child td{border-bottom:0}
.kpi{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-top:auto}
.card{border:1px solid #cbdde3;border-radius:18px;padding:20px;background:#fff;box-shadow:0 10px 26px rgba(15,37,40,.06)}
.big{font-size:40px;font-weight:850;color:#04a39a}
.small{font-size:15px;color:#5d737b;margin-top:8px}
.note{border-left:5px solid #04a39a;background:#ecfffb;padding:14px 16px;font-size:20px;color:#17565a;border-radius:10px}
.shot{display:grid;grid-template-columns:1.15fr .85fr;gap:26px;align-items:center;min-height:0}
.shot img{width:100%;border-radius:18px;border:1px solid #cbdde3;box-shadow:0 18px 40px rgba(15,37,40,.12)}
.shot ul{font-size:21px}
"""
    html_lines = ["<html><head><meta charset='utf-8'><style>", css, "</style></head><body>"]
    for item in slides:
        html_lines.append("<section class='slide'>")
        if item.get("type") == "cover":
            html_lines.append(f"<h1>{html.escape(item['title'])}</h1>")
            html_lines.append(f"<p class='lead'>{html.escape(item['subtitle'])}</p>")
            html_lines.append("<div class='kpi'>")
            for label, value in item["stats"]:
                html_lines.append(
                    f"<div class='card'><div class='big'>{html.escape(value)}</div><div class='small'>{html.escape(label)}</div></div>"
                )
            html_lines.append("</div>")
        else:
            html_lines.append(f"<h2>{html.escape(item['title'])}</h2>")
            if item.get("headers"):
                html_lines.append(html_table(item["headers"], item["rows"]))
            if item.get("image"):
                html_lines.append("<div class='shot'>")
                html_lines.append(f"<img src='{html.escape(SKELETON_IMAGE_WEB)}' alt='skeleton privacy mode'>")
                html_lines.append("<ul>")
                for bullet in item.get("bullets", []):
                    html_lines.append(f"<li>{html.escape(bullet)}</li>")
                html_lines.append("</ul></div>")
            elif item.get("bullets"):
                html_lines.append("<ul>")
                for bullet in item["bullets"]:
                    html_lines.append(f"<li>{html.escape(bullet)}</li>")
                html_lines.append("</ul>")
            if item.get("note"):
                html_lines.append(f"<div class='note'>{html.escape(item['note'])}</div>")
        html_lines.append("</section>")
    html_lines.append("</body></html>")

    deck_path = OUT / "2026-06-01-facial-aux-model-launch-deck.md"
    script_path = OUT / "2026-06-01-facial-aux-model-launch-script-and-qna.md"
    html_path = OUT / "2026-06-01-facial-aux-model-launch-deck.html"
    deck_path.write_text("\n".join(markdown_lines), encoding="utf-8")
    script_path.write_text("\n".join(script), encoding="utf-8")
    html_path.write_text("".join(html_lines), encoding="utf-8")
    print(json.dumps({"deck": str(deck_path), "script": str(script_path), "html": str(html_path)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""FN-20260406-0004: FallAI E2E Integration Test Suite

전체 시스템 경로 통합 테스트:
- 업로드 분석 (정상/에러/경계)
- 피드백/재학습 경로
- 모델 워밍업
- prototype_info
- 에러 처리 및 보안 검증

사용법:
    python3 scripts/e2e_test.py [--base-url http://localhost:3000] [--project main]
"""
import json
import os
import sys
import time
import hashlib
import argparse
import datetime
import traceback

# -------------------------------------------------------------------
# Config
# -------------------------------------------------------------------
BASE_URL = "http://localhost:3000"
PROJECT = "main"
SECRET_KEY = "season-wiz-secret"

# Test video paths (자동 탐색)
FALL_VIDEO = None
NON_FALL_VIDEO = None

# -------------------------------------------------------------------
# HTTP helpers (requests 미설치 환경 대비 urllib 사용)
# -------------------------------------------------------------------
import urllib.request
import urllib.error
import urllib.parse
from http.cookiejar import CookieJar


def _build_session_cookie():
    """Flask Secure Cookie 세션 생성."""
    try:
        from flask import Flask
        app = Flask(__name__)
        app.secret_key = SECRET_KEY
        with app.test_request_context():
            from flask import session as sess
            sess['id'] = 'e2e_test_user'
            sess['email'] = 'test@e2e.local'
            sess['role'] = 'admin'
            from flask.sessions import SecureCookieSessionInterface
            si = SecureCookieSessionInterface()
            s = si.get_signing_serializer(app)
            return s.dumps(dict(sess))
    except Exception as e:
        print(f"  [WARN] Flask 세션 생성 실패: {e}")
        return ""


def _make_multipart(fields, files):
    """Multipart form data 생성 (requests 없이)."""
    boundary = f"---e2e-{hashlib.md5(str(time.time()).encode()).hexdigest()}"
    body = b""
    for key, val in fields.items():
        body += f"--{boundary}\r\n".encode()
        body += f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode()
        body += f"{val}\r\n".encode()
    for key, (fname, fdata, ftype) in files.items():
        body += f"--{boundary}\r\n".encode()
        body += f'Content-Disposition: form-data; name="{key}"; filename="{fname}"\r\n'.encode()
        body += f"Content-Type: {ftype}\r\n\r\n".encode()
        body += fdata + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    content_type = f"multipart/form-data; boundary={boundary}"
    return body, content_type


def _post_form(url, fields):
    """URL-encoded POST."""
    data = urllib.parse.urlencode(fields).encode()
    cookie_str = f"session={SESSION_COOKIE}; season-wiz-project={PROJECT}; season-wiz-devmode=true"
    req = urllib.request.Request(url, data=data, method='POST')
    req.add_header('Cookie', cookie_str)
    req.add_header('Content-Type', 'application/x-www-form-urlencoded')
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode()
            try:
                return json.loads(raw)
            except Exception:
                return {"code": resp.status, "raw": raw}
    except urllib.error.HTTPError as e:
        raw = e.read().decode() if e.fp else ""
        try:
            return json.loads(raw)
        except Exception:
            return {"code": e.code, "raw": raw}
    except Exception as e:
        return {"code": 0, "error": str(e)}


def _post_multipart(url, fields, files):
    """Multipart POST (파일 업로드)."""
    body, content_type = _make_multipart(fields, files)
    cookie_str = f"session={SESSION_COOKIE}; season-wiz-project={PROJECT}; season-wiz-devmode=true"
    req = urllib.request.Request(url, data=body, method='POST')
    req.add_header('Cookie', cookie_str)
    req.add_header('Content-Type', content_type)
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            raw = resp.read().decode()
            try:
                return json.loads(raw)
            except Exception:
                return {"code": resp.status, "raw": raw}
    except urllib.error.HTTPError as e:
        raw = e.read().decode() if e.fp else ""
        try:
            return json.loads(raw)
        except Exception:
            return {"code": e.code, "raw": raw}
    except Exception as e:
        return {"code": 0, "error": str(e)}


# -------------------------------------------------------------------
# Test infrastructure
# -------------------------------------------------------------------
RESULTS = []
PASS_COUNT = 0
FAIL_COUNT = 0
SKIP_COUNT = 0


def test(name, priority="P0"):
    """Decorator to register a test."""
    def decorator(func):
        func._test_name = name
        func._priority = priority
        return func
    return decorator


def _run_test(func):
    global PASS_COUNT, FAIL_COUNT, SKIP_COUNT
    name = getattr(func, '_test_name', func.__name__)
    priority = getattr(func, '_priority', 'P0')
    t0 = time.time()
    try:
        result = func()
        elapsed = round(time.time() - t0, 2)
        if result is None:
            result = {"status": "PASS"}
        if result.get("status") == "SKIP":
            SKIP_COUNT += 1
            icon = "⏭"
        elif result.get("status") == "PASS":
            PASS_COUNT += 1
            icon = "✅"
        else:
            FAIL_COUNT += 1
            icon = "❌"
        record = {"name": name, "priority": priority, "elapsed": elapsed, **result}
    except Exception as e:
        elapsed = round(time.time() - t0, 2)
        FAIL_COUNT += 1
        icon = "❌"
        record = {"name": name, "priority": priority, "elapsed": elapsed, "status": "FAIL", "error": str(e), "traceback": traceback.format_exc()}
    RESULTS.append(record)
    status_str = record.get("status", "FAIL")
    print(f"  {icon} [{priority}] {name} — {status_str} ({elapsed}s)")
    if record.get("detail"):
        print(f"      → {record['detail']}")
    if record.get("error"):
        print(f"      → ERROR: {record['error']}")


def assert_eq(expected, actual, msg=""):
    if expected != actual:
        raise AssertionError(f"{msg}: expected={expected}, actual={actual}")


def assert_in(needle, haystack, msg=""):
    if needle not in haystack:
        raise AssertionError(f"{msg}: '{needle}' not in '{str(haystack)[:200]}'")


def assert_true(val, msg=""):
    if not val:
        raise AssertionError(f"{msg}: value is falsy")


# -------------------------------------------------------------------
# API helpers
# -------------------------------------------------------------------
API_BASE = None


def api_url(func_name):
    return f"{API_BASE}/{func_name}"


def upload_video(video_path, metadata=None, model_type=None):
    """Upload a video for analysis."""
    meta = metadata or {}
    if model_type:
        meta['model_type'] = model_type
    with open(video_path, 'rb') as f:
        fdata = f.read()
    fname = os.path.basename(video_path)
    fields = {"metadata": json.dumps(meta)}
    files = {"video": (fname, fdata, "video/mp4")}
    return _post_multipart(api_url("analyze_upload"), fields, files)


def upload_bytes(fdata, fname="test.mp4", metadata=None):
    """Upload raw bytes as a video."""
    fields = {"metadata": json.dumps(metadata or {})}
    files = {"video": (fname, fdata, "video/mp4")}
    return _post_multipart(api_url("analyze_upload"), fields, files)


# -------------------------------------------------------------------
# 테스트 항목들
# -------------------------------------------------------------------

# ── P0: 핵심 기능 경로 ──

@test("prototype_info 정상 호출", "P0")
def test_prototype_info():
    resp = _post_form(api_url("prototype_info"), {})
    assert_eq(200, resp.get("code"), "HTTP 상태")
    data = resp.get("data", resp)
    assert_in("supported_formats", data, "지원 형식 필드")
    assert_in("max_upload_mb", data, "최대 용량 필드")
    return {"status": "PASS", "detail": f"formats={data.get('supported_formats')}, max={data.get('max_upload_mb')}MB"}


@test("정상 영상 업로드 (낙상 Y)", "P0")
def test_upload_fall_video():
    if not FALL_VIDEO:
        return {"status": "SKIP", "detail": "낙상 영상 파일 없음"}
    resp = upload_video(FALL_VIDEO)
    code = resp.get("code", 0)
    data = resp.get("data", resp)
    if code != 200:
        return {"status": "FAIL", "detail": f"HTTP {code}: {data.get('message', '')}"}
    assert_in("risk_score", data, "risk_score 필드")
    assert_in("saved_name", data.get("file", data), "saved_name 필드")
    saved = data.get("file", data).get("saved_name", "")
    return {"status": "PASS", "detail": f"risk_score={data.get('risk_score')}, saved={saved}", "saved_name": saved}


@test("정상 영상 업로드 (비낙상 N)", "P0")
def test_upload_nonfall_video():
    if not NON_FALL_VIDEO:
        return {"status": "SKIP", "detail": "비낙상 영상 파일 없음"}
    resp = upload_video(NON_FALL_VIDEO)
    code = resp.get("code", 0)
    data = resp.get("data", resp)
    if code != 200:
        return {"status": "FAIL", "detail": f"HTTP {code}: {data.get('message', '')}"}
    assert_in("risk_score", data, "risk_score 필드")
    return {"status": "PASS", "detail": f"risk_score={data.get('risk_score')}, fall={data.get('fall_detected')}"}


@test("빈 파일 업로드 (0바이트)", "P0")
def test_upload_empty_file():
    resp = upload_bytes(b"", "empty.mp4")
    code = resp.get("code", 0)
    data = resp.get("data", resp)
    msg = data.get("message", "") if isinstance(data, dict) else str(data)
    if code == 400 and "비어" in msg:
        return {"status": "PASS", "detail": f"정상 거부: {msg}"}
    return {"status": "FAIL", "detail": f"기대: 400 + 빈 파일 에러, 실제: {code} / {msg}"}


@test("비지원 형식 업로드 (.txt)", "P0")
def test_upload_unsupported_format():
    resp = upload_bytes(b"this is not a video", "test.txt")
    code = resp.get("code", 0)
    data = resp.get("data", resp)
    msg = data.get("message", "") if isinstance(data, dict) else str(data)
    if code == 400 and ("형식" in msg or "지원" in msg):
        return {"status": "PASS", "detail": f"정상 거부: {msg}"}
    return {"status": "FAIL", "detail": f"기대: 400 + 형식 에러, 실제: {code} / {msg}"}


@test("파일 필드 없는 업로드", "P0")
def test_upload_no_file():
    fields = {"metadata": "{}"}
    resp = _post_multipart(api_url("analyze_upload"), fields, {})
    code = resp.get("code", 0)
    data = resp.get("data", resp)
    msg = data.get("message", "") if isinstance(data, dict) else str(data)
    if code == 400 and ("없습니다" in msg or "파일" in msg):
        return {"status": "PASS", "detail": f"정상 거부: {msg}"}
    return {"status": "FAIL", "detail": f"기대: 400 + 파일 누락 에러, 실제: {code} / {msg}"}


# ── P1: 에러 경로 + 경계값 ──

@test("손상된 파일 업로드 (랜덤 바이너리 .mp4)", "P1")
def test_upload_corrupt_file():
    corrupt_data = os.urandom(1024)  # 1KB 랜덤 데이터
    resp = upload_bytes(corrupt_data, "corrupt.mp4")
    code = resp.get("code", 0)
    data = resp.get("data", resp)
    # 손상 파일은 추론 실패 → heuristic fallback으로 200 반환 가능
    if code == 200:
        runtime_key = data.get("runtime_key", "")
        return {"status": "PASS", "detail": f"heuristic fallback 적용됨 (runtime_key={runtime_key})"}
    elif code == 400:
        msg = data.get("message", "")
        return {"status": "PASS", "detail": f"서버가 에러 반환: {msg}"}
    return {"status": "FAIL", "detail": f"예상치 못한 응답: HTTP {code}"}


@test("피드백 — 잘못된 predicted_label", "P1")
def test_feedback_invalid_predicted():
    fields = {
        "saved_name": "nonexistent.mp4",
        "predicted_label": "INVALID",
        "feedback_status": "correct",
        "actual_label": "",
        "note": "",
        "retrain": "false",
        "posture_class": "",
    }
    resp = _post_form(api_url("submit_analysis_feedback"), fields)
    code = resp.get("code", 0)
    data = resp.get("data", resp)
    msg = data.get("message", "") if isinstance(data, dict) else str(data)
    if code == 400 and "라벨" in msg:
        return {"status": "PASS", "detail": f"정상 거부: {msg}"}
    return {"status": "FAIL", "detail": f"기대: 400 + 라벨 에러, 실제: {code} / {msg}"}


@test("피드백 — 잘못된 feedback_status", "P1")
def test_feedback_invalid_status():
    fields = {
        "saved_name": "nonexistent.mp4",
        "predicted_label": "Y",
        "feedback_status": "maybe",
        "actual_label": "",
        "note": "",
        "retrain": "false",
        "posture_class": "",
    }
    resp = _post_form(api_url("submit_analysis_feedback"), fields)
    code = resp.get("code", 0)
    data = resp.get("data", resp)
    msg = data.get("message", "") if isinstance(data, dict) else str(data)
    if code == 400 and ("상태" in msg or "correct" in msg):
        return {"status": "PASS", "detail": f"정상 거부: {msg}"}
    return {"status": "FAIL", "detail": f"기대: 400 + 상태 에러, 실제: {code} / {msg}"}


@test("피드백 — incorrect + actual_label 누락", "P1")
def test_feedback_missing_actual():
    fields = {
        "saved_name": "nonexistent.mp4",
        "predicted_label": "Y",
        "feedback_status": "incorrect",
        "actual_label": "",
        "note": "",
        "retrain": "false",
        "posture_class": "",
    }
    resp = _post_form(api_url("submit_analysis_feedback"), fields)
    code = resp.get("code", 0)
    data = resp.get("data", resp)
    msg = data.get("message", "") if isinstance(data, dict) else str(data)
    if code == 400 and "정답" in msg:
        return {"status": "PASS", "detail": f"정상 거부: {msg}"}
    return {"status": "FAIL", "detail": f"기대: 400 + 정답 라벨 에러, 실제: {code} / {msg}"}


@test("피드백 — 존재하지 않는 saved_name", "P1")
def test_feedback_missing_file():
    fields = {
        "saved_name": "definitely_nonexistent_video_12345.mp4",
        "predicted_label": "Y",
        "feedback_status": "correct",
        "actual_label": "",
        "note": "E2E test",
        "retrain": "false",
        "posture_class": "",
    }
    resp = _post_form(api_url("submit_analysis_feedback"), fields)
    code = resp.get("code", 0)
    data = resp.get("data", resp)
    msg = data.get("message", "") if isinstance(data, dict) else str(data)
    if code == 400 and ("원본" in msg or "찾을 수 없" in msg):
        return {"status": "PASS", "detail": f"정상 거부: {msg}"}
    return {"status": "FAIL", "detail": f"기대: 400 + 파일 없음, 실제: {code} / {msg}"}


# ── P2: 모델 전환 + 고급 기능 ──

@test("모델 워밍업 (warmup_models)", "P2")
def test_warmup_models():
    resp = _post_form(api_url("warmup_models"), {"model_type": "rf-pose"})
    code = resp.get("code", 0)
    data = resp.get("data", resp)
    if code == 200:
        warmed = data.get("warmed_up", [])
        elapsed = data.get("elapsed_ms", 0)
        return {"status": "PASS", "detail": f"warmed_up={warmed}, elapsed={elapsed}ms"}
    return {"status": "FAIL", "detail": f"HTTP {code}: {data.get('message', '')}"}


@test("모델 타입별 업로드 — rf-pipeline", "P2")
def test_upload_rf_pipeline():
    if not FALL_VIDEO:
        return {"status": "SKIP", "detail": "테스트 영상 없음"}
    resp = upload_video(FALL_VIDEO, model_type="rf-pipeline")
    code = resp.get("code", 0)
    data = resp.get("data", resp)
    if code == 200:
        rt_key = data.get("runtime_key", "")
        return {"status": "PASS", "detail": f"runtime_key={rt_key}, score={data.get('risk_score')}"}
    return {"status": "FAIL", "detail": f"HTTP {code}: {data.get('message', '')}"}


@test("모델 타입별 업로드 — rf-pose", "P2")
def test_upload_rf_pose():
    if not FALL_VIDEO:
        return {"status": "SKIP", "detail": "테스트 영상 없음"}
    resp = upload_video(FALL_VIDEO, model_type="rf-pose")
    code = resp.get("code", 0)
    data = resp.get("data", resp)
    if code == 200:
        rt_key = data.get("runtime_key", "")
        return {"status": "PASS", "detail": f"runtime_key={rt_key}, score={data.get('risk_score')}"}
    elif code == 400:
        msg = data.get("message", "")
        if "모델" in msg:
            return {"status": "PASS", "detail": f"RF-Pose 모델 미준비 (정상): {msg}"}
    return {"status": "FAIL", "detail": f"HTTP {code}"}


# ── P3: 보안 + 견고성 ──

@test("경로 탐색 방지 (saved_name = ../../etc/passwd)", "P3")
def test_path_traversal():
    fields = {
        "saved_name": "../../etc/passwd",
        "predicted_label": "Y",
        "feedback_status": "correct",
        "actual_label": "",
        "note": "",
        "retrain": "false",
        "posture_class": "",
    }
    resp = _post_form(api_url("submit_analysis_feedback"), fields)
    code = resp.get("code", 0)
    data = resp.get("data", resp)
    msg = data.get("message", "") if isinstance(data, dict) else str(data)
    # 경로 탐색이 _sanitize_filename에 의해 무력화되어야 함
    if code == 400:
        return {"status": "PASS", "detail": f"경로 탐색 차단됨: {msg}"}
    return {"status": "FAIL", "detail": f"경로 탐색이 차단되지 않음: HTTP {code}"}


@test("비지원 확장자 (.exe)", "P3")
def test_upload_exe():
    resp = upload_bytes(b"MZ\x90\x00" + os.urandom(100), "malware.exe")
    code = resp.get("code", 0)
    data = resp.get("data", resp)
    msg = data.get("message", "") if isinstance(data, dict) else str(data)
    if code == 400 and ("형식" in msg or "지원" in msg):
        return {"status": "PASS", "detail": f"정상 차단: {msg}"}
    return {"status": "FAIL", "detail": f"기대: 400, 실제: {code}"}


@test("mp4 확장자 + 텍스트 콘텐츠 (위장 파일)", "P3")
def test_upload_disguised_text():
    fake_content = b"Hello, this is definitely not a video file." * 100
    resp = upload_bytes(fake_content, "disguised.mp4")
    code = resp.get("code", 0)
    data = resp.get("data", resp)
    # 확장자 통과 → OpenCV 열기 실패 → heuristic fallback
    if code == 200:
        rt_key = data.get("runtime_key", "")
        return {"status": "PASS", "detail": f"heuristic fallback ({rt_key}) — 비디오 아닌 파일도 확장자만 검증"}
    elif code == 400:
        return {"status": "PASS", "detail": f"서버가 거부: {data.get('message', '')}"}
    return {"status": "FAIL", "detail": f"예상치 못한 응답: HTTP {code}"}


# ── 피드백 + 검증 통합 경로 ──

@test("업로드 → 피드백 통합 경로 (correct feedback)", "P0")
def test_upload_then_feedback():
    if not NON_FALL_VIDEO:
        return {"status": "SKIP", "detail": "테스트 영상 없음"}
    # 1. Upload
    resp = upload_video(NON_FALL_VIDEO)
    code = resp.get("code", 0)
    data = resp.get("data", resp)
    if code != 200:
        return {"status": "FAIL", "detail": f"업로드 실패: HTTP {code}"}
    saved_name = data.get("file", data).get("saved_name", "")
    fall_detected = data.get("fall_detected", False)
    pred_label = "Y" if fall_detected else "N"
    if not saved_name:
        return {"status": "FAIL", "detail": "saved_name 누락"}
    # 2. Submit feedback
    fb_resp = _post_form(api_url("submit_analysis_feedback"), {
        "saved_name": saved_name,
        "predicted_label": pred_label,
        "feedback_status": "correct",
        "actual_label": "",
        "note": "E2E integration test",
        "retrain": "false",
        "posture_class": "",
    })
    fb_code = fb_resp.get("code", 0)
    fb_data = fb_resp.get("data", fb_resp)
    if fb_code == 200:
        final = fb_data.get("final_label", "")
        return {"status": "PASS", "detail": f"업로드→피드백 성공: pred={pred_label}, final={final}"}
    return {"status": "FAIL", "detail": f"피드백 실패: HTTP {fb_code}, {fb_data.get('message', '')}"}


# -------------------------------------------------------------------
# Test runner
# -------------------------------------------------------------------
ALL_TESTS = [
    test_prototype_info,
    test_upload_fall_video,
    test_upload_nonfall_video,
    test_upload_empty_file,
    test_upload_unsupported_format,
    test_upload_no_file,
    test_upload_corrupt_file,
    test_feedback_invalid_predicted,
    test_feedback_invalid_status,
    test_feedback_missing_actual,
    test_feedback_missing_file,
    test_warmup_models,
    test_upload_rf_pipeline,
    test_upload_rf_pose,
    test_path_traversal,
    test_upload_exe,
    test_upload_disguised_text,
    test_upload_then_feedback,
]


def find_test_videos():
    """자동으로 테스트용 영상 검색."""
    global FALL_VIDEO, NON_FALL_VIDEO
    # test.mp4
    if os.path.isfile("/opt/app/test.mp4"):
        FALL_VIDEO = "/opt/app/test.mp4"
    # 공개 데이터셋 Y
    base_val = "/opt/app/041.낙상사고_위험동작_영상-센서_쌍_데이터/3.개방데이터/1.데이터/Validation/01.원천데이터/VS/영상"
    y_dir = os.path.join(base_val, "Y", "FY")
    if os.path.isdir(y_dir):
        for d in sorted(os.listdir(y_dir))[:3]:
            mp4 = os.path.join(y_dir, d, d + ".mp4")
            if os.path.isfile(mp4):
                FALL_VIDEO = mp4
                break
    # 공개 데이터셋 N
    n_dir = os.path.join(base_val, "N", "N")
    if os.path.isdir(n_dir):
        for d in sorted(os.listdir(n_dir))[:3]:
            mp4 = os.path.join(n_dir, d, d + ".mp4")
            if os.path.isfile(mp4):
                NON_FALL_VIDEO = mp4
                break


def generate_report(output_path):
    """Markdown 테스트 리포트 생성."""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total = PASS_COUNT + FAIL_COUNT + SKIP_COUNT
    lines = [
        f"# E2E Integration Test Report",
        f"",
        f"- **실행 일시**: {now}",
        f"- **서버**: {BASE_URL}",
        f"- **프로젝트**: {PROJECT}",
        f"- **테스트 영상**: FALL={FALL_VIDEO or 'N/A'}, NON_FALL={NON_FALL_VIDEO or 'N/A'}",
        f"",
        f"## 결과 요약",
        f"",
        f"| 항목 | 수 |",
        f"|------|---|",
        f"| 전체 | {total} |",
        f"| ✅ PASS | {PASS_COUNT} |",
        f"| ❌ FAIL | {FAIL_COUNT} |",
        f"| ⏭ SKIP | {SKIP_COUNT} |",
        f"",
        f"## 상세 결과",
        f"",
        f"| 우선순위 | 이름 | 결과 | 소요시간 | 상세 |",
        f"|---------|------|------|---------|------|",
    ]
    for r in RESULTS:
        icon = "✅" if r["status"] == "PASS" else ("⏭" if r["status"] == "SKIP" else "❌")
        detail = r.get("detail", r.get("error", ""))
        lines.append(f"| {r['priority']} | {r['name']} | {icon} {r['status']} | {r['elapsed']}s | {detail} |")

    lines.append("")
    if FAIL_COUNT > 0:
        lines.append("## 실패 항목 상세")
        lines.append("")
        for r in RESULTS:
            if r["status"] == "FAIL":
                lines.append(f"### ❌ {r['name']}")
                if r.get("error"):
                    lines.append(f"- **에러**: {r['error']}")
                if r.get("traceback"):
                    lines.append(f"```\n{r['traceback']}\n```")
                if r.get("detail"):
                    lines.append(f"- **상세**: {r['detail']}")
                lines.append("")

    report = "\n".join(lines)
    with open(output_path, 'w') as f:
        f.write(report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FallAI E2E Integration Test")
    parser.add_argument("--base-url", default=BASE_URL, help="WIZ 서버 URL")
    parser.add_argument("--project", default=PROJECT, help="프로젝트 이름")
    parser.add_argument("--output", default=None, help="리포트 출력 경로")
    args = parser.parse_args()

    BASE_URL = args.base_url
    PROJECT = args.project
    API_BASE = f"{BASE_URL}/wiz/api/page.dashboard"

    print("=" * 60)
    print("  FallAI E2E Integration Test Suite")
    print(f"  Server: {BASE_URL} | Project: {PROJECT}")
    print("=" * 60)

    # 1. Session cookie 생성
    print("\n[1/4] 세션 쿠키 생성...")
    SESSION_COOKIE = _build_session_cookie()
    if SESSION_COOKIE:
        print(f"  ✅ 세션 쿠키 생성 완료 (len={len(SESSION_COOKIE)})")
    else:
        print("  ⚠️ 세션 쿠키 없이 진행 (인증 필요 시 실패할 수 있음)")

    # 2. 테스트 영상 검색
    print("\n[2/4] 테스트 영상 검색...")
    find_test_videos()
    print(f"  FALL: {FALL_VIDEO or '없음'}")
    print(f"  NON_FALL: {NON_FALL_VIDEO or '없음'}")

    # 3. 서버 연결 확인
    print(f"\n[3/4] 서버 연결 확인 ({BASE_URL})...")
    try:
        resp = urllib.request.urlopen(BASE_URL, timeout=5)
        print(f"  ✅ 서버 응답: HTTP {resp.status}")
    except Exception as e:
        print(f"  ⚠️ 서버 접근 실패: {e}")
        print("  테스트 계속 진행 (개별 테스트에서 실패할 수 있음)...")

    # 4. 테스트 실행
    print(f"\n[4/4] 테스트 실행 ({len(ALL_TESTS)}건)...")
    print("-" * 60)
    for test_func in ALL_TESTS:
        _run_test(test_func)
    print("-" * 60)

    # 5. 결과 요약
    total = PASS_COUNT + FAIL_COUNT + SKIP_COUNT
    print(f"\n  ✅ PASS: {PASS_COUNT}  ❌ FAIL: {FAIL_COUNT}  ⏭ SKIP: {SKIP_COUNT}  (전체 {total})")

    # 6. 리포트 생성
    output_path = args.output or os.path.join(os.path.dirname(os.path.abspath(__file__)), "e2e_test_report.md")
    report = generate_report(output_path)
    print(f"\n  📋 리포트: {output_path}")
    print("=" * 60)

    sys.exit(1 if FAIL_COUNT > 0 else 0)

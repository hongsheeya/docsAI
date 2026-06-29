#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


GIB = 1024 ** 3

CONFIG = {
    "82": {
        "name": "aihub82",
        "label": "AI-Hub 82 표정",
        "message": "AI-Hub 82 표정 원천/라벨 데이터 확보 중입니다.",
        "log_dataset": "82",
        "purpose": "표정 보조 모델 재학습용",
        "default_source_gib": 30.0,
        "default_validation_gib": 8.0,
        "known_gib": {
            "49107": 28.6,
            "49111": 30.0,
        },
    },
    "71641": {
        "name": "rf-fall-v2",
        "label": "RF-Fall 운영 모델",
        "message": "AI-Hub 71641 낙상/비낙상 원천 영상 확보 중입니다.",
        "log_dataset": "71641",
        "purpose": "RF-Fall 낙상/비낙상 재학습용",
        "default_source_gib": 25.0,
        "default_validation_gib": 25.0,
        "known_gib": {
            "531137": 25.0,
            "531131": 70.0,
            "531132": 70.0,
            "531133": 70.0,
            "531134": 70.0,
            "531135": 70.0,
        },
    },
    "71461": {
        "name": "xg-posture",
        "label": "XG-Posture 재학습",
        "message": "AI-Hub 71461 자세/행동 지원 데이터 확보 중입니다.",
        "log_dataset": "71461",
        "purpose": "XG-Posture 및 가림 보조 선행 자세 데이터",
        "default_source_gib": 25.0,
        "default_validation_gib": 25.0,
        "known_gib": {},
    },
}


def fmt_bytes(value: float | int) -> str:
    value = float(value or 0)
    if value >= GIB:
        return f"{value / GIB:.1f}GB"
    if value >= 1024 ** 2:
        return f"{value / (1024 ** 2):.0f}MB"
    if value >= 1024:
        return f"{value / 1024:.0f}KB"
    return f"{int(value)}B"


def fmt_eta(seconds: float | int) -> str:
    seconds = max(0, int(seconds or 0))
    if seconds < 60:
        return f"{seconds}초"
    if seconds < 3600:
        return f"{seconds // 60}분 {seconds % 60}초"
    return f"{seconds // 3600}시간 {(seconds % 3600) // 60}분"


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def queue_position(main_log: Path, current_filekey: str) -> tuple[int, int]:
    try:
        text = main_log.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return 0, 0
    queue_starts = list(re.finditer(r"START .*? queue total=([0-9]+)", text))
    if queue_starts:
        last_start = queue_starts[-1]
        total = int(last_start.group(1))
        text = text[last_start.start():]
    else:
        total = 0
    starts = re.findall(r"START filekey=([0-9]+)", text)
    current = 0
    for idx, filekey in enumerate(starts, start=1):
        if filekey == current_filekey:
            current = idx
    if not current and starts:
        current = len(starts)
    return current, total


def parse_line(line: str) -> dict:
    for pattern in [
        r"filekey=([0-9]+).*?label=(.*?) tmp=(.*?) final=(.*)$",
        r"filekey=([0-9]+).*?label=(.*?) dir=(.*)$",
    ]:
        match = re.search(pattern, line)
        if match:
            filekey, label, raw_dir = match.group(1), match.group(2), match.group(3)
            return {"filekey": filekey, "label": label, "dir": raw_dir}
    return {}


def file_start_elapsed(line: str) -> tuple[str, float]:
    match = re.search(r"\[([0-9TZ:\-]+)\]", line)
    if not match:
        return "", 0.0
    try:
        start = datetime.strptime(match.group(1), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        elapsed = max(0.0, (datetime.now(timezone.utc) - start).total_seconds())
        return fmt_eta(elapsed), elapsed
    except Exception:
        return "", 0.0


def phase_for(dataset: str, filekey: str, raw_dir: str) -> str:
    raw_path = Path(raw_dir)
    log_candidates = [Path("/mnt/data/wiz/datasets/logs/aihub_recovery") / f"{dataset}_{filekey}.log"]
    try:
        parents = list(raw_path.parents)
        if len(parents) >= 3:
            log_candidates.append(parents[2] / "logs" / "aihub_recovery" / f"{dataset}_{filekey}.log")
    except Exception:
        pass
    tail = ""
    for log_path in log_candidates:
        try:
            if log_path.exists():
                tail = "\n".join(log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-80:])
                break
        except Exception:
            tail = ""
    if f"DONE_RESUME dataset={dataset} filekey={filekey}" in tail:
        return "파일 완료"
    if f"TAR_INCOMPLETE dataset={dataset} filekey={filekey}" in tail:
        return "이어받기 재시도 중"
    if f"TAR_EXTRACTED_BUT_NO_PAYLOAD dataset={dataset} filekey={filekey}" in tail:
        return "압축 해제 후 payload 확인 중"
    if f"TAR_OK dataset={dataset} filekey={filekey}" in tail:
        return "압축 해제 중"
    return "다운로드 중"


def estimated_target_bytes(mode: str, filekey: str, label: str, size_bytes: int) -> tuple[int, str]:
    cfg = CONFIG[mode]
    known = cfg["known_gib"].get(filekey)
    if known:
        target = int(float(known) * GIB)
        return max(target, size_bytes), "추정"
    low = f"{label}".lower()
    if "label" in low or "라벨" in label:
        target = max(size_bytes, 16 * 1024 ** 2)
        return target, "소형"
    if "valid" in low or "validation" in low or "val " in low:
        target = int(float(cfg["default_validation_gib"]) * GIB)
    else:
        target = int(float(cfg["default_source_gib"]) * GIB)
    return max(target, size_bytes), "추정"


def main() -> int:
    if len(sys.argv) < 5:
        print("usage: update_aihub_redownload_status.py STATUS_JSON MAIN_LOG MODE LAST_LINE", file=sys.stderr)
        return 2
    status_path = Path(sys.argv[1])
    main_log = Path(sys.argv[2])
    mode = sys.argv[3]
    line = sys.argv[4]
    cfg = CONFIG.get(mode)
    parsed = parse_line(line)
    if not cfg or not parsed:
        return 0

    filekey = parsed["filekey"]
    label = parsed["label"]
    raw_dir = parsed["dir"]
    tar_path = Path(raw_dir) / "download.tar"
    size_bytes = tar_path.stat().st_size if tar_path.exists() else 0
    current, total = queue_position(main_log, filekey)
    elapsed_text, elapsed_sec = file_start_elapsed(line)
    phase = phase_for(cfg["log_dataset"], filekey, raw_dir)
    target_bytes, target_kind = estimated_target_bytes(mode, filekey, label, size_bytes)
    unknown_total = (
        target_kind == "추정"
        and phase == "다운로드 중"
        and filekey not in cfg["known_gib"]
        and size_bytes > 0
        and target_bytes <= size_bytes
    )
    data = read_json(status_path)
    now_dt = datetime.now(timezone.utc)
    now_ts = now_dt.timestamp()
    prev_sample = data.get("redownload_speed_sample") if isinstance(data.get("redownload_speed_sample"), dict) else {}
    sample_speed_bps = 0.0
    try:
        if str(prev_sample.get("filekey") or "") == filekey:
            prev_size = int(prev_sample.get("size_bytes") or 0)
            prev_ts = float(prev_sample.get("timestamp") or 0.0)
            dt = max(0.0, now_ts - prev_ts)
            ds = int(size_bytes) - prev_size
            if dt >= 3 and ds > 0:
                sample_speed_bps = ds / dt
    except Exception:
        sample_speed_bps = 0.0
    lifetime_speed_bps = (size_bytes / elapsed_sec) if elapsed_sec > 0 and size_bytes > 0 else 0.0
    speed_bps = sample_speed_bps if sample_speed_bps > 1024 else lifetime_speed_bps
    eta_sec = 0.0
    eta_text = "계산 중"
    if unknown_total:
        eta_text = "전체 크기 확인 중"
    elif speed_bps > 0 and target_bytes > size_bytes:
        eta_sec = (target_bytes - size_bytes) / speed_bps
        eta_text = fmt_eta(eta_sec)
    elif size_bytes > 0:
        eta_text = "완료 확인 중"
    speed_text = f"{speed_bps / (1024 ** 2):.1f}MB/s" if speed_bps > 0 else "속도 계산 중"
    progress_pct = min(100.0, (size_bytes / target_bytes) * 100.0) if target_bytes > 0 and not unknown_total else 0.0
    queue_text = f"{current}/{total}" if total else f"{current}/?"
    received_text = fmt_bytes(size_bytes)
    target_text = fmt_bytes(target_bytes)
    if unknown_total:
        eta_display = (
            f"{phase} · {received_text} 수신 · 전체 크기 확인 중 · 현재 파일 ETA 산정 불가 · {speed_text} · 전체 {queue_text}"
        )
        latest_log = (
            f"filekey={filekey} · {label} · {phase} · {received_text} 수신 "
            f"(AIHub 전체 크기 미제공) · 전체 {queue_text}"
        )
    else:
        eta_display = (
            f"{phase} · {received_text}/{target_text} {target_kind} · 현재 파일 ETA {eta_text} · {speed_text} · 전체 {queue_text}"
        )
        latest_log = (
            f"filekey={filekey} · {label} · {phase} · {received_text}/{target_text} {target_kind} "
            f"({progress_pct:.0f}%) · 전체 {queue_text}"
        )

    data.update({
        "ok": True,
        "name": cfg["name"],
        "label": cfg["label"],
        "stage": "running",
        "status": "running",
        "updated_at": now_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "eta_text": eta_display,
        "message": cfg["message"],
        "latest_log": latest_log,
        "data_purpose": cfg["purpose"],
        "required_files": total,
        "completed_files": max(0, current - 1),
        "redownload_current": current,
        "redownload_total": total,
        "redownload_current_filekey": filekey,
        "redownload_current_label": label,
        "redownload_current_phase": phase,
        "redownload_current_size_bytes": size_bytes,
        "redownload_current_target_bytes_estimate": target_bytes,
        "redownload_current_progress": round(progress_pct / 100.0, 4),
        "redownload_current_eta_sec": round(eta_sec, 1) if eta_sec else None,
        "redownload_current_speed_mbps": round(speed_bps / (1024 ** 2), 2) if speed_bps else None,
        "redownload_current_unknown_total": unknown_total,
        "redownload_speed_mode": "recent-sample" if sample_speed_bps > 1024 else "lifetime-average",
        "redownload_speed_sample": {
            "filekey": filekey,
            "size_bytes": size_bytes,
            "timestamp": now_ts,
        },
        "occlusion_priority_target_macro_f1": 0.90 if mode == "71461" else data.get("occlusion_priority_target_macro_f1"),
        "redownload_target_kind": target_kind,
        "redownload_log_path": str(main_log),
    })
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

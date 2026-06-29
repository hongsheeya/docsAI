/// <reference path="../../types/wiz-view-modules.d.ts" />

import { OnDestroy, OnInit, ViewChild, ElementRef } from '@angular/core';
import { Service } from '@wiz/libs/portal/season/service';
import { PoseLandmarker, FilesetResolver, DrawingUtils } from '@mediapipe/tasks-vision';

declare const wiz: any;

const LAST_ANALYSIS_STORAGE_KEY = 'fallai:last-analysis';
const PRIVACY_VIEW_STORAGE_KEY = 'fallai:admin-privacy-view';

// ── COCO-17 Skeleton Constants ──
const COCO_SKELETON_PAIRS: [number, number][] = [
    [0, 1], [0, 2], [1, 3], [2, 4],
    [5, 6], [5, 7], [7, 9], [6, 8], [8, 10],
    [5, 11], [6, 12], [11, 12],
    [11, 13], [13, 15], [12, 14], [14, 16],
];
const COCO_KP_COLORS: Record<number, string> = {
    0: '#f0abfc', 1: '#f0abfc', 2: '#f0abfc', 3: '#f0abfc', 4: '#f0abfc',
    5: '#67e8f9', 6: '#67e8f9', 7: '#67e8f9', 8: '#67e8f9', 9: '#67e8f9', 10: '#67e8f9',
    11: '#86efac', 12: '#86efac', 13: '#86efac', 14: '#86efac', 15: '#86efac', 16: '#86efac',
};
const COCO_HAND_KEYPOINTS = new Set<number>([9, 10]);

// ── MediaPipe 33-landmark skeleton ──
const MP_POSE_CONNECTIONS: [number, number][] = [
    [0, 1], [1, 2], [2, 3], [3, 7],
    [0, 4], [4, 5], [5, 6], [6, 8],
    [9, 10],
    [11, 12],
    [11, 13], [13, 15], [15, 17], [15, 19], [15, 21], [17, 19],
    [12, 14], [14, 16], [16, 18], [16, 20], [16, 22], [18, 20],
    [11, 23], [12, 24], [23, 24],
    [23, 25], [25, 27], [27, 29], [27, 31], [29, 31],
    [24, 26], [26, 28], [28, 30], [28, 32], [30, 32],
];

const MP_LANDMARK_COLORS: Record<number, string> = (() => {
    const c: Record<number, string> = {};
    for (let i = 0; i <= 10; i++) c[i] = '#f0abfc';
    for (let i = 11; i <= 22; i++) c[i] = '#67e8f9';
    for (let i = 23; i <= 32; i++) c[i] = '#86efac';
    return c;
})();
const MP_WRIST_LANDMARKS = new Set<number>([15, 16]);
const MP_HAND_DETAIL_LANDMARKS = new Set<number>([17, 18, 19, 20, 21, 22]);

const MP_FRAME_INTERVAL_MS = 66; // ~15fps throttle
const MP_MAX_POSES = 20;
const MP_PERSON_COLORS = [
    '#67e8f9', '#f0abfc', '#86efac', '#fbbf24', '#a78bfa',
    '#fb7185', '#38bdf8', '#34d399', '#f97316', '#c084fc',
    '#2dd4bf', '#facc15', '#60a5fa', '#f472b6', '#4ade80',
    '#e879f9', '#22d3ee', '#a3e635', '#fdba74', '#93c5fd',
];

// ── Kalman 1D Filter (constant-velocity model) for occluded landmark prediction ──
class Kalman1D {
    private _pos = 0;
    private _vel = 0;
    private _p00 = 1;
    private _p01 = 0;
    private _p10 = 0;
    private _p11 = 1;
    private _init = false;

    reset() {
        this._init = false;
        this._pos = 0;
        this._vel = 0;
    }

    predict(): number {
        if (!this._init) return 0;
        this._pos += this._vel;
        this._p00 += this._p01 + this._p10 + this._p11 + 0.0005;
        this._p01 += this._p11;
        this._p10 += this._p11;
        this._p11 += 0.005;
        return this._pos;
    }

    update(z: number): number {
        const R = 0.003;
        if (!this._init) {
            this._pos = z;
            this._vel = 0;
            this._p00 = R;
            this._p01 = 0;
            this._p10 = 0;
            this._p11 = 0.1;
            this._init = true;
            return z;
        }
        const s = this._p00 + R;
        const k0 = this._p00 / s;
        const k1 = this._p10 / s;
        const y = z - this._pos;
        this._pos += k0 * y;
        this._vel += k1 * y;
        const p00 = this._p00 * (1 - k0);
        const p01 = this._p01 * (1 - k0);
        this._p10 -= k1 * this._p00;
        this._p11 -= k1 * this._p01;
        this._p00 = p00;
        this._p01 = p01;
        return this._pos;
    }

    get initialized(): boolean { return this._init; }
    get position(): number { return this._pos; }
}

type MpLandmarkFilters = { x: Kalman1D; y: Kalman1D; missCount: number }[];
type MpPoseTrack = { id: number; centerX: number; centerY: number; lastSeenMs: number; missed: number };

export class Component implements OnInit, OnDestroy {
    public prototypeInfo: any = null;
    public inputMode: string = 'webcam';
    public analysisProfile: string = 'balanced';
    public selectedModelType: string = 'rf-dual';
    public loadingInfo: boolean = true;
    public privacyViewMode: 'skeleton' | 'raw' = 'skeleton';

    public selectedFile: File | null = null;
    public selectedFiles: File[] = [];
    public selectedVideoUrl: string = '';
    public uploadWorkflowMode: 'analyze' | 'train' = 'analyze';
    public trainingTargetModel: string = 'rf-dual';
    public videoMeta: any = { duration: 0, width: 0, height: 0, fps: 0 };
    public analysisSavedName: string = '';
    public dragover: boolean = false;
    public analyzing: boolean = false;
    public uploadProgress: number = 0;
    public analysisResult: any = null;
    public rootAnalysisResult: any = null;
    public selectedPersonAnalysisId: string = 'overall';
    public errorMessage: string = '';
    public uploadLogEntries: any[] = [];
    public uploadChunkSummary: any = null;

    public feedbackStatus: string = '';
    public feedbackActualLabel: string = '';
    public feedbackPostureClass: string = '';
    public feedbackNote: string = '';
    public feedbackSubmitting: boolean = false;
    public feedbackRetrainDone: boolean = false;
    public feedbackRetrainRequested: boolean = false;
    public feedbackMessage: string = '';
    public feedbackMessageType: string = 'info';
    public feedbackAmbiguityFlag: boolean = false;
    public feedbackOcclusionFlag: boolean = false;
    public feedbackShortClipFlag: boolean = false;
    public feedbackElapsedSec: number = 0;
    private feedbackTimerHandle: any = null;

    public trainingUploadLabel: string = 'N';
    public trainingUploadPostureClass: string = '';
    public trainingUploadNote: string = '';
    public trainingUploading: boolean = false;
    public trainingUploadDone: number = 0;
    public trainingUploadTotal: number = 0;
    public trainingUploadMessage: string = '';
    public trainingUploadMessageType: string = 'info';
    public trainingJob: any = null;
    public continuousTrainingStatus: any = null;
    public continuousTrainingItems: any[] = [];
    public continuousTrainingResuming: Record<string, boolean> = {};
    public trainingJobStarting: boolean = false;
    public trainingJobApplying: boolean = false;
    private trainingJobPollHandle: any = null;
    private continuousTrainingPollHandle: any = null;

    public fallbackTrainingTargetOptions = [
        { key: 'rf-dual', label: 'RF-Dual 통합', job_type: 'full', description: '낙상 Y/N과 행동 라벨을 함께 반영합니다.' },
        { key: 'rf-fall-v2', label: 'RF-Fall v2', job_type: 'rf', description: '낙상/비낙상 이진 분류 보강 자료입니다.' },
        { key: 'xg-posture', label: 'XG-Posture', job_type: 'posture', description: 'stand/walk/run/sit/lie 행동 분류 보강 자료입니다.' },
        { key: 'facial-aihub82', label: 'AI-Hub 82 표정', job_type: 'aihub82', description: '표정 보조 모델 자료로 표시하고 연속 학습 상태를 추적합니다.' },
        { key: 'driver-aihub173', label: 'AI-Hub 173 상태', job_type: 'aihub173', description: '졸림/하품/통화/흡연 보조 모델 자료로 표시합니다.' },
    ];

    public postureClasses = [
        { code: 'stand', label: '서기', icon: '🧍' },
        { code: 'walk', label: '걷기', icon: '🚶' },
        { code: 'sit', label: '앉기', icon: '🪑' },
        { code: 'run', label: '뛰기', icon: '🏃' },
        { code: 'lie', label: '눕기', icon: '🛌' },
        { code: 'fall', label: '낙상', icon: '⚠️' },
    ];

    public webcamStream: MediaStream | null = null;
    public webcamReady: boolean = false;
    public webcamError: string = '';

    public poseLandmarker: any = null;
    public mpRunning: boolean = false;
    public mpProcessing: boolean = false;
    public mpRafId: number = 0;
    public mpInitializing: boolean = false;
    public mpReady: boolean = false;
    public mpFps: number = 0;
    public mpFrameCount: number = 0;
    public mpFpsTimer: any = null;
    public mpResizeObserver: any = null;
    public mpLastFrameTime: number = 0;
    public mpDetectedPoseCount: number = 0;
    public kalmanFilters: { x: Kalman1D; y: Kalman1D; missCount: number }[] = [];
    private mpPoseKalmanFilters: { x: Kalman1D; y: Kalman1D; missCount: number }[][] = [];
    private mpPoseTrackFilters: Record<number, MpLandmarkFilters> = {};
    private mpPoseTracks: MpPoseTrack[] = [];
    private mpNextPoseTrackId: number = 1;
    private readonly KF_MAX_MISS: number = 15;
    private readonly KF_VIS_THRESHOLD: number = 0.15;
    private readonly KF_HAND_VIS_THRESHOLD: number = 0.55;

    public realtimeActive: boolean = false;
    public realtimeStarting: boolean = false;
    public realtimeChunkCount: number = 0;
    public postureTimeline: { time: string; posture: string; label: string; score: number; chunkId: number }[] = [];
    public postureTransitions: { time: string; from: string; to: string; fromLabel: string; toLabel: string }[] = [];
    public currentPosture: string = '';
    public currentPostureLabel: string = '';
    public postureTransitionText: string = '';
    public realtimeCumulativeScore: number = 0;
    public realtimeScoreHistory: number[] = [];
    public realtimeIntervalSec: number = 5;
    public realtimeOverlapSec: number = 3;
    public realtimeLastElapsed: number = 0;
    public realtimePendingConfirmation: boolean = false;
    private recorderSlots: { recorder: MediaRecorder; chunks: Blob[]; timer: any; slotId: number; durationSec: number; startedAtMs: number }[] = [];
    private recorderSpawnTimer: any = null;
    private nextSlotId: number = 0;
    private realtimeSessionId: string = '';
    private realtimeSessionStartedAt: number = 0;
    private dispatchQueue: { blob: Blob; chunkId: number; durationSec: number; chunkWindow: any; attempt?: number }[] = [];
    private dispatchWorkerRunning: boolean = false;
    private realtimeWindowKeys: Set<string> = new Set();
    private uploadAnalysisRequestKey: string = '';
    public dispatchQueueSize: number = 0;
    public dispatchMaxQueue: number = 6;
    public realtimeDispatching: boolean = false;

    public realtimeOverlayScore: number = 0;
    public realtimeOverlayLevel: string = 'low';
    public realtimeOverlayLabel: string = '대기';
    public realtimeOverlayBasis: string = '';
    public realtimeOverlayRuntime: string = '';
    public realtimeOverlayFlash: boolean = false;
    public realtimeOverlayFlashTimer: any = null;
    public lastNonEmptyOverlayBasis: string = '';

    public realtimeLogEntries: any[] = [];
    public logDetailOpen: boolean = false;
    public logDetailEntry: any = null;
    public logDetailVideoUrl: string = '';
    public logDetailVideoLoading: boolean = false;
    public logDetailVideoError: string = '';
    public logDetailVideoRange: { startSec: number; endSec: number } | null = null;
    public logDetailVideoMode: 'blob' | 'upload' | '' = '';
    public logFeedbackStatus: string = '';
    public logFeedbackActualLabel: string = '';
    public logFeedbackPostureClass: string = '';
    public logFeedbackNote: string = '';
    public logFeedbackSubmitting: boolean = false;
    public logFeedbackAmbiguityFlag: boolean = false;
    public logFeedbackOcclusionFlag: boolean = false;
    public logFeedbackShortClipFlag: boolean = false;
    public logFeedbackRetrainRequested: boolean = false;
    public logFeedbackElapsedSec: number = 0;
    private logFeedbackTimerHandle: any = null;
    public logFeedbackMessage: string = '';
    public logFeedbackMessageType: string = 'info';

    public detectionReplayPlaying: boolean = false;
    public detectionReplayIndex: number = 0;
    public detectionReplayTimer: any = null;
    public bboxOverlayEnabled: boolean = false;
    public alertWorkflow: any = null;
    public emergencyPopupOpen: boolean = false;
    public referencePopupOpen: boolean = false;
    public referencePopupData: any = null;
    public referencePopupLoading: boolean = false;
    public realtimePerfStats: any = { avgRtt: 0, avgServer: 0, currentInterval: 0, discarded: 0, queued: 0, retrying: 0, failed: 0 };
    public realtimeRoundTripHistory: number[] = [];
    public realtimeServerTimeHistory: number[] = [];
    public realtimeAdaptiveEnabled: boolean = false;

    public POSTURE_LABEL_MAP: Record<string, string> = {
        stand: '서기', walk: '걷기', run: '뛰기', sit: '앉기', lie: '눕기', fall: '낙상', unknown: '미확인'
    };
    public DECISION_STATE_META: Record<string, any> = {
        safe: { label: '안전', color: 'text-emerald-600', icon: '✅', badgeCls: 'bg-emerald-100 text-emerald-700 border-emerald-200' },
        posture_only: { label: '자세 감지', color: 'text-sky-600', icon: '🧍', badgeCls: 'bg-sky-100 text-sky-700 border-sky-200' },
        fall_suspected: { label: '낙상 의심', color: 'text-amber-600', icon: '⚠️', badgeCls: 'bg-amber-100 text-amber-700 border-amber-200' },
        fall_confirmed: { label: '낙상 확인', color: 'text-rose-600', icon: '🚨', badgeCls: 'bg-rose-100 text-rose-700 border-rose-200' },
        uncertain: { label: '불확실', color: 'text-violet-600', icon: '❓', badgeCls: 'bg-violet-100 text-violet-700 border-violet-200' },
    };

    @ViewChild('webcamVideo') webcamVideoRef!: ElementRef<HTMLVideoElement>;
    @ViewChild('mpPoseCanvas') set _mpPoseCanvasSetter(el: ElementRef<HTMLCanvasElement>) { this._mpPoseCanvasEl = el; }
    private _mpPoseCanvasEl: ElementRef<HTMLCanvasElement> | null = null;
    private mpInputCanvas: HTMLCanvasElement | null = null;
    private mpInputCtx: CanvasRenderingContext2D | null = null;
    private mpInputTransform: { side: number; offsetX: number; offsetY: number; drawW: number; drawH: number } | null = null;
    @ViewChild('realtimeBboxCanvas') realtimeBboxCanvasRef!: ElementRef<HTMLCanvasElement>;
    @ViewChild('uploadBboxCanvas') uploadBboxCanvasRef!: ElementRef<HTMLCanvasElement>;
    @ViewChild('uploadPreviewVideo') uploadPreviewVideoRef!: ElementRef<HTMLVideoElement>;
    @ViewChild('detCanvas') detCanvasRef!: ElementRef<HTMLCanvasElement>;
    @ViewChild('logScrollContainer') logScrollContainerRef!: ElementRef;

    constructor(public service: Service) { }

    private getChunkConfig(): { version: string; chunkSec: number; spawnMs: number; maxSlots: number; maxQueue: number; bootstrapDurations: number[]; strideSec: number } {
        const backend = this.prototypeInfo?.chunk_policy?.realtime || {};
        if (backend?.enabled === true || backend?.steady_sec || backend?.stride_sec) {
            return {
                version: String(backend?.version || 'overlap-4s-stride2-v3'),
                chunkSec: Number(backend?.steady_sec || 4),
                spawnMs: Number(backend?.spawn_ms || 2000),
                maxSlots: Number(backend?.max_slots || 2),
                maxQueue: Number(backend?.max_queue || 120),
                bootstrapDurations: Array.isArray(backend?.dense_intro) ? backend.dense_intro.map((v: any) => Number(v || 0)).filter((v: number) => v > 0) : [],
                strideSec: Number(backend?.stride_sec || 2),
            };
        }
        const key = this.selectedModelType || '';
        if (key === 'rf-dual' || key === 'rf-pipeline') return { version: 'legacy-rf-dual-v1', chunkSec: 4, spawnMs: 4000, maxSlots: 2, maxQueue: 120, bootstrapDurations: [], strideSec: 4 };
        return { version: 'legacy-generic-v1', chunkSec: 4, spawnMs: 4000, maxSlots: 2, maxQueue: 120, bootstrapDurations: [], strideSec: 4 };
    }

    private formatChunkSecond(value: number): string {
        const rounded = Math.round((Number(value || 0)) * 10) / 10;
        return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
    }

    private buildChunkLabel(startSec: number, endSec: number): string { return `${this.formatChunkSecond(startSec)}~${this.formatChunkSecond(endSec)}초`; }
    private buildRealtimeChunkWindow(startedAtMs: number, durationSec: number) {
        const startSec = Math.max(0, (startedAtMs - this.realtimeSessionStartedAt) / 1000);
        const endSec = startSec + Number(durationSec || 0);
        return { startSec: Math.round(startSec * 10) / 10, endSec: Math.round(endSec * 10) / 10, label: this.buildChunkLabel(startSec, endSec) };
    }

    private async readJsonResponse(res: Response): Promise<any> {
        const text = await res.text();
        const trimmed = String(text || '').trim();
        if (!trimmed) {
            throw new Error(`서버 응답이 비어 있습니다. HTTP ${res.status || 'unknown'}`);
        }
        const contentType = String(res.headers?.get('content-type') || '').toLowerCase();
        if (contentType.includes('text/html') || /^<!doctype\s+html/i.test(trimmed) || /^<html[\s>]/i.test(trimmed)) {
            const titleMatch = trimmed.match(/<title[^>]*>(.*?)<\/title>/i);
            const title = titleMatch ? titleMatch[1].replace(/\s+/g, ' ').trim() : '';
            const detail = title ? ` · ${title}` : '';
            throw new Error(`서버가 JSON 대신 HTML 오류 페이지를 반환했습니다. HTTP ${res.status || 'unknown'}${detail}. 화면을 새로고침한 뒤 다시 시도하고, 계속 반복되면 파일 수를 줄여 나눠 등록하거나 학습 현황/서버 로그를 확인하세요.`);
        }
        try {
            return JSON.parse(trimmed);
        } catch (e) {
            const normalized = trimmed.replace(/([:\[,]\s*)(?:NaN|-?Infinity)(?=\s*[,}\]])/g, (_match, prefix) => `${prefix}0`);
            if (normalized !== trimmed) {
                try {
                    return JSON.parse(normalized);
                } catch (_normalizedError) { }
            }
            const snippet = trimmed.replace(/\s+/g, ' ').slice(0, 180);
            if (/^upstream\b/i.test(snippet) || snippet.includes('upstream connect error')) {
                throw new Error(`서버 업스트림 연결이 끊겼습니다. 요청은 일부 처리됐을 수 있으니 학습 현황을 새로고침해 확인하세요. (${snippet})`);
            }
            throw new Error(`서버가 JSON이 아닌 응답을 반환했습니다. HTTP ${res.status || 'unknown'} · ${snippet}`);
        }
    }

    private requestErrorMessage(error: any, context: string = '요청'): string {
        const raw = String(error?.message || error || '').trim();
        if (raw.includes('JSON 대신 HTML') || raw.includes('<!DOCTYPE') || raw.includes('Unexpected token')) {
            return `${context} 오류: 서버가 정상 JSON 대신 오류 화면을 반환했습니다. 먼저 페이지를 새로고침하고 다시 시도하세요. 계속 반복되면 선택한 파일을 100개 이하로 나눠 등록하고, 학습 현황 카드에서 저장 여부를 확인하세요. 상세: ${raw}`;
        }
        if (raw.includes('upstream connect error') || raw.includes('업스트림')) {
            return `${context} 오류: 서버 연결이 중간에 끊겼습니다. 일부 파일은 저장됐을 수 있으니 학습 현황을 새로고침한 뒤, 실패한 파일만 다시 등록하세요. 상세: ${raw}`;
        }
        return `${context} 오류: ${raw || '알 수 없는 오류'}`;
    }

    private currentRootAnalysisResult(): any {
        return this.rootAnalysisResult || this.analysisResult || null;
    }

    private findPersonAnalysisItem(personId: string, root?: any): any {
        const target = String(personId || '');
        const people = (root || this.currentRootAnalysisResult())?.multi_person?.people || [];
        if (!Array.isArray(people) || !target) return null;
        return people.find((item: any) => String(item?.id || '') === target || String(item?.track_id || '') === target || String(item?.person_label || '') === target) || null;
    }

    private applyAnalysisRoot(result: any, preserveSelection: boolean = true) {
        this.rootAnalysisResult = result || null;
        const previousId = preserveSelection ? String(this.selectedPersonAnalysisId || 'overall') : 'overall';
        const selectedItem = previousId !== 'overall' ? this.findPersonAnalysisItem(previousId, result) : null;
        if (selectedItem?.result) {
            this.selectedPersonAnalysisId = String(selectedItem.id || previousId);
            this.analysisResult = selectedItem.result;
        } else {
            this.selectedPersonAnalysisId = 'overall';
            this.analysisResult = result || null;
        }
        this.detectionReplayIndex = 0;
        if (this.detectionReplayPlaying) this.stopDetectionReplay();
    }

    private clearAnalysisState() {
        this.rootAnalysisResult = null;
        this.analysisResult = null;
        this.selectedPersonAnalysisId = 'overall';
        this.detectionReplayIndex = 0;
        if (this.detectionReplayPlaying) this.stopDetectionReplay();
    }

    public selectPersonAnalysis(personId: string) {
        const root = this.currentRootAnalysisResult();
        if (!root) return;
        const nextId = String(personId || 'overall');
        if (nextId === 'overall' || nextId === String(this.selectedPersonAnalysisId || 'overall')) {
            this.selectedPersonAnalysisId = 'overall';
            this.analysisResult = root;
        } else {
            const item = this.findPersonAnalysisItem(nextId, root);
            if (!item?.result) return;
            this.selectedPersonAnalysisId = String(item.id || nextId);
            this.analysisResult = item.result;
        }
        this.detectionReplayIndex = 0;
        if (this.detectionReplayPlaying) this.stopDetectionReplay();
        this.updateRealtimeOverlay();
        this.service.render();
    }

    public multiPersonPeople(): any[] {
        const people = this.currentRootAnalysisResult()?.multi_person?.people || [];
        return Array.isArray(people) ? people : [];
    }

    public hasMultiPersonCards(): boolean {
        return this.multiPersonPeople().length > 0;
    }

    public multiPersonSummaryLine(): string {
        const root = this.currentRootAnalysisResult() || {};
        return root?.multi_person?.summary_line || `${this.multiPersonPeople().length}명 사람별 행동 분석`;
    }

    public multiPersonCardItems(): any[] {
        return this.multiPersonPeople();
    }

    public isPersonAnalysisSelected(): boolean {
        return this.selectedPersonAnalysisId !== 'overall' && Boolean(this.analysisResult?.person_id || this.analysisResult?.runtime_inference?.person_track);
    }

    public selectedPersonDetailsVisible(): boolean {
        return !this.hasMultiPersonCards() || this.isPersonAnalysisSelected();
    }

    public realtimeDetailOverlayTop(): string {
        return this.hasMultiPersonCards() ? '244px' : '12px';
    }

    public personCardClass(item: any): string {
        const selected = String(item?.id || '') === String(this.selectedPersonAnalysisId || 'overall');
        const level = item?.risk_level || 'low';
        const base = selected ? 'ring-2 ring-sky-400 border-sky-300 ' : 'border-zinc-200 ';
        if (level === 'high') return base + 'bg-rose-50 text-rose-950';
        if (level === 'medium') return base + 'bg-amber-50 text-amber-950';
        return base + 'bg-white text-zinc-900';
    }

    public personCardDotClass(item: any): string {
        const level = item?.risk_level || 'low';
        if (level === 'high') return 'bg-rose-500';
        if (level === 'medium') return 'bg-amber-500';
        return 'bg-emerald-500';
    }

    public personCardRiskText(item: any): string {
        const pct = Math.round(Number(item?.risk_score || 0) * 100);
        const label = String(item?.risk_label || '').trim();
        return `${pct}%${label ? ' · ' + label : ''}`;
    }

    public personCardMetaText(item: any): string {
        const frames = Number(item?.frame_count || 0);
        const conf = Math.round(Number(item?.avg_conf || 0) * 100);
        return `${frames}프레임 · 포즈 ${conf}%`;
    }

    public selectedPersonHeaderText(): string {
        if (this.selectedPersonAnalysisId === 'overall') return '인원 선택';
        const item = this.findPersonAnalysisItem(this.selectedPersonAnalysisId);
        return item?.person_label ? `${item.person_label} 분석` : '선택 인원 분석';
    }

    private async warmupRealtimeModels() {
        const start = performance.now();
        try {
            const res = await fetch(`/wiz/api/page.dashboard/warmup_models?model_type=${encodeURIComponent(this.selectedModelType || 'rf-dual')}`);
            const json = await this.readJsonResponse(res);
            const elapsed = Math.round(performance.now() - start);
            if (json?.code === 200) {
                this.realtimePerfStats.warmupMs = Number(json?.data?.elapsed_ms || elapsed);
                this.realtimePerfStats.warmed = Array.isArray(json?.data?.warmed_up) ? json.data.warmed_up.join(', ') : '';
            }
        } catch (e) {
            this.realtimePerfStats.warmupFailed = true;
        }
    }

    private fallbackLogDescription(result: any): string {
        const summary = String(result?.summary || '').trim();
        if (summary) return summary;
        const explain = Array.isArray(result?.explain) ? result.explain : [];
        if (explain.length > 0) return String(explain[0] || '');
        const basis = Array.isArray(result?.analysis_basis) ? result.analysis_basis : [];
        if (basis.length > 0) return String(basis[0]?.description || basis[0]?.label || '');
        return '';
    }

    private nonFallRealtimeLabel(result: any): string {
        const ri = result?.runtime_inference || {};
        const shortClip = ri?.short_clip || {};
        const postureRaw = ri?.posture_label || result?.posture_label || '';
        if (shortClip?.confidence_level === 'insufficient' || (shortClip?.is_short_clip && ri?.posture_available === false)) {
            return '분석 준비 중';
        }
        if (postureRaw && postureRaw !== 'unknown') {
            const postureKr = this.POSTURE_LABEL_MAP[postureRaw] || postureRaw;
            return postureKr ? `비낙상·${postureKr}` : '비낙상';
        }
        if (ri?.posture_available === false) return '비낙상·서기';
        if (postureRaw === 'unknown') {
            const topCode = this.topNonFallPostureCode(result);
            if (topCode && topCode !== 'unknown') {
                const postureKr = this.POSTURE_LABEL_MAP[topCode] || topCode;
                return `비낙상·${postureKr}`;
            }
            return '비낙상·서기';
        }
        return '비낙상';
    }

    private createLogEntry(result: any, options: any = {}) {
        const ri = result?.runtime_inference || {};
        const displayProbs = this.displayPostureProbs(result);
        let postureRaw = options.posture || ri?.posture_label || result?.posture_label || '';
        if (postureRaw === 'unknown') {
            const topCode = this.topNonFallPostureCode(result);
            if (topCode && topCode !== 'unknown') postureRaw = topCode;
        }
        if (!postureRaw && result?.fall_detected === false) postureRaw = 'stand';
        if (postureRaw === 'unknown' && Object.keys(displayProbs).length === 0) postureRaw = result?.fall_detected === false ? 'stand' : '';
        const postureKr = postureRaw ? (this.POSTURE_LABEL_MAP[postureRaw] || '') : '';
        const behaviorTransition = options.behaviorTransition || result?.behavior_transition || {};
        const transitionDisplayRaw = behaviorTransition?.display_label || '';
        const transitionDisplay = behaviorTransition?.changed_from_previous === true ? transitionDisplayRaw : '';
        const transitionContext = behaviorTransition?.context_label || '';
        const postureDisplayLabel = transitionDisplayRaw || postureKr;
        const facial = this.facialStateAux(result);
        const facialLabel = facial ? this.facialStateLabel(result) : '';
        const facialPercent = facial ? this.facialStatePercent(result) : 0;
        const decState = options.decisionState || ri?.decision_state || result?.decision_state || 'safe';
        const nonFallLabel = this.nonFallRealtimeLabel(result);
        const logLabel = options.label || (result?.fall_detected ? '낙상' : nonFallLabel);
        const summary = result?.log_summary || {};
        const baseOneLine = options.oneLine || summary.line || '';
        const oneLine = transitionDisplay && baseOneLine && !baseOneLine.includes(transitionDisplay) ? `${transitionDisplay} · ${baseOneLine}` : (transitionDisplay || baseOneLine);
        const basisText = options.basis || summary.description || this.fallbackLogDescription(result);
        return {
            id: options.id,
            timestamp: options.timestamp || new Date().toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
            blobUrl: options.blobUrl || '',
            result: { ...result },
            score: result?.risk_score || 0,
            rawLevel: result?.raw_risk_level || result?.risk_level || 'low',
            level: result?.display_risk_level || result?.risk_level || 'low',
            displayRiskLabel: result?.display_risk_label || '',
            overlapContext: result?.overlap_context || null,
            label: logLabel,
            posture: postureRaw,
            postureLabel: postureDisplayLabel,
            currentPostureLabel: postureKr,
            facialLabel,
            facialPercent,
            transitionLabel: transitionDisplay,
            transitionContext,
            behaviorTransition,
            decisionState: decState,
            basis: transitionContext && basisText && !basisText.includes(transitionContext) ? `${transitionContext} · ${basisText}` : (transitionContext || basisText),
            runtimeKey: result?.runtime_key || '',
            elapsed: options.elapsed ?? this.realtimeLastElapsed,
            cumulativeScore: options.cumulativeScore ?? this.realtimeCumulativeScore,
            feedbackDone: Boolean(options.feedbackDone),
            oneLine,
            chunkLabel: options.chunkLabel || options.chunkWindow?.label || '',
            chunkWindow: options.chunkWindow || null,
        };
    }

    private syncUploadChunkLogs(result: any) {
        const logs = Array.isArray(result?.chunk_analysis?.logs) ? result.chunk_analysis.logs : [];
        this.uploadChunkSummary = result?.chunk_analysis?.summary || null;
        this.uploadLogEntries = logs.map((item: any) => this.createLogEntry(item?.result || {}, {
            id: item?.chunk_id,
            timestamp: '업로드 분할 분석',
            elapsed: Number(item?.elapsed_sec || 0),
            basis: item?.description || item?.facial_state?.label || '',
            oneLine: item?.one_line || '',
            behaviorTransition: item?.behavior_transition || item?.result?.behavior_transition || {},
            chunkLabel: item?.chunk_label || item?.window?.label || '',
            chunkWindow: item?.window || null,
        }));
    }

    public chunkTimelineTotal(entries: any[], fallbackTotal: number = 0): number {
        const maxEnd = (entries || []).reduce((acc: number, entry: any) => Math.max(acc, Number(entry?.chunkWindow?.end_sec ?? entry?.chunkWindow?.endSec ?? 0)), 0);
        return Math.max(maxEnd, Number(fallbackTotal || 0), 1);
    }
    public chunkBarStyle(entry: any, totalSec: number) {
        const total = Math.max(Number(totalSec || 1), 1);
        const start = Number(entry?.chunkWindow?.start_sec ?? entry?.chunkWindow?.startSec ?? 0);
        const end = Number(entry?.chunkWindow?.end_sec ?? entry?.chunkWindow?.endSec ?? start);
        const width = Math.max(end - start, 0.4);
        return { left: `${(start / total) * 100}%`, width: `${Math.max((width / total) * 100, 3)}%` };
    }
    public chunkBarLeft(entry: any, totalSec: number): string { return this.chunkBarStyle(entry, totalSec).left; }
    public chunkBarWidth(entry: any, totalSec: number): string { return this.chunkBarStyle(entry, totalSec).width; }

    public async ngOnInit() {
        await this.service.init(this);
        this.restorePrivacyViewMode();
        await this.loadPrototypeInfo();
        await this.loadContinuousTrainingStatus();
        this.startContinuousTrainingPolling();
        if (this.inputMode === 'webcam') await this.ensureWebcamReady();
        try {
            const saved = localStorage.getItem(LAST_ANALYSIS_STORAGE_KEY);
            if (saved && this.inputMode === 'upload') {
                const restored = JSON.parse(saved);
                this.applyAnalysisRoot(restored, false);
                this.analysisSavedName = restored?.saved_name || '';
                this.alertWorkflow = restored?.alert_workflow || null;
            }
        } catch (e) { }
        await this.service.render();
    }

    private restorePrivacyViewMode() {
        try {
            const saved = localStorage.getItem(PRIVACY_VIEW_STORAGE_KEY);
            this.privacyViewMode = saved === 'raw' ? 'raw' : 'skeleton';
        } catch (e) {
            this.privacyViewMode = 'skeleton';
        }
    }

    public isAdminUser(): boolean {
        return this.service?.auth?.check?.role?.('admin') === true;
    }

    public canShowRawVideo(): boolean {
        return this.privacyViewMode === 'raw';
    }

    public isSkeletonPrivacyMode(): boolean {
        return !this.canShowRawVideo();
    }

    public privacyViewLabel(): string {
        return this.canShowRawVideo() ? '원본+스켈레톤' : '스켈레톤 전용';
    }

    public async setPrivacyViewMode(mode: 'skeleton' | 'raw') {
        this.privacyViewMode = mode === 'raw' ? 'raw' : 'skeleton';
        try { localStorage.setItem(PRIVACY_VIEW_STORAGE_KEY, this.privacyViewMode); } catch (e) { }
        if (this.isSkeletonPrivacyMode()) this.clearRealtimeServerDetectionOverlay();
        await this.service.render();
    }

    public ngOnDestroy() {
        this.stopRealtimeAnalysis();
        this.stopWebcamStream();
        this.stopPoseLoop();
        this.stopDetectionReplay();
        this.stopFeedbackTimer();
        this.stopTrainingJobPolling();
        this.stopContinuousTrainingPolling();
        if (this.logFeedbackTimerHandle) { clearInterval(this.logFeedbackTimerHandle); this.logFeedbackTimerHandle = null; }
        if (this.realtimeOverlayFlashTimer) clearTimeout(this.realtimeOverlayFlashTimer);
        if (this.mpFpsTimer) clearInterval(this.mpFpsTimer);
        this.cleanupLogBlobUrls();
    }

    public async loadPrototypeInfo() {
        this.loadingInfo = true;
        await this.service.render();
        try {
            const { code, data }: any = await wiz.call('prototype_info');
            if (code === 200) {
                this.prototypeInfo = data;
                const optionKeys = this.analysisModelOptionsForView().map((item: any) => String(item?.key || ''));
                if (optionKeys.length > 0 && !optionKeys.includes(this.selectedModelType)) {
                    this.selectedModelType = String(this.prototypeInfo?.model_options?.default || optionKeys[0] || 'rf-dual');
                }
            }
            else this.errorMessage = data?.message || '프로토타입 정보를 불러오지 못했습니다.';
        } catch (e: any) {
            this.errorMessage = e?.message || '프로토타입 정보를 불러오지 못했습니다.';
        }
        this.continuousTrainingStatus = this.prototypeInfo?.continuous_training?.aihub82 || this.continuousTrainingStatus;
        this.continuousTrainingItems = this.normalizeContinuousTrainingItems(
            this.prototypeInfo?.continuous_training_items || this.prototypeInfo?.continuous_training
        );
        this.loadingInfo = false;
        await this.service.render();
    }

    public async saveAlertSettings(form: any) {
        try {
            const params: any = { action: 'save_alert_settings', ...form };
            const { code, data } = await wiz.call('prototype_info', params);
            if (code === 200 && data?.alert_settings) this.prototypeInfo.alert_settings = data.alert_settings;
        } catch (e) { }
        await this.service.render();
    }

    public async switchInputMode(mode: string) {
        if (this.inputMode === mode) return;
        this.inputMode = mode;
        this.errorMessage = '';
        this.clearAnalysisState();
        this.feedbackStatus = '';
        this.feedbackMessage = '';
        if (mode === 'webcam') await this.ensureWebcamReady();
        else this.stopRealtimeAnalysis();
        await this.service.render();
    }

    public async ensureWebcamReady() {
        if (this.webcamStream) {
            this.webcamReady = true;
            await this.service.render();
            setTimeout(() => {
                const videoEl = this.webcamVideoRef?.nativeElement;
                if (videoEl && this.webcamStream) {
                    videoEl.srcObject = this.webcamStream;
                    videoEl.play().catch(() => { });
                }
                if (!this.mpRunning) this.initMediaPipePose();
            }, 200);
            return;
        }
        this.webcamError = '';
        try {
            const constraints: any = { video: { facingMode: 'user', width: { ideal: 1280 }, height: { ideal: 720 }, frameRate: { ideal: 15, max: 30 } }, audio: false };
            this.webcamStream = await navigator.mediaDevices.getUserMedia(constraints);
            this.webcamReady = true;
            await this.service.render();
            setTimeout(() => {
                const videoEl = this.webcamVideoRef?.nativeElement;
                if (videoEl && this.webcamStream) {
                    videoEl.srcObject = this.webcamStream;
                    videoEl.play().catch(() => { });
                }
                this.initMediaPipePose();
            }, 200);
            return;
        } catch (e: any) {
            this.webcamError = '카메라 접근 실패: ' + (e.message || e);
            this.webcamReady = false;
        }
        await this.service.render();
    }

    public stopWebcamStream() {
        if (this.webcamStream) {
            this.webcamStream.getTracks().forEach(t => t.stop());
            this.webcamStream = null;
        }
        this.webcamReady = false;
    }

    public async initMediaPipePose() {
        if (this.poseLandmarker || this.mpInitializing) return;
        this.mpInitializing = true;
        await this.service.render();
        try {
            const vision = await FilesetResolver.forVisionTasks('https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.34/wasm');
            this.poseLandmarker = await PoseLandmarker.createFromOptions(vision, {
                baseOptions: { modelAssetPath: 'https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task', delegate: 'GPU' },
                runningMode: 'VIDEO',
                numPoses: MP_MAX_POSES,
            });
            this.mpReady = true;
            this.startPoseLoop();
        } catch (e: any) {
            console.warn('MediaPipe init failed:', e);
            this.mpReady = false;
        }
        this.mpInitializing = false;
        await this.service.render();
    }

    public startPoseLoop() {
        if (this.mpRunning || !this.poseLandmarker) return;
        this.mpRunning = true;
        this.mpFrameCount = 0;
        this.mpLastFrameTime = 0;
        this.resetMediaPipeTracks();
        this.initKalmanFilters();
        this.mpFpsTimer = setInterval(() => { this.mpFps = this.mpFrameCount; this.mpFrameCount = 0; }, 1000);
        const canvasEl = this._mpPoseCanvasEl?.nativeElement || document.querySelector('[data-mp-pose-canvas]') as HTMLCanvasElement;
        if (canvasEl && !this.mpResizeObserver) {
            this.mpResizeObserver = new ResizeObserver((entries: any[]) => {
                for (const entry of entries) {
                    const { width, height } = entry.contentRect;
                    if (width > 0 && height > 0) { canvasEl.width = width; canvasEl.height = height; }
                }
            });
            this.mpResizeObserver.observe(canvasEl.parentElement || canvasEl);
        }
        const loop = () => {
            if (!this.mpRunning) return;
            this.mpRafId = requestAnimationFrame(loop);
            const now = performance.now();
            if (now - this.mpLastFrameTime < MP_FRAME_INTERVAL_MS) return;
            this.mpLastFrameTime = now;
            this.drawMpPose();
        };
        loop();
    }

    public stopPoseLoop() {
        this.mpRunning = false;
        if (this.mpRafId) { cancelAnimationFrame(this.mpRafId); this.mpRafId = 0; }
        if (this.mpFpsTimer) { clearInterval(this.mpFpsTimer); this.mpFpsTimer = null; }
        if (this.mpResizeObserver) { this.mpResizeObserver.disconnect(); this.mpResizeObserver = null; }
        this.kalmanFilters = [];
        this.mpPoseKalmanFilters = [];
        this.resetMediaPipeTracks();
        this.mpDetectedPoseCount = 0;
    }

    private createLandmarkFilters() {
        const filters: { x: Kalman1D; y: Kalman1D; missCount: number }[] = [];
        for (let i = 0; i < 33; i++) filters.push({ x: new Kalman1D(), y: new Kalman1D(), missCount: 0 });
        return filters;
    }

    private initKalmanFilters(maxPoses: number = MP_MAX_POSES) {
        this.mpPoseKalmanFilters = [];
        for (let i = 0; i < maxPoses; i++) this.mpPoseKalmanFilters.push(this.createLandmarkFilters());
        this.kalmanFilters = this.mpPoseKalmanFilters[0] || [];
    }

    private getPoseKalmanFilters(poseIndex: number) {
        while (this.mpPoseKalmanFilters.length <= poseIndex) this.mpPoseKalmanFilters.push(this.createLandmarkFilters());
        this.kalmanFilters = this.mpPoseKalmanFilters[0] || [];
        return this.mpPoseKalmanFilters[poseIndex];
    }

    private resetMediaPipeTracks() {
        this.mpPoseTracks = [];
        this.mpPoseTrackFilters = {};
        this.mpNextPoseTrackId = 1;
    }

    private getPoseKalmanFiltersForTrack(trackId: number): MpLandmarkFilters {
        const key = Math.max(1, Math.round(Number(trackId || 1)));
        if (!this.mpPoseTrackFilters[key]) this.mpPoseTrackFilters[key] = this.createLandmarkFilters();
        this.kalmanFilters = this.mpPoseTrackFilters[1] || this.mpPoseTrackFilters[key] || [];
        return this.mpPoseTrackFilters[key];
    }

    private mediaPipePoseCenter(landmarks: any[]): { x: number; y: number; visible: number } | null {
        let sx = 0, sy = 0, n = 0;
        for (const lm of landmarks || []) {
            if ((lm?.visibility ?? 0) < this.KF_VIS_THRESHOLD) continue;
            const p = this.normalizeMediaPipePoint(lm);
            sx += p.x;
            sy += p.y;
            n++;
        }
        if (n <= 0) return null;
        return { x: sx / n, y: sy / n, visible: n };
    }

    private assignMediaPipeTracks(candidates: { landmarks: any[]; sourceIndex: number; center: { x: number; y: number; visible: number } }[], nowMs: number) {
        const usedTrackIds = new Set<number>();
        this.mpPoseTracks = this.mpPoseTracks.filter(track => {
            const alive = nowMs - Number(track.lastSeenMs || 0) <= 1800 && Number(track.missed || 0) <= 25;
            if (!alive) delete this.mpPoseTrackFilters[track.id];
            return alive;
        });
        const assigned: { landmarks: any[]; sourceIndex: number; trackId: number }[] = [];
        for (const candidate of candidates) {
            let best: MpPoseTrack | null = null;
            let bestScore = Number.POSITIVE_INFINITY;
            for (const track of this.mpPoseTracks) {
                if (usedTrackIds.has(track.id)) continue;
                const stalePenalty = Math.min(0.12, Math.max(0, nowMs - Number(track.lastSeenMs || nowMs)) / 1000 * 0.04);
                const distance = Math.hypot(candidate.center.x - track.centerX, candidate.center.y - track.centerY) + stalePenalty;
                if (distance < bestScore) {
                    bestScore = distance;
                    best = track;
                }
            }
            const threshold = candidate.center.visible >= 12 ? 0.22 : 0.16;
            if (!best || bestScore > threshold) {
                best = { id: this.mpNextPoseTrackId++, centerX: candidate.center.x, centerY: candidate.center.y, lastSeenMs: nowMs, missed: 0 };
                this.mpPoseTracks.push(best);
            } else {
                best.centerX = candidate.center.x;
                best.centerY = candidate.center.y;
                best.lastSeenMs = nowMs;
                best.missed = 0;
            }
            usedTrackIds.add(best.id);
            assigned.push({ landmarks: candidate.landmarks, sourceIndex: candidate.sourceIndex, trackId: best.id });
        }
        for (const track of this.mpPoseTracks) {
            if (!usedTrackIds.has(track.id)) track.missed = Number(track.missed || 0) + 1;
        }
        return assigned;
    }

    private getMediaPipeInputSource(videoEl: HTMLVideoElement): any {
        const sourceW = Math.max(1, Math.round(videoEl.videoWidth || videoEl.clientWidth || 0));
        const sourceH = Math.max(1, Math.round(videoEl.videoHeight || videoEl.clientHeight || 0));
        if (!sourceW || !sourceH) return videoEl;
        const side = Math.max(sourceW, sourceH);
        const offsetX = Math.floor((side - sourceW) / 2);
        const offsetY = Math.floor((side - sourceH) / 2);
        if (!this.mpInputCanvas) {
            this.mpInputCanvas = document.createElement('canvas');
            this.mpInputCtx = this.mpInputCanvas.getContext('2d');
        }
        if (!this.mpInputCanvas || !this.mpInputCtx) return videoEl;
        if (this.mpInputCanvas.width !== side || this.mpInputCanvas.height !== side) {
            this.mpInputCanvas.width = side;
            this.mpInputCanvas.height = side;
        }
        try {
            this.mpInputCtx.fillStyle = '#000';
            this.mpInputCtx.fillRect(0, 0, side, side);
            this.mpInputCtx.drawImage(videoEl, offsetX, offsetY, sourceW, sourceH);
            this.mpInputTransform = { side, offsetX, offsetY, drawW: sourceW, drawH: sourceH };
            return this.mpInputCanvas;
        } catch (e) {
            this.mpInputTransform = null;
            return videoEl;
        }
    }

    private normalizeMediaPipePoint(lm: any): { x: number; y: number } {
        const tr = this.mpInputTransform;
        if (!tr) return { x: Number(lm.x || 0), y: Number(lm.y || 0) };
        const x = ((Number(lm.x || 0) * tr.side) - tr.offsetX) / Math.max(1, tr.drawW);
        const y = ((Number(lm.y || 0) * tr.side) - tr.offsetY) / Math.max(1, tr.drawH);
        return { x: Math.max(0, Math.min(1, x)), y: Math.max(0, Math.min(1, y)) };
    }

    private mediaPipeLandmarkVisible(lm: any, index: number): boolean {
        if (MP_HAND_DETAIL_LANDMARKS.has(index)) return false;
        const visibility = Number(lm?.visibility ?? 0);
        const presenceRaw = lm?.presence;
        const presence = presenceRaw == null ? 1 : Number(presenceRaw || 0);
        const threshold = MP_WRIST_LANDMARKS.has(index) ? this.KF_HAND_VIS_THRESHOLD : this.KF_VIS_THRESHOLD;
        return visibility >= threshold && presence >= threshold;
    }

    private cocoKeypointVisible(kp: any, index: number): boolean {
        if (!kp) return false;
        const conf = Number(kp[2] || 0);
        return conf >= (COCO_HAND_KEYPOINTS.has(index) ? this.KF_HAND_VIS_THRESHOLD : 0.30);
    }

    private drawMpPose() {
        if (this.mpProcessing || !this.poseLandmarker) return;
        const videoEl = this.webcamVideoRef?.nativeElement;
        if (!videoEl || videoEl.readyState < 2) return;
        if (document.hidden) return;
        const canvasEl = this._mpPoseCanvasEl?.nativeElement || document.querySelector('[data-mp-pose-canvas]') as HTMLCanvasElement;
        if (!canvasEl) return;
        const ctx = canvasEl.getContext('2d');
        if (!ctx) return;
        const canvasRect = canvasEl.getBoundingClientRect();
        const targetW = Math.max(1, Math.round(canvasRect.width || videoEl.clientWidth || videoEl.videoWidth || 1));
        const targetH = Math.max(1, Math.round(canvasRect.height || videoEl.clientHeight || videoEl.videoHeight || 1));
        if (canvasEl.width !== targetW || canvasEl.height !== targetH) {
            canvasEl.width = targetW;
            canvasEl.height = targetH;
        }
        this.mpProcessing = true;
        try {
            const mpInput = this.getMediaPipeInputSource(videoEl);
            const detectTs = performance.now();
            const result = this.poseLandmarker.detectForVideo(mpInput, detectTs);
            ctx.clearRect(0, 0, canvasEl.width, canvasEl.height);
            if (result.landmarks && result.landmarks.length > 0) {
                const poses = result.landmarks.slice(0, MP_MAX_POSES);
                const displayRect = this.getVideoContentRect(videoEl);
                const offX = displayRect.x; const offY = displayRect.y;
                const w = displayRect.w; const h = displayRect.h;
                if (this.mpPoseKalmanFilters.length === 0) this.initKalmanFilters(MP_MAX_POSES);
                const poseCandidates = poses
                    .map((landmarks: any[], sourceIndex: number) => ({ landmarks: landmarks || [], sourceIndex, center: this.mediaPipePoseCenter(landmarks || []) }))
                    .filter((item: any) => !!item.center);
                const trackedPoses = this.assignMediaPipeTracks(poseCandidates as any, detectTs);
                this.mpDetectedPoseCount = trackedPoses.length;
                for (let poseIndex = 0; poseIndex < trackedPoses.length; poseIndex++) {
                    const trackedPose = trackedPoses[poseIndex];
                    const landmarks = trackedPose.landmarks || [];
                    const filters = this.getPoseKalmanFiltersForTrack(trackedPose.trackId);
                    const personColor = MP_PERSON_COLORS[(trackedPose.trackId - 1) % MP_PERSON_COLORS.length];
                    const pts: { x: number; y: number; predicted: boolean; valid: boolean }[] = [];
                    for (let k = 0; k < landmarks.length; k++) {
                        const lm = landmarks[k];
                        const vis = this.mediaPipeLandmarkVisible(lm, k);
                        const kf = filters[k];
                        const p = this.normalizeMediaPipePoint(lm);
                        if (!kf) { pts.push({ x: p.x, y: p.y, predicted: false, valid: vis }); continue; }
                        kf.x.predict(); kf.y.predict();
                        if (vis) {
                            const fx = kf.x.update(p.x); const fy = kf.y.update(p.y); kf.missCount = 0; pts.push({ x: fx, y: fy, predicted: false, valid: true });
                        } else {
                            kf.missCount++;
                            if (!MP_WRIST_LANDMARKS.has(k) && !MP_HAND_DETAIL_LANDMARKS.has(k) && kf.x.initialized && kf.missCount < this.KF_MAX_MISS) pts.push({ x: kf.x.position, y: kf.y.position, predicted: true, valid: true });
                            else pts.push({ x: 0, y: 0, predicted: false, valid: false });
                        }
                    }
                    for (const [i, j] of MP_POSE_CONNECTIONS) {
                        if (MP_HAND_DETAIL_LANDMARKS.has(i) || MP_HAND_DETAIL_LANDMARKS.has(j)) continue;
                        const a = pts[i], b = pts[j];
                        if (!a?.valid || !b?.valid) continue;
                        const pred = a.predicted || b.predicted;
                        ctx.beginPath(); ctx.moveTo(offX + a.x * w, offY + a.y * h); ctx.lineTo(offX + b.x * w, offY + b.y * h);
                        ctx.strokeStyle = this.colorWithAlpha(pred ? (MP_LANDMARK_COLORS[i] || personColor) : personColor, pred ? 0.28 : 0.86);
                        ctx.lineWidth = pred ? 1 : (trackedPose.trackId === 1 ? 2 : 1.5); ctx.setLineDash(pred ? [4, 4] : []); ctx.stroke();
                    }
                    ctx.setLineDash([]);
                    let minX = 1, minY = 1, hasPoint = false;
                    for (let k = 0; k < pts.length; k++) {
                        if (MP_HAND_DETAIL_LANDMARKS.has(k)) continue;
                        const pt = pts[k];
                        if (!pt.valid) continue;
                        minX = Math.min(minX, pt.x);
                        minY = Math.min(minY, pt.y);
                        hasPoint = true;
                        ctx.beginPath(); ctx.arc(offX + pt.x * w, offY + pt.y * h, pt.predicted ? 2 : 3, 0, 2 * Math.PI);
                        if (pt.predicted) { ctx.strokeStyle = this.colorWithAlpha(personColor, 0.45); ctx.lineWidth = 1; ctx.stroke(); }
                        else { ctx.fillStyle = personColor; ctx.fill(); }
                    }
                    if (hasPoint) {
                        const labelX = Math.max(offX + 2, Math.min(offX + minX * w, offX + w - 24));
                        const labelY = Math.max(offY + 14, Math.min(offY + minY * h - 4, offY + h - 4));
                        ctx.font = '11px sans-serif';
                        ctx.fillStyle = this.colorWithAlpha(personColor, 0.88);
                        ctx.fillText(`P${trackedPose.trackId}`, labelX, labelY);
                    }
                }
            } else if (this.kalmanFilters.length > 0) {
                this.mpDetectedPoseCount = 0;
                for (const filters of this.mpPoseKalmanFilters) {
                    for (const kf of filters) { kf.x.predict(); kf.y.predict(); kf.missCount++; }
                }
                for (const filters of Object.values(this.mpPoseTrackFilters)) {
                    for (const kf of filters) { kf.x.predict(); kf.y.predict(); kf.missCount++; }
                }
            }
            this.mpFrameCount++;
        } catch (e) { }
        this.mpProcessing = false;
    }

    private colorWithAlpha(hex: string, alpha: number): string {
        const r = parseInt(hex.slice(1, 3), 16); const g = parseInt(hex.slice(3, 5), 16); const b = parseInt(hex.slice(5, 7), 16);
        return `rgba(${r},${g},${b},${alpha})`;
    }

    public async startRealtimeAnalysis() {
        if (this.realtimeStarting || this.realtimeActive || !this.webcamStream) return;
        this.realtimeStarting = true;
        this.realtimePerfStats = { avgRtt: 0, avgServer: 0, currentInterval: 0, discarded: 0, queued: 0, retrying: 0, failed: 0 };
        this.errorMessage = '';
        await this.service.render();
        try {
            await this.warmupRealtimeModels();
            if (!this.webcamStream) return;
            this.realtimeActive = true;
            this.realtimeSessionId = `rt-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
            this.realtimeSessionStartedAt = Date.now();
            this.realtimeChunkCount = 0;
            this.realtimeScoreHistory = [];
            this.realtimeCumulativeScore = 0;
            this.realtimeLogEntries = [];
            this.realtimeLastElapsed = 0;
            this.postureTimeline = []; this.postureTransitions = []; this.currentPosture = ''; this.currentPostureLabel = ''; this.postureTransitionText = '';
            this.realtimeOverlayScore = 0; this.realtimeOverlayLevel = 'low'; this.realtimeOverlayLabel = '대기'; this.realtimeOverlayBasis = ''; this.lastNonEmptyOverlayBasis = '';
            this.realtimeRoundTripHistory = []; this.realtimeServerTimeHistory = [];
            this.dispatchQueue = []; this.dispatchQueueSize = 0; this.dispatchWorkerRunning = false; this.nextSlotId = 0; this.recorderSlots = []; this.realtimeWindowKeys.clear(); this.errorMessage = '';
            await this.service.render();
            const chunkCfg = this.getChunkConfig();
            if (chunkCfg.bootstrapDurations.length > 0) for (const durationSec of chunkCfg.bootstrapDurations) this.spawnRecorderSlot(durationSec);
            else this.spawnRecorderSlot(chunkCfg.chunkSec);
            this.recorderSpawnTimer = setInterval(() => { if (!this.realtimeActive) return; this.spawnRecorderSlot(chunkCfg.chunkSec); }, chunkCfg.spawnMs);
        } finally {
            this.realtimeStarting = false;
            await this.service.render();
        }
    }

    private spawnRecorderSlot(durationSec?: number) {
        if (!this.realtimeActive || !this.webcamStream) return;
        const chunkCfg = this.getChunkConfig();
        if (this.recorderSlots.length >= chunkCfg.maxSlots) return;
        const actualDurationSec = Number(durationSec || chunkCfg.chunkSec || 5);
        try {
            const mimeType = MediaRecorder.isTypeSupported('video/webm;codecs=vp8') ? 'video/webm;codecs=vp8' : 'video/webm';
            const recorder = new MediaRecorder(this.webcamStream!, { mimeType });
            const chunks: Blob[] = [];
            const slotId = this.nextSlotId++;
            const slot = { recorder, chunks, timer: null as any, slotId, durationSec: actualDurationSec, startedAtMs: Date.now() };
            recorder.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data); };
            recorder.onstop = () => {
                const idx = this.recorderSlots.indexOf(slot);
                if (idx >= 0) this.recorderSlots.splice(idx, 1);
                if (!this.realtimeActive) return;
                const chunkId = this.realtimeChunkCount++;
                if (chunks.length > 0) {
                    const blob = new Blob(chunks, { type: 'video/webm' });
                    this.enqueueChunk(blob, chunkId, actualDurationSec, this.buildRealtimeChunkWindow(slot.startedAtMs, actualDurationSec));
                }
            };
            recorder.start(500);
            slot.timer = setTimeout(() => { if (recorder.state === 'recording') { try { recorder.stop(); } catch (e) { } } }, actualDurationSec * 1000);
            this.recorderSlots.push(slot);
        } catch (e: any) {
            this.errorMessage = '녹화 실패: ' + (e.message || e);
            this.realtimeActive = false;
            this.service.render();
        }
    }

    private realtimeWindowKey(chunkWindow: any): string {
        const start = Math.round(Number(chunkWindow?.start_sec ?? chunkWindow?.startSec ?? 0));
        const end = Math.round(Number(chunkWindow?.end_sec ?? chunkWindow?.endSec ?? start));
        return `${start}-${end}`;
    }

    private enqueueChunk(blob: Blob, chunkId: number, durationSec: number, chunkWindow: any) {
        const key = this.realtimeWindowKey(chunkWindow);
        if (this.realtimeWindowKeys.has(key)) {
            this.realtimePerfStats.discarded = (this.realtimePerfStats.discarded || 0) + 1;
            return;
        }
        this.realtimeWindowKeys.add(key);
        this.dispatchQueue.push({ blob, chunkId, durationSec, chunkWindow, attempt: 0 });
        this.dispatchQueueSize = this.dispatchQueue.length;
        this.realtimePerfStats.queued = this.dispatchQueueSize;
        if (!this.dispatchWorkerRunning) this.runDispatchWorker();
    }

    private async runDispatchWorker() {
        if (this.dispatchWorkerRunning) return;
        this.dispatchWorkerRunning = true;
        while (this.dispatchQueue.length > 0) {
            const item = this.dispatchQueue.shift()!;
            this.dispatchQueueSize = this.dispatchQueue.length;
            this.realtimePerfStats.queued = this.dispatchQueueSize;
            const ok = await this.dispatchRealtimeChunk(item.blob, item.chunkId, item.durationSec, item.chunkWindow);
            if (!ok && this.realtimeActive && Number(item.attempt || 0) < 2) {
                item.attempt = Number(item.attempt || 0) + 1;
                this.realtimePerfStats.retrying = item.attempt;
                this.dispatchQueue.push(item);
                this.dispatchQueueSize = this.dispatchQueue.length;
                this.realtimePerfStats.queued = this.dispatchQueueSize;
                await new Promise(resolve => setTimeout(resolve, Math.min(3000, 600 * item.attempt)));
            }
        }
        this.dispatchWorkerRunning = false;
        this.dispatchQueueSize = this.dispatchQueue.length;
        this.realtimePerfStats.queued = this.dispatchQueueSize;
    }

    public async stopRealtimeAnalysis() {
        this.realtimeStarting = false; this.realtimeActive = false; this.realtimeSessionId = ''; this.realtimeSessionStartedAt = 0;
        if (this.recorderSpawnTimer) { clearInterval(this.recorderSpawnTimer); this.recorderSpawnTimer = null; }
        for (const slot of this.recorderSlots) {
            if (slot.timer) clearTimeout(slot.timer);
            if (slot.recorder.state === 'recording') { try { slot.recorder.stop(); } catch (e) { } }
        }
        this.recorderSlots = []; this.dispatchQueue = []; this.dispatchQueueSize = 0; this.realtimeWindowKeys.clear();
        await this.service.render();
    }

    private async dispatchRealtimeChunk(blob: Blob, chunkId: number, durationSec: number, chunkWindow: any): Promise<boolean> {
        this.realtimeDispatching = true;
        const startTime = performance.now();
        try {
            const fd = new FormData();
            fd.append('video', blob, `chunk_${chunkId}.webm`);
            fd.append('metadata', JSON.stringify({ analysis_profile: this.analysisProfile, input_source: 'webcam-live', model_type: this.selectedModelType, duration: durationSec, chunk_id: chunkId, realtime_session_id: this.realtimeSessionId, chunk_window: chunkWindow }));
            const res = await fetch(`/wiz/api/page.dashboard/analyze_upload`, { method: 'POST', body: fd });
            const json = await this.readJsonResponse(res);
            if (json.code === 200 && json.data) {
                const result = json.data;
                this.applyAnalysisRoot(result, true);
                this.analysisSavedName = result.saved_name || '';
                this.realtimeLastElapsed = result.server_timing?.total_server_sec || 0;
                const score = result.risk_score || 0;
                this.realtimeScoreHistory.push(score);
                if (this.realtimeScoreHistory.length > 3) this.realtimeScoreHistory.shift();
                const weights = [1, 2, 3];
                const n = this.realtimeScoreHistory.length;
                let wSum = 0, wTotal = 0;
                for (let i = 0; i < n; i++) { const w = weights[weights.length - n + i] || 1; wSum += this.realtimeScoreHistory[i] * w; wTotal += w; }
                this.realtimeCumulativeScore = wSum / wTotal;
                this.updateRealtimeOverlay();
                this.drawRealtimeServerDetectionOverlay(result);
                this.pushRealtimeLog(blob, chunkId, chunkWindow);
                const rtt = performance.now() - startTime;
                this.realtimeRoundTripHistory.push(rtt);
                if (this.realtimeRoundTripHistory.length > 10) this.realtimeRoundTripHistory.shift();
                const st = (result.server_timing?.total_server_sec || 0) * 1000;
                this.realtimeServerTimeHistory.push(st);
                if (this.realtimeServerTimeHistory.length > 10) this.realtimeServerTimeHistory.shift();
                this.realtimePerfStats.avgRtt = Math.round(this.realtimeRoundTripHistory.reduce((a: number, b: number) => a + b, 0) / this.realtimeRoundTripHistory.length);
                this.realtimePerfStats.avgServer = Math.round(this.realtimeServerTimeHistory.reduce((a: number, b: number) => a + b, 0) / this.realtimeServerTimeHistory.length);
                this.realtimePerfStats.currentInterval = this.getChunkConfig().spawnMs;
                this.realtimeDispatching = false;
                await this.service.render();
                return true;
            }
        } catch (e: any) {
            if (e instanceof SyntaxError) console.error('Dispatch error (JSON parse failed — server may have returned NaN):', e.message);
            else console.error('Dispatch error:', e);
        }
        this.realtimePerfStats.failed = (this.realtimePerfStats.failed || 0) + 1;
        this.realtimeDispatching = false;
        await this.service.render();
        return false;
    }

    private updateRealtimeOverlay() {
        if (!this.analysisResult) return;
        const displayScore = this.isPersonAnalysisSelected() ? Number(this.analysisResult?.risk_score || 0) : this.realtimeCumulativeScore;
        this.realtimeOverlayScore = Math.round(displayScore * 100);
        const level = this.analysisResult?.risk_level || 'low';
        this.realtimeOverlayLevel = level;
        this.realtimeOverlayLabel = this.realtimePendingConfirmation ? '확인 대기' : this.analysisResult?.fall_detected ? '낙상 감지' : this.nonFallRealtimeLabel(this.analysisResult);
        const basis: string[] = [];
        const ri = this.analysisResult?.runtime_inference;
        const runtimeKey = this.analysisResult?.runtime_key || '';
        const isXgb = runtimeKey === 'person-feature-runtime';
        const fallDetected = this.analysisResult?.fall_detected;
        if (fallDetected) basis.push('⚠ 낙상');
        else if (ri?.fall_score != null || ri?.fall_probability != null) basis.push('비낙상');
        const fallProb = ri?.fall_probability;
        if (fallProb != null) basis.push(`확률 ${(fallProb * 100).toFixed(0)}%`);
        else { const rawProb = ri?.raw_fall_probability; if (rawProb != null) basis.push(`Raw ${(rawProb * 100).toFixed(0)}%`); }
        if (isXgb) {
            const tf = ri?.top_features || {};
            const mds = tf['max_down_speed']; const cdy = tf['center_dy']; const fp = tf['floor_proximity']; const hr = tf['height_ratio'];
            if (mds != null) basis.push(`하강속도 ${Number(mds).toFixed(2)}`);
            if (cdy != null && Number(cdy) > 0.01) basis.push(`수직이동 ${Number(cdy).toFixed(2)}`);
            if (fp != null && Number(fp) > 0.5) basis.push(`바닥근접 ${(Number(fp) * 100).toFixed(0)}%`);
            if (hr != null && Number(hr) < -0.03) basis.push(`높이↓ ${(Number(hr) * 100).toFixed(0)}%`);
        } else {
            const feats = ri?.features || {};
            const dym = feats['delta_y_max']; const fhr = feats['final_height_ratio'];
            if (dym != null) basis.push(`△Y ${Number(dym).toFixed(1)}px`);
            if (fhr != null) basis.push(`자세 ${(Number(fhr) * 100).toFixed(0)}%`);
        }
        const nFrames = ri?.short_clip?.n_det_frames || ri?.windows;
        if (nFrames != null) basis.push(`${nFrames}${isXgb ? 'w' : 'f'} 검출`);
        const postureLabel = ri?.posture_label; const decisionState = ri?.decision_state;
        if (postureLabel) {
            if (postureLabel === 'unknown') {
                const topCode = this.topNonFallPostureCode(this.analysisResult);
                const probs = this.displayPostureProbs(this.analysisResult);
                const topPct = Math.round(Number(probs?.[topCode] || 0) * 100);
                basis.push(topCode && topCode !== 'unknown' ? `추정(${this.POSTURE_LABEL_MAP[topCode] || topCode} ${topPct}%)` : '추정(서기)');
            } else {
                basis.push(this.POSTURE_LABEL_MAP[postureLabel] || postureLabel);
            }
        }
        if (decisionState && decisionState !== 'safe') { const dsMeta = this.DECISION_STATE_META[decisionState]; if (dsMeta) basis.push(dsMeta.label); }
        const llmReview = this.analysisResult?.llm_behavior_review || ri?.llm_behavior_review || this.analysisResult?.llm_interpretation;
        if (llmReview?.status === 'generated') basis.push('LLM검토');
        else if (llmReview?.status === 'cached') basis.push('LLM캐시');
        const facial = ri?.facial_state || this.analysisResult?.facial_state;
        if (facial?.applied) basis.push(`표정보조 +${Math.round(Number(facial.support_score || 0) * 100)}%p`);
        else if (facial?.available && Number(facial?.support_score || 0) > 0) basis.push('표정보조 검토');
        else if (facial?.reason === 'face_not_detected' && fallDetected) basis.push('얼굴미검출');
        if (isXgb) { if (ri?.motion_gate && !ri.motion_gate.passed) basis.push('Gate억제'); }
        else { if (ri?.motion_guard?.applied) basis.push('Guard'); }
        if (ri?.short_clip?.is_short_clip) basis.push('Short-clip');
        if (this.realtimeLastElapsed > 0) basis.push(`${this.realtimeLastElapsed.toFixed(1)}초`);
        const newBasis = basis.slice(0, 7).join(' · ') || '';
        if (newBasis) { this.realtimeOverlayBasis = newBasis; this.lastNonEmptyOverlayBasis = newBasis; }
        else if (this.lastNonEmptyOverlayBasis) this.realtimeOverlayBasis = this.lastNonEmptyOverlayBasis;
        this.realtimeOverlayRuntime = '';
        if (this.analysisResult?.fall_detected && !this.analysisResult?._dedup_suppressed) {
            this.realtimeOverlayFlash = true;
            if (this.realtimeOverlayFlashTimer) clearTimeout(this.realtimeOverlayFlashTimer);
            this.realtimeOverlayFlashTimer = setTimeout(() => { this.realtimeOverlayFlash = false; }, 2000);
        }
    }

    private isUploadVideoFile(file: File): boolean {
        const name = String(file?.name || '').toLowerCase();
        return Boolean(file?.type?.startsWith('video/')) || /\.(mp4|mov|avi|mkv|webm|m4v)$/.test(name);
    }

    private revokeSelectedVideoUrl() {
        if (this.selectedVideoUrl) {
            try { URL.revokeObjectURL(this.selectedVideoUrl); } catch (e) { }
        }
        this.selectedVideoUrl = '';
    }

    private fileIdentity(file: File): string {
        const anyFile: any = file as any;
        return [
            anyFile.webkitRelativePath || file.name || '',
            file.size || 0,
            file.lastModified || 0,
        ].join('|');
    }

    private dedupeUploadFiles(files: File[]): File[] {
        const seen = new Set<string>();
        const out: File[] = [];
        for (const file of files || []) {
            if (!file) continue;
            const key = this.fileIdentity(file);
            if (seen.has(key)) continue;
            seen.add(key);
            out.push(file);
        }
        return out;
    }

    private uploadFolderKey(file: File): string {
        const rel = String((file as any)?.webkitRelativePath || '');
        if (!rel || !rel.includes('/')) return '';
        return rel.split('/').slice(0, -1).join('/');
    }

    private uploadDisplayName(file: File): string {
        const rel = String((file as any)?.webkitRelativePath || '');
        return rel || file.name || '파일';
    }

    private async syncSelectedUploadPreview(files: File[]) {
        const cleanFiles = this.dedupeUploadFiles(files);
        this.revokeSelectedVideoUrl();
        this.selectedFiles = cleanFiles;
        const firstVideo = cleanFiles.find(file => this.isUploadVideoFile(file)) || null;
        this.selectedFile = firstVideo;
        this.selectedVideoUrl = firstVideo ? URL.createObjectURL(firstVideo) : '';
    }

    private async setSelectedUploadFiles(files: File[]) {
        const cleanFiles = (files || []).filter(Boolean);
        if (cleanFiles.length === 0) return;
        await this.syncSelectedUploadPreview(cleanFiles);
        this.clearAnalysisState();
        this.feedbackStatus = '';
        this.feedbackMessage = '';
        this.trainingUploadMessage = '';
        this.trainingUploadDone = 0;
        this.trainingUploadTotal = 0;
        this.errorMessage = '';
        this.uploadLogEntries = [];
        this.uploadChunkSummary = null;
        await this.service.render();
    }

    public async onFileSelected(event: any) {
        const files = Array.from(event?.target?.files || []) as File[];
        await this.setSelectedUploadFiles(files);
        if (event?.target) event.target.value = '';
    }
    public async onFolderSelected(event: any) {
        const files = Array.from(event?.target?.files || []) as File[];
        await this.setSelectedUploadFiles(files);
        if (event?.target) event.target.value = '';
    }
    public async onDrop(event: DragEvent) {
        event.preventDefault();
        this.dragover = false;
        const files = Array.from(event.dataTransfer?.files || []) as File[];
        await this.setSelectedUploadFiles(files);
    }
    public onDragOver(event: DragEvent) { event.preventDefault(); this.dragover = true; }
    public onDragLeave(event: DragEvent) { event.preventDefault(); this.dragover = false; }

    public async setUploadWorkflowMode(mode: 'analyze' | 'train') {
        this.uploadWorkflowMode = mode === 'train' ? 'train' : 'analyze';
        if (this.uploadWorkflowMode === 'train') await this.loadContinuousTrainingStatus();
        await this.service.render();
    }

    public selectedUploadCount(): number {
        return this.selectedFiles.length;
    }

    public selectedUploadSummary(): string {
        const count = this.selectedUploadCount();
        if (count === 0) return '선택된 파일 없음';
        const firstNames = this.selectedFiles.slice(0, 3).map(file => file.name).join(', ');
        const extra = count > 3 ? ` 외 ${count - 3}개` : '';
        return `${count}개 선택 · ${firstNames}${extra}`;
    }

    public selectedUploadItems(): any[] {
        return this.selectedFiles.slice(0, 12).map((file, index) => ({
            index,
            name: this.uploadDisplayName(file),
            folder: this.uploadFolderKey(file),
            size_mb: file.size ? (file.size / (1024 * 1024)).toFixed(1) : '0.0',
            type: this.isUploadVideoFile(file) ? '영상' : (this._isArchiveName(file.name) ? '압축' : '파일'),
        }));
    }

    public selectedUploadHiddenCount(): number {
        return Math.max(0, this.selectedFiles.length - 12);
    }

    public selectedUploadFolderGroups(): any[] {
        const groups: Record<string, number> = {};
        for (const file of this.selectedFiles) {
            const folder = this.uploadFolderKey(file);
            if (!folder) continue;
            groups[folder] = (groups[folder] || 0) + 1;
        }
        return Object.keys(groups).sort().map(key => ({ key, label: key.split('/')[0] || key, count: groups[key] }));
    }

    private _isArchiveName(name: string): boolean {
        return /\.(zip|tar|tar\.gz|tgz)$/i.test(String(name || ''));
    }

    public async removeSelectedUploadFile(index: number, event?: Event) {
        if (event) {
            event.preventDefault();
            event.stopPropagation();
        }
        if (index < 0 || index >= this.selectedFiles.length) return;
        const next = this.selectedFiles.filter((_, i) => i !== index);
        await this.syncSelectedUploadPreview(next);
        if (next.length === 0) this.clearSelectedFile();
        else {
            this.clearAnalysisState();
            this.uploadLogEntries = [];
            this.uploadChunkSummary = null;
            this.trainingUploadMessage = '';
            this.errorMessage = '';
        }
        await this.service.render();
    }

    public async removeSelectedUploadFolder(folder: string, event?: Event) {
        if (event) {
            event.preventDefault();
            event.stopPropagation();
        }
        const key = String(folder || '');
        if (!key) return;
        const next = this.selectedFiles.filter(file => this.uploadFolderKey(file) !== key);
        await this.syncSelectedUploadPreview(next);
        if (next.length === 0) this.clearSelectedFile();
        else {
            this.clearAnalysisState();
            this.uploadLogEntries = [];
            this.uploadChunkSummary = null;
            this.trainingUploadMessage = '';
            this.errorMessage = '';
        }
        await this.service.render();
    }

    public selectedUploadTrainingHint(): string {
        if (this.selectedUploadCount() === 0) return '영상 여러 개 또는 zip/tar 압축 파일을 한 번에 선택할 수 있습니다.';
        if (!this.selectedFile) return '압축 파일은 학습 등록만 가능하고, 분석 미리보기는 영상 파일에서만 동작합니다.';
        if (this.selectedUploadCount() > 1) return '분석은 첫 번째 영상으로 실행하고, 학습 등록은 선택된 전체 파일을 순차 저장합니다.';
        return '선택한 영상을 분석하거나 학습 데이터로 등록할 수 있습니다.';
    }

    public trainingTargetOptionsForView(): any[] {
        const options = this.prototypeInfo?.training_target_options;
        return Array.isArray(options) && options.length > 0 ? options : this.fallbackTrainingTargetOptions;
    }

    public trainingTargetOption(key?: string): any {
        const target = String(key || this.trainingTargetModel || 'rf-dual');
        return this.trainingTargetOptionsForView().find((item: any) => item.key === target) || this.trainingTargetOptionsForView()[0] || {};
    }

    public trainingTargetLabel(): string {
        return this.trainingTargetOption().label || this.trainingTargetModel || '모델';
    }

    public trainingTargetDescription(): string {
        return this.trainingTargetOption().description || '선택한 모델 학습 자료로 metadata를 저장합니다.';
    }

    public uploadSettingsTitle(): string {
        return this.uploadWorkflowMode === 'train' ? '등록 기준' : '분석 설정';
    }

    public uploadSelectionModeText(): string {
        if (this.uploadWorkflowMode === 'train') return `${this.trainingTargetLabel()} 학습 자료`;
        return this.selectedFile ? 'RF-Dual 업로드 분석' : '분석할 영상 대기';
    }

    public llmModeHint(): string {
        const settings = this.prototypeInfo?.llm_settings || {};
        if (!settings.enabled) return 'LLM 설명 꺼짐';
        return '기본 local_fast 요약 · 동기 OpenAI 호출 없음';
    }

    public trainingTargetJobType(): string {
        return String(this.trainingTargetOption().job_type || 'full');
    }

    public trainingTargetSupportsDashboardJob(): boolean {
        return ['full', 'rf', 'posture'].includes(this.trainingTargetJobType());
    }

    public async onTrainingTargetModelChanged() {
        if (this.trainingTargetModel === 'xg-posture' && !this.trainingUploadPostureClass) {
            this.trainingUploadMessage = 'XG-Posture 자료는 행동 라벨을 같이 선택해야 학습에 바로 쓰기 좋습니다.';
            this.trainingUploadMessageType = 'info';
        } else if (!this.trainingTargetSupportsDashboardJob()) {
            await this.loadContinuousTrainingStatus(false);
            const status = this.selectedContinuousTrainingStatus();
            this.trainingUploadMessage = `${this.trainingTargetLabel()}은 전용/연속 학습 파이프라인으로 관리됩니다. ${this.continuousTrainingStageText(status)}`;
            this.trainingUploadMessageType = 'info';
        } else {
            this.trainingUploadMessage = '';
        }
        await this.service.render();
    }

    public async analyze() {
        if (!this.selectedFile || this.analyzing) {
            if (!this.selectedFile && this.selectedUploadCount() > 0) this.errorMessage = '분석은 영상 파일 하나가 필요합니다. 압축 파일은 학습 데이터 등록으로 처리해주세요.';
            return;
        }
        const requestKey = `${this.selectedFile.name}:${this.selectedFile.size}:${this.selectedFile.lastModified}:${this.analysisProfile}:${this.selectedModelType}`;
        if (this.uploadAnalysisRequestKey === requestKey) return;
        this.uploadAnalysisRequestKey = requestKey;
        this.analyzing = true;
        this.clearAnalysisState();
        this.errorMessage = '';
        this.feedbackStatus = '';
        this.feedbackMessage = '';
        this.uploadProgress = 0;
        this.uploadLogEntries = [];
        this.uploadChunkSummary = null;
        await this.service.render();
        try {
            const fd = new FormData();
            fd.append('video', this.selectedFile);
            fd.append('metadata', JSON.stringify({ analysis_profile: this.analysisProfile, input_source: 'upload', model_type: this.selectedModelType }));
            const res = await fetch(`/wiz/api/page.dashboard/analyze_upload`, { method: 'POST', body: fd });
            const json = await this.readJsonResponse(res);
            if (json.code === 200 && json.data) {
                this.applyAnalysisRoot(json.data, false);
                this.analysisSavedName = json.data.saved_name || '';
                this.alertWorkflow = json.data.alert_workflow || null;
                this.syncUploadChunkLogs(json.data);
                try {
                    localStorage.setItem(LAST_ANALYSIS_STORAGE_KEY, JSON.stringify(json.data));
                } catch (e) { }
            } else {
                this.errorMessage = json.data?.message || '분석 실패';
            }
        } catch (e: any) {
            this.errorMessage = this.requestErrorMessage(e, '분석 요청');
        }
        this.analyzing = false;
        this.uploadAnalysisRequestKey = '';
        await this.service.render();
    }

    public async registerSelectedFileForTraining(): Promise<boolean> {
        const files = this.selectedFiles.length > 0 ? this.selectedFiles : (this.selectedFile ? [this.selectedFile] : []);
        if (files.length === 0 || this.trainingUploading) return false;
        this.trainingUploading = true;
        this.trainingUploadDone = 0;
        this.trainingUploadTotal = files.length;
        this.trainingUploadMessage = '';
        this.trainingUploadMessageType = 'info';
        await this.service.render();
        let savedTotal = 0;
        const errors: string[] = [];
        try {
            for (let i = 0; i < files.length; i++) {
                const file = files[i];
                const metadata: any = {
                    input_source: 'upload-mode-bulk-training-registration',
                    analysis_profile: this.analysisProfile,
                    model_type: this.selectedModelType,
                    target_model: this.trainingTargetModel,
                    training_target_model: this.trainingTargetModel,
                    training_target_label: this.trainingTargetLabel(),
                    posture_class: this.trainingUploadPostureClass || '',
                    bulk_index: i + 1,
                    bulk_total: files.length,
                };
                if (this.analysisSavedName) metadata.analysis_saved_name = this.analysisSavedName;
                const fd = new FormData();
                fd.append('video', file);
                fd.append('label', this.trainingUploadLabel || 'N');
                fd.append('note', this.trainingUploadNote || '');
                fd.append('metadata', JSON.stringify(metadata));
                const res = await fetch(`/wiz/api/page.dashboard/submit_training_sample`, { method: 'POST', body: fd });
                const json = await this.readJsonResponse(res);
                if (json.code === 200 && json.data) {
                    savedTotal += Number(json.data.saved_count || 1);
                } else {
                    errors.push(`${file.name}: ${json.data?.message || '등록 실패'}`);
                }
                this.trainingUploadDone = i + 1;
                this.trainingUploadMessage = `등록 중 ${this.trainingUploadDone}/${this.trainingUploadTotal} · 저장 ${savedTotal}건`;
                await this.service.render();
            }
            if (errors.length === 0) {
                const postureSaved = this.trainingUploadPostureClass ? ` / 행동 ${this.trainingUploadPostureClass}` : '';
                this.trainingUploadMessage = `학습 데이터 등록 완료: ${this.trainingTargetLabel()} · 파일 ${files.length}개, 영상 ${savedTotal}건 · 라벨 ${this.trainingUploadLabel || 'N'}${postureSaved}`;
                this.trainingUploadMessageType = 'success';
                this.trainingUploadNote = '';
            } else {
                this.trainingUploadMessage = `일부 등록 실패: 저장 ${savedTotal}건, 실패 ${errors.length}건 · ${errors.slice(0, 2).join(' / ')}`;
                this.trainingUploadMessageType = savedTotal > 0 ? 'success' : 'error';
            }
        } catch (e: any) {
            this.trainingUploadMessage = this.requestErrorMessage(e, '학습 데이터 등록');
            this.trainingUploadMessageType = 'error';
        }
        this.trainingUploading = false;
        await this.service.render();
        return this.trainingUploadMessageType !== 'error';
    }

    public async registerAndStartBackgroundTraining() {
        if (this.trainingUploading || this.trainingJobStarting) return;
        const ok = await this.registerSelectedFileForTraining();
        if (!ok) return;
        await this.startBackgroundTraining();
    }

    private stopTrainingJobPolling() {
        if (this.trainingJobPollHandle) {
            clearInterval(this.trainingJobPollHandle);
            this.trainingJobPollHandle = null;
        }
    }

    private startTrainingJobPolling() {
        this.stopTrainingJobPolling();
        this.trainingJobPollHandle = setInterval(() => { this.refreshTrainingJobStatus(); }, 5000);
    }

    private stopContinuousTrainingPolling() {
        if (this.continuousTrainingPollHandle) {
            clearInterval(this.continuousTrainingPollHandle);
            this.continuousTrainingPollHandle = null;
        }
    }

    private startContinuousTrainingPolling() {
        this.stopContinuousTrainingPolling();
        this.continuousTrainingPollHandle = setInterval(() => { this.loadContinuousTrainingStatus(false); }, 20000);
    }

    public async loadContinuousTrainingStatus(render: boolean = true) {
        try {
            const res = await fetch('/wiz/api/page.dashboard/continuous_training_status?name=all');
            const json = await this.readJsonResponse(res);
            if (json.code === 200 && json.data) {
                const items = this.normalizeContinuousTrainingItems(json.data.items || json.data);
                this.continuousTrainingItems = items;
                this.continuousTrainingStatus = this.selectedContinuousTrainingStatus() || json.data;
                if (this.prototypeInfo) {
                    this.prototypeInfo.continuous_training = this.prototypeInfo.continuous_training || {};
                    for (const item of items) {
                        const name = String(item?.name || '').trim();
                        if (name) this.prototypeInfo.continuous_training[name] = item;
                    }
                    this.prototypeInfo.continuous_training_items = items;
                }
            }
        } catch (e) { }
        if (render) await this.service.render();
    }

    private continuousTrainingResumeTarget(status: any): string {
        const name = String(status?.name || '').trim();
        if (name.startsWith('dashboard-')) return this.trainingTargetModel || 'all';
        if (name === 'rf-fall-v2') return 'rf-fall-v2';
        if (name === 'xg-posture') return 'xg-posture';
        if (name === 'xg-posture-occlusion-aux') return 'xg-posture-occlusion-aux';
        if (name === 'aihub82') return 'aihub82';
        if (name === 'aihub173') return 'aihub173';
        return name || this.trainingTargetContinuousStatusName() || 'all';
    }

    public isContinuousTrainingResuming(status: any): boolean {
        return !!this.continuousTrainingResuming[this.continuousTrainingResumeTarget(status)];
    }

    public continuousTrainingResumeButtonText(status: any): string {
        if (this.isContinuousTrainingResuming(status)) return '요청 중';
        const stage = this.continuousTrainingStageValue(status);
        if (stage === 'running') return '점검';
        if (stage === 'blocked' || stage === 'stale' || stage === 'failed') return '재개';
        if (stage === 'queued' || stage === 'preparing') return '점검';
        return '재개';
    }

    public async resumeContinuousTraining(status?: any) {
        const target = this.continuousTrainingResumeTarget(status || {});
        if (this.continuousTrainingResuming[target]) return;
        this.continuousTrainingResuming[target] = true;
        this.trainingUploadMessage = `${this.continuousTrainingCardTitle(status || {})} 재개/점검 요청 중입니다.`;
        this.trainingUploadMessageType = 'info';
        await this.service.render();
        try {
            const params = new URLSearchParams();
            params.set('target', target);
            const res = await fetch(`/wiz/api/page.dashboard/resume_continuous_training?${params.toString()}`, { method: 'POST' });
            const json = await this.readJsonResponse(res);
            if (json.code === 200 && json.data?.ok !== false) {
                const items = this.normalizeContinuousTrainingItems(json.data?.status?.items || json.data?.status || []);
                if (items.length > 0) {
                    this.continuousTrainingItems = items;
                    this.continuousTrainingStatus = this.selectedContinuousTrainingStatus() || json.data.status;
                }
                this.trainingUploadMessage = json.data?.message || '학습 재개/점검 요청을 보냈습니다.';
                this.trainingUploadMessageType = 'success';
            } else {
                this.trainingUploadMessage = json.data?.message || '학습 재개 요청 실패';
                this.trainingUploadMessageType = 'error';
            }
        } catch (e: any) {
            this.trainingUploadMessage = this.requestErrorMessage(e, '학습 재개');
            this.trainingUploadMessageType = 'error';
        }
        this.continuousTrainingResuming[target] = false;
        await this.loadContinuousTrainingStatus(false);
        await this.service.render();
    }

    public async startBackgroundTraining(jobType: string = 'full') {
        if (this.trainingJobStarting) return;
        const resolvedJobType = jobType === 'full' ? this.trainingTargetJobType() : jobType;
        if (!['full', 'rf', 'posture'].includes(resolvedJobType)) {
            await this.loadContinuousTrainingStatus(false);
            const status = this.selectedContinuousTrainingStatus();
            const eta = this.continuousTrainingEtaText(status);
            this.trainingUploadMessage = `${this.trainingTargetLabel()}은 대시보드 HITL job 대신 별도 연속 학습/전용 학습 파이프라인으로 관리됩니다. ${this.continuousTrainingStageText(status)}${eta && eta !== '-' ? ` · ETA ${eta}` : ''}`;
            this.trainingUploadMessageType = 'info';
            await this.service.render();
            return;
        }
        this.trainingJobStarting = true;
        this.trainingUploadMessage = '백그라운드 학습 job을 시작합니다.';
        this.trainingUploadMessageType = 'info';
        await this.service.render();
        try {
            const params = new URLSearchParams();
            params.set('job_type', resolvedJobType || 'full');
            params.set('apply_mode', 'manual');
            params.set('note', this.trainingUploadNote || '');
            params.set('target_model', this.trainingTargetModel || 'rf-dual');
            const res = await fetch(`/wiz/api/page.dashboard/start_training_job?${params.toString()}`, { method: 'POST' });
            const json = await this.readJsonResponse(res);
            const stage = String(json?.data?.stage || json?.data?.status || '').trim();
            if (json.code === 200 && json.data && json.data.ok !== false && stage !== 'blocked' && stage !== 'failed') {
                this.trainingJob = json.data;
                this.trainingUploadMessage = `학습 job 시작: ${json.data.job_id || ''}`;
                this.trainingUploadMessageType = 'success';
                this.startTrainingJobPolling();
            } else {
                if (json.data) this.trainingJob = json.data;
                this.trainingUploadMessage = json.data?.message || '학습 job 시작 실패';
                this.trainingUploadMessageType = 'error';
            }
        } catch (e: any) {
            this.trainingUploadMessage = this.requestErrorMessage(e, '학습 job 요청');
            this.trainingUploadMessageType = 'error';
        }
        this.trainingJobStarting = false;
        await this.service.render();
    }

    public async refreshTrainingJobStatus() {
        const jobId = this.trainingJob?.job_id || 'latest';
        try {
            const res = await fetch(`/wiz/api/page.dashboard/training_job_status?job_id=${encodeURIComponent(jobId)}`);
            const json = await this.readJsonResponse(res);
            if (json.code === 200 && json.data) {
                this.trainingJob = json.data;
                const status = String(this.trainingJob?.status || '');
                if (!['queued', 'running'].includes(status)) {
                    this.stopTrainingJobPolling();
                    const metric = this.trainingJobCandidateMetricText();
                    const sample = this.trainingJobTrainingSampleText();
                    if (status === 'completed_pending_apply' || status === 'completed') {
                        this.trainingUploadMessage = `학습 완료: ${metric} · 샘플 ${sample}`;
                        this.trainingUploadMessageType = 'success';
                    } else if (status === 'applied') {
                        this.trainingUploadMessage = `학습 결과 적용 완료: ${metric}`;
                        this.trainingUploadMessageType = 'success';
                    } else if (status === 'blocked' || status === 'failed') {
                        this.trainingUploadMessage = this.trainingJob?.message || this.trainingJobStatusText();
                        this.trainingUploadMessageType = 'error';
                    }
                }
                await this.service.render();
            }
        } catch (e) { }
    }

    public async applyTrainingJob() {
        if (!this.trainingJob?.job_id || this.trainingJobApplying) return;
        this.trainingJobApplying = true;
        await this.service.render();
        try {
            const res = await fetch(`/wiz/api/page.dashboard/apply_training_job?job_id=${encodeURIComponent(this.trainingJob.job_id)}`, { method: 'POST' });
            const json = await this.readJsonResponse(res);
            if (json.code === 200 && json.data) {
                this.trainingJob = json.data;
                await this.loadPrototypeInfo();
            } else {
                this.trainingUploadMessage = json.data?.message || '학습 결과 적용 실패';
                this.trainingUploadMessageType = 'error';
            }
        } catch (e: any) {
            this.trainingUploadMessage = this.requestErrorMessage(e, '학습 적용');
            this.trainingUploadMessageType = 'error';
        }
        this.trainingJobApplying = false;
        await this.service.render();
    }

    public trainingJobProgressPercent(): number {
        return Math.max(0, Math.min(100, Math.round(Number(this.trainingJob?.progress || 0) * 100)));
    }

    public trainingJobStatusText(): string {
        const status = String(this.trainingJob?.status || '');
        if (status === 'queued') return '대기 중';
        if (status === 'running') return '학습 중';
        if (status === 'completed_pending_apply') return '학습 완료';
        if (status === 'completed') return '학습 완료';
        if (status === 'applied') return '적용 완료';
        if (status === 'blocked') return '데이터 필요';
        if (status === 'failed') return '실패';
        return status || '상태 없음';
    }

    public trainingJobEtaText(): string {
        const status = String(this.trainingJob?.status || '');
        if (status === 'completed_pending_apply' || status === 'completed' || status === 'applied') return '완료';
        if (status === 'blocked') return '데이터 필요';
        if (status === 'failed') return '실패';
        const eta = Number(this.trainingJob?.eta_sec);
        if (!Number.isFinite(eta) || eta <= 0) return '계산 중';
        if (eta < 60) return `${Math.round(eta)}초`;
        const min = Math.floor(eta / 60);
        const sec = Math.round(eta % 60);
        return `${min}분 ${sec}초`;
    }

    public trainingJobVersionText(): string {
        const jobId = String(this.trainingJob?.job_id || '').trim();
        if (!jobId) return '-';
        const version = String(this.trainingJob?.training_run_label || this.trainingJob?.version_badge || '').trim();
        const target = this.trainingJob?.target_model ? String(this.trainingJob.target_model) : '';
        const shortId = jobId.length > 13 ? jobId.slice(0, 12) : jobId;
        if (version) return target ? `${version} · ${target} · ${shortId}` : `${version} · ${shortId}`;
        return target ? `${target} · ${shortId}` : shortId;
    }

    public trainingJobCanApply(): boolean {
        return this.trainingJob?.status === 'completed_pending_apply';
    }

    private jobNumber(value: any): number {
        const n = Number(value);
        return Number.isFinite(n) ? n : 0;
    }

    private jobPct(value: any, digits: number = 1): string {
        const n = this.jobNumber(value);
        return n > 0 ? `${(n * 100).toFixed(digits)}%` : '';
    }

    private dashboardJobRfSummary(jobArg?: any): any {
        const job = jobArg || this.trainingJob || {};
        const result = job.result || {};
        if (result.rf_pipeline_training && typeof result.rf_pipeline_training === 'object') return result.rf_pipeline_training;
        const steps = Array.isArray(job.steps) ? job.steps : [];
        const rfStep = steps.find((step: any) => String(step?.name || '') === 'rf_pipeline');
        const summary = rfStep?.result?.summary;
        return summary && typeof summary === 'object' ? summary : {};
    }

    private dashboardJobCvMetrics(jobArg?: any): any {
        const job = jobArg || this.trainingJob || {};
        const rf = this.dashboardJobRfSummary(job);
        if (rf.cv && typeof rf.cv === 'object') return rf.cv;
        const model = job?.result?.model_comparison?.models?.['rf-pipeline'] || {};
        return {
            f1: model?.f1?.cv ?? job?.candidate_f1,
            accuracy: model?.accuracy?.cv ?? job?.candidate_accuracy,
            precision: model?.precision?.cv ?? job?.candidate_precision,
            recall: model?.recall?.cv ?? job?.candidate_recall,
            roc_auc: model?.roc_auc?.cv ?? job?.candidate_roc_auc,
        };
    }

    public trainingJobTrainingSampleText(jobArg?: any): string {
        const job = jobArg || this.trainingJob || {};
        const rf = this.dashboardJobRfSummary(job);
        const samples = this.jobNumber(rf.training_samples ?? job?.training_samples ?? job?.intake_summary?.total ?? job?.processed);
        return samples > 0 ? samples.toLocaleString() : '-';
    }

    public trainingJobCandidateMetricText(jobArg?: any): string {
        const cv = this.dashboardJobCvMetrics(jobArg);
        const bits = [];
        const f1 = this.jobPct(cv.f1);
        const acc = this.jobPct(cv.accuracy);
        const recall = this.jobPct(cv.recall);
        if (f1) bits.push(`CV F1 ${f1}`);
        if (acc) bits.push(`Acc ${acc}`);
        if (recall) bits.push(`Recall ${recall}`);
        return bits.join(' · ') || '-';
    }

    public trainingJobClassBalanceText(jobArg?: any): string {
        const job = jobArg || this.trainingJob || {};
        const rf = this.dashboardJobRfSummary(job);
        const dist = rf.class_distribution || job.intake_summary || {};
        const y = this.jobNumber(dist.Y);
        const n = this.jobNumber(dist.N);
        if (y > 0 || n > 0) return `Y ${y.toLocaleString()} / N ${n.toLocaleString()}`;
        return '-';
    }

    public normalizeContinuousTrainingItems(raw: any): any[] {
        if (Array.isArray(raw)) return raw.filter(Boolean);
        if (raw?.items && Array.isArray(raw.items)) return raw.items.filter(Boolean);
        if (raw && typeof raw === 'object') {
            if (raw.aihub82 || raw.aihub173 || raw['xg-posture-occlusion-aux']) {
                return Object.keys(raw).map(key => ({ name: key, ...(raw[key] || {}) })).filter(Boolean);
            }
            return [raw];
        }
        return [];
    }

    private trainingTargetContinuousStatusName(): string {
        const option = this.trainingTargetOption();
        const key = String(option?.key || this.trainingTargetModel || '').trim();
        const jobType = String(option?.job_type || '').trim();
        if (jobType === 'aihub82' || key.includes('aihub82')) return 'aihub82';
        if (jobType === 'aihub173' || key.includes('aihub173') || key.includes('driver')) return 'aihub173';
        if (key === 'rf-fall-v2') return 'rf-fall-v2';
        if (key === 'xg-posture') return 'xg-posture';
        if (key.includes('occlusion')) return 'xg-posture-occlusion-aux';
        return '';
    }

    public selectedContinuousTrainingStatus(): any {
        const selectedName = this.trainingTargetContinuousStatusName();
        const items = this.normalizeContinuousTrainingItems(this.continuousTrainingItems);
        if (selectedName) {
            const selected = items.find((item: any) => String(item?.name || '') === selectedName);
            if (selected) return selected;
        }
        const running = items.find((item: any) => ['queued', 'running'].includes(this.continuousTrainingStageValue(item)));
        return running || items.find((item: any) => String(item?.name || '') === 'aihub82') || this.continuousTrainingStatus || {};
    }

    private continuousTrainingStatusValues(): any[] {
        const byName: Record<string, any> = {};
        const items = this.normalizeContinuousTrainingItems(this.continuousTrainingItems);
        for (let index = 0; index < items.length; index += 1) {
            const item = items[index];
            const key = String(item?.name || item?.label || item?.job_id || `item-${index}`);
            byName[key] = item;
        }
        if (this.continuousTrainingStatus && Object.keys(byName).length === 0) {
            byName['aihub82'] = { name: 'aihub82', label: 'AI-Hub 82 표정', ...this.continuousTrainingStatus };
        }
        if (this.trainingJob?.status) {
            const jobKey = 'dashboard-' + String(this.trainingJob.job_id || 'latest');
            if (!byName[jobKey]) {
                byName[jobKey] = {
                    name: jobKey,
                    label: this.trainingTargetLabel() || '대시보드 학습',
                    model_family: 'dashboard-job',
                    ...this.trainingJob,
                };
            }
        }
        return Object.values(byName);
    }

    private isMainContinuousTrainingStage(stage: string): boolean {
        return ['queued', 'running', 'blocked', 'failed', 'stale', 'preparing', 'completed_pending_apply'].includes(stage);
    }

    private isCompletedContinuousTrainingStage(stage: string): boolean {
        return stage === 'completed' || stage === 'applied';
    }

    public continuousTrainingCards(): any[] {
        const selectedName = this.trainingTargetContinuousStatusName();
        const values = this.continuousTrainingStatusValues().filter((item: any) => {
            const stage = this.continuousTrainingStageValue(item);
            if (!stage || stage === 'missing' || stage === 'not-started') return false;
            if (stage === 'queued' || stage === 'running') return true;
            if (this.uploadWorkflowMode !== 'train') return false;
            return this.isMainContinuousTrainingStage(stage);
        });
        values.sort((a: any, b: any) => {
            const rank = (item: any) => {
                const stage = this.continuousTrainingStageValue(item);
                if (stage === 'running') return 0;
                if (stage === 'queued') return 1;
                if (String(item?.name || '') === selectedName) return 2;
                if (stage === 'stale' || stage === 'failed' || stage === 'blocked') return 3;
                if (stage === 'preparing') return 4;
                return 5;
            };
            const rankDiff = rank(a) - rank(b);
            if (rankDiff !== 0) return rankDiff;
            return String(b?.updated_at || b?.created_at || '').localeCompare(String(a?.updated_at || a?.created_at || ''));
        });
        return values.slice(0, 6);
    }

    public completedTrainingLogCards(): any[] {
        const values = this.continuousTrainingStatusValues().filter((item: any) => {
            const stage = this.continuousTrainingStageValue(item);
            return this.isCompletedContinuousTrainingStage(stage);
        });
        values.sort((a: any, b: any) => {
            return String(b?.updated_at || b?.created_at || '').localeCompare(String(a?.updated_at || a?.created_at || ''));
        });
        return values.slice(0, 6);
    }

    public completedTrainingLogCount(): number {
        return this.continuousTrainingStatusValues().filter((item: any) => {
            return this.isCompletedContinuousTrainingStage(this.continuousTrainingStageValue(item));
        }).length;
    }

    public trainingStatusMainCountText(): string {
        const count = this.continuousTrainingCards().length;
        return count > 0 ? `${count}개 진행/조치 상태 표시` : '진행/조치 상태 없음';
    }

    public isTrainingJobActive(): boolean {
        const status = String(this.trainingJob?.status || '');
        return status === 'queued' || status === 'running';
    }

    public continuousTrainingGridClass(): string {
        const count = this.continuousTrainingCards().length;
        if (count >= 2) return 'xl:grid-cols-2';
        return 'xl:grid-cols-1';
    }

    public continuousTrainingCardTitle(status: any): string {
        return String(status?.label || status?.title || status?.name || '학습 상태');
    }

    public continuousTrainingStageBadgeText(status: any): string {
        const stage = this.continuousTrainingStageValue(status);
        if (stage === 'running' && this.isSourceRecoveryTrainingStatus(status)) return '재수신 중';
        if (stage === 'running') return '학습 중';
        if (stage === 'queued') return '대기';
        if (stage === 'blocked') return '데이터 대기';
        if (stage === 'preparing') return '준비 필요';
        if (stage === 'stale') return '중단';
        if (stage === 'completed_pending_apply') return '적용 대기';
        if (stage === 'applied') return '적용 완료';
        if (stage === 'completed') return '완료';
        if (stage === 'failed') return '실패';
        return stage || '-';
    }

    private continuousTrainingStageValue(status: any): string {
        const rawStage = String(status?.stage || '').trim();
        const rawStatus = String(status?.status || '').trim();
        if (rawStage === 'finished' && rawStatus) return rawStatus;
        if (rawStage === 'blocked' || rawStatus === 'blocked') return 'blocked';
        if (rawStage === 'stale' || rawStatus === 'stale') return 'stale';
        return rawStage || rawStatus;
    }

    public continuousTrainingCardClass(status: any): string {
        const stage = this.continuousTrainingStageValue(status);
        if (stage === 'failed') return 'border-rose-200 bg-rose-50';
        if (stage === 'stale' || stage === 'blocked') return 'border-amber-200 bg-amber-50';
        if (stage === 'preparing') return 'border-zinc-200 bg-zinc-50';
        if (stage === 'queued' || stage === 'running') return 'border-emerald-200 bg-emerald-50';
        if (stage === 'completed' || stage === 'completed_pending_apply' || stage === 'applied') return 'border-blue-200 bg-blue-50';
        return 'border-zinc-200 bg-white';
    }

    public continuousTrainingStageText(statusArg?: any): string {
        const status = statusArg || this.continuousTrainingStatus || {};
        const stage = this.continuousTrainingStageValue(status);
        const version = String(status.candidate_version_text || status.training_version_text || '').trim()
            || this.compactExperimentVersion(String(status.experiment || '').trim());
        const suffix = version && version !== '-' ? ` · ${version}` : '';
        const label = this.continuousTrainingCardTitle(status);
        if (stage === 'running' && this.isSourceRecoveryTrainingStatus(status)) return `${label} 데이터 재수신 중${suffix}`;
        if (stage === 'running') return `${label} 학습 중${suffix}`;
        if (stage === 'queued') return `${label} 대기 중${suffix}`;
        if (stage === 'blocked') return `${label} 데이터 대기${suffix}`;
        if (stage === 'preparing') return `${label} 준비 필요${suffix}`;
        if (stage === 'completed_pending_apply') return `${label} 학습 완료 · 적용 대기`;
        if (stage === 'applied') return `${label} 학습 결과 적용 완료`;
        if (stage === 'completed') return status.promoted ? `${label} 운영 성능 충족` : `${label} 학습 완료`;
        if (stage === 'failed') return `${label} 학습 실패`;
        if (stage === 'stale') return `${label} 중단됨 · 상태 확인 필요`;
        if (stage === 'already-running') return '이미 실행 중';
        if (stage === 'not-started' || stage === 'missing') return '대기 중';
        return stage || '상태 확인 중';
    }

    public continuousTrainingMetricText(statusArg?: any): string {
        const status = statusArg || this.continuousTrainingStatus || {};
        if (status?.model_family === 'dashboard-job') {
            const stage = this.continuousTrainingStageValue(status);
            const metric = this.trainingJobCandidateMetricText(status);
            const samples = this.trainingJobTrainingSampleText(status);
            const balance = this.trainingJobClassBalanceText(status);
            if (metric !== '-') {
                const bits = [metric];
                if (samples !== '-') bits.push(`샘플 ${samples}`);
                if (balance !== '-') bits.push(balance);
                return bits.join(' · ');
            }
            if (stage === 'blocked') return status?.message || '학습 차단 · 데이터 필요';
            if (stage === 'failed') return status?.message || '학습 실패';
            const progress = Math.round(Number(status.progress || 0) * 100);
            const processed = Number(status.processed || 0);
            const total = Number(status.total || 0);
            return total > 0 ? `진행 ${progress}% · 처리 ${processed}/${total}` : `진행 ${progress}%`;
        }
        const candidateSeqF1 = Number(status?.candidate_sequence_macro_f1 || 0);
        const candidateF1 = Number(status?.candidate_macro_f1 || 0);
        if (candidateSeqF1 > 0 || candidateF1 > 0) {
            const activeSeqF1 = Number(status?.sequence_macro_f1 || 0);
            const activeF1 = Number(status?.active_macro_f1 || status?.macro_f1 || 0);
            const bits = [];
            if (activeSeqF1 > 0) bits.push(`active sequence F1 ${(activeSeqF1 * 100).toFixed(1)}%`);
            else if (activeF1 > 0) bits.push(`active F1 ${(activeF1 * 100).toFixed(1)}%`);
            if (candidateSeqF1 > 0) bits.push(`후보 sequence F1 ${(candidateSeqF1 * 100).toFixed(1)}%`);
            else if (candidateF1 > 0) bits.push(`후보 F1 ${(candidateF1 * 100).toFixed(1)}%`);
            if (status?.candidate_saved === false) bits.push('미승격');
            const target = Number(status?.target_macro_f1 || 0.95);
            bits.push(`목표 ${(target * 100).toFixed(0)}%`);
            return bits.join(' · ');
        }
        const seqF1 = Number(status?.sequence_macro_f1 || 0);
        const seqAcc = Number(status?.sequence_accuracy || 0);
        if (seqF1 > 0 || seqAcc > 0) {
            const group = Number(status?.active_macro_f1 || status?.macro_f1 || 0);
            const bits = [];
            if (seqF1 > 0) bits.push(`sequence F1 ${(seqF1 * 100).toFixed(1)}%`);
            if (seqAcc > 0) bits.push(`sequence Acc ${(seqAcc * 100).toFixed(1)}%`);
            if (group > 0) bits.push(`window F1 ${(group * 100).toFixed(1)}%`);
            return bits.join(' · ');
        }
        const active = Number(status?.active_macro_f1 || status?.macro_f1 || 0);
        const candidate = Number(status?.candidate_macro_f1 || 0);
        const target = Number(status?.target_macro_f1 || 0.9);
        const stretch = Number(status?.stretch_macro_f1 || 0.95);
        const activeVersion = String(status?.active_version_text || '').trim();
        const activePrefix = activeVersion ? `active ${activeVersion} ` : 'active ';
        const activeText = active > 0 ? `${activePrefix}macro F1 ${(active * 100).toFixed(1)}%` : `${activePrefix}F1 확인 중`;
        const targetText = `목표 ${(target * 100).toFixed(0)}%→${(stretch * 100).toFixed(0)}%`;
        return candidate > 0 ? `${activeText} · 학습 결과 ${(candidate * 100).toFixed(1)}% · ${targetText}` : `${activeText} · ${targetText}`;
    }

    private compactExperimentVersion(label: string): string {
        const raw = String(label || '').trim();
        const match = raw.match(/^(\d+)_([A-Za-z0-9_.-]+?)(?:_\d{8}_\d{6})?$/);
        if (!match) return raw || '-';
        return `#${match[1]} ${match[2].replace(/_/g, ' ')}`;
    }

    private isSourceRecoveryTrainingStatus(status: any): boolean {
        const text = [
            status?.latest_log,
            status?.message,
            status?.eta_text,
        ].map((value: any) => String(value || '').toLowerCase()).join(' ');
        return text.includes('[source]')
            || text.includes('download')
            || text.includes('다운로드')
            || text.includes('재수신')
            || text.includes('split zip')
            || text.includes('assembly');
    }

    public continuousTrainingVersionText(statusArg?: any): string {
        const status = statusArg || this.continuousTrainingStatus || {};
        const readyText = String(status.training_version_text || '').trim();
        if (readyText) return readyText;
        const candidate = String(status.candidate_version_text || '').trim();
        const active = String(status.active_version_text || '').trim();
        const experiment = String(status.experiment || '').trim();
        const bits = [];
        if (candidate) bits.push(`진행 ${candidate}`);
        else if (experiment) bits.push(`진행 ${this.compactExperimentVersion(experiment)}`);
        if (active) bits.push(`active ${active}`);
        const total = Number(status.total_candidate_versions || 0);
        if (Number.isFinite(total) && total > 0) bits.push(`누적 후보 ${total}개`);
        return bits.length > 0 ? bits.join(' · ') : '-';
    }

    public continuousTrainingUpdatedText(): string {
        return String(this.continuousTrainingStatus?.updated_at || '-');
    }

    public continuousTrainingUpdatedTextFor(statusArg?: any): string {
        const status = statusArg || {};
        return String(status.updated_at || status.created_at || '-');
    }

    public continuousTrainingEtaText(statusArg?: any): string {
        const status = statusArg || this.continuousTrainingStatus || {};
        const text = String(status.eta_text || '').trim();
        if (text) return text;
        const eta = Number(status.eta_sec);
        if (!Number.isFinite(eta) || eta <= 0) {
            const stage = this.continuousTrainingStageValue(status);
            if (stage === 'completed' || stage === 'completed_pending_apply' || stage === 'applied') return '완료';
            if (stage === 'stale') return '중단';
            if (stage === 'blocked') return '데이터 필요';
            return '-';
        }
        if (eta < 60) return `${Math.round(eta)}초`;
        const min = Math.floor(eta / 60);
        const sec = Math.round(eta % 60);
        if (min < 60) return `${min}분 ${sec}초`;
        const hour = Math.floor(min / 60);
        const remMin = min % 60;
        return `${hour}시간 ${remMin}분`;
    }

    public continuousTrainingDataProgressText(statusArg?: any): string {
        const status = statusArg || this.continuousTrainingStatus || {};
        const completed = Number(status.completed_files);
        const required = Number(status.required_files);
        const current = Number(status.redownload_current);
        const total = Number(status.redownload_total);
        const progress = Number(status.redownload_current_progress);
        const speed = Number(status.redownload_current_speed_mbps);
        const bits: string[] = [];
        if (Number.isFinite(completed) && Number.isFinite(required) && required > 0) {
            bits.push(`확보 ${completed}/${required}`);
        }
        if (Number.isFinite(current) && Number.isFinite(total) && total > 0) {
            bits.push(`현재 ${current}/${total}`);
        }
        if (Number.isFinite(progress) && progress > 0) {
            bits.push(`파일 ${Math.round(Math.max(0, Math.min(1, progress)) * 100)}%`);
        }
        if (Number.isFinite(speed) && speed > 0) {
            bits.push(`${speed.toFixed(1)}MB/s`);
        }
        if (bits.length > 0) return bits.join(' · ');
        const purpose = String(status.data_purpose || '').trim();
        if (purpose) return purpose;
        return this.continuousTrainingUpdatedTextFor(status);
    }

    public continuousTrainingDownloadProgressPercent(statusArg?: any): number {
        const progress = Number((statusArg || {}).redownload_current_progress);
        if (!Number.isFinite(progress) || progress <= 0) return 0;
        return Math.round(Math.max(0, Math.min(1, progress)) * 100);
    }

    public modelTrainingStatCards(): any[] {
        const stats = this.prototypeInfo?.dataset_summary?.model_training_stats;
        if (Array.isArray(stats) && stats.length > 0) return stats.slice(0, 6);
        return [];
    }

    public analysisModelOptionsForView(): any[] {
        const options = this.prototypeInfo?.model_options?.options;
        if (Array.isArray(options) && options.length > 0) {
            return options.filter((item: any) => item?.available !== false);
        }
        return [{ key: 'rf-dual', label: 'RF-Dual (Fall+Posture)', description: '현재 운영 모델' }];
    }

    public selectedAnalysisModelOption(): any {
        return this.analysisModelOptionsForView().find((item: any) => item?.key === this.selectedModelType) || this.analysisModelOptionsForView()[0] || {};
    }

    public selectedAnalysisModelLabel(): string {
        return this.selectedAnalysisModelOption()?.label || 'RF-Dual (Fall+Posture)';
    }

    public async onAnalysisModelChanged() {
        this.uploadAnalysisRequestKey = '';
        this.realtimePerfStats.warmupMs = 0;
        if (this.realtimeActive) {
            this.errorMessage = '모델 변경은 다음 청크부터 반영됩니다.';
        }
        await this.service.render();
    }

    public modelMetricText(item: any): string {
        const bits = [];
        if (item?.algorithm) bits.push(String(item.algorithm));
        const f1 = Number(item?.macro_f1 ?? item?.f1 ?? 0);
        const acc = Number(item?.accuracy ?? 0);
        const recall = Number(item?.recall ?? 0);
        if (Number.isFinite(f1) && f1 > 0) bits.push(`F1 ${(f1 * 100).toFixed(1)}%`);
        if (Number.isFinite(acc) && acc > 0) bits.push(`Acc ${(acc * 100).toFixed(1)}%`);
        if (Number.isFinite(recall) && recall > 0) bits.push(`Recall ${(recall * 100).toFixed(1)}%`);
        return bits.join(' · ') || item?.metric_note || '-';
    }

    public modelVersionBadge(item: any): string {
        const direct = String(item?.version_badge || '').trim();
        if (direct) return direct;
        const values = [
            item?.training_run_label,
            item?.version_text,
            item?.active_version_text,
            item?.model_version,
            item?.version,
        ];
        for (const value of values) {
            const text = String(value || '').trim();
            if (!text) continue;
            const longMatch = text.match(/(?:^|[^A-Za-z0-9])v\s*([0-9]{8,20})(?:[^A-Za-z0-9]|$)/i);
            if (longMatch) return `v${longMatch[1]}`;
            const match = text.match(/(?:^|[^A-Za-z0-9])v\s*([0-9]{1,4})(?:[^A-Za-z0-9]|$)/i);
            if (match) return `v${Number(match[1])}`;
            const cycle = text.match(/(?:^|[^A-Za-z0-9])cycle\s*0*([1-9][0-9]{0,5})(?:[^0-9]|$)/i);
            if (cycle) return `v${Number(cycle[1])}`;
        }
        return '';
    }

    public modelVersionText(item: any): string {
        const label = String(item?.training_run_label || '').trim();
        const text = String(item?.version_text || '').trim();
        if (label && text && text !== '-') return `${label} · ${text}`;
        if (label) return label;
        if (text && text !== '-') return `active 버전: ${text}`;
        const source = String(item?.model_path || '').split('/').pop() || '';
        return source ? `active 버전: ${source}` : 'active 버전: -';
    }

    public modelContinuousTrainingText(item: any): string {
        const badge = String(item?.current_training_badge || '').trim();
        const text = String(item?.continuous_training_version_text || '').trim();
        if (badge && text && text !== '-') return `${badge} · ${text}`;
        if (badge) return badge;
        if (!text || text === '-') return '';
        const stage = String(item?.continuous_training_stage || '').trim();
        const prefix = stage === 'running' ? '연속 학습' : '연속 상태';
        return `${prefix}: ${text}`;
    }

    public clearSelectedFile() {
        this.revokeSelectedVideoUrl();
        this.selectedFile = null;
        this.selectedFiles = [];
        this.clearAnalysisState();
        this.feedbackStatus = '';
        this.trainingUploadMessage = '';
        this.trainingUploadDone = 0;
        this.trainingUploadTotal = 0;
        this.trainingJob = null;
        this.stopTrainingJobPolling();
        this.errorMessage = '';
        this.uploadLogEntries = [];
        this.uploadChunkSummary = null;
    }

    public riskClass(level: string): string { if (level === 'high') return 'text-rose-600'; if (level === 'medium') return 'text-amber-600'; return 'text-emerald-600'; }
    public riskBgClass(level: string): string { if (level === 'high') return 'bg-rose-50 border-rose-200'; if (level === 'medium') return 'bg-amber-50 border-amber-200'; return 'bg-emerald-50 border-emerald-200'; }
    public riskBadgeClass(level: string): string { if (level === 'high') return 'bg-rose-100 text-rose-700'; if (level === 'medium') return 'bg-amber-100 text-amber-700'; return 'bg-emerald-100 text-emerald-700'; }
    public riskScorePercent(): number { return Math.round((this.analysisResult?.risk_score || 0) * 100); }
    public formatRisk(score: number): string { return (score * 100).toFixed(0) + '%'; }
    public currentEngineLabel(): string {
        const key = this.analysisResult?.runtime_key || '';
        const selectedVersion = this.analysisResult?.selected_model_version?.label || '';
        if (selectedVersion) return selectedVersion;
        const runtimeLabel = this.prototypeInfo?.analysis_engine_summary?.current_runtime?.label || '';
        if (this.currentModelStatusLabel() === 'ready' && (!key || key === 'heuristic-fallback')) {
            return runtimeLabel || 'RF-Dual (Fall+Posture)';
        }
        if (key === 'person-feature-runtime') return 'XGBoost v2 (사람 추적)';
        if (key === 'rf-pipeline-runtime') return 'RF 보조 (RandomForest)';
        if (key === 'rf-dual') return 'RF-Dual (Fall+Posture)';
        if (key === 'rf-dual-person') return 'RF-Dual 사람별 분석';
        if (key === 'heuristic-fallback') return '휴리스틱 Fallback';
        if (runtimeLabel) return runtimeLabel;
        if (this.selectedModelType === 'rf-dual') {
            return this.prototypeInfo?.trained_model?.runtime_ready ? 'RF-Dual (Fall+Posture)' : '모델 없음 (Fallback)';
        }
        return this.selectedAnalysisModelLabel() || key || '알 수 없음';
    }
    public currentModelStatusLabel(): string {
        const trainedReady = this.prototypeInfo?.trained_model?.runtime_ready === true;
        const runtimeReady = this.prototypeInfo?.analysis_engine_summary?.current_runtime?.key === 'rf-dual-runtime';
        const baseReady = this.prototypeInfo?.baseline_model_ready === true && this.prototypeInfo?.behavior_model_ready === true;
        if (trainedReady || runtimeReady || baseReady) return 'ready';
        if (this.analysisResult?.runtime_key === 'heuristic-fallback') return 'fallback';
        return 'missing';
    }
    public currentModelStatusText(): string {
        const status = this.currentModelStatusLabel();
        if (status === 'ready') return '운영 모델 연결됨';
        if (status === 'fallback') return 'fallback 동작 중';
        return '운영 모델 파일 없음';
    }
    public currentModelWeightsPath(): string {
        return this.prototypeInfo?.trained_model?.weights_path || '';
    }
    public runtimeRfModelPath(): string {
        return this.analysisResult?.model_runtime?.rf_model_path || '';
    }
    public runtimePostureClassifierPath(): string {
        return this.analysisResult?.model_runtime?.posture_classifier || '';
    }
    public modelSpeedHint(): string {
        const key = this.selectedModelType || '';
        if (key.startsWith('registry:')) return '선택한 모델 버전으로 RF-Dual 분석';
        if (this.inputMode === 'webcam') {
            if (key === 'person-feature') return '~8초/청크';
            if (key === 'rf-dual') return '4초 청크 / 누락 없는 순차 큐';
            return '~3초/청크';
        }
        if (key === 'person-feature') return '5~15초';
        if (key === 'rf-dual') return '단일 분석 + 실시간은 4초 청크';
        return '3~8초';
    }
    public getRiskScoreFormula(): string {
        const key = this.analysisResult?.runtime_key || '';
        const guide = this.analysisResult?.risk_score_guide;
        if (guide?.formula) return guide.formula;
        if (key === 'rf-dual' || key === 'rf-dual-person') return 'RF predict_proba → motion guard → XG-Posture 5-class';
        if (key === 'person-feature-runtime') return 'max(window_probs) × fall_ratio';
        return 'fall_probability × motion_factor';
    }
    public sortedAnalysisBasis(): any[] { const basis = this.analysisResult?.analysis_basis || []; return [...basis].sort((a: any, b: any) => (a.contribution_rank || 99) - (b.contribution_rank || 99)); }
    public basisCardClass(item: any): string { const lvl = item.level || 'normal'; if (lvl === 'danger' || lvl === 'high') return 'border-rose-200 bg-rose-50'; if (lvl === 'warning' || lvl === 'medium') return 'border-amber-200 bg-amber-50'; return 'border-zinc-200 bg-zinc-50'; }
    public facialStateAux(result?: any): any {
        const res = result || this.analysisResult || {};
        return res?.facial_state || res?.runtime_inference?.facial_state || null;
    }
    public hasFacialStateAux(result?: any): boolean {
        const face = this.facialStateAux(result);
        return Boolean(face);
    }
    public facialStateAuxText(result?: any): string {
        const face = this.facialStateAux(result);
        if (!face) return '';
        const actualFaceRatio = Number(face.actual_face_ratio || 0);
        const poseFallbackRatio = Number(face.pose_head_roi_ratio || 0);
        if (face.reason === 'face_not_detected' || face.face_visible === false || (!face.face_detected && poseFallbackRatio >= 0.5)) {
            return `얼굴/표정 미검출 · 실제얼굴 ${Math.round(actualFaceRatio * 100)}% · pose대체 ${Math.round(poseFallbackRatio * 100)}% · 감정 점수 미사용`;
        }
        const emotion = face.emotion_display_label || face.emotion_top_label || this.facialEmotionLabel(face.emotion_top);
        const emotionConfidence = Math.round(Number(face.emotion_confidence || 0) * 100);
        const emotionMargin = Math.round(Number(face.emotion_margin || 0) * 100);
        const emotionConsistency = Math.round(Number(face.emotion_consistency || 0) * 100);
        const qualityMap: Record<string, string> = { high: '높음', medium: '보통', low: '낮음', unavailable: '불가' };
        const quality = qualityMap[String(face.emotion_quality || 'unavailable')] || '낮음';
        const rawDistress = Math.round(Number(face.distress_score ?? 0) * 100);
        const trustedDistress = Math.round(Number(face.trusted_distress_score ?? face.distress_score ?? 0) * 100);
        const faceRatio = Math.round(Number(face.actual_face_ratio || 0) * 100);
        const driver = face.driver_state_top_label || this.facialDriverStateLabel(face.driver_state_top);
        const driverConfidence = Math.round(Number(face.driver_state_confidence || 0) * 100);
        const driverRisk = Math.round(Number(face.driver_state_risk || 0) * 100);
        const modelMode = String(face.emotion_output_mode || '') === 'distress_signal' ? '불편신호 모델' : '표정분류 모델';
        const suffix = face.emotion_top && face.emotion_top !== 'unavailable'
            ? `${modelMode} · ${emotion} · 모델확신 ${emotionConfidence}% · margin ${emotionMargin}% · 일치 ${emotionConsistency}% · 신뢰 ${quality} · 불편 raw ${rawDistress}% / 신뢰보정 ${trustedDistress}% · 실제얼굴 ${faceRatio}%`
            : '';
        const driverSuffix = face.driver_state_top && face.driver_state_top !== 'unavailable'
            ? `상태 ${driver} ${driverConfidence}% · 주의저하 ${driverRisk}%${face.driver_state_reliable ? '' : ' · 저신뢰'}`
            : '';
        const combined = [suffix, driverSuffix].filter(Boolean).join(' · ');
        if (face.applied) return `${combined || face.label || '표정 보조'} · +${Math.round(Number(face.support_score || 0) * 100)}%p 반영`;
        if (face.available) return `${combined || face.label || '표정 분석'} · 점수 미반영`;
        if (face.reason === 'face_not_detected') return '얼굴 미검출 · 점수 미반영';
        if (face.reason === 'body_not_suspected') return '낙상 의심 점수 미만 · 표시 대기';
        return face.description || '표정 보조 분석 불가';
    }
    public facialEmotionLabel(code: string): string {
        const labels: Record<string, string> = {
            neutral: '중립',
            happiness: '기쁨',
            embarrassed: '당황',
            surprise: '놀람',
            anxiety: '불안',
            distress: '불편/고통',
            non_distress: '비불편',
            hurt: '상처',
            sadness: '슬픔',
            anger: '분노',
            disgust: '불쾌',
            fear: '공포',
            contempt: '경멸',
            unavailable: '분석 불가',
        };
        return labels[code || ''] || code || '분석 불가';
    }
    public facialDriverStateLabel(code: string): string {
        const labels: Record<string, string> = {
            normal_focus: '정상/집중',
            drowsy: '졸림',
            yawn: '하품',
            phone_call: '통화',
            smoking: '흡연',
            unavailable: '상태 분석 불가',
        };
        return labels[code || ''] || code || '상태 분석 불가';
    }
    public facialStateLabel(result?: any): string {
        const face = this.facialStateAux(result);
        if (!face) return '대기';
        if (face.reason === 'face_not_detected' || face.face_visible === false || (!face.face_detected && Number(face.pose_head_roi_ratio || 0) >= 0.5)) return '얼굴/표정 미검출';
        if (face.applied) return face.label || '표정 보조 반영';
        if (face.available) {
            if (face.label) return face.label;
            if (face.emotion_top && face.emotion_top !== 'unavailable') return face.emotion_display_label || face.emotion_top_label || this.facialEmotionLabel(face.emotion_top);
            if (face.driver_state_top && face.driver_state_top !== 'unavailable') return face.driver_state_top_label || this.facialDriverStateLabel(face.driver_state_top);
            return face.label || '표정 분석';
        }
        if (face.reason === 'face_not_detected') return '얼굴 미검출';
        if (face.reason === 'body_not_suspected') return '표시 대기';
        if (face.reason === 'no_frames') return '프레임 없음';
        return '분석 불가';
    }
    public facialStatePercent(result?: any): number {
        const face = this.facialStateAux(result);
        if (!face) return 0;
        if (face.reason === 'face_not_detected' || face.face_visible === false || (!face.face_detected && Number(face.pose_head_roi_ratio || 0) >= 0.5)) return 0;
        if (face.available && face.emotion_reliable && Number(face.emotion_confidence || 0) > 0) return Math.round(Number(face.emotion_confidence || 0) * 100);
        if (face.available && Number.isFinite(Number(face.actual_face_ratio))) {
            return Math.round(Number(face.facial_confidence || 0) * Number(face.actual_face_ratio || 0) * 100);
        }
        if (face.available && Number(face.facial_confidence || 0) > 0) return Math.round(Number(face.facial_confidence || 0) * 100);
        if (face.available && Number(face.driver_state_confidence || 0) > 0) return Math.round(Number(face.driver_state_confidence || 0) * 100);
        if (face.reason === 'face_not_detected') return 0;
        return Math.round(Number(face.support_score || 0) * 100);
    }
    public facialEvidenceLines(result?: any): string[] {
        const face = this.facialStateAux(result);
        const lines = Array.isArray(face?.evidence_summary) ? face.evidence_summary : [];
        return lines.map((line: any) => String(line || '')).filter(Boolean).slice(0, 5);
    }
    public facialStateItems(result?: any): any[] {
        const face = this.facialStateAux(result);
        if (!face) return [];
        const pct = (value: any) => Math.max(0, Math.min(100, Math.round(Number(value || 0) * 100)));
        if (face.reason === 'face_not_detected' || face.face_visible === false || (!face.face_detected && Number(face.pose_head_roi_ratio || 0) >= 0.5)) {
            return [
                { key: 'actual_face', label: '실제얼굴', percent: pct(face.actual_face_ratio), active: false, color: '#94a3b8' },
                { key: 'pose_fallback', label: 'pose대체', percent: pct(face.pose_head_roi_ratio), active: Number(face.pose_head_roi_ratio || 0) > 0, color: '#64748b' },
                { key: 'emotion_skip', label: '감정미사용', percent: 100, active: false, color: '#71717a' },
            ];
        }
        const emotionColors: Record<string, string> = {
            neutral: '#64748b',
            happiness: '#14b8a6',
            embarrassed: '#f59e0b',
            surprise: '#f59e0b',
            anxiety: '#a855f7',
            distress: '#f43f5e',
            non_distress: '#64748b',
            hurt: '#e11d48',
            sadness: '#6366f1',
            anger: '#ef4444',
            disgust: '#84cc16',
            fear: '#a855f7',
            contempt: '#f97316',
        };
        const probs = face.emotion_probs || {};
        const driverProbs = face.driver_state_probs || {};
        const showEmotionCandidates = Boolean(face.emotion_reliable) || Number(face.support_score || 0) > 0;
        const emotionItems = (showEmotionCandidates ? Object.keys(probs) : [])
            .map((key: string) => ({
                key,
                label: this.facialEmotionLabel(key),
                percent: pct(probs[key]),
                active: key === face.emotion_top && Boolean(face.emotion_reliable),
                color: emotionColors[key] || '#71717a',
            }))
            .sort((a: any, b: any) => b.percent - a.percent)
            .slice(0, 3);
        if (emotionItems.length > 0) {
            emotionItems.push({
                key: 'quality',
                label: '모델신뢰',
                percent: face.emotion_quality === 'high' ? 90 : (face.emotion_quality === 'medium' ? 62 : 28),
                active: Boolean(face.emotion_reliable),
                color: face.emotion_reliable ? '#0ea5e9' : '#94a3b8',
            });
            emotionItems.push({
                key: 'distress',
                label: '신뢰보정 불편',
                percent: pct(face.trusted_distress_score ?? face.distress_score),
                active: Number(face.trusted_distress_score ?? face.distress_score ?? 0) >= 0.30,
                color: '#f43f5e',
            });
            if (Object.keys(driverProbs).length > 0) {
                emotionItems.push({
                    key: 'driver_state',
                    label: `상태 ${face.driver_state_top_label || this.facialDriverStateLabel(face.driver_state_top)}`,
                    percent: pct(face.driver_state_risk),
                    active: Boolean(face.driver_state_reliable) && Number(face.driver_state_risk || 0) >= 0.35,
                    color: '#0ea5e9',
                });
            }
            emotionItems.push({
                key: 'face',
                label: '실제얼굴',
                percent: pct(face.actual_face_ratio ?? face.facial_confidence),
                active: Number(face.actual_face_ratio || 0) >= 0.50,
                color: '#22d3ee',
            });
            return emotionItems;
        }
        const items: any[] = [
            { key: 'face', label: '얼굴', percent: face.face_detected ? pct(face.facial_confidence) : 0, active: Boolean(face.face_detected), color: '#22d3ee' },
            { key: 'calm', label: '평온/차분', percent: Number(face.support_score || 0) > 0 ? 0 : 100, active: Number(face.support_score || 0) <= 0, color: '#14b8a6' },
            { key: 'distress', label: '신뢰보정 불편', percent: pct(face.support_score), active: Number(face.support_score || 0) > 0, color: '#f59e0b' },
            { key: 'driver_state', label: `상태 ${face.driver_state_top_label || this.facialDriverStateLabel(face.driver_state_top)}`, percent: pct(face.driver_state_risk), active: Number(face.driver_state_risk || 0) >= 0.35, color: '#0ea5e9' },
            { key: 'eyes', label: '눈감김', percent: pct(face.eye_closed_ratio), active: Boolean(face.eye_closed), color: '#8b5cf6' },
            { key: 'mouth', label: '입/긴장', percent: Math.max(pct(face.mouth_open_ratio), pct(face.upper_tension_ratio)), active: Number(face.mouth_open_ratio || 0) > 0 || Number(face.upper_tension_ratio || 0) > 0, color: '#f43f5e' },
        ];
        if (!face.available && face.reason !== 'face_not_detected') {
            return [{ key: 'status', label: this.facialStateLabel(result), percent: 100, active: false, color: '#71717a' }];
        }
        return items;
    }
    public facialStateAuxClass(result?: any): string {
        const face = this.facialStateAux(result);
        if (face?.applied) return 'border-amber-200 bg-amber-50 text-amber-800';
        if (face?.available && Number(face?.support_score || 0) > 0) return 'border-sky-200 bg-sky-50 text-sky-800';
        return 'border-zinc-200 bg-zinc-50 text-zinc-600';
    }
    public isDualModeResult(result?: any): boolean { const res = result || this.analysisResult || {}; return ['rf-dual', 'rf-dual-person'].includes(res?.runtime_key || ''); }
    public rawPostureProbs(result?: any): Record<string, number> {
        const res = result || this.analysisResult || {};
        return res?.posture_candidate_probs || res?.runtime_inference?.posture_candidate_probs || res?.posture_raw_probs || res?.runtime_inference?.posture_raw_probs || res?.posture_probs || res?.runtime_inference?.posture_probs || {};
    }
    public isFinalNonFall(result?: any): boolean { const res = result || this.analysisResult || {}; return Boolean(res) && res?.fall_detected === false; }
    public topNonFallPostureCode(result?: any): string {
        const res = result || this.analysisResult || {};
        const direct = res?.posture_label || res?.runtime_inference?.posture_label || '';
        if (direct && direct !== 'fall' && direct !== 'unknown') return direct;
        const probs = this.displayPostureProbs(res);
        const entries = Object.entries(probs || {});
        if (entries.length === 0) return this.isFinalNonFall(res) ? 'stand' : (direct || 'unknown');
        entries.sort((a, b) => Number(b[1] || 0) - Number(a[1] || 0));
        return entries[0][0] || (this.isFinalNonFall(res) ? 'stand' : (direct || 'unknown'));
    }
    public displayPostureProbs(result?: any): Record<string, number> {
        const res = result || this.analysisResult || {};
        const direct = res?.posture_probs || res?.runtime_inference?.posture_probs || {};
        const directKeys = Object.keys(direct || {});
        const raw = this.rawPostureProbs(res);
        const positiveOnly = (source: Record<string, number>) => {
            const out: Record<string, number> = {};
            for (const [key, value] of Object.entries(source || {})) {
                if (key === 'unknown') continue;
                const num = Number(value || 0);
                if (Number.isFinite(num) && num > 0.0001) out[key] = num;
            }
            return out;
        };
        const normalizeWithoutFall = (source: Record<string, number>) => {
            const nonFallEntries = Object.entries(source || {}).filter(([key, value]) => key !== 'fall' && key !== 'unknown' && Number(value || 0) > 0.0001);
            const total = nonFallEntries.reduce((acc, [, value]) => acc + Number(value || 0), 0);
            if (total <= 0) return {} as Record<string, number>;
            const normalized: Record<string, number> = {};
            for (const [key, value] of nonFallEntries) normalized[key] = Number(value || 0) / total;
            return normalized;
        };
        if (directKeys.length > 0) {
            if (!this.isFinalNonFall(res)) return direct;
            if (directKeys.includes('fall')) {
                const normalized = normalizeWithoutFall(raw && Object.keys(raw).length > 0 ? raw : direct);
                return Object.keys(normalized).length > 0 ? normalized : direct;
            }
            const directPositive = positiveOnly(direct);
            if (Object.keys(directPositive).length > 0) return directPositive;
            const rawNormalized = normalizeWithoutFall(raw);
            if (Object.keys(rawNormalized).length > 0) return rawNormalized;
            return directPositive;
        }
        if (this.isFinalNonFall(res)) {
            const normalized = normalizeWithoutFall(raw);
            if (Object.keys(normalized).length > 0) return normalized;
        }
        return positiveOnly(raw);
    }
    public hasPostureData(result?: any): boolean { return Object.values(this.displayPostureProbs(result)).some((v: any) => Number(v || 0) > 0.0001); }
    public postureLabel(result?: any): string {
        const res = result || this.analysisResult || {};
        const direct = res?.posture_label || res?.runtime_inference?.posture_label || '';
        let code = direct;
        if (!code || (this.isFinalNonFall(res) && (code === 'fall' || code === 'unknown'))) code = this.topNonFallPostureCode(res);
        return this.POSTURE_LABEL_MAP[code] || this.POSTURE_LABEL_MAP['unknown'];
    }
    public postureDisplayCaption(): string { return this.isDualModeResult() ? '행동' : '자세'; }
    private postureDiagnostics(result?: any): any {
        const res = result || this.analysisResult || {};
        return res?.runtime_inference?.posture_diagnostics || {};
    }
    public postureDiagnosticText(result?: any): string {
        const res = result || this.analysisResult || {};
        const diag = this.postureDiagnostics(res);
        const reason = String(diag?.reason || '');
        const postureCode = res?.posture_label || res?.runtime_inference?.posture_label || '';
        if (!reason && postureCode !== 'unknown') return '';
        const pct = (value: any) => `${Math.round(Number(value || 0) * 100)}%`;
        if (diag?.description) {
            const bits = [];
            if (diag.avg_conf != null) bits.push(`포즈 ${pct(diag.avg_conf)}`);
            if (diag.lower_body_visibility != null) bits.push(`하반신 ${pct(diag.lower_body_visibility)}`);
            return `${diag.description}${bits.length ? ` (${bits.join(', ')})` : ''}`;
        }
        if (reason === 'low_pose_confidence') return `포즈 신뢰도(${pct(diag.avg_conf)}) 또는 하반신 검출률(${pct(diag.lower_body_visibility)})이 낮아 행동을 확정하지 않았습니다.`;
        if (reason === 'lie_evidence_too_weak') return `원 모델은 눕기에 기울었지만 전신 가로비, 직립 억제, 하반신 검출 조건이 부족해 미확인으로 표시했습니다.`;
        if (reason === 'low_margin') return `1순위와 2순위 행동 확률 차이가 작아 행동을 확정하지 않았습니다.`;
        if (reason === 'no_windows') return `행동분류에 사용할 유효 포즈 구간을 만들지 못했습니다.`;
        if (postureCode === 'unknown') return `행동분류 신뢰도가 낮아 실시간 기본 행동으로 추정 표시했습니다.`;
        return '';
    }
    public postureDisplayHint(): string {
        const diagnostic = this.postureDiagnosticText();
        if (diagnostic) return diagnostic;
        const raw = this.rawPostureProbs();
        const rawFall = Number(raw?.['fall'] || 0);
        if (this.isFinalNonFall() && rawFall > 0) return `raw 낙상 신호 ${Math.round(rawFall * 100)}%는 진단용 값이며, 표시는 비낙상 5-class 기준입니다.`;
        return '';
    }
    public decisionStateMeta(result?: any): any { const res = result || this.analysisResult || {}; const state = res?.decision_state || res?.runtime_inference?.decision_state || 'safe'; return this.DECISION_STATE_META[state] || this.DECISION_STATE_META['safe']; }
    public isAmbiguousDecision(result?: any): boolean { const res = result || this.analysisResult || {}; const state = res?.decision_state || res?.runtime_inference?.decision_state || ''; return state === 'uncertain' || state === 'fall_suspected'; }
    public postureItems(result?: any): any[] {
        const res = result || this.analysisResult || {};
        const probs = this.displayPostureProbs(res);
        const iconMap: Record<string, string> = { stand: '🧍', walk: '🚶', run: '🏃', sit: '🪑', lie: '🛌', fall: '⚠️' };
        const currentCode = this.topNonFallPostureCode(res);
        return Object.entries(probs).filter(([key, val]) => key !== 'unknown' && Number(val || 0) > 0.0001).map(([key, val]) => ({ code: key, key, label: this.POSTURE_LABEL_MAP[key] || key, icon: iconMap[key] || '❓', prob: Number(val || 0), percent: Math.round(Number(val || 0) * 100), score: Math.round(Number(val || 0) * 100), active: key === currentCode })).sort((a, b) => b.prob - a.prob);
    }
    public getExplainItems(): string[] { return this.analysisResult?.explain || []; }
    public getSuppressedBy(): string[] { return this.analysisResult?.runtime_inference?.suppressed_by || []; }
    public llmInterpretationText(): string {
        return String(this.analysisResult?.llm_interpretation?.text || '').trim();
    }
    public llmInterpretationStatus(): string {
        const llm = this.analysisResult?.llm_interpretation || {};
        if (llm?.status === 'generated') return `${llm.model || 'LLM'} 판독`;
        if (llm?.status === 'local_fast') return '로컬 빠른 근거 요약';
        if (llm?.status === 'queued') return 'LLM 판독 대기';
        if (llm?.status === 'cached') return `${llm.model || 'LLM'} 캐시 판독`;
        if (llm?.status === 'missing_api_key') return 'LLM API Key 필요';
        if (llm?.status === 'error') return `LLM 판독 실패: ${llm.error || '오류'}`;
        if (llm?.status === 'disabled') return 'LLM 판독 꺼짐';
        return '';
    }

    private numericTiming(value: any): number {
        const num = Number(value || 0);
        return Number.isFinite(num) ? num : 0;
    }

    public getUploadAnalysisSlowReason(): string {
        const st = this.analysisResult?.server_timing || {};
        if (!st) return '';
        const inference = this.numericTiming(st.inference_sec);
        const build = this.numericTiming(st.result_build_sec);
        const llm = this.numericTiming(st.llm_sec);
        const total = this.numericTiming(st.total_server_sec || st.response_ready_sec);
        if (llm >= 1 && llm >= inference * 0.5 && llm >= build * 0.5) {
            return `LLM 동기 판독이 ${llm.toFixed(2)}초 걸렸습니다. local_fast 또는 비동기 판독으로 낮출 수 있습니다.`;
        }
        if (inference >= build && inference >= 1) {
            return `주요 지연은 RF-Dual 영상 추론입니다. 추론 ${inference.toFixed(2)}초 / 전체 ${total.toFixed(2)}초입니다.`;
        }
        if (build >= 1) {
            return `주요 지연은 업로드 분할 로그와 결과 구성입니다. 결과 구성 ${build.toFixed(2)}초 / LLM ${llm.toFixed(2)}초입니다.`;
        }
        return `LLM ${llm.toFixed(2)}초, 전체 ${total.toFixed(2)}초로 병목은 크지 않습니다.`;
    }

    public getServerTimingDetail(): any[] {
        const st = this.analysisResult?.server_timing;
        if (!st) return [];
        return [
            { label: '파일 읽기', value: st.file_read_sec },
            { label: '파일 저장', value: st.file_save_sec },
            { label: '모델 로드', value: st.summary_load_sec },
            { label: 'RF-Dual 추론', value: st.inference_sec },
            { label: '분할 로그/결과', value: st.result_build_sec },
            { label: 'LLM 설명', value: st.llm_sec },
            { label: '알림 디스패치', value: st.alert_dispatch_sec },
            { label: '전체 응답', value: st.response_ready_sec },
        ].filter(i => i.value != null);
    }

    private startFeedbackTimer() {
        this.feedbackElapsedSec = 0;
        this.stopFeedbackTimer();
        this.feedbackTimerHandle = setInterval(async () => { this.feedbackElapsedSec++; await this.service.render(); }, 1000);
    }
    private stopFeedbackTimer() { if (this.feedbackTimerHandle) { clearInterval(this.feedbackTimerHandle); this.feedbackTimerHandle = null; } }

    public async submitAnalysisFeedback() {
        if (!this.feedbackStatus || !this.analysisSavedName) return;
        this.feedbackSubmitting = true;
        this.feedbackMessage = '';
        this.startFeedbackTimer();
        await this.service.render();
        try {
            const params: any = { saved_name: this.analysisSavedName, predicted_label: this.analysisResult?.fall_detected ? 'Y' : 'N', feedback_status: this.feedbackStatus, actual_label: this.feedbackActualLabel || '', note: this.feedbackNote || '', retrain: String(this.feedbackRetrainRequested), posture_class: this.feedbackPostureClass || '', predicted_posture: this.analysisResult?.posture_label || '', ambiguity_flag: String(this.feedbackAmbiguityFlag), occlusion_flag: String(this.feedbackOcclusionFlag), short_clip_flag: String(this.feedbackShortClipFlag) };
            const { code, data } = await wiz.call('submit_analysis_feedback', params);
            if (code === 200) {
                const elapsed = this.feedbackElapsedSec;
                this.feedbackMessage = data?.learning_message || `✅ 피드백 저장 완료 (${elapsed}초)`;
                this.feedbackMessageType = 'success';
                if (data?.auto_retrain_triggered || data?.manual_retrain_triggered || data?.auto_posture_retrain_triggered) {
                    this.feedbackRetrainDone = true;
                    this.feedbackMessage = data?.learning_message || `✅ 피드백 저장 + 재학습 완료 (${elapsed}초)`;
                }
            } else {
                this.feedbackMessage = data?.message || '피드백 저장 실패';
                this.feedbackMessageType = 'error';
            }
        } catch (e: any) {
            this.feedbackMessage = '오류: ' + (e.message || e);
            this.feedbackMessageType = 'error';
        }
        this.stopFeedbackTimer();
        this.feedbackSubmitting = false;
        await this.service.render();
    }
    public toggleFeedbackFlag(flag: string) { if (flag === 'ambiguity') this.feedbackAmbiguityFlag = !this.feedbackAmbiguityFlag; if (flag === 'occlusion') this.feedbackOcclusionFlag = !this.feedbackOcclusionFlag; if (flag === 'short_clip') this.feedbackShortClipFlag = !this.feedbackShortClipFlag; }

    private pushRealtimeLog(blob: Blob, chunkId: number, chunkWindow: any) {
        const key = this.realtimeWindowKey(chunkWindow);
        const duplicate = this.realtimeLogEntries.find((entry: any) => this.realtimeWindowKey(entry?.chunkWindow || {}) === key);
        if (duplicate) return;
        const blobUrl = URL.createObjectURL(blob);
        const postureRaw = this.analysisResult?.posture_label || this.analysisResult?.runtime_inference?.posture_label || '';
        const currentCode = postureRaw && postureRaw !== 'unknown' ? postureRaw : this.topNonFallPostureCode(this.analysisResult);
        const currentLabel = this.POSTURE_LABEL_MAP[currentCode] || currentCode || '';
        const changed = Boolean(this.currentPosture && currentCode && this.currentPosture !== currentCode);
        const behaviorTransition = {
            current_code: currentCode || '',
            current_label: currentLabel || '',
            previous_code: this.currentPosture || '',
            previous_label: this.currentPostureLabel || '',
            next_code: '',
            next_label: '',
            changed_from_previous: changed,
            changes_to_next: false,
            display_label: changed ? `${this.currentPostureLabel || this.currentPosture} → ${currentLabel || currentCode}` : (currentLabel || ''),
            context_label: changed ? `이전 ${this.currentPostureLabel || this.currentPosture} · 현재 ${currentLabel || currentCode}` : (currentLabel ? `현재 ${currentLabel}` : ''),
        };
        const entry = this.createLogEntry(this.analysisResult, { id: chunkId, blobUrl, elapsed: this.realtimeLastElapsed, basis: this.realtimeOverlayBasis || this.lastNonEmptyOverlayBasis || '', cumulativeScore: this.realtimeCumulativeScore, chunkWindow, chunkLabel: chunkWindow?.label || '', behaviorTransition });
        this.realtimeLogEntries.unshift(entry);
        if (this.realtimeLogEntries.length > 50) {
            const removed = this.realtimeLogEntries.pop();
            if (removed?.blobUrl) URL.revokeObjectURL(removed.blobUrl);
        }
        this.trackPostureTimeline(entry.posture, entry.currentPostureLabel || entry.postureLabel, this.analysisResult?.posture_score || 0, chunkId, entry.timestamp);
        this.scrollLogToBottom();
    }
    private scrollLogToBottom() { setTimeout(() => { const el = this.logScrollContainerRef?.nativeElement; if (el) el.scrollTo({ top: 0, behavior: 'smooth' }); }, 120); }
    private trackPostureTimeline(posture: string, label: string, score: number, chunkId: number, timestamp: string) {
        if (!posture || posture === 'unknown') return;
        this.postureTimeline.push({ time: timestamp, posture, label, score, chunkId });
        if (this.postureTimeline.length > 60) this.postureTimeline.shift();
        if (this.currentPosture && this.currentPosture !== posture) {
            this.postureTransitions.push({ time: timestamp, from: this.currentPosture, to: posture, fromLabel: this.currentPostureLabel || this.currentPosture, toLabel: label || posture });
            if (this.postureTransitions.length > 20) this.postureTransitions.shift();
            this.postureTransitionText = `${this.currentPostureLabel || this.currentPosture} → ${label || posture}`;
        } else this.postureTransitionText = '';
        this.currentPosture = posture;
        this.currentPostureLabel = label;
    }
    public recentPostureSummary(): { posture: string; label: string; count: number; pct: number }[] {
        const recent = this.postureTimeline.slice(-20);
        if (recent.length === 0) return [];
        const counts: Record<string, { label: string; count: number }> = {};
        for (const entry of recent) {
            if (!counts[entry.posture]) counts[entry.posture] = { label: entry.label, count: 0 };
            counts[entry.posture].count++;
        }
        return Object.entries(counts).map(([p, v]) => ({ posture: p, label: v.label, count: v.count, pct: Math.round((v.count / recent.length) * 100) })).sort((a, b) => b.count - a.count);
    }
    public isPostureFrequentChange(): boolean { if (this.postureTransitions.length < 3) return false; return this.postureTransitions.slice(-5).length >= 3; }
    public cleanupLogBlobUrls() { for (const entry of this.realtimeLogEntries) if (entry.blobUrl) URL.revokeObjectURL(entry.blobUrl); this.realtimeLogEntries = []; }
    public async clearAllLogs() { this.cleanupLogBlobUrls(); await this.service.render(); }

    public async openLogDetail(entry: any) {
        this.logDetailEntry = entry;
        this.logDetailOpen = true;
        this.logDetailVideoUrl = '';
        this.logDetailVideoLoading = false;
        this.logDetailVideoError = '';
        this.logDetailVideoRange = null;
        this.logDetailVideoMode = '';
        if (entry?.blobUrl) {
            this.logDetailVideoUrl = entry.blobUrl; this.logDetailVideoMode = 'blob';
        } else if (this.selectedVideoUrl) {
            this.logDetailVideoUrl = this.selectedVideoUrl; this.logDetailVideoMode = 'upload';
            const startSec = Number(entry?.chunkWindow?.start_sec ?? entry?.chunkWindow?.startSec ?? 0);
            const endSecRaw = Number(entry?.chunkWindow?.end_sec ?? entry?.chunkWindow?.endSec ?? startSec);
            this.logDetailVideoRange = { startSec: Math.max(0, startSec), endSec: Math.max(Math.max(0, startSec), endSecRaw) };
        } else if (this.analysisSavedName) {
            this.logDetailVideoLoading = true; this.logDetailVideoMode = 'upload';
            const startSec = Number(entry?.chunkWindow?.start_sec ?? entry?.chunkWindow?.startSec ?? 0);
            const endSecRaw = Number(entry?.chunkWindow?.end_sec ?? entry?.chunkWindow?.endSec ?? startSec);
            this.logDetailVideoRange = { startSec: Math.max(0, startSec), endSec: Math.max(Math.max(0, startSec), endSecRaw) };
            this.logDetailVideoUrl = `/wiz/api/page.dashboard/analysis_video?saved_name=${encodeURIComponent(this.analysisSavedName)}`;
        } else {
            this.logDetailVideoError = '부분 영상을 준비하지 못했습니다.';
        }
        this.logFeedbackStatus = ''; this.logFeedbackActualLabel = ''; this.logFeedbackPostureClass = ''; this.logFeedbackNote = ''; this.logFeedbackAmbiguityFlag = false; this.logFeedbackOcclusionFlag = false; this.logFeedbackShortClipFlag = false; this.logFeedbackRetrainRequested = false;
        await this.service.render();
    }
    public async closeLogDetail() {
        this.logDetailOpen = false; this.logDetailEntry = null; this.logDetailVideoUrl = ''; this.logDetailVideoLoading = false; this.logDetailVideoError = ''; this.logDetailVideoRange = null; this.logDetailVideoMode = '';
        await this.service.render();
    }
    public async onLogDetailVideoLoaded(videoEl?: HTMLVideoElement) {
        if (!this.logDetailOpen) return;
        if (videoEl && this.logDetailVideoMode === 'upload' && this.logDetailVideoRange) {
            try { videoEl.currentTime = this.logDetailVideoRange.startSec; } catch (e) { }
        }
        this.logDetailVideoLoading = false; this.logDetailVideoError = ''; await this.service.render();
    }
    public async onLogDetailVideoError() { if (!this.logDetailOpen) return; this.logDetailVideoLoading = false; this.logDetailVideoError = '부분 영상을 불러오지 못했습니다.'; await this.service.render(); }
    public onLogDetailVideoTimeUpdate(videoEl: HTMLVideoElement) {
        if (!videoEl || this.logDetailVideoMode !== 'upload' || !this.logDetailVideoRange) return;
        const endSec = Number(this.logDetailVideoRange.endSec || 0); const startSec = Number(this.logDetailVideoRange.startSec || 0);
        if (endSec > startSec && videoEl.currentTime >= endSec) { videoEl.pause(); try { videoEl.currentTime = startSec; } catch (e) { } }
    }
    public async deleteLogEntry(entry: any, event?: Event) {
        if (event) event.stopPropagation();
        const idx = this.realtimeLogEntries.indexOf(entry);
        if (idx >= 0) { if (entry.blobUrl) URL.revokeObjectURL(entry.blobUrl); this.realtimeLogEntries.splice(idx, 1); }
        const uploadIdx = this.uploadLogEntries.indexOf(entry);
        if (uploadIdx >= 0) this.uploadLogEntries.splice(uploadIdx, 1);
        if (this.logDetailEntry === entry) { this.logDetailOpen = false; this.logDetailEntry = null; this.logDetailVideoUrl = ''; this.logDetailVideoLoading = false; this.logDetailVideoError = ''; this.logDetailVideoRange = null; this.logDetailVideoMode = ''; }
        await this.service.render();
    }
    public logDetailRangeLabel(): string {
        const start = Number(this.logDetailEntry?.chunkWindow?.start_sec ?? this.logDetailEntry?.chunkWindow?.startSec ?? 0);
        const end = Number(this.logDetailEntry?.chunkWindow?.end_sec ?? this.logDetailEntry?.chunkWindow?.endSec ?? start);
        if (end <= start) return '';
        return `${this.formatChunkSecond(start)}s → ${this.formatChunkSecond(end)}s`;
    }
    public logRiskClass(level: string): string { if (level === 'high') return 'text-rose-500'; if (level === 'medium') return 'text-amber-500'; return 'text-emerald-500'; }
    public logRiskDotClass(level: string): string { if (level === 'high') return 'bg-rose-500'; if (level === 'medium') return 'bg-amber-500'; return 'bg-emerald-500'; }
    public chunkRiskLabel(entry: any): string {
        if (entry?.displayRiskLabel) return entry.displayRiskLabel;
        if (entry?.level === 'high') return '고위험';
        if (entry?.level === 'medium') return '주의';
        return '안정';
    }
    public async submitLogFeedback() {
        if (!this.logFeedbackStatus || !this.logDetailEntry) return;
        this.logFeedbackSubmitting = true;
        this.logFeedbackMessage = '';
        this.logFeedbackElapsedSec = 0;
        if (this.logFeedbackTimerHandle) clearInterval(this.logFeedbackTimerHandle);
        this.logFeedbackTimerHandle = setInterval(async () => { this.logFeedbackElapsedSec++; await this.service.render(); }, 1000);
        await this.service.render();
        try {
            const entry = this.logDetailEntry;
            const params: any = { saved_name: entry.result?.saved_name || '', predicted_label: entry.result?.fall_detected ? 'Y' : 'N', feedback_status: this.logFeedbackStatus, actual_label: this.logFeedbackActualLabel || '', note: this.logFeedbackNote || '', retrain: String(this.logFeedbackRetrainRequested), posture_class: this.logFeedbackPostureClass || '', predicted_posture: entry.result?.posture_label || '', ambiguity_flag: String(this.logFeedbackAmbiguityFlag), occlusion_flag: String(this.logFeedbackOcclusionFlag), short_clip_flag: String(this.logFeedbackShortClipFlag) };
            const { code, data } = await wiz.call('submit_analysis_feedback', params);
            if (code === 200) {
                entry.feedbackDone = true;
                const elapsed = this.logFeedbackElapsedSec;
                this.logFeedbackMessage = data?.learning_message || `✅ 피드백 저장 완료 (${elapsed}초)`;
                this.logFeedbackMessageType = 'success';
                if (data?.auto_retrain_triggered || data?.manual_retrain_triggered || data?.auto_posture_retrain_triggered) this.logFeedbackMessage = data?.learning_message || `✅ 피드백 저장 + 재학습 완료 (${elapsed}초)`;
            } else {
                this.logFeedbackMessage = data?.message || '저장 실패';
                this.logFeedbackMessageType = 'error';
            }
        } catch (e: any) {
            this.logFeedbackMessage = '오류: ' + (e.message || e);
            this.logFeedbackMessageType = 'error';
        }
        if (this.logFeedbackTimerHandle) { clearInterval(this.logFeedbackTimerHandle); this.logFeedbackTimerHandle = null; }
        this.logFeedbackSubmitting = false;
        await this.service.render();
    }
    public toggleLogFeedbackFlag(flag: string) { if (flag === 'ambiguity') this.logFeedbackAmbiguityFlag = !this.logFeedbackAmbiguityFlag; if (flag === 'occlusion') this.logFeedbackOcclusionFlag = !this.logFeedbackOcclusionFlag; if (flag === 'short_clip') this.logFeedbackShortClipFlag = !this.logFeedbackShortClipFlag; }
    public setLogFeedbackPostureClass(code: string) { this.logFeedbackPostureClass = this.logFeedbackPostureClass === code ? '' : code; }

    public getDetectionFrames(): any[] { return this.analysisResult?.model_runtime?.detection_frames || []; }
    public async toggleDetectionReplay() { if (this.detectionReplayPlaying) this.stopDetectionReplay(); else this.startDetectionReplay(); await this.service.render(); }
    private startDetectionReplay() {
        const frames = this.getDetectionFrames();
        if (frames.length === 0) return;
        this.detectionReplayPlaying = true; this.detectionReplayIndex = 0; this.drawDetectionFrame(0);
        this.detectionReplayTimer = setInterval(() => {
            this.detectionReplayIndex++;
            if (this.detectionReplayIndex >= frames.length) { this.stopDetectionReplay(); return; }
            this.drawDetectionFrame(this.detectionReplayIndex);
        }, 200);
    }
    public stopDetectionReplay() { this.detectionReplayPlaying = false; if (this.detectionReplayTimer) { clearInterval(this.detectionReplayTimer); this.detectionReplayTimer = null; } }
    public seekDetectionReplay(idx: number) { const frames = this.getDetectionFrames(); if (idx >= 0 && idx < frames.length) { this.detectionReplayIndex = idx; this.drawDetectionFrame(idx); } }
    private drawDetectionFrame(idx: number) {
        const frames = this.getDetectionFrames(); const frame = frames[idx]; if (!frame) return;
        const canvasEl = this.detCanvasRef?.nativeElement; if (!canvasEl) return;
        const ctx = canvasEl.getContext('2d'); if (!ctx) return;
        const rect = canvasEl.getBoundingClientRect(); if (rect.width > 0 && rect.height > 0) { canvasEl.width = rect.width; canvasEl.height = rect.height; }
        const vidW = this.analysisResult?.video_meta?.width || 1; const vidH = this.analysisResult?.video_meta?.height || 1;
        const videoEl = this.uploadPreviewVideoRef?.nativeElement;
        let offX = 0, offY = 0, scaleX: number, scaleY: number;
        if (videoEl && videoEl.videoWidth > 0) {
            const cr = this.getVideoContentRect(videoEl);
            offX = cr.x; offY = cr.y; scaleX = cr.w / vidW; scaleY = cr.h / vidH;
        } else { scaleX = canvasEl.width / vidW; scaleY = canvasEl.height / vidH; }
        ctx.clearRect(0, 0, canvasEl.width, canvasEl.height);
        const detections = frame.detections || [];
        for (const det of detections) {
            ctx.strokeStyle = '#22d3ee'; ctx.lineWidth = 2;
            const x = det.x1 * scaleX + offX; const y = det.y1 * scaleY + offY; const w = (det.x2 - det.x1) * scaleX; const h = (det.y2 - det.y1) * scaleY;
            ctx.strokeRect(x, y, w, h);
            ctx.fillStyle = '#22d3ee'; ctx.font = '10px sans-serif'; ctx.fillText(`${(det.conf * 100).toFixed(0)}%`, x, y - 4);
            const kps = det.keypoints;
            if (kps && kps.length >= 17) {
                for (const [i, j] of COCO_SKELETON_PAIRS) {
                    const a = kps[i], b = kps[j];
                    if (!this.cocoKeypointVisible(a, i) || !this.cocoKeypointVisible(b, j)) continue;
                    ctx.beginPath(); ctx.moveTo(a[0] * scaleX + offX, a[1] * scaleY + offY); ctx.lineTo(b[0] * scaleX + offX, b[1] * scaleY + offY); ctx.strokeStyle = COCO_KP_COLORS[i] || '#67e8f9'; ctx.lineWidth = 1.5; ctx.stroke();
                }
                for (let k = 0; k < Math.min(kps.length, 17); k++) {
                    const kp = kps[k];
                    if (!this.cocoKeypointVisible(kp, k)) continue;
                    ctx.beginPath(); ctx.arc(kp[0] * scaleX + offX, kp[1] * scaleY + offY, 3, 0, 2 * Math.PI); ctx.fillStyle = COCO_KP_COLORS[k] || '#67e8f9'; ctx.fill();
                }
            }
        }
    }
    private clearRealtimeServerDetectionOverlay() {
        const canvasEl = this.realtimeBboxCanvasRef?.nativeElement;
        if (!canvasEl) return;
        const ctx = canvasEl.getContext('2d');
        if (!ctx) return;
        ctx.clearRect(0, 0, canvasEl.width, canvasEl.height);
    }
    private drawRealtimeServerDetectionOverlay(result: any) {
        const frames = result?.model_runtime?.detection_frames || [];
        const frame = frames.length > 0 ? frames[frames.length - 1] : null;
        const canvasEl = this.realtimeBboxCanvasRef?.nativeElement;
        if (!canvasEl) return;
        const ctx = canvasEl.getContext('2d');
        if (!ctx) return;
        const rect = canvasEl.getBoundingClientRect();
        const targetW = Math.max(1, Math.round(rect.width || canvasEl.clientWidth || 1));
        const targetH = Math.max(1, Math.round(rect.height || canvasEl.clientHeight || 1));
        if (canvasEl.width !== targetW || canvasEl.height !== targetH) {
            canvasEl.width = targetW;
            canvasEl.height = targetH;
        }
        ctx.clearRect(0, 0, canvasEl.width, canvasEl.height);
        if (this.isSkeletonPrivacyMode()) return;
        if (!frame) return;
        const vidW = Number(result?.video_meta?.width || this.webcamVideoRef?.nativeElement?.videoWidth || 1);
        const vidH = Number(result?.video_meta?.height || this.webcamVideoRef?.nativeElement?.videoHeight || 1);
        const videoEl = this.webcamVideoRef?.nativeElement;
        let offX = 0, offY = 0, scaleX = canvasEl.width / Math.max(1, vidW), scaleY = canvasEl.height / Math.max(1, vidH);
        if (videoEl && videoEl.videoWidth > 0) {
            const cr = this.getVideoContentRect(videoEl);
            offX = cr.x; offY = cr.y; scaleX = cr.w / Math.max(1, vidW); scaleY = cr.h / Math.max(1, vidH);
        }
        const detections = frame.detections || [];
        for (const det of detections) {
            const labelColor = det?.is_primary ? '#22c55e' : '#22d3ee';
            const kps = det.keypoints;
            if (!kps || kps.length < 17) continue;
            for (const [i, j] of COCO_SKELETON_PAIRS) {
                const a = kps[i], b = kps[j];
                if (!this.cocoKeypointVisible(a, i) || !this.cocoKeypointVisible(b, j)) continue;
                ctx.beginPath();
                ctx.moveTo(Number(a[0] || 0) * scaleX + offX, Number(a[1] || 0) * scaleY + offY);
                ctx.lineTo(Number(b[0] || 0) * scaleX + offX, Number(b[1] || 0) * scaleY + offY);
                ctx.strokeStyle = det?.is_primary ? '#22c55e' : (COCO_KP_COLORS[i] || '#67e8f9');
                ctx.lineWidth = det?.is_primary ? 2.25 : 1.75;
                ctx.stroke();
            }
            for (let k = 0; k < Math.min(kps.length, 17); k++) {
                const kp = kps[k];
                if (!this.cocoKeypointVisible(kp, k)) continue;
                ctx.beginPath();
                ctx.arc(Number(kp[0] || 0) * scaleX + offX, Number(kp[1] || 0) * scaleY + offY, 3, 0, 2 * Math.PI);
                ctx.fillStyle = COCO_KP_COLORS[k] || '#67e8f9';
                ctx.fill();
            }
            if (det?.person_label) {
                const x = Number(det.x1 || 0) * scaleX + offX + 3;
                const y = Math.max(12, Number(det.y1 || 0) * scaleY + offY - 4);
                ctx.font = '11px sans-serif';
                ctx.fillStyle = labelColor;
                ctx.fillText(String(det.person_label), x, y);
            }
        }
    }
    private getVideoContentRect(videoEl: HTMLVideoElement): { x: number; y: number; w: number; h: number } {
        const rect = videoEl.getBoundingClientRect();
        const vw = videoEl.videoWidth || 1, vh = videoEl.videoHeight || 1;
        const containerAspect = rect.width / rect.height, videoAspect = vw / vh;
        let contentW: number; let contentH: number; let ox: number; let oy: number;
        if (videoAspect > containerAspect) { contentW = rect.width; contentH = rect.width / videoAspect; ox = 0; oy = (rect.height - contentH) / 2; }
        else { contentH = rect.height; contentW = rect.height * videoAspect; ox = (rect.width - contentW) / 2; oy = 0; }
        return { x: ox, y: oy, w: contentW, h: contentH };
    }
    public onUploadVideoTimeUpdate() {
        if (!this.analysisResult || this.detectionReplayPlaying) return;
        const videoEl = this.uploadPreviewVideoRef?.nativeElement; if (!videoEl) return;
        const currentTime = videoEl.currentTime;
        const frames = this.getDetectionFrames(); if (frames.length === 0) return;
        let bestIdx = 0, bestDiff = Math.abs((frames[0].time_sec || 0) - currentTime);
        for (let i = 1; i < frames.length; i++) {
            const diff = Math.abs((frames[i].time_sec || 0) - currentTime);
            if (diff < bestDiff) { bestDiff = diff; bestIdx = i; }
        }
        this.detectionReplayIndex = bestIdx; this.drawDetectionFrame(bestIdx);
    }
    public drawBboxesOnCanvas(canvas: HTMLCanvasElement, detections: any[], w: number, h: number) {
        const ctx = canvas.getContext('2d'); if (!ctx) return;
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        if (!this.bboxOverlayEnabled) return;
        for (const det of detections) {
            const color = det?.is_primary ? '#22c55e' : '#22d3ee';
            ctx.strokeStyle = color; ctx.lineWidth = det?.is_primary ? 2.5 : 2;
            ctx.strokeRect(det.x1 * w, det.y1 * h, (det.x2 - det.x1) * w, (det.y2 - det.y1) * h);
            if (det?.person_label) {
                ctx.fillStyle = color; ctx.font = '11px sans-serif';
                ctx.fillText(String(det.person_label), det.x1 * w + 3, Math.max(12, det.y1 * h - 4));
            }
        }
    }

    public async openRiskAlertWorkflow() {
        if (!this.analysisResult || !this.analysisSavedName) return;
        try {
            const params = { saved_name: this.analysisSavedName, risk_level: this.analysisResult.risk_level || 'low', risk_score: String(this.analysisResult.risk_score || 0), risk_label: this.analysisResult.risk_label || '', summary: this.analysisResult.summary || '', fall_detected: String(this.analysisResult.fall_detected || false) };
            const { code, data } = await wiz.call('dispatch_risk_alerts', params);
            if (code === 200) { this.alertWorkflow = data; if (data?.emergency?.popup_required) this.emergencyPopupOpen = true; }
        } catch (e) { }
        await this.service.render();
    }
    public closeEmergencyPopup() { this.emergencyPopupOpen = false; }
    public async openReferencePopup(sceneId: string) {
        this.referencePopupLoading = true; this.referencePopupOpen = true; await this.service.render();
        try {
            const { code, data } = await wiz.call('reference_preview_info', { scene_id: sceneId });
            if (code === 200) this.referencePopupData = data;
        } catch (e) { }
        this.referencePopupLoading = false;
        await this.service.render();
    }
    public closeReferencePopup() { this.referencePopupOpen = false; this.referencePopupData = null; }
    public goPipelinePage() { this.service.href('/pipeline'); }
    public goManualPage() { this.service.href('/manual'); }
    public goAdminPage() { this.service.href('/admin/analysis'); }
}

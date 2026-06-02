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

const MP_FRAME_INTERVAL_MS = 66; // ~15fps throttle

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
    public videoMeta: any = { duration: 0, width: 0, height: 0, fps: 0 };
    public analysisSavedName: string = '';
    public dragover: boolean = false;
    public analyzing: boolean = false;
    public uploadProgress: number = 0;
    public analysisResult: any = null;
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
    public trainingJobStarting: boolean = false;
    public trainingJobApplying: boolean = false;
    private trainingJobPollHandle: any = null;
    private continuousTrainingPollHandle: any = null;

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
    public kalmanFilters: { x: Kalman1D; y: Kalman1D; missCount: number }[] = [];
    private readonly KF_MAX_MISS: number = 15;
    private readonly KF_VIS_THRESHOLD: number = 0.15;

    public realtimeActive: boolean = false;
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
        if (backend?.version === 'dense-bootstrap-v2') {
            return {
                version: 'dense-bootstrap-v2',
                chunkSec: Number(backend?.steady_sec || 4),
                spawnMs: Number(backend?.spawn_ms || 4000),
                maxSlots: Number(backend?.max_slots || 2),
                maxQueue: Number(backend?.max_queue || 120),
                bootstrapDurations: Array.isArray(backend?.dense_intro) ? backend.dense_intro.map((v: any) => Number(v || 0)).filter((v: number) => v > 0) : [],
                strideSec: Number(backend?.stride_sec || 4),
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
        try {
            return JSON.parse(text);
        } catch (e) {
            const normalized = text.replace(/([:\[,]\s*)(?:NaN|-?Infinity)(?=\s*[,}\]])/g, (_match, prefix) => `${prefix}0`);
            if (normalized !== text) return JSON.parse(normalized);
            throw e;
        }
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
            level: result?.risk_level || 'low',
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
        await this.service.init();
        this.restorePrivacyViewMode();
        await this.loadPrototypeInfo();
        await this.loadContinuousTrainingStatus();
        this.startContinuousTrainingPolling();
        if (this.inputMode === 'webcam') await this.ensureWebcamReady();
        try {
            const saved = localStorage.getItem(LAST_ANALYSIS_STORAGE_KEY);
            if (saved && this.inputMode === 'upload') {
                this.analysisResult = JSON.parse(saved);
                this.analysisSavedName = this.analysisResult?.saved_name || '';
                this.alertWorkflow = this.analysisResult?.alert_workflow || null;
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
            if (code === 200) this.prototypeInfo = data;
            else this.errorMessage = data?.message || '프로토타입 정보를 불러오지 못했습니다.';
        } catch (e: any) {
            this.errorMessage = e?.message || '프로토타입 정보를 불러오지 못했습니다.';
        }
        this.continuousTrainingStatus = this.prototypeInfo?.continuous_training?.aihub82 || this.continuousTrainingStatus;
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
        this.analysisResult = null;
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
                numPoses: 1,
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
    }

    private initKalmanFilters() {
        this.kalmanFilters = [];
        for (let i = 0; i < 33; i++) this.kalmanFilters.push({ x: new Kalman1D(), y: new Kalman1D(), missCount: 0 });
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

    private drawMpPose() {
        if (this.mpProcessing || !this.poseLandmarker) return;
        const videoEl = this.webcamVideoRef?.nativeElement;
        if (!videoEl || videoEl.readyState < 2) return;
        if (document.hidden) return;
        const canvasEl = this._mpPoseCanvasEl?.nativeElement || document.querySelector('[data-mp-pose-canvas]') as HTMLCanvasElement;
        if (!canvasEl) return;
        const ctx = canvasEl.getContext('2d');
        if (!ctx) return;
        if (canvasEl.width === 0 || canvasEl.height === 0) {
            canvasEl.width = videoEl.videoWidth || videoEl.clientWidth;
            canvasEl.height = videoEl.videoHeight || videoEl.clientHeight;
        }
        this.mpProcessing = true;
        try {
            const mpInput = this.getMediaPipeInputSource(videoEl);
            const result = this.poseLandmarker.detectForVideo(mpInput, performance.now());
            ctx.clearRect(0, 0, canvasEl.width, canvasEl.height);
            if (result.landmarks && result.landmarks.length > 0) {
                const landmarks = result.landmarks[0];
                const displayRect = this.getVideoContentRect(videoEl);
                const offX = displayRect.x; const offY = displayRect.y;
                const w = displayRect.w; const h = displayRect.h;
                if (this.kalmanFilters.length === 0) this.initKalmanFilters();
                const pts: { x: number; y: number; predicted: boolean; valid: boolean }[] = [];
                for (let k = 0; k < landmarks.length; k++) {
                    const lm = landmarks[k];
                    const vis = (lm.visibility ?? 0) >= this.KF_VIS_THRESHOLD;
                    const kf = this.kalmanFilters[k];
                    const p = this.normalizeMediaPipePoint(lm);
                    if (!kf) { pts.push({ x: p.x, y: p.y, predicted: false, valid: vis }); continue; }
                    kf.x.predict(); kf.y.predict();
                    if (vis) {
                        const fx = kf.x.update(p.x); const fy = kf.y.update(p.y); kf.missCount = 0; pts.push({ x: fx, y: fy, predicted: false, valid: true });
                    } else {
                        kf.missCount++;
                        if (kf.x.initialized && kf.missCount < this.KF_MAX_MISS) pts.push({ x: kf.x.position, y: kf.y.position, predicted: true, valid: true });
                        else pts.push({ x: 0, y: 0, predicted: false, valid: false });
                    }
                }
                for (const [i, j] of MP_POSE_CONNECTIONS) {
                    const a = pts[i], b = pts[j];
                    if (!a?.valid || !b?.valid) continue;
                    const pred = a.predicted || b.predicted;
                    ctx.beginPath(); ctx.moveTo(offX + a.x * w, offY + a.y * h); ctx.lineTo(offX + b.x * w, offY + b.y * h);
                    ctx.strokeStyle = this.colorWithAlpha(MP_LANDMARK_COLORS[i] || '#67e8f9', pred ? 0.3 : 0.9);
                    ctx.lineWidth = pred ? 1 : 2; ctx.setLineDash(pred ? [4, 4] : []); ctx.stroke();
                }
                ctx.setLineDash([]);
                for (let k = 0; k < pts.length; k++) {
                    const pt = pts[k];
                    if (!pt.valid) continue;
                    ctx.beginPath(); ctx.arc(offX + pt.x * w, offY + pt.y * h, pt.predicted ? 2 : 3, 0, 2 * Math.PI);
                    if (pt.predicted) { ctx.strokeStyle = this.colorWithAlpha(MP_LANDMARK_COLORS[k] || '#67e8f9', 0.5); ctx.lineWidth = 1; ctx.stroke(); }
                    else { ctx.fillStyle = MP_LANDMARK_COLORS[k] || '#67e8f9'; ctx.fill(); }
                }
            } else if (this.kalmanFilters.length > 0) {
                for (const kf of this.kalmanFilters) { kf.x.predict(); kf.y.predict(); kf.missCount++; }
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
        if (this.realtimeActive || !this.webcamStream) return;
        this.realtimePerfStats = { avgRtt: 0, avgServer: 0, currentInterval: 0, discarded: 0, queued: 0, retrying: 0, failed: 0 };
        await this.warmupRealtimeModels();
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
        this.dispatchQueue = []; this.dispatchQueueSize = 0; this.dispatchWorkerRunning = false; this.nextSlotId = 0; this.recorderSlots = []; this.errorMessage = '';
        await this.service.render();
        const chunkCfg = this.getChunkConfig();
        if (chunkCfg.bootstrapDurations.length > 0) for (const durationSec of chunkCfg.bootstrapDurations) this.spawnRecorderSlot(durationSec);
        else this.spawnRecorderSlot(chunkCfg.chunkSec);
        this.recorderSpawnTimer = setInterval(() => { if (!this.realtimeActive) return; this.spawnRecorderSlot(chunkCfg.chunkSec); }, chunkCfg.spawnMs);
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

    private enqueueChunk(blob: Blob, chunkId: number, durationSec: number, chunkWindow: any) {
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
            if (!ok && this.realtimeActive) {
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
        this.realtimeActive = false; this.realtimeSessionId = ''; this.realtimeSessionStartedAt = 0;
        if (this.recorderSpawnTimer) { clearInterval(this.recorderSpawnTimer); this.recorderSpawnTimer = null; }
        for (const slot of this.recorderSlots) {
            if (slot.timer) clearTimeout(slot.timer);
            if (slot.recorder.state === 'recording') { try { slot.recorder.stop(); } catch (e) { } }
        }
        this.recorderSlots = []; this.dispatchQueue = []; this.dispatchQueueSize = 0;
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
                this.analysisResult = result;
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
        this.realtimeOverlayScore = Math.round(this.realtimeCumulativeScore * 100);
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

    private async setSelectedUploadFiles(files: File[]) {
        const cleanFiles = (files || []).filter(Boolean);
        if (cleanFiles.length === 0) return;
        this.revokeSelectedVideoUrl();
        this.selectedFiles = cleanFiles;
        const firstVideo = cleanFiles.find(file => this.isUploadVideoFile(file)) || null;
        this.selectedFile = firstVideo;
        this.selectedVideoUrl = firstVideo ? URL.createObjectURL(firstVideo) : '';
        this.analysisResult = null;
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

    public selectedUploadTrainingHint(): string {
        if (this.selectedUploadCount() === 0) return '영상 여러 개 또는 zip/tar 압축 파일을 한 번에 선택할 수 있습니다.';
        if (!this.selectedFile) return '압축 파일은 학습 등록만 가능하고, 분석 미리보기는 영상 파일에서만 동작합니다.';
        if (this.selectedUploadCount() > 1) return '분석은 첫 번째 영상으로 실행하고, 학습 등록은 선택된 전체 파일을 순차 저장합니다.';
        return '선택한 영상을 분석하거나 학습 데이터로 등록할 수 있습니다.';
    }

    public async analyze() {
        if (!this.selectedFile || this.analyzing) {
            if (!this.selectedFile && this.selectedUploadCount() > 0) this.errorMessage = '분석은 영상 파일 하나가 필요합니다. 압축 파일은 학습 데이터 등록으로 처리해주세요.';
            return;
        }
        this.analyzing = true;
        this.analysisResult = null;
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
                this.analysisResult = json.data;
                this.analysisSavedName = json.data.saved_name || '';
                this.alertWorkflow = json.data.alert_workflow || null;
                this.syncUploadChunkLogs(json.data);
                localStorage.setItem(LAST_ANALYSIS_STORAGE_KEY, JSON.stringify(json.data));
            } else {
                this.errorMessage = json.data?.message || '분석 실패';
            }
        } catch (e: any) {
            this.errorMessage = '요청 오류: ' + (e.message || e);
        }
        this.analyzing = false;
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
                this.trainingUploadMessage = `학습 데이터 등록 완료: 파일 ${files.length}개, 영상 ${savedTotal}건 · 라벨 ${this.trainingUploadLabel || 'N'}${postureSaved}`;
                this.trainingUploadMessageType = 'success';
                this.trainingUploadNote = '';
            } else {
                this.trainingUploadMessage = `일부 등록 실패: 저장 ${savedTotal}건, 실패 ${errors.length}건 · ${errors.slice(0, 2).join(' / ')}`;
                this.trainingUploadMessageType = savedTotal > 0 ? 'success' : 'error';
            }
        } catch (e: any) {
            this.trainingUploadMessage = '요청 오류: ' + (e.message || e);
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
        this.continuousTrainingPollHandle = setInterval(() => { this.loadContinuousTrainingStatus(false); }, 600000);
    }

    public async loadContinuousTrainingStatus(render: boolean = true) {
        try {
            const res = await fetch('/wiz/api/page.dashboard/continuous_training_status?name=aihub82');
            const json = await this.readJsonResponse(res);
            if (json.code === 200 && json.data) {
                this.continuousTrainingStatus = json.data;
                if (this.prototypeInfo) {
                    this.prototypeInfo.continuous_training = this.prototypeInfo.continuous_training || {};
                    this.prototypeInfo.continuous_training.aihub82 = json.data;
                }
            }
        } catch (e) { }
        if (render) await this.service.render();
    }

    public async startBackgroundTraining(jobType: string = 'full') {
        if (this.trainingJobStarting) return;
        this.trainingJobStarting = true;
        this.trainingUploadMessage = '백그라운드 학습 job을 시작합니다.';
        this.trainingUploadMessageType = 'info';
        await this.service.render();
        try {
            const params = new URLSearchParams();
            params.set('job_type', jobType || 'full');
            params.set('apply_mode', 'manual');
            params.set('note', this.trainingUploadNote || '');
            const res = await fetch(`/wiz/api/page.dashboard/start_training_job?${params.toString()}`, { method: 'POST' });
            const json = await this.readJsonResponse(res);
            if (json.code === 200 && json.data) {
                this.trainingJob = json.data;
                this.trainingUploadMessage = `학습 job 시작: ${json.data.job_id || ''}`;
                this.trainingUploadMessageType = 'success';
                this.startTrainingJobPolling();
            } else {
                this.trainingUploadMessage = json.data?.message || '학습 job 시작 실패';
                this.trainingUploadMessageType = 'error';
            }
        } catch (e: any) {
            this.trainingUploadMessage = '학습 job 요청 오류: ' + (e.message || e);
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
                if (!['queued', 'running'].includes(status)) this.stopTrainingJobPolling();
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
            this.trainingUploadMessage = '학습 적용 오류: ' + (e.message || e);
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
        if (status === 'applied') return '적용 완료';
        if (status === 'failed') return '실패';
        return status || '상태 없음';
    }

    public trainingJobEtaText(): string {
        const eta = Number(this.trainingJob?.eta_sec);
        if (!Number.isFinite(eta) || eta <= 0) return '계산 중';
        if (eta < 60) return `${Math.round(eta)}초`;
        const min = Math.floor(eta / 60);
        const sec = Math.round(eta % 60);
        return `${min}분 ${sec}초`;
    }

    public trainingJobCanApply(): boolean {
        return this.trainingJob?.status === 'completed_pending_apply';
    }

    public continuousTrainingStageText(): string {
        const status = this.continuousTrainingStatus || {};
        const stage = String(status.stage || status.status || '');
        if (stage === 'running') return '82번 표정 모델 학습 중';
        if (stage === 'completed') return status.promoted ? '성능 개선 적용 완료' : '후보 검증 완료';
        if (stage === 'failed') return '후보 학습 실패';
        if (stage === 'already-running') return '이미 실행 중';
        if (stage === 'not-started' || stage === 'missing') return '대기 중';
        return stage || '상태 확인 중';
    }

    public continuousTrainingMetricText(): string {
        const active = Number(this.continuousTrainingStatus?.active_macro_f1 || 0);
        const candidate = Number(this.continuousTrainingStatus?.candidate_macro_f1 || 0);
        const activeText = active > 0 ? `active macro F1 ${(active * 100).toFixed(1)}%` : 'active F1 확인 중';
        return candidate > 0 ? `${activeText} · candidate ${(candidate * 100).toFixed(1)}%` : activeText;
    }

    public continuousTrainingUpdatedText(): string {
        return String(this.continuousTrainingStatus?.updated_at || '-');
    }

    public clearSelectedFile() {
        this.revokeSelectedVideoUrl();
        this.selectedFile = null;
        this.selectedFiles = [];
        this.analysisResult = null;
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
        if (key === 'person-feature-runtime') return 'XGBoost v2 (사람 추적)';
        if (key === 'rf-pipeline-runtime') return 'RF 보조 (RandomForest)';
        if (key === 'rf-dual') return 'RF-Dual (Fall+Posture)';
        if (key === 'heuristic-fallback') return '휴리스틱 Fallback';
        const runtimeLabel = this.prototypeInfo?.analysis_engine_summary?.current_runtime?.label || '';
        if (runtimeLabel) return runtimeLabel;
        if (this.selectedModelType === 'rf-dual') {
            return this.prototypeInfo?.trained_model?.runtime_ready ? 'RF-Dual (Fall+Posture)' : '모델 없음 (Fallback)';
        }
        return key || '알 수 없음';
    }
    public currentModelStatusLabel(): string {
        if (this.analysisResult?.runtime_key === 'heuristic-fallback') return 'fallback';
        return this.prototypeInfo?.trained_model?.runtime_ready ? 'ready' : 'missing';
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
        if (key === 'rf-dual') return 'RF predict_proba → motion guard → XG-Posture 5-class';
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
        const distress = Math.round(Number(face.trusted_distress_score ?? face.distress_score ?? 0) * 100);
        const faceRatio = Math.round(Number(face.actual_face_ratio || 0) * 100);
        const driver = face.driver_state_top_label || this.facialDriverStateLabel(face.driver_state_top);
        const driverConfidence = Math.round(Number(face.driver_state_confidence || 0) * 100);
        const driverRisk = Math.round(Number(face.driver_state_risk || 0) * 100);
        const suffix = face.emotion_top && face.emotion_top !== 'unavailable'
            ? `${emotion} · top ${emotionConfidence}% · margin ${emotionMargin}% · 일치 ${emotionConsistency}% · 신뢰 ${quality} · 보정불편 ${distress}% · 실제얼굴 ${faceRatio}%`
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
            hurt: '#e11d48',
            sadness: '#6366f1',
            anger: '#ef4444',
            disgust: '#84cc16',
            fear: '#a855f7',
            contempt: '#f97316',
        };
        const probs = face.emotion_probs || {};
        const driverProbs = face.driver_state_probs || {};
        const showEmotionCandidates = Boolean(face.emotion_reliable) || Number(face.actual_face_ratio || 0) >= 0.50;
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
                label: '보정불편',
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
            { key: 'distress', label: '불편', percent: pct(face.support_score), active: Number(face.support_score || 0) > 0, color: '#f59e0b' },
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
    public isDualModeResult(result?: any): boolean { const res = result || this.analysisResult || {}; return (res?.runtime_key || '') === 'rf-dual'; }
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
        if (llm?.status === 'queued') return 'LLM 판독 대기';
        if (llm?.status === 'cached') return `${llm.model || 'LLM'} 캐시 판독`;
        if (llm?.status === 'missing_api_key') return 'LLM API Key 필요';
        if (llm?.status === 'error') return `LLM 판독 실패: ${llm.error || '오류'}`;
        if (llm?.status === 'disabled') return 'LLM 판독 꺼짐';
        return '';
    }

    public getServerTimingDetail(): any[] {
        const st = this.analysisResult?.server_timing;
        if (!st) return [];
        return [
            { label: '파일 읽기', value: st.file_read_sec },
            { label: '파일 저장', value: st.file_save_sec },
            { label: '모델 로드', value: st.summary_load_sec },
            { label: '추론', value: st.inference_sec },
            { label: '결과 구성', value: st.result_build_sec },
            { label: '알림 디스패치', value: st.alert_dispatch_sec },
            { label: '응답 준비', value: st.response_ready_sec },
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
                    if (!a || !b || a[2] < 0.3 || b[2] < 0.3) continue;
                    ctx.beginPath(); ctx.moveTo(a[0] * scaleX + offX, a[1] * scaleY + offY); ctx.lineTo(b[0] * scaleX + offX, b[1] * scaleY + offY); ctx.strokeStyle = COCO_KP_COLORS[i] || '#67e8f9'; ctx.lineWidth = 1.5; ctx.stroke();
                }
                for (let k = 0; k < Math.min(kps.length, 17); k++) {
                    const kp = kps[k];
                    if (!kp || kp[2] < 0.3) continue;
                    ctx.beginPath(); ctx.arc(kp[0] * scaleX + offX, kp[1] * scaleY + offY, 3, 0, 2 * Math.PI); ctx.fillStyle = COCO_KP_COLORS[k] || '#67e8f9'; ctx.fill();
                }
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
        for (const det of detections) { ctx.strokeStyle = '#22d3ee'; ctx.lineWidth = 2; ctx.strokeRect(det.x1 * w, det.y1 * h, (det.x2 - det.x1) * w, (det.y2 - det.y1) * h); }
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

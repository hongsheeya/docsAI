/// <reference path="../../types/wiz-view-modules.d.ts" />

import { OnDestroy, OnInit, ViewChild, ElementRef } from '@angular/core';
import { Service } from '@wiz/libs/portal/season/service';
import { PoseLandmarker, FilesetResolver, DrawingUtils } from '@mediapipe/tasks-vision';

declare const wiz: any;

const LAST_ANALYSIS_STORAGE_KEY = 'fallai:last-analysis';

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

const MP_FRAME_INTERVAL_MS = 83; // ~12fps throttle

export class Component implements OnInit, OnDestroy {
    // ── System ──
    public prototypeInfo: any = null;
    public inputMode: string = 'webcam';
    public analysisProfile: string = 'balanced';
    public selectedModelType: string = 'person-feature';
    public loadingInfo: boolean = true;

    // ── Upload mode ──
    public selectedFile: File | null = null;
    public selectedVideoUrl: string = '';
    public videoMeta: any = { duration: 0, width: 0, height: 0, fps: 0 };
    public analysisSavedName: string = '';
    public dragover: boolean = false;
    public analyzing: boolean = false;
    public uploadProgress: number = 0;
    public analysisResult: any = null;
    public errorMessage: string = '';

    // ── Feedback (2-Level HITL) ──
    public feedbackStatus: string = '';
    public feedbackActualLabel: string = '';
    public feedbackPostureClass: string = '';
    public feedbackNote: string = '';
    public feedbackSubmitting: boolean = false;
    public feedbackRetrainDone: boolean = false;
    public feedbackMessage: string = '';
    public feedbackMessageType: string = 'info';
    public feedbackAmbiguityFlag: boolean = false;
    public feedbackOcclusionFlag: boolean = false;
    public feedbackShortClipFlag: boolean = false;

    public postureClasses = [
        { code: 'stand', label: '서기', icon: '🧍' },
        { code: 'walk', label: '걷기', icon: '🚶' },
        { code: 'sit', label: '앉기', icon: '🪑' },
        { code: 'run', label: '뛰기', icon: '🏃' },
        { code: 'lie', label: '눕기', icon: '🛌' },
        { code: 'fall', label: '낙상', icon: '⚠️' },
    ];

    // ── Webcam ──
    public webcamStream: MediaStream | null = null;
    public webcamReady: boolean = false;
    public webcamError: string = '';
    public webcamZoom: number = 1.0;

    // ── MediaPipe Pose ──
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

    // ── Realtime analysis ──
    public realtimeActive: boolean = false;
    public realtimeChunkCount: number = 0;
    public realtimeCumulativeScore: number = 0;
    public realtimeScoreHistory: number[] = [];
    public realtimeIntervalSec: number = 5;
    public realtimeOverlapSec: number = 4;
    public realtimeLastElapsed: number = 0;
    public realtimePendingConfirmation: boolean = false;
    public mediaRecorder: MediaRecorder | null = null;
    public mediaRecorderChunks: Blob[] = [];
    public realtimeTimer: any = null;
    public realtimeDispatching: boolean = false;

    // ── Realtime overlay ──
    public realtimeOverlayScore: number = 0;
    public realtimeOverlayLevel: string = 'low';
    public realtimeOverlayLabel: string = '대기';
    public realtimeOverlayBasis: string = '';
    public realtimeOverlayRuntime: string = '';
    public realtimeOverlayFlash: boolean = false;
    public realtimeOverlayFlashTimer: any = null;
    public lastNonEmptyOverlayBasis: string = '';

    // ── Realtime log ──
    public realtimeLogEntries: any[] = [];
    public logDetailOpen: boolean = false;
    public logDetailEntry: any = null;
    public logFeedbackStatus: string = '';
    public logFeedbackActualLabel: string = '';
    public logFeedbackPostureClass: string = '';
    public logFeedbackNote: string = '';
    public logFeedbackSubmitting: boolean = false;
    public logFeedbackAmbiguityFlag: boolean = false;
    public logFeedbackOcclusionFlag: boolean = false;
    public logFeedbackShortClipFlag: boolean = false;

    // ── Detection replay ──
    public detectionReplayPlaying: boolean = false;
    public detectionReplayIndex: number = 0;
    public detectionReplayTimer: any = null;

    // ── Bbox overlay ──
    public bboxOverlayEnabled: boolean = false;

    // ── Alert workflow ──
    public alertWorkflow: any = null;
    public emergencyPopupOpen: boolean = false;

    // ── Reference preview ──
    public referencePopupOpen: boolean = false;
    public referencePopupData: any = null;
    public referencePopupLoading: boolean = false;

    // ── Performance monitoring ──
    public realtimePerfStats: any = { avgRtt: 0, avgServer: 0, currentInterval: 0, discarded: 0 };
    public realtimeRoundTripHistory: number[] = [];
    public realtimeServerTimeHistory: number[] = [];
    public realtimeAdaptiveEnabled: boolean = false;

    // ── Constants ──
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

    // ── ViewChild refs ──
    @ViewChild('webcamVideo') webcamVideoRef!: ElementRef<HTMLVideoElement>;
    @ViewChild('mpPoseCanvas') set _mpPoseCanvasSetter(el: ElementRef<HTMLCanvasElement>) { this._mpPoseCanvasEl = el; }
    private _mpPoseCanvasEl: ElementRef<HTMLCanvasElement> | null = null;
    @ViewChild('realtimeBboxCanvas') realtimeBboxCanvasRef!: ElementRef<HTMLCanvasElement>;
    @ViewChild('uploadBboxCanvas') uploadBboxCanvasRef!: ElementRef<HTMLCanvasElement>;
    @ViewChild('uploadPreviewVideo') uploadPreviewVideoRef!: ElementRef<HTMLVideoElement>;
    @ViewChild('detCanvas') detCanvasRef!: ElementRef<HTMLCanvasElement>;
    @ViewChild('logScrollContainer') logScrollContainerRef!: ElementRef;

    constructor(public service: Service) { }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // Lifecycle
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    public async ngOnInit() {
        await this.service.init();
        await this.loadPrototypeInfo();
        if (this.inputMode === 'webcam') {
            await this.ensureWebcamReady();
        }
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

    public ngOnDestroy() {
        this.stopRealtimeAnalysis();
        this.stopWebcamStream();
        this.stopPoseLoop();
        this.stopDetectionReplay();
        if (this.realtimeOverlayFlashTimer) clearTimeout(this.realtimeOverlayFlashTimer);
        if (this.mpFpsTimer) clearInterval(this.mpFpsTimer);
        this.cleanupLogBlobUrls();
    }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // Prototype Info
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    public async loadPrototypeInfo() {
        this.loadingInfo = true;
        await this.service.render();
        try {
            const { code, data } = await wiz.call('prototype_info');
            if (code === 200) {
                this.prototypeInfo = data;
            }
        } catch (e) { }
        this.loadingInfo = false;
        await this.service.render();
    }

    public async saveAlertSettings(form: any) {
        try {
            const params: any = { action: 'save_alert_settings', ...form };
            const { code, data } = await wiz.call('prototype_info', params);
            if (code === 200 && data?.alert_settings) {
                this.prototypeInfo.alert_settings = data.alert_settings;
            }
        } catch (e) { }
        await this.service.render();
    }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // Input Mode
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    public async switchInputMode(mode: string) {
        if (this.inputMode === mode) return;
        this.inputMode = mode;
        this.errorMessage = '';
        this.analysisResult = null;
        this.feedbackStatus = '';
        this.feedbackMessage = '';
        if (mode === 'webcam') {
            await this.ensureWebcamReady();
        } else {
            this.stopRealtimeAnalysis();
        }
        await this.service.render();
    }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // Webcam Management
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    public async ensureWebcamReady() {
        if (this.webcamStream) { this.webcamReady = true; return; }
        this.webcamError = '';
        try {
            const constraints: any = {
                video: { facingMode: 'user', width: { ideal: 1280 }, height: { ideal: 720 } },
                audio: false
            };
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

    public async setWebcamHwZoom(zoom: number) {
        this.webcamZoom = zoom;
        try {
            const track = this.webcamStream?.getVideoTracks()[0];
            if (track) {
                const caps = track.getCapabilities() as any;
                if (caps.zoom) {
                    const clamped = Math.max(caps.zoom.min, Math.min(caps.zoom.max, zoom));
                    await track.applyConstraints({ advanced: [{ zoom: clamped } as any] });
                }
            }
        } catch (e) { }
        await this.service.render();
    }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // MediaPipe Pose
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    public async initMediaPipePose() {
        if (this.poseLandmarker || this.mpInitializing) return;
        this.mpInitializing = true;
        await this.service.render();
        try {
            const vision = await FilesetResolver.forVisionTasks(
                'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.34/wasm'
            );
            this.poseLandmarker = await PoseLandmarker.createFromOptions(vision, {
                baseOptions: {
                    modelAssetPath: 'https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task',
                    delegate: 'GPU'
                },
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
        this.mpFpsTimer = setInterval(() => { this.mpFps = this.mpFrameCount; this.mpFrameCount = 0; }, 1000);
        const canvasEl = this._mpPoseCanvasEl?.nativeElement
            || document.querySelector('[data-mp-pose-canvas]') as HTMLCanvasElement;
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
    }

    private drawMpPose() {
        if (this.mpProcessing || !this.poseLandmarker) return;
        const videoEl = this.webcamVideoRef?.nativeElement;
        if (!videoEl || videoEl.readyState < 2) return;
        const canvasEl = this._mpPoseCanvasEl?.nativeElement
            || document.querySelector('[data-mp-pose-canvas]') as HTMLCanvasElement;
        if (!canvasEl) return;
        const ctx = canvasEl.getContext('2d');
        if (!ctx) return;
        if (canvasEl.width === 0 || canvasEl.height === 0) {
            canvasEl.width = videoEl.videoWidth || videoEl.clientWidth;
            canvasEl.height = videoEl.videoHeight || videoEl.clientHeight;
        }
        this.mpProcessing = true;
        try {
            const result = this.poseLandmarker.detectForVideo(videoEl, performance.now());
            ctx.clearRect(0, 0, canvasEl.width, canvasEl.height);
            if (result.landmarks && result.landmarks.length > 0) {
                const landmarks = result.landmarks[0];
                const w = canvasEl.width, h = canvasEl.height;
                for (const [i, j] of MP_POSE_CONNECTIONS) {
                    const a = landmarks[i], b = landmarks[j];
                    if (!a || !b) continue;
                    const vis = Math.min(a.visibility ?? 0, b.visibility ?? 0);
                    if (vis < 0.15) continue;
                    ctx.beginPath();
                    ctx.moveTo(a.x * w, a.y * h);
                    ctx.lineTo(b.x * w, b.y * h);
                    ctx.strokeStyle = this.colorWithAlpha(MP_LANDMARK_COLORS[i] || '#67e8f9', vis > 0.5 ? 0.9 : 0.4);
                    ctx.lineWidth = vis > 0.5 ? 2 : 1;
                    ctx.setLineDash(vis > 0.5 ? [] : [4, 4]);
                    ctx.stroke();
                }
                ctx.setLineDash([]);
                for (let k = 0; k < landmarks.length; k++) {
                    const lm = landmarks[k];
                    if ((lm.visibility ?? 0) < 0.15) continue;
                    ctx.beginPath();
                    ctx.arc(lm.x * w, lm.y * h, 3, 0, 2 * Math.PI);
                    ctx.fillStyle = MP_LANDMARK_COLORS[k] || '#67e8f9';
                    ctx.fill();
                }
            }
            this.mpFrameCount++;
        } catch (e) { }
        this.mpProcessing = false;
    }

    private colorWithAlpha(hex: string, alpha: number): string {
        const r = parseInt(hex.slice(1, 3), 16);
        const g = parseInt(hex.slice(3, 5), 16);
        const b = parseInt(hex.slice(5, 7), 16);
        return `rgba(${r},${g},${b},${alpha})`;
    }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // Realtime Analysis
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    public async startRealtimeAnalysis() {
        if (this.realtimeActive || !this.webcamStream) return;
        this.realtimeActive = true;
        this.realtimeChunkCount = 0;
        this.realtimeScoreHistory = [];
        this.realtimeCumulativeScore = 0;
        this.realtimeLogEntries = [];
        this.realtimeLastElapsed = 0;
        this.realtimeOverlayScore = 0;
        this.realtimeOverlayLevel = 'low';
        this.realtimeOverlayLabel = '대기';
        this.realtimeOverlayBasis = '';
        this.lastNonEmptyOverlayBasis = '';
        this.realtimeRoundTripHistory = [];
        this.realtimeServerTimeHistory = [];
        this.realtimePerfStats = { avgRtt: 0, avgServer: 0, currentInterval: 0, discarded: 0 };
        this.errorMessage = '';
        await this.service.render();
        this.startNextRecording();
    }

    private startNextRecording() {
        if (!this.realtimeActive || !this.webcamStream) return;
        try {
            const mimeType = MediaRecorder.isTypeSupported('video/webm;codecs=vp8')
                ? 'video/webm;codecs=vp8' : 'video/webm';
            this.mediaRecorder = new MediaRecorder(this.webcamStream!, { mimeType });
            this.mediaRecorderChunks = [];
            this.mediaRecorder.ondataavailable = (e) => {
                if (e.data.size > 0) this.mediaRecorderChunks.push(e.data);
            };
            this.mediaRecorder.onstop = () => {
                if (!this.realtimeActive) return;
                const chunks = [...this.mediaRecorderChunks];
                const _chunkId = this.realtimeChunkCount++;
                if (chunks.length > 0) {
                    const blob = new Blob(chunks, { type: 'video/webm' });
                    this.dispatchRealtimeChunk(blob, _chunkId);
                }
                this.startNextRecording();
            };
            this.mediaRecorder.start(1000);
            this.realtimeTimer = setTimeout(() => {
                if (this.mediaRecorder && this.mediaRecorder.state === 'recording') {
                    this.mediaRecorder.stop();
                }
            }, this.realtimeIntervalSec * 1000);
        } catch (e: any) {
            this.errorMessage = '녹화 실패: ' + (e.message || e);
            this.realtimeActive = false;
            this.service.render();
        }
    }

    public async stopRealtimeAnalysis() {
        this.realtimeActive = false;
        if (this.realtimeTimer) { clearTimeout(this.realtimeTimer); this.realtimeTimer = null; }
        if (this.mediaRecorder && this.mediaRecorder.state === 'recording') {
            try { this.mediaRecorder.stop(); } catch (e) { }
        }
        this.mediaRecorder = null;
        this.mediaRecorderChunks = [];
        await this.service.render();
    }

    private async dispatchRealtimeChunk(blob: Blob, chunkId: number) {
        if (this.realtimeDispatching) {
            this.realtimePerfStats.discarded = (this.realtimePerfStats.discarded || 0) + 1;
            return;
        }
        this.realtimeDispatching = true;
        const startTime = performance.now();
        try {
            const fd = new FormData();
            fd.append('video', blob, `chunk_${chunkId}.webm`);
            fd.append('metadata', JSON.stringify({
                analysis_profile: this.analysisProfile,
                input_source: 'webcam-live',
                model_type: this.selectedModelType,
                duration: this.realtimeIntervalSec,
                chunk_id: chunkId,
            }));
            const res = await fetch(`/wiz/api/page.dashboard/analyze_upload`, { method: 'POST', body: fd });
            const json = await res.json();
            if (json.code === 200 && json.data) {
                const result = json.data;
                this.analysisResult = result;
                this.analysisSavedName = result.saved_name || '';
                this.realtimeLastElapsed = result.server_timing?.total_server_sec || 0;
                // Cumulative scoring — weighted average of last 3 chunks
                const score = result.risk_score || 0;
                this.realtimeScoreHistory.push(score);
                if (this.realtimeScoreHistory.length > 3) this.realtimeScoreHistory.shift();
                const weights = [1, 2, 3];
                const n = this.realtimeScoreHistory.length;
                let wSum = 0, wTotal = 0;
                for (let i = 0; i < n; i++) {
                    const w = weights[weights.length - n + i] || 1;
                    wSum += this.realtimeScoreHistory[i] * w;
                    wTotal += w;
                }
                this.realtimeCumulativeScore = wSum / wTotal;
                this.updateRealtimeOverlay();
                this.pushRealtimeLog(blob, chunkId);
                // Performance tracking
                const rtt = performance.now() - startTime;
                this.realtimeRoundTripHistory.push(rtt);
                if (this.realtimeRoundTripHistory.length > 10) this.realtimeRoundTripHistory.shift();
                const st = (result.server_timing?.total_server_sec || 0) * 1000;
                this.realtimeServerTimeHistory.push(st);
                if (this.realtimeServerTimeHistory.length > 10) this.realtimeServerTimeHistory.shift();
                this.realtimePerfStats.avgRtt = Math.round(this.realtimeRoundTripHistory.reduce((a: number, b: number) => a + b, 0) / this.realtimeRoundTripHistory.length);
                this.realtimePerfStats.avgServer = Math.round(this.realtimeServerTimeHistory.reduce((a: number, b: number) => a + b, 0) / this.realtimeServerTimeHistory.length);
            }
        } catch (e: any) {
            console.error('Dispatch error:', e);
        }
        this.realtimeDispatching = false;
        await this.service.render();
    }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // Realtime Overlay
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    private updateRealtimeOverlay() {
        if (!this.analysisResult) return;
        this.realtimeOverlayScore = Math.round(this.realtimeCumulativeScore * 100);
        const level = this.analysisResult?.risk_level || 'low';
        this.realtimeOverlayLevel = level;
        this.realtimeOverlayLabel = this.realtimePendingConfirmation ? '확인 대기'
            : this.analysisResult?.fall_detected ? '낙상 감지' : '정상';
        const basis: string[] = [];
        const ri = this.analysisResult?.runtime_inference;
        const runtimeKey = this.analysisResult?.runtime_key || '';
        const isXgb = runtimeKey === 'person-feature-runtime';
        // 1) 낙상 판정 결과
        const fallDetected = this.analysisResult?.fall_detected;
        if (fallDetected) {
            basis.push('⚠ 낙상');
        } else if (ri?.fall_score != null || ri?.fall_probability != null) {
            basis.push('정상');
        }
        // 2) 낙상 확률
        const fallProb = ri?.fall_probability;
        if (fallProb != null) {
            basis.push(`확률 ${(fallProb * 100).toFixed(0)}%`);
        } else {
            const rawProb = ri?.raw_fall_probability;
            if (rawProb != null) basis.push(`Raw ${(rawProb * 100).toFixed(0)}%`);
        }
        // 3) 핵심 피처값
        if (isXgb) {
            const tf = ri?.top_features || {};
            const mds = tf['max_down_speed'];
            const cdy = tf['center_dy'];
            const fp = tf['floor_proximity'];
            const hr = tf['height_ratio'];
            if (mds != null) basis.push(`하강속도 ${Number(mds).toFixed(2)}`);
            if (cdy != null && Number(cdy) > 0.01) basis.push(`수직이동 ${Number(cdy).toFixed(2)}`);
            if (fp != null && Number(fp) > 0.5) basis.push(`바닥근접 ${(Number(fp) * 100).toFixed(0)}%`);
            if (hr != null && Number(hr) < -0.03) basis.push(`높이↓ ${(Number(hr) * 100).toFixed(0)}%`);
        } else {
            const feats = ri?.features || {};
            const dym = feats['delta_y_max'];
            const fhr = feats['final_height_ratio'];
            if (dym != null) basis.push(`△Y ${Number(dym).toFixed(1)}px`);
            if (fhr != null) basis.push(`자세 ${(Number(fhr) * 100).toFixed(0)}%`);
        }
        // 4) 검출 프레임/윈도우
        const nFrames = ri?.short_clip?.n_det_frames || ri?.windows;
        if (nFrames != null) basis.push(`${nFrames}${isXgb ? 'w' : 'f'} 검출`);
        // 4.5) XG-Dual posture + decision state
        const postureLabel = ri?.posture_label;
        const decisionState = ri?.decision_state;
        if (postureLabel) basis.push(this.POSTURE_LABEL_MAP[postureLabel] || postureLabel);
        if (decisionState && decisionState !== 'safe') {
            const dsMeta = this.DECISION_STATE_META[decisionState];
            if (dsMeta) basis.push(dsMeta.label);
        }
        // 5) 보정 배지
        if (isXgb) {
            if (ri?.motion_gate && !ri.motion_gate.passed) basis.push('Gate억제');
        } else {
            if (ri?.motion_guard?.applied) basis.push('Guard');
        }
        if (ri?.short_clip?.is_short_clip) basis.push('Short-clip');
        // 6) 소요 시간
        if (this.realtimeLastElapsed > 0) basis.push(`${this.realtimeLastElapsed.toFixed(1)}초`);
        const newBasis = basis.slice(0, 6).join(' · ') || '';
        if (newBasis) {
            this.realtimeOverlayBasis = newBasis;
            this.lastNonEmptyOverlayBasis = newBasis;
        } else if (this.lastNonEmptyOverlayBasis) {
            this.realtimeOverlayBasis = this.lastNonEmptyOverlayBasis;
        }
        this.realtimeOverlayRuntime = '';
        if (this.analysisResult?.fall_detected && !this.analysisResult?._dedup_suppressed) {
            this.realtimeOverlayFlash = true;
            if (this.realtimeOverlayFlashTimer) clearTimeout(this.realtimeOverlayFlashTimer);
            this.realtimeOverlayFlashTimer = setTimeout(() => { this.realtimeOverlayFlash = false; }, 2000);
        }
    }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // Upload Analysis
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    public async onFileSelected(event: any) {
        const file = event?.target?.files?.[0];
        if (!file) return;
        this.selectedFile = file;
        this.selectedVideoUrl = URL.createObjectURL(file);
        this.analysisResult = null;
        this.feedbackStatus = '';
        this.feedbackMessage = '';
        this.errorMessage = '';
        await this.service.render();
    }

    public async onDrop(event: DragEvent) {
        event.preventDefault();
        this.dragover = false;
        const file = event.dataTransfer?.files?.[0];
        if (!file) return;
        this.selectedFile = file;
        this.selectedVideoUrl = URL.createObjectURL(file);
        this.analysisResult = null;
        this.feedbackStatus = '';
        this.errorMessage = '';
        await this.service.render();
    }

    public onDragOver(event: DragEvent) { event.preventDefault(); this.dragover = true; }
    public onDragLeave(event: DragEvent) { event.preventDefault(); this.dragover = false; }

    public async analyze() {
        if (!this.selectedFile || this.analyzing) return;
        this.analyzing = true;
        this.analysisResult = null;
        this.errorMessage = '';
        this.feedbackStatus = '';
        this.feedbackMessage = '';
        this.uploadProgress = 0;
        await this.service.render();
        try {
            const fd = new FormData();
            fd.append('video', this.selectedFile);
            fd.append('metadata', JSON.stringify({
                analysis_profile: this.analysisProfile,
                input_source: 'upload',
                model_type: this.selectedModelType,
            }));
            const res = await fetch(`/wiz/api/page.dashboard/analyze_upload`, {
                method: 'POST',
                body: fd,
            });
            const json = await res.json();
            if (json.code === 200 && json.data) {
                this.analysisResult = json.data;
                this.analysisSavedName = json.data.saved_name || '';
                this.alertWorkflow = json.data.alert_workflow || null;
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

    public clearSelectedFile() {
        this.selectedFile = null;
        this.selectedVideoUrl = '';
        this.analysisResult = null;
        this.feedbackStatus = '';
        this.errorMessage = '';
    }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // Result Display Helpers
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    public riskClass(level: string): string {
        if (level === 'high') return 'text-rose-600';
        if (level === 'medium') return 'text-amber-600';
        return 'text-emerald-600';
    }

    public riskBgClass(level: string): string {
        if (level === 'high') return 'bg-rose-50 border-rose-200';
        if (level === 'medium') return 'bg-amber-50 border-amber-200';
        return 'bg-emerald-50 border-emerald-200';
    }

    public riskBadgeClass(level: string): string {
        if (level === 'high') return 'bg-rose-100 text-rose-700';
        if (level === 'medium') return 'bg-amber-100 text-amber-700';
        return 'bg-emerald-100 text-emerald-700';
    }

    public riskScorePercent(): number {
        return Math.round((this.analysisResult?.risk_score || 0) * 100);
    }

    public formatRisk(score: number): string {
        return (score * 100).toFixed(0) + '%';
    }

    public currentEngineLabel(): string {
        const key = this.analysisResult?.runtime_key || '';
        if (key === 'xg-dual') return 'XG-Dual (Fall+Posture)';
        if (key === 'person-feature-runtime') return 'XGBoost v2 (사람 추적)';
        if (key === 'rf-pipeline-runtime') return 'RF 보조 (RandomForest)';
        if (key === 'heuristic-fallback') return '휴리스틱 Fallback';
        return key || '알 수 없음';
    }

    public currentEngineNote(): string {
        const key = this.analysisResult?.runtime_key || '';
        if (key === 'xg-dual') return '낙상+자세 동시 분석';
        if (key === 'person-feature-runtime') return 'bbox 궤적 기반 37-feature 분석';
        if (key === 'rf-pipeline-runtime') return 'RF 보조 파이프라인';
        return '';
    }

    public modelSpeedHint(): string {
        const key = this.selectedModelType || '';
        if (this.inputMode === 'webcam') {
            if (key === 'person-feature' || key === 'xg-dual') return '~8초/청크';
            return '~3초/청크';
        }
        if (key === 'person-feature' || key === 'xg-dual') return '5~15초';
        return '3~8초';
    }

    public getRiskScoreFormula(): string {
        const key = this.analysisResult?.runtime_key || '';
        const guide = this.analysisResult?.risk_score_guide;
        if (guide?.formula) return guide.formula;
        if (key === 'xg-dual') return 'max_prob × (1 - suppress_factor)';
        if (key === 'person-feature-runtime') return 'max(window_probs) × fall_ratio';
        return 'fall_probability × motion_factor';
    }

    public sortedAnalysisBasis(): any[] {
        const basis = this.analysisResult?.analysis_basis || [];
        return [...basis].sort((a: any, b: any) => (a.contribution_rank || 99) - (b.contribution_rank || 99));
    }

    public basisCardClass(item: any): string {
        const lvl = item.level || 'normal';
        if (lvl === 'danger' || lvl === 'high') return 'border-rose-200 bg-rose-50';
        if (lvl === 'warning' || lvl === 'medium') return 'border-amber-200 bg-amber-50';
        return 'border-zinc-200 bg-zinc-50';
    }

    // ── XG-Dual helpers ──
    public isXgDualResult(): boolean {
        return this.analysisResult?.runtime_key === 'xg-dual';
    }

    public hasPostureData(): boolean {
        const pp = this.analysisResult?.posture_probs || this.analysisResult?.runtime_inference?.posture_probs;
        return pp && Object.keys(pp).length > 0;
    }

    public postureLabel(): string {
        const label = this.analysisResult?.posture_label || this.analysisResult?.runtime_inference?.posture_label || 'unknown';
        return this.POSTURE_LABEL_MAP[label] || label;
    }

    public decisionStateMeta(): any {
        const state = this.analysisResult?.decision_state || this.analysisResult?.runtime_inference?.decision_state || 'safe';
        return this.DECISION_STATE_META[state] || this.DECISION_STATE_META['safe'];
    }

    public isAmbiguousDecision(): boolean {
        const state = this.analysisResult?.decision_state || '';
        return state === 'uncertain' || state === 'fall_suspected';
    }

    public postureItems(): any[] {
        const pp = this.analysisResult?.posture_probs || this.analysisResult?.runtime_inference?.posture_probs || {};
        const iconMap: Record<string, string> = { stand: '🧍', walk: '🚶', run: '🏃', sit: '🪑', lie: '🛌', fall: '⚠️' };
        const currentLabel = this.analysisResult?.posture_label || this.analysisResult?.runtime_inference?.posture_label || '';
        return Object.entries(pp).map(([key, val]) => ({
            code: key,
            label: this.POSTURE_LABEL_MAP[key] || key,
            icon: iconMap[key] || '❓',
            prob: val as number,
            percent: Math.round((val as number) * 100),
            active: key === currentLabel,
        })).sort((a, b) => b.prob - a.prob);
    }

    public getExplainItems(): string[] {
        return this.analysisResult?.explain || [];
    }

    public getSuppressedBy(): string[] {
        return this.analysisResult?.runtime_inference?.suppressed_by || [];
    }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // E2E Timing
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

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

    public getE2ETimeline(): any[] {
        const st = this.analysisResult?.server_timing;
        if (!st) return [];
        const total = st.total_server_sec || 1;
        const items = this.getServerTimingDetail();
        let cumulative = 0;
        return items.map(i => {
            const pct = ((i.value || 0) / total) * 100;
            const start = cumulative;
            cumulative += pct;
            return { ...i, pct, start };
        });
    }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // Feedback (Upload mode — 2-Level HITL)
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    public async submitAnalysisFeedback() {
        if (!this.feedbackStatus || !this.analysisSavedName) return;
        this.feedbackSubmitting = true;
        this.feedbackMessage = '';
        await this.service.render();
        try {
            const params: any = {
                saved_name: this.analysisSavedName,
                predicted_label: this.analysisResult?.fall_detected ? 'Y' : 'N',
                feedback_status: this.feedbackStatus,
                actual_label: this.feedbackActualLabel || '',
                note: this.feedbackNote || '',
                retrain: 'false',
                posture_class: this.feedbackPostureClass || '',
                predicted_posture: this.analysisResult?.posture_label || '',
                ambiguity_flag: String(this.feedbackAmbiguityFlag),
                occlusion_flag: String(this.feedbackOcclusionFlag),
                short_clip_flag: String(this.feedbackShortClipFlag),
            };
            const { code, data } = await wiz.call('submit_analysis_feedback', params);
            if (code === 200) {
                this.feedbackMessage = '피드백이 저장되었습니다.';
                this.feedbackMessageType = 'success';
                if (data?.auto_retrain_triggered) {
                    this.feedbackRetrainDone = true;
                    this.feedbackMessage += ' (자동 재학습 트리거됨)';
                }
            } else {
                this.feedbackMessage = data?.message || '피드백 저장 실패';
                this.feedbackMessageType = 'error';
            }
        } catch (e: any) {
            this.feedbackMessage = '오류: ' + (e.message || e);
            this.feedbackMessageType = 'error';
        }
        this.feedbackSubmitting = false;
        await this.service.render();
    }

    public toggleFeedbackFlag(flag: string) {
        if (flag === 'ambiguity') this.feedbackAmbiguityFlag = !this.feedbackAmbiguityFlag;
        if (flag === 'occlusion') this.feedbackOcclusionFlag = !this.feedbackOcclusionFlag;
        if (flag === 'short_clip') this.feedbackShortClipFlag = !this.feedbackShortClipFlag;
    }

    public resetFeedback() {
        this.feedbackStatus = '';
        this.feedbackActualLabel = '';
        this.feedbackPostureClass = '';
        this.feedbackNote = '';
        this.feedbackAmbiguityFlag = false;
        this.feedbackOcclusionFlag = false;
        this.feedbackShortClipFlag = false;
        this.feedbackMessage = '';
    }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // Realtime Log
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    private pushRealtimeLog(blob: Blob, chunkId: number) {
        const blobUrl = URL.createObjectURL(blob);
        const entry = {
            id: chunkId,
            timestamp: new Date().toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
            blobUrl,
            result: { ...this.analysisResult },
            score: this.analysisResult?.risk_score || 0,
            level: this.analysisResult?.risk_level || 'low',
            label: this.analysisResult?.fall_detected ? '낙상' : '정상',
            runtimeKey: this.analysisResult?.runtime_key || '',
            elapsed: this.realtimeLastElapsed,
            cumulativeScore: this.realtimeCumulativeScore,
            feedbackDone: false,
        };
        this.realtimeLogEntries.unshift(entry);
        if (this.realtimeLogEntries.length > 50) {
            const removed = this.realtimeLogEntries.pop();
            if (removed?.blobUrl) URL.revokeObjectURL(removed.blobUrl);
        }
        this.scrollLogToBottom();
    }

    private scrollLogToBottom() {
        setTimeout(() => {
            const el = this.logScrollContainerRef?.nativeElement;
            if (el) el.scrollTop = 0;
        }, 50);
    }

    public cleanupLogBlobUrls() {
        for (const entry of this.realtimeLogEntries) {
            if (entry.blobUrl) URL.revokeObjectURL(entry.blobUrl);
        }
        this.realtimeLogEntries = [];
    }

    public async openLogDetail(entry: any) {
        this.logDetailEntry = entry;
        this.logDetailOpen = true;
        this.logFeedbackStatus = '';
        this.logFeedbackActualLabel = '';
        this.logFeedbackPostureClass = '';
        this.logFeedbackNote = '';
        this.logFeedbackAmbiguityFlag = false;
        this.logFeedbackOcclusionFlag = false;
        this.logFeedbackShortClipFlag = false;
        await this.service.render();
    }

    public async closeLogDetail() {
        this.logDetailOpen = false;
        this.logDetailEntry = null;
        await this.service.render();
    }

    public async deleteLogEntry(entry: any, event?: Event) {
        if (event) event.stopPropagation();
        const idx = this.realtimeLogEntries.indexOf(entry);
        if (idx >= 0) {
            if (entry.blobUrl) URL.revokeObjectURL(entry.blobUrl);
            this.realtimeLogEntries.splice(idx, 1);
        }
        if (this.logDetailEntry === entry) {
            this.logDetailOpen = false;
            this.logDetailEntry = null;
        }
        await this.service.render();
    }

    public logRiskClass(level: string): string {
        if (level === 'high') return 'text-rose-500';
        if (level === 'medium') return 'text-amber-500';
        return 'text-emerald-500';
    }

    public logRiskDotClass(level: string): string {
        if (level === 'high') return 'bg-rose-500';
        if (level === 'medium') return 'bg-amber-500';
        return 'bg-emerald-500';
    }

    public async submitLogFeedback() {
        if (!this.logFeedbackStatus || !this.logDetailEntry) return;
        this.logFeedbackSubmitting = true;
        await this.service.render();
        try {
            const entry = this.logDetailEntry;
            const params: any = {
                saved_name: entry.result?.saved_name || '',
                predicted_label: entry.result?.fall_detected ? 'Y' : 'N',
                feedback_status: this.logFeedbackStatus,
                actual_label: this.logFeedbackActualLabel || '',
                note: this.logFeedbackNote || '',
                retrain: 'false',
                posture_class: this.logFeedbackPostureClass || '',
                predicted_posture: entry.result?.posture_label || '',
                ambiguity_flag: String(this.logFeedbackAmbiguityFlag),
                occlusion_flag: String(this.logFeedbackOcclusionFlag),
                short_clip_flag: String(this.logFeedbackShortClipFlag),
            };
            const { code } = await wiz.call('submit_analysis_feedback', params);
            if (code === 200) {
                entry.feedbackDone = true;
            }
        } catch (e) { }
        this.logFeedbackSubmitting = false;
        await this.service.render();
    }

    public toggleLogFeedbackFlag(flag: string) {
        if (flag === 'ambiguity') this.logFeedbackAmbiguityFlag = !this.logFeedbackAmbiguityFlag;
        if (flag === 'occlusion') this.logFeedbackOcclusionFlag = !this.logFeedbackOcclusionFlag;
        if (flag === 'short_clip') this.logFeedbackShortClipFlag = !this.logFeedbackShortClipFlag;
    }

    public setLogFeedbackPostureClass(code: string) {
        this.logFeedbackPostureClass = this.logFeedbackPostureClass === code ? '' : code;
    }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // Detection Replay
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    public getDetectionFrames(): any[] {
        return this.analysisResult?.model_runtime?.detection_frames || [];
    }

    public async toggleDetectionReplay() {
        if (this.detectionReplayPlaying) {
            this.stopDetectionReplay();
        } else {
            this.startDetectionReplay();
        }
        await this.service.render();
    }

    private startDetectionReplay() {
        const frames = this.getDetectionFrames();
        if (frames.length === 0) return;
        this.detectionReplayPlaying = true;
        this.detectionReplayIndex = 0;
        this.drawDetectionFrame(0);
        this.detectionReplayTimer = setInterval(() => {
            this.detectionReplayIndex++;
            if (this.detectionReplayIndex >= frames.length) {
                this.stopDetectionReplay();
                return;
            }
            this.drawDetectionFrame(this.detectionReplayIndex);
        }, 200);
    }

    public stopDetectionReplay() {
        this.detectionReplayPlaying = false;
        if (this.detectionReplayTimer) { clearInterval(this.detectionReplayTimer); this.detectionReplayTimer = null; }
    }

    public seekDetectionReplay(idx: number) {
        const frames = this.getDetectionFrames();
        if (idx >= 0 && idx < frames.length) {
            this.detectionReplayIndex = idx;
            this.drawDetectionFrame(idx);
        }
    }

    private drawDetectionFrame(idx: number) {
        const frames = this.getDetectionFrames();
        const frame = frames[idx];
        if (!frame) return;
        const canvasEl = this.detCanvasRef?.nativeElement;
        if (!canvasEl) return;
        const ctx = canvasEl.getContext('2d');
        if (!ctx) return;
        ctx.clearRect(0, 0, canvasEl.width, canvasEl.height);
        const detections = frame.detections || [];
        for (const det of detections) {
            ctx.strokeStyle = '#22d3ee';
            ctx.lineWidth = 2;
            const x = det.x1 * canvasEl.width;
            const y = det.y1 * canvasEl.height;
            const w = (det.x2 - det.x1) * canvasEl.width;
            const h = (det.y2 - det.y1) * canvasEl.height;
            ctx.strokeRect(x, y, w, h);
            ctx.fillStyle = '#22d3ee';
            ctx.font = '10px sans-serif';
            ctx.fillText(`${(det.conf * 100).toFixed(0)}%`, x, y - 4);
        }
    }

    public drawBboxesOnCanvas(canvas: HTMLCanvasElement, detections: any[], w: number, h: number) {
        const ctx = canvas.getContext('2d');
        if (!ctx) return;
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        if (!this.bboxOverlayEnabled) return;
        for (const det of detections) {
            ctx.strokeStyle = '#22d3ee';
            ctx.lineWidth = 2;
            ctx.strokeRect(det.x1 * w, det.y1 * h, (det.x2 - det.x1) * w, (det.y2 - det.y1) * h);
        }
    }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // Alert / Emergency / Reference
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    public async openRiskAlertWorkflow() {
        if (!this.analysisResult || !this.analysisSavedName) return;
        try {
            const params = {
                saved_name: this.analysisSavedName,
                risk_level: this.analysisResult.risk_level || 'low',
                risk_score: String(this.analysisResult.risk_score || 0),
                risk_label: this.analysisResult.risk_label || '',
                summary: this.analysisResult.summary || '',
                fall_detected: String(this.analysisResult.fall_detected || false),
            };
            const { code, data } = await wiz.call('dispatch_risk_alerts', params);
            if (code === 200) {
                this.alertWorkflow = data;
                if (data?.emergency?.popup_required) {
                    this.emergencyPopupOpen = true;
                }
            }
        } catch (e) { }
        await this.service.render();
    }

    public closeEmergencyPopup() {
        this.emergencyPopupOpen = false;
    }

    public async openReferencePopup(sceneId: string) {
        this.referencePopupLoading = true;
        this.referencePopupOpen = true;
        await this.service.render();
        try {
            const { code, data } = await wiz.call('reference_preview_info', { scene_id: sceneId });
            if (code === 200) {
                this.referencePopupData = data;
            }
        } catch (e) { }
        this.referencePopupLoading = false;
        await this.service.render();
    }

    public closeReferencePopup() {
        this.referencePopupOpen = false;
        this.referencePopupData = null;
    }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // Navigation
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    public goPipelinePage() { this.service.href('/pipeline'); }
    public goManualPage() { this.service.href('/manual'); }
    public goAdminPage() { this.service.href('/admin/analysis'); }
}

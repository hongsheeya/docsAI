import { OnInit } from '@angular/core';
import { Service } from '@wiz/libs/portal/season/service';

declare const wiz: any;

export class Component implements OnInit {
    public registry: any = null;
    public loading: boolean = true;
    public uploadFiles: File[] = [];
    public uploadFamily: string = 'rf-fall-v2';
    public uploadLabel: string = '';
    public uploadNote: string = '';
    public uploading: boolean = false;
    public uploadDone: number = 0;
    public uploadMessage: string = '';
    public uploadMessageType: string = 'info';
    public familyFilter: string = 'all';
    public compareMetric: string = 'f1';
    public deletingId: string = '';
    public selectedModelId: string = '';
    public selectedComparisonIds: string[] = [];
    public savingFamily: string = '';
    public cleanupBusy: boolean = false;
    public bundleLabel: string = '';
    public bundleSaving: boolean = false;
    public applyingBundleId: string = '';
    public deletingBundleId: string = '';
    public cancelingDeleteId: string = '';
    public showDeleteOnly: boolean = false;
    public sensitivityLevel: number = 50;
    public sensitivitySaving: boolean = false;
    public modelManagerMode: string = 'overview';

    constructor(public service: Service) { }

    public async ngOnInit() {
        await this.service.init(this);
        await this.loadRegistry();
    }

    private async readJsonResponse(res: Response): Promise<any> {
        const text = await res.text();
        const trimmed = String(text || '').trim();
        if (!trimmed) throw new Error(`서버 응답이 비어 있습니다. HTTP ${res.status || 'unknown'}`);
        if (/^<!doctype\s+html/i.test(trimmed) || /^<html[\s>]/i.test(trimmed)) {
            throw new Error(`서버가 JSON 대신 HTML 오류 페이지를 반환했습니다. HTTP ${res.status || 'unknown'}`);
        }
        return JSON.parse(trimmed);
    }

    private responsePayload(json: any): any {
        return json?.data && typeof json.data === 'object' ? json.data : (json || {});
    }

    public async loadRegistry() {
        this.loading = true;
        await this.service.render();
        try {
            const { code, data, message }: any = await wiz.call('model_registry');
            if (code === 200) {
                this.registry = data || {};
                this.syncFallSensitivity();
                this.syncComparisonSelection();
            } else {
                this.uploadMessage = message || data?.message || '모델 목록을 불러오지 못했습니다.';
                this.uploadMessageType = 'error';
            }
        } catch (e: any) {
            this.uploadMessage = e?.message || '모델 목록을 불러오지 못했습니다.';
            this.uploadMessageType = 'error';
        }
        this.loading = false;
        await this.service.render();
    }

    public families(): any[] {
        return Array.isArray(this.registry?.families) ? this.registry.families : [];
    }

    public allItems(): any[] {
        return Array.isArray(this.registry?.items) ? this.registry.items : [];
    }

    public setModelManagerMode(mode: string) {
        this.modelManagerMode = String(mode || 'overview');
        this.service.render();
    }

    public modelManagerModeClass(mode: string): string {
        return this.modelManagerMode === mode
            ? 'border-zinc-900 bg-zinc-900 text-white shadow-sm'
            : 'border-zinc-200 bg-white text-zinc-600 hover:bg-zinc-50';
    }

    private pct(value: any, digits: number = 1): string {
        const n = Number(value);
        return Number.isFinite(n) && n > 0 ? `${(n * 100).toFixed(digits)}%` : '-';
    }

    public activeModelItems(): any[] {
        return this.allItems().filter((item: any) => item?.source === 'active' || item?.source === 'custom-final').slice(0, 6);
    }

    public dashboardTrainingItems(): any[] {
        return Array.isArray(this.registry?.training_dashboard?.items) ? this.registry.training_dashboard.items : [];
    }

    public friendlyTrainingItems(): any[] {
        const rows = this.dashboardTrainingItems();
        const running = rows.filter((item: any) => ['queued', 'running'].includes(String(item?.stage || item?.status || '')));
        const important = rows.filter((item: any) => ['aihub82', 'aihub173', 'xg-posture'].includes(String(item?.name || item?.key || '')));
        return Array.from(new Map([...running, ...important, ...rows].map((item: any) => [String(item?.name || item?.key || item?.label || Math.random()), item])).values()).slice(0, 5);
    }

    public trainingItemTitle(item: any): string {
        return String(item?.label || item?.name || item?.key || '학습 상태');
    }

    public trainingItemStageLabel(item: any): string {
        const stage = String(item?.stage || item?.status || '').trim();
        if (stage === 'running') return '학습 중';
        if (stage === 'queued') return '대기 중';
        if (stage === 'completed') return '완료';
        if (stage === 'blocked') return '확인 필요';
        if (stage === 'failed') return '실패';
        if (stage === 'not-started') return '미시작';
        return stage || '상태 확인';
    }

    public trainingItemStageClass(item: any): string {
        const stage = String(item?.stage || item?.status || '').trim();
        if (stage === 'running' || stage === 'queued') return 'bg-emerald-50 text-emerald-700 border-emerald-200';
        if (stage === 'completed') return 'bg-sky-50 text-sky-700 border-sky-200';
        if (stage === 'blocked' || stage === 'failed') return 'bg-rose-50 text-rose-700 border-rose-200';
        return 'bg-zinc-50 text-zinc-600 border-zinc-200';
    }

    public trainingItemMetricText(item: any): string {
        const macro = Number(item?.active_macro_f1 || item?.best_macro_f1 || item?.candidate_macro_f1 || item?.macro_f1 || 0);
        const acc = Number(item?.active_accuracy || item?.candidate_accuracy || item?.accuracy || 0);
        const bits = [];
        if (macro > 0) bits.push(`F1 ${this.pct(macro)}`);
        if (acc > 0) bits.push(`Acc ${this.pct(acc)}`);
        return bits.join(' · ') || String(item?.message || item?.latest_log || '-');
    }

    public trainingItemVersionText(item: any): string {
        return String(item?.training_version_text || item?.candidate_version_text || item?.active_version_text || item?.version_text || '-');
    }

    public trainingItemEtaText(item: any): string {
        return String(item?.eta_text || item?.eta || '-');
    }

    public trainingItemProgressPercent(item: any): number {
        const progress = Number(item?.progress || 0);
        if (Number.isFinite(progress) && progress > 0) return Math.max(2, Math.min(100, Math.round(progress * 100)));
        const percent = Number(item?.download_progress_percent || item?.progress_percent || 0);
        if (Number.isFinite(percent) && percent > 0) return Math.max(2, Math.min(100, Math.round(percent)));
        return ['running', 'queued'].includes(String(item?.stage || item?.status || '')) ? 6 : 0;
    }

    public modelOverviewCards(): any[] {
        const comparison = this.comparisonCandidateRows();
        const best = comparison[0] || {};
        const facial = this.registry?.training_dashboard?.facial_bottleneck?.active || {};
        const running = Number(this.registry?.training_dashboard?.running_count || 0);
        return [
            {
                label: '운영 모델',
                value: best?.display_name || best?.label || 'RF-Dual',
                note: best?.f1 ? `대표 F1 ${this.pct(best.f1)}` : '현재 적용 조합 기준',
                tone: 'emerald',
            },
            {
                label: '표정 모델',
                value: this.pct(facial?.macro_f1 || this.findModelMetric('facial-aihub82', 'macro_f1')),
                note: '경계 혼동 병목 추적 중',
                tone: 'amber',
            },
            {
                label: '백그라운드 학습',
                value: `${running}개 진행`,
                note: `${Number(this.registry?.training_dashboard?.total_count || 0)}개 상태 확인`,
                tone: running > 0 ? 'sky' : 'zinc',
            },
            {
                label: '관리 모델',
                value: `${this.allItems().length}개`,
                note: `${this.deletableCount()}개 정리 가능`,
                tone: 'violet',
            },
        ];
    }

    public overviewCardClass(card: any): string {
        const tone = String(card?.tone || 'zinc');
        if (tone === 'emerald') return 'border-emerald-200 bg-emerald-50 text-emerald-950';
        if (tone === 'amber') return 'border-amber-200 bg-amber-50 text-amber-950';
        if (tone === 'sky') return 'border-sky-200 bg-sky-50 text-sky-950';
        if (tone === 'violet') return 'border-violet-200 bg-violet-50 text-violet-950';
        return 'border-zinc-200 bg-white text-zinc-950';
    }

    public modelQuickActions(): any[] {
        return [
            { mode: 'upload', title: '모델 파일 등록', description: '새 모델이나 summary 파일을 올려 성능 비교에 추가합니다.', button: '등록하기' },
            { mode: 'sensitivity', title: '낙상 감도 조절', description: '오탐을 줄이거나 민감하게 잡는 정도만 간단히 바꿉니다.', button: '감도 조절' },
            { mode: 'advanced', title: '고급 모델 조합', description: '세부 모델 선택, 최종 조합 저장, 후보 정리를 관리합니다.', button: '고급 열기' },
        ];
    }

    public facialBottleneckLines(): string[] {
        const report = this.registry?.training_dashboard?.facial_bottleneck || {};
        const lines: string[] = [];
        const active = report?.active || {};
        if (active?.macro_f1) lines.push(`현재 active F1 ${this.pct(active.macro_f1)} · selection ${this.pct(active.selection_score)}`);
        const confusions = Array.isArray(report?.recurring_confusions) ? report.recurring_confusions : [];
        for (const item of confusions.slice(0, 2)) {
            lines.push(`${item.truth} -> ${item.pred} 평균 ${(Number(item.mean_rate || 0) * 100).toFixed(1)}%`);
        }
        const actions = Array.isArray(report?.next_actions) ? report.next_actions : [];
        if (actions[0]) lines.push(actions[0]);
        return lines.length ? lines : ['표정 모델 병목 리포트를 불러오는 중입니다.'];
    }

    private findModelMetric(key: string, metric: string): number {
        const item = this.allItems().find((row: any) => String(row?.family || row?.key || '') === key || String(row?.model_id || '').includes(key));
        return Number(item?.metrics?.[metric] || item?.metrics?.f1 || item?.metrics?.macro_f1 || 0);
    }

    public visibleItems(): any[] {
        let rows = this.allItems();
        if (this.familyFilter !== 'all') {
            rows = rows.filter((item: any) => String(item?.family || '') === this.familyFilter);
        }
        if (this.showDeleteOnly) {
            rows = rows.filter((item: any) => item?.deletable !== false);
        }
        return rows;
    }

    public comparisonRows(): any[] {
        const rows = this.comparisonCandidateRows();
        const selected = rows.filter((item: any) => this.isCompareSelected(item));
        return selected.length > 0 ? selected : rows.slice(0, 6);
    }

    public comparisonCandidateRows(): any[] {
        const rows = Array.isArray(this.registry?.comparison?.rows) ? this.registry.comparison.rows : [];
        if (this.familyFilter === 'all') return rows;
        return rows.filter((item: any) => String(item?.family || '') === this.familyFilter);
    }

    private syncComparisonSelection() {
        const rows = this.comparisonCandidateRows();
        const validIds = new Set(rows.map((row: any) => String(row?.model_id || '')));
        this.selectedComparisonIds = this.selectedComparisonIds.filter(id => validIds.has(String(id)));
        if (this.selectedComparisonIds.length === 0) {
            const defaults = [
                ...rows.filter((row: any) => row?.active).map((row: any) => String(row?.model_id || '')),
                ...rows.slice(0, 6).map((row: any) => String(row?.model_id || '')),
            ].filter(Boolean);
            this.selectedComparisonIds = Array.from(new Set(defaults)).slice(0, 6);
        }
        this.selectedModelId = this.selectedComparisonIds[0] || rows[0]?.model_id || '';
    }

    public comparisonSelectedCount(): number {
        return this.comparisonCandidateRows().filter((row: any) => this.isCompareSelected(row)).length;
    }

    public metricValue(row: any, metric?: string): number {
        const key = metric || this.compareMetric || 'f1';
        const value = Number(row?.[key] ?? row?.metrics?.[key] ?? 0);
        return Number.isFinite(value) ? value : 0;
    }

    public metricText(row: any, metric?: string): string {
        const value = this.metricValue(row, metric);
        return value > 0 ? `${(value * 100).toFixed(1)}%` : '-';
    }

    public metricBarWidth(row: any): string {
        const rows = this.comparisonRows();
        const best = Math.max(...rows.map((item: any) => this.metricValue(item)), 0.01);
        return `${Math.max(4, Math.round((this.metricValue(row) / best) * 100))}%`;
    }

    public selectComparisonRow(row: any) {
        this.selectedModelId = String(row?.model_id || '');
        this.service.render();
    }

    public toggleCompareRow(row: any) {
        const id = String(row?.model_id || '');
        if (!id) return;
        if (this.selectedComparisonIds.includes(id)) {
            this.selectedComparisonIds = this.selectedComparisonIds.filter(item => item !== id);
        } else {
            this.selectedComparisonIds = [...this.selectedComparisonIds, id];
        }
        this.selectedModelId = this.selectedComparisonIds[0] || this.comparisonCandidateRows()[0]?.model_id || '';
        this.service.render();
    }

    public selectBestComparisonRows() {
        this.selectedComparisonIds = this.comparisonCandidateRows().slice(0, 6).map((row: any) => String(row?.model_id || '')).filter(Boolean);
        this.selectedModelId = this.selectedComparisonIds[0] || '';
        this.service.render();
    }

    public clearComparisonSelection() {
        this.selectedComparisonIds = [];
        this.selectedModelId = '';
        this.service.render();
    }

    public selectedComparisonRow(): any {
        const rows = this.comparisonRows();
        return rows.find((row: any) => String(row?.model_id || '') === this.selectedModelId) || rows[0] || {};
    }

    public isSelected(row: any): boolean {
        return !!row?.model_id && String(row.model_id) === String(this.selectedComparisonRow()?.model_id || '');
    }

    public isCompareSelected(row: any): boolean {
        return !!row?.model_id && this.selectedComparisonIds.includes(String(row.model_id));
    }

    public versionText(item: any): string {
        const badge = String(item?.display_version || item?.version_badge || '').trim();
        if (badge && badge !== '-') return badge;
        const text = String(item?.version_text || item?.summary?.model_version || item?.summary?.version || '').trim();
        return text || '-';
    }

    public modelTitle(item: any): string {
        if (item?.display_name) return String(item.display_name);
        const title = String(item?.label || item?.model_id || '-');
        const version = this.versionText(item);
        return version && version !== '-' && !title.includes(version) ? `${title} · ${version}` : title;
    }

    public itemMetricText(item: any): string {
        const metrics = item?.metrics || {};
        const bits = [];
        if (metrics.algorithm) bits.push(String(metrics.algorithm));
        if (Number(metrics.f1 || metrics.macro_f1 || 0) > 0) bits.push(`F1 ${this.metricText(metrics, metrics.f1 ? 'f1' : 'macro_f1')}`);
        if (Number(metrics.accuracy || 0) > 0) bits.push(`Acc ${this.metricText(metrics, 'accuracy')}`);
        if (Number(metrics.recall || 0) > 0) bits.push(`Recall ${this.metricText(metrics, 'recall')}`);
        return bits.join(' · ') || '성능 수치 없음';
    }

    public itemSampleText(item: any): string {
        const n = Number(item?.metrics?.sample_count || 0);
        return n > 0 ? `${n.toLocaleString()}건` : '-';
    }

    public itemManageText(item: any): string {
        if (item?.active_reference) return '운영 참조 보호';
        if (item?.deletable !== false) return item?.source === 'candidate' ? '삭제 예약 가능' : '삭제 가능';
        if (item?.source === 'active') return '운영 보호';
        if (item?.source === 'custom-final') return '사용 중 보호';
        if (item?.source === 'candidate') return '사용 중 보호';
        return '보호됨';
    }

    public deletableCount(): number {
        return this.allItems().filter((item: any) => item?.deletable !== false).length;
    }

    public toggleDeleteOnly() {
        this.showDeleteOnly = !this.showDeleteOnly;
        this.service.render();
    }

    private syncFallSensitivity() {
        const level = Number(this.registry?.fall_sensitivity?.level ?? 50);
        this.sensitivityLevel = Number.isFinite(level) ? Math.max(0, Math.min(100, Math.round(level))) : 50;
    }

    public fallSensitivity(): any {
        return this.registry?.fall_sensitivity || {};
    }

    public sensitivityLabel(): string {
        return String(this.fallSensitivity()?.label || '균형');
    }

    private thresholdPercent(value: any): string {
        const n = Number(value);
        return Number.isFinite(n) && n > 0 ? `${(n * 100).toFixed(1)}%` : '-';
    }

    public sensitivityThresholdText(): string {
        const thresholds = this.fallSensitivity()?.effective_thresholds || {};
        return `confirm ${this.thresholdPercent(thresholds.confirm)} · suspect ${this.thresholdPercent(thresholds.suspect)} · high ${this.thresholdPercent(thresholds.high)}`;
    }

    public sensitivityDeltaText(): string {
        const delta = Number(this.fallSensitivity()?.threshold_delta || 0);
        if (!Number.isFinite(delta) || delta === 0) return '±0.0pp';
        return `${delta > 0 ? '+' : ''}${(delta * 100).toFixed(1)}pp`;
    }

    public sensitivityHelpText(): string {
        if (this.sensitivityLevel >= 75) return '민감: 작은 낙상 가능성도 더 빨리 잡습니다.';
        if (this.sensitivityLevel <= 25) return '보수: 오탐을 줄이는 방향으로 판정합니다.';
        return '균형: 현재 검증 기준 threshold를 그대로 사용합니다.';
    }

    public async setSensitivityPreset(level: number) {
        this.sensitivityLevel = Math.max(0, Math.min(100, Math.round(Number(level) || 50)));
        await this.saveFallSensitivity();
    }

    public async saveFallSensitivity() {
        if (this.sensitivitySaving) return;
        this.sensitivitySaving = true;
        this.uploadMessage = '낙상 감도를 저장하는 중입니다.';
        this.uploadMessageType = 'info';
        await this.service.render();
        try {
            const params = new URLSearchParams();
            params.set('level', String(Math.max(0, Math.min(100, Math.round(Number(this.sensitivityLevel) || 50)))));
            params.set('enabled', 'true');
            const res = await fetch(`/wiz/api/page.models/set_fall_sensitivity?${params.toString()}`, { method: 'POST' });
            const json = await this.readJsonResponse(res);
            if (json.code === 200) {
                this.registry = json.registry || json.data?.registry || this.registry;
                if (json.fall_sensitivity && this.registry) this.registry.fall_sensitivity = json.fall_sensitivity;
                this.syncFallSensitivity();
                this.uploadMessage = `낙상 감도 저장 완료: ${this.sensitivityLabel()} ${this.sensitivityLevel}`;
                this.uploadMessageType = 'success';
            } else {
                this.uploadMessage = json.data?.message || json.message || '낙상 감도 저장 실패';
                this.uploadMessageType = 'error';
            }
        } catch (e: any) {
            this.uploadMessage = e?.message || '낙상 감도 저장 실패';
            this.uploadMessageType = 'error';
        }
        this.sensitivitySaving = false;
        await this.service.render();
    }

    public selectedFileSummary(): string {
        if (this.uploadFiles.length === 0) return '선택된 모델 파일 없음';
        const names = this.uploadFiles.slice(0, 3).map(file => this.displayName(file)).join(', ');
        return `${this.uploadFiles.length}개 선택 · ${names}${this.uploadFiles.length > 3 ? ` 외 ${this.uploadFiles.length - 3}개` : ''}`;
    }

    public displayName(file: File): string {
        return String((file as any)?.webkitRelativePath || file.name || '파일');
    }

    public onModelFilesSelected(event: any) {
        this.uploadFiles = Array.from(event?.target?.files || []) as File[];
        this.uploadMessage = '';
        if (event?.target) event.target.value = '';
        this.service.render();
    }

    public clearUploadFiles() {
        this.uploadFiles = [];
        this.uploadDone = 0;
        this.uploadMessage = '';
        this.service.render();
    }

    public async uploadSelectedModels() {
        if (this.uploadFiles.length === 0 || this.uploading) return;
        this.uploading = true;
        this.uploadDone = 0;
        this.uploadMessage = '모델 파일을 등록하는 중입니다.';
        this.uploadMessageType = 'info';
        await this.service.render();
        const importId = `manual-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
        const errors: string[] = [];
        for (let i = 0; i < this.uploadFiles.length; i++) {
            const file = this.uploadFiles[i];
            try {
                const fd = new FormData();
                fd.append('model', file);
                fd.append('family', this.uploadFamily || 'rf-fall-v2');
                fd.append('label', this.uploadLabel || importId);
                fd.append('note', this.uploadNote || '');
                fd.append('metadata', JSON.stringify({
                    model_id: importId,
                    relative_path: this.displayName(file),
                    bulk_index: i + 1,
                    bulk_total: this.uploadFiles.length,
                }));
                const res = await fetch('/wiz/api/page.models/upload_model_asset', { method: 'POST', body: fd });
                const json = await this.readJsonResponse(res);
                if (json.code !== 200) errors.push(`${file.name}: ${json.data?.message || json.message || '등록 실패'}`);
            } catch (e: any) {
                errors.push(`${file.name}: ${e?.message || e}`);
            }
            this.uploadDone = i + 1;
            this.uploadMessage = `등록 중 ${this.uploadDone}/${this.uploadFiles.length}`;
            await this.service.render();
        }
        this.uploading = false;
        if (errors.length === 0) {
            this.uploadMessage = `모델 등록 완료: ${this.uploadLabel || importId}`;
            this.uploadMessageType = 'success';
            this.uploadFiles = [];
            this.uploadLabel = '';
            this.uploadNote = '';
        } else {
            this.uploadMessage = `일부 등록 실패: ${errors.slice(0, 2).join(' / ')}`;
            this.uploadMessageType = 'error';
        }
        await this.loadRegistry();
    }

    public async deleteModel(item: any) {
        const modelId = String(item?.model_id || '');
        if (!modelId || item?.deletable === false || this.deletingId) return;
        this.deletingId = modelId;
        this.uploadMessage = `${item?.label || modelId} 삭제 예약 중`;
        this.uploadMessageType = 'info';
        await this.service.render();
        try {
            const params = new URLSearchParams();
            params.set('model_id', modelId);
            const res = await fetch(`/wiz/api/page.models/delete_model_asset?${params.toString()}`, { method: 'POST' });
            const json = await this.readJsonResponse(res);
            const payload = this.responsePayload(json);
            if (json.code === 200) {
                this.uploadMessage = payload.delete_after ? `모델 삭제를 예약했습니다. 실제 삭제 예정: ${payload.delete_after}` : '모델 삭제를 예약했습니다.';
                this.uploadMessageType = 'success';
                await this.loadRegistry();
            } else {
                this.uploadMessage = json.data?.message || json.message || '모델 삭제 실패';
                this.uploadMessageType = 'error';
            }
        } catch (e: any) {
            this.uploadMessage = e?.message || '모델 삭제 실패';
            this.uploadMessageType = 'error';
        }
        this.deletingId = '';
        await this.service.render();
    }

    public async cancelDelete(item: any) {
        const modelId = String(item?.model_id || '');
        if (!modelId || this.cancelingDeleteId) return;
        this.cancelingDeleteId = modelId;
        this.uploadMessage = `${item?.display_name || item?.label || modelId} 삭제 예약 취소 중`;
        this.uploadMessageType = 'info';
        await this.service.render();
        try {
            const params = new URLSearchParams();
            params.set('model_id', modelId);
            const res = await fetch(`/wiz/api/page.models/cancel_model_delete?${params.toString()}`, { method: 'POST' });
            const json = await this.readJsonResponse(res);
            if (json.code === 200) {
                this.uploadMessage = '삭제 예약을 취소했습니다.';
                this.uploadMessageType = 'success';
                await this.loadRegistry();
            } else {
                this.uploadMessage = json.data?.message || json.message || '삭제 예약 취소 실패';
                this.uploadMessageType = 'error';
            }
        } catch (e: any) {
            this.uploadMessage = e?.message || '삭제 예약 취소 실패';
            this.uploadMessageType = 'error';
        }
        this.cancelingDeleteId = '';
        await this.service.render();
    }

    public trashRows(): any[] {
        return Array.isArray(this.registry?.trash) ? this.registry.trash : [];
    }

    public compositionRows(): any[] {
        return Array.isArray(this.registry?.runtime_composition?.families) ? this.registry.runtime_composition.families : [];
    }

    public runtimeBundles(): any[] {
        return Array.isArray(this.registry?.runtime_bundles) ? this.registry.runtime_bundles : [];
    }

    public compositionOptions(row: any): any[] {
        return Array.isArray(row?.options) ? row.options : [];
    }

    public runtimeOptionText(option: any): string {
        const source = option?.source ? ` · ${option.source}` : '';
        const version = option?.display_version && option.display_version !== '-' ? ` · ${option.display_version}` : '';
        const f1 = Number(option?.metric_f1 || 0) > 0 ? ` · F1 ${(Number(option.metric_f1) * 100).toFixed(1)}%` : '';
        return `${option?.display_name || option?.label || 'active 기본값'}${version}${source}${f1}`;
    }

    public async setRuntimeSelection(row: any, event: any) {
        const family = String(row?.family || '');
        if (!family || this.savingFamily) return;
        const modelId = String(event?.target?.value || '');
        this.savingFamily = family;
        this.uploadMessage = `${row?.family_label || family} 통합 조합을 저장하는 중입니다.`;
        this.uploadMessageType = 'info';
        await this.service.render();
        try {
            const params = new URLSearchParams();
            params.set('family', family);
            params.set('model_id', modelId);
            const res = await fetch(`/wiz/api/page.models/set_runtime_model_selection?${params.toString()}`, { method: 'POST' });
            const json = await this.readJsonResponse(res);
            if (json.code === 200) {
                this.uploadMessage = 'RF-Dual 통합 조합에 반영했습니다.';
                this.uploadMessageType = 'success';
                await this.loadRegistry();
            } else {
                this.uploadMessage = json.data?.message || json.message || '통합 조합 저장 실패';
                this.uploadMessageType = 'error';
            }
        } catch (e: any) {
            this.uploadMessage = e?.message || '통합 조합 저장 실패';
            this.uploadMessageType = 'error';
        }
        this.savingFamily = '';
        await this.service.render();
    }

    private currentRuntimeSelections(): any {
        const selections: any = {};
        for (const row of this.compositionRows()) {
            const family = String(row?.family || '');
            const modelId = String(row?.selected_model_id || '');
            if (family && modelId) selections[family] = modelId;
        }
        return selections;
    }

    public async saveRuntimeBundle() {
        if (this.bundleSaving) return;
        this.bundleSaving = true;
        this.uploadMessage = '현재 선택한 세부 모델 조합을 저장하는 중입니다.';
        this.uploadMessageType = 'info';
        await this.service.render();
        try {
            const params = new URLSearchParams();
            params.set('label', this.bundleLabel || '');
            params.set('selections', JSON.stringify(this.currentRuntimeSelections()));
            const res = await fetch(`/wiz/api/page.models/save_runtime_model_bundle?${params.toString()}`, { method: 'POST' });
            const json = await this.readJsonResponse(res);
            if (json.code === 200) {
                this.bundleLabel = '';
                this.uploadMessage = '선택한 모델 조합을 저장하고 적용했습니다.';
                this.uploadMessageType = 'success';
                await this.loadRegistry();
            } else {
                this.uploadMessage = json.data?.message || json.message || '모델 조합 저장 실패';
                this.uploadMessageType = 'error';
            }
        } catch (e: any) {
            this.uploadMessage = e?.message || '모델 조합 저장 실패';
            this.uploadMessageType = 'error';
        }
        this.bundleSaving = false;
        await this.service.render();
    }

    public async applyRuntimeBundle(bundle: any) {
        const bundleId = String(bundle?.bundle_id || '');
        if (!bundleId || this.applyingBundleId) return;
        this.applyingBundleId = bundleId;
        this.uploadMessage = `${bundle?.label || '모델 조합'} 적용 중입니다.`;
        this.uploadMessageType = 'info';
        await this.service.render();
        try {
            const params = new URLSearchParams();
            params.set('bundle_id', bundleId);
            const res = await fetch(`/wiz/api/page.models/apply_runtime_model_bundle?${params.toString()}`, { method: 'POST' });
            const json = await this.readJsonResponse(res);
            if (json.code === 200) {
                this.uploadMessage = '모델 조합을 적용했습니다.';
                this.uploadMessageType = 'success';
                await this.loadRegistry();
            } else {
                this.uploadMessage = json.data?.message || json.message || '모델 조합 적용 실패';
                this.uploadMessageType = 'error';
            }
        } catch (e: any) {
            this.uploadMessage = e?.message || '모델 조합 적용 실패';
            this.uploadMessageType = 'error';
        }
        this.applyingBundleId = '';
        await this.service.render();
    }

    public async deleteRuntimeBundle(bundle: any) {
        const bundleId = String(bundle?.bundle_id || '');
        if (!bundleId || this.deletingBundleId) return;
        this.deletingBundleId = bundleId;
        this.uploadMessage = `${bundle?.label || '모델 조합'} 삭제 중입니다.`;
        this.uploadMessageType = 'info';
        await this.service.render();
        try {
            const params = new URLSearchParams();
            params.set('bundle_id', bundleId);
            const res = await fetch(`/wiz/api/page.models/delete_runtime_model_bundle?${params.toString()}`, { method: 'POST' });
            const json = await this.readJsonResponse(res);
            const payload = this.responsePayload(json);
            if (json.code === 200) {
                this.uploadMessage = payload.delete_after ? `커스텀 최종 모델 삭제를 예약했습니다. 실제 삭제 예정: ${payload.delete_after}` : '커스텀 최종 모델 삭제를 예약했습니다.';
                this.uploadMessageType = 'success';
                await this.loadRegistry();
            } else {
                this.uploadMessage = json.data?.message || json.message || '모델 조합 삭제 실패';
                this.uploadMessageType = 'error';
            }
        } catch (e: any) {
            this.uploadMessage = e?.message || '모델 조합 삭제 실패';
            this.uploadMessageType = 'error';
        }
        this.deletingBundleId = '';
        await this.service.render();
    }

    public bundleSelectionText(bundle: any): string {
        const rows = Array.isArray(bundle?.selection_rows) ? bundle.selection_rows : [];
        if (rows.length === 0) return 'active 기본값 조합';
        return rows.map((row: any) => `${row.family_label}: ${row.display_version || '-'} ${row.label || ''}`.trim()).join(' / ');
    }

    public async cleanupCandidates() {
        if (this.cleanupBusy) return;
        this.cleanupBusy = true;
        this.uploadMessage = '낮은 우선순위 후보 모델 삭제 예약을 계산하는 중입니다.';
        this.uploadMessageType = 'info';
        await this.service.render();
        try {
            const params = new URLSearchParams();
            params.set('keep_per_family', '1');
            params.set('min_f1', '0.90');
            const res = await fetch(`/wiz/api/page.models/cleanup_model_candidates?${params.toString()}`, { method: 'POST' });
            const json = await this.readJsonResponse(res);
            const payload = this.responsePayload(json);
            if (json.code === 200) {
                const bad = Number(payload.low_score_count || 0);
                const extra = Number(payload.extra_count || 0);
                this.uploadMessage = `후보 정리 예약 완료: ${payload.scheduled_count || 0}개 · 저성능 ${bad}개 · 하위 후보 ${extra}개`;
                this.uploadMessageType = 'success';
                await this.loadRegistry();
            } else {
                this.uploadMessage = json.data?.message || json.message || '후보 정리 실패';
                this.uploadMessageType = 'error';
            }
        } catch (e: any) {
            this.uploadMessage = e?.message || '후보 정리 실패';
            this.uploadMessageType = 'error';
        }
        this.cleanupBusy = false;
        await this.service.render();
    }

    public sourceText(item: any): string {
        const source = String(item?.source || '');
        if (source === 'active') return '운영';
        if (source === 'custom-final') return '최종 모델';
        if (source === 'candidate') return '후보';
        if (source === 'uploaded') return '업로드';
        return source || '-';
    }

    public badgeClass(item: any): string {
        const source = String(item?.source || '');
        if (source === 'active') return 'bg-emerald-50 text-emerald-700 border-emerald-200';
        if (source === 'custom-final') return 'bg-indigo-50 text-indigo-700 border-indigo-200';
        if (source === 'candidate') return 'bg-amber-50 text-amber-700 border-amber-200';
        if (source === 'uploaded') return 'bg-sky-50 text-sky-700 border-sky-200';
        return 'bg-slate-50 text-slate-700 border-slate-200';
    }

    public manageBadgeClass(item: any): string {
        if (item?.deletable !== false) return 'bg-rose-50 text-rose-700 border-rose-200';
        return 'bg-zinc-50 text-zinc-500 border-zinc-200';
    }

    public occlusionLines(): string[] {
        return Array.isArray(this.registry?.occlusion_policy?.explanation) ? this.registry.occlusion_policy.explanation : [];
    }

    public occlusionTuningPlan(): string[] {
        return Array.isArray(this.registry?.occlusion_policy?.tuning_plan) ? this.registry.occlusion_policy.tuning_plan : [];
    }

    public occlusionStatusText(): string {
        return String(this.registry?.occlusion_policy?.training_status?.message || this.registry?.occlusion_policy?.training_status?.latest_log || '상태 확인 중');
    }

    public occlusionVersionText(): string {
        const status = this.registry?.occlusion_policy?.training_status || {};
        return String(status.active_version_text || status.training_version_text || '-');
    }

    public occlusionSequenceText(): string {
        const status = this.registry?.occlusion_policy?.training_status || {};
        const sequence = Number(status.best_sequence_macro_f1 || status.sequence_macro_f1 || 0);
        const window = Number(status.best_macro_f1 || status.active_macro_f1 || 0);
        const bits = [];
        if (sequence > 0) bits.push(`Sequence F1 ${(sequence * 100).toFixed(1)}%`);
        if (window > 0) bits.push(`Window F1 ${(window * 100).toFixed(1)}%`);
        return bits.join(' · ') || '-';
    }
}

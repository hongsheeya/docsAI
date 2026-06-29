// @ts-ignore WIZ build 단계에서 Angular import가 실제 컴포넌트 코드로 변환됩니다.
import { OnInit } from '@angular/core';
// @ts-ignore WIZ build 단계에서 서비스 경로가 실제 src/libs 경로로 재작성됩니다.
import { Service } from '@wiz/libs/portal/season/service';

declare const wiz: any;

export class Component implements OnInit {
    public prototypeInfo: any = null;
    public loadingInfo: boolean = true;

    constructor(public service: Service) { }

    public async ngOnInit() {
        await this.service.init(this);
        await this.loadPrototypeInfo();
    }

    public async loadPrototypeInfo() {
        this.loadingInfo = true;
        await this.service.render();
        const { code, data } = await wiz.call('prototype_info');
        if (code === 200) {
            this.prototypeInfo = data || null;
        }
        this.loadingInfo = false;
        await this.service.render();
    }

    public isAdminUser() {
        return this.service.auth?.check?.role('admin') === true;
    }

    public statusBadgeClass(status: string) {
        switch (String(status || '').toLowerCase()) {
            case 'ready':
            case 'always-on':
            case 'ready-now':
            case 'hybrid-summary-runtime':
            case 'trained-yolo-runtime':
            case 'pass':
                return 'bg-emerald-50 text-emerald-700 border border-emerald-200';
            case 'preview':
            case 'next':
            case 'phase-1-browser-streaming':
            case 'review':
                return 'bg-sky-50 text-sky-700 border border-sky-200';
            case 'fallback':
            case 'training-needed':
            case 'heuristic-fallback':
            case 'needs-review':
            case 'not-run':
                return 'bg-amber-50 text-amber-700 border border-amber-200';
            default:
                return 'bg-slate-100 text-slate-700 border border-slate-200';
        }
    }

    public diagnosticClass(severity: string) {
        switch (String(severity || '').toLowerCase()) {
            case 'warn':
            case 'warning':
                return 'bg-amber-50 text-amber-800 border border-amber-200';
            case 'error':
            case 'fail':
                return 'bg-rose-50 text-rose-800 border border-rose-200';
            default:
                return 'bg-slate-50 text-slate-700 border border-slate-200';
        }
    }

    public modelTrainingStats(): any[] {
        const stats = this.prototypeInfo?.dataset_summary?.model_training_stats;
        return Array.isArray(stats) ? stats : [];
    }

    public modelTrainingStat(key: string): any {
        return this.modelTrainingStats().find((item: any) => item?.key === key) || {};
    }

    public modelTrainingStatCards(): any[] {
        return this.modelTrainingStats().slice(0, 6);
    }

    public totalTrainingSamples(): number {
        const total = Number(this.prototypeInfo?.dataset_summary?.total_training_samples || 0);
        if (Number.isFinite(total) && total > 0) return total;
        return this.modelTrainingStats().reduce((sum: number, item: any) => sum + Number(item?.sample_count || 0), 0);
    }

    public percentText(value: any): string {
        const num = Number(value || 0);
        if (!Number.isFinite(num) || num <= 0) return '-';
        return `${(num * 100).toFixed(1)}%`;
    }

    public modelMetricText(item: any): string {
        const bits = [];
        if (item?.algorithm) bits.push(String(item.algorithm));
        const f1 = Number(item?.macro_f1 ?? item?.f1 ?? 0);
        const acc = Number(item?.accuracy ?? 0);
        const recall = Number(item?.recall ?? 0);
        const precision = Number(item?.precision ?? 0);
        if (Number.isFinite(f1) && f1 > 0) bits.push(`F1 ${(f1 * 100).toFixed(1)}%`);
        if (Number.isFinite(acc) && acc > 0) bits.push(`Acc ${(acc * 100).toFixed(1)}%`);
        if (Number.isFinite(recall) && recall > 0) bits.push(`Recall ${(recall * 100).toFixed(1)}%`);
        if (Number.isFinite(precision) && precision > 0) bits.push(`Precision ${(precision * 100).toFixed(1)}%`);
        return bits.join(' · ') || '-';
    }
}

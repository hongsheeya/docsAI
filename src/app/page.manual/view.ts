import { OnInit } from '@angular/core';
import { Service } from '@wiz/libs/portal/season/service';

declare const wiz: any;

export class Component implements OnInit {
    constructor(public service: Service) { }

    public activeSection: string = 'overview';
    public sidebarOpen: boolean = false;
    public prototypeInfo: any = null;

    public sections = [
        { id: 'overview', label: '서비스 소개', icon: 'home' },
        { id: 'login', label: '로그인', icon: 'login' },
        { id: 'dashboard', label: '영상 분석 (메인)', icon: 'analysis' },
        { id: 'upload', label: '업로드 분석', icon: 'upload' },
        { id: 'upload-guide', label: '업로드 파일/라벨 가이드', icon: 'upload' },
        { id: 'webcam', label: '실시간 웹캠 분석', icon: 'webcam' },
        { id: 'result', label: '분석 결과 보기', icon: 'result' },
        { id: 'feedback', label: '피드백 / 재학습', icon: 'feedback' },
        { id: 'alert', label: '위험 알림', icon: 'alert' },
        { id: 'pipeline', label: 'AI 파이프라인', icon: 'pipeline' },
        { id: 'model-training', label: 'RF/XGBoost/SHAP 재현', icon: 'pipeline' },
        { id: 'admin', label: '관리자 설정', icon: 'admin' },
        { id: 'faq', label: '자주 묻는 질문', icon: 'faq' },
    ];

    public async ngOnInit() {
        await this.service.init(this);
        await this.loadPrototypeInfo();
        await this.service.render();
    }

    public async loadPrototypeInfo() {
        try {
            const { code, data } = await wiz.call('prototype_info');
            if (code === 200) this.prototypeInfo = data || null;
        } catch (e) {
            this.prototypeInfo = null;
        }
    }

    public scrollTo(sectionId: string) {
        this.activeSection = sectionId;
        this.sidebarOpen = false;
        const el = document.getElementById('section-' + sectionId);
        if (el) {
            el.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
        this.service.render();
    }

    public toggleSidebar() {
        this.sidebarOpen = !this.sidebarOpen;
        this.service.render();
    }

    public isAdminUser() {
        return this.service.auth?.check?.role('admin') === true;
    }

    public goMain() {
        this.service.href('/');
    }

    public modelTrainingStats(): any[] {
        const stats = this.prototypeInfo?.dataset_summary?.model_training_stats;
        return Array.isArray(stats) ? stats : [];
    }

    public modelTrainingStat(key: string): any {
        return this.modelTrainingStats().find((item: any) => item?.key === key) || {};
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

    public totalTrainingSamples(): number {
        const total = Number(this.prototypeInfo?.dataset_summary?.total_training_samples || 0);
        if (Number.isFinite(total) && total > 0) return total;
        return this.modelTrainingStats().reduce((sum: number, item: any) => sum + Number(item?.sample_count || 0), 0);
    }
}

import { OnInit } from '@angular/core';
import { Service } from '@wiz/libs/portal/season/service';

export class Component implements OnInit {
    constructor(public service: Service) { }

    public activeSection: string = 'overview';
    public sidebarOpen: boolean = false;

    public sections = [
        { id: 'overview', label: '서비스 소개', icon: 'home' },
        { id: 'login', label: '로그인', icon: 'login' },
        { id: 'dashboard', label: '영상 분석 (메인)', icon: 'analysis' },
        { id: 'upload', label: '업로드 분석', icon: 'upload' },
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
        await this.service.init();
        await this.service.render();
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
}

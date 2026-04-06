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
        await this.service.init();
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
}

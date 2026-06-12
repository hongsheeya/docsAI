import { Component, OnInit, ChangeDetectorRef, enableProdMode } from '@angular/core';
import { Router } from '@angular/router';
import { Service } from '@wiz/libs/portal/season/service';
import { TranslateService } from '@ngx-translate/core';

@Component({
    selector: 'app-root',
    templateUrl: './app.component.html',
    styleUrls: ['./app.component.scss']
})
export class AppComponent implements OnInit {
    constructor(
        public service: Service,
        public router: Router,
        public ref: ChangeDetectorRef,
        public translate: TranslateService
    ) {
        this.installPostMessageOriginGuard();
        window['MonacoEnvironment'] = {
            getWorkerUrl: function (moduleId: string, label: string) {
                return `/lib/vs/base/worker/workerMain.js`;
            }
        };
    }

    private installPostMessageOriginGuard() {
        const legacyReviewOrigin = 'https://review.season.co.kr';
        const safeOriginFor = (targetWindow: Window): string => {
            try {
                return targetWindow?.location?.origin || window.location.origin;
            } catch (e) {
                try {
                    return window.location.origin;
                } catch (_) {
                    return '*';
                }
            }
        };
        const patchWindow = (target: Window) => {
            try {
                const proto: any = (target as any).Window?.prototype;
                if (!proto || proto.__docsAiPostMessageOriginGuard) return;
                const original = proto.postMessage;
                if (typeof original !== 'function') return;
                Object.defineProperty(proto, '__docsAiPostMessageOriginGuard', { value: true });
                proto.postMessage = function (message: any, targetOriginOrOptions: any, transfer?: any) {
                    if (targetOriginOrOptions === legacyReviewOrigin) {
                        const safeOrigin = safeOriginFor(this as Window);
                        if (transfer !== undefined) return original.call(this, message, safeOrigin, transfer);
                        return original.call(this, message, safeOrigin);
                    }
                    if (
                        targetOriginOrOptions &&
                        typeof targetOriginOrOptions === 'object' &&
                        targetOriginOrOptions.targetOrigin === legacyReviewOrigin
                    ) {
                        return original.call(this, message, { ...targetOriginOrOptions, targetOrigin: safeOriginFor(this as Window) });
                    }
                    return original.apply(this, arguments);
                };
            } catch (e) {
                // Cross-origin frames are intentionally ignored.
            }
        };

        patchWindow(window);
        try {
            if (window.parent && window.parent !== window) patchWindow(window.parent);
        } catch (e) {
            // Cross-origin parent access is intentionally ignored.
        }
        try {
            if (window.top && window.top !== window) patchWindow(window.top);
        } catch (e) {
            // Cross-origin top access is intentionally ignored.
        }
    }

    public async ngOnInit() {
        enableProdMode();
        await this.service.init(this);
    }
}

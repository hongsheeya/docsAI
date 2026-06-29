// @ts-ignore WIZ build 단계에서 Angular import가 실제 컴포넌트 코드로 변환됩니다.
import { OnInit } from '@angular/core';
// @ts-ignore WIZ build 단계에서 서비스 경로가 실제 src/libs 경로로 재작성됩니다.
import { Service } from '@wiz/libs/portal/season/service';

declare const wiz: any;

export class Component implements OnInit {
    public loading: boolean = true;
    public saving: boolean = false;
    public message: string = '';
    public apiKeyInput: string = '';
    public settings: any = {
        enabled: false,
        provider: 'openai',
        model: 'gpt-4.1',
        temperature: 0.1,
        max_output_tokens: 700,
        mode: 'advisory',
        prompt_policy: '',
        api_key_configured: false,
        api_key_masked: '',
        api_key_source: '',
    };

    constructor(public service: Service) { }

    public async ngOnInit() {
        await this.service.init(this);
        await this.loadSettings();
    }

    public async loadSettings() {
        this.loading = true;
        await this.service.render();
        const { code, data, message }: any = await wiz.call('settings');
        this.loading = false;
        if (code === 200) {
            this.applySettings(data || {});
        } else {
            this.message = this.errorMessage(code, message || data?.message, 'LLM 설정을 불러오지 못했습니다.');
        }
        await this.service.render();
    }

    public applySettings(data: any) {
        this.settings = {
            ...this.settings,
            ...(data || {}),
        };
        this.apiKeyInput = '';
    }

    public async saveSettings(clearKey: boolean = false) {
        this.saving = true;
        this.message = clearKey ? 'API Key를 삭제하는 중입니다.' : 'LLM 설정을 저장하는 중입니다.';
        await this.service.render();
        const { code, data, message }: any = await wiz.call('save_settings', {
            enabled: this.settings.enabled ? 'true' : 'false',
            model: this.settings.model || 'gpt-4.1',
            api_key: clearKey ? '' : (this.apiKeyInput || ''),
            api_key_action: clearKey ? 'clear' : '',
            temperature: String(this.settings.temperature ?? 0.1),
            max_output_tokens: String(this.settings.max_output_tokens ?? 700),
            mode: this.settings.mode || 'advisory',
            prompt_policy: this.settings.prompt_policy || '',
        });
        this.saving = false;
        if (code === 200) {
            this.applySettings(data || {});
            this.message = clearKey ? 'API Key가 삭제되었습니다.' : 'LLM 설정이 저장되었습니다.';
        } else {
            this.message = this.errorMessage(code, message || data?.message, 'LLM 설정 저장에 실패했습니다.');
        }
        await this.service.render();
    }

    public errorMessage(code: number, detail: string, fallback: string) {
        if (code === 401 || code === 403) {
            return '관리자 권한 세션이 만료되었거나 권한이 없습니다. 다시 로그인한 뒤 저장해주세요.';
        }
        if (detail) {
            return `${fallback} (${detail})`;
        }
        return fallback;
    }

    public statusClass() {
        if (this.settings?.enabled && this.settings?.api_key_configured) {
            return 'bg-emerald-50 text-emerald-700 border border-emerald-200';
        }
        if (this.settings?.enabled) {
            return 'bg-amber-50 text-amber-700 border border-amber-200';
        }
        return 'bg-slate-100 text-slate-700 border border-slate-200';
    }

    public statusLabel() {
        if (this.settings?.enabled && this.settings?.api_key_configured) return 'ready';
        if (this.settings?.enabled) return 'key required';
        return 'disabled';
    }
}

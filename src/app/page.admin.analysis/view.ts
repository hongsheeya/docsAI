// @ts-ignore WIZ build 단계에서 Angular import가 실제 컴포넌트 코드로 변환됩니다.
import { OnInit } from '@angular/core';
// @ts-ignore WIZ build 단계에서 서비스 경로가 실제 src/libs 경로로 재작성됩니다.
import { Service } from '@wiz/libs/portal/season/service';

declare const wiz: any;

export class Component implements OnInit {
    public prototypeInfo: any = null;
    public loadingInfo: boolean = true;
    public trainingFile: File | null = null;
    public trainingLabel: string = 'Y';
    public trainingNote: string = '';
    public intakeUploading: boolean = false;
    public intakeProgress: number = 0;
    public trainingMessage: string = '';
    public retraining: boolean = false;
    public guardianName: string = '보호자';
    public guardianPhone: string = '010-1234-5678';
    public guardians: any[] = [];
    public alertHistory: any = null;
    public alertHistoryLoading: boolean = false;
    public alertHistoryPage: number = 1;
    public smsGatewayEnabled: boolean = false;
    public smsProviderName: string = 'solapi';
    public smsWebhookUrl: string = '';
    public smsAuthToken: string = '';
    public smsAuthTokenMasked: string = '';
    public smsSender: string = '';
    public pushGatewayEnabled: boolean = false;
    public pushProviderName: string = 'fcm';
    public pushWebhookUrl: string = '';
    public pushAuthToken: string = '';
    public pushAuthTokenMasked: string = '';
    public pushTarget: string = '';
    public pushPlatform: string = 'fcm';
    public pushBundleId: string = '';
    public settingsSaving: boolean = false;
    public settingsMessage: string = '';

    constructor(public service: Service) { }

    public async ngOnInit() {
        await this.service.init(this);
        await this.loadPrototypeInfo();
        await this.loadAlertHistory();
    }

    public async loadPrototypeInfo() {
        this.loadingInfo = true;
        await this.service.render();
        const { code, data } = await wiz.call('prototype_info');
        if (code === 200) {
            this.prototypeInfo = data || null;
            this.applyAlertSettings(data?.alert_settings || null);
        }
        this.loadingInfo = false;
        await this.service.render();
    }

    public applyAlertSettings(settings: any) {
        if (!settings) return;
        const guardian = settings?.guardian || {};
        const sms = settings?.gateway?.sms || {};
        const push = settings?.gateway?.push || {};
        this.guardianName = guardian?.name || this.guardianName;
        this.guardianPhone = guardian?.phone || this.guardianPhone;
        this.guardians = (settings?.guardians || []).map((g: any) => ({...g}));
        if (this.guardians.length === 0 && this.guardianName) {
            this.guardians = [{ name: this.guardianName, phone: this.guardianPhone, enabled: true }];
        }
        this.smsGatewayEnabled = !!sms?.enabled;
        this.smsProviderName = sms?.provider_name || this.smsProviderName;
        this.smsWebhookUrl = sms?.webhook_url || '';
        this.smsAuthTokenMasked = sms?.auth_token_masked || '';
        this.smsSender = sms?.sender || '';
        this.pushGatewayEnabled = !!push?.enabled;
        this.pushProviderName = push?.provider_name || this.pushProviderName;
        this.pushWebhookUrl = push?.webhook_url || '';
        this.pushAuthTokenMasked = push?.auth_token_masked || '';
        this.pushTarget = push?.target || '';
        this.pushPlatform = push?.platform || this.pushPlatform;
        this.pushBundleId = push?.bundle_id || '';
    }

    public async saveAlertSettings() {
        this.settingsSaving = true;
        this.settingsMessage = '운영 알림 설정을 저장하는 중입니다.';
        await this.service.render();
        const { code, data, message }: any = await wiz.call('prototype_info', {
            action: 'save_alert_settings',
            guardian_name: this.guardianName || '보호자',
            guardian_phone: this.guardianPhone || '',
            sms_enabled: this.smsGatewayEnabled ? 'true' : 'false',
            sms_provider_name: this.smsProviderName || 'solapi',
            sms_webhook_url: this.smsWebhookUrl || '',
            sms_auth_token: this.smsAuthToken || '',
            sms_timeout_sec: '8',
            sms_sender: this.smsSender || '',
            push_enabled: this.pushGatewayEnabled ? 'true' : 'false',
            push_provider_name: this.pushProviderName || 'fcm',
            push_webhook_url: this.pushWebhookUrl || '',
            push_auth_token: this.pushAuthToken || '',
            push_timeout_sec: '8',
            push_target: this.pushTarget || '',
            push_platform: this.pushPlatform || 'fcm',
            push_bundle_id: this.pushBundleId || '',
        });
        this.settingsSaving = false;
        if (code === 200) {
            this.applyAlertSettings(data || null);
            this.smsAuthToken = '';
            this.pushAuthToken = '';
            this.settingsMessage = '운영 알림 설정이 저장되었습니다.';
            await this.loadPrototypeInfo();
        } else {
            this.settingsMessage = message || data?.message || '알림 설정 저장에 실패했습니다.';
        }
        await this.service.render();
    }

    public async onTrainingFileSelected(event: any) {
        this.trainingFile = event?.target?.files?.[0] || null;
        this.trainingMessage = this.trainingFile ? '학습 데이터 파일이 선택되었습니다.' : '';
        if (event?.target) event.target.value = '';
        await this.service.render();
    }

    public setTrainingLabel(label: string) {
        this.trainingLabel = label;
    }

    public async submitTrainingSample() {
        if (!this.trainingFile) {
            this.trainingMessage = '등록할 학습 영상 파일을 선택해주세요.';
            await this.service.render();
            return;
        }
        this.intakeUploading = true;
        this.intakeProgress = 0;
        this.trainingMessage = '학습 데이터를 업로드합니다.';
        await this.service.render();
        const fd = new FormData();
        fd.append('video', this.trainingFile);
        fd.append('label', this.trainingLabel);
        fd.append('note', this.trainingNote || '');
        fd.append('metadata', JSON.stringify({ size: this.trainingFile.size }));
        let response: any = await this.service.file.upload('/wiz/api/page.admin.analysis/submit_training_sample', fd, async (percent: number) => {
            this.intakeProgress = percent;
            this.trainingMessage = percent < 100 ? `학습 데이터 업로드 중... ${percent.toFixed(0)}%` : '업로드 완료';
            await this.service.render();
        });
        if (typeof response === 'string') {
            try {
                response = JSON.parse(response);
            } catch (e) {
                response = { code: 500, data: { message: response } };
            }
        }
        this.intakeUploading = false;
        if (response?.code === 200) {
            this.trainingMessage = '학습 데이터가 등록되었습니다.';
            this.trainingFile = null;
            this.trainingNote = '';
            await this.loadPrototypeInfo();
        } else {
            this.trainingMessage = response?.data?.message || response?.message || '학습 데이터 등록에 실패했습니다.';
        }
        await this.service.render();
    }

    public async retrainBaseline() {
        this.retraining = true;
        this.trainingMessage = '베이스라인 모델을 재학습합니다.';
        await this.service.render();
        const { code, data, message }: any = await wiz.call('retrain_baseline');
        this.retraining = false;
        if (code === 200) {
            this.trainingMessage = '베이스라인 재학습이 완료되었습니다.';
            this.prototypeInfo = { ...(this.prototypeInfo || {}), baseline_training: data };
            await this.loadPrototypeInfo();
        } else {
            this.trainingMessage = message || data?.message || '재학습에 실패했습니다.';
        }
        await this.service.render();
    }

    public addGuardian() {
        this.guardians.push({ name: '', phone: '', enabled: true });
    }

    public removeGuardian(index: number) {
        this.guardians.splice(index, 1);
    }

    public async saveGuardians() {
        this.settingsSaving = true;
        this.settingsMessage = '보호자 목록을 저장하는 중입니다.';
        await this.service.render();
        const { code, data, message }: any = await wiz.call('save_guardians', {
            guardians: JSON.stringify(this.guardians),
        });
        this.settingsSaving = false;
        if (code === 200) {
            this.applyAlertSettings(data || null);
            this.settingsMessage = '보호자 목록이 저장되었습니다.';
            await this.loadPrototypeInfo();
        } else {
            this.settingsMessage = message || data?.message || '보호자 목록 저장에 실패했습니다.';
        }
        await this.service.render();
    }

    public async loadAlertHistory(page: number = 1) {
        this.alertHistoryLoading = true;
        this.alertHistoryPage = page;
        await this.service.render();
        const { code, data }: any = await wiz.call('alert_history', { page: String(page), page_size: '10' });
        this.alertHistoryLoading = false;
        if (code === 200) {
            this.alertHistory = data || null;
        }
        await this.service.render();
    }

    public riskBadgeClass(level: string) {
        switch (String(level || '').toLowerCase()) {
            case 'high': return 'bg-rose-50 text-rose-700 border border-rose-200';
            case 'medium': return 'bg-amber-50 text-amber-700 border border-amber-200';
            default: return 'bg-emerald-50 text-emerald-700 border border-emerald-200';
        }
    }

    public guardianStatusLabel(status: string) {
        switch (String(status || '')) {
            case 'sent': return '전송 완료';
            case 'send-failed': return '전송 실패';
            case 'missing-config': return '미설정';
            case 'disabled': return '미발송';
            default: return status || '-';
        }
    }

    public healthClass(status: string) {
        switch (status) {
            case 'healthy':
            case 'pass':
                return 'bg-emerald-50 text-emerald-700 border border-emerald-200';
            case 'monitor':
            case 'warn':
                return 'bg-amber-50 text-amber-700 border border-amber-200';
            case 'action-required':
            case 'fail':
                return 'bg-rose-50 text-rose-700 border border-rose-200';
            default:
                return 'bg-gray-50 text-gray-700 border border-gray-200';
        }
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
            case 'heuristic-fallback':
            case 'needs-review':
            case 'training-needed':
            case 'not-run':
                return 'bg-amber-50 text-amber-700 border border-amber-200';
            default:
                return 'bg-gray-50 text-gray-700 border border-gray-200';
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
                return 'bg-gray-50 text-gray-700 border border-gray-200';
        }
    }

}

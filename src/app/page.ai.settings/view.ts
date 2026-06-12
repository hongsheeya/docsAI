import { OnInit } from '@angular/core';
import { Service } from '@wiz/libs/portal/season/service';

export class Component implements OnInit {
    constructor(public service: Service) { }

    // ── AI 설정 ──
    public configs: any[] = [];
    public editMode: boolean = false;
    public formData: any = {
        provider: 'openai',
        model_name: 'gpt-5.4-mini',
        api_key: '',
        endpoint: '',
        is_active: false,
        extra_json: {}
    };
    public editId: string = '';
    public testing: boolean = false;
    public togglingConfigId: string = '';
    public testResult: any = null;

    // ── 프로필 메모리 ──
    public activeTab: string = 'config';
    public profileData: any = {};
    public profileKeys: string[] = [];
    public newProfileKey: string = '';
    public newProfileValue: string = '';
    public editingProfileKey: string = '';
    public editingProfileValue: string = '';

    // ── 인스트럭션 ──
    public instructions: any[] = [];
    public instructionEditMode: boolean = false;
    public instructionEditId: string = '';
    public instructionForm: any = { title: '', content: '', category: 'general', is_active: false };
    public categoryFilter: string = 'all';
    public categories = [
        { value: 'general', label: '전체 공통' },
        { value: 'fill', label: '필드 채우기' },
        { value: 'section', label: '섹션 작성' }
    ];

    public providers = [
        { value: 'openai', label: 'OpenAI', models: ['gpt-5.4-mini', 'gpt-5.3', 'gpt-5.2', 'gpt-5.1', 'gpt-5', 'gpt-4.1', 'gpt-4.1-mini', 'gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'gpt-3.5-turbo'] },
        { value: 'anthropic', label: 'Anthropic', models: ['claude-sonnet-4-20250514', 'claude-3-5-haiku-20241022', 'claude-opus-4-20250514'] },
        { value: 'google', label: 'Google', models: ['gemini-2.0-flash', 'gemini-1.5-pro'] },
        { value: 'custom', label: 'Custom', models: [] }
    ];

    public async ngOnInit() {
        await this.service.init();
        await this.load();
        await this.loadProfile();
        await this.loadInstructions();
    }

    // ── AI 설정 CRUD ──

    public async load() {
        let { code, data } = await wiz.call("list");
        if (code === 200) {
            this.configs = data || [];
        }
        await this.service.render();
    }

    public getProviderLabel(value: string) {
        let p = this.providers.find(x => x.value === value);
        return p ? p.label : value;
    }

    public getModels() {
        let p = this.providers.find(x => x.value === this.formData.provider);
        return p ? p.models : [];
    }

    public onProviderChange() {
        let models = this.getModels();
        if (models.length > 0) {
            this.formData.model_name = models[0];
        } else {
            this.formData.model_name = '';
        }
    }

    public openCreate() {
        this.editMode = false;
        this.editId = '';
        this.formData = {
            provider: 'openai',
            model_name: 'gpt-5.4-mini',
            api_key: '',
            endpoint: '',
            is_active: false,
            extra_json: {}
        };
        this.testResult = null;
    }

    public openEdit(config: any) {
        this.editMode = true;
        this.editId = config.id;
        this.formData = {
            provider: config.provider || 'openai',
            model_name: config.model_name === 'gpt-5.4' ? 'gpt-5.4-mini' : (config.model_name || ''),
            api_key: '',
            endpoint: config.endpoint || '',
            is_active: config.is_active || false,
            extra_json: config.extra_json || {}
        };
        this.testResult = null;
    }

    public async save() {
        if (!this.formData.provider) {
            await this.service.modal.show({ title: '', message: 'Provider를 선택해주세요.', cancel: false, action: '확인', status: 'error' });
            return;
        }
        if (!this.formData.model_name) {
            await this.service.modal.show({ title: '', message: '모델명을 입력해주세요.', cancel: false, action: '확인', status: 'error' });
            return;
        }

        let payload: any = { ...this.formData };
        payload.extra_json = JSON.stringify(payload.extra_json || {});

        if (this.editMode) {
            payload.id = this.editId;
            if (!payload.api_key) delete payload.api_key;
            let { code, data } = await wiz.call("update", payload);
            if (code === 200) {
                await this.load();
            } else {
                await this.service.modal.show({ title: '', message: data?.message || '저장 실패', cancel: false, action: '확인', status: 'error' });
            }
        } else {
            if (!payload.api_key) {
                await this.service.modal.show({ title: '', message: 'API Key를 입력해주세요.', cancel: false, action: '확인', status: 'error' });
                return;
            }
            let { code, data } = await wiz.call("create", payload);
            if (code === 200) {
                await this.load();
            } else {
                await this.service.modal.show({ title: '', message: data?.message || '생성 실패', cancel: false, action: '확인', status: 'error' });
            }
        }
        await this.service.render();
    }

    public async remove(id: string) {
        let res = await this.service.modal.show({
            title: '',
            message: '이 AI 설정을 삭제하시겠습니까?',
            action: '삭제',
            actionBtn: 'error',
            status: 'error'
        });
        if (!res) return;
        let { code } = await wiz.call("delete", { id });
        if (code === 200) await this.load();
    }

    public async setActive(id: string) {
        let { code } = await wiz.call("set_active", { id });
        if (code === 200) await this.load();
    }

    public async toggleActive(config: any) {
        if (!config?.id || this.togglingConfigId) return;
        this.togglingConfigId = config.id;
        await this.service.render();

        let { code, data } = await wiz.call("toggle_active", { id: config.id });
        this.togglingConfigId = '';

        if (code === 200) {
            await this.load();
        } else {
            await this.service.modal.show({
                title: '',
                message: data?.message || '활성 상태 변경 실패',
                cancel: false,
                action: '확인',
                status: 'error'
            });
        }
        await this.service.render();
    }

    public async testConnection() {
        if (!this.formData.api_key && !this.editMode) {
            await this.service.modal.show({ title: '', message: 'API Key를 입력해주세요.', cancel: false, action: '확인', status: 'error' });
            return;
        }
        this.testing = true;
        this.testResult = null;
        await this.service.render();

        let payload: any = {
            provider: this.formData.provider,
            model_name: this.formData.model_name,
            api_key: this.formData.api_key,
            endpoint: this.formData.endpoint
        };
        if (this.editMode) payload.config_id = this.editId;

        let { code, data } = await wiz.call("test_connection", payload);
        this.testing = false;
        this.testResult = { success: code === 200, message: data?.message || (code === 200 ? '연결 성공' : '연결 실패') };
        await this.service.render();
    }

    // ── 프로필 메모리 관리 ──

    public async loadProfile() {
        let { code, data } = await wiz.call("get_profile");
        if (code === 200) {
            this.profileData = data?.profile_data || {};
            this.profileKeys = Object.keys(this.profileData);
        }
        await this.service.render();
    }

    public async addProfileKey() {
        if (!this.newProfileKey.trim()) return;
        let { code, data } = await wiz.call("update_profile_key", {
            key: this.newProfileKey.trim(),
            value: this.newProfileValue.trim()
        });
        if (code === 200) {
            this.newProfileKey = '';
            this.newProfileValue = '';
            await this.loadProfile();
        } else {
            await this.service.modal.show({ title: '', message: data?.message || '추가 실패', cancel: false, action: '확인', status: 'error' });
        }
        await this.service.render();
    }

    public startEditProfile(key: string) {
        this.editingProfileKey = key;
        this.editingProfileValue = this.profileData[key] || '';
        this.service.render();
    }

    public cancelEditProfile() {
        this.editingProfileKey = '';
        this.editingProfileValue = '';
        this.service.render();
    }

    public async saveProfileKey() {
        if (!this.editingProfileKey) return;
        let { code } = await wiz.call("update_profile_key", {
            key: this.editingProfileKey,
            value: this.editingProfileValue
        });
        if (code === 200) {
            this.editingProfileKey = '';
            this.editingProfileValue = '';
            await this.loadProfile();
        }
        await this.service.render();
    }

    public async deleteProfileKey(key: string) {
        let res = await this.service.modal.show({
            title: '',
            message: `'${key}' 항목을 삭제하시겠습니까?`,
            action: '삭제',
            actionBtn: 'error'
        });
        if (!res) return;
        let { code } = await wiz.call("delete_profile_key", { key });
        if (code === 200) {
            await this.loadProfile();
        }
        await this.service.render();
    }

    public async clearAllProfile() {
        let res = await this.service.modal.show({
            title: '',
            message: 'AI가 기억한 모든 정보를 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.',
            action: '전체 삭제',
            actionBtn: 'error',
            status: 'error'
        });
        if (!res) return;
        let { code } = await wiz.call("clear_profile");
        if (code === 200) {
            await this.loadProfile();
        }
        await this.service.render();
    }

    // ── 인스트럭션 관리 ──

    public async loadInstructions() {
        let { code, data } = await wiz.call("list_instructions");
        if (code === 200) {
            this.instructions = data || [];
        }
        await this.service.render();
    }

    public get filteredInstructions() {
        if (this.categoryFilter === 'all') return this.instructions;
        return this.instructions.filter((i: any) => i.category === this.categoryFilter);
    }

    public getCategoryLabel(value: string) {
        let c = this.categories.find(x => x.value === value);
        return c ? c.label : value;
    }

    public openCreateInstruction() {
        this.instructionEditMode = false;
        this.instructionEditId = '';
        this.instructionForm = { title: '', content: '', category: 'general', is_active: false };
        this.service.render();
    }

    public openEditInstruction(inst: any) {
        this.instructionEditMode = true;
        this.instructionEditId = inst.id;
        this.instructionForm = {
            title: inst.title || '',
            content: inst.content || '',
            category: inst.category || 'general',
            is_active: inst.is_active || false
        };
        this.service.render();
    }

    public async saveInstruction() {
        if (!this.instructionForm.title.trim()) {
            await this.service.modal.show({ title: '', message: '제목을 입력해주세요.', cancel: false, action: '확인', status: 'error' });
            return;
        }
        if (!this.instructionForm.content.trim()) {
            await this.service.modal.show({ title: '', message: '내용을 입력해주세요.', cancel: false, action: '확인', status: 'error' });
            return;
        }

        if (this.instructionEditMode) {
            let { code, data } = await wiz.call("update_instruction", {
                id: this.instructionEditId,
                title: this.instructionForm.title,
                content: this.instructionForm.content,
                category: this.instructionForm.category
            });
            if (code !== 200) {
                await this.service.modal.show({ title: '', message: data?.message || '수정 실패', cancel: false, action: '확인', status: 'error' });
                return;
            }
        } else {
            let { code, data } = await wiz.call("create_instruction", {
                title: this.instructionForm.title,
                content: this.instructionForm.content,
                category: this.instructionForm.category,
                is_active: this.instructionForm.is_active ? 'true' : 'false'
            });
            if (code !== 200) {
                await this.service.modal.show({ title: '', message: data?.message || '생성 실패', cancel: false, action: '확인', status: 'error' });
                return;
            }
        }
        this.openCreateInstruction();
        await this.loadInstructions();
    }

    public async deleteInstruction(id: string) {
        let res = await this.service.modal.show({
            title: '',
            message: '이 인스트럭션을 삭제하시겠습니까?',
            action: '삭제',
            actionBtn: 'error',
            status: 'error'
        });
        if (!res) return;
        let { code } = await wiz.call("delete_instruction", { id });
        if (code === 200) await this.loadInstructions();
    }

    public async toggleInstruction(id: string) {
        let { code } = await wiz.call("toggle_instruction", { id });
        if (code === 200) await this.loadInstructions();
    }
}

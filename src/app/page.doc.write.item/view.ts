import { OnInit, OnDestroy } from '@angular/core';
import { Router, NavigationEnd } from '@angular/router';
import { Service } from '@wiz/libs/portal/season/service';

export class Component implements OnInit, OnDestroy {
    public WizRoute: any;
    private routerSub: any;

    constructor(public service: Service, private router: Router) { }

    public id: string = '';
    public tab: string = 'settings';
    public instance: any = null;
    public sections: any[] = [];
    public folders: any[] = [];
    public loading: boolean = true;
    public previewPanePercent: number = 68;
    public resizingReviewPane: boolean = false;

    // Step 1 — 설정
    public settingsForm: any = {
        week_label: '',
        deadline: '',
        guide_notes: '',
        report_items_text: ''
    };
    public referenceFiles: File[] = [];
    public existingReferenceFiles: any[] = [];
    public existingReferenceFileNames: string[] = [];
    public referenceDocs: any[] = [];
    public selectedReferenceDocIds: string[] = [];

    // 인스트럭션
    public instructions: any[] = [];
    public selectedInstructionIds: string[] = [];

    // Step 2 — 자동 생성
    public generating: boolean = false;
    public generateProgress: number = 0;
    public generateLogs: any[] = [];
    public expandedLogIndices: Set<number> = new Set();
    public followupQuestions: string[] = [];
    public followupMissingFields: string[] = [];
    public followupAnswers: any = {};
    public activeFollowupQuestion: string = '';
    public followupAnswerDraft: string = '';
    public followupAnswerSaving: boolean = false;

    // Step 3 — 검토
    public reviewTab: string = 'overview';
    public chatMessages: any[] = [];
    public chatInput: string = '';
    public chatLoading: boolean = false;
    public chatComposing: boolean = false;
    public editingSection: any = null;
    public editContent: string = '';

    // 양식 편집 (Field editor)
    public fieldValues: any = {};
    public fieldStyles: any = {};
    public tableFills: any[] = [];
    public fieldGroups: any[] = [];  // [{groupType, label, fields:[]}]
    public editingFieldLabel: string = '';
    public editingFieldValue: string = '';
    public editingFieldStyle: any = {
        font_family: 'gothic',
        font_size: 9,
        bold: false,
        align: 'left',
        color: '#080808'
    };
    public fieldImageUploadingLabel: string = '';
    public regenOutputLoading: boolean = false;
    public regenOutputLogs: string[] = [];

    // AI 채팅 — 섹션 컨텍스트
    public chatContextSection: any = null;

    // AI 채팅 — 이미지 첨부
    public chatImageFile: File | null = null;

    // 빠른 프롬프트
    public quickPrompts: string[] = [
        '이 섹션을 더 구체적으로 작성해줘',
        '전문적인 어조로 다시 작성해줘',
        '핵심 내용을 요약해줘',
        '이 부분에 데이터/수치를 추가해줘',
        '문법과 맞춤법을 교정해줘'
    ];

    // 섹션 인라인 수정 요청
    public inlineEditSectionId: string = '';
    public inlineEditInstruction: string = '';
    public inlineEditLoading: boolean = false;

    // PDF 미리보기
    public previewMode: string = 'direct';
    public settingsPreviewSource: string = '';
    public settingsPreviewUrl: string = '';
    public settingsPreviewOptions: any[] = [];
    public pdfPreviewUrl: string = '';
    public directEditorUrl: string = '';
    public downloadingPdf: boolean = false;
    public downloadingDocx: boolean = false;
    public downloadingHwp: boolean = false;

    // 이미지/그래프
    public images: any[] = [];
    public chartPrompt: string = '';
    public chartGenerating: boolean = false;
    public uploadingImage: boolean = false;
    public chartCsvFile: File | null = null;

    // 이미지 배치
    public imagePositions: string[] = [];
    public imagePlacements: any = {};
    public imagePlacementDetails: any = {};
    public manualImageDrafts: any = {};

    private directEditorMessageHandler = async (event: any) => {
        if (!event?.data || typeof event.data !== 'object') return;
        if (event.data.type === 'wiz-direct-editor-saved') {
            const appId = 'page.doc.write.item';
            this.pdfPreviewUrl = `/wiz/api/${appId}/preview_pdf?id=${this.id}&t=${Date.now()}`;
        }
        if (event.data.type === 'wiz-refresh-preview') {
            this.refreshPreview();
        }
    };
    private reviewPaneMoveHandler = (event: MouseEvent) => {
        if (!this.resizingReviewPane) return;
        const container = document.getElementById('reviewSplitPane');
        if (!container) return;
        const rect = container.getBoundingClientRect();
        const pct = ((event.clientX - rect.left) / rect.width) * 100;
        this.previewPanePercent = Math.max(30, Math.min(85, pct));
    };
    private reviewPaneUpHandler = () => {
        if (!this.resizingReviewPane) return;
        this.resizingReviewPane = false;
        this.service.render();
    };

    // Steps 정의
    public steps = [
        { key: 'settings', label: '설정', number: 1 },
        { key: 'generate', label: '자동 생성', number: 2 },
        { key: 'review', label: '검토/수정', number: 3 }
    ];

    public async ngOnInit() {
        await this.service.init();
        window.addEventListener('message', this.directEditorMessageHandler);
        window.addEventListener('mousemove', this.reviewPaneMoveHandler);
        window.addEventListener('mouseup', this.reviewPaneUpHandler);
        this.id = WizRoute.segment.id;
        this.tab = WizRoute.segment.tab || 'settings';

        if (!this.id) {
            this.service.href('/doc/write');
            return;
        }

        this.routerSub = this.router.events.subscribe(async (event: any) => {
            if (event instanceof NavigationEnd) {
                const newTab = WizRoute.segment.tab || 'settings';
                if (newTab !== this.tab) {
                    this.tab = newTab;
                    if (this.tab === 'review') {
                        await this.loadSections();
                        await this.loadChats();
                        await this.loadImages();
                        await this.loadFieldValues();
                        this.showDirectPreview();
                    }
                    await this.service.render();
                }
            }
        });

        await this.loadInstance();
        await this.loadFolders();
        await this.loadReferenceDocs();
        await this.loadInstructions();
        if (this.tab === 'review') {
            await this.loadSections();
            await this.loadChats();
            await this.loadImages();
            await this.loadFieldValues();
            this.showDirectPreview();
        }
        this.loading = false;
        await this.service.render();
    }

    ngOnDestroy() {
        window.removeEventListener('message', this.directEditorMessageHandler);
        window.removeEventListener('mousemove', this.reviewPaneMoveHandler);
        window.removeEventListener('mouseup', this.reviewPaneUpHandler);
        if (this.routerSub) this.routerSub.unsubscribe();
    }

    public startReviewPaneResize(event: MouseEvent) {
        this.resizingReviewPane = true;
        event.preventDefault();
    }

    public async loadInstance() {
        let { code, data } = await wiz.call("detail", { id: this.id });
        if (code === 200) {
            this.instance = data;
            let settings = data?.settings_json || {};
            this.settingsForm.week_label = data?.week_label || '';
            this.settingsForm.deadline = data?.deadline || '';
            this.settingsForm.guide_notes = settings?.guide_notes || '';
            this.settingsForm.report_items_text = Array.isArray(settings?.report_items) ? settings.report_items.join('\n') : '';
            this.selectedReferenceDocIds = Array.isArray(settings?.reference_doc_ids) ? [...settings.reference_doc_ids] : [];
            this.selectedInstructionIds = Array.isArray(settings?.instruction_ids)
                ? settings.instruction_ids.map((id: any) => String(id))
                : [];
            this.existingReferenceFiles = Array.isArray(settings?.reference_files) ? [...settings.reference_files] : [];
            this.existingReferenceFileNames = Array.isArray(settings?.reference_file_names) ? [...settings.reference_file_names] : [];
            this.followupQuestions = Array.isArray(data?.content_json?.followup_questions) ? [...data.content_json.followup_questions] : [];
            this.followupMissingFields = Array.isArray(data?.content_json?.missing_fields) ? [...data.content_json.missing_fields] : [];
            this.followupAnswers = data?.content_json?.followup_answers && typeof data.content_json.followup_answers === 'object'
                ? { ...data.content_json.followup_answers }
                : {};
            this.rebuildSettingsPreviewOptions();
        } else {
            this.service.href('/doc/write');
        }
    }

    public hasTemplatePreview() {
        const cj = this.instance?.content_json || {};
        const schema = cj?.fields_schema || {};
        return !!(
            cj?.template_id ||
            cj?.template_file_path ||
            cj?.uploaded_file ||
            cj?.editable_docx_path ||
            schema?.editable_docx_path ||
            schema?.converted_docx_path
        );
    }

    public rebuildSettingsPreviewOptions() {
        const options: any[] = [];
        if (this.hasTemplatePreview()) {
            options.push({ value: 'template', label: '기본 양식', type: 'template' });
        }
        for (const file of this.existingReferenceFiles || []) {
            const filename = file?.filename || '';
            if (!filename) continue;
            options.push({
                value: `reference-file:${filename}`,
                label: `참고자료: ${file.original_name || filename}`,
                type: 'reference-file'
            });
        }
        for (const doc of this.referenceDocs || []) {
            const docId = doc?.id || '';
            if (!docId) continue;
            options.push({
                value: `reference-doc:${docId}`,
                label: `이전 문서: ${doc.title || doc.week_label || docId}`,
                type: 'reference-doc'
            });
        }

        this.settingsPreviewOptions = options;
        if (!options.some(option => option.value === this.settingsPreviewSource)) {
            this.settingsPreviewSource = options[0]?.value || '';
        }
        this.refreshSettingsPreviewUrl(false);
    }

    public refreshSettingsPreviewUrl(render: boolean = true) {
        if (!this.id || !this.settingsPreviewSource) {
            this.settingsPreviewUrl = '';
            return;
        }

        const appId = 'page.doc.write.item';
        const t = Date.now();
        if (this.settingsPreviewSource === 'template') {
            this.settingsPreviewUrl = `/wiz/api/${appId}/template_preview_pdf?id=${this.id}&t=${t}`;
        } else if (this.settingsPreviewSource.startsWith('reference-file:')) {
            const filename = this.settingsPreviewSource.replace('reference-file:', '');
            this.settingsPreviewUrl = `/wiz/api/${appId}/reference_file_preview?id=${this.id}&filename=${encodeURIComponent(filename)}&t=${t}`;
        } else if (this.settingsPreviewSource.startsWith('reference-doc:')) {
            const docId = this.settingsPreviewSource.replace('reference-doc:', '');
            this.settingsPreviewUrl = `/wiz/api/${appId}/reference_doc_preview?id=${encodeURIComponent(docId)}&t=${t}`;
        } else {
            this.settingsPreviewUrl = '';
        }

        if (render) this.service.render();
    }

    public async loadReferenceDocs() {
        let { code, data } = await wiz.call("reference_docs", { id: this.id });
        if (code === 200) {
            this.referenceDocs = data || [];
            this.rebuildSettingsPreviewOptions();
        }
    }

    public async loadInstructions() {
        let { code, data } = await wiz.call("list_instructions");
        if (code === 200) {
            this.instructions = Array.isArray(data)
                ? data.map((inst: any) => ({ ...inst, id: String(inst.id) }))
                : [];
        }
    }

    public isInstructionSelected(id: string) {
        return this.selectedInstructionIds.includes(String(id));
    }

    public async toggleInstructionSelect(id: string) {
        const normalizedId = String(id);
        if (this.selectedInstructionIds.includes(normalizedId)) {
            this.selectedInstructionIds = this.selectedInstructionIds.filter(x => x !== normalizedId);
        } else {
            this.selectedInstructionIds = [...this.selectedInstructionIds, normalizedId];
        }
        await this.service.render();
    }

    public async loadFolders() {
        let { code, data } = await wiz.call('folders');
        if (code === 200) {
            this.folders = data || [];
        }
    }

    public async loadSections() {
        let { code, data } = await wiz.call("sections", { instance_id: this.id });
        if (code === 200) {
            this.sections = data || [];
        }
    }

    public async loadFieldValues() {
        let { code, data } = await wiz.call("get_field_values", { id: this.id });
        if (code !== 200) return;
        this.fieldValues = data?.field_values || {};
        this.fieldStyles = data?.field_styles || {};
        this.tableFills = data?.table_fills || [];
        this.fieldGroups = this._buildFieldGroups(this.tableFills, this.fieldValues, this.fieldStyles);
    }

    /**
     * tableFills + fieldValues → [{groupType:'서두'|'본문'|'결론', label, fields:[{label,value,fill}]}]
     */
    private _buildFieldGroups(fills: any[], values: any, styles: any): any[] {
        if (!fills || fills.length === 0) return [];

        // 1) 반복 row_group 갯수 집계
        const rowGroupCounts: Record<string, number> = {};
        for (const f of fills) {
            const lbl = f.label || '';
            const m = lbl.match(/^(.+?)\s*[>│|]\s*/);
            const grp = m ? m[1] : '';
            if (grp) rowGroupCounts[grp] = (rowGroupCounts[grp] || 0) + 1;
        }

        // 2) groupType 분류
        const classifyField = (f: any): string => {
            const lbl = (f.label || '').toLowerCase();
            if (f.type === 'key_value') return '서두';
            if (/주차|week|회차|수업일/.test(lbl)) return '본문';
            if (/평가|소견|종합|결론|특이|의견|총평|comment/.test(lbl)) return '결론';
            const m = f.label.match(/^(.+?)\s*[>│|]\s*/);
            const grp = m ? m[1] : '';
            if (grp && rowGroupCounts[grp] > 1) return '본문';
            return '기타';
        };

        const groups: Record<string, any> = {};
        for (const f of fills) {
            const gt = classifyField(f);
            if (!groups[gt]) groups[gt] = { groupType: gt, label: gt, fields: [] };
            groups[gt].fields.push({
                label: f.label,
                fill: f,
                value: values[f.label] ?? '',
                style: this.normalizeFieldStyle(styles?.[f.label])
            });
        }

        // 정렬: 서두 → 본문 → 결론 → 기타
        const order = ['서두', '본문', '결론', '기타'];
        return order.filter(k => groups[k]).map(k => groups[k]);
    }

    public normalizeFieldStyle(style: any) {
        return {
            font_family: ['gothic', 'myeongjo', 'batang', 'mono'].includes(style?.font_family) ? style.font_family : 'gothic',
            font_size: Number(style?.font_size || 9),
            bold: !!style?.bold,
            align: ['left', 'center', 'right'].includes(style?.align) ? style.align : 'left',
            color: /^#[0-9a-fA-F]{6}$/.test(style?.color || '') ? style.color : '#080808'
        };
    }

    public startFieldEdit(label: string, current: string, style?: any) {
        this.editingFieldLabel = label;
        this.editingFieldValue = current;
        this.editingFieldStyle = this.normalizeFieldStyle(style || this.fieldStyles[label]);
    }

    public cancelFieldEdit() {
        this.editingFieldLabel = '';
        this.editingFieldValue = '';
        this.editingFieldStyle = this.normalizeFieldStyle({});
    }

    public async saveFieldEdit() {
        if (!this.editingFieldLabel) return;
        this.fieldValues[this.editingFieldLabel] = this.editingFieldValue;
        this.fieldStyles[this.editingFieldLabel] = this.normalizeFieldStyle(this.editingFieldStyle);
        // 그룹 내 값 즉시 반영
        for (const g of this.fieldGroups) {
            for (const f of g.fields) {
                if (f.label === this.editingFieldLabel) {
                    f.value = this.editingFieldValue;
                    f.style = this.normalizeFieldStyle(this.editingFieldStyle);
                }
            }
        }
        await wiz.call("save_field_value", {
            id: this.id,
            label: this.editingFieldLabel,
            content: this.editingFieldValue,
            style: JSON.stringify(this.normalizeFieldStyle(this.editingFieldStyle))
        });
        this.editingFieldLabel = '';
        this.editingFieldValue = '';
        this.editingFieldStyle = this.normalizeFieldStyle({});
        this.refreshPreview();
        await this.service.render();
    }

    public async insertImageForField(field: any, event: any) {
        const file = event?.target?.files?.[0];
        if (event?.target) event.target.value = '';
        if (!file || !field?.label) return;

        this.fieldImageUploadingLabel = field.label;
        await this.service.render();

        const uploadForm = new FormData();
        uploadForm.append('instance_id', this.id);
        uploadForm.append('file', file);

        const uploadRes = await wiz.call("upload_image", uploadForm, { processData: false, contentType: false });
        if (uploadRes.code !== 200) {
            this.fieldImageUploadingLabel = '';
            await this.service.modal.show({ title: '', message: uploadRes.data?.message || '이미지 업로드 실패', cancel: false, action: '확인', status: 'error' });
            await this.service.render();
            return;
        }

        const uploaded = uploadRes.data?.filename ? uploadRes.data : (uploadRes.data?.data || uploadRes.data || {});
        const filename = uploaded?.filename || uploaded?.file_name || '';
        if (!filename) {
            this.fieldImageUploadingLabel = '';
            await this.service.modal.show({ title: '', message: '업로드된 이미지 정보를 찾지 못했습니다.', cancel: false, action: '확인', status: 'error' });
            await this.service.render();
            return;
        }

        const placeRes = await wiz.call("save_image_placement", {
            instance_id: this.id,
            filename,
            position: field.label,
            insert_mode: 'below'
        });

        this.fieldImageUploadingLabel = '';
        if (placeRes.code === 200) {
            await this.loadImages();
            await this.loadImagePositions();
            this.refreshPreview();
        } else {
            await this.service.modal.show({ title: '', message: placeRes.data?.message || '이미지 삽입 위치 저장 실패', cancel: false, action: '확인', status: 'error' });
        }
        await this.service.render();
    }

    public async regenOutput() {
        if (this.regenOutputLoading) return;
        this.regenOutputLoading = true;
        this.regenOutputLogs = [];
        await this.service.render();
        const formData = new FormData();
        formData.append('id', this.id);
        try {
            const response = await fetch(`/wiz/api/page.doc.write.item/regenerate_output`, { method: 'POST', body: formData });
            const reader = response.body!.getReader();
            const decoder = new TextDecoder();
            let buf = '';
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buf += decoder.decode(value, { stream: true });
                const parts = buf.split('\n\n');
                buf = parts.pop() || '';
                for (const part of parts) {
                    if (!part.startsWith('data: ')) continue;
                    try {
                        const ev = JSON.parse(part.slice(6));
                        if (ev.message) this.regenOutputLogs.push(ev.message);
                        if (ev.type === 'done' || ev.type === 'error') {
                            this.regenOutputLoading = false;
                            if (ev.type === 'done') await this.loadSections();
                        }
                    } catch (_) {}
                }
                await this.service.render();
            }
        } catch (e: any) {
            this.regenOutputLogs.push(`오류: ${e?.message || e}`);
        }
        this.regenOutputLoading = false;
        await this.service.render();
    }

    public async loadChats() {
        let { code, data } = await wiz.call("chats", { instance_id: this.id });
        if (code === 200) {
            this.chatMessages = data || [];
        }
    }

    public async loadImages() {
        let { code, data } = await wiz.call("list_images", { instance_id: this.id });
        if (code === 200) {
            this.images = data || [];
        }
        // 배치 정보도 로드
        await this.loadImagePositions();
    }

    public async loadImagePositions() {
        let { code, data } = await wiz.call("get_image_positions", { instance_id: this.id });
        if (code === 200) {
            this.imagePositions = data?.positions || [];
            this.imagePlacements = data?.placements || {};
            this.imagePlacementDetails = data?.placement_details || {};
            this.manualImageDrafts = {};
        }
    }

    public goStep(key: string) {
        this.service.href(`/doc/write/${this.id}/${key}`);
    }

    public stepIndex(key: string) {
        return this.steps.findIndex(s => s.key === key);
    }

    public isStepActive(key: string) {
        return this.tab === key;
    }

    public isStepDone(key: string) {
        return this.stepIndex(key) < this.stepIndex(this.tab);
    }

    // ── Step 1: 설정 저장 ──

    public onRefFileSelect(event: any) {
        const files = Array.from(event.target.files || []) as File[];
        if (files.length > 0) {
            this.referenceFiles = files;
        }
        this.service.render();
    }

    public clearReferenceFiles() {
        this.referenceFiles = [];
        this.service.render();
    }

    public removeExistingReferenceFile(file: any) {
        this.existingReferenceFiles = this.existingReferenceFiles.filter((item: any) => item.filename !== file.filename);
        this.existingReferenceFileNames = this.existingReferenceFiles.map((item: any) => item.original_name || item.filename);
        this.rebuildSettingsPreviewOptions();
        this.service.render();
    }

    public isReferenceDocSelected(id: string) {
        return this.selectedReferenceDocIds.includes(id);
    }

    public async toggleReferenceDoc(id: string) {
        if (this.selectedReferenceDocIds.includes(id)) {
            this.selectedReferenceDocIds = this.selectedReferenceDocIds.filter(docId => docId !== id);
        } else {
            this.selectedReferenceDocIds = [...this.selectedReferenceDocIds, id];
        }
        await this.service.render();
    }

    public async saveSettings() {
        let fd = new FormData();
        fd.append('id', this.id);
        fd.append('title', this.instance?.title || '');
        fd.append('status', this.instance?.status || '');
        fd.append('folder_id', this.instance?.folder_id || '');
        fd.append('week_label', this.settingsForm.week_label);
        fd.append('deadline', this.settingsForm.deadline);
        fd.append('guide_notes', this.settingsForm.guide_notes);
        const reportItems = (this.settingsForm.report_items_text || '')
            .split('\n')
            .map((item: string) => item.trim())
            .filter((item: string) => !!item);
        fd.append('report_items', JSON.stringify(reportItems));
        fd.append('reference_doc_ids', JSON.stringify(this.selectedReferenceDocIds));
        fd.append('instruction_ids', JSON.stringify(this.selectedInstructionIds));
        fd.append('keep_reference_files', JSON.stringify(this.existingReferenceFiles.map((item: any) => item.filename)));
        if (this.referenceFiles.length > 0) {
            for (const file of this.referenceFiles) {
                fd.append('reference_file', file);
            }
        }

        let { code, data } = await wiz.call("save_settings", fd, { processData: false, contentType: false });
        if (code === 200) {
            await this.service.modal.show({ title: '', message: '변경사항이 저장되었습니다.', cancel: false, action: '확인', status: 'success' });
            this.referenceFiles = [];
            await this.loadInstance();
            return true;
        } else {
            await this.service.modal.show({ title: '', message: data?.message || '저장 실패', cancel: false, action: '확인', status: 'error' });
        }
        await this.service.render();
        return false;
    }

    public async goToGenerate() {
        let saved = await this.saveSettings();
        if (saved) {
            this.goStep('generate');
        }
    }

    public async deleteDoc() {
        let ok = await this.service.modal.show({
            title: '',
            message: '이 문서를 삭제하시겠습니까?',
            action: '삭제',
            actionBtn: 'error',
            status: 'error'
        });
        if (!ok) return;
        let { code, data } = await wiz.call('delete_instance', { id: this.id });
        if (code === 200) {
            this.service.href('/doc/write');
            return;
        }
        await this.service.modal.show({ title: '', message: data?.message || '문서 삭제 실패', cancel: false, action: '확인', status: 'error' });
    }

    // ── Step 2: 자동 생성 ──

    public async startGenerate() {
        this.generating = true;
        this.generateProgress = 0;
        this.generateLogs = [{type: 'text', message: 'AI 문서 생성을 시작합니다...'}];
        this.expandedLogIndices = new Set();
        this.followupQuestions = [];
        this.followupMissingFields = [];
        this.activeFollowupQuestion = '';
        this.followupAnswerDraft = '';
        await this.service.render();

        try {
            const formData = new FormData();
            formData.append('id', this.id);

            const appId = 'page.doc.write.item';
            const response = await fetch(
                `/wiz/api/${appId}/generate`,
                { method: 'POST', body: formData }
            );

            const reader = response.body!.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n\n');
                buffer = lines.pop() || '';

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const event = JSON.parse(line.slice(6));
                            if (event.type === 'progress') {
                                this.generateProgress = event.progress || 0;
                                if (event.message) this.generateLogs.push({type: 'text', message: event.message});
                            } else if (event.type === 'section') {
                                this.generateLogs.push({type: 'section', title: event.title, index: event.index});
                            } else if (event.type === 'prompt') {
                                this.generateLogs.push(event);
                            } else if (event.type === 'ai_response') {
                                this.generateLogs.push(event);
                            } else if (event.type === 'detail') {
                                this.generateLogs.push(event);
                            } else if (event.type === 'needs_input') {
                                this.followupQuestions = Array.isArray(event.questions) ? [...event.questions] : [];
                                this.followupMissingFields = Array.isArray(event.missing_fields) ? [...event.missing_fields] : [];
                                this.generateLogs.push({ type: 'detail', message: event.message || '추가 정보 확인이 필요합니다.' });
                            } else if (event.type === 'done') {
                                this.generateProgress = 100;
                                this.generateLogs.push({type: 'text', message: '✅ 문서 생성이 완료되었습니다!'});
                            } else if (event.type === 'error') {
                                this.generateLogs.push({type: 'error', message: event.message});
                            }
                            this.scrollLogToBottom();
                            await this.service.render();
                        } catch (e) { }
                    }
                }
            }
        } catch (e: any) {
            this.generateLogs.push({type: 'error', message: `오류 발생: ${e.message || e}`});
        }

        this.generating = false;
        await this.service.render();
    }

    public toggleLogExpand(index: number) {
        if (this.expandedLogIndices.has(index)) {
            this.expandedLogIndices.delete(index);
        } else {
            this.expandedLogIndices.add(index);
        }
        this.service.render();
    }

    private scrollLogToBottom() {
        setTimeout(() => {
            const el = document.querySelector('.generate-log-container');
            if (el) el.scrollTop = el.scrollHeight;
        }, 50);
    }

    public async goToReview() {
        this.reviewTab = 'fields';
        this.showDirectPreview();
        this.goStep('review');
    }

    public async goToReviewChat() {
        this.reviewTab = 'chat';
        this.showDirectPreview();
        this.goStep('review');
        await this.service.render();
    }

    public async useFollowupQuestion(question: string) {
        this.activeFollowupQuestion = question;
        this.followupAnswerDraft = this.followupAnswers?.[question] || '';
        await this.service.render();
    }

    public cancelFollowupAnswer() {
        this.activeFollowupQuestion = '';
        this.followupAnswerDraft = '';
        this.service.render();
    }

    public hasFollowupAnswer(question: string) {
        return !!String(this.followupAnswers?.[question] || '').trim();
    }

    public async saveFollowupAnswer() {
        if (!this.activeFollowupQuestion || !this.followupAnswerDraft.trim()) return false;

        this.followupAnswerSaving = true;
        await this.service.render();

        let { code, data } = await wiz.call('save_followup_answer', {
            id: this.id,
            question: this.activeFollowupQuestion,
            answer: this.followupAnswerDraft.trim()
        });

        this.followupAnswerSaving = false;

        if (code === 200) {
            this.followupAnswers = data?.followup_answers && typeof data.followup_answers === 'object'
                ? { ...data.followup_answers }
                : { ...this.followupAnswers, [this.activeFollowupQuestion]: this.followupAnswerDraft.trim() };
            this.settingsForm.guide_notes = data?.guide_notes || this.settingsForm.guide_notes;
            this.generateLogs.push({
                type: 'detail',
                message: `추가 답변 저장됨: ${this.activeFollowupQuestion}`
            });
            await this.service.render();
            return true;
        }

        await this.service.modal.show({ title: '', message: data?.message || '답변 저장 실패', cancel: false, action: '확인', status: 'error' });
        await this.service.render();
        return false;
    }

    public async saveFollowupAnswerAndRestart() {
        const saved = await this.saveFollowupAnswer();
        if (!saved) return;
        this.activeFollowupQuestion = '';
        this.followupAnswerDraft = '';
        await this.startGenerate();
    }

    // ── Step 3: 검토/수정 — 채팅 ──

    public setChatContext(section: any) {
        if (this.chatContextSection?.id === section?.id) {
            this.chatContextSection = null;
        } else {
            this.chatContextSection = section;
        }
        this.service.render();
    }

    public clearChatContext() {
        this.chatContextSection = null;
        this.service.render();
    }

    // 채팅 이미지 첨부
    public onChatImageSelect(event: any) {
        const file = event.target.files[0];
        if (file) {
            this.chatImageFile = file;
        }
        this.service.render();
    }

    public clearChatImage() {
        this.chatImageFile = null;
        this.service.render();
    }

    public onChatCompositionStart() {
        this.chatComposing = true;
    }

    public onChatCompositionEnd(event: any) {
        this.chatComposing = false;
        if (event?.target) {
            this.chatInput = event.target.value || '';
        }
    }

    public onChatKeydown(event: KeyboardEvent) {
        if (event.key !== 'Enter') return;
        if (this.chatComposing || event.isComposing || (event as any).keyCode === 229) return;
        event.preventDefault();
        const inputValue = (event.target as HTMLInputElement)?.value || this.chatInput;
        this.sendChat(undefined, inputValue);
    }

    public async sendChat(promptText?: string, inputValue?: string) {
        if (this.chatLoading) return;
        let msg = promptText ? promptText.trim() : (inputValue ?? this.chatInput).trim();
        if (!msg && !this.chatImageFile) return;

        if (this.chatContextSection) {
            msg = `[${this.chatContextSection.section_title}] 섹션에 대해: ${msg}`;
        }

        let displayMsg = msg;
        if (this.chatImageFile) {
            displayMsg += `\n📎 ${this.chatImageFile.name}`;
        }

        this.chatMessages.push({ role: 'user', content: displayMsg });
        this.chatInput = '';
        this.chatLoading = true;
        await this.service.render();

        // FormData로 전송 (이미지 포함 가능) - fetch() 직접 사용 (wiz.call은 multipart 미지원)
        const fd = new FormData();
        fd.append('instance_id', this.id);
        fd.append('message', msg);
        if (this.chatContextSection) {
            fd.append('section_id', this.chatContextSection.id);
        }
        if (this.chatImageFile) {
            fd.append('image', this.chatImageFile);
        }

        let code = 200;
        let data: any = {};
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 90000);
        try {
            const response = await fetch(`/wiz/api/page.doc.write.item/chat`, { method: 'POST', body: fd, signal: controller.signal });
            code = response.status;
            data = await response.json().catch(() => ({}));
        } catch (e: any) {
            code = 500;
            data = { message: e?.name === 'AbortError' ? 'AI 응답 시간이 초과되었습니다. 요청을 조금 짧게 나눠 다시 시도해주세요.' : (e?.message || '네트워크 오류') };
        } finally {
            clearTimeout(timeout);
        }
        this.chatLoading = false;
        this.chatImageFile = null;
        const payload = data?.data || data || {};
        const resultCode = Number(data?.code || code);

        if (resultCode === 200) {
            this.chatMessages.push({ role: 'assistant', content: payload?.reply || '응답을 받지 못했습니다.' });

            // AI가 섹션을 수정한 경우 → 미리보기 갱신
            if (payload?.content_modified) {
                await this.loadSections();
                this.refreshPreview();
            }

            // 이미지가 업로드된 경우 → 이미지 목록 갱신
            if (payload?.uploaded_image) {
                await this.loadImages();
            }
        } else {
            this.chatMessages.push({ role: 'assistant', content: `오류: ${payload?.message || data?.message || '처리 실패'}` });
        }
        await this.service.render();
    }

    public async useQuickPrompt(prompt: string) {
        await this.sendChat(prompt);
    }

    // ── Step 3: 검토/수정 — 섹션 직접 편집 ──

    public startEditSection(section: any) {
        this.editingSection = section;
        this.editContent = section.content || '';
        this.service.render();
    }

    public cancelEdit() {
        this.editingSection = null;
        this.editContent = '';
        this.service.render();
    }

    public async saveSection() {
        if (!this.editingSection) return;
        let { code } = await wiz.call("save_section", {
            id: this.editingSection.id,
            content: this.editContent
        });
        if (code === 200) {
            this.editingSection.content = this.editContent;
            this.editingSection = null;
            this.editContent = '';
            await this.loadSections();
            this.refreshPreview();
        }
        await this.service.render();
    }

    // ── Step 3: 검토/수정 — AI 재작성 ──

    public async regenerateSection(section: any) {
        let res = await this.service.modal.show({
            title: '',
            message: `'${section.section_title}' 섹션을 AI로 다시 작성하시겠습니까?`,
            action: '재생성',
            actionBtn: 'warning'
        });
        if (!res) return;

        section._regenerating = true;
        await this.service.render();

        let { code, data } = await wiz.call("regenerate_section", {
            instance_id: this.id,
            section_id: section.id
        });

        section._regenerating = false;
        if (code === 200) {
            await this.loadSections();
            this.refreshPreview();
        } else {
            await this.service.modal.show({ title: '', message: data?.message || '재생성 실패', cancel: false, action: '확인', status: 'error' });
        }
        await this.service.render();
    }

    // ── Step 3: 검토/수정 — 인라인 AI 수정 요청 ──

    public showInlineEdit(section: any) {
        this.inlineEditSectionId = section.id;
        this.inlineEditInstruction = '';
        this.service.render();
    }

    public cancelInlineEdit() {
        this.inlineEditSectionId = '';
        this.inlineEditInstruction = '';
        this.service.render();
    }

    public async submitInlineEdit(section: any) {
        if (!this.inlineEditInstruction.trim()) return;

        this.inlineEditLoading = true;
        await this.service.render();

        let { code, data } = await wiz.call("regenerate_section", {
            instance_id: this.id,
            section_id: section.id,
            instruction: this.inlineEditInstruction
        });

        this.inlineEditLoading = false;
        this.inlineEditSectionId = '';
        this.inlineEditInstruction = '';

        if (code === 200) {
            await this.loadSections();
            this.refreshPreview();
        } else {
            await this.service.modal.show({ title: '', message: data?.message || '수정 실패', cancel: false, action: '확인', status: 'error' });
        }
        await this.service.render();
    }

    // ── 미리보기 모드 전환 + 갱신 ──

    private showDirectPreview() {
        this.previewMode = 'direct';
        const appId = 'page.doc.write.item';
        this.directEditorUrl = `/wiz/api/${appId}/direct_editor_html?id=${this.id}&t=${Date.now()}`;
    }

    public togglePreviewMode(mode: string) {
        this.previewMode = mode;
        const appId = 'page.doc.write.item';
        if (mode === 'pdf') {
            this.pdfPreviewUrl = `/wiz/api/${appId}/preview_pdf?id=${this.id}&t=${Date.now()}`;
        } else if (mode === 'direct') {
            this.directEditorUrl = `/wiz/api/${appId}/direct_editor_html?id=${this.id}&t=${Date.now()}`;
        }
        this.service.render();
    }

    public refreshPreview() {
        const appId = 'page.doc.write.item';
        if (this.previewMode === 'pdf') {
            this.pdfPreviewUrl = `/wiz/api/${appId}/preview_pdf?id=${this.id}&t=${Date.now()}`;
        } else if (this.previewMode === 'direct') {
            this.directEditorUrl = `/wiz/api/${appId}/direct_editor_html?id=${this.id}&t=${Date.now()}`;
        }
        this.service.render();
    }

    // ── PDF/DOCX 다운로드 ──

    public async downloadPdf() {
        this.downloadingPdf = true;
        await this.service.render();

        try {
            const appId = 'page.doc.write.item';
            const formData = new FormData();
            formData.append('id', this.id);
            const response = await fetch(`/wiz/api/${appId}/download_pdf`, {
                method: 'POST', body: formData
            });
            if (response.ok) {
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `${this.instance?.title || '문서'}.pdf`;
                a.click();
                window.URL.revokeObjectURL(url);
            } else {
                await this.service.modal.show({ title: '', message: 'PDF 생성 실패', cancel: false, action: '확인', status: 'error' });
            }
        } catch (e) {
            await this.service.modal.show({ title: '', message: 'PDF 다운로드 오류', cancel: false, action: '확인', status: 'error' });
        }

        this.downloadingPdf = false;
        await this.service.render();
    }

    public async downloadDocx() {
        this.downloadingDocx = true;
        await this.service.render();

        try {
            const appId = 'page.doc.write.item';
            const formData = new FormData();
            formData.append('id', this.id);
            const response = await fetch(`/wiz/api/${appId}/download_docx`, {
                method: 'POST', body: formData
            });
            if (response.ok) {
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `${this.instance?.title || '문서'}.docx`;
                a.click();
                window.URL.revokeObjectURL(url);
            } else {
                await this.service.modal.show({ title: '', message: 'DOCX 생성 실패', cancel: false, action: '확인', status: 'error' });
            }
        } catch (e) {
            await this.service.modal.show({ title: '', message: 'DOCX 다운로드 오류', cancel: false, action: '확인', status: 'error' });
        }

        this.downloadingDocx = false;
        await this.service.render();
    }

    public async downloadHwp() {
        this.downloadingHwp = true;
        await this.service.render();

        try {
            const appId = 'page.doc.write.item';
            const formData = new FormData();
            formData.append('id', this.id);
            const response = await fetch(`/wiz/api/${appId}/download_hwp`, {
                method: 'POST', body: formData
            });
            if (response.ok) {
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                const disposition = response.headers.get('Content-Disposition') || response.headers.get('content-disposition') || '';
                const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i);
                const plain = disposition.match(/filename="?([^";]+)"?/i);
                let filename = `${this.instance?.title || '문서'}.hwpx`;
                if (encoded && encoded[1]) filename = decodeURIComponent(encoded[1]);
                else if (plain && plain[1]) filename = plain[1];
                a.download = filename;
                a.click();
                window.URL.revokeObjectURL(url);
            } else {
                await this.service.modal.show({ title: '', message: 'HWPX 생성 실패', cancel: false, action: '확인', status: 'error' });
            }
        } catch (e) {
            await this.service.modal.show({ title: '', message: 'HWPX 다운로드 오류', cancel: false, action: '확인', status: 'error' });
        }

        this.downloadingHwp = false;
        await this.service.render();
    }

    // ── 이미지 업로드 ──

    public async onImageUpload(event: any) {
        const file = event.target.files[0];
        if (!file) return;

        this.uploadingImage = true;
        await this.service.render();

        let fd = new FormData();
        fd.append('instance_id', this.id);
        fd.append('file', file);

        let { code, data } = await wiz.call("upload_image", fd, { processData: false, contentType: false });
        this.uploadingImage = false;

        if (code === 200) {
            await this.loadImages();
        } else {
            await this.service.modal.show({ title: '', message: data?.message || '업로드 실패', cancel: false, action: '확인', status: 'error' });
        }
        await this.service.render();
    }

    public async deleteImage(img: any) {
        let res = await this.service.modal.show({
            title: '',
            message: '이미지를 삭제하시겠습니까?',
            action: '삭제',
            actionBtn: 'danger'
        });
        if (!res) return;

        let { code } = await wiz.call("delete_image", {
            instance_id: this.id,
            filename: img.filename
        });
        if (code === 200) {
            await this.loadImages();
            this.refreshPreview();
        }
        await this.service.render();
    }

    public getImageUrl(img: any) {
        const appId = 'page.doc.write.item';
        return `/wiz/api/${appId}/get_image?instance_id=${this.id}&filename=${img.filename}`;
    }

    // ── 이미지 배치 ──

    public getImagePlacement(filename: string): string {
        const detail = this.getPlacementDetail(filename);
        if (detail?.insert_mode === 'absolute') {
            return `직접 위치 ${detail.page || 1}p`;
        }
        for (const [pos, files] of Object.entries(this.imagePlacements)) {
            if (Array.isArray(files) && (files as string[]).includes(filename)) {
                if (pos === '__absolute__') return '직접 위치';
                return pos;
            }
        }
        return '';
    }

    public getPlacementDetail(filename: string): any {
        for (const [pos, items] of Object.entries(this.imagePlacementDetails || {})) {
            if (!Array.isArray(items)) continue;
            const found = (items as any[]).find(item => item?.filename === filename);
            if (found) return { ...found, position: pos };
        }
        return null;
    }

    public getImageDraft(filename: string): any {
        if (!this.manualImageDrafts[filename]) {
            const detail = this.getPlacementDetail(filename);
            this.manualImageDrafts[filename] = {
                page: Number(detail?.page || 1),
                x_pct: Number(detail?.x_pct ?? 8),
                y_pct: Number(detail?.y_pct ?? 8),
                w_pct: Number(detail?.w_pct ?? 32),
                h_pct: Number(detail?.h_pct ?? 20),
                insert_mode: detail?.insert_mode && detail.insert_mode !== 'absolute' ? detail.insert_mode : 'below'
            };
        }
        return this.manualImageDrafts[filename];
    }

    public async placeImage(img: any, position: string, insertMode: string = 'below') {
        if (!position) return;
        let { code, data } = await wiz.call("save_image_placement", {
            instance_id: this.id,
            filename: img.filename,
            position: position,
            insert_mode: insertMode || 'below'
        });
        if (code === 200) {
            this.imagePlacements = data?.placements || data || {};
            await this.loadImagePositions();
            this.refreshPreview();
        }
        await this.service.render();
    }

    public async placeImageAbsolute(img: any) {
        const draft = this.getImageDraft(img.filename);
        let { code, data } = await wiz.call("save_image_placement", {
            instance_id: this.id,
            filename: img.filename,
            position: '__absolute__',
            insert_mode: 'absolute',
            page: draft.page,
            x_pct: draft.x_pct,
            y_pct: draft.y_pct,
            w_pct: draft.w_pct,
            h_pct: draft.h_pct
        });
        if (code === 200) {
            this.imagePlacements = data?.placements || data || {};
            await this.loadImagePositions();
            this.refreshPreview();
        }
        await this.service.render();
    }

    public async unplaceImage(img: any) {
        let { code, data } = await wiz.call("remove_image_placement", {
            instance_id: this.id,
            filename: img.filename
        });
        if (code === 200) {
            this.imagePlacements = data?.placements || data || {};
            await this.loadImagePositions();
            this.refreshPreview();
        }
        await this.service.render();
    }

    // ── AI 그래프 생성 ──

    public async generateChart() {
        if (!this.chartPrompt.trim() && !this.chartCsvFile) return;

        this.chartGenerating = true;
        await this.service.render();

        let code = 0;
        let data: any = null;
        if (this.chartCsvFile) {
            let fd = new FormData();
            fd.append('instance_id', this.id);
            fd.append('prompt', this.chartPrompt || 'CSV 실험 데이터 그래프를 MATLAB 스타일로 생성');
            fd.append('file', this.chartCsvFile);
            let res = await wiz.call("generate_chart", fd, { processData: false, contentType: false });
            code = res.code;
            data = res.data;
        } else {
            let res = await wiz.call("generate_chart", {
                instance_id: this.id,
                prompt: this.chartPrompt
            });
            code = res.code;
            data = res.data;
        }

        this.chartGenerating = false;

        if (code === 200) {
            this.chartPrompt = '';
            this.chartCsvFile = null;
            await this.loadImages();
        } else {
            await this.service.modal.show({ title: '', message: data?.message || '그래프 생성 실패', cancel: false, action: '확인', status: 'error' });
        }
        await this.service.render();
    }

    public onChartCsvSelect(event: any) {
        const file = event.target.files[0];
        if (!file) return;
        const ext = file.name.split('.').pop()?.toLowerCase();
        if (ext !== 'csv') {
            this.service.modal.show({ title: '', message: 'CSV 파일만 업로드 가능합니다.', cancel: false, action: '확인', status: 'error' });
            return;
        }
        this.chartCsvFile = file;
        this.service.render();
    }

    public clearChartCsv() {
        this.chartCsvFile = null;
        this.service.render();
    }

    public sectionStatusLabel(status: string) {
        let map: any = { pending: '대기', writing: '작성중', done: '완료' };
        return map[status] || status;
    }

    public sectionStatusClass(status: string) {
        let map: any = {
            pending: 'bg-zinc-100 text-zinc-600',
            writing: 'bg-amber-100 text-amber-700',
            done: 'bg-green-100 text-green-700'
        };
        return map[status] || 'bg-zinc-100 text-zinc-600';
    }
}

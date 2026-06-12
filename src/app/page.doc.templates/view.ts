import { OnInit, ChangeDetectorRef } from '@angular/core';
import { Service } from '@wiz/libs/portal/season/service';

export class Component implements OnInit {
    constructor(public service: Service, private cdr: ChangeDetectorRef) { }

    public templates: any[] = [];
    public showModal: boolean = false;
    public editMode: boolean = false;
    public editId: string = '';
    public formData: any = { title: '', description: '' };
    public selectedFile: File | null = null;
    public referenceFiles: File[] = [];
    public existingReferenceFiles: any[] = [];
    public uploading: boolean = false;
    public editTemplateInfo: any = null;
    public expandedTemplateId: string = '';
    public reanalyzingId: string = '';

    public async ngOnInit() {
        await this.service.init();
        await this.load();
    }

    public async load() {
        let { code, data } = await wiz.call("list");
        if (code === 200) {
            this.templates = data || [];
        }
        await this.service.render();
    }

    public async openCreate() {
        this.editMode = false;
        this.editId = '';
        this.formData = { title: '', description: '' };
        this.selectedFile = null;
        this.referenceFiles = [];
        this.existingReferenceFiles = [];
        this.editTemplateInfo = null;
        this.showModal = true;
        this.cdr.detectChanges();
        await this.service.render();
    }

    public async openEdit(tpl: any) {
        this.editMode = true;
        this.editId = tpl.id;
        this.formData = { title: tpl.title, description: tpl.description || '' };
        this.selectedFile = null;
        this.referenceFiles = [];
        this.existingReferenceFiles = Array.isArray(tpl?.fields_schema?.reference_files)
            ? [...tpl.fields_schema.reference_files]
            : [];
        this.editTemplateInfo = tpl;
        this.showModal = true;
        this.cdr.detectChanges();
        await this.service.render();
    }

    public async closeModal() {
        this.showModal = false;
        this.editTemplateInfo = null;
        this.referenceFiles = [];
        this.existingReferenceFiles = [];
        this.cdr.detectChanges();
        await this.service.render();
    }

    public onFileSelect(event: any) {
        let file = event.target.files[0];
        if (file) {
            let ext = file.name.split('.').pop()?.toLowerCase();
            if (!['hwp', 'doc', 'docx'].includes(ext || '')) {
                this.service.modal.show({ title: '', message: 'HWP, DOC, DOCX 파일만 업로드 가능합니다.', cancel: false, action: '확인', status: 'error' });
                return;
            }
            this.selectedFile = file;
        }
        this.service.render();
    }

    public onReferenceFileSelect(event: any) {
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

    public removeExistingReference(file: any) {
        this.existingReferenceFiles = this.existingReferenceFiles.filter((item: any) => item.filename !== file.filename);
        this.service.render();
    }

    public async save() {
        if (!this.formData.title) {
            await this.service.modal.show({ title: '', message: '양식 이름을 입력해주세요.', cancel: false, action: '확인', status: 'error' });
            return;
        }

        this.uploading = true;
        await this.service.render();

        let fd = new FormData();
        fd.append('title', this.formData.title);
        fd.append('description', this.formData.description || '');
        fd.append('keep_reference_files', JSON.stringify(this.existingReferenceFiles.map((item: any) => item.filename)));
        if (this.referenceFiles.length > 0) {
            for (const file of this.referenceFiles) {
                fd.append('reference_file', file);
            }
        }

        if (this.editMode) {
            fd.append('id', this.editId);
            if (this.selectedFile) fd.append('file', this.selectedFile);
            let { code, data } = await wiz.call("update", fd, { processData: false, contentType: false });
            if (code !== 200) {
                this.uploading = false;
                await this.service.modal.show({ title: '', message: data?.message || '수정 실패', cancel: false, action: '확인', status: 'error' });
                await this.service.render();
                return;
            }
        } else {
            if (!this.selectedFile) {
                this.uploading = false;
                await this.service.modal.show({ title: '', message: '양식 파일을 업로드해주세요.', cancel: false, action: '확인', status: 'error' });
                await this.service.render();
                return;
            }
            fd.append('file', this.selectedFile);
            let { code, data } = await wiz.call("create", fd, { processData: false, contentType: false });
            if (code !== 200) {
                this.uploading = false;
                await this.service.modal.show({ title: '', message: data?.message || '등록 실패', cancel: false, action: '확인', status: 'error' });
                await this.service.render();
                return;
            }
        }

        this.uploading = false;
        this.showModal = false;
        this.editTemplateInfo = null;
        this.referenceFiles = [];
        this.existingReferenceFiles = [];
        await this.load();
    }

    public async remove(id: string) {
        let res = await this.service.modal.show({
            title: '',
            message: '이 양식을 삭제하시겠습니까?',
            action: '삭제',
            actionBtn: 'error',
            status: 'error'
        });
        if (!res) return;
        let { code } = await wiz.call("delete", { id });
        if (code === 200) await this.load();
    }

    public async reanalyze(tpl: any, event?: any) {
        if (event) event.stopPropagation();
        this.reanalyzingId = tpl.id;
        await this.service.render();

        let { code, data } = await wiz.call("reanalyze", { id: tpl.id });
        this.reanalyzingId = '';

        if (code === 200) {
            tpl.fields_schema = data || {};
            this.expandedTemplateId = tpl.id;
            await this.load();
        } else {
            await this.service.modal.show({ title: '', message: data?.message || '양식 재분석 실패', cancel: false, action: '확인', status: 'error' });
        }
        await this.service.render();
    }

    public toggleTemplate(tpl: any) {
        this.expandedTemplateId = this.expandedTemplateId === tpl.id ? '' : tpl.id;
        this.service.render();
    }

    public fileTypeLabel(type: string) {
        let map: any = { hwp: 'HWP', doc: 'DOC', docx: 'DOCX', pdf: 'PDF' };
        return map[type] || type?.toUpperCase() || '-';
    }

    public fileTypeBadgeClass(type: string) {
        let map: any = {
            hwp: 'bg-blue-50 text-blue-600',
            doc: 'bg-sky-50 text-sky-600',
            docx: 'bg-violet-50 text-violet-600',
            pdf: 'bg-rose-50 text-rose-600'
        };
        return map[type] || 'bg-slate-50 text-slate-600';
    }

    public fillCapabilityLabel(tpl: any) {
        let enabled = tpl?.fields_schema?.capabilities?.preserve_layout_fill;
        return enabled ? '원본 양식 삽입 지원' : '섹션 기반 작성';
    }

    public fillCapabilityClass(tpl: any) {
        let enabled = tpl?.fields_schema?.capabilities?.preserve_layout_fill;
        return enabled ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-700';
    }

    public schemaStats(tpl: any) {
        let schema = tpl?.fields_schema || {};
        let tables = schema.tables || [];
        let tableCount = tables.length || 0;
        let rowCount = tables.reduce((sum: number, table: any[]) => sum + (table?.length || 0), 0);
        let maxCols = tables.reduce((max: number, table: any[]) => {
            let tableMax = (table || []).reduce((m: number, row: any[]) => Math.max(m, row?.length || 0), 0);
            return Math.max(max, tableMax);
        }, 0);
        return {
            fields: (schema.fields || []).length,
            sections: (schema.sections || []).length,
            tables: tableCount,
            rows: rowCount,
            maxCols,
            fills: (schema.table_fills || []).length,
            placeholders: (schema.placeholders || []).length
        };
    }

    public tablePreviewRows(table: any[]) {
        return (table || []).slice(0, 4).map((row: any[]) => (row || []).slice(0, 6));
    }

    public tableColumnCount(table: any[]) {
        return (table || []).reduce((max: number, row: any[]) => Math.max(max, row?.length || 0), 0);
    }

    public firstTableFills(tpl: any) {
        return (tpl?.fields_schema?.table_fills || []).slice(0, 8);
    }

    public referenceCount(tpl: any) {
        return (tpl?.fields_schema?.reference_files || []).length;
    }
}

import { OnInit, ChangeDetectorRef } from '@angular/core';
import { Service } from '@wiz/libs/portal/season/service';

export class Component implements OnInit {
    constructor(public service: Service, private cdr: ChangeDetectorRef) { }

    public instances: any[] = [];
    public weeklyGroups: any[] = [];
    public templates: any[] = [];
    public folders: any[] = [];
    public stats: any = { total: 0, in_progress: 0, done: 0 };

    public selectedFolderId: string = '__all__';
    public viewMode: 'list' | 'weeks' = 'list';
    public sortBy: string = 'title';
    public order: string = 'ASC';

    public showNewModal: boolean = false;
    public sourceType: string = 'template';
    public selectedTemplateId: string = '';
    public newTitle: string = '';
    public newWeekLabel: string = '';
    public newDocFolderId: string = '';
    public creating: boolean = false;
    public selectedFile: File | null = null;

    public showCompletedModal: boolean = false;
    public uploadingCompleted: boolean = false;
    public completedFile: File | null = null;
    public completedTitle: string = '';
    public completedWeekLabel: string = '';
    public completedFolderId: string = '';

    public showBulkModal: boolean = false;
    public bulkCreating: boolean = false;
    public bulkSourceType: 'template' | 'blank' = 'template';
    public bulkTemplateId: string = '';
    public bulkFolderId: string = '';
    public bulkStartWeek: number = 1;
    public bulkEndWeek: number = 4;
    public bulkTitlePattern: string = '{week} 활동보고서';

    public showFolderModal: boolean = false;
    public folderMode: 'create' | 'rename' = 'create';
    public folderName: string = '';
    public editingFolderId: string = '';

    public showManageModal: boolean = false;
    public manageDocForm: any = { id: '', title: '', status: 'draft', folder_id: '', week_label: '', deadline: '' };
    public savingMeta: boolean = false;

    public selectedDocs: any = {};
    public selectedMoveFolderId: string = '';

    public async ngOnInit() {
        await this.service.init();
        await this.load();
    }

    public async load() {
        await Promise.all([
            this.loadFolders(),
            this.loadList(),
            this.loadWeekly(),
            this.loadStatsAndTemplates()
        ]);
        await this.service.render();
    }

    public async loadList() {
        let { code, data } = await wiz.call('list', {
            folder_id: this.selectedFolderId,
            sort_by: this.sortBy,
            order: this.order
        });
        if (code === 200) this.instances = data || [];
        this.trimSelectionToVisible();
    }

    public async loadWeekly() {
        let { code, data } = await wiz.call('weekly', {
            folder_id: this.selectedFolderId
        });
        if (code === 200) this.weeklyGroups = data || [];
    }

    public async loadFolders() {
        let { code, data } = await wiz.call('folders');
        if (code === 200) this.folders = data || [];
    }

    public async loadStatsAndTemplates() {
        let [statsRes, tplRes] = await Promise.all([
            wiz.call('stats'),
            wiz.call('templates')
        ]);
        if (statsRes.code === 200) this.stats = statsRes.data || { total: 0, in_progress: 0, done: 0 };
        if (tplRes.code === 200) this.templates = tplRes.data || [];
    }

    public async selectFolder(folderId: string) {
        this.selectedFolderId = folderId;
        this.clearSelection(false);
        await Promise.all([this.loadList(), this.loadWeekly()]);
        await this.service.render();
    }

    public async changeSort() {
        await this.loadList();
        await this.service.render();
    }

    public async switchView(mode: 'list' | 'weeks') {
        this.viewMode = mode;
        if (mode === 'weeks') await this.loadWeekly();
        await this.service.render();
    }

    public async openNew() {
        this.showNewModal = true;
        this.sourceType = 'template';
        this.selectedTemplateId = '';
        this.newTitle = '';
        this.newWeekLabel = '';
        this.newDocFolderId = this.selectedFolderId === '__all__' ? '' : this.selectedFolderId;
        this.selectedFile = null;
        this.cdr.detectChanges();
        await this.service.render();
    }

    public async closeNew() {
        this.showNewModal = false;
        this.cdr.detectChanges();
        await this.service.render();
    }

    public async openBulk() {
        this.showBulkModal = true;
        this.bulkSourceType = 'template';
        this.bulkTemplateId = this.selectedTemplateId || this.templates[0]?.id || '';
        this.bulkFolderId = this.selectedFolderId === '__all__' ? '' : this.selectedFolderId;
        this.bulkStartWeek = 1;
        this.bulkEndWeek = 4;
        this.bulkTitlePattern = '{week} 활동보고서';
        this.cdr.detectChanges();
        await this.service.render();
    }

    public async closeBulk() {
        this.showBulkModal = false;
        this.cdr.detectChanges();
        await this.service.render();
    }

    public async openCompletedUpload() {
        this.showCompletedModal = true;
        this.uploadingCompleted = false;
        this.completedFile = null;
        this.completedTitle = '';
        this.completedWeekLabel = '';
        this.completedFolderId = this.selectedFolderId === '__all__' ? '' : this.selectedFolderId;
        this.cdr.detectChanges();
        await this.service.render();
    }

    public async closeCompletedUpload() {
        this.showCompletedModal = false;
        this.uploadingCompleted = false;
        this.completedFile = null;
        this.completedTitle = '';
        this.completedWeekLabel = '';
        this.cdr.detectChanges();
        await this.service.render();
    }

    public onCompletedFileSelect(event: any) {
        let file = event.target.files[0];
        if (!file) return;

        let ext = file.name.split('.').pop()?.toLowerCase();
        if (!['pdf', 'hwp', 'doc', 'docx'].includes(ext || '')) {
            this.service.modal.show({ title: '', message: 'PDF, HWP, DOC, DOCX 파일만 지원합니다.', cancel: false, action: '확인', status: 'error' });
            return;
        }

        this.completedFile = file;
        if (!this.completedTitle.trim()) {
            this.completedTitle = file.name.replace(/\.[^/.]+$/, '');
        }
        this.cdr.detectChanges();
        this.service.render();
    }

    public async uploadCompletedFile() {
        if (!this.completedFile) {
            await this.service.modal.show({ title: '', message: '업로드할 완료 파일을 선택해주세요.', cancel: false, action: '확인', status: 'error' });
            return;
        }

        this.uploadingCompleted = true;
        this.cdr.detectChanges();
        await this.service.render();

        let fd = new FormData();
        fd.append('file', this.completedFile);
        fd.append('title', this.completedTitle.trim());
        fd.append('folder_id', this.completedFolderId || '');
        fd.append('week_label', this.completedWeekLabel.trim());

        let { code, data } = await wiz.call('upload_completed', fd, { processData: false, contentType: false });
        this.uploadingCompleted = false;

        if (code === 200) {
            this.showCompletedModal = false;
            this.selectedFolderId = this.completedFolderId || '';
            await Promise.all([this.loadFolders(), this.loadList(), this.loadWeekly(), this.loadStatsAndTemplates()]);
            await this.service.modal.show({ title: '', message: '완료 파일을 폴더에 추가했습니다.', cancel: false, action: '확인', status: 'success' });
        } else {
            await this.service.modal.show({ title: '', message: data?.message || '완료 파일 업로드 실패', cancel: false, action: '확인', status: 'error' });
        }
        this.cdr.detectChanges();
        await this.service.render();
    }

    public bulkCount() {
        let start = Number(this.bulkStartWeek || 0);
        let end = Number(this.bulkEndWeek || 0);
        if (!start || !end || end < start) return 0;
        return end - start + 1;
    }

    public bulkPreviewTitle() {
        let week = `${Number(this.bulkStartWeek || 1)}주차`;
        return (this.bulkTitlePattern || '{week} 문서').replace('{week}', week).replace('{n}', String(Number(this.bulkStartWeek || 1)));
    }

    public async createBulkWeeks() {
        if (this.bulkCount() <= 0) {
            await this.service.modal.show({ title: '', message: '주차 범위를 확인해주세요.', cancel: false, action: '확인', status: 'error' });
            return;
        }
        if (this.bulkSourceType === 'template' && !this.bulkTemplateId) {
            await this.service.modal.show({ title: '', message: '양식을 선택해주세요.', cancel: false, action: '확인', status: 'error' });
            return;
        }

        this.bulkCreating = true;
        this.cdr.detectChanges();
        await this.service.render();

        let { code, data } = await wiz.call('create_bulk_weeks', {
            source_type: this.bulkSourceType,
            template_id: this.bulkTemplateId,
            folder_id: this.bulkFolderId || '',
            start_week: this.bulkStartWeek,
            end_week: this.bulkEndWeek,
            title_pattern: this.bulkTitlePattern || '{week} 문서'
        });
        this.bulkCreating = false;

        if (code === 200) {
            this.showBulkModal = false;
            this.selectedFolderId = this.bulkFolderId || '';
            await Promise.all([this.loadFolders(), this.loadList(), this.loadWeekly(), this.loadStatsAndTemplates()]);
            await this.service.modal.show({ title: '', message: `${data?.count || 0}개 문서를 생성했습니다.`, cancel: false, action: '확인', status: 'success' });
        } else {
            await this.service.modal.show({ title: '', message: data?.message || '일괄 생성 실패', cancel: false, action: '확인', status: 'error' });
        }
        this.cdr.detectChanges();
        await this.service.render();
    }

    public onFileSelect(event: any) {
        let file = event.target.files[0];
        if (file) {
            let ext = file.name.split('.').pop()?.toLowerCase();
            if (!['pdf', 'hwp', 'doc', 'docx'].includes(ext || '')) {
                this.service.modal.show({ title: '', message: 'PDF, HWP, DOC, DOCX 파일만 지원합니다.', cancel: false, action: '확인', status: 'error' });
                return;
            }
            this.selectedFile = file;
        }
        this.cdr.detectChanges();
        this.service.render();
    }

    public async createDoc() {
        if (!this.newTitle) {
            await this.service.modal.show({ title: '', message: '문서 제목을 입력해주세요.', cancel: false, action: '확인', status: 'error' });
            return;
        }

        this.creating = true;
        this.cdr.detectChanges();
        await this.service.render();

        let fd = new FormData();
        fd.append('title', this.newTitle);
        fd.append('source_type', this.sourceType);
        fd.append('folder_id', this.newDocFolderId || '');
        fd.append('week_label', this.newWeekLabel || '');

        if (this.sourceType === 'template') {
            if (!this.selectedTemplateId) {
                this.creating = false;
                await this.service.modal.show({ title: '', message: '양식을 선택해주세요.', cancel: false, action: '확인', status: 'error' });
                this.cdr.detectChanges();
                await this.service.render();
                return;
            }
            fd.append('template_id', this.selectedTemplateId);
        } else if (this.sourceType === 'upload') {
            if (!this.selectedFile) {
                this.creating = false;
                await this.service.modal.show({ title: '', message: '파일을 업로드해주세요.', cancel: false, action: '확인', status: 'error' });
                this.cdr.detectChanges();
                await this.service.render();
                return;
            }
            fd.append('file', this.selectedFile);
        }

        let { code, data } = await wiz.call('create', fd, { processData: false, contentType: false });
        this.creating = false;

        if (code === 200) {
            this.showNewModal = false;
            let newId = data?.id || '';
            if (newId) {
                this.service.href(`/doc/write/${newId}/settings`);
                return;
            }
            await this.load();
        } else {
            await this.service.modal.show({ title: '', message: data?.message || '생성 실패', cancel: false, action: '확인', status: 'error' });
        }
        this.cdr.detectChanges();
        await this.service.render();
    }

    public openCreateFolder() {
        this.folderMode = 'create';
        this.editingFolderId = '';
        this.folderName = '';
        this.showFolderModal = true;
        this.service.render();
    }

    public openRenameFolder(folder: any) {
        this.folderMode = 'rename';
        this.editingFolderId = folder.id;
        this.folderName = folder.name || '';
        this.showFolderModal = true;
        this.service.render();
    }

    public closeFolderModal() {
        this.showFolderModal = false;
        this.folderName = '';
        this.editingFolderId = '';
        this.service.render();
    }

    public async saveFolder() {
        if (!this.folderName.trim()) return;
        let response = this.folderMode === 'create'
            ? await wiz.call('create_folder', { name: this.folderName.trim() })
            : await wiz.call('rename_folder', { id: this.editingFolderId, name: this.folderName.trim() });

        if (response.code === 200) {
            let newId = response.data?.id || '';
            this.closeFolderModal();
            if (this.folderMode === 'create' && newId) this.selectedFolderId = newId;
            await Promise.all([this.loadFolders(), this.loadList(), this.loadWeekly()]);
        } else {
            await this.service.modal.show({ title: '', message: response.data?.message || '폴더 저장 실패', cancel: false, action: '확인', status: 'error' });
        }
        await this.service.render();
    }

    public async deleteFolder(folder: any) {
        let ok = await this.service.modal.show({
            title: '',
            message: `'${folder.name}' 폴더를 삭제하시겠습니까? 폴더 안 문서는 미분류로 이동합니다.`,
            action: '삭제',
            actionBtn: 'error',
            status: 'error'
        });
        if (!ok) return;
        let { code, data } = await wiz.call('delete_folder', { id: folder.id });
        if (code === 200) {
            if (this.selectedFolderId === folder.id) this.selectedFolderId = '__all__';
            await this.load();
        } else {
            await this.service.modal.show({ title: '', message: data?.message || '폴더 삭제 실패', cancel: false, action: '확인', status: 'error' });
        }
    }

    public openManageDoc(doc: any) {
        this.manageDocForm = {
            id: doc.id,
            title: doc.title,
            status: doc.status,
            folder_id: doc.folder_id || '',
            week_label: doc.week_label || '',
            deadline: doc.deadline || ''
        };
        this.showManageModal = true;
        this.service.render();
    }

    public closeManageModal() {
        this.showManageModal = false;
        this.manageDocForm = { id: '', title: '', status: 'draft', folder_id: '', week_label: '', deadline: '' };
        this.service.render();
    }

    public async saveDocMeta() {
        this.savingMeta = true;
        await this.service.render();
        let { code, data } = await wiz.call('update_meta', this.manageDocForm);
        this.savingMeta = false;
        if (code === 200) {
            this.closeManageModal();
            await Promise.all([this.loadList(), this.loadWeekly(), this.loadFolders()]);
        } else {
            await this.service.modal.show({ title: '', message: data?.message || '문서 정보 저장 실패', cancel: false, action: '확인', status: 'error' });
        }
        await this.service.render();
    }

    public async removeDoc(id: string) {
        let res = await this.service.modal.show({
            title: '',
            message: '이 문서를 삭제하시겠습니까?',
            action: '삭제',
            actionBtn: 'error',
            status: 'error'
        });
        if (!res) return;
        let { code } = await wiz.call('delete', { id });
        if (code === 200) await this.load();
    }

    public selectedDocIds() {
        return Object.keys(this.selectedDocs).filter((id: string) => !!this.selectedDocs[id]);
    }

    public selectedDocCount() {
        return this.selectedDocIds().length;
    }

    public isDocSelected(id: string) {
        return !!this.selectedDocs[id];
    }

    public toggleDocSelection(doc: any, event?: any) {
        if (event) event.stopPropagation();
        this.selectedDocs[doc.id] = !this.selectedDocs[doc.id];
        if (this.selectedDocCount() === 1 && !this.selectedMoveFolderId) {
            this.selectedMoveFolderId = doc.folder_id || '';
        }
        this.service.render();
    }

    public visibleSelectedCount() {
        let visible = new Set((this.instances || []).map((doc: any) => doc.id));
        return this.selectedDocIds().filter((id: string) => visible.has(id)).length;
    }

    public allVisibleSelected() {
        return this.instances.length > 0 && this.visibleSelectedCount() === this.instances.length;
    }

    public toggleAllVisible(event?: any) {
        if (event) event.stopPropagation();
        let checked = !this.allVisibleSelected();
        (this.instances || []).forEach((doc: any) => this.selectedDocs[doc.id] = checked);
        this.service.render();
    }

    public clearSelection(render: boolean = true) {
        this.selectedDocs = {};
        if (render) this.service.render();
    }

    private trimSelectionToVisible() {
        let visible = new Set((this.instances || []).map((doc: any) => doc.id));
        Object.keys(this.selectedDocs).forEach((id: string) => {
            if (!visible.has(id)) delete this.selectedDocs[id];
        });
    }

    public async moveSelectedToFolder() {
        let ids = this.selectedDocIds();
        if (!ids.length) return;
        let { code, data } = await wiz.call('move_to_folder', {
            ids: JSON.stringify(ids),
            folder_id: this.selectedMoveFolderId || ''
        });
        if (code === 200) {
            this.clearSelection(false);
            await Promise.all([this.loadFolders(), this.loadList(), this.loadWeekly()]);
        } else {
            await this.service.modal.show({ title: '', message: data?.message || '폴더 이동 실패', cancel: false, action: '확인', status: 'error' });
        }
        await this.service.render();
    }

    public statusLabel(status: string) {
        let map: any = { draft: '초안', writing: '작성중', review: '검토', done: '완료' };
        return map[status] || status;
    }

    public statusClass(status: string) {
        let map: any = {
            draft: 'bg-slate-100 text-slate-600',
            writing: 'bg-amber-50 text-amber-700',
            review: 'bg-blue-50 text-blue-700',
            done: 'bg-green-50 text-green-700'
        };
        return map[status] || 'bg-slate-100 text-slate-600';
    }

    public sourceLabel(type: string) {
        let map: any = { template: '양식', upload: '외부 파일', blank: '빈 문서', archive: '외부 보관 파일' };
        return map[type] || type;
    }

    public selectedFolderName() {
        if (this.selectedFolderId === '__all__') return '전체 문서';
        if (this.selectedFolderId === '') return '미분류';
        return this.folders.find((x: any) => x.id === this.selectedFolderId)?.name || '폴더';
    }

    public goDetail(id: string) {
        this.service.href(`/doc/write/${id}/settings`);
    }
}

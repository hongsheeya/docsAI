# =============================================================================
# Doc Sub-Struct (문서 비즈니스 로직)
# =============================================================================
import datetime
import json
import os

class Doc:
    def __init__(self, core):
        self.core = core
        self.db_template = core.orm.use("doc_template")
        self.db_folder = core.orm.use("doc_folder")
        self.db_instance = core.orm.use("doc_instance")
        self.db_section = core.orm.use("doc_section")

    def _loads_json(self, value, fallback):
        if isinstance(value, (dict, list)):
            return value
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return fallback
            try:
                parsed = json.loads(raw)
                return parsed if isinstance(parsed, (dict, list)) else fallback
            except Exception:
                return fallback
        return fallback

    def _normalize_schema(self, value):
        schema = self._loads_json(value, {})
        return schema if isinstance(schema, dict) else {}

    def _normalize_content_json(self, value):
        content = self._loads_json(value, {})
        if not isinstance(content, dict):
            return {}
        content['fields_schema'] = self._normalize_schema(content.get('fields_schema', {}))
        return content

    def _normalize_settings_json(self, value):
        settings = self._loads_json(value, {})
        if not isinstance(settings, dict):
            return {}
        for key in ['report_items', 'reference_doc_ids', 'reference_doc_titles', 'instruction_ids', 'reference_files']:
            if isinstance(settings.get(key), str):
                parsed = self._loads_json(settings.get(key), [])
                settings[key] = parsed if isinstance(parsed, list) else []
        return settings

    # ── Template CRUD ──

    def create_template(self, data):
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        data['created'] = now
        data['updated'] = now
        if isinstance(data.get('fields_schema'), (dict, list)):
            data['fields_schema'] = json.dumps(data['fields_schema'], ensure_ascii=False)
        return self.db_template.insert(data)

    def get_template(self, id):
        tpl = self.db_template.get(id=id)
        if tpl and tpl.get('fields_schema'):
            tpl['fields_schema'] = self._normalize_schema(tpl.get('fields_schema'))
        return tpl

    def list_templates(self):
        rows = self.db_template.rows(orderby="title", order="ASC")
        for r in rows:
            r['fields_schema'] = self._normalize_schema(r.get('fields_schema', {}))
        return rows

    # ── Folder CRUD ──

    def create_folder(self, data):
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        data['created'] = now
        data['updated'] = now
        if 'sort_order' not in data:
            current = self.db_folder.count(user_id=data.get('user_id', '')) or 0
            data['sort_order'] = current
        return self.db_folder.insert(data)

    def get_folder(self, id):
        return self.db_folder.get(id=id)

    def list_folders(self, user_id=None):
        kwargs = {}
        if user_id:
            kwargs['user_id'] = user_id
        rows = self.db_folder.rows(orderby="sort_order", order="ASC", **kwargs)
        for row in rows:
            row['doc_count'] = self.db_instance.count(folder_id=row['id'], user_id=row.get('user_id', '')) or 0
        return rows

    def update_folder(self, id, **fields):
        fields['updated'] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.db_folder.update(fields, id=id)

    def delete_folder(self, id):
        docs = self.db_instance.rows(folder_id=id)
        for doc in docs:
            self.db_instance.update({'folder_id': ''}, id=doc['id'])
        self.db_folder.delete(id=id)

    def update_template(self, id, **fields):
        fields['updated'] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if isinstance(fields.get('fields_schema'), (dict, list)):
            fields['fields_schema'] = json.dumps(fields['fields_schema'], ensure_ascii=False)
        self.db_template.update(fields, id=id)

    def delete_template(self, id):
        self.db_template.delete(id=id)

    # ── Instance CRUD ──

    def create_instance(self, data):
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        data['created'] = now
        data['updated'] = now
        data.setdefault('status', 'draft')
        if isinstance(data.get('content_json'), (dict, list)):
            data['content_json'] = json.dumps(data['content_json'], ensure_ascii=False)
        if isinstance(data.get('settings_json'), (dict, list)):
            data['settings_json'] = json.dumps(data['settings_json'], ensure_ascii=False)
        return self.db_instance.insert(data)

    def get_instance(self, id):
        inst = self.db_instance.get(id=id)
        if inst:
            inst['content_json'] = self._normalize_content_json(inst.get('content_json', {}))
            inst['settings_json'] = self._normalize_settings_json(inst.get('settings_json', {}))
            if inst.get('folder_id'):
                folder = self.get_folder(inst['folder_id'])
                if folder:
                    inst['folder_name'] = folder.get('name', '')
        return inst

    def list_instances(self, user_id=None, status=None, folder_id=None, sort_by="title", order="ASC"):
        kwargs = {}
        if user_id:
            kwargs['user_id'] = user_id
        if status:
            kwargs['status'] = status
        if folder_id is not None:
            kwargs['folder_id'] = folder_id
        rows = self.db_instance.rows(orderby=sort_by, order=order, **kwargs)
        for r in rows:
            r['content_json'] = self._normalize_content_json(r.get('content_json', {}))
            r['settings_json'] = self._normalize_settings_json(r.get('settings_json', {}))
            if r.get('folder_id'):
                folder = self.get_folder(r['folder_id'])
                if folder:
                    r['folder_name'] = folder.get('name', '')
        return rows

    def update_instance(self, id, **fields):
        fields['updated'] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for key in ['content_json', 'settings_json']:
            if isinstance(fields.get(key), (dict, list)):
                fields[key] = json.dumps(fields[key], ensure_ascii=False)
        self.db_instance.update(fields, id=id)

    def update_instance_meta(self, id, **fields):
        allowed = {}
        for key in ['title', 'status', 'folder_id', 'week_label', 'deadline']:
            if key in fields:
                allowed[key] = fields[key]
        if allowed:
            self.update_instance(id, **allowed)

    def delete_instance(self, id):
        # 섹션도 함께 삭제
        sections = self.db_section.rows(instance_id=id)
        for s in sections:
            self.db_section.delete(id=s['id'])

        inst = self.get_instance(id)
        if inst:
            content_json = inst.get('content_json', {}) if isinstance(inst.get('content_json', {}), dict) else {}
            for rel_path, subdirs in [
                (content_json.get('generated_output_file', ''), ("data", "outputs", "documents")),
                (content_json.get('uploaded_file', ''), ("data", "uploads", "instances")),
                (content_json.get('editable_docx_path', ''), ("data", "uploads", "instances"))
            ]:
                if rel_path:
                    try:
                        fs = wiz.project.fs(*subdirs)
                        abspath = fs.abspath(rel_path)
                        if os.path.exists(abspath):
                            os.remove(abspath)
                        converted_pdf = os.path.splitext(abspath)[0] + '_converted.pdf'
                        if os.path.exists(converted_pdf):
                            os.remove(converted_pdf)
                    except Exception:
                        pass
        self.db_instance.delete(id=id)

    # ── Section CRUD ──

    def create_section(self, data):
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        data['created'] = now
        data['updated'] = now
        data.setdefault('status', 'pending')
        return self.db_section.insert(data)

    def get_section(self, id):
        return self.db_section.get(id=id)

    def list_sections(self, instance_id):
        return self.db_section.rows(instance_id=instance_id, orderby="sort_order", order="ASC")

    def update_section(self, id, **fields):
        fields['updated'] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.db_section.update(fields, id=id)

    def delete_section(self, id):
        self.db_section.delete(id=id)

    def clear_sections(self, instance_id):
        sections = self.db_section.rows(instance_id=instance_id)
        for sec in sections:
            self.db_section.delete(id=sec['id'])

    def count_sections(self, instance_id, status=None):
        kwargs = {'instance_id': instance_id}
        if status:
            kwargs['status'] = status
        return self.db_section.count(**kwargs) or 0

    def instance_stats(self, user_id=None):
        """통계: 전체/진행중/완료"""
        kwargs = {}
        if user_id:
            kwargs['user_id'] = user_id
        total = self.db_instance.count(**kwargs) or 0
        kwargs_draft = dict(**kwargs, status='draft')
        kwargs_writing = dict(**kwargs, status='writing')
        kwargs_done = dict(**kwargs, status='done')
        draft = self.db_instance.count(**kwargs_draft) or 0
        writing = self.db_instance.count(**kwargs_writing) or 0
        done = self.db_instance.count(**kwargs_done) or 0
        return {
            'total': total,
            'in_progress': draft + writing,
            'done': done
        }

Model = Doc

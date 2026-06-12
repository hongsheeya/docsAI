import json
import os
import uuid
import builtins

struct = wiz.model("struct")

def _template_content_json(template_id):
    tpl = struct.doc.get_template(template_id)
    if not tpl:
        return None

    ftype = tpl.get('file_type', '')
    fschema = tpl.get('fields_schema', {})
    capabilities = fschema.get('capabilities', {}) if isinstance(fschema, dict) else {}
    converted_docx = fschema.get('converted_docx_path', '') if isinstance(fschema, dict) else ''
    editable_docx = fschema.get('editable_docx_path', '') if isinstance(fschema, dict) else ''
    if not editable_docx and ftype == 'docx':
        editable_docx = tpl.get('file_path', '')

    if ftype == 'docx':
        gen_mode = 'template-fill'
    elif ftype in ('hwp', 'doc', 'pdf') and (editable_docx or converted_docx or capabilities.get('preserve_layout_fill')):
        gen_mode = 'template-fill'
    else:
        gen_mode = 'section-generate'

    return {
        'template_title': tpl.get('title', ''),
        'template_description': tpl.get('description', ''),
        'fields_schema': fschema,
        'file_type': ftype,
        'template_file_path': tpl.get('file_path', ''),
        'editable_docx_path': editable_docx or converted_docx,
        'generation_mode': gen_mode
    }

def _template_settings_json(template_id):
    tpl = struct.doc.get_template(template_id)
    if not tpl:
        return {}
    fschema = tpl.get('fields_schema', {})
    if not isinstance(fschema, dict):
        return {}

    reference_files = fschema.get('reference_files', [])
    if not isinstance(reference_files, builtins.list):
        reference_files = []

    reference_texts = []
    normalized_files = []
    for item in reference_files:
        if not isinstance(item, dict) or not item.get('filename'):
            continue
        copied = dict(item)
        copied['source'] = copied.get('source') or 'template'
        normalized_files.append(copied)
        text = str(copied.get('text_excerpt', '')).strip()
        if text:
            reference_texts.append(f"[기본 참고자료: {copied.get('original_name', copied.get('filename', ''))}]\n{text}")

    if not normalized_files and not fschema.get('reference_text'):
        return {}

    return {
        'reference_files': normalized_files,
        'reference_file_names': [item.get('original_name', item.get('filename', '')) for item in normalized_files],
        'reference_text': (fschema.get('reference_text') or '\n\n'.join(reference_texts))[:12000],
        'template_reference_file_names': [item.get('filename', '') for item in normalized_files if item.get('filename')]
    }

def _section_defs_from_content(content_json):
    fields_schema = content_json.get('fields_schema', {}) if isinstance(content_json, dict) else {}
    if not isinstance(fields_schema, dict):
        fields_schema = {}

    section_defs = []
    for idx, sec in enumerate(fields_schema.get('sections', []) or []):
        title = sec.get('section_title', sec.get('title', f'섹션 {idx + 1}'))
        hint = sec.get('content', '') or f'{title} 내용을 검토하세요.'
        section_defs.append({
            'section_key': sec.get('section_key', f'section_{idx + 1}'),
            'section_title': title,
            'content': hint,
            'sort_order': idx + 1
        })

    if not section_defs:
        raw_text = fields_schema.get('raw_text', '')
        if raw_text:
            try:
                parsed = struct.file_parser._split_text_to_sections(raw_text)
                for idx, sec in enumerate(parsed[:12]):
                    title = sec.get('title', f'섹션 {idx + 1}')
                    content = sec.get('content', '') or f'{title} 내용을 검토하세요.'
                    section_defs.append({
                        'section_key': f'raw_{idx + 1}',
                        'section_title': title,
                        'content': content,
                        'sort_order': idx + 1
                    })
            except Exception:
                pass

    if not section_defs:
        section_defs = [
            {'section_key': 'overview', 'section_title': '개요', 'content': '문서 개요를 검토하세요.', 'sort_order': 1},
            {'section_key': 'body', 'section_title': '본문', 'content': '본문 내용을 검토하세요.', 'sort_order': 2},
            {'section_key': 'conclusion', 'section_title': '결론', 'content': '결론 및 향후 계획을 검토하세요.', 'sort_order': 3}
        ]
    return section_defs

def _seed_review_sections(instance_id, content_json):
    try:
        existing = struct.doc.list_sections(instance_id)
        if existing:
            return
        for sec in _section_defs_from_content(content_json)[:20]:
            struct.doc.create_section({
                'instance_id': instance_id,
                'section_key': sec.get('section_key', ''),
                'section_title': sec.get('section_title', ''),
                'content': sec.get('content', ''),
                'sort_order': sec.get('sort_order', 0),
                'status': 'done'
            })
    except Exception:
        pass

def _blank_content_json():
    return {
        'template_title': '',
        'fields_schema': {'sections': []},
        'file_type': '',
        'raw_text': ''
    }

def _parse_ids(raw):
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, builtins.list):
            return [str(x) for x in parsed if str(x).strip()]
    except Exception:
        pass
    return [x.strip() for x in str(raw).split(',') if x.strip()]

def list():
    user_id = wiz.session.get("id")
    folder_id = wiz.request.query("folder_id", "__all__")
    sort_by = wiz.request.query("sort_by", "title")
    order = wiz.request.query("order", "ASC")

    allowed_sort = ['updated', 'created', 'title', 'status']
    if sort_by not in allowed_sort:
        sort_by = 'updated'
    if order not in ['ASC', 'DESC']:
        order = 'DESC'

    folder_filter = None if folder_id == '__all__' else folder_id
    instances = struct.doc.list_instances(user_id=user_id, folder_id=folder_filter, sort_by=sort_by, order=order)
    wiz.response.status(200, instances)

def stats():
    user_id = wiz.session.get("id")
    data = struct.doc.instance_stats(user_id=user_id)
    wiz.response.status(200, data)

def templates():
    templates = struct.doc.list_templates()
    wiz.response.status(200, templates)

def folders():
    user_id = wiz.session.get("id")
    rows = struct.doc.list_folders(user_id=user_id)
    wiz.response.status(200, rows)

def weekly():
    user_id = wiz.session.get("id")
    folder_id = wiz.request.query("folder_id", "__all__")
    folder_filter = None if folder_id == '__all__' else folder_id

    def _date_text(value):
        if not value:
            return ''
        if hasattr(value, 'strftime'):
            try:
                return value.strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                pass
        return str(value)

    try:
        instances = struct.doc.list_instances(user_id=user_id, folder_id=folder_filter, sort_by='updated', order='DESC')
        groups = {}
        for inst in instances:
            week = (inst.get('week_label') or '').strip() or '주차 미지정'
            content_json = inst.get('content_json', {}) if isinstance(inst.get('content_json'), dict) else {}
            sections = struct.doc.list_sections(inst.get('id'))
            preview_parts = []
            for sec in sections[:4]:
                content = (sec.get('content') or '').strip()
                if not content:
                    continue
                title = sec.get('section_title') or '본문'
                preview_parts.append(f"{title}: {content[:220]}")
            if not preview_parts and content_json.get('archive_only'):
                fields_schema = content_json.get('fields_schema', {}) if isinstance(content_json.get('fields_schema'), dict) else {}
                reference_text = (content_json.get('reference_text') or fields_schema.get('raw_text') or '').strip()
                original = content_json.get('original_filename') or content_json.get('uploaded_file') or ''
                if reference_text:
                    preview_parts.append(f"업로드 파일: {reference_text[:360]}")
                else:
                    preview_parts.append(f"보관 파일: {original}")
            row = {
                'id': inst.get('id', ''),
                'title': inst.get('title', ''),
                'status': inst.get('status', ''),
                'folder_name': inst.get('folder_name', '') or '미분류',
                'created': _date_text(inst.get('created')),
                'updated': _date_text(inst.get('updated')),
                'source_type': inst.get('source_type', ''),
                'preview': "\n".join(preview_parts)[:900],
                'section_count': len(sections)
            }
            if week not in groups:
                groups[week] = {
                    'week_label': week,
                    'count': 0,
                    'done_count': 0,
                    'latest_updated': '',
                    'docs': []
                }
            groups[week]['count'] += 1
            if inst.get('status') == 'done':
                groups[week]['done_count'] += 1
            latest = _date_text(inst.get('updated') or inst.get('created'))
            groups[week]['latest_updated'] = max(groups[week]['latest_updated'] or '', latest)
            groups[week]['docs'].append(row)

        rows = [group for group in groups.values()]
        rows.sort(key=lambda x: x.get('latest_updated') or '', reverse=True)
        rows.sort(key=lambda x: x['week_label'] == '주차 미지정')
    except Exception as e:
        wiz.response.status(400, message=str(e))
    wiz.response.status(200, rows)

def create():
    title = wiz.request.query("title", True)
    source_type = wiz.request.query("source_type", "template")
    template_id = wiz.request.query("template_id", "")
    folder_id = wiz.request.query("folder_id", "")
    week_label = wiz.request.query("week_label", "")
    user_id = wiz.session.get("id")

    data = {
        'title': title,
        'user_id': user_id,
        'folder_id': folder_id,
        'week_label': week_label,
        'source_type': source_type,
        'template_id': template_id,
        'status': 'draft'
    }

    if source_type == 'template' and template_id:
        content_json = _template_content_json(template_id)
        if content_json:
            data['content_json'] = content_json
        settings_json = _template_settings_json(template_id)
        if settings_json:
            data['settings_json'] = settings_json

    elif source_type == 'upload':
        file = wiz.request.file("file")
        if file:
            filename = file.filename
            ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
            if ext not in ['pdf', 'hwp', 'doc', 'docx']:
                wiz.response.status(400, message="PDF, HWP, DOC, DOCX 파일만 지원합니다.")

            fs = wiz.project.fs("data", "uploads", "instances")
            import uuid
            file_id = str(uuid.uuid4())[:8]
            saved_name = f"{file_id}.{ext}"
            filepath = fs.abspath(saved_name)
            fs.makedirs("")
            file.save(filepath)

            parse_result = None
            try:
                parse_result = struct.file_parser.parse_uploaded_file(filepath)
            except Exception:
                parse_result = None

            capabilities = parse_result.get('capabilities', {}) if parse_result else {}
            converted_docx = parse_result.get('converted_docx_path', '') if parse_result else ''
            editable_docx = parse_result.get('editable_docx_path', '') if parse_result else ''
            if not editable_docx and ext == 'docx':
                editable_docx = saved_name

            if ext == 'docx':
                gen_mode = 'template-fill'
            elif ext in ('hwp', 'doc', 'pdf') and (editable_docx or converted_docx or capabilities.get('preserve_layout_fill')):
                gen_mode = 'template-fill'
            else:
                gen_mode = 'section-generate'

            data['content_json'] = {
                'uploaded_file': saved_name,
                'file_type': ext,
                'fields_schema': {
                    'fields': parse_result.get('fields', []) if parse_result else [],
                    'raw_text': (parse_result.get('text', '')[:5000] if parse_result else ''),
                    'sections': parse_result.get('sections', []) if parse_result else [],
                    'capabilities': capabilities,
                    'placeholders': parse_result.get('placeholders', []) if parse_result else [],
                    'metadata': parse_result.get('metadata', {}) if parse_result else {},
                    'tables': parse_result.get('tables', []) if parse_result else [],
                    'table_fills': parse_result.get('table_fills', []) if parse_result else [],
                    'converted_docx_path': converted_docx,
                    'editable_docx_path': editable_docx or converted_docx
                },
                'template_file_path': saved_name,
                'editable_docx_path': editable_docx or converted_docx,
                'generation_mode': gen_mode
            }

    elif source_type == 'blank':
        data['content_json'] = _blank_content_json()

    try:
        result = struct.doc.create_instance(data)
        new_id = result if isinstance(result, str) else ''
    except Exception as e:
        wiz.response.status(400, message=str(e))
    wiz.response.status(200, id=new_id)

def upload_completed():
    user_id = wiz.session.get("id")
    if not user_id:
        return wiz.response.status(401, message="로그인이 필요합니다.")

    file = wiz.request.file("file")
    if not file:
        return wiz.response.status(400, message="업로드할 파일을 선택해주세요.")

    original_filename = file.filename or "completed-document"
    ext = original_filename.rsplit('.', 1)[-1].lower() if '.' in original_filename else ''
    if ext not in ['pdf', 'hwp', 'doc', 'docx']:
        return wiz.response.status(400, message="PDF, HWP, DOC, DOCX 파일만 지원합니다.")

    title = (wiz.request.query("title", "") or "").strip()
    folder_id = wiz.request.query("folder_id", "")
    week_label = wiz.request.query("week_label", "")
    if not title:
        title = os.path.splitext(original_filename)[0] or "완료 문서"

    if folder_id:
        folder = struct.doc.get_folder(folder_id)
        if not folder or folder.get('user_id') != user_id:
            return wiz.response.status(400, message="폴더를 찾을 수 없습니다.")

    fs = wiz.project.fs("data", "uploads", "instances")
    saved_name = f"{str(uuid.uuid4())[:8]}.{ext}"
    filepath = fs.abspath(saved_name)
    fs.makedirs("")
    file.save(filepath)

    parse_result = None
    try:
        parse_result = struct.file_parser.parse_uploaded_file(filepath)
    except Exception:
        parse_result = None

    reference_text = (parse_result.get('text', '') if parse_result else '')[:7000]
    converted_docx = parse_result.get('converted_docx_path', '') if parse_result else ''
    editable_docx = parse_result.get('editable_docx_path', '') if parse_result else ''
    if not editable_docx and ext == 'docx':
        editable_docx = saved_name

    data = {
        'title': title,
        'user_id': user_id,
        'folder_id': folder_id,
        'week_label': week_label,
        'source_type': 'archive',
        'template_id': '',
        'status': 'done',
        'content_json': {
            'uploaded_file': saved_name,
            'template_file_path': saved_name,
            'file_type': ext,
            'original_filename': original_filename,
            'archive_only': True,
            'generation_mode': 'archive',
            'reference_text': reference_text,
            'fields_schema': {
                'fields': parse_result.get('fields', []) if parse_result else [],
                'sections': parse_result.get('sections', []) if parse_result else [],
                'raw_text': reference_text,
                'tables': parse_result.get('tables', []) if parse_result else [],
                'table_fills': parse_result.get('table_fills', []) if parse_result else [],
                'capabilities': parse_result.get('capabilities', {}) if parse_result else {},
                'placeholders': parse_result.get('placeholders', []) if parse_result else [],
                'metadata': {
                    'original_filename': original_filename,
                    'converted_docx_path': converted_docx,
                    'editable_docx_path': editable_docx
                },
                'converted_docx_path': converted_docx,
                'editable_docx_path': editable_docx or converted_docx
            },
            'editable_docx_path': editable_docx or converted_docx
        }
    }

    try:
        new_id = struct.doc.create_instance(data)
    except Exception as e:
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
        except Exception:
            pass
        return wiz.response.status(400, message=str(e))

    return wiz.response.status(200, id=new_id if isinstance(new_id, str) else '')

def create_bulk_weeks():
    user_id = wiz.session.get("id")
    if not user_id:
        return wiz.response.status(401, message="로그인이 필요합니다.")
    source_type = wiz.request.query("source_type", "template")
    template_id = wiz.request.query("template_id", "")
    folder_id = wiz.request.query("folder_id", "")
    title_pattern = wiz.request.query("title_pattern", "{week} 문서")
    start_week_raw = wiz.request.query("start_week", "1")
    end_week_raw = wiz.request.query("end_week", "1")

    try:
        start_week = int(float(start_week_raw))
        end_week = int(float(end_week_raw))
    except Exception:
        return wiz.response.status(400, message="주차 범위를 숫자로 입력해주세요.")

    if start_week < 1 or end_week < 1 or end_week < start_week:
        return wiz.response.status(400, message="주차 범위를 확인해주세요.")
    if end_week - start_week + 1 > 60:
        return wiz.response.status(400, message="한 번에 만들 수 있는 문서는 최대 60개입니다.")

    if source_type not in ['template', 'blank']:
        return wiz.response.status(400, message="일괄 생성은 양식 또는 빈 문서만 지원합니다.")

    content_json = None
    if source_type == 'template':
        if not template_id:
            return wiz.response.status(400, message="양식을 선택해주세요.")
        content_json = _template_content_json(template_id)
        if not content_json:
            return wiz.response.status(400, message="양식을 찾을 수 없습니다.")
    else:
        template_id = ''
        content_json = _blank_content_json()

    created = []
    try:
        for week_no in range(start_week, end_week + 1):
            week_label = f"{week_no}주차"
            title = (title_pattern or "{week} 문서").replace("{week}", week_label).replace("{n}", str(week_no)).strip()
            if not title:
                title = f"{week_label} 문서"

            data = {
                'title': title,
                'user_id': user_id,
                'folder_id': folder_id,
                'week_label': week_label,
                'source_type': source_type,
                'template_id': template_id,
                'status': 'review',
                'content_json': json.loads(json.dumps(content_json, ensure_ascii=False))
            }
            settings_json = _template_settings_json(template_id) if template_id else {}
            if settings_json:
                data['settings_json'] = json.loads(json.dumps(settings_json, ensure_ascii=False))
            new_id = struct.doc.create_instance(data)
            if isinstance(new_id, str):
                _seed_review_sections(new_id, data['content_json'])
            created.append({'id': new_id if isinstance(new_id, str) else '', 'title': title, 'week_label': week_label})
    except Exception as e:
        return wiz.response.status(400, message=str(e))

    return wiz.response.status(200, count=len(created), items=created)

def create_folder():
    user_id = wiz.session.get("id")
    if not user_id:
        return wiz.response.status(401, message="로그인이 필요합니다.")
    name = wiz.request.query("name", True)
    try:
        folder_id = struct.doc.create_folder({'user_id': user_id, 'name': name})
    except Exception as e:
        return wiz.response.status(400, message=str(e))
    return wiz.response.status(200, id=folder_id if isinstance(folder_id, str) else '')

def rename_folder():
    id = wiz.request.query("id", True)
    name = wiz.request.query("name", True)
    try:
        struct.doc.update_folder(id, name=name)
    except Exception as e:
        wiz.response.status(400, message=str(e))
    wiz.response.status(200)

def delete_folder():
    id = wiz.request.query("id", True)
    try:
        struct.doc.delete_folder(id)
    except Exception as e:
        wiz.response.status(400, message=str(e))
    wiz.response.status(200)

def update_meta():
    id = wiz.request.query("id", True)
    title = wiz.request.query("title", "")
    status = wiz.request.query("status", "")
    folder_id = wiz.request.query("folder_id", "")
    week_label = wiz.request.query("week_label", "")
    deadline = wiz.request.query("deadline", "")

    fields = {}
    if title != "":
        fields['title'] = title
    if status != "":
        fields['status'] = status
    fields['folder_id'] = folder_id
    fields['week_label'] = week_label
    fields['deadline'] = deadline

    try:
        struct.doc.update_instance_meta(id, **fields)
    except Exception as e:
        wiz.response.status(400, message=str(e))
    wiz.response.status(200)

def move_to_folder():
    user_id = wiz.session.get("id")
    if not user_id:
        return wiz.response.status(401, message="로그인이 필요합니다.")
    ids = _parse_ids(wiz.request.query("ids", "[]"))
    folder_id = wiz.request.query("folder_id", "")

    if not ids:
        return wiz.response.status(400, message="이동할 문서를 선택해주세요.")

    if folder_id:
        folder = struct.doc.get_folder(folder_id)
        if not folder or folder.get('user_id') != user_id:
            return wiz.response.status(400, message="폴더를 찾을 수 없습니다.")

    moved = 0
    try:
        for doc_id in ids:
            inst = struct.doc.get_instance(doc_id)
            if not inst or inst.get('user_id') != user_id:
                continue
            struct.doc.update_instance_meta(doc_id, folder_id=folder_id)
            moved += 1
    except Exception as e:
        return wiz.response.status(400, message=str(e))

    return wiz.response.status(200, moved=moved)

def delete():
    id = wiz.request.query("id", True)
    try:
        struct.doc.delete_instance(id)
    except Exception as e:
        wiz.response.status(400, message=str(e))
    wiz.response.status(200)

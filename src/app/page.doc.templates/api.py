import json
import os
import uuid
import csv
import builtins

struct = wiz.model("struct")

def _schema_from_parse_result(parse_result):
    return {
        "fields": parse_result.get('fields', []),
        "raw_text": parse_result.get('text', '')[:5000],
        "sections": parse_result.get('sections', []),
        "capabilities": parse_result.get('capabilities', {}),
        "placeholders": parse_result.get('placeholders', []),
        "metadata": parse_result.get('metadata', {}),
        "tables": parse_result.get('tables', []),
        "table_fills": parse_result.get('table_fills', []),
        "converted_docx_path": parse_result.get('converted_docx_path', ''),
        "editable_docx_path": parse_result.get('editable_docx_path', '') or parse_result.get('converted_docx_path', '')
    }

def _extract_reference_text(filepath, ext):
    ext = (ext or '').lower()
    if ext in ['docx', 'doc', 'pdf', 'hwp']:
        parse_result = struct.file_parser.parse(filepath)
        return parse_result.get('text', '')[:7000]
    if ext in ['txt', 'md', 'log', 'py', 'ts', 'js', 'json', 'yaml', 'yml']:
        with open(filepath, 'r', encoding='utf-8-sig', errors='ignore') as f:
            return f.read()[:7000]
    if ext == 'csv':
        with open(filepath, 'r', encoding='utf-8-sig', errors='ignore', newline='') as f:
            reader = csv.reader(f)
            rows = []
            for idx, row in enumerate(reader):
                rows.append(', '.join([str(cell or '').strip() for cell in row]))
                if idx >= 40:
                    break
        return '\n'.join(rows)[:7000]
    return ''

def _reference_files_from_request(existing=None):
    existing = existing if isinstance(existing, builtins.list) else []
    keep_raw = wiz.request.query("keep_reference_files", None)
    if keep_raw is not None:
        try:
            keep_names = json.loads(keep_raw or "[]")
            if not isinstance(keep_names, builtins.list):
                keep_names = []
            keep_names = {str(name) for name in keep_names}
            preserved = [item for item in existing if isinstance(item, dict) and item.get('filename') in keep_names]
        except Exception:
            preserved = existing
    else:
        preserved = existing

    uploaded_refs = []
    try:
        uploaded_refs = builtins.list(wiz.response._flask.request.files.getlist("reference_file") or [])
    except Exception:
        ref_file = wiz.request.file("reference_file")
        if ref_file:
            uploaded_refs = [ref_file]

    if uploaded_refs:
        fs = wiz.project.fs("data", "uploads", "references")
        fs.makedirs("")
        for ref in uploaded_refs:
            if not ref or not getattr(ref, 'filename', ''):
                continue
            ext = ref.filename.rsplit('.', 1)[-1].lower() if '.' in ref.filename else 'bin'
            saved_name = f"{uuid.uuid4().hex[:8]}.{ext}"
            filepath = fs.abspath(saved_name)
            ref.save(filepath)
            text_excerpt = ''
            try:
                text_excerpt = _extract_reference_text(filepath, ext)
            except Exception:
                text_excerpt = ''
            preserved.append({
                'filename': saved_name,
                'original_name': ref.filename,
                'ext': ext,
                'source': 'template',
                'text_excerpt': text_excerpt[:4000]
            })

    preserved = [item for item in preserved if isinstance(item, dict) and item.get('filename')][-20:]
    reference_texts = []
    for item in preserved:
        text = str(item.get('text_excerpt', '')).strip()
        if text:
            reference_texts.append(f"[기본 참고자료: {item.get('original_name', item.get('filename', ''))}]\n{text}")
    return {
        'reference_files': preserved,
        'reference_file_names': [item.get('original_name', item.get('filename', '')) for item in preserved],
        'reference_text': '\n\n'.join(reference_texts)[:12000]
    }

def _apply_reference_payload(fields_schema, payload):
    if not isinstance(fields_schema, dict):
        fields_schema = {}
    fields_schema['reference_files'] = payload.get('reference_files', [])
    fields_schema['reference_file_names'] = payload.get('reference_file_names', [])
    fields_schema['reference_text'] = payload.get('reference_text', '')
    return fields_schema

def list():
    templates = struct.doc.list_templates()
    wiz.response.status(200, templates)

def create():
    title = wiz.request.query("title", True)
    description = wiz.request.query("description", "")
    file = wiz.request.file("file")

    if not file:
        wiz.response.status(400, message="파일을 업로드해주세요.")

    filename = file.filename
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    if ext not in ['hwp', 'doc', 'docx']:
        wiz.response.status(400, message="HWP, DOC, DOCX 파일만 지원합니다.")

    # 파일 저장
    fs = wiz.project.fs("data", "uploads", "templates")
    import datetime, uuid
    file_id = str(uuid.uuid4())[:8]
    saved_name = f"{file_id}.{ext}"
    filepath = fs.abspath(saved_name)
    fs.makedirs("")
    file.save(filepath)

    # 양식 필드 자동 감지 — FileParser Sub-Struct 사용
    fields_schema = {"fields": [], "raw_text": "", "sections": [], "capabilities": {}, "placeholders": [], "metadata": {}, "tables": [], "table_fills": [], "converted_docx_path": "", "editable_docx_path": ""}
    try:
        parse_result = struct.file_parser.parse_uploaded_file(filepath)
        fields_schema = _schema_from_parse_result(parse_result)
    except Exception:
        pass
    fields_schema = _apply_reference_payload(fields_schema, _reference_files_from_request([]))

    data = {
        'title': title,
        'description': description,
        'file_path': saved_name,
        'file_type': ext,
        'fields_schema': fields_schema
    }

    try:
        struct.doc.create_template(data)
    except Exception as e:
        wiz.response.status(400, message=str(e))
    wiz.response.status(200)

def update():
    id = wiz.request.query("id", True)
    title = wiz.request.query("title", "")
    description = wiz.request.query("description", "")
    tpl = struct.doc.get_template(id)
    current_schema = tpl.get('fields_schema', {}) if tpl and isinstance(tpl.get('fields_schema'), dict) else {}

    fields = {}
    if title:
        fields['title'] = title
    if description is not None:
        fields['description'] = description

    file = wiz.request.file("file")
    if file:
        filename = file.filename
        ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
        if ext not in ['hwp', 'doc', 'docx']:
            wiz.response.status(400, message="HWP, DOC, DOCX 파일만 지원합니다.")

        fs = wiz.project.fs("data", "uploads", "templates")
        import uuid
        file_id = str(uuid.uuid4())[:8]
        saved_name = f"{file_id}.{ext}"
        filepath = fs.abspath(saved_name)
        fs.makedirs("")
        file.save(filepath)

        fields['file_path'] = saved_name
        fields['file_type'] = ext

        try:
            parse_result = struct.file_parser.parse_uploaded_file(filepath)
            fields['fields_schema'] = _schema_from_parse_result(parse_result)
        except Exception as e:
            wiz.response.status(400, message=f"파일 분석 실패: {str(e)}")

    base_schema = fields.get('fields_schema') if isinstance(fields.get('fields_schema'), dict) else current_schema
    fields['fields_schema'] = _apply_reference_payload(
        base_schema,
        _reference_files_from_request(current_schema.get('reference_files', []))
    )

    try:
        struct.doc.update_template(id, **fields)
    except Exception as e:
        wiz.response.status(400, message=str(e))
    wiz.response.status(200)

def reanalyze():
    id = wiz.request.query("id", True)
    tpl = struct.doc.get_template(id)
    if not tpl:
        wiz.response.status(404, message="양식을 찾을 수 없습니다.")

    file_path = tpl.get('file_path', '')
    if not file_path:
        wiz.response.status(400, message="분석할 파일이 없습니다.")

    fs = wiz.project.fs("data", "uploads", "templates")
    abspath = fs.abspath(file_path)
    if not os.path.exists(abspath):
        wiz.response.status(404, message="양식 파일을 찾을 수 없습니다.")

    try:
        parse_result = struct.file_parser.parse_uploaded_file(abspath)
        fields_schema = _schema_from_parse_result(parse_result)
        fields_schema = _apply_reference_payload(fields_schema, {
            'reference_files': tpl.get('fields_schema', {}).get('reference_files', []) if isinstance(tpl.get('fields_schema'), dict) else [],
            'reference_file_names': tpl.get('fields_schema', {}).get('reference_file_names', []) if isinstance(tpl.get('fields_schema'), dict) else [],
            'reference_text': tpl.get('fields_schema', {}).get('reference_text', '') if isinstance(tpl.get('fields_schema'), dict) else ''
        })
        struct.doc.update_template(id, fields_schema=fields_schema)
    except Exception as e:
        wiz.response.status(400, message=f"양식 재분석 실패: {str(e)}")

    wiz.response.status(200, fields_schema)

def delete():
    id = wiz.request.query("id", True)
    try:
        # 파일 삭제
        tpl = struct.doc.get_template(id)
        if tpl and tpl.get('file_path'):
            fs = wiz.project.fs("data", "uploads", "templates")
            fpath = fs.abspath(tpl['file_path'])
            for path in [
                fpath,
                os.path.splitext(fpath)[0] + '_converted.docx',
                os.path.splitext(fpath)[0] + '_converted.pdf',
            ]:
                if os.path.exists(path):
                    os.remove(path)
        struct.doc.delete_template(id)
    except Exception as e:
        wiz.response.status(400, message=str(e))
    wiz.response.status(200)

import json
import os
import uuid
import csv
import html
import re
import io
import zipfile
import tempfile
import shutil
from urllib.parse import quote as url_quote

struct = wiz.model("struct")

def _sse(payload):
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

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
                if idx >= 20:
                    break
        return '\n'.join(rows)[:7000]
    return ''

def _reference_text_preview_html(title, text, message=""):
    safe_title = html.escape(str(title or "참고자료"))
    safe_message = html.escape(str(message or ""))
    safe_text = html.escape(str(text or "").strip() or "미리볼 수 있는 텍스트가 없습니다.")
    message_html = f'<div class="message">{safe_message}</div>' if safe_message else ''
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<style>
body {{ margin: 0; background: #f8fafc; color: #1e293b; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
.wrap {{ max-width: 860px; margin: 0 auto; padding: 28px; }}
.title {{ font-size: 18px; font-weight: 700; margin-bottom: 8px; }}
.message {{ margin-bottom: 14px; color: #64748b; font-size: 13px; line-height: 1.6; }}
pre {{ white-space: pre-wrap; word-break: break-word; margin: 0; padding: 20px; border: 1px solid #e2e8f0; border-radius: 10px; background: #fff; font-size: 13px; line-height: 1.7; }}
</style>
</head>
<body>
<div class="wrap">
<div class="title">{safe_title}</div>
{message_html}
<pre>{safe_text}</pre>
</div>
</body>
</html>"""

def _reference_docs(user_id, current_id=""):
    docs = struct.doc.list_instances(user_id=user_id)
    result = []

    for doc in docs:
        if doc.get('id') == current_id:
            continue
        if doc.get('status') not in ['review', 'done']:
            continue

        sections = struct.doc.list_sections(doc['id'])
        preview_parts = []
        for sec in sections[:3]:
            content = (sec.get('content') or '').strip()
            if not content:
                continue
            preview_parts.append(f"[{sec.get('section_title', '')}]\n{content[:280]}")

        content_json = doc.get('content_json', {}) if isinstance(doc.get('content_json'), dict) else {}
        fields_schema = content_json.get('fields_schema', {}) if isinstance(content_json.get('fields_schema'), dict) else {}
        archive_text = (content_json.get('reference_text') or fields_schema.get('raw_text') or '').strip()
        if not preview_parts and archive_text:
            preview_parts.append(f"[업로드 파일]\n{archive_text[:600]}")

        result.append({
            'id': doc.get('id', ''),
            'title': doc.get('title', ''),
            'status': doc.get('status', ''),
            'week_label': doc.get('week_label', ''),
            'created': doc.get('created', ''),
            'section_count': len(sections),
            'preview': "\n\n".join(preview_parts)[:1200]
        })

    return result[:12]

def _normal_ref_item(item, source="manual"):
    if not isinstance(item, dict) or not item.get('filename'):
        return None
    copied = dict(item)
    filename = str(copied.get('filename') or '').strip()
    if not filename:
        return None
    copied['filename'] = filename
    copied['original_name'] = str(copied.get('original_name') or filename)
    copied['ext'] = str(copied.get('ext') or (filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'bin'))
    copied['text_excerpt'] = str(copied.get('text_excerpt') or '')[:4000]
    copied['source'] = str(copied.get('source') or source)
    return copied

def _template_reference_files(instance):
    if not isinstance(instance, dict):
        return []
    content_json = instance.get('content_json', {}) if isinstance(instance.get('content_json', {}), dict) else {}
    template_id = content_json.get('template_id', '') or instance.get('template_id', '')
    if not template_id:
        return []
    try:
        tpl = struct.doc.get_template(template_id)
    except Exception:
        tpl = None
    if not tpl:
        return []
    schema = tpl.get('fields_schema', {}) if isinstance(tpl.get('fields_schema', {}), dict) else {}
    refs = schema.get('reference_files', [])
    if not isinstance(refs, list):
        refs = []
    normalized = []
    for item in refs:
        ref = _normal_ref_item(item, source="template")
        if ref:
            normalized.append(ref)
    return normalized

def _compose_reference_text(reference_files):
    parts = []
    for item in reference_files or []:
        if not isinstance(item, dict):
            continue
        text = str(item.get('text_excerpt', '') or '').strip()
        if not text:
            continue
        title = item.get('original_name', item.get('filename', '참고자료'))
        prefix = '기본 참고자료' if item.get('source') == 'template' else '참고자료'
        parts.append(f"[{prefix}: {title}]\n{text[:4000]}")
    return '\n\n'.join(parts)[:12000]

def _settings_with_template_references(instance, settings=None):
    settings = settings if isinstance(settings, dict) else {}
    current_refs = settings.get('reference_files', [])
    if not isinstance(current_refs, list):
        current_refs = []

    removed = settings.get('removed_template_reference_files', [])
    if not isinstance(removed, list):
        removed = []
    removed = {str(item) for item in removed}

    merged = []
    seen = set()
    for item in _template_reference_files(instance):
        filename = item.get('filename')
        if not filename or filename in removed or filename in seen:
            continue
        merged.append(item)
        seen.add(filename)

    for item in current_refs:
        ref = _normal_ref_item(item, source=item.get('source', 'manual') if isinstance(item, dict) else 'manual')
        if not ref:
            continue
        filename = ref.get('filename')
        if filename in removed and ref.get('source') == 'template':
            continue
        if filename in seen:
            for idx, existing in enumerate(merged):
                if existing.get('filename') == filename:
                    merged[idx] = {**existing, **ref, 'source': existing.get('source') or ref.get('source') or 'template'}
                    break
            continue
        merged.append(ref)
        seen.add(filename)

    limited = merged[:20]
    settings['reference_files'] = limited
    settings['reference_file_names'] = [item.get('original_name', item.get('filename', '')) for item in limited]
    settings['reference_text'] = _compose_reference_text(limited)
    settings['reference_file'] = limited[-1].get('filename', '') if limited else ''
    settings['removed_template_reference_files'] = sorted(removed)
    return settings

def _promote_instance_references_to_template(instance, settings):
    if not isinstance(instance, dict) or not isinstance(settings, dict):
        return False
    content_json = instance.get('content_json', {}) if isinstance(instance.get('content_json', {}), dict) else {}
    template_id = content_json.get('template_id', '') or instance.get('template_id', '')
    if not template_id or _template_reference_files(instance):
        return False

    current_refs = settings.get('reference_files', [])
    if not isinstance(current_refs, list) or not current_refs:
        return False

    promoted = []
    for item in current_refs:
        ref = _normal_ref_item(item, source="template")
        if not ref:
            continue
        ref['source'] = 'template'
        promoted.append(ref)
    if not promoted:
        return False

    try:
        tpl = struct.doc.get_template(template_id)
        if not tpl:
            return False
        schema = tpl.get('fields_schema', {}) if isinstance(tpl.get('fields_schema', {}), dict) else {}
        schema['reference_files'] = promoted[:20]
        schema['reference_file_names'] = [item.get('original_name', item.get('filename', '')) for item in schema['reference_files']]
        schema['reference_text'] = _compose_reference_text(schema['reference_files'])
        struct.doc.update_template(template_id, fields_schema=schema)
        settings['reference_files'] = schema['reference_files']
        settings['reference_file_names'] = schema['reference_file_names']
        settings['reference_text'] = schema['reference_text']
        settings['reference_file'] = schema['reference_files'][-1].get('filename', '') if schema['reference_files'] else ''
        return True
    except Exception:
        return False

def _ensure_template_references(instance, persist=True):
    if not isinstance(instance, dict):
        return instance
    before = json.dumps(instance.get('settings_json', {}) or {}, ensure_ascii=False, sort_keys=True)
    settings = instance.get('settings_json', {}) if isinstance(instance.get('settings_json', {}), dict) else {}
    settings = _settings_with_template_references(instance, settings)
    _promote_instance_references_to_template(instance, settings)
    settings = _settings_with_template_references(instance, settings)
    after = json.dumps(settings, ensure_ascii=False, sort_keys=True)
    if before != after:
        instance['settings_json'] = settings
        if persist and instance.get('id'):
            try:
                struct.doc.update_instance(instance['id'], settings_json=settings)
            except Exception:
                pass
    return instance

def _parsed_sections_are_meaningful(parsed_sections, fallback_values=None):
    if not isinstance(parsed_sections, list) or not parsed_sections:
        return False
    contents = []
    titles = []
    for sec in parsed_sections:
        if not isinstance(sec, dict):
            continue
        titles.append(str(sec.get('title', '') or '').strip())
        contents.append(str(sec.get('content', '') or '').strip())
    total = sum(len(item) for item in contents)
    fallback_total = 0
    if isinstance(fallback_values, dict):
        fallback_total = sum(len(str(value or '').strip()) for value in fallback_values.values())
    if total < 80:
        return False
    if len(parsed_sections) == 1 and (titles[0] if titles else '') in ['서두', '본문', '개요']:
        return total >= max(200, int(fallback_total * 0.5))
    if fallback_total and total < min(200, int(fallback_total * 0.25)):
        return False
    return True

def _is_meaningful_template_section(title):
    text = str(title or '').strip()
    if not text:
        return False
    compact = re.sub(r'[\s\.\:：·\-\_\(\)\[\]<>|│/]', '', text)
    if compact in {'활동주제', '차기활동계획'} or compact.startswith('세부활동내용'):
        return True
    if compact in {
        '팀명', '활동사진', '차수', '주제', '진행과정', '활동내용',
        '성명', '학번', '학과부', '학과', '서명', '참여자', '불참자',
        '멘토', '멘티', '구분'
    }:
        return False
    if text in ['서두', '개요', '본문', '결론']:
        return True
    return bool(re.match(r'^\d+\.\s*\S+', text))

def _template_docx_candidate(template_id, template_file_path='', editable_docx_path='', converted_docx_path='', file_type=''):
    fs = wiz.project.fs("data", "uploads", "templates") if template_id else wiz.project.fs("data", "uploads", "instances")
    candidates = []
    for rel in [editable_docx_path, converted_docx_path]:
        if rel:
            candidates.append(rel)
    if file_type == 'docx' and template_file_path:
        candidates.append(template_file_path)
    if template_file_path:
        base, _ = os.path.splitext(template_file_path)
        candidates.append(base + '_converted.docx')

    seen = set()
    for rel in candidates:
        rel = str(rel or '').strip()
        if not rel or rel in seen:
            continue
        seen.add(rel)
        try:
            abs_path = fs.abspath(rel)
            if os.path.exists(abs_path) and abs_path.lower().endswith('.docx'):
                return rel, abs_path
        except Exception:
            pass
    return '', ''

def _enrich_schema_from_editable_docx(instance, content_json, fields_schema, template_file_path='', editable_docx_path='', converted_docx_path='', file_type=''):
    if not isinstance(fields_schema, dict):
        fields_schema = {}
    if fields_schema.get('tables') and fields_schema.get('table_fills'):
        return fields_schema, editable_docx_path or converted_docx_path

    template_id = content_json.get('template_id', '') or instance.get('template_id', '')
    rel_path, abs_path = _template_docx_candidate(
        template_id, template_file_path, editable_docx_path, converted_docx_path, file_type
    )
    if not abs_path:
        return fields_schema, editable_docx_path or converted_docx_path

    try:
        parsed = struct.file_parser.parse_docx(abs_path)
    except Exception:
        return fields_schema, editable_docx_path or converted_docx_path

    parsed_tables = parsed.get('tables', []) if isinstance(parsed, dict) else []
    parsed_fills = parsed.get('table_fills', []) if isinstance(parsed, dict) else []
    if not parsed_tables and not parsed_fills:
        return fields_schema, rel_path

    merged = dict(fields_schema)
    if parsed_tables:
        merged['tables'] = parsed_tables
    if parsed_fills:
        merged['table_fills'] = parsed_fills
    for key in ['placeholders', 'metadata', 'capabilities']:
        if parsed.get(key) and not merged.get(key):
            merged[key] = parsed.get(key)
    parsed_text = str(parsed.get('text', '') or '').strip()
    current_text = str(merged.get('raw_text', '') or '').strip()
    if parsed_text and (len(current_text) < 500 or parsed_text not in current_text):
        merged['raw_text'] = (current_text + '\n\n' + parsed_text).strip()[:8000] if current_text else parsed_text[:8000]
    if parsed.get('fields') and not merged.get('fields'):
        merged['fields'] = parsed.get('fields')
    if rel_path:
        merged['editable_docx_path'] = rel_path
        if not merged.get('converted_docx_path'):
            merged['converted_docx_path'] = rel_path
    return merged, rel_path

def _ensure_editable_schema(instance, persist=True):
    """외부에서 업로드한 문서도 양식 편집/직접 편집에서 쓸 표 채움 정보를 갖도록 보강한다."""
    if not isinstance(instance, dict):
        return instance

    content_json = instance.get('content_json', {}) if isinstance(instance.get('content_json', {}), dict) else {}
    fields_schema = content_json.get('fields_schema', {}) if isinstance(content_json.get('fields_schema', {}), dict) else {}
    metadata = fields_schema.get('metadata', {}) if isinstance(fields_schema.get('metadata', {}), dict) else {}

    original = json.dumps(content_json, ensure_ascii=False, sort_keys=True)

    if fields_schema.get('tables'):
        try:
            recomputed_fills = struct.file_parser._analyze_table_fills(fields_schema.get('tables', []))
            if recomputed_fills:
                fields_schema['table_fills'] = recomputed_fills
        except Exception:
            if not fields_schema.get('table_fills'):
                fields_schema['table_fills'] = []

    template_file_path = content_json.get('template_file_path', '') or content_json.get('uploaded_file', '')
    file_type = content_json.get('file_type', '')
    converted_docx_path = (
        fields_schema.get('converted_docx_path', '')
        or metadata.get('converted_docx_path', '')
    )
    editable_docx_path = (
        content_json.get('editable_docx_path', '')
        or fields_schema.get('editable_docx_path', '')
        or metadata.get('editable_docx_path', '')
        or converted_docx_path
    )
    if not editable_docx_path and file_type == 'docx':
        editable_docx_path = template_file_path

    enriched_schema, enriched_docx_path = _enrich_schema_from_editable_docx(
        instance, content_json, fields_schema,
        template_file_path=template_file_path,
        editable_docx_path=editable_docx_path,
        converted_docx_path=converted_docx_path,
        file_type=file_type
    )
    fields_schema = enriched_schema if isinstance(enriched_schema, dict) else fields_schema

    if enriched_docx_path:
        editable_docx_path = enriched_docx_path
    if editable_docx_path:
        content_json['editable_docx_path'] = editable_docx_path
        fields_schema['editable_docx_path'] = editable_docx_path
    if converted_docx_path and not fields_schema.get('converted_docx_path'):
        fields_schema['converted_docx_path'] = converted_docx_path

    content_json['fields_schema'] = fields_schema
    if template_file_path and not content_json.get('template_file_path'):
        content_json['template_file_path'] = template_file_path

    if persist and instance.get('id') and json.dumps(content_json, ensure_ascii=False, sort_keys=True) != original:
        try:
            struct.doc.update_instance(instance['id'], content_json=content_json)
        except Exception:
            pass
    instance['content_json'] = content_json
    return instance

def _sanitize_instance_generated_fields(instance, persist=True):
    if not isinstance(instance, dict):
        return instance
    content_json = instance.get('content_json', {}) if isinstance(instance.get('content_json', {}), dict) else {}
    generated = content_json.get('generated_fields', {}) if isinstance(content_json.get('generated_fields', {}), dict) else {}
    cleaned = struct.ai_agent.sanitize_generated_fields(generated)
    if cleaned != generated:
        content_json['generated_fields'] = cleaned
        content_json['generated_output_file'] = ''
        instance['content_json'] = content_json
        if persist and instance.get('id'):
            try:
                struct.doc.update_instance(instance['id'], content_json=content_json)
            except Exception:
                pass
    return instance

def _editor_fields_from_existing_tables(fields_schema):
    """이미 작성된 외부 문서의 표를 양식 편집용 라벨/값 쌍으로 정리한다."""
    tables = fields_schema.get('tables', []) if isinstance(fields_schema, dict) else []
    if not isinstance(tables, list):
        return [], {}

    def norm(value):
        return re.sub(r'\s+', ' ', str(value or '')).strip()

    def valid_label(value):
        text = norm(value)
        if not text or len(text) > 90:
            return False
        compact = re.sub(r'[\s\.\:：·\-\_\(\)\[\]<>|│/]', '', text)
        if not compact or re.fullmatch(r'[\d~:/\\-]+', compact):
            return False
        return True

    def valid_value(value):
        text = norm(value)
        if not text:
            return False
        lowered = text.lower()
        if text.startswith('※') or 'xx' in lowered or '○○' in text or 'ㅇㅇ' in text:
            return False
        if any(token in text for token in ['기재하세요', '작성해주세요', '입력', '예시', 'sample', '샘플']):
            return False
        if re.fullmatch(r'[\-_\.·•※○◯□☐Xx\s]+', text):
            return False
        return True

    fills = []
    values = {}
    seen = set()
    for t_idx, table in enumerate(tables):
        if not isinstance(table, list):
            continue
        for r_idx, row in enumerate(table):
            if not isinstance(row, list) or len(row) < 2:
                continue
            cells = [norm(cell) for cell in row]
            non_empty = [idx for idx, cell in enumerate(cells) if cell]
            if len(non_empty) < 2:
                continue

            label_idx = non_empty[0]
            value_idx = non_empty[1]
            label = cells[label_idx]
            value = cells[value_idx]
            if not valid_label(label) or not valid_value(value) or label == value:
                continue

            key = re.sub(r'[\s\.\:：·\-\_\(\)\[\]<>|│/]', '', label)
            if key in seen:
                continue
            seen.add(key)
            values[label] = value
            fills.append({
                'table_idx': t_idx,
                'row': r_idx,
                'col': value_idx,
                'label': label,
                'type': 'key_value',
                'context': f"기존 외부 문서의 '{label}' 값을 수정합니다.",
                'answer_type': {},
                'nearby': " | ".join([cell for cell in cells if cell])[:500],
                'left_label': label,
                'top_label': '',
                'row_label': label,
                'section_label': '',
                'current_value': value
            })

    return fills, values

def reference_docs():
    id = wiz.request.query("id", "")
    user_id = wiz.session.get("id")
    try:
        docs = _reference_docs(user_id, id)
    except Exception as e:
        wiz.response.status(400, message=str(e))
    wiz.response.status(200, docs)

def list_instructions():
    user_id = wiz.session.get("id")
    try:
        rows = struct.ai.list_all_instructions(user_id)
    except Exception as e:
        wiz.response.status(400, message=str(e))
    wiz.response.status(200, rows)

def detail():
    id = wiz.request.query("id", True)
    try:
        inst = struct.doc.get_instance(id)
    except Exception as e:
        wiz.response.status(400, message=str(e))
    if not inst:
        wiz.response.status(404, message="문서를 찾을 수 없습니다.")
    inst = _ensure_template_references(inst)
    inst = _ensure_editable_schema(inst)
    inst = _sanitize_instance_generated_fields(inst)
    wiz.response.status(200, inst)

def folders():
    user_id = wiz.session.get("id")
    try:
        rows = struct.doc.list_folders(user_id=user_id)
    except Exception as e:
        wiz.response.status(400, message=str(e))
    wiz.response.status(200, rows)

def sections():
    instance_id = wiz.request.query("instance_id", True)
    try:
        secs = struct.doc.list_sections(instance_id)
    except Exception as e:
        wiz.response.status(400, message=str(e))
    wiz.response.status(200, secs)

def chats():
    instance_id = wiz.request.query("instance_id", True)
    try:
        msgs = struct.ai.list_chats(instance_id)
    except Exception as e:
        wiz.response.status(400, message=str(e))
    wiz.response.status(200, msgs)

def save_settings():
    id = wiz.request.query("id", True)
    title = wiz.request.query("title", "")
    status = wiz.request.query("status", "")
    folder_id = wiz.request.query("folder_id", "")
    week_label = wiz.request.query("week_label", "")
    deadline = wiz.request.query("deadline", "")
    guide_notes = wiz.request.query("guide_notes", "")
    report_items_raw = wiz.request.query("report_items", "[]")
    reference_doc_ids_raw = wiz.request.query("reference_doc_ids", "[]")
    keep_reference_files_raw = wiz.request.query("keep_reference_files", None)
    user_id = wiz.session.get("id")

    try:
        instance = struct.doc.get_instance(id)
    except Exception as e:
        wiz.response.status(400, message=str(e))

    if not instance:
        wiz.response.status(404, message="문서를 찾을 수 없습니다.")

    settings = instance.get('settings_json', {})
    if not isinstance(settings, dict):
        settings = {}
    settings = _settings_with_template_references(instance, settings)

    try:
        reference_doc_ids = json.loads(reference_doc_ids_raw)
        if not isinstance(reference_doc_ids, list):
            reference_doc_ids = []
    except Exception:
        reference_doc_ids = []

    docs_by_id = {doc['id']: doc for doc in _reference_docs(user_id, id)}
    selected_docs = [docs_by_id[doc_id] for doc_id in reference_doc_ids if doc_id in docs_by_id]

    style_reference = []
    for doc in selected_docs:
        preview = (doc.get('preview') or '').strip()
        if preview:
            style_reference.append(f"[이전 문서 예시: {doc.get('title', '')}]\n{preview}")

    instruction_ids_raw = wiz.request.query("instruction_ids", "[]")
    try:
        instruction_ids = json.loads(instruction_ids_raw)
        if not isinstance(instruction_ids, list):
            instruction_ids = []
    except Exception:
        instruction_ids = []

    try:
        report_items = json.loads(report_items_raw)
        if not isinstance(report_items, list):
            report_items = []
        report_items = [str(item or '').strip() for item in report_items if str(item or '').strip()]
    except Exception:
        report_items = []

    settings['guide_notes'] = guide_notes
    settings['report_items'] = report_items
    settings['reference_doc_ids'] = [doc.get('id', '') for doc in selected_docs]
    settings['reference_doc_titles'] = [doc.get('title', '') for doc in selected_docs]
    settings['style_reference'] = "\n\n".join(style_reference)[:6000]
    settings['instruction_ids'] = instruction_ids

    fields = {
        'week_label': week_label,
        'deadline': deadline,
        'settings_json': settings
    }

    # 참고자료 파일 처리
    uploaded_refs = []
    try:
        uploaded_refs = wiz.request.files() or []
    except Exception:
        uploaded_refs = []

    ref_file = wiz.request.file("reference_file")
    if ref_file and not any(getattr(item, 'filename', '') == getattr(ref_file, 'filename', '') for item in uploaded_refs):
        uploaded_refs.append(ref_file)

    existing_reference_files = settings.get('reference_files', []) if isinstance(settings.get('reference_files', []), list) else []
    if keep_reference_files_raw is not None:
        try:
            keep_reference_files = json.loads(keep_reference_files_raw or "[]")
            if not isinstance(keep_reference_files, list):
                keep_reference_files = []
            keep_reference_files = {str(item) for item in keep_reference_files}
            template_reference_names = {item.get('filename') for item in _template_reference_files(instance) if item.get('filename')}
            removed_defaults = settings.get('removed_template_reference_files', [])
            if not isinstance(removed_defaults, list):
                removed_defaults = []
            removed_defaults = {str(item) for item in removed_defaults}
            removed_defaults.update(filename for filename in template_reference_names if filename not in keep_reference_files)
            removed_defaults.difference_update(filename for filename in template_reference_names if filename in keep_reference_files)
            settings['removed_template_reference_files'] = sorted(removed_defaults)
            existing_reference_files = [
                item for item in existing_reference_files
                if isinstance(item, dict) and item.get('filename') in keep_reference_files
            ]
        except Exception:
            pass

    aggregated_reference_texts = []
    preserved_reference_files = []
    for item in existing_reference_files:
        if isinstance(item, dict) and item.get('filename'):
            normalized_item = _normal_ref_item(item, source=item.get('source', 'manual'))
            if not normalized_item:
                continue
            preserved_reference_files.append(normalized_item)
            text = str(item.get('text_excerpt', '')).strip()
            if text:
                prefix = '기본 참고자료' if normalized_item.get('source') == 'template' else '참고자료'
                aggregated_reference_texts.append(f"[{prefix}: {item.get('original_name', item.get('filename', ''))}]\n{text}")

    if uploaded_refs:
        fs = wiz.project.fs("data", "uploads", "references")
        fs.makedirs("")
        for ref in uploaded_refs:
            if not ref or not getattr(ref, 'filename', ''):
                continue
            file_id = str(uuid.uuid4())[:8]
            ext = ref.filename.rsplit('.', 1)[-1].lower() if '.' in ref.filename else 'bin'
            saved_name = f"{file_id}.{ext}"
            filepath = fs.abspath(saved_name)
            ref.save(filepath)

            text_excerpt = ''
            try:
                text_excerpt = _extract_reference_text(filepath, ext)
            except Exception:
                text_excerpt = ''

            item = {
                'filename': saved_name,
                'original_name': ref.filename,
                'ext': ext,
                'text_excerpt': text_excerpt[:4000],
                'source': 'manual'
            }
            preserved_reference_files.append(item)
            if text_excerpt:
                aggregated_reference_texts.append(f"[참고자료: {ref.filename}]\n{text_excerpt[:4000]}")

    settings['reference_files'] = preserved_reference_files[:20]
    settings['reference_file_names'] = [item.get('original_name', item.get('filename', '')) for item in settings['reference_files']]
    settings['reference_text'] = '\n\n'.join(aggregated_reference_texts)[:12000]
    if settings['reference_files']:
        settings['reference_file'] = settings['reference_files'][-1].get('filename', '')
    else:
        settings['reference_file'] = ''
    _promote_instance_references_to_template(instance, settings)

    fields['settings_json'] = settings
    if title != "":
        fields['title'] = title
    if status != "":
        fields['status'] = status
    fields['folder_id'] = folder_id

    try:
        struct.doc.update_instance(id, **fields)
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

    fields = {
        'folder_id': folder_id,
        'week_label': week_label,
        'deadline': deadline
    }
    if title != "":
        fields['title'] = title
    if status != "":
        fields['status'] = status

    try:
        struct.doc.update_instance_meta(id, **fields)
    except Exception as e:
        wiz.response.status(400, message=str(e))
    wiz.response.status(200)

def delete_instance():
    id = wiz.request.query("id", True)
    try:
        struct.doc.delete_instance(id)
    except Exception as e:
        wiz.response.status(400, message=str(e))
    wiz.response.status(200)

def generate():
    """SSE 스트리밍으로 AI 문서 생성"""
    flask = wiz.response._flask
    id = wiz.request.query("id", True)

    # Request Context 내에서 필요한 데이터 미리 추출
    instance = struct.doc.get_instance(id)
    if not instance:
        wiz.response.status(404, message="문서를 찾을 수 없습니다.")
    instance = _ensure_template_references(instance)
    instance = _ensure_editable_schema(instance)

    user_id = wiz.session.get("id")
    ai_config = struct.ai_agent.get_config()

    # 양식 필드 스키마 추출
    content_json = instance.get('content_json', {})
    settings_json = instance.get('settings_json', {}) if isinstance(instance.get('settings_json', {}), dict) else {}
    fields_schema = content_json.get('fields_schema', {})
    if not isinstance(fields_schema, dict):
        fields_schema = {}
    template_id = content_json.get('template_id', '') or instance.get('template_id', '')
    file_type = content_json.get('file_type', '')
    template_file_path = content_json.get('template_file_path', '') or content_json.get('uploaded_file', '')
    converted_docx_path = fields_schema.get('converted_docx_path', '')
    editable_docx_path = (
        content_json.get('editable_docx_path', '')
        or fields_schema.get('editable_docx_path', '')
        or converted_docx_path
    )
    if not editable_docx_path and file_type == 'docx':
        editable_docx_path = template_file_path
    generation_mode = content_json.get('generation_mode', '')
    report_items = settings_json.get('report_items', []) if isinstance(settings_json, dict) else []
    if not isinstance(report_items, list):
        report_items = []

    # template_file_path가 없으면 template_id로 DB에서 조회
    if not template_file_path and template_id:
        try:
            tpl = struct.doc.get_template(template_id)
            if tpl:
                template_file_path = tpl.get('file_path', '')
                if not file_type:
                    file_type = tpl.get('file_type', '')
                # fields_schema가 비어있으면 template에서 복원
                if not fields_schema.get('fields') and tpl.get('fields_schema'):
                    tpl_schema = tpl['fields_schema'] if isinstance(tpl['fields_schema'], dict) else {}
                    if not converted_docx_path:
                        converted_docx_path = tpl_schema.get('converted_docx_path', '')
                    if not editable_docx_path:
                        editable_docx_path = tpl_schema.get('editable_docx_path', '') or converted_docx_path
                    if not editable_docx_path and file_type == 'docx':
                        editable_docx_path = template_file_path
        except Exception:
            pass

    enriched_schema, enriched_docx_path = _enrich_schema_from_editable_docx(
        instance, content_json, fields_schema,
        template_file_path=template_file_path,
        editable_docx_path=editable_docx_path,
        converted_docx_path=converted_docx_path,
        file_type=file_type
    )
    if enriched_schema is not fields_schema:
        fields_schema = enriched_schema
        content_json['fields_schema'] = fields_schema
        if enriched_docx_path:
            editable_docx_path = enriched_docx_path
            content_json['editable_docx_path'] = enriched_docx_path
            if not converted_docx_path:
                converted_docx_path = enriched_docx_path
        try:
            struct.doc.update_instance(id, content_json=content_json)
            instance['content_json'] = content_json
        except Exception:
            pass

    # 섹션 구조 결정
    section_defs = []
    if fields_schema.get('sections'):
        for idx, sec in enumerate(fields_schema['sections']):
            section_defs.append({
                'title': sec.get('section_title', sec.get('title', f'섹션 {idx+1}')),
                'hint': sec.get('content', ''),
                'key': sec.get('section_key', f'section_{idx+1}')
            })
    elif template_id:
        try:
            parser_sections = struct.file_parser.create_sections_from_template(template_id)
            for sec in parser_sections:
                section_defs.append({
                    'title': sec['section_title'],
                    'hint': sec.get('content', ''),
                    'key': sec['section_key']
                })
        except Exception:
            pass

    if not section_defs:
        raw_text = fields_schema.get('raw_text', '')
        if raw_text:
            try:
                parsed = struct.file_parser._split_text_to_sections(raw_text)
                for idx, sec in enumerate(parsed):
                    section_defs.append({
                        'title': sec.get('title', f'섹션 {idx+1}'),
                        'hint': sec.get('content', ''),
                        'key': f'section_{idx+1}'
                    })
            except Exception:
                pass

    if not section_defs:
        section_defs = [
            {'title': '개요', 'hint': '문서 개요 및 목적', 'key': 'overview'},
            {'title': '본문', 'hint': '주요 내용', 'key': 'body'},
            {'title': '결론', 'hint': '결론 및 향후 계획', 'key': 'conclusion'}
        ]

    # ── table_fills 기반 섹션 보완 ──
    # 이미 구성된 section_defs에 없는 주차/활동/결론 섹션을 table_fills에서 추출해 추가
    table_fills_for_sections = fields_schema.get('table_fills', [])
    if table_fills_for_sections:
        try:
            extra_sections = struct.file_parser.infer_sections_from_table_fills(table_fills_for_sections)
            existing_titles = {s['title'] for s in section_defs}
            for sec in extra_sections:
                if sec['section_title'] not in existing_titles:
                    section_defs.append({
                        'title': sec['section_title'],
                        'hint': sec.get('content', ''),
                        'key': sec['section_key']
                    })
                    existing_titles.add(sec['section_title'])
        except Exception:
            pass

    # ── raw_text 기반 섹션 보완 ──
    # 헤딩(1. 2. 3. / 가. 나. 등)을 파싱해 추가 섹션 도출 (기존 섹션과 중복 제외)
    raw_text_for_sections = fields_schema.get('raw_text', '')
    if raw_text_for_sections and len(section_defs) <= 2:
        try:
            parsed_extra = struct.file_parser._split_text_to_sections(raw_text_for_sections)
            existing_titles = {s['title'] for s in section_defs}
            for idx, sec in enumerate(parsed_extra):
                t = sec.get('title', '').strip()
                if t and t not in existing_titles and t not in ('서두', '본문', '개요'):
                    key = 'raw_' + str(idx)
                    section_defs.append({
                        'title': t,
                        'hint': sec.get('content', ''),
                        'key': key
                    })
                    existing_titles.add(t)
        except Exception:
            pass

    if len(section_defs) > 1:
        non_generic_defs = [
            sec for sec in section_defs
            if str(sec.get('title', '') or '').strip() not in ('서두', '개요')
        ]
        if non_generic_defs:
            section_defs = non_generic_defs

    if generation_mode == 'template-fill':
        meaningful_defs = []
        seen_section_titles = set()
        for sec in section_defs:
            title = str(sec.get('title', '') or '').strip()
            if not _is_meaningful_template_section(title):
                continue
            if title in seen_section_titles:
                continue
            meaningful_defs.append(sec)
            seen_section_titles.add(title)
        if meaningful_defs:
            section_defs = meaningful_defs

    if report_items and generation_mode != 'template-fill':
        section_defs = []
        for idx, item in enumerate(report_items):
            section_defs.append({
                'title': item,
                'hint': f'{item} 항목을 문서 주제와 실험 맥락에 맞게 작성',
                'key': f'report_item_{idx+1}'
            })

    agent = struct.ai_agent

    def _generate():
        try:
            yield _sse({'type': 'progress', 'progress': 5, 'message': '양식 구조를 먼저 이해하는 중...'})
            yield _sse({'type': 'progress', 'progress': 10, 'message': f'{len(section_defs)}개 작성 섹션 감지'})

            if not ai_config:
                yield _sse({'type': 'progress', 'progress': 20, 'message': 'AI 설정이 없습니다. 기본 템플릿으로 생성합니다.'})

            struct.doc.update_instance(id, status='writing')

            # Phase 1: 양식 이해
            raw_text = fields_schema.get('raw_text', '') if isinstance(fields_schema, dict) else ''
            tables = fields_schema.get('tables', []) if isinstance(fields_schema, dict) else []
            schema_sections = fields_schema.get('sections', []) if isinstance(fields_schema, dict) else []
            schema_fields = fields_schema.get('fields', []) if isinstance(fields_schema, dict) else []
            form_desc = struct.file_parser.build_form_description(tables, schema_sections, schema_fields, raw_text)
            form_analysis = ''
            if ai_config and (tables or raw_text):
                analysis_events = []
                ctx = agent.build_context(id, user_id)
                form_analysis = agent._analyze_form_intent(ai_config, ctx, raw_text, form_desc, analysis_events)
                for ev in analysis_events:
                    yield _sse(ev)

            yield _sse({'type': 'progress', 'progress': 18, 'message': '양식 해석 완료. 본문 초안을 먼저 작성합니다.'})
            struct.doc.clear_sections(id)

            # Phase 2: 텍스트 본문 먼저 작성
            section_values = {}
            total = max(1, len(section_defs))
            for i, sec_def in enumerate(section_defs):
                progress = 20 + int((i / total) * 38)
                yield _sse({'type': 'progress', 'progress': progress, 'message': f"본문 작성 중: {sec_def['title']}"})
                try:
                    sec_events = []
                    content = agent.generate_section(
                        id, sec_def, user_id, events=sec_events,
                        field_values={}, form_desc=form_desc, form_analysis=form_analysis
                    )
                    for ev in sec_events:
                        yield _sse(ev)
                except Exception as e:
                    content = f"[AI 생성 실패: {str(e)}]\n\n{sec_def.get('hint', '')}"

                section_values[sec_def['title']] = content
                struct.doc.create_section({
                    'instance_id': id,
                    'section_key': sec_def.get('key', f'section_{i+1}'),
                    'section_title': sec_def['title'],
                    'content': content,
                    'sort_order': i + 1,
                    'status': 'done'
                })
                yield _sse({'type': 'section', 'title': sec_def['title'], 'index': i + 1})

            # Phase 3: 그래프/이미지 배치 확인
            yield _sse({'type': 'progress', 'progress': 60, 'message': '그래프/이미지 배치 상태를 확인합니다.'})
            try:
                image_count = len(struct.graph_gen.list_images(id))
                placements = struct.graph_gen.get_placements(id)
                placed_count = sum(len(v) for v in placements.values()) if isinstance(placements, dict) else 0
                if image_count:
                    yield _sse({'type': 'detail', 'phase': 'graph_assets', 'message': f'등록된 이미지/그래프 {image_count}개, 배치 {placed_count}개 확인'})
                else:
                    yield _sse({'type': 'detail', 'phase': 'graph_assets', 'message': '등록된 그래프가 없어 텍스트 중심으로 작성합니다.'})
            except Exception:
                yield _sse({'type': 'detail', 'phase': 'graph_assets', 'message': '그래프 배치 확인을 건너뜁니다.'})

            # Phase 4: 작성된 본문을 참고해 양식 필드값 매핑
            yield _sse({'type': 'detail', 'message': '작성된 본문을 기준으로 양식 칸 매핑을 시작합니다...'})
            field_events = []
            field_result = agent.generate_field_values(
                id, user_id, events=field_events, include_sections=False,
                precomputed_form_analysis=form_analysis,
                precomputed_form_desc=form_desc
            )
            for ev in field_events:
                yield _sse(ev)
            field_values = struct.ai_agent.sanitize_generated_fields(field_result.get('values', {}))
            missing_fields = field_result.get('missing_fields', [])
            followup_questions = field_result.get('followup_questions', []) if isinstance(field_result, dict) else []

            if field_values:
                yield _sse({'type': 'progress', 'progress': 72, 'message': f'{len(field_values)}개 양식 항목 값을 준비했습니다.'})
            if missing_fields:
                yield _sse({'type': 'progress', 'progress': 74, 'message': f'추가 정보가 필요한 항목: {", ".join(missing_fields[:5])}'})
            if followup_questions:
                yield _sse({
                    'type': 'needs_input',
                    'message': '양식 해석 결과, 더 정확한 작성을 위해 사용자 확인이 필요한 항목이 있습니다.',
                    'missing_fields': missing_fields[:10],
                    'questions': followup_questions[:5]
                })

            # Phase 5: 마지막에 템플릿 채우기 (DOCX/HWP/PDF)
            generated_output_file = ''
            actual_template_path = ''

            # 사용할 DOCX 템플릿 경로 결정
            tpl_fs = wiz.project.fs("data", "uploads", "templates") if template_id else wiz.project.fs("data", "uploads", "instances")

            if editable_docx_path:
                candidate = tpl_fs.abspath(editable_docx_path)
                if os.path.exists(candidate):
                    actual_template_path = candidate
            if not actual_template_path and file_type == 'docx' and template_file_path:
                actual_template_path = tpl_fs.abspath(template_file_path)
            elif not actual_template_path and file_type in ('hwp', 'doc', 'pdf') and template_file_path:
                # 1) 변환된 DOCX가 이미 있으면 사용
                if converted_docx_path:
                    candidate = tpl_fs.abspath(converted_docx_path)
                    if os.path.exists(candidate):
                        actual_template_path = candidate
                # 2) 원본 옆에 _converted.docx가 있는지 확인
                if not actual_template_path:
                    original_path = tpl_fs.abspath(template_file_path)
                    basename_no_ext = os.path.splitext(original_path)[0]
                    candidate = basename_no_ext + '_converted.docx'
                    if os.path.exists(candidate):
                        actual_template_path = candidate
                # 3) 없으면 실시간 변환
                if not actual_template_path:
                    original_path = tpl_fs.abspath(template_file_path)
                    if os.path.exists(original_path):
                        try:
                            yield _sse({'type': 'progress', 'progress': 82, 'message': f'{file_type.upper()} → DOCX 변환 중...'})
                            actual_template_path = struct.file_parser._convert_to_docx(original_path)
                            yield _sse({'type': 'detail', 'message': f'DOCX 변환 완료: {os.path.basename(actual_template_path)}'})
                        except Exception as conv_err:
                            yield _sse({'type': 'warning', 'message': f'DOCX 변환 실패 (섹션 기반으로 대체 생성): {str(conv_err)[:200]}'})

            if actual_template_path and os.path.exists(actual_template_path):
                output_fs = wiz.project.fs("data", "outputs", "documents")
                output_fs.makedirs("")
                generated_output_file = f"{uuid.uuid4().hex[:12]}.docx"
                output_abs = output_fs.abspath(generated_output_file)

                yield _sse({'type': 'progress', 'progress': 85, 'message': '마지막 단계: 원본 양식에 내용 삽입 중...'})
                try:
                    struct.file_parser.fill_template_document(actual_template_path, output_abs, field_values, section_values, layout_options=content_json)
                except Exception as fill_err:
                    generated_output_file = ''
                    output_abs = ''
                    yield _sse({'type': 'warning', 'message': f'원본 양식 삽입 실패. 작성 본문은 유지합니다: {str(fill_err)[:200]}'})

                if generated_output_file and output_abs and os.path.exists(output_abs):
                    try:
                        struct.file_parser.apply_images_to_docx(output_abs, output_abs, id)
                    except Exception as img_err:
                        yield _sse({'type': 'warning', 'message': f'이미지 삽입은 건너뜁니다: {str(img_err)[:200]}'})

                    # 채워진 DOCX를 파싱하여 표시용 섹션 추출
                    try:
                        parsed_output = struct.file_parser.parse(output_abs)
                        parsed_sections = parsed_output.get('sections', []) if isinstance(parsed_output, dict) else []
                        if _parsed_sections_are_meaningful(parsed_sections, section_values):
                            struct.doc.clear_sections(id)
                            for idx, sec in enumerate(parsed_sections):
                                struct.doc.create_section({
                                    'instance_id': id,
                                    'section_key': f'filled_{idx+1}',
                                    'section_title': sec.get('title', f'섹션 {idx+1}'),
                                    'content': sec.get('content', ''),
                                    'sort_order': idx + 1,
                                    'status': 'done'
                                })
                        else:
                            yield _sse({'type': 'detail', 'message': '출력 문서 섹션 파싱 내용이 부족해 먼저 작성한 본문을 유지합니다.'})
                    except Exception as parse_err:
                        yield _sse({'type': 'warning', 'message': f'출력 문서 미리보기 파싱은 건너뜁니다: {str(parse_err)[:200]}'})
                    yield _sse({'type': 'progress', 'progress': 88, 'message': '원본 양식에 내용을 삽입했습니다.'})

            if not generated_output_file:
                yield _sse({'type': 'detail', 'message': '원본 양식 파일이 없어 먼저 작성한 본문 섹션을 결과로 유지합니다.'})

            # Phase 6: 결과 저장
            content_json_updated = instance.get('content_json', {}) if isinstance(instance.get('content_json', {}), dict) else {}
            content_json_updated['generated_fields'] = field_values
            content_json_updated['missing_fields'] = missing_fields
            content_json_updated['followup_questions'] = followup_questions[:5] if isinstance(followup_questions, list) else []
            content_json_updated['generation_pipeline'] = [
                'template_understanding',
                'draft_text_sections',
                'graph_asset_check',
                'field_mapping',
                'template_insertion'
            ]
            # 템플릿 경로 보존 (다음 재생성/다운로드용)
            if template_file_path:
                content_json_updated['template_file_path'] = template_file_path
            if file_type:
                content_json_updated['file_type'] = file_type
            if editable_docx_path:
                content_json_updated['editable_docx_path'] = editable_docx_path
                fschema = content_json_updated.get('fields_schema', {})
                if isinstance(fschema, dict):
                    fschema['editable_docx_path'] = editable_docx_path
                    if converted_docx_path and not fschema.get('converted_docx_path'):
                        fschema['converted_docx_path'] = converted_docx_path
                    content_json_updated['fields_schema'] = fschema
            if generated_output_file:
                content_json_updated['generated_output_file'] = generated_output_file
            struct.doc.update_instance(id, content_json=content_json_updated)

            struct.doc.update_instance(id, status='review')

            # 프로필 학습 (실패해도 무시)
            try:
                agent.learn_from_conversation(id, user_id)
            except Exception:
                pass

            yield _sse({'type': 'done', 'progress': 100})

        except Exception as e:
            try:
                struct.doc.update_instance(id, status='draft')
            except Exception:
                pass
            yield _sse({'type': 'error', 'message': str(e)})

    resp = flask.Response(_generate(), mimetype='text/event-stream')
    resp.headers['Cache-Control'] = 'no-cache'
    resp.headers['X-Accel-Buffering'] = 'no'
    wiz.response.response(resp)

def chat():
    # FormData(multipart) + URLSearchParams(urlencoded) 모두 지원하기 위해 Flask request 직접 사용
    _flask = wiz.response._flask
    _req = _flask.request
    instance_id = (_req.form.get("instance_id") or _req.args.get("instance_id") or '').strip()
    message = (_req.form.get("message") or _req.args.get("message") or '').strip()
    section_id = (_req.form.get("section_id") or _req.args.get("section_id") or '').strip()
    user_id = wiz.session.get("id")

    if not instance_id or not message:
        wiz.response.status(400, message="instance_id와 message가 필요합니다.")

    # 이미지 파일이 첨부된 경우 업로드 처리
    uploaded_image_info = None
    try:
        file = _req.files.get("image")
        if file:
            ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
            if ext == 'csv':
                uploaded_image_info = struct.graph_gen.generate_chart_from_csv_upload(file, instance_id, message, user_id)
                source_csv = uploaded_image_info.get('source_csv', {}) if isinstance(uploaded_image_info, dict) else {}
                message += f"\n[첨부 CSV 그래프 생성: {source_csv.get('original_name', file.filename)} → {uploaded_image_info.get('filename', '')}]"
            elif ext in ('hwp', 'pdf', 'docx', 'doc'):
                # 문서 파일이면 텍스트 추출해서 채팅 컨텍스트에 포함
                import tempfile as _tmpmod
                import uuid as _uuid
                tmp_suffix = f".{ext}"
                tmp_path = None
                try:
                    with _tmpmod.NamedTemporaryFile(suffix=tmp_suffix, delete=False) as tmp:
                        file.save(tmp.name)
                        tmp_path = tmp.name
                    parse_result = struct.file_parser.parse(tmp_path)
                    doc_text = (parse_result.get('text', '') or '').strip()[:5000]
                    if doc_text:
                        message += f"\n\n[첨부 문서: {file.filename}]\n{doc_text}"
                    else:
                        message += f"\n[첨부 문서: {file.filename} (텍스트 추출 실패)]"
                except Exception as _e:
                    message += f"\n[첨부 문서: {file.filename} (파싱 오류: {str(_e)[:100]})]"
                finally:
                    try:
                        if tmp_path and os.path.exists(tmp_path):
                            os.unlink(tmp_path)
                    except Exception:
                        pass
            else:
                uploaded_image_info = struct.graph_gen.upload_image(file, instance_id)
                message += f"\n[첨부 이미지: {uploaded_image_info.get('original_name', uploaded_image_info.get('filename', ''))}]"
    except Exception:
        pass

    # AI 응답 생성 (ai_agent 사용). 현재 메시지는 ai_agent에 직접 넘기고,
    # 저장은 응답 생성 후에 한다. 먼저 저장하면 history에 같은 메시지가 중복된다.
    try:
        result = struct.ai_agent.chat(instance_id, message, user_id, section_id=section_id or None)
    except Exception as e:
        wiz.response.status(500, message=f"AI 응답 오류: {str(e)[:200]}")
    reply = result.get('reply', '') if isinstance(result, dict) else str(result)
    content_modified = result.get('content_modified', False) if isinstance(result, dict) else False
    modified_sections = result.get('modified_sections', []) if isinstance(result, dict) else []

    # 대화 저장
    try:
        struct.ai.add_chat({'instance_id': instance_id, 'role': 'user', 'content': message})
    except Exception:
        pass
    try:
        struct.ai.add_chat({'instance_id': instance_id, 'role': 'assistant', 'content': reply})
    except Exception:
        pass

    # AI가 섹션을 수정한 경우 캐시 DOCX 초기화
    if content_modified:
        try:
            inst = struct.doc.get_instance(instance_id)
            if inst:
                cj = inst.get('content_json', {}) or {}
                if cj.get('generated_output_file'):
                    cj['generated_output_file'] = ''
                    struct.doc.update_instance(instance_id, content_json=cj)
        except Exception:
            pass

    wiz.response.status(200, reply=reply, content_modified=content_modified,
                        modified_sections=modified_sections,
                        uploaded_image=uploaded_image_info)

def save_followup_answer():
    id = wiz.request.query("id", True)
    question = wiz.request.query("question", True)
    answer = wiz.request.query("answer", True)

    try:
        instance = struct.doc.get_instance(id)
    except Exception as e:
        wiz.response.status(400, message=str(e))

    if not instance:
        wiz.response.status(404, message="문서를 찾을 수 없습니다.")

    settings_json = instance.get('settings_json', {}) if isinstance(instance.get('settings_json', {}), dict) else {}
    content_json = instance.get('content_json', {}) if isinstance(instance.get('content_json', {}), dict) else {}

    followup_answers = content_json.get('followup_answers', {})
    if not isinstance(followup_answers, dict):
        followup_answers = {}
    followup_answers[question] = answer

    guide_notes = str(settings_json.get('guide_notes', '') or '').strip()
    answer_block = f"[생성 중 추가 답변]\n질문: {question}\n답변: {answer}"
    existing_blocks = [
        f"질문: {q}\n답변: {a}"
        for q, a in followup_answers.items()
        if str(q).strip() and str(a).strip()
    ]
    if existing_blocks:
        merged_block = "[생성 중 추가 답변]\n" + "\n\n".join(existing_blocks)
        if guide_notes:
            prefix = guide_notes.split('[생성 중 추가 답변]\n', 1)[0].rstrip()
            guide_notes = f"{prefix}\n\n{merged_block}" if prefix else merged_block
        else:
            guide_notes = merged_block
    elif answer_block not in guide_notes:
        guide_notes = f"{guide_notes}\n\n{answer_block}".strip() if guide_notes else answer_block

    content_json['followup_answers'] = followup_answers
    settings_json['guide_notes'] = guide_notes

    try:
        struct.doc.update_instance(id, settings_json=settings_json, content_json=content_json)
    except Exception as e:
        wiz.response.status(400, message=str(e))

    wiz.response.status(200, guide_notes=guide_notes, followup_answers=followup_answers)

def save_section():
    id = wiz.request.query("id", True)
    content = wiz.request.query("content", "")
    try:
        struct.doc.update_section(id, content=content, status='done')
        # 섹션이 수정되면 캐싱된 출력 파일 초기화 (PDF/미리보기 동기화)
        section = struct.doc.get_section(id)
        if section and section.get('instance_id'):
            try:
                inst = struct.doc.get_instance(section['instance_id'])
                if inst:
                    cj = inst.get('content_json', {}) or {}
                    if cj.get('generated_output_file'):
                        cj['generated_output_file'] = ''
                        struct.doc.update_instance(section['instance_id'], content_json=cj)
            except Exception:
                pass
    except Exception as e:
        wiz.response.status(400, message=str(e))
    wiz.response.status(200)

def get_field_values():
    """생성된 양식 필드값 + 표 구조 반환 (웹 에디터용)"""
    id = wiz.request.query("id", True)
    instance = struct.doc.get_instance(id)
    if not instance:
        wiz.response.status(404, message="문서를 찾을 수 없습니다.")
    instance = _ensure_editable_schema(instance)
    instance = _ensure_template_references(instance)
    instance = _sanitize_instance_generated_fields(instance)
    content_json = instance.get('content_json', {}) or {}
    fields_schema = content_json.get('fields_schema', {}) or {}
    table_fills = fields_schema.get('table_fills', []) or []
    generated_fields = content_json.get('generated_fields', {}) or {}
    field_styles = content_json.get('field_styles', {}) or {}
    existing_fills, existing_values = _editor_fields_from_existing_tables(fields_schema)
    if existing_fills and (
        content_json.get('archive_only')
        or instance.get('source_type') in ['archive', 'upload']
        or not table_fills
    ):
        table_fills = existing_fills
    merged_values = dict(existing_values)
    if isinstance(generated_fields, dict):
        merged_values.update(generated_fields)
    wiz.response.status(200, field_values=merged_values, field_styles=field_styles, table_fills=table_fills)

def save_field_value():
    """개별 양식 필드값 저장"""
    id = wiz.request.query("id", True)
    label = wiz.request.query("label", True)
    content = wiz.request.query("content", "")
    style_raw = wiz.request.query("style", "")
    layout_raw = wiz.request.query("layout", "")
    delete_flag = str(wiz.request.query("delete", "") or "").lower() in ("1", "true", "yes")
    skip_content = str(wiz.request.query("skip_content", "") or "").lower() in ("1", "true", "yes")
    try:
        instance = struct.doc.get_instance(id)
        if not instance:
            wiz.response.status(404, message="문서를 찾을 수 없습니다.")
        content_json = instance.get('content_json', {}) or {}
        if delete_flag:
            for key in ('generated_fields', 'field_styles', 'field_layouts'):
                if isinstance(content_json.get(key), dict):
                    content_json[key].pop(label, None)
        else:
            if not skip_content:
                if 'generated_fields' not in content_json or not isinstance(content_json['generated_fields'], dict):
                    content_json['generated_fields'] = {}
                content_json['generated_fields'][label] = content
            if style_raw:
                try:
                    style = json.loads(style_raw)
                except Exception:
                    style = {}
                if isinstance(style, dict):
                    if 'field_styles' not in content_json or not isinstance(content_json.get('field_styles'), dict):
                        content_json['field_styles'] = {}
                    content_json['field_styles'][label] = {
                        'font_family': style.get('font_family', 'gothic'),
                        'font_size': style.get('font_size', 9),
                        'bold': bool(style.get('bold', False)),
                        'align': style.get('align', 'left'),
                        'color': style.get('color', '#080808')
                    }
            if layout_raw:
                try:
                    layout = json.loads(layout_raw)
                except Exception:
                    layout = {}
                if isinstance(layout, dict):
                    def _num(name, default=0, minimum=0, maximum=100):
                        try:
                            value = float(layout.get(name, default))
                        except Exception:
                            value = default
                        return max(minimum, min(maximum, value))

                    if 'field_layouts' not in content_json or not isinstance(content_json.get('field_layouts'), dict):
                        content_json['field_layouts'] = {}
                    try:
                        page_no = int(layout.get('page') or 1)
                    except Exception:
                        page_no = 1
                    content_json['field_layouts'][label] = {
                        'page': max(1, page_no),
                        'left': _num('left'),
                        'top': _num('top'),
                        'width': _num('width', 8, 1, 100),
                        'height': _num('height', 3, 1, 100)
                    }
        # 수정 시 캐시 초기화 (PDF/미리보기 동기화)
        if isinstance(content_json.get('generated_fields'), dict):
            content_json['generated_fields'] = struct.ai_agent.sanitize_generated_fields(content_json.get('generated_fields', {}))
        content_json['generated_output_file'] = ''
        struct.doc.update_instance(id, content_json=content_json)
    except Exception as e:
        wiz.response.status(400, message=str(e))
    wiz.response.status(200)

def save_direct_overlays():
    """직접 편집기의 자유 텍스트 저장"""
    id = wiz.request.query("id", True)
    raw = wiz.request.query("overlays", "[]")
    normalized = []

    def _num(value, default, min_value, max_value):
        try:
            number = float(value)
        except Exception:
            number = float(default)
        return round(max(float(min_value), min(float(max_value), number)), 4)

    def _style(raw_style):
        if not isinstance(raw_style, dict):
            raw_style = {}
        family = str(raw_style.get('font_family', 'gothic') or 'gothic')
        if family not in ['gothic', 'myeongjo', 'batang', 'mono']:
            family = 'gothic'
        align = str(raw_style.get('align', 'left') or 'left')
        if align not in ['left', 'center', 'right']:
            align = 'left'
        color = str(raw_style.get('color', '#080808') or '#080808')
        if not isinstance(color, str) or len(color) != 7 or not color.startswith('#'):
            color = '#080808'
        return {
            'font_family': family,
            'font_size': _num(raw_style.get('font_size', 9), 9, 5, 28),
            'bold': bool(raw_style.get('bold', False)),
            'align': align,
            'color': color
        }

    try:
        overlays = json.loads(raw)
        if not isinstance(overlays, list):
            overlays = []

        for idx, item in enumerate(overlays):
            if not isinstance(item, dict):
                continue
            kind = str(item.get('type', 'text') or 'text')
            if kind == 'whiteout':
                continue
            if kind != 'text':
                kind = 'text'
            try:
                page = int(float(item.get('page') or 1))
            except Exception:
                page = 1
            normalized.append({
                'id': str(item.get('id') or f'overlay-{idx + 1}'),
                'type': kind,
                'page': max(1, min(999, page)),
                'left': _num(item.get('left', 8), 8, 0, 98),
                'top': _num(item.get('top', 8), 8, 0, 98),
                'width': _num(item.get('width', 28), 28, 1, 100),
                'height': _num(item.get('height', 8), 8, 1, 100),
                'text': str(item.get('text') or ''),
                'style': _style(item.get('style', {})),
                'border': bool(item.get('border', False))
            })

        instance = struct.doc.get_instance(id)
        if not instance:
            wiz.response.status(404, message="문서를 찾을 수 없습니다.")
        content_json = instance.get('content_json', {}) or {}
        content_json['direct_overlays'] = normalized
        content_json['generated_output_file'] = ''
        struct.doc.update_instance(id, content_json=content_json)
    except Exception as e:
        wiz.response.status(400, message=str(e))
    wiz.response.status(200, overlays=normalized)

def save_table_spacing():
    """직접 편집기에서 조정한 표 사이 추가 간격 저장"""
    id = wiz.request.query("id", True)
    spacing_id = wiz.request.query("spacing_id", True)
    try:
        page = int(wiz.request.query("page", "1") or 1)
    except Exception:
        page = 1
    try:
        after_table = int(wiz.request.query("after_table", "0") or 0)
    except Exception:
        after_table = 0
    try:
        before_table = int(wiz.request.query("before_table", "0") or 0)
    except Exception:
        before_table = 0
    try:
        docx_before_table = int(wiz.request.query("docx_before_table", "0") or 0)
    except Exception:
        docx_before_table = 0
    try:
        extra_pct = float(wiz.request.query("extra_pct", "0") or 0)
    except Exception:
        extra_pct = 0
    try:
        extra_pt = float(wiz.request.query("extra_pt", "0") or 0)
    except Exception:
        extra_pt = 0
    page_break = str(wiz.request.query("page_break", "0") or "0").lower() in ["1", "true", "yes", "on"]
    if before_table < 1 and after_table >= 1:
        before_table = after_table + 1

    try:
        instance = struct.doc.get_instance(id)
        if not instance:
            wiz.response.status(404, message="문서를 찾을 수 없습니다.")
        content_json = instance.get('content_json', {}) or {}
        if 'table_spacings' not in content_json or not isinstance(content_json.get('table_spacings'), dict):
            content_json['table_spacings'] = {}
        if before_table < 1 or (extra_pct <= 0 and extra_pt <= 0 and not page_break):
            content_json['table_spacings'].pop(spacing_id, None)
        else:
            content_json['table_spacings'][spacing_id] = {
                'page': max(1, page),
                'before_table': before_table,
                'after_table': max(0, after_table),
                'docx_before_table': max(0, docx_before_table),
                'extra_pct': max(0, min(30, extra_pct)),
                'extra_pt': max(0, min(160, extra_pt)),
                'page_break': page_break
            }
        content_json['generated_output_file'] = ''
        struct.doc.update_instance(id, content_json=content_json)
    except Exception as e:
        wiz.response.status(400, message=str(e))
    wiz.response.status(200)

def save_field_layouts():
    """직접 편집기에서 여러 표 셀의 위치/크기를 한 번에 저장"""
    id = wiz.request.query("id", True)
    raw = wiz.request.query("layouts", "[]")

    def _num(value, default=0, minimum=0, maximum=100):
        try:
            number = float(value)
        except Exception:
            number = float(default)
        return round(max(float(minimum), min(float(maximum), number)), 4)

    try:
        instance = struct.doc.get_instance(id)
        if not instance:
            wiz.response.status(404, message="문서를 찾을 수 없습니다.")
        items = json.loads(raw)
        if not isinstance(items, list):
            items = []

        content_json = instance.get('content_json', {}) or {}
        if 'field_layouts' not in content_json or not isinstance(content_json.get('field_layouts'), dict):
            content_json['field_layouts'] = {}

        saved = 0
        for item in items:
            if not isinstance(item, dict):
                continue
            label = str(item.get('label') or '').strip()
            layout = item.get('layout', {})
            if not label or not isinstance(layout, dict):
                continue
            try:
                page_no = int(layout.get('page') or 1)
            except Exception:
                page_no = 1
            content_json['field_layouts'][label] = {
                'page': max(1, page_no),
                'left': _num(layout.get('left'), 0, 0, 99),
                'top': _num(layout.get('top'), 0, 0, 99),
                'width': _num(layout.get('width'), 8, 1, 100),
                'height': _num(layout.get('height'), 3, 1, 100),
            }
            saved += 1

        content_json['generated_output_file'] = ''
        struct.doc.update_instance(id, content_json=content_json)
    except Exception as e:
        wiz.response.status(400, message=str(e))
    wiz.response.status(200, saved=saved)

def regenerate_output():
    """현재 field_values로 템플릿 재생성 (SSE)"""
    flask = wiz.response._flask
    id = wiz.request.query("id", True)

    instance = struct.doc.get_instance(id)
    if not instance:
        wiz.response.status(404, message="문서를 찾을 수 없습니다.")
    instance = _ensure_editable_schema(instance)
    instance = _sanitize_instance_generated_fields(instance)

    content_json = instance.get('content_json', {}) or {}
    fields_schema = content_json.get('fields_schema', {}) or {}
    field_values = content_json.get('generated_fields', {}) or {}

    template_file_path = content_json.get('template_file_path', '') or content_json.get('uploaded_file', '')
    file_type = content_json.get('file_type', '')
    template_id = content_json.get('template_id', '') or instance.get('template_id', '')
    converted_docx_path = fields_schema.get('converted_docx_path', '')
    editable_docx_path = (
        content_json.get('editable_docx_path', '')
        or fields_schema.get('editable_docx_path', '')
        or converted_docx_path
    )
    if not editable_docx_path and file_type == 'docx':
        editable_docx_path = template_file_path

    if not template_file_path and template_id:
        try:
            tpl = struct.doc.get_template(template_id)
            if tpl:
                template_file_path = tpl.get('file_path', '')
                if not file_type:
                    file_type = tpl.get('file_type', '')
                if not converted_docx_path:
                    tpl_schema = tpl.get('fields_schema', {}) or {}
                    converted_docx_path = tpl_schema.get('converted_docx_path', '')
                if not editable_docx_path:
                    tpl_schema = tpl.get('fields_schema', {}) or {}
                    editable_docx_path = tpl_schema.get('editable_docx_path', '') or converted_docx_path
                if not editable_docx_path and file_type == 'docx':
                    editable_docx_path = template_file_path
        except Exception:
            pass

    # 섹션값 (DB)을 section_values dict로 변환
    try:
        secs = struct.doc.list_sections(id)
        section_values = {s['section_title']: s['content'] for s in secs if s.get('section_title')}
    except Exception:
        section_values = {}

    def _regen():
        try:
            tpl_fs = wiz.project.fs("data", "uploads", "templates") if template_id else wiz.project.fs("data", "uploads", "instances")
            actual_template_path = ''

            if editable_docx_path:
                candidate = tpl_fs.abspath(editable_docx_path)
                if os.path.exists(candidate):
                    actual_template_path = candidate
            if not actual_template_path and file_type == 'docx' and template_file_path:
                actual_template_path = tpl_fs.abspath(template_file_path)
            elif not actual_template_path and file_type in ('hwp', 'doc', 'pdf') and template_file_path:
                if converted_docx_path:
                    candidate = tpl_fs.abspath(converted_docx_path)
                    if os.path.exists(candidate):
                        actual_template_path = candidate
                if not actual_template_path:
                    original_path = tpl_fs.abspath(template_file_path)
                    basename_no_ext = os.path.splitext(original_path)[0]
                    candidate = basename_no_ext + '_converted.docx'
                    if os.path.exists(candidate):
                        actual_template_path = candidate
                if not actual_template_path:
                    original_path = tpl_fs.abspath(template_file_path)
                    if os.path.exists(original_path):
                        yield _sse({'type': 'progress', 'progress': 30, 'message': f'{file_type.upper()} → DOCX 변환 중...'})
                        actual_template_path = struct.file_parser._convert_to_docx(original_path)

            if not actual_template_path or not os.path.exists(actual_template_path):
                yield _sse({'type': 'error', 'message': '템플릿 파일을 찾을 수 없습니다.'})
                return

            yield _sse({'type': 'progress', 'progress': 60, 'message': '양식에 내용 삽입 중...'})
            output_fs = wiz.project.fs("data", "outputs", "documents")
            output_fs.makedirs("")
            generated_output_file = f"{uuid.uuid4().hex[:12]}.docx"
            output_abs = output_fs.abspath(generated_output_file)
            try:
                struct.file_parser.fill_template_document(actual_template_path, output_abs, field_values, section_values, layout_options=content_json)
            except Exception as fill_err:
                yield _sse({'type': 'error', 'message': f'양식 삽입 실패: {str(fill_err)[:300]}'})
                return
            try:
                struct.file_parser.apply_images_to_docx(output_abs, output_abs, id)
            except Exception as img_err:
                yield _sse({'type': 'warning', 'message': f'이미지 삽입은 건너뜁니다: {str(img_err)[:200]}'})

            # 기존 섹션 다시 파싱
            parsed_sections = []
            try:
                parsed_output = struct.file_parser.parse(output_abs)
                parsed_sections = parsed_output.get('sections', []) if isinstance(parsed_output, dict) else []
            except Exception as parse_err:
                yield _sse({'type': 'warning', 'message': f'출력 문서 미리보기 파싱은 건너뜁니다: {str(parse_err)[:200]}'})
            struct.doc.clear_sections(id)
            if _parsed_sections_are_meaningful(parsed_sections, section_values):
                for idx, sec in enumerate(parsed_sections):
                    struct.doc.create_section({
                        'instance_id': id,
                        'section_key': f'filled_{idx+1}',
                        'section_title': sec.get('title', f'섹션 {idx+1}'),
                        'content': sec.get('content', ''),
                        'sort_order': idx + 1,
                        'status': 'done'
                    })
            else:
                for idx, (title, content) in enumerate(section_values.items()):
                    struct.doc.create_section({
                        'instance_id': id,
                        'section_key': f'section_{idx+1}',
                        'section_title': title,
                        'content': content,
                        'sort_order': idx + 1,
                        'status': 'done'
                    })

            content_json_upd = instance.get('content_json', {}) or {}
            content_json_upd['generated_output_file'] = generated_output_file
            if editable_docx_path:
                content_json_upd['editable_docx_path'] = editable_docx_path
                fschema = content_json_upd.get('fields_schema', {})
                if isinstance(fschema, dict):
                    fschema['editable_docx_path'] = editable_docx_path
                    if converted_docx_path and not fschema.get('converted_docx_path'):
                        fschema['converted_docx_path'] = converted_docx_path
                    content_json_upd['fields_schema'] = fschema
            struct.doc.update_instance(id, content_json=content_json_upd)

            yield _sse({'type': 'progress', 'progress': 100, 'message': '재생성 완료'})
            yield _sse({'type': 'done', 'message': '완료'})
        except Exception as e:
            yield _sse({'type': 'error', 'message': str(e)[:300]})

    resp = flask.Response(_regen(), mimetype='text/event-stream')
    resp.headers['Cache-Control'] = 'no-cache'
    resp.headers['X-Accel-Buffering'] = 'no'
    wiz.response.response(resp)

def regenerate_section():
    instance_id = wiz.request.query("instance_id", True)
    section_id = wiz.request.query("section_id", True)
    instruction = wiz.request.query("instruction", "")
    user_id = wiz.session.get("id")

    try:
        new_content = struct.ai_agent.regenerate_section(instance_id, section_id, user_id, instruction)
        struct.doc.update_section(section_id, content=new_content, status='done')
        # 섹션 수정 시 캐시 DOCX 초기화
        try:
            inst = struct.doc.get_instance(instance_id)
            if inst:
                cj = inst.get('content_json', {}) or {}
                if cj.get('generated_output_file'):
                    cj['generated_output_file'] = ''
                    struct.doc.update_instance(instance_id, content_json=cj)
        except Exception:
            pass
    except Exception as e:
        wiz.response.status(400, message=str(e))
    wiz.response.status(200)

def ask_ai():
    """AI에게 추가 질문 생성 요청"""
    instance_id = wiz.request.query("instance_id", True)
    section_title = wiz.request.query("section_title", "")

    question = struct.ai_agent.ask_question(instance_id, section_title)
    if question:
        wiz.response.status(200, question=question)
    wiz.response.status(200, question=None)

def download_pdf():
    """PDF 다운로드"""
    id = wiz.request.query("id", True)
    flask = wiz.response._flask
    try:
        pdf_bytes = struct.doc_export.generate_pdf_weasy(id)
        instance = struct.doc.get_instance(id)
        title = instance.get('title', '문서') if instance else '문서'
    except Exception as e:
        wiz.response.status(400, message=str(e))

    filename = f"{title}.pdf"
    resp = flask.Response(pdf_bytes, mimetype='application/pdf')
    resp.headers['Content-Disposition'] = f"attachment; filename*=UTF-8''{url_quote(filename)}"
    wiz.response.response(resp)

def download_docx():
    """DOCX 다운로드"""
    id = wiz.request.query("id", True)
    flask = wiz.response._flask
    try:
        docx_bytes = struct.doc_export.generate_docx(id)
        instance = struct.doc.get_instance(id)
        title = instance.get('title', '문서') if instance else '문서'
    except Exception as e:
        wiz.response.status(400, message=str(e))

    filename = f"{title}.docx"
    resp = flask.Response(docx_bytes, mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    resp.headers['Content-Disposition'] = f"attachment; filename*=UTF-8''{url_quote(filename)}"
    wiz.response.response(resp)

def preview_pdf():
    """PDF 미리보기 (브라우저 내 표시)"""
    id = wiz.request.query("id", True)
    flask = wiz.response._flask
    try:
        pdf_bytes = struct.doc_export.generate_pdf_weasy(id)
    except Exception as e:
        wiz.response.status(400, message=str(e))

    resp = flask.Response(pdf_bytes, mimetype='application/pdf')
    resp.headers['Content-Disposition'] = "inline"
    wiz.response.response(resp)

def template_preview_pdf():
    """설정 화면용 원본/기본 양식 PDF 미리보기"""
    id = wiz.request.query("id", True)
    flask = wiz.response._flask
    try:
        pdf_bytes = struct.doc_export.generate_template_pdf(id)
    except Exception as e:
        wiz.response.status(400, message=str(e))

    resp = flask.Response(pdf_bytes, mimetype='application/pdf')
    resp.headers['Content-Disposition'] = "inline"
    wiz.response.response(resp)

def reference_file_preview():
    """설정 화면용 업로드 참고자료 미리보기"""
    id = wiz.request.query("id", True)
    filename = wiz.request.query("filename", True)
    flask = wiz.response._flask
    body = b""
    mimetype = 'text/html; charset=utf-8'

    try:
        instance = struct.doc.get_instance(id)
        if not instance:
            raise Exception("문서를 찾을 수 없습니다.")

        settings = instance.get('settings_json', {}) if isinstance(instance.get('settings_json', {}), dict) else {}
        reference_files = settings.get('reference_files', []) if isinstance(settings.get('reference_files', []), list) else []
        ref = None
        for item in reference_files:
            if isinstance(item, dict) and item.get('filename') == filename:
                ref = item
                break
        if not ref:
            raise Exception("참고자료를 찾을 수 없습니다.")

        fs = wiz.project.fs("data", "uploads", "references")
        filepath = fs.abspath(filename)
        if not os.path.exists(filepath):
            raise Exception("참고자료 파일이 없습니다.")

        ext = (ref.get('ext') or (filename.rsplit('.', 1)[-1] if '.' in filename else '')).lower()
        title = ref.get('original_name') or filename

        if ext == 'pdf':
            with open(filepath, 'rb') as f:
                body = f.read()
            mimetype = 'application/pdf'
        elif ext in ['png', 'jpg', 'jpeg', 'gif', 'webp']:
            mimetype = 'image/jpeg' if ext in ['jpg', 'jpeg'] else f'image/{ext}'
            with open(filepath, 'rb') as f:
                body = f.read()
        elif ext == 'hwp':
            tmpdir = tempfile.mkdtemp()
            try:
                pdf_path = struct.doc_export._render_hwp_template_to_pdf_file(filepath, tmpdir)
                with open(pdf_path, 'rb') as f:
                    body = f.read()
                mimetype = 'application/pdf'
            except Exception:
                text = ref.get('text_excerpt') or _extract_reference_text(filepath, ext)
                body = _reference_text_preview_html(title, text, "HWP 양식 렌더링에 실패해 추출 텍스트로 표시합니다.")
                mimetype = 'text/html; charset=utf-8'
            finally:
                shutil.rmtree(tmpdir, ignore_errors=True)
        elif ext in ['doc', 'docx']:
            tmpdir = tempfile.mkdtemp()
            try:
                pdf_path = struct.doc_export._convert_office_to_pdf_file(filepath, tmpdir)
                with open(pdf_path, 'rb') as f:
                    body = f.read()
                mimetype = 'application/pdf'
            except Exception:
                text = ref.get('text_excerpt') or _extract_reference_text(filepath, ext)
                body = _reference_text_preview_html(title, text, "원본 레이아웃 변환에 실패해 추출 텍스트로 표시합니다.")
                mimetype = 'text/html; charset=utf-8'
            finally:
                shutil.rmtree(tmpdir, ignore_errors=True)
        else:
            text = ref.get('text_excerpt') or _extract_reference_text(filepath, ext)
            body = _reference_text_preview_html(title, text)
            mimetype = 'text/html; charset=utf-8'
    except Exception as e:
        wiz.response.status(400, message=str(e))

    resp = flask.Response(body, mimetype=mimetype)
    resp.headers['Content-Disposition'] = "inline"
    wiz.response.response(resp)

def reference_doc_preview():
    """설정 화면용 이전 문서 미리보기"""
    id = wiz.request.query("id", True)
    flask = wiz.response._flask
    user_id = wiz.session.get("id")
    try:
        instance = struct.doc.get_instance(id)
        if not instance:
            raise Exception("문서를 찾을 수 없습니다.")
        if user_id and instance.get('user_id') != user_id:
            raise Exception("접근 권한이 없습니다.")
        pdf_bytes = struct.doc_export.generate_pdf_weasy(id)
    except Exception as e:
        wiz.response.status(400, message=str(e))

    resp = flask.Response(pdf_bytes, mimetype='application/pdf')
    resp.headers['Content-Disposition'] = "inline"
    wiz.response.response(resp)

def preview_html():
    """HTML 미리보기"""
    id = wiz.request.query("id", True)
    flask = wiz.response._flask
    try:
        html_str = struct.doc_export.preview_html(id)
    except Exception as e:
        wiz.response.status(400, message=str(e))

    resp = flask.Response(html_str, mimetype='text/html; charset=utf-8')
    wiz.response.response(resp)

def direct_editor_html():
    """원본 양식 직접 편집 HTML"""
    id = wiz.request.query("id", True)
    flask = wiz.response._flask
    try:
        html_str = struct.doc_export.direct_editor_html(id)
    except Exception as e:
        wiz.response.status(400, message=str(e))

    resp = flask.Response(html_str, mimetype='text/html; charset=utf-8')
    resp.headers['Cache-Control'] = 'no-store'
    wiz.response.response(resp)

def download_hwp():
    """HWPX 다운로드."""
    id = wiz.request.query("id", True)
    flask = wiz.response._flask
    try:
        instance = struct.doc.get_instance(id)
        title = instance.get('title', '문서') if instance else '문서'
        safe_title = re.sub(r'[\\/:*?"<>|]+', '_', str(title or '문서')).strip() or '문서'
        hwpx_bytes = struct.doc_export.generate_hwpx(id)
    except Exception as e:
        wiz.response.status(400, message=str(e))

    filename = f"{safe_title}.hwpx"
    resp = flask.Response(hwpx_bytes, mimetype='application/hwp+zip')
    resp.headers['Content-Disposition'] = f"attachment; filename*=UTF-8''{url_quote(filename)}"
    wiz.response.response(resp)

def upload_image():
    """이미지 업로드"""
    instance_id = wiz.request.query("instance_id", True)
    file = wiz.request.file("file")
    if not file:
        wiz.response.status(400, message="파일이 없습니다.")

    try:
        result = struct.graph_gen.upload_image(file, instance_id)
    except Exception as e:
        wiz.response.status(400, message=str(e))
    wiz.response.status(200, result)

def list_images():
    """업로드된 이미지 목록"""
    instance_id = wiz.request.query("instance_id", True)
    try:
        images = struct.graph_gen.list_images(instance_id)
    except Exception as e:
        wiz.response.status(400, message=str(e))
    wiz.response.status(200, images)

def get_image():
    """이미지 바이너리 반환"""
    instance_id = wiz.request.query("instance_id", True)
    filename = wiz.request.query("filename", True)
    flask = wiz.response._flask

    img_bytes, mimetype = struct.graph_gen.get_image_bytes(instance_id, filename)
    if not img_bytes:
        wiz.response.status(404, message="이미지를 찾을 수 없습니다.")

    resp = flask.Response(img_bytes, mimetype=mimetype)
    resp.headers['Cache-Control'] = 'public, max-age=3600'
    wiz.response.response(resp)

def delete_image():
    """이미지 삭제"""
    instance_id = wiz.request.query("instance_id", True)
    filename = wiz.request.query("filename", True)

    try:
        struct.graph_gen.delete_image(instance_id, filename)
    except Exception as e:
        wiz.response.status(400, message=str(e))
    wiz.response.status(200)

def save_image_placement():
    """이미지를 문서 특정 위치에 배치"""
    instance_id = wiz.request.query("instance_id", True)
    filename = wiz.request.query("filename", True)
    position = wiz.request.query("position", True)
    insert_mode = wiz.request.query("insert_mode", "auto")
    page = wiz.request.query("page", "")
    x_pct = wiz.request.query("x_pct", "")
    y_pct = wiz.request.query("y_pct", "")
    w_pct = wiz.request.query("w_pct", "")
    h_pct = wiz.request.query("h_pct", "")
    try:
        placements = struct.graph_gen.save_placement(
            instance_id, filename, position, insert_mode=insert_mode,
            page=page, x_pct=x_pct, y_pct=y_pct, w_pct=w_pct, h_pct=h_pct
        )
        try:
            inst = struct.doc.get_instance(instance_id)
            if inst:
                cj = inst.get('content_json', {}) if isinstance(inst.get('content_json', {}), dict) else {}
                if cj.get('generated_output_file'):
                    cj['generated_output_file'] = ''
                    struct.doc.update_instance(instance_id, content_json=cj)
        except Exception:
            pass
    except Exception as e:
        wiz.response.status(400, message=str(e))
    wiz.response.status(200, placements=placements)

def remove_image_placement():
    """이미지 배치 해제"""
    instance_id = wiz.request.query("instance_id", True)
    filename = wiz.request.query("filename", True)
    position = wiz.request.query("position", "")
    try:
        placements = struct.graph_gen.remove_placement(instance_id, filename, position or None)
        try:
            inst = struct.doc.get_instance(instance_id)
            if inst:
                cj = inst.get('content_json', {}) if isinstance(inst.get('content_json', {}), dict) else {}
                if cj.get('generated_output_file'):
                    cj['generated_output_file'] = ''
                    struct.doc.update_instance(instance_id, content_json=cj)
        except Exception:
            pass
    except Exception as e:
        wiz.response.status(400, message=str(e))
    wiz.response.status(200, placements)

def get_image_positions():
    """현재 배치 정보 및 사용 가능한 위치 목록 반환"""
    instance_id = wiz.request.query("instance_id", True)
    try:
        placements = struct.graph_gen.get_placements(instance_id)
        placement_details = struct.graph_gen.get_placements(instance_id, detailed=True)
        # HWP 템플릿에서 이미지 셀 위치 목록 추출
        positions = struct.doc_export.get_image_positions(instance_id)
    except Exception as e:
        wiz.response.status(400, message=str(e))
    wiz.response.status(200, placements=placements, placement_details=placement_details, positions=positions)

def generate_chart():
    """AI로 그래프 생성"""
    instance_id = wiz.request.query("instance_id", True)
    prompt = wiz.request.query("prompt", "")
    user_id = wiz.session.get("id")
    file = wiz.request.file("file")

    try:
        if file:
            result = struct.graph_gen.generate_chart_from_csv_upload(file, instance_id, prompt, user_id)
        else:
            if not prompt:
                wiz.response.status(400, message="그래프 설명 또는 CSV 파일이 필요합니다.")
            result = struct.graph_gen.ai_generate_chart(instance_id, prompt, user_id)
    except Exception as e:
        wiz.response.status(400, message=str(e))
    wiz.response.status(200, result)

# =============================================================================
# doc_export Sub-Struct — PDF/DOCX/HWP 문서 내보내기
# =============================================================================
import io
import datetime
import os
import re
import base64
import subprocess
import tempfile
import shutil
import json
import html
import mimetypes
import zipfile
from urllib.parse import unquote

class DocExport:
    def __init__(self, struct):
        self.struct = struct

    # ─── 섹션 content에서 <라벨> 값 형식 파싱 ─────────────────
    def _parse_section_fields(self, sections):
        """섹션 content에서 <라벨> 값 쌍을 추출한다.
        AI는 HWP 양식 필드를 <필드명> 값 형태로 생성한다.
        """
        values = {}
        for sec in sections:
            content = sec.get('content', '') or ''
            lines = content.split('\n')
            last_label = None
            for line in lines:
                line_stripped = line.strip()
                if not line_stripped:
                    continue
                # 1) "라벨 : 값" 또는 "라벨 ： 값" 패턴
                m = re.match(r'^<?([^<>\n]{1,80}?)>?\s*[:：]\s*(.*)$', line_stripped)
                if m:
                    label = m.group(1).strip()
                    value = m.group(2).strip()
                    if label:
                        values[label] = value
                        last_label = label
                    continue

                # 2) "<라벨><값>" 패턴
                m = re.match(r'^<([^>]{1,80})>\s*<([^>]*)>\s*$', line_stripped)
                if m:
                    label = m.group(1).strip()
                    value = m.group(2).strip()
                    if label:
                        values[label] = value
                        last_label = label
                    continue

                # 3) "<라벨> 값" 패턴 (단, 단독 제목 라인은 제외)
                m = re.match(r'^<([^>]{1,80})>\s+(.+)$', line_stripped)
                if m:
                    label = m.group(1).strip()
                    value = m.group(2).strip()
                    if label:
                        values[label] = value
                        last_label = label
                    continue

                if last_label and values.get(last_label, '') != '':
                    # 이전 라벨의 연속 내용 (멀티라인 값)
                    values[last_label] += '\n' + line_stripped
                elif last_label and values.get(last_label, '') == '':
                    # 빈 값이었던 라벨의 첫 번째 값 줄
                    values[last_label] = line_stripped
        return values

    # ─── 값 수집: generated_fields + 섹션 파싱 ────────────────
    def _collect_all_values(self, instance_id, instance):
        """인스턴스에서 사용 가능한 모든 필드 값을 수집한다."""
        content_json = instance.get('content_json', {}) if instance and isinstance(instance.get('content_json'), dict) else {}
        field_values = content_json.get('generated_fields', {}) or {}
        try:
            field_values = self.struct.ai_agent.sanitize_generated_fields(field_values)
        except Exception:
            pass

        sections_data = self.struct.doc.list_sections(instance_id)
        # 섹션 content에서 <라벨> 값 파싱 (주요 데이터 소스)
        parsed_values = self._parse_section_fields(sections_data)

        # 모든 값 합치기. 섹션 파싱값은 사용자가 직접 고친 내용일 수 있지만,
        # 양식의 예시/플레이스홀더가 생성값을 덮어쓰면 표가 다시 망가진다.
        all_values = {}
        all_values.update(field_values)
        for key, value in parsed_values.items():
            existing = all_values.get(key, '')
            if existing and self._is_hwp_placeholder_text(value):
                continue
            if existing and not self._is_hwp_placeholder_text(existing):
                continue
            all_values[key] = value
        return all_values

    def _resolve_template_info(self, instance, content_json=None):
        """인스턴스/템플릿에서 실제 원본 양식 정보를 복원한다."""
        if content_json is None:
            content_json = instance.get('content_json', {}) if instance and isinstance(instance.get('content_json'), dict) else {}
        file_type = content_json.get('file_type', '')
        template_file_path = content_json.get('template_file_path', '') or content_json.get('uploaded_file', '')
        template_id = content_json.get('template_id', '') or (instance.get('template_id', '') if instance else '')

        if template_id:
            try:
                tpl = self.struct.doc.get_template(template_id)
                if tpl:
                    # 인스턴스에 업로드 파일이 남아 있지 않으면 템플릿 원본으로 복원한다.
                    if not template_file_path:
                        template_file_path = tpl.get('file_path', '')
                    # 인스턴스 타입이 비어 있거나 PDF 변환본으로 잘못 저장된 경우 템플릿 원본 타입을 우선한다.
                    tpl_type = tpl.get('file_type', '')
                    if not file_type or (file_type == 'pdf' and tpl_type in ('hwp', 'doc', 'docx')):
                        file_type = tpl_type
                        template_file_path = tpl.get('file_path', template_file_path)
            except Exception:
                pass

        return file_type, template_file_path, template_id

    def _template_abspath(self, template_file_path, template_id):
        tpl_fs = wiz.project.fs("data", "uploads", "templates") if template_id else wiz.project.fs("data", "uploads", "instances")
        return tpl_fs.abspath(template_file_path)

    def _source_fs(self, template_id):
        return wiz.project.fs("data", "uploads", "templates") if template_id else wiz.project.fs("data", "uploads", "instances")

    def _resolve_editable_docx_path(self, instance, content_json=None, create_if_missing=True):
        """문서의 내부 편집 기준 DOCX 절대경로를 찾는다."""
        if content_json is None:
            content_json = instance.get('content_json', {}) if instance and isinstance(instance.get('content_json'), dict) else {}
        raw_file_type = content_json.get('file_type', '')
        raw_template_file_path = content_json.get('template_file_path', '') or content_json.get('uploaded_file', '')
        if raw_file_type == 'pdf' and raw_template_file_path:
            return ''
        file_type, template_file_path, template_id = self._resolve_template_info(instance, content_json)
        fields_schema = content_json.get('fields_schema', {}) if isinstance(content_json.get('fields_schema', {}), dict) else {}
        fs = self._source_fs(template_id)

        candidates = [
            content_json.get('editable_docx_path', ''),
            fields_schema.get('editable_docx_path', ''),
            fields_schema.get('converted_docx_path', ''),
        ]
        if file_type == 'docx' and template_file_path:
            candidates.append(template_file_path)

        if template_id:
            try:
                tpl = self.struct.doc.get_template(template_id)
                tpl_schema = tpl.get('fields_schema', {}) if tpl and isinstance(tpl.get('fields_schema', {}), dict) else {}
                candidates.extend([
                    tpl_schema.get('editable_docx_path', ''),
                    tpl_schema.get('converted_docx_path', ''),
                ])
                if tpl and tpl.get('file_type') == 'docx':
                    candidates.append(tpl.get('file_path', ''))
            except Exception:
                pass

        for rel_path in candidates:
            if not rel_path:
                continue
            candidate = rel_path if os.path.isabs(rel_path) else fs.abspath(rel_path)
            if os.path.exists(candidate) and candidate.lower().endswith('.docx'):
                return candidate

        if create_if_missing and template_file_path and file_type in ('hwp', 'doc'):
            original = fs.abspath(template_file_path)
            if os.path.exists(original):
                converted = os.path.splitext(original)[0] + '_converted.docx'
                if os.path.exists(converted):
                    return converted
                return self.struct.file_parser._convert_to_docx(original)

        return ''

    def _pdf_as_html(self, pdf_bytes):
        encoded = base64.b64encode(pdf_bytes).decode('ascii')
        return (
            '<!DOCTYPE html><html><head><meta charset="utf-8">'
            '<style>html,body{margin:0;width:100%;height:100%;background:#f5f5f5;}'
            'iframe{width:100%;height:100%;border:0;display:block;}</style>'
            '</head><body>'
            f'<iframe src="data:application/pdf;base64,{encoded}"></iframe>'
            '</body></html>'
        )

    def _register_pdf_korean_font(self):
        return self._register_pdf_font('gothic', bold=False)

    def _register_pdf_font(self, font_family='gothic', bold=False):
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        family = str(font_family or 'gothic').lower()
        font_map = {
            'gothic': [
                ('NanumGothicBold' if bold else 'NanumGothic', '/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf' if bold else '/usr/share/fonts/truetype/nanum/NanumGothic.ttf'),
                ('NotoSansCJK', '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'),
            ],
            'myeongjo': [
                ('NanumMyeongjoBold' if bold else 'NanumMyeongjo', '/usr/share/fonts/truetype/nanum/NanumMyeongjoBold.ttf' if bold else '/usr/share/fonts/truetype/nanum/NanumMyeongjo.ttf'),
                ('NotoSerifCJK', '/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc'),
            ],
            'mono': [
                ('NanumGothicCoding', '/usr/share/fonts/truetype/nanum/NanumGothicCoding.ttf'),
                ('NanumGothicBold' if bold else 'NanumGothic', '/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf' if bold else '/usr/share/fonts/truetype/nanum/NanumGothic.ttf'),
            ],
            'batang': [
                ('NanumMyeongjoBold' if bold else 'NanumMyeongjo', '/usr/share/fonts/truetype/nanum/NanumMyeongjoBold.ttf' if bold else '/usr/share/fonts/truetype/nanum/NanumMyeongjo.ttf'),
            ],
        }
        font_candidates = font_map.get(family, font_map['gothic']) + [
            ('SpoqaHanSansNeo', '/opt/conda/envs/app/lib/python3.14/site-packages/season/data/sample/src/portal/season/assets/font/spoqa/SpoqaHanSansNeo-Regular.ttf'),
        ]
        for name, path in font_candidates:
            if os.path.exists(path):
                try:
                    pdfmetrics.getFont(name)
                except Exception:
                    pdfmetrics.registerFont(TTFont(name, path))
                return name
        return 'Helvetica'

    def _normalize_field_style(self, style):
        if not isinstance(style, dict):
            style = {}

        def _num(key, default, min_value, max_value):
            try:
                value = float(style.get(key, default))
            except Exception:
                value = float(default)
            return max(min_value, min(max_value, value))

        family = str(style.get('font_family', 'gothic') or 'gothic').lower()
        if family not in ['gothic', 'myeongjo', 'batang', 'mono']:
            family = 'gothic'
        align = str(style.get('align', 'left') or 'left').lower()
        if align not in ['left', 'center', 'right']:
            align = 'left'
        color = str(style.get('color', '#080808') or '#080808').strip()
        if not re.match(r'^#[0-9a-fA-F]{6}$', color):
            color = '#080808'
        return {
            'font_family': family,
            'font_size': _num('font_size', 9, 5, 28),
            'bold': bool(style.get('bold', False)),
            'align': align,
            'color': color,
        }

    def _field_styles(self, instance):
        content_json = instance.get('content_json', {}) if instance and isinstance(instance.get('content_json'), dict) else {}
        raw = content_json.get('field_styles', {}) or {}
        if not isinstance(raw, dict):
            return {}
        return {str(label): self._normalize_field_style(style) for label, style in raw.items() if isinstance(style, dict)}

    def _direct_field_layouts(self, instance):
        content_json = instance.get('content_json', {}) if instance and isinstance(instance.get('content_json'), dict) else {}
        raw = content_json.get('field_layouts', {}) or {}
        if not isinstance(raw, dict):
            return {}

        result = {}
        for label, item in raw.items():
            if not isinstance(item, dict):
                continue
            try:
                page = int(item.get('page') or 1)
                left = float(item.get('left') or 0)
                top = float(item.get('top') or 0)
                width = float(item.get('width') or 0)
                height = float(item.get('height') or 0)
            except Exception:
                continue
            result[str(label)] = {
                'page': max(1, page),
                'left': max(0, min(100, left)),
                'top': max(0, min(100, top)),
                'width': max(1, min(100, width)),
                'height': max(1, min(100, height)),
            }
        return result

    def _direct_table_spacings(self, instance):
        content_json = instance.get('content_json', {}) if instance and isinstance(instance.get('content_json'), dict) else {}
        raw = content_json.get('table_spacings', {}) or {}
        if not isinstance(raw, dict):
            return {}

        result = {}
        for key, item in raw.items():
            if not isinstance(item, dict):
                continue
            try:
                page = int(item.get('page') or 1)
                after_table = int(item.get('after_table') or 0)
                before_table = int(item.get('before_table') or 0)
                docx_before_table = int(item.get('docx_before_table') or 0)
                extra_pct = float(item.get('extra_pct') or 0)
                extra_pt = float(item.get('extra_pt') or 0)
            except Exception:
                continue
            if before_table < 1:
                continue
            result[str(key)] = {
                'page': max(1, page),
                'before_table': before_table,
                'after_table': max(0, after_table),
                'docx_before_table': max(0, docx_before_table),
                'extra_pct': max(0, min(30, extra_pct)),
                'extra_pt': max(0, min(160, extra_pt)),
                'page_break': bool(item.get('page_break', False)),
            }
        return result

    def _has_docx_table_layout_controls(self, content_json):
        raw = content_json.get('table_spacings', {}) if isinstance(content_json, dict) else {}
        if not isinstance(raw, dict):
            return False
        for item in raw.values():
            if not isinstance(item, dict):
                continue
            try:
                before_table = int(item.get('before_table') or 0)
                extra_pt = float(item.get('extra_pt') or 0)
                extra_pct = float(item.get('extra_pct') or 0)
            except Exception:
                continue
            if before_table >= 1 and (extra_pt > 0 or extra_pct > 0 or bool(item.get('page_break', False))):
                return True
        return False

    def _needs_report_docx_layout(self, content_json):
        if not isinstance(content_json, dict):
            return False
        fields_schema = content_json.get('fields_schema', {})
        if not isinstance(fields_schema, dict):
            return False
        haystack = '\n'.join([
            str(fields_schema.get('raw_text', '') or ''),
            str(fields_schema.get('tables', '') or '')[:5000],
        ])
        compact = re.sub(r'\s+', '', haystack)
        return '결론' in compact and ('활동참여내역' in compact or '튜터링진행과정' in compact or '진행과정' in compact)

    def _conclusion_table_index(self, instance):
        content_json = instance.get('content_json', {}) if instance and isinstance(instance.get('content_json'), dict) else {}
        fields_schema = content_json.get('fields_schema', {}) if isinstance(content_json.get('fields_schema'), dict) else {}
        tables = fields_schema.get('tables', []) if isinstance(fields_schema.get('tables', []), list) else []
        for idx, table in enumerate(tables, start=1):
            if not isinstance(table, list) or not table:
                continue
            first_row = table[0] if isinstance(table[0], list) else []
            first_text = str(first_row[0] if first_row else '').strip()
            if '결론' in re.sub(r'\s+', '', first_text):
                return idx
        return 0

    def _conclusion_value(self, all_values):
        for label in ['4. 결론', '결론', '종합평가', '소감', '성과']:
            value = self._find_value_for_label(label, all_values or {})
            if str(value or '').strip():
                return str(value).strip()
        return ''

    def _should_synthesize_conclusion_table(self, pdf, all_values):
        if not self._conclusion_value(all_values or {}):
            return False
        try:
            if len(pdf.pages) < 2:
                return False
            last_boxes = self._pdf_visible_table_boxes(pdf.pages[-1])
            return not bool(last_boxes)
        except Exception:
            return False

    def _synthetic_conclusion_geometry(self):
        """HWP 렌더링이 결론 표의 제목/본문을 서로 다른 페이지로 쪼갠 경우 사용할 보정 좌표."""
        return {
            'old_title': {'left': 9.55, 'top': 69.75, 'width': 81.2, 'height': 5.0},
            'gap': {'left': 9.8, 'top': 4.55, 'width': 80.5, 'height': 1.0},
            'title': {'left': 9.72, 'top': 6.05, 'width': 80.45, 'height': 4.05},
            'body': {'left': 9.72, 'top': 10.1, 'width': 80.45, 'height': 26.5},
            'field': {'left': 10.45, 'top': 11.25, 'width': 78.95, 'height': 24.25},
        }

    def _synthetic_conclusion_field_rect(self, saved_layout=None, page_number=1):
        geometry = self._synthetic_conclusion_geometry()
        field = dict(geometry['field'])
        body = geometry['body']

        if not isinstance(saved_layout, dict):
            return field

        try:
            layout_page = int(saved_layout.get('page') or page_number)
        except Exception:
            layout_page = page_number
        if layout_page != int(page_number or 1):
            return field

        try:
            candidate = {
                'left': float(saved_layout.get('left', field['left'])),
                'top': float(saved_layout.get('top', field['top'])),
                'width': float(saved_layout.get('width', field['width'])),
                'height': float(saved_layout.get('height', field['height'])),
            }
        except Exception:
            return field

        margin_x = 0.7
        margin_y = 0.75
        left_min = body['left'] + margin_x
        top_min = body['top'] + margin_y
        right_max = body['left'] + body['width'] - margin_x
        bottom_max = body['top'] + body['height'] - margin_y

        left = max(left_min, min(candidate['left'], right_max - 1))
        top = max(top_min, min(candidate['top'], bottom_max - 1))
        width = max(1, min(candidate['width'], right_max - left))
        height = max(1, min(candidate['height'], bottom_max - top))

        if height < 4 and bottom_max - top >= 4:
            height = min(field['height'], bottom_max - top)
        return {'left': left, 'top': top, 'width': width, 'height': height}

    def _pdf_pct_rect(self, page_width, page_height, rect):
        x = page_width * float(rect.get('left', 0)) / 100
        w = page_width * float(rect.get('width', 0)) / 100
        h = page_height * float(rect.get('height', 0)) / 100
        top = page_height * float(rect.get('top', 0)) / 100
        y = page_height - top - h
        return x, y, w, h

    def _direct_overlays(self, instance):
        content_json = instance.get('content_json', {}) if instance and isinstance(instance.get('content_json'), dict) else {}
        raw = content_json.get('direct_overlays', []) or []
        if not isinstance(raw, list):
            return []

        result = []
        for idx, item in enumerate(raw):
            if isinstance(item, dict) and str(item.get('type', '')).lower() == 'whiteout':
                continue
            normalized = self._normalize_direct_overlay(item, idx)
            if normalized:
                result.append(normalized)
        return result

    def _normalize_direct_overlay(self, item, idx=0):
        if not isinstance(item, dict):
            return None

        kind = str(item.get('type', 'text') or 'text').lower()
        if kind != 'text':
            kind = 'text'

        def _pct(key, default, min_value, max_value):
            try:
                value = float(item.get(key, default))
            except Exception:
                value = float(default)
            return round(max(min_value, min(max_value, value)), 4)

        try:
            page = int(float(item.get('page') or 1))
        except Exception:
            page = 1
        page = max(1, min(999, page))

        return {
            'id': str(item.get('id') or f'overlay-{idx + 1}'),
            'type': kind,
            'page': page,
            'left': _pct('left', 8, 0, 98),
            'top': _pct('top', 8, 0, 98),
            'width': _pct('width', 28, 1, 100),
            'height': _pct('height', 8, 1, 100),
            'text': str(item.get('text') or ''),
            'style': self._normalize_field_style(item.get('style', {})),
            'border': bool(item.get('border', False)),
        }

    def _find_style_for_label(self, label, field_styles):
        if not label or not field_styles:
            return self._normalize_field_style({})

        def normalize(text):
            return re.sub(r'[\s\.\:：·\-\_\(\)\（\）]', '', str(text or ''))

        if label in field_styles:
            return self._normalize_field_style(field_styles[label])
        clean_label = normalize(label)
        for key, style in field_styles.items():
            if normalize(key) == clean_label:
                return self._normalize_field_style(style)
        for key, style in field_styles.items():
            clean_key = normalize(key)
            if clean_key and (clean_label.startswith(clean_key) or clean_key.startswith(clean_label)):
                return self._normalize_field_style(style)
        return self._normalize_field_style({})

    def _hex_color(self, color):
        from reportlab.lib.colors import HexColor, black
        try:
            return HexColor(color)
        except Exception:
            return black

    def _wrap_pdf_text(self, text, max_width, canvas, font_name, font_size):
        words = re.split(r'(\s+)', str(text or '').strip())
        lines = []
        current = ''
        for token in words:
            trial = current + token
            if canvas.stringWidth(trial, font_name, font_size) <= max_width:
                current = trial
                continue
            if current.strip():
                lines.append(current.strip())
            current = token.strip()
            # 공백 없는 긴 한국어 문장 처리
            while current and canvas.stringWidth(current, font_name, font_size) > max_width:
                cut = len(current)
                while cut > 1 and canvas.stringWidth(current[:cut], font_name, font_size) > max_width:
                    cut -= 1
                lines.append(current[:cut])
                current = current[cut:]
        if current.strip():
            lines.append(current.strip())
        return lines

    def _office_converter_path(self):
        return shutil.which('libreoffice') or shutil.which('soffice')

    def _convert_office_to_pdf_file(self, input_path, output_dir):
        converter = self._office_converter_path()
        if not converter:
            raise Exception("LibreOffice가 설치되어 있지 않아 DOCX/PPT 계열 양식을 PDF로 렌더링할 수 없습니다.")

        result = subprocess.run(
            [
                converter, '--headless', '--nologo', '--nofirststartwizard',
                '--norestore', '--convert-to', 'pdf', '--outdir', output_dir, input_path
            ],
            capture_output=True, text=True, timeout=180
        )
        if result.returncode != 0:
            raise Exception(f"LibreOffice PDF 변환 실패: {(result.stderr or result.stdout)[:400]}")

        basename = os.path.splitext(os.path.basename(input_path))[0]
        output_path = os.path.join(output_dir, f"{basename}.pdf")
        if not os.path.exists(output_path):
            for name in os.listdir(output_dir):
                if name.lower().endswith('.pdf'):
                    output_path = os.path.join(output_dir, name)
                    break

        if not os.path.exists(output_path):
            raise Exception("변환된 PDF 파일이 생성되지 않았습니다.")
        return output_path

    def _render_hwp_template_to_pdf_file(self, hwp_path, output_dir):
        hwp5html = shutil.which('hwp5html')
        if not hwp5html:
            raise Exception("hwp5html이 설치되어 있지 않아 HWP 양식을 PDF로 렌더링할 수 없습니다.")

        html_dir = os.path.join(output_dir, 'hwp_html')
        result = subprocess.run(
            [hwp5html, '--output', html_dir, hwp_path],
            capture_output=True, text=True, timeout=180
        )
        if result.returncode != 0:
            raise Exception(f"HWP HTML 변환 실패: {(result.stderr or result.stdout)[:400]}")

        xhtml_path = os.path.join(html_dir, 'index.xhtml')
        if not os.path.exists(xhtml_path):
            raise Exception("HWP HTML 변환 결과를 찾을 수 없습니다.")

        css_path = os.path.join(html_dir, 'styles.css')
        with open(xhtml_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
        css_content = ''
        if os.path.exists(css_path):
            with open(css_path, 'r', encoding='utf-8') as f:
                css_content = f.read()
        if css_content:
            html_content = re.sub(
                r'<link\s+rel="stylesheet"\s+href="styles\.css"\s+type="text/css"\s*/?>',
                f'<style type="text/css">{css_content}</style>',
                html_content
            )
        html_content = html_content.replace('background-color: #eee;', 'background-color: #fff;')
        html_content = html_content.replace(
            '</style>',
            '''
@page { size: A4; margin: 18mm 0 18mm 0; }
body { margin: 0; padding: 0; }
.Paper { border: none !important; box-shadow: none !important; margin: 0 auto !important; }
''' + '</style>',
            1
        )

        from weasyprint import HTML as WeasyHTML
        output_path = os.path.join(output_dir, 'template.pdf')
        WeasyHTML(string=html_content, base_url=html_dir).write_pdf(output_path)
        if not os.path.exists(output_path):
            raise Exception("HWP PDF 렌더링 결과를 찾을 수 없습니다.")
        return output_path

    def _render_template_to_pdf_path(self, file_type, template_file_path, template_id, tmpdir):
        actual_path = self._template_abspath(template_file_path, template_id)
        if not os.path.exists(actual_path):
            raise Exception(f"원본 양식 파일을 찾을 수 없습니다: {template_file_path}")

        file_type = (file_type or '').lower()
        if file_type == 'pdf':
            return actual_path
        if file_type in ('doc', 'docx'):
            return self._convert_office_to_pdf_file(actual_path, tmpdir)
        if file_type == 'hwp':
            return self._render_hwp_template_to_pdf_file(actual_path, tmpdir)
        raise Exception(f"지원하지 않는 원본 양식 형식입니다: {file_type or 'unknown'}")

    def _generate_pdf_overlay_from_template(self, instance_id, instance, file_type, template_file_path, template_id):
        tmpdir = tempfile.mkdtemp()
        try:
            pdf_path = self._render_template_to_pdf_path(file_type, template_file_path, template_id, tmpdir)
            return self._generate_pdf_overlay_from_path(instance_id, instance, pdf_path)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def generate_template_pdf(self, instance_id):
        """작성 결과가 아닌 원본/기본 양식만 PDF로 렌더링한다."""
        instance = self.struct.doc.get_instance(instance_id)
        if not instance:
            raise Exception("문서를 찾을 수 없습니다.")

        content_json = instance.get('content_json', {}) if isinstance(instance.get('content_json'), dict) else {}
        file_type, template_file_path, template_id = self._resolve_template_info(instance, content_json)
        tmpdir = tempfile.mkdtemp()
        errors = []
        try:
            if file_type in ('pdf', 'doc', 'docx', 'hwp') and template_file_path:
                try:
                    pdf_path = self._render_template_to_pdf_path(file_type, template_file_path, template_id, tmpdir)
                    with open(pdf_path, 'rb') as f:
                        return f.read()
                except Exception as e:
                    errors.append(str(e))

            editable_docx_path = self._resolve_editable_docx_path(instance, content_json, create_if_missing=False)
            if editable_docx_path and os.path.exists(editable_docx_path):
                try:
                    pdf_path = self._convert_office_to_pdf_file(editable_docx_path, tmpdir)
                    with open(pdf_path, 'rb') as f:
                        return f.read()
                except Exception as e:
                    errors.append(str(e))

            reason = errors[-1] if errors else "원본 양식 파일이 없습니다."
            raise Exception(reason)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def _pdf_image_reader_from_data_uri(self, data_uri):
        from reportlab.lib.utils import ImageReader
        if not data_uri or ',' not in data_uri:
            return None
        try:
            payload = data_uri.split(',', 1)[1]
            return ImageReader(io.BytesIO(base64.b64decode(payload)))
        except Exception:
            return None

    def _draw_pdf_image_stack(self, canvas_obj, images, x0, top, x1, bottom, page_height, clear_background=True,
                              reserved_top=0):
        if not images:
            return False

        from reportlab.lib.colors import white

        rect_x = x0 + 1
        rect_y = page_height - bottom + 1
        rect_w = max(1, x1 - x0 - 2)
        rect_h = max(1, bottom - top - 2)
        pad_x = 5
        pad_y = 5
        max_w = max(8, rect_w - pad_x * 2)
        max_h_total = max(8, rect_h - pad_y * 2 - max(0, reserved_top))
        slot_h = max(8, max_h_total / max(1, len(images)))

        if clear_background:
            canvas_obj.setFillColor(white)
            canvas_obj.rect(rect_x, rect_y, rect_w, rect_h, stroke=0, fill=1)

        drew = False
        for idx, item in enumerate(images):
            reader = self._pdf_image_reader_from_data_uri(item.get('data_uri', ''))
            if not reader:
                continue
            try:
                img_w, img_h = reader.getSize()
            except Exception:
                continue
            if not img_w or not img_h:
                continue

            scale = min(max_w / img_w, slot_h / img_h)
            draw_w = img_w * scale
            draw_h = img_h * scale
            draw_x = x0 + pad_x + (max_w - draw_w) / 2
            slot_bottom = page_height - bottom + pad_y + (len(images) - idx - 1) * slot_h
            draw_y = slot_bottom + (slot_h - draw_h) / 2
            canvas_obj.drawImage(reader, draw_x, draw_y, width=draw_w, height=draw_h, preserveAspectRatio=True, mask='auto')
            drew = True
        return drew

    def _draw_pdf_table_values(self, plumber_page, canvas_obj, page_height, all_values, font_name,
                               image_placements=None, instance_id=None, field_styles=None,
                               field_layouts=None, page_number=1, page_width=None,
                               sequence_state=None):
        """PDF 표의 라벨 셀을 읽고 바로 오른쪽 값 셀에 텍스트/이미지를 배치한다."""
        from reportlab.lib.colors import white

        wrote = False
        field_layouts = field_layouts or {}
        include_all_cells = bool(field_layouts) or any(
            re.match(r'^표\d+\s+\d+행\s+\d+열', str(key or ''))
            for key in (all_values or {}).keys()
        )
        if page_width is None:
            try:
                page_width = float(plumber_page.width)
            except Exception:
                page_width = 0

        items = self._pdf_table_fields(
            plumber_page, all_values, field_styles or {},
            include_all_cells=include_all_cells, sequence_state=sequence_state
        )
        page_table_start = 0
        if sequence_state is not None:
            try:
                page_table_start = int(sequence_state.get('_pdf_global_table_index') or 0)
            except Exception:
                page_table_start = 0
        max_local_table = 0

        for item in items:
            label_text = item.get('label', '')
            try:
                local_table_index = int(item.get('table_index') or 0)
                row_index = int(item.get('row_index') or 0)
                col_index = int(item.get('col_index') or 0)
            except Exception:
                local_table_index, row_index, col_index = 0, 0, 0
            max_local_table = max(max_local_table, local_table_index)
            global_table_index = page_table_start + local_table_index if local_table_index > 0 else 0
            global_label = ''
            if not item.get('semantic') and global_table_index > 0:
                source_text = str(item.get('source_text') or '').strip()
                base_label = f"표{global_table_index} {row_index + 1}행 {col_index + 1}열"
                global_label = f"{base_label} ({source_text})" if source_text else base_label
            label_candidates = [candidate for candidate in [global_label, label_text] if candidate]
            has_saved_value = any(candidate in (all_values or {}) for candidate in label_candidates)
            has_saved_layout = any(candidate in field_layouts for candidate in label_candidates)
            if include_all_cells and not item.get('semantic') and not has_saved_value and not has_saved_layout:
                continue
            x0, top, x1, bottom = item.get('rect')
            layout = next((field_layouts.get(candidate) for candidate in label_candidates if field_layouts.get(candidate)), None)
            if layout and int(layout.get('page') or 1) == int(page_number or 1) and page_width:
                x0 = page_width * float(layout.get('left', 0)) / 100
                top = page_height * float(layout.get('top', 0)) / 100
                x1 = x0 + page_width * float(layout.get('width', 1)) / 100
                bottom = top + page_height * float(layout.get('height', 1)) / 100
            matched_images = self._find_images_for_label(label_text, image_placements or {}, instance_id) if instance_id else []
            fill_value = ''
            for candidate in label_candidates:
                fill_value = self._find_value_for_label(candidate, all_values)
                if fill_value or candidate in (all_values or {}):
                    break
            if not fill_value:
                if has_saved_value:
                    canvas_obj.setFillColor(white)
                    canvas_obj.rect(
                        x0 + 1,
                        page_height - bottom + 1,
                        max(1, x1 - x0 - 2),
                        max(1, bottom - top - 2),
                        stroke=0,
                        fill=1
                    )
                    wrote = True
                    continue
                if matched_images:
                    if self._draw_pdf_image_stack(canvas_obj, matched_images, x0, top, x1, bottom, page_height):
                        wrote = True
                continue

            style = item.get('style') or self._find_style_for_label(label_text, field_styles or {})
            pad_x = 5
            pad_y = 4
            rect_x = x0 + 1
            rect_y = page_height - bottom + 1
            rect_w = max(1, x1 - x0 - 2)
            rect_h = max(1, bottom - top - 2)

            # 기존 값만 가리고 테두리는 원본 PDF 배경을 그대로 보존한다.
            canvas_obj.setFillColor(white)
            canvas_obj.rect(rect_x, rect_y, rect_w, rect_h, stroke=0, fill=1)

            font_size = float(style.get('font_size') or 9)
            max_text_w = max(8, rect_w - pad_x * 2)
            styled_font = self._register_pdf_font(style.get('font_family', 'gothic'), bold=style.get('bold', False))
            lines = []
            max_lines = 1
            while True:
                leading = font_size + 2.4
                lines = []
                for paragraph in str(fill_value).splitlines() or ['']:
                    wrapped = self._wrap_pdf_text(paragraph, max_text_w, canvas_obj, styled_font, font_size)
                    lines.extend(wrapped or [''])
                max_lines = max(1, int((rect_h - pad_y * 2) // leading))
                if matched_images and rect_h > 80:
                    max_lines = max(1, min(max_lines, int(rect_h * 0.34 // leading)))
                if len(lines) <= max_lines or font_size <= 6:
                    break
                font_size -= 0.5
            lines = lines[:max_lines]

            canvas_obj.setFillColor(self._hex_color(style.get('color', '#080808')))
            canvas_obj.setFont(styled_font, font_size)
            if len(lines) <= 1 and rect_h <= 32:
                text_y = page_height - top - ((rect_h - font_size) / 2) - 2
            else:
                text_y = page_height - top - pad_y - font_size
            for line in lines:
                line_w = canvas_obj.stringWidth(line, styled_font, font_size)
                align = style.get('align', 'left')
                if align == 'center':
                    text_x = x0 + pad_x + max(0, (max_text_w - line_w) / 2)
                elif align == 'right':
                    text_x = x1 - pad_x - line_w
                else:
                    text_x = x0 + pad_x
                canvas_obj.drawString(text_x, text_y, line)
                text_y -= leading
            if matched_images:
                text_used_h = pad_y * 2 + max(1, len(lines)) * leading + 6
                img_top = min(bottom - 10, top + text_used_h)
                self._draw_pdf_image_stack(
                    canvas_obj, matched_images, x0, img_top, x1, bottom, page_height,
                    clear_background=False
                )
            wrote = True
        if sequence_state is not None and max_local_table:
            sequence_state['_pdf_global_table_index'] = page_table_start + max_local_table
        return wrote

    def _draw_direct_overlays(self, canvas_obj, page_number, page_width, page_height, overlays=None):
        """직접 편집기의 자유 텍스트를 PDF 위에 투명하게 그린다."""
        if not overlays:
            return False

        wrote = False
        page_items = []
        for item in overlays:
            if not isinstance(item, dict):
                continue
            try:
                item_page = int(item.get('page') or 1)
            except Exception:
                item_page = 1
            if item_page == page_number:
                page_items.append(item)

        for item in page_items:
            try:
                left = float(item.get('left', 0))
                top = float(item.get('top', 0))
                width = float(item.get('width', 10))
                height = float(item.get('height', 5))
            except Exception:
                continue

            draw_x = page_width * left / 100
            draw_w = max(1, page_width * width / 100)
            draw_h = max(1, page_height * height / 100)
            draw_y = page_height - (page_height * top / 100) - draw_h
            kind = item.get('type', 'text')
            if kind != 'text':
                continue

            if item.get('border'):
                canvas_obj.setStrokeColor(self._hex_color('#080808'))
                canvas_obj.setLineWidth(0.4)
                canvas_obj.rect(draw_x, draw_y, draw_w, draw_h, stroke=1, fill=0)

            text = str(item.get('text') or '').strip()
            if not text:
                wrote = True
                continue

            style = self._normalize_field_style(item.get('style', {}))
            font_size = float(style.get('font_size') or 9)
            leading = font_size + 3
            pad_x = 5
            pad_y = 4
            max_text_w = max(8, draw_w - pad_x * 2)
            styled_font = self._register_pdf_font(style.get('font_family', 'gothic'), bold=style.get('bold', False))
            lines = []
            for paragraph in text.splitlines() or ['']:
                wrapped = self._wrap_pdf_text(paragraph, max_text_w, canvas_obj, styled_font, font_size)
                lines.extend(wrapped or [''])
            max_lines = max(1, int((draw_h - pad_y * 2) // leading))
            lines = lines[:max_lines]

            canvas_obj.setFillColor(self._hex_color(style.get('color', '#080808')))
            canvas_obj.setFont(styled_font, font_size)
            text_y = draw_y + draw_h - pad_y - font_size
            for line in lines:
                line_w = canvas_obj.stringWidth(line, styled_font, font_size)
                align = style.get('align', 'left')
                if align == 'center':
                    text_x = draw_x + pad_x + max(0, (max_text_w - line_w) / 2)
                elif align == 'right':
                    text_x = draw_x + draw_w - pad_x - line_w
                else:
                    text_x = draw_x + pad_x
                canvas_obj.drawString(text_x, text_y, line)
                text_y -= leading
            wrote = True

        return wrote

    def _draw_synthetic_conclusion_field(self, canvas_obj, page_number, total_pages, page_width, page_height,
                                         all_values=None, field_styles=None, field_layouts=None,
                                         synthesize_table=False):
        """원본 HWP 렌더링이 결론 표를 페이지 사이에서 쪼갠 경우 표를 한 페이지에 재구성한다."""
        if not synthesize_table:
            return False
        text = self._conclusion_value(all_values or {})
        if not text:
            return False

        geometry = self._synthetic_conclusion_geometry()
        page_number = int(page_number or 1)
        total_pages = int(total_pages or 1)

        if page_number == total_pages - 1:
            x0, draw_y, rect_w, rect_h = self._pdf_pct_rect(page_width, page_height, geometry['old_title'])
            from reportlab.lib.colors import white
            canvas_obj.saveState()
            canvas_obj.setFillColor(white)
            canvas_obj.rect(x0, draw_y, rect_w, rect_h, stroke=0, fill=1)
            canvas_obj.restoreState()
            return True

        if page_number != total_pages:
            return False

        canvas_obj.saveState()
        from reportlab.lib.colors import white
        title_x, title_y, title_w, title_h = self._pdf_pct_rect(page_width, page_height, geometry['title'])
        body_x, body_y, body_w, body_h = self._pdf_pct_rect(page_width, page_height, geometry['body'])

        canvas_obj.setFillColor(white)
        canvas_obj.rect(body_x, body_y, body_w, body_h, stroke=0, fill=1)
        canvas_obj.setFillColor(self._hex_color('#d7e5f6'))
        canvas_obj.setStrokeColor(self._hex_color('#080808'))
        canvas_obj.setLineWidth(0.9)
        canvas_obj.rect(title_x, title_y, title_w, title_h, stroke=1, fill=1)
        canvas_obj.setFillColor(white)
        canvas_obj.rect(body_x, body_y, body_w, body_h, stroke=0, fill=1)
        canvas_obj.setStrokeColor(self._hex_color('#080808'))
        canvas_obj.rect(body_x, body_y, body_w, body_h, stroke=1, fill=0)

        title_font = self._register_pdf_font('myeongjo', bold=False)
        title_size = 11
        canvas_obj.setFillColor(self._hex_color('#080808'))
        canvas_obj.setFont(title_font, title_size)
        canvas_obj.drawString(title_x + 8, title_y + (title_h - title_size) / 2 + 1, '4. 결론')

        layout = (field_layouts or {}).get('4. 결론') or {}
        rect = self._synthetic_conclusion_field_rect(layout, page_number=page_number)
        x0, draw_y, rect_w, rect_h = self._pdf_pct_rect(page_width, page_height, rect)

        style = self._find_style_for_label('4. 결론', field_styles or {})
        font_size = float(style.get('font_size') or 9)
        pad_x = 8
        pad_y = 8
        max_text_w = max(8, rect_w - pad_x * 2)
        styled_font = self._register_pdf_font(style.get('font_family', 'gothic'), bold=style.get('bold', False))
        while True:
            leading = font_size + 3
            lines = []
            for paragraph in str(text).splitlines() or ['']:
                wrapped = self._wrap_pdf_text(paragraph, max_text_w, canvas_obj, styled_font, font_size)
                lines.extend(wrapped or [''])
            max_lines = max(1, int((rect_h - pad_y * 2) // leading))
            if len(lines) <= max_lines or font_size <= 7:
                break
            font_size -= 0.5
        lines = lines[:max_lines]

        canvas_obj.setFillColor(self._hex_color(style.get('color', '#080808')))
        canvas_obj.setFont(styled_font, font_size)
        text_y = draw_y + rect_h - pad_y - font_size
        for line in lines:
            line_w = canvas_obj.stringWidth(line, styled_font, font_size)
            align = style.get('align', 'left')
            if align == 'center':
                text_x = x0 + pad_x + max(0, (max_text_w - line_w) / 2)
            elif align == 'right':
                text_x = x0 + rect_w - pad_x - line_w
            else:
                text_x = x0 + pad_x
            canvas_obj.drawString(text_x, text_y, line)
            text_y -= leading
        canvas_obj.restoreState()
        return True

    def _draw_absolute_pdf_images(self, canvas_obj, page_number, page_width, page_height, image_placements=None, instance_id=None):
        items = []
        if isinstance(image_placements, dict):
            items = image_placements.get('__absolute__', []) or []
        if not items or not instance_id:
            return False

        wrote = False
        for item in items:
            if not isinstance(item, dict) or not item.get('filename'):
                continue
            try:
                item_page = int(item.get('page') or 1)
            except Exception:
                item_page = 1
            if item_page != page_number:
                continue

            reader = self._pdf_image_reader_from_data_uri(
                self.struct.graph_gen.get_image_base64(instance_id, item.get('filename'))
            )
            if not reader:
                continue
            try:
                x_pct = float(item.get('x_pct', 8))
                y_pct = float(item.get('y_pct', 8))
                w_pct = float(item.get('w_pct', 32))
                h_pct = float(item.get('h_pct', 20))
            except Exception:
                x_pct, y_pct, w_pct, h_pct = 8, 8, 32, 20

            draw_x = page_width * x_pct / 100
            draw_w = page_width * w_pct / 100
            draw_h = page_height * h_pct / 100
            draw_y = page_height - (page_height * y_pct / 100) - draw_h
            canvas_obj.drawImage(reader, draw_x, draw_y, width=draw_w, height=draw_h, preserveAspectRatio=True, mask='auto')
            wrote = True
        return wrote

    def _generate_raster_pdf_overlay(self, actual_path, all_values, font_name, image_placements=None,
                                     instance_id=None, field_styles=None, direct_overlays=None,
                                     field_layouts=None):
        """원본 PDF 페이지를 이미지 배경으로 고정하고, 값 셀만 새로 그린 제출용 PDF를 만든다."""
        import fitz
        import pdfplumber
        from reportlab.pdfgen import canvas
        from reportlab.lib.utils import ImageReader

        dpi = int(os.environ.get('WIZ_TEMPLATE_RASTER_DPI', '180') or '180')
        zoom = dpi / 72
        out = io.BytesIO()
        doc = fitz.open(actual_path)
        try:
            c = canvas.Canvas(out)
            with pdfplumber.open(actual_path) as pdf:
                sequence_state = {}
                synthesize_conclusion = self._should_synthesize_conclusion_table(pdf, all_values)
                for page_idx, plumber_page in enumerate(pdf.pages):
                    page_width = float(plumber_page.width)
                    page_height = float(plumber_page.height)
                    c.setPageSize((page_width, page_height))

                    fitz_page = doc.load_page(page_idx)
                    pix = fitz_page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
                    c.drawImage(
                        ImageReader(io.BytesIO(pix.tobytes('png'))),
                        0, 0, width=page_width, height=page_height
                    )
                    self._draw_pdf_table_values(
                        plumber_page, c, page_height, all_values, font_name,
                        image_placements=image_placements, instance_id=instance_id,
                        field_styles=field_styles, field_layouts=field_layouts,
                        page_number=page_idx + 1, page_width=page_width,
                        sequence_state=sequence_state
                    )
                    self._draw_direct_overlays(
                        c, page_idx + 1, page_width, page_height,
                        overlays=direct_overlays
                    )
                    self._draw_synthetic_conclusion_field(
                        c, page_idx + 1, len(pdf.pages), page_width, page_height,
                        all_values=all_values, field_styles=field_styles, field_layouts=field_layouts,
                        synthesize_table=synthesize_conclusion
                    )
                    self._draw_absolute_pdf_images(
                        c, page_idx + 1, page_width, page_height,
                        image_placements=image_placements, instance_id=instance_id
                    )
                    c.showPage()
            c.save()
            return out.getvalue()
        finally:
            doc.close()

    def _generate_pdf_overlay_from_path(self, instance_id, instance, actual_path, use_field_layouts=True):
        """PDF를 원본 양식으로 사용해 표의 값 셀에만 텍스트/이미지를 덮어쓴다."""
        import pdfplumber
        from pypdf import PdfReader, PdfWriter
        from reportlab.pdfgen import canvas

        if not os.path.exists(actual_path):
            raise Exception("PDF 원본 양식 파일을 찾을 수 없습니다.")

        all_values = self._collect_all_values(instance_id, instance)
        image_placements = {}
        try:
            image_placements = self.struct.graph_gen.get_placements(instance_id, detailed=True)
        except Exception:
            image_placements = {}
        field_styles = self._field_styles(instance)
        field_layouts = self._direct_field_layouts(instance) if use_field_layouts else {}
        direct_overlays = self._direct_overlays(instance)

        if not all_values and not image_placements and not direct_overlays and not field_layouts:
            with open(actual_path, 'rb') as f:
                return f.read()

        font_name = self._register_pdf_korean_font()

        try:
            return self._generate_raster_pdf_overlay(
                actual_path, all_values, font_name,
                image_placements=image_placements, instance_id=instance_id,
                field_styles=field_styles, direct_overlays=direct_overlays,
                field_layouts=field_layouts
            )
        except Exception:
            pass

        overlays = []

        with pdfplumber.open(actual_path) as pdf:
            sequence_state = {}
            synthesize_conclusion = self._should_synthesize_conclusion_table(pdf, all_values)
            for page_idx, page in enumerate(pdf.pages):
                page_width = float(page.width)
                page_height = float(page.height)
                packet = io.BytesIO()
                c = canvas.Canvas(packet, pagesize=(page_width, page_height))
                wrote = self._draw_pdf_table_values(
                    page, c, page_height, all_values, font_name,
                    image_placements=image_placements, instance_id=instance_id,
                    field_styles=field_styles, field_layouts=field_layouts,
                    page_number=page_idx + 1, page_width=page_width,
                    sequence_state=sequence_state
                )
                wrote = self._draw_direct_overlays(
                    c, page_idx + 1, page_width, page_height,
                    overlays=direct_overlays
                ) or wrote
                wrote = self._draw_synthetic_conclusion_field(
                    c, page_idx + 1, len(pdf.pages), page_width, page_height,
                    all_values=all_values, field_styles=field_styles, field_layouts=field_layouts,
                    synthesize_table=synthesize_conclusion
                ) or wrote
                wrote = self._draw_absolute_pdf_images(
                    c, page_idx + 1, page_width, page_height,
                    image_placements=image_placements, instance_id=instance_id
                ) or wrote

                c.save()
                packet.seek(0)
                overlays.append(packet.getvalue() if wrote else None)

        reader = PdfReader(actual_path)
        writer = PdfWriter()
        for idx, page in enumerate(reader.pages):
            overlay_bytes = overlays[idx] if idx < len(overlays) else None
            if overlay_bytes:
                overlay_reader = PdfReader(io.BytesIO(overlay_bytes))
                page.merge_page(overlay_reader.pages[0])
            writer.add_page(page)

        out = io.BytesIO()
        writer.write(out)
        return out.getvalue()

    def _generate_pdf_overlay(self, instance_id, instance, template_file_path, template_id):
        actual_path = self._template_abspath(template_file_path, template_id)
        return self._generate_pdf_overlay_from_path(instance_id, instance, actual_path)

    # ─── LibreOffice 기반 DOCX → PDF 변환 ─────────────────────
    def _convert_docx_to_pdf(self, docx_path):
        """LibreOffice로 DOCX → PDF 변환. PDF 바이트를 반환."""
        if not os.path.exists(docx_path):
            raise Exception(f"DOCX 파일이 존재하지 않습니다: {docx_path}")

        tmpdir = tempfile.mkdtemp()
        try:
            output_path = self._convert_office_to_pdf_file(docx_path, tmpdir)
            with open(output_path, 'rb') as f:
                return f.read()
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    # ─── PDF 생성 (원본 양식 렌더링 → 오버레이 우선) ──────────
    def generate_pdf_weasy(self, instance_id):
        """PDF 생성: 기존 PDF 원본은 PDF 오버레이를 유지하고, 편집 문서만 DOCX 경로를 탄다."""
        instance = self.struct.doc.get_instance(instance_id)
        content_json = instance.get('content_json', {}) if instance and isinstance(instance.get('content_json'), dict) else {}

        raw_file_type = content_json.get('file_type', '')
        raw_template_file_path = content_json.get('template_file_path', '') or content_json.get('uploaded_file', '')
        raw_template_id = content_json.get('template_id', '') or (instance.get('template_id', '') if instance else '')
        has_table_layout_controls = self._has_docx_table_layout_controls(content_json)
        if raw_file_type == 'pdf' and raw_template_file_path:
            return self._generate_pdf_overlay_from_template(
                instance_id, instance, raw_file_type, raw_template_file_path, raw_template_id
            )
        if has_table_layout_controls and raw_file_type in ('hwp', 'doc', 'docx') and raw_template_file_path:
            try:
                docx_bytes = self.generate_docx(instance_id)
                if docx_bytes:
                    tmpdir = tempfile.mkdtemp()
                    try:
                        tmp_docx = os.path.join(tmpdir, "layout-document.docx")
                        with open(tmp_docx, 'wb') as f:
                            f.write(docx_bytes)
                        pdf_path = self._convert_office_to_pdf_file(tmp_docx, tmpdir)
                        return self._generate_pdf_overlay_from_path(instance_id, instance, pdf_path, use_field_layouts=False)
                    finally:
                        shutil.rmtree(tmpdir, ignore_errors=True)
            except Exception:
                pass
        if raw_file_type in ('hwp', 'doc') and raw_template_file_path:
            return self._generate_pdf_overlay_from_template(
                instance_id, instance, raw_file_type, raw_template_file_path, raw_template_id
            )

        # 1. 이미 생성된 DOCX 출력 파일이 있으면 그것을 최우선 기준으로 PDF 변환한다.
        generated_output_file = content_json.get('generated_output_file', '')
        if generated_output_file:
            fs = wiz.project.fs("data", "outputs", "documents")
            docx_path = fs.abspath(generated_output_file)
            if os.path.exists(docx_path):
                tmpdir = tempfile.mkdtemp()
                try:
                    pdf_path = self._convert_office_to_pdf_file(docx_path, tmpdir)
                    return self._generate_pdf_overlay_from_path(instance_id, instance, pdf_path)
                except Exception:
                    pass
                finally:
                    shutil.rmtree(tmpdir, ignore_errors=True)

        # 2. 수정 가능한 원본 DOCX가 있으면 DOCX 채움 결과를 만든 뒤 PDF로 변환한다.
        try:
            docx_bytes = self.generate_docx(instance_id)
            if docx_bytes:
                tmpdir = tempfile.mkdtemp()
                try:
                    tmp_docx = os.path.join(tmpdir, "document.docx")
                    with open(tmp_docx, 'wb') as f:
                        f.write(docx_bytes)
                    pdf_path = self._convert_office_to_pdf_file(tmp_docx, tmpdir)
                    return self._generate_pdf_overlay_from_path(instance_id, instance, pdf_path)
                finally:
                    shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass

        # 3. 원본 문서 호환용 폴백.
        if raw_file_type == 'docx' and raw_template_file_path:
            return self._generate_pdf_overlay_from_template(
                instance_id, instance, raw_file_type, raw_template_file_path, raw_template_id
            )

        file_type, template_file_path, template_id = self._resolve_template_info(instance, content_json)

        if file_type in ('pdf', 'doc', 'docx', 'hwp') and template_file_path:
            return self._generate_pdf_overlay_from_template(
                instance_id, instance, file_type, template_file_path, template_id
            )

        # 4. 모두 실패 시 ReportLab 폴백
        return self.generate_pdf(instance_id)

    # ─── PDF 생성 (ReportLab 폴백) ────────────────────────────
    def generate_pdf(self, instance_id):
        """섹션 내용을 조합하여 PDF 바이트를 반환 (ReportLab)"""
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.lib.enums import TA_LEFT

        instance = self.struct.doc.get_instance(instance_id)
        sections = self.struct.doc.list_sections(instance_id)

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4,
                                topMargin=25*mm, bottomMargin=20*mm,
                                leftMargin=20*mm, rightMargin=20*mm)

        # 한글 폰트 등록 시도
        font_name = "Helvetica"
        bold_font = "Helvetica-Bold"
        try:
            font_paths = [
                "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
                "/usr/share/fonts/truetype/noto/NotoSansKR-Regular.ttf",
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
            ]
            bold_paths = [
                "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
                "/usr/share/fonts/truetype/noto/NotoSansKR-Bold.ttf",
            ]
            for fp in font_paths:
                if os.path.exists(fp):
                    pdfmetrics.registerFont(TTFont("KorFont", fp))
                    font_name = "KorFont"
                    break
            for fp in bold_paths:
                if os.path.exists(fp):
                    pdfmetrics.registerFont(TTFont("KorFontBold", fp))
                    bold_font = "KorFontBold"
                    break
            if bold_font == "Helvetica-Bold" and font_name == "KorFont":
                bold_font = "KorFont"
        except Exception:
            pass

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'DocTitle', parent=styles['Title'],
            fontName=bold_font, fontSize=18, spaceAfter=12
        )
        heading_style = ParagraphStyle(
            'SecHeading', parent=styles['Heading2'],
            fontName=bold_font, fontSize=13, spaceBefore=16, spaceAfter=6
        )
        body_style = ParagraphStyle(
            'SecBody', parent=styles['BodyText'],
            fontName=font_name, fontSize=10, leading=15, alignment=TA_LEFT
        )
        meta_style = ParagraphStyle(
            'Meta', parent=styles['Normal'],
            fontName=font_name, fontSize=8, textColor='#888888', spaceAfter=20
        )

        story = []
        title_text = self._escape_xml(instance.get('title', '문서'))
        story.append(Paragraph(title_text, title_style))

        meta_parts = []
        if instance.get('week_label'):
            meta_parts.append(f"주차: {instance['week_label']}")
        meta_parts.append(f"생성일: {self._safe_date(instance.get('created'))}")
        story.append(Paragraph(" | ".join(meta_parts), meta_style))
        story.append(Spacer(1, 8*mm))

        for sec in sections:
            sec_title = self._escape_xml(sec.get('section_title', ''))
            story.append(Paragraph(sec_title, heading_style))
            content = sec.get('content', '') or ''
            paragraphs = content.split('\n')
            for para in paragraphs:
                para = para.strip()
                if para:
                    story.append(Paragraph(self._escape_xml(para), body_style))
                else:
                    story.append(Spacer(1, 3*mm))

        doc.build(story)
        pdf_bytes = buf.getvalue()
        buf.close()
        return pdf_bytes

    # ─── DOCX 생성 (python-docx) ─────────────────────────────
    def generate_docx(self, instance_id, use_cached=False):
        """섹션 내용을 조합하여 DOCX 바이트를 반환"""
        instance = self.struct.doc.get_instance(instance_id)
        return self._generate_docx_from_template_or_sections(instance_id, instance, use_cached=use_cached)

    def _generate_docx_from_template_or_sections(self, instance_id, instance=None, use_cached=False):
        """템플릿 기반 DOCX 생성 우선, 없으면 섹션 기반 생성"""
        if not instance:
            instance = self.struct.doc.get_instance(instance_id)
        content_json = instance.get('content_json', {}) if instance and isinstance(instance.get('content_json'), dict) else {}

        # 1. 캐시된 출력 파일은 명시적으로 요청한 경우에만 사용한다.
        # 직접 편집/AI 수정 후 오래된 DOCX가 내려가면 "다운로드는 되지만 내용이 맞지 않는" 문제가 반복된다.
        generated_output_file = content_json.get('generated_output_file', '') if use_cached else ''
        if generated_output_file:
            fs = wiz.project.fs("data", "outputs", "documents")
            output_path = fs.abspath(generated_output_file)
            if os.path.exists(output_path):
                with open(output_path, 'rb') as f:
                    return f.read()

        # 2. 템플릿이 있으면 채워서 DOCX 생성
        template_file_path = content_json.get('template_file_path', '') or content_json.get('uploaded_file', '')
        template_id = content_json.get('template_id', '') or (instance.get('template_id', '') if instance else '')
        file_type = content_json.get('file_type', '')
        if file_type == 'pdf' and template_file_path:
            raise Exception("PDF 원본은 DOCX로 안정적으로 변환할 수 없습니다. PDF 미리보기를 사용하세요.")

        if template_file_path:
            try:
                tpl_fs = wiz.project.fs("data", "uploads", "templates") if template_id else wiz.project.fs("data", "uploads", "instances")
                actual_path = tpl_fs.abspath(template_file_path)
                editable_docx_path = self._resolve_editable_docx_path(instance, content_json)

                if editable_docx_path and os.path.exists(editable_docx_path):
                    all_values = self._collect_all_values(instance_id, instance)
                    sections = self.struct.doc.list_sections(instance_id)
                    section_values = {}
                    for sec in sections:
                        title = sec.get('section_title', '')
                        content = sec.get('content', '')
                        if title and content:
                            section_values[title] = content

                    fill_options = dict(content_json)
                    fill_options['template_id'] = template_id
                    tmpdir = tempfile.mkdtemp()
                    try:
                        output_path = os.path.join(tmpdir, 'output.docx')
                        self.struct.file_parser.fill_template_document(editable_docx_path, output_path, all_values, section_values, layout_options=fill_options)
                        self.struct.file_parser.apply_images_to_docx(output_path, output_path, instance_id)
                        with open(output_path, 'rb') as f:
                            return f.read()
                    finally:
                        shutil.rmtree(tmpdir, ignore_errors=True)

                elif file_type in ('hwp', 'doc'):
                    basename_no_ext = os.path.splitext(actual_path)[0]
                    converted = basename_no_ext + '_converted.docx'
                    if os.path.exists(converted):
                        all_values = self._collect_all_values(instance_id, instance)
                        sections = self.struct.doc.list_sections(instance_id)
                        section_values = {}
                        for sec in sections:
                            title = sec.get('section_title', '')
                            content = sec.get('content', '')
                            if title and content:
                                section_values[title] = content

                        fill_options = dict(content_json)
                        fill_options['template_id'] = template_id
                        tmpdir = tempfile.mkdtemp()
                        try:
                            output_path = os.path.join(tmpdir, 'output.docx')
                            self.struct.file_parser.fill_template_document(converted, output_path, all_values, section_values, layout_options=fill_options)
                            self.struct.file_parser.apply_images_to_docx(output_path, output_path, instance_id)
                            with open(output_path, 'rb') as f:
                                return f.read()
                        finally:
                            shutil.rmtree(tmpdir, ignore_errors=True)
            except Exception as e:
                raise Exception(f"원본 양식 기반 DOCX 생성 실패: {str(e)}")

        if template_id or template_file_path:
            raise Exception("원본 양식 파일을 찾지 못해 DOCX를 생성할 수 없습니다.")

        # 3. 템플릿 없는 문서만 섹션 기반 새 DOCX 생성
        return self._generate_docx_from_sections(instance_id, instance)

    def _generate_docx_from_sections(self, instance_id, instance=None):
        """섹션 내용을 조합하여 새 DOCX 바이트를 생성"""
        from docx import Document
        from docx.shared import Pt, Mm
        from docx.enum.text import WD_ALIGN_PARAGRAPH

        if not instance:
            instance = self.struct.doc.get_instance(instance_id)
        sections = self.struct.doc.list_sections(instance_id)

        document = Document()
        for section in document.sections:
            section.left_margin = Mm(20)
            section.right_margin = Mm(20)
            section.top_margin = Mm(25)
            section.bottom_margin = Mm(20)

        title_para = document.add_heading(instance.get('title', '문서'), level=0)
        title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER

        meta_parts = []
        if instance.get('week_label'):
            meta_parts.append(f"주차: {instance['week_label']}")
        meta_parts.append(f"생성일: {self._safe_date(instance.get('created'))}")
        meta_para = document.add_paragraph(" | ".join(meta_parts))
        meta_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        meta_run = meta_para.runs[0] if meta_para.runs else None
        if meta_run:
            meta_run.font.size = Pt(9)
        document.add_paragraph()

        for sec in sections:
            document.add_heading(sec.get('section_title', ''), level=2)
            content = sec.get('content', '') or ''
            for para_text in content.split('\n'):
                para_text = para_text.strip()
                if para_text:
                    p = document.add_paragraph(para_text)
                    for run in p.runs:
                        run.font.size = Pt(10)

        buf = io.BytesIO()
        document.save(buf)
        docx_bytes = buf.getvalue()
        buf.close()
        return docx_bytes

    # ─── 미리보기 HTML ────────────────────────────────────────
    def preview_html(self, instance_id):
        """문서 미리보기 HTML. 원본 양식이 있으면 원본 렌더링을 우선한다."""
        instance = self.struct.doc.get_instance(instance_id)
        content_json = instance.get('content_json', {}) if instance else {}
        if not isinstance(content_json, dict):
            content_json = {}

        raw_file_type = content_json.get('file_type', '')
        raw_template_file_path = content_json.get('template_file_path', '') or content_json.get('uploaded_file', '')
        raw_template_id = content_json.get('template_id', '') or (instance.get('template_id', '') if instance else '')
        has_table_layout_controls = self._has_docx_table_layout_controls(content_json)
        if has_table_layout_controls and raw_file_type in ('hwp', 'doc', 'docx') and raw_template_file_path:
            try:
                docx_bytes = self.generate_docx(instance_id)
                if docx_bytes:
                    tmpdir = tempfile.mkdtemp()
                    try:
                        tmp_docx = os.path.join(tmpdir, "layout-preview.docx")
                        with open(tmp_docx, 'wb') as f:
                            f.write(docx_bytes)
                        pdf_bytes = self._convert_docx_to_pdf(tmp_docx)
                        return self._pdf_as_html(pdf_bytes)
                    finally:
                        shutil.rmtree(tmpdir, ignore_errors=True)
            except Exception:
                pass
        if raw_file_type in ('pdf', 'hwp', 'doc') and raw_template_file_path:
            try:
                pdf_bytes = self._generate_pdf_overlay_from_template(
                    instance_id, instance, raw_file_type, raw_template_file_path, raw_template_id
                )
                return self._pdf_as_html(pdf_bytes)
            except Exception as e:
                return self._template_error_html(f"원본 양식 미리보기 실패: {str(e)}")

        generated_output_file = content_json.get('generated_output_file', '')
        if generated_output_file:
            fs = wiz.project.fs("data", "outputs", "documents")
            output_path = fs.abspath(generated_output_file)
            if os.path.exists(output_path):
                try:
                    return self._render_docx_file_to_html(output_path, instance)
                except Exception as e:
                    return self._template_error_html(f"DOCX 미리보기 실패: {str(e)}")

        editable_docx_path = self._resolve_editable_docx_path(instance, content_json, create_if_missing=False)
        if editable_docx_path:
            tmpdir = tempfile.mkdtemp()
            try:
                pdf_path = self._convert_office_to_pdf_file(editable_docx_path, tmpdir)
                pdf_bytes = self._generate_pdf_overlay_from_path(instance_id, instance, pdf_path)
                return self._pdf_as_html(pdf_bytes)
            except Exception:
                pass
            finally:
                shutil.rmtree(tmpdir, ignore_errors=True)

        if raw_file_type == 'docx' and raw_template_file_path:
            try:
                pdf_bytes = self._generate_pdf_overlay_from_template(
                    instance_id, instance, raw_file_type, raw_template_file_path, raw_template_id
                )
                return self._pdf_as_html(pdf_bytes)
            except Exception as e:
                return self._template_error_html(f"원본 양식 미리보기 실패: {str(e)}")

        file_type, template_file_path, template_id = self._resolve_template_info(instance, content_json)

        if file_type in ('pdf', 'doc', 'docx', 'hwp') and template_file_path:
            try:
                pdf_bytes = self._generate_pdf_overlay_from_template(
                    instance_id, instance, file_type, template_file_path, template_id
                )
                return self._pdf_as_html(pdf_bytes)
            except Exception as e:
                return self._template_error_html(f"원본 양식 미리보기 실패: {str(e)}")

        if template_id or template_file_path:
            return self._template_error_html("원본 양식 기반 미리보기를 만들 수 없어 줄글 대체 생성을 중단했습니다.")

        sections = self.struct.doc.list_sections(instance_id)
        return self._build_sections_html(instance, sections)

    def direct_editor_html(self, instance_id):
        """원본 페이지 위에 편집 가능한 필드/이미지 오버레이를 얹은 직접 편집 HTML."""
        instance = self.struct.doc.get_instance(instance_id)
        if not instance:
            return self._template_error_html("문서를 찾을 수 없습니다.")

        content_json = instance.get('content_json', {}) if isinstance(instance.get('content_json'), dict) else {}
        raw_file_type = content_json.get('file_type', '')
        raw_template_file_path = content_json.get('template_file_path', '') or content_json.get('uploaded_file', '')
        raw_template_id = content_json.get('template_id', '') or instance.get('template_id', '')

        file_type = raw_file_type
        template_file_path = raw_template_file_path
        template_id = raw_template_id
        if not (file_type in ('pdf', 'doc', 'docx', 'hwp') and template_file_path):
            file_type, template_file_path, template_id = self._resolve_template_info(instance, content_json)
        editable_docx_path = self._resolve_editable_docx_path(instance, content_json, create_if_missing=False)
        generated_output_file = content_json.get('generated_output_file', '')
        if not editable_docx_path and not (file_type in ('pdf', 'doc', 'docx', 'hwp') and template_file_path):
            return self._template_error_html("직접 편집할 원본 양식 파일이 없습니다.")

        tmpdir = tempfile.mkdtemp()
        try:
            pdf_path = ''
            if not pdf_path and raw_file_type in ('pdf', 'hwp', 'doc') and raw_template_file_path:
                pdf_path = self._render_template_to_pdf_path(raw_file_type, raw_template_file_path, raw_template_id, tmpdir)
            if not pdf_path and editable_docx_path and os.path.exists(editable_docx_path):
                pdf_path = self._convert_office_to_pdf_file(editable_docx_path, tmpdir)
            if not pdf_path and generated_output_file:
                output_fs = wiz.project.fs("data", "outputs", "documents")
                output_path = output_fs.abspath(generated_output_file)
                if os.path.exists(output_path):
                    pdf_path = self._convert_office_to_pdf_file(output_path, tmpdir)
            if not pdf_path:
                pdf_path = self._render_template_to_pdf_path(file_type, template_file_path, template_id, tmpdir)
            editor_data = self._build_direct_editor_data(instance_id, instance, pdf_path)
            return self._render_direct_editor_html_v2(instance_id, editor_data)
        except Exception as e:
            return self._template_error_html(f"직접 편집 화면 생성 실패: {str(e)}")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def _pdf_cell_text(self, plumber_page, cell):
        if not cell:
            return ''
        try:
            return (plumber_page.crop(cell).extract_text() or '').replace('\n', ' ').strip()
        except Exception:
            return ''

    def _compact_table_text(self, text):
        return re.sub(r'[\s\.\:：·\-\_\(\)\[\]<>|│/]', '', str(text or '')).lower()

    def _is_pdf_header_row(self, row_texts):
        non_empty = [text for text in row_texts if str(text or '').strip()]
        if len(non_empty) < 2:
            return False
        header_keys = {'구분', '성명', '이름', '학과부', '학과', '전공', '학번', '서명', '차수', '활동내용', '내용', '비고'}
        count = 0
        for text in non_empty:
            compact = self._compact_table_text(text)
            if compact in header_keys:
                count += 1
            elif any(key in compact for key in ['성명', '학과', '학번', '서명']):
                count += 1
        return count >= 2

    def _pdf_visible_table_boxes(self, plumber_page):
        try:
            tables = plumber_page.find_tables()
        except Exception:
            tables = []

        page_width = float(plumber_page.width)
        page_height = float(plumber_page.height)
        boxes = []
        for table in tables:
            cells = []
            try:
                for row in list(table.rows or []):
                    cells.extend([cell for cell in list(row.cells or []) if cell])
            except Exception:
                cells = []
            if cells:
                x0 = min(cell[0] for cell in cells)
                top = min(cell[1] for cell in cells)
                x1 = max(cell[2] for cell in cells)
                bottom = max(cell[3] for cell in cells)
            else:
                try:
                    x0, top, x1, bottom = table.bbox
                except Exception:
                    continue
            if x0 <= 2 and x1 >= page_width - 2:
                continue
            if bottom - top < 4 or x1 - x0 < 20:
                continue
            boxes.append({
                'left': round(x0 / page_width * 100, 4),
                'top': round(top / page_height * 100, 4),
                'width': round((x1 - x0) / page_width * 100, 4),
                'height': round((bottom - top) / page_height * 100, 4),
                'bottom': round(bottom / page_height * 100, 4),
                'left_pt': x0,
                'top_pt': top,
                'right_pt': x1,
                'bottom_pt': bottom,
            })
        boxes.sort(key=lambda item: (item.get('top_pt', 0), item.get('left_pt', 0)))
        for idx, item in enumerate(boxes, start=1):
            item['index'] = idx
        return boxes

    def _sequence_repeated_report_label(self, label, sequence_state=None):
        if sequence_state is None:
            return label
        raw = str(label or '').strip()
        compact = self._compact_table_text(raw)
        targets = {
            '주제': '주제',
            '진행과정': '진행 과정',
            '활동내용': '활동 내용',
        }
        for base, display in targets.items():
            if compact == base:
                counts = sequence_state.setdefault('repeated_counts', {})
                counts[base] = int(counts.get(base, 0) or 0) + 1
                return f"{display} {counts[base]}"
            m = re.fullmatch(rf'{base}(\d+)', compact)
            if m:
                counts = sequence_state.setdefault('repeated_counts', {})
                counts[base] = max(int(counts.get(base, 0) or 0), int(m.group(1)))
                return raw
        return raw

    def _pdf_table_fields(self, plumber_page, all_values=None, field_styles=None, include_all_cells=False,
                          sequence_state=None):
        """PDF 표 셀을 라벨/좌표로 추출한다. include_all_cells=True면 헤더/빈칸까지 직접 편집 가능하게 만든다."""
        all_values = all_values or {}
        field_styles = field_styles or {}
        role_labels = {'멘토', '멘티', '튜터', '튜티', '멘 토', '멘 티'}
        results = []
        try:
            tables = plumber_page.find_tables()
        except Exception:
            tables = []

        page_width = float(plumber_page.width)
        page_height = float(plumber_page.height)

        for t_idx, table in enumerate(tables):
            rows = list(table.rows or [])
            row_cells = [list(row.cells or []) for row in rows]
            row_texts = [[self._pdf_cell_text(plumber_page, cell) for cell in cells] for cells in row_cells]
            table_title = ''
            for texts in row_texts[:3]:
                for text in texts:
                    text = str(text or '').strip()
                    if text:
                        table_title = text
                        break
                if table_title:
                    break

            activity_header_idx = -1
            activity_header_cells = []
            activity_header_texts = []
            for r_idx, texts in enumerate(row_texts):
                compacts = [self._compact_table_text(text) for text in texts]
                if '차수' in compacts and ('활동일자' in compacts or '활동장소' in compacts or '참여자' in compacts):
                    activity_header_idx = r_idx
                    activity_header_cells = row_cells[r_idx]
                    activity_header_texts = texts
                    break
            if activity_header_idx >= 0 and activity_header_cells:
                header_boxes = [cell for cell in activity_header_cells if cell]
                if len(header_boxes) >= 3:
                    for r_idx in range(activity_header_idx + 1, len(row_cells)):
                        texts = row_texts[r_idx] if r_idx < len(row_texts) else []
                        first_text = str(texts[0] if texts else '').strip()
                        if not re.fullmatch(r'\d{1,2}', first_text):
                            continue
                        first_cell = next((cell for cell in row_cells[r_idx] if cell), None)
                        if not first_cell:
                            continue
                        row_top, row_bottom = first_cell[1], first_cell[3]
                        row_cells[r_idx] = [
                            (cell[0], row_top, cell[2], row_bottom)
                            for cell in header_boxes
                        ]
                        row_texts[r_idx] = [first_text] + [''] * (len(header_boxes) - 1)

            header_for_row = {}
            current_header = None
            for r_idx, texts in enumerate(row_texts):
                if self._is_pdf_header_row(texts):
                    current_header = texts
                header_for_row[r_idx] = current_header

            row_roles = {}
            role_counts = {}
            last_role = ''
            for r_idx, texts in enumerate(row_texts):
                if self._is_pdf_header_row(texts):
                    last_role = ''
                    continue
                first_text = str(texts[0] if texts else '').strip()
                first_compact = self._compact_table_text(first_text)
                role = ''
                if first_text and (first_text in role_labels or first_compact in {'멘토', '멘티', '튜터', '튜티'}):
                    role = first_text
                    last_role = first_text
                elif last_role and header_for_row.get(r_idx):
                    role = last_role
                row_roles[r_idx] = role
                if role:
                    role_counts[role] = role_counts.get(role, 0) + 1

            role_seen = {}
            key_value_used = set()
            seen_rects = set()
            for r_idx, cells in enumerate(row_cells):
                texts = row_texts[r_idx] if r_idx < len(row_texts) else []
                is_header = self._is_pdf_header_row(texts)
                role = row_roles.get(r_idx, '')
                role_index = 0
                if role:
                    role_seen[role] = role_seen.get(role, 0) + 1
                    role_index = role_seen[role]

                for c_idx, cell in enumerate(cells):
                    if not cell:
                        continue
                    x0, top, x1, bottom = cell
                    cell_w_pct = (x1 - x0) / page_width * 100 if page_width else 0
                    cell_h_pct = (bottom - top) / page_height * 100 if page_height else 0
                    rect_key = (round(x0, 1), round(top, 1), round(x1, 1), round(bottom, 1))
                    if rect_key in seen_rects:
                        continue
                    seen_rects.add(rect_key)

                    cell_text = texts[c_idx] if c_idx < len(texts) else ''
                    if x0 <= 2 and x1 >= page_width - 2:
                        continue
                    label = ''
                    semantic_target = False

                    header = header_for_row.get(r_idx) or []
                    header_text = header[c_idx] if c_idx < len(header) else ''
                    header_compact = self._compact_table_text(header_text)
                    first_cell = texts[0] if texts else ''
                    left_text = ''
                    for left_idx in range(c_idx - 1, -1, -1):
                        candidate = texts[left_idx] if left_idx < len(texts) else ''
                        if candidate:
                            left_text = candidate
                            break

                    generic_label = f"표{t_idx + 1} {r_idx + 1}행 {c_idx + 1}열"
                    if is_header:
                        if include_all_cells:
                            label = f"{generic_label} ({cell_text})" if cell_text else generic_label
                        else:
                            label = cell_text or generic_label
                    elif (
                        activity_header_idx >= 0
                        and r_idx > activity_header_idx
                        and c_idx > 0
                        and re.fullmatch(r'\d{1,2}', str(first_cell or '').strip())
                        and c_idx < len(activity_header_texts)
                    ):
                        header_text = str(activity_header_texts[c_idx] or '').strip()
                        header_compact = self._compact_table_text(header_text)
                        if header_text and header_compact not in {'차수'}:
                            prefix = table_title if table_title else '활동 참여내역'
                            label = f"{prefix} > {header_text} {r_idx}".strip()
                            semantic_target = True
                    elif c_idx > 0 and role and header_text and header_compact not in {'구분'}:
                        suffix = f" {role_index}" if role_counts.get(role, 0) > 1 else ''
                        label = f"{role} > {header_text}{suffix}".strip()
                        semantic_target = True
                    elif c_idx > 0 and re.fullmatch(r'\d{1,2}', str(first_cell or '').strip()) and left_text:
                        left_compact = self._compact_table_text(left_text)
                        if left_compact in {'주제', '진행과정', '활동사진', '활동내용'}:
                            label = f"{left_text} {int(str(first_cell).strip())}".strip()
                            semantic_target = True
                    elif c_idx > 0 and left_text and not self._is_pdf_header_row(texts):
                        key = (t_idx, r_idx, left_text)
                        if key not in key_value_used:
                            label = left_text
                            semantic_target = True
                            key_value_used.add(key)
                        elif include_all_cells:
                            label = f"{generic_label} ({cell_text})" if cell_text else generic_label
                    elif (c_idx == 0 or len(cells) == 1) and (cell_w_pct >= 55 or len(cells) == 1):
                        prev_texts = row_texts[r_idx - 1] if r_idx > 0 and r_idx - 1 < len(row_texts) else []
                        prev_labels = [str(item or '').strip() for item in prev_texts if str(item or '').strip()]
                        prev_label = prev_labels[0] if prev_labels else ''
                        prev_compact = self._compact_table_text(prev_label)
                        if prev_label and any(key in prev_compact for key in ['활동목표', '학습목표', '결론', '종합평가', '성과', '소감', '진행결과']):
                            label = prev_label
                            semantic_target = True
                    elif include_all_cells:
                        label = f"{generic_label} ({cell_text})" if cell_text else generic_label

                    if not label:
                        continue
                    if not include_all_cells and not semantic_target:
                        continue
                    if semantic_target:
                        label = self._sequence_repeated_report_label(label, sequence_state)

                    if include_all_cells and not semantic_target:
                        current_value = str(all_values[label]) if label in all_values else ''
                    else:
                        current_value = self._find_value_for_label(label, all_values)
                    if not current_value:
                        current_value = cell_text if include_all_cells else ''

                    results.append({
                        'label': label,
                        'value': current_value,
                        'source_text': cell_text,
                        'semantic': semantic_target,
                        'table_index': t_idx + 1,
                        'row_index': r_idx,
                        'col_index': c_idx,
                        'is_header': is_header,
                        'shade': bool(is_header or c_idx == 0 or (r_idx == 0 and cell_text)),
                        'rect': (x0, top, x1, bottom),
                        'left': round(x0 / page_width * 100, 4),
                        'top': round(top / page_height * 100, 4),
                        'width': round((x1 - x0) / page_width * 100, 4),
                        'height': round((bottom - top) / page_height * 100, 4),
                        'style': self._find_style_for_label(label, field_styles),
                    })

        return results

    def _build_direct_editor_data(self, instance_id, instance, pdf_path):
        import fitz
        import pdfplumber

        def _image_url(filename):
            from urllib.parse import quote
            if not filename:
                return ''
            return (
                '/wiz/api/page.doc.write.item/get_image'
                f'?instance_id={quote(str(instance_id))}&filename={quote(str(filename))}'
            )

        dpi = 144
        zoom = dpi / 72
        all_values = self._collect_all_values(instance_id, instance)
        field_styles = self._field_styles(instance)
        field_layouts = self._direct_field_layouts(instance)
        table_spacings = self._direct_table_spacings(instance)
        direct_overlays = self._direct_overlays(instance)
        image_placements = {}
        images = []
        try:
            image_placements = self.struct.graph_gen.get_placements(instance_id, detailed=True)
            images = self.struct.graph_gen.list_images(instance_id)
            for img in images:
                img['data_uri'] = _image_url(img.get('filename'))
        except Exception:
            image_placements = {}
            images = []

        pages = []
        pdf_doc = fitz.open(pdf_path)
        try:
            with pdfplumber.open(pdf_path) as pdf:
                global_table_index = 0
                previous_table_box = None
                sequence_state = {}
                total_pages = len(pdf.pages)
                conclusion_value = self._conclusion_value(all_values)
                conclusion_docx_table = self._conclusion_table_index(instance)
                synthesize_conclusion = self._should_synthesize_conclusion_table(pdf, all_values)
                conclusion_geometry = self._synthetic_conclusion_geometry()
                for page_idx, plumber_page in enumerate(pdf.pages):
                    page_width = float(plumber_page.width)
                    page_height = float(plumber_page.height)
                    fitz_page = pdf_doc.load_page(page_idx)
                    fields = []
                    table_gaps = []
                    synthetic_blocks = []
                    table_boxes = self._pdf_visible_table_boxes(plumber_page)
                    page_table_start_index = global_table_index
                    if synthesize_conclusion and page_idx + 1 == total_pages - 1:
                        synthetic_blocks.append({
                            'type': 'whiteout',
                            **conclusion_geometry['old_title'],
                        })
                    if synthesize_conclusion and page_idx + 1 == total_pages:
                        synthetic_blocks.extend([
                            {
                                'type': 'conclusion_title',
                                'text': '4. 결론',
                                'table_index': page_table_start_index + 1,
                                **conclusion_geometry['title'],
                            },
                            {
                                'type': 'conclusion_body',
                                'table_index': page_table_start_index + 1,
                                **conclusion_geometry['body'],
                            },
                        ])
                    for item in self._pdf_table_fields(
                        plumber_page, all_values, field_styles,
                        include_all_cells=True, sequence_state=sequence_state
                    ):
                        label = item.get('label', '')
                        value = item.get('value', '')
                        source_text = item.get('source_text', '')
                        try:
                            local_table_index = int(item.get('table_index') or 0)
                        except Exception:
                            local_table_index = 0
                        global_field_table_index = (
                            page_table_start_index + local_table_index
                            if local_table_index > 0 else 0
                        )
                        if not bool(item.get('semantic', False)) and global_field_table_index > 0:
                            row_no = int(item.get('row_index') or 0) + 1
                            col_no = int(item.get('col_index') or 0) + 1
                            generic_label = f"표{global_field_table_index} {row_no}행 {col_no}열"
                            label = f"{generic_label} ({source_text})" if source_text else generic_label
                        field = {
                            'label': label,
                            'value': value,
                            'source_text': source_text,
                            'semantic': bool(item.get('semantic', False)),
                            'table_index': global_field_table_index,
                            'local_table': local_table_index,
                            'row_index': int(item.get('row_index') or 0),
                            'col_index': int(item.get('col_index') or 0),
                            'is_table_cell': True,
                            'is_header': bool(item.get('is_header', False)),
                            'shade': bool(item.get('shade', False)),
                            'left': item.get('left', 0),
                            'top': item.get('top', 0),
                            'width': item.get('width', 0),
                            'height': item.get('height', 0),
                            'style': item.get('style', {}),
                        }
                        layout = field_layouts.get(label) if label else None
                        if layout and int(layout.get('page') or 1) == page_idx + 1:
                            for key in ('left', 'top', 'width', 'height'):
                                field[key] = layout.get(key, field.get(key, 0))
                        fields.append({
                            **field,
                            'page': page_idx + 1,
                        })

                    has_conclusion_field = any('결론' in str(field.get('label', '')) for field in fields)
                    if page_idx + 1 == total_pages and conclusion_value and not has_conclusion_field:
                        default_rect = (
                            self._synthetic_conclusion_field_rect(page_number=page_idx + 1)
                            if synthesize_conclusion
                            else {'left': 10.3, 'top': 7.2, 'width': 79.4, 'height': 28.5}
                        )
                        conclusion_field = {
                            'label': '4. 결론',
                            'value': conclusion_value,
                            'source_text': '',
                            'semantic': True,
                            'left': default_rect['left'],
                            'top': default_rect['top'],
                            'width': default_rect['width'],
                            'height': default_rect['height'],
                            'style': self._find_style_for_label('4. 결론', field_styles),
                            'table_index': global_table_index + 1,
                            'local_table': 0,
                            'row_index': 1,
                            'col_index': 1,
                            'is_table_cell': True,
                            'is_header': False,
                            'shade': False,
                            'page': page_idx + 1,
                        }
                        layout = field_layouts.get('4. 결론')
                        if layout and int(layout.get('page') or 1) == page_idx + 1:
                            if synthesize_conclusion:
                                fitted = self._synthetic_conclusion_field_rect(layout, page_number=page_idx + 1)
                                for key in ('left', 'top', 'width', 'height'):
                                    conclusion_field[key] = fitted.get(key, conclusion_field.get(key, 0))
                            else:
                                for key in ('left', 'top', 'width', 'height'):
                                    conclusion_field[key] = layout.get(key, conclusion_field.get(key, 0))
                        fields.append(conclusion_field)

                    for current in table_boxes:
                        global_table_index += 1
                        local_index = int(current.get('index') or 0)
                        current['global_index'] = global_table_index
                        current['page'] = page_idx + 1
                        current['local_index'] = local_index

                        if global_table_index > 1:
                            spacing_id = f"table_{global_table_index}"
                            saved = table_spacings.get(spacing_id, {})
                            same_page = (
                                isinstance(previous_table_box, dict)
                                and int(previous_table_box.get('page') or 0) == page_idx + 1
                            )

                            extra_pct = float(saved.get('extra_pct', 0) or 0) if isinstance(saved, dict) else 0
                            page_break = bool(saved.get('page_break', False)) if isinstance(saved, dict) else False

                            if same_page:
                                gap_top_pt = float(previous_table_box.get('bottom_pt', current.get('top_pt', 0)) or 0)
                                gap_bottom_pt = float(current.get('top_pt', gap_top_pt) or gap_top_pt)
                                gap_pt = max(0, gap_bottom_pt - gap_top_pt)
                                base_pct = max(0.8, gap_pt / page_height * 100)
                                top_pt = max(0, min(page_height - 6, gap_top_pt))
                                left_pt = min(float(previous_table_box.get('left_pt', current.get('left_pt', 0)) or 0), float(current.get('left_pt', 0) or 0))
                                right_pt = max(float(previous_table_box.get('right_pt', current.get('right_pt', page_width)) or page_width), float(current.get('right_pt', page_width) or page_width))
                            else:
                                base_pct = 1.0
                                top_pt = max(0, float(current.get('top_pt', 0) or 0) - (page_height * 0.012))
                                left_pt = float(current.get('left_pt', 0) or 0)
                                right_pt = float(current.get('right_pt', page_width) or page_width)

                            table_gaps.append({
                                'id': spacing_id,
                                'page': page_idx + 1,
                                'before_table': global_table_index,
                                'after_table': global_table_index - 1,
                                'docx_before_table': global_table_index,
                                'local_table': local_index,
                                'left': round(max(0, left_pt) / page_width * 100, 4),
                                'top': round(top_pt / page_height * 100, 4),
                                'width': round(max(12, right_pt - left_pt) / page_width * 100, 4),
                                'height': round(max(0.8, min(40, base_pct + extra_pct)), 4),
                                'base_height': round(max(0.8, base_pct), 4),
                                'page_height_pt': page_height,
                                'page_break': page_break,
                            })

                        previous_table_box = current

                    if page_idx + 1 == total_pages and conclusion_value and not table_boxes:
                        spacing_id = 'conclusion_before'
                        saved = table_spacings.get(spacing_id, {})
                        extra_pct = float(saved.get('extra_pct', 0) or 0) if isinstance(saved, dict) else 0
                        gap_rect = conclusion_geometry['gap'] if synthesize_conclusion else {
                            'left': 9.8, 'top': 4.9, 'width': 80.5, 'height': 1.0
                        }
                        table_gaps.append({
                            'id': spacing_id,
                            'label': '결론 표 앞',
                            'page': page_idx + 1,
                            'before_table': global_table_index + 1,
                            'after_table': global_table_index,
                            'docx_before_table': conclusion_docx_table,
                            'local_table': 1,
                            'left': gap_rect['left'],
                            'top': gap_rect['top'],
                            'width': gap_rect['width'],
                            'height': round(max(0.8, min(40, 1.0 + extra_pct)), 4),
                            'base_height': 1.0,
                            'page_height_pt': page_height,
                            'page_break': bool(saved.get('page_break', False)) if isinstance(saved, dict) else False,
                        })

                    pix = fitz_page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
                    bg = 'data:image/png;base64,' + base64.b64encode(pix.tobytes('png')).decode('ascii')

                    absolute_images = []
                    for item in image_placements.get('__absolute__', []) if isinstance(image_placements, dict) else []:
                        if not isinstance(item, dict):
                            continue
                        try:
                            item_page = int(item.get('page') or 1)
                        except Exception:
                            item_page = 1
                        if item_page != page_idx + 1:
                            continue
                        data_uri = _image_url(item.get('filename'))
                        if not data_uri:
                            continue
                        absolute_images.append({
                            'filename': item.get('filename'),
                            'data_uri': data_uri,
                            'page': item_page,
                            'left': float(item.get('x_pct', 8)),
                            'top': float(item.get('y_pct', 8)),
                            'width': float(item.get('w_pct', 32)),
                            'height': float(item.get('h_pct', 20)),
                        })

                    pages.append({
                        'number': page_idx + 1,
                        'width': page_width,
                        'height': page_height,
                        'background': bg,
                        'fields': fields,
                        'table_gaps': table_gaps,
                        'synthetic_blocks': synthetic_blocks,
                        'absolute_images': absolute_images,
                        'custom_overlays': [
                            item for item in direct_overlays
                            if int(item.get('page') or 1) == page_idx + 1
                        ],
                    })
        finally:
            pdf_doc.close()

        return {
            'title': instance.get('title', '문서'),
            'pages': pages,
            'images': images,
        }

    def _post_message_origin_guard_script(self):
        return """<script>
(function () {
  var legacyReviewOrigin = 'https://review.season.co.kr';
  function sameOriginFor(targetWindow) {
    try {
      if (targetWindow && targetWindow.location && targetWindow.location.origin) {
        return targetWindow.location.origin;
      }
    } catch (e) {}
    try {
      return window.location.origin;
    } catch (e) {
      return '*';
    }
  }
  function patch(targetWindow) {
    try {
      if (!targetWindow || !targetWindow.Window || !targetWindow.Window.prototype) return;
      var proto = targetWindow.Window.prototype;
      if (proto.__docsAiPostMessageOriginGuard) return;
      var original = proto.postMessage;
      if (typeof original !== 'function') return;
      Object.defineProperty(proto, '__docsAiPostMessageOriginGuard', { value: true });
      proto.postMessage = function (message, targetOriginOrOptions, transfer) {
        if (targetOriginOrOptions === legacyReviewOrigin) {
          var safeOrigin = sameOriginFor(this);
          if (transfer !== undefined) return original.call(this, message, safeOrigin, transfer);
          return original.call(this, message, safeOrigin);
        }
        if (
          targetOriginOrOptions &&
          typeof targetOriginOrOptions === 'object' &&
          targetOriginOrOptions.targetOrigin === legacyReviewOrigin
        ) {
          var options = Object.assign({}, targetOriginOrOptions, { targetOrigin: sameOriginFor(this) });
          return original.call(this, message, options);
        }
        return original.apply(this, arguments);
      };
    } catch (e) {}
  }
  patch(window);
  try { patch(window.parent); } catch (e) {}
  try { patch(window.top); } catch (e) {}
})();
</script>"""

    def _render_direct_editor_html_v2(self, instance_id, editor_data):
        data_json = json.dumps(editor_data, ensure_ascii=False).replace('</', '<\\/')
        instance_json = json.dumps(instance_id, ensure_ascii=False).replace('</', '<\\/')
        title_html = html.escape(str(editor_data.get('title', '문서')))
        html_doc = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
__POST_MESSAGE_GUARD__
<style>
* { box-sizing: border-box; }
html, body { margin: 0; min-height: 100%; }
body { background: #f4f4f2; color: #080808; font-family: Inter, Arial, "Malgun Gothic", sans-serif; }
.app { min-height: 100vh; display: grid; grid-template-columns: minmax(0, 1fr) 304px; }
.pages { padding: 24px; overflow: auto; }
.page { position: relative; margin: 0 auto 24px; background: #fff; box-shadow: 0 84px 24px rgba(0,0,0,0), 0 54px 22px rgba(0,0,0,0.01), 0 30px 18px rgba(0,0,0,0.04), 0 13px 13px rgba(0,0,0,0.08), 0 3px 7px rgba(0,0,0,0.09); }
.page-bg { display: block; width: 100%; height: auto; user-select: none; pointer-events: none; }
.synthetic-block { position: absolute; z-index: 3; pointer-events: none; }
.synthetic-whiteout { background: #fff; }
.synthetic-conclusion-title { display: flex; align-items: center; padding: 0 8px; border: 1px solid #080808; background: #d7e5f6; color: #080808; font-family: "Nanum Myeongjo","Batang",serif; font-size: 11pt; line-height: 1.2; }
.synthetic-conclusion-body { border: 1px solid #080808; background: #fff; }
.field { position: absolute; z-index: 6; border: 1px solid rgba(20,110,245,.12); background: rgba(255,255,255,.02); color: #080808; padding: 3px 5px; resize: both; overflow: auto; outline: none; line-height: 1.35; min-width: 24px; min-height: 18px; white-space: pre-wrap; }
.field.table-cell { border-color: #222; background: #fff; box-shadow: inset 0 0 0 .2px #222; }
.field.table-cell.table-shade { background: #d7e5f6; font-weight: 600 !important; text-align: center !important; }
.field.table-cell:focus { background: #fff; }
.field:hover { border-color: rgba(20,110,245,.55); background: rgba(255,255,255,.18); }
.field.table-cell:hover { background: #fff; }
.field.table-cell.table-shade:hover { background: #d7e5f6; }
.field:focus { border-color: #146ef5; background: rgba(255,255,255,.82); box-shadow: 0 0 0 2px rgba(20,110,245,.18); z-index: 20; }
.field.table-cell:focus { background: #fff; }
.field::placeholder { color: transparent; }
.field:focus::placeholder { color: #9ca3af; }
.field.batch-selected { border-color: #0f766e; background: rgba(20,184,166,.16); box-shadow: inset 0 0 0 1px rgba(15,118,110,.45); }
.table-gap { position: absolute; z-index: 14; border: 1px dashed rgba(20,110,245,.55); background: rgba(20,110,245,.08); cursor: ns-resize; min-height: 8px; }
.table-gap::before { content: attr(data-label); position: absolute; left: 8px; right: 8px; top: 50%; border-top: 2px solid rgba(20,110,245,.55); color: #146ef5; font-size: 11px; font-weight: 700; line-height: 16px; text-align: center; transform: translateY(-50%); text-shadow: 0 1px 0 #fff; }
.table-gap:hover, .table-gap.selected { background: rgba(20,110,245,.16); border-color: #146ef5; z-index: 18; }
.table-gap.page-break { border-style: solid; border-color: #7c3aed; background: rgba(124,58,237,.14); }
.table-gap.page-break::before { border-top-color: #7c3aed; color: #5b21b6; content: "다음 페이지"; }
.gap-resize { position: absolute; left: 50%; bottom: -5px; width: 38px; height: 10px; transform: translateX(-50%); background: #146ef5; border: 2px solid #fff; border-radius: 999px; cursor: ns-resize; }
.table-resize-handle { position: absolute; z-index: 17; background: rgba(20,110,245,0); }
.table-resize-handle.col { width: 10px; margin-left: -5px; cursor: col-resize; }
.table-resize-handle.row { height: 10px; margin-top: -5px; cursor: row-resize; }
.table-resize-handle::after { content: ""; position: absolute; background: rgba(20,110,245,0); transition: background .12s ease; }
.table-resize-handle.col::after { top: 0; bottom: 0; left: 4px; width: 2px; }
.table-resize-handle.row::after { left: 0; right: 0; top: 4px; height: 2px; }
.table-resize-handle:hover::after, .table-resize-handle.active::after { background: #146ef5; }
.abs-img, .custom-box { position: absolute; border: 1px solid #146ef5; background: rgba(255,255,255,.35); cursor: move; z-index: 5; }
.abs-img { z-index: 4; }
.custom-text { z-index: 7; }
.abs-img.selected, .custom-box.selected { border-color: #080808; box-shadow: 0 0 0 2px rgba(8,8,8,.16); z-index: 8; }
.abs-img img { width: 100%; height: 100%; object-fit: contain; display: block; pointer-events: none; }
.custom-box { background: transparent; }
.custom-box textarea { width: 100%; height: 100%; border: 0; background: transparent; resize: none; outline: none; padding: 5px; line-height: 1.35; overflow: auto; cursor: text; white-space: pre-wrap; }
.resize { position: absolute; right: -5px; bottom: -5px; width: 11px; height: 11px; background: #146ef5; border: 2px solid #fff; cursor: nwse-resize; }
.side { border-left: 1px solid #d8d8d8; background: #fff; padding: 16px; overflow: auto; position: sticky; top: 0; height: 100vh; }
.eyebrow { font-size: 11px; letter-spacing: .8px; text-transform: uppercase; color: #5a5a5a; margin: 18px 0 8px; }
.eyebrow:first-child { margin-top: 0; }
.title { font-size: 16px; font-weight: 600; margin-bottom: 16px; line-height: 1.35; }
.control { margin-bottom: 12px; }
.control label { display: block; font-size: 12px; color: #4b5563; margin-bottom: 5px; }
select, input[type="number"], input[type="color"] { width: 100%; border: 1px solid #d8d8d8; border-radius: 4px; padding: 8px; font-size: 13px; background: #fff; }
.row { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.seg { display: flex; gap: 6px; flex-wrap: wrap; }
button { border: 1px solid #d8d8d8; background: #fff; color: #080808; border-radius: 4px; padding: 8px 10px; font-size: 12px; cursor: pointer; }
button.active, .primary { background: #080808; color: #fff; border-color: #080808; }
button.danger { color: #ee1d36; }
button:disabled { opacity: .45; cursor: not-allowed; }
.tool-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.tool-grid .wide { grid-column: 1 / -1; }
.gap-panel { display: none; margin: 8px 0 12px; padding: 10px; border: 1px solid #e5e7eb; border-radius: 6px; background: #f9fafb; }
.gap-panel.active { display: block; }
.gap-actions { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.status { min-height: 18px; font-size: 12px; color: #5a5a5a; margin: 8px 0 16px; line-height: 1.45; }
.image-list { display: grid; gap: 8px; }
.image-item { border: 1px solid #e5e7eb; border-radius: 6px; padding: 8px; }
.image-item img { width: 100%; height: 92px; object-fit: contain; background: #f9fafb; border-radius: 4px; }
.image-name { font-size: 11px; color: #4b5563; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; margin: 6px 0; }
.selection-rect { position: absolute; border: 1px dashed #0f766e; background: rgba(20,184,166,.12); z-index: 20; pointer-events: none; }
@media (max-width: 900px) { .app { grid-template-columns: 1fr; } .side { position: static; height: auto; border-left: 0; border-top: 1px solid #d8d8d8; } .pages { padding: 12px; } }
</style>
</head>
<body>
<div class="app">
  <main class="pages" id="pages"></main>
  <aside class="side">
    <div class="eyebrow">Direct Editor</div>
    <div class="title">__TITLE__</div>

    <div class="eyebrow">Text Style</div>
    <div class="control">
      <label>글꼴</label>
      <select id="fontFamily">
        <option value="gothic">고딕</option>
        <option value="myeongjo">명조</option>
        <option value="batang">바탕</option>
        <option value="mono">고정폭</option>
      </select>
    </div>
    <div class="row">
      <div class="control">
        <label>크기(pt)</label>
        <input id="fontSize" type="number" min="5" max="28" step="0.5" value="9">
      </div>
      <div class="control">
        <label>색상</label>
        <input id="fontColor" type="color" value="#080808">
      </div>
    </div>
    <div class="control">
      <label>정렬/굵기</label>
      <div class="seg">
        <button id="boldBtn" type="button">B</button>
        <button data-align="left" type="button">좌</button>
        <button data-align="center" type="button">중</button>
        <button data-align="right" type="button">우</button>
      </div>
    </div>

	    <div class="eyebrow">Free Layout</div>
	    <div class="tool-grid">
	      <button type="button" id="addTextBtn" class="wide">텍스트 박스</button>
	      <button type="button" id="deleteBtn" class="wide danger">선택 항목 삭제</button>
	    </div>
    <div class="eyebrow">Table Layout</div>
    <div class="gap-panel" id="gapPanel">
      <div class="control">
        <label>표 앞 간격(mm)</label>
        <input id="gapMm" type="number" min="0" max="80" step="1" value="0">
      </div>
      <div class="gap-actions">
        <button type="button" id="gapMinusBtn">-5mm</button>
        <button type="button" id="gapPlusBtn">+5mm</button>
      </div>
    </div>
    <div class="tool-grid">
      <button type="button" id="pageBreakBtn" class="wide">선택 표 다음 페이지로</button>
      <button type="button" id="resetGapBtn" class="wide">표 간격 초기화</button>
    </div>
    <div class="status" id="status">필드나 박스를 클릭해서 바로 수정하세요.</div>
    <button class="primary" type="button" id="reloadBtn">저장된 PDF 새로고침</button>

    <div class="eyebrow">Images</div>
    <div class="image-list" id="imageList"></div>
  </aside>
</div>
<script>
const INSTANCE_ID = __INSTANCE_JSON__;
const DATA = __DATA_JSON__;
const SAVE_FIELD_URL = '/wiz/api/page.doc.write.item/save_field_value';
const SAVE_IMAGE_URL = '/wiz/api/page.doc.write.item/save_image_placement';
const REMOVE_IMAGE_URL = '/wiz/api/page.doc.write.item/remove_image_placement';
const SAVE_OVERLAYS_URL = '/wiz/api/page.doc.write.item/save_direct_overlays';
const SAVE_TABLE_SPACING_URL = '/wiz/api/page.doc.write.item/save_table_spacing';
const SAVE_FIELD_LAYOUTS_URL = '/wiz/api/page.doc.write.item/save_field_layouts';
let activeField = null;
let selectedBox = null;
let activeAlign = 'left';
let dragState = null;
let gapState = null;
let tableResizeState = null;
let overlayTimer = null;
let selectedFields = new Set();
let selectDrag = null;
let selectedGap = null;

function status(text) { document.getElementById('status').textContent = text; }
function uid() { return 'ov-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 8); }
function styleOf(el) {
  try { return JSON.parse(el.dataset.style || '{}'); } catch (_) { return {}; }
}
function normalizeStyle(st) {
  return {
    font_family: st.font_family || 'gothic',
    font_size: Number(st.font_size || 9),
    bold: !!st.bold,
    align: st.align || 'left',
    color: st.color || '#080808'
  };
}
function cssFont(family) {
  if (family === 'myeongjo' || family === 'batang') return '"Nanum Myeongjo","Batang",serif';
  if (family === 'mono') return '"Nanum Gothic Coding","Consolas",monospace';
  return '"Nanum Gothic","Malgun Gothic",sans-serif';
}
function applyTextStyle(el, st) {
  st = normalizeStyle(st || styleOf(el));
  el.style.fontFamily = cssFont(st.font_family);
  el.style.fontSize = st.font_size + 'pt';
  el.style.fontWeight = st.bold ? '600' : '400';
  el.style.textAlign = st.align;
  el.style.color = st.color;
}
function applyFieldStyle(el) { applyTextStyle(el, styleOf(el)); }
function applyCustomBoxStyle(box) {
  const area = box.querySelector('textarea');
  if (area) applyTextStyle(area, styleOf(box));
}
function clampNum(value, min, max) {
  value = Number(value);
  if (!Number.isFinite(value)) value = min;
  return Math.max(min, Math.min(max, value));
}
function pctValue(value, fallback) {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}
function gapExtraPct(gap) {
  if (!gap) return 0;
  const height = pctValue(parseFloat(gap.style.height), 0);
  const base = pctValue(parseFloat(gap.dataset.baseHeight), 0);
  return Math.max(0, height - base);
}
function sortedPageGaps(page) {
  return Array.from(page.querySelectorAll('.table-gap'))
    .sort((a, b) => Number(a.dataset.beforeTable || 0) - Number(b.dataset.beforeTable || 0));
}
function tableOffsetPctFor(page, tableIndex) {
  tableIndex = Number(tableIndex || 0);
  if (!page || tableIndex <= 0) return 0;
  return sortedPageGaps(page).reduce((sum, gap) => {
    const before = Number(gap.dataset.beforeTable || 0);
    return before > 0 && tableIndex >= before ? sum + gapExtraPct(gap) : sum;
  }, 0);
}
function tableOffsetPctForElement(el) {
  const page = el.closest('.page');
  return tableOffsetPctFor(page, Number(el.dataset.tableIndex || 0));
}
function fieldBaseTop(el) {
  return pctValue(parseFloat(el.dataset.baseTop), parseFloat(el.style.top) || 0);
}
function fieldRectPct(el) {
  return {
    left: pctValue(parseFloat(el.style.left), 0),
    top: fieldBaseTop(el),
    width: pctValue(parseFloat(el.style.width), 1),
    height: pctValue(parseFloat(el.style.height), 1)
  };
}
function setFieldRectPct(el, rect) {
  const left = Math.max(0, Math.min(99, Number(rect.left || 0)));
  const top = Math.max(0, Math.min(99, Number(rect.top || 0)));
  const width = Math.max(1, Math.min(100 - left, Number(rect.width || 1)));
  const height = Math.max(1, Math.min(100 - top, Number(rect.height || 1)));
  el.dataset.baseTop = String(top);
  el.style.left = left + '%';
  el.style.top = (top + tableOffsetPctForElement(el)) + '%';
  el.style.width = width + '%';
  el.style.height = height + '%';
}
function gapOffsetPct(gap) {
  const page = gap.closest('.page');
  const beforeTable = Number(gap.dataset.beforeTable || 0);
  if (!page || beforeTable <= 0) return 0;
  return sortedPageGaps(page).reduce((sum, other) => {
    if (other === gap) return sum;
    const otherBefore = Number(other.dataset.beforeTable || 0);
    return otherBefore > 0 && otherBefore < beforeTable ? sum + gapExtraPct(other) : sum;
  }, 0);
}
function applyTableLayoutOffsets() {
  document.querySelectorAll('.page').forEach(page => {
    page.querySelectorAll('[data-table-index]').forEach(el => {
      const tableIndex = Number(el.dataset.tableIndex || 0);
      if (!tableIndex) return;
      if (!el.dataset.baseTop) el.dataset.baseTop = String(parseFloat(el.style.top) || 0);
      const baseTop = pctValue(parseFloat(el.dataset.baseTop), parseFloat(el.style.top) || 0);
      const height = pctValue(parseFloat(el.style.height), 0);
      const nextTop = Math.max(0, Math.min(100 - Math.min(height, 99), baseTop + tableOffsetPctFor(page, tableIndex)));
      el.style.top = nextTop + '%';
    });
    sortedPageGaps(page).forEach(gap => {
      if (!gap.dataset.baseTop) gap.dataset.baseTop = String(parseFloat(gap.style.top) || 0);
      const baseTop = pctValue(parseFloat(gap.dataset.baseTop), parseFloat(gap.style.top) || 0);
      gap.style.top = Math.max(0, Math.min(98, baseTop + gapOffsetPct(gap))) + '%';
    });
    positionTableResizeHandles(page);
  });
}
function fieldLayout(el) {
  return {
    page: Number(el.dataset.page || el.closest('.page')?.dataset.page || 1),
    left: clampNum(parseFloat(el.style.left), 0, 100),
    top: clampNum(parseFloat(el.dataset.baseTop || el.style.top), 0, 100),
    width: clampNum(parseFloat(el.style.width), 1, 100),
    height: clampNum(parseFloat(el.style.height), 1, 100)
  };
}
function syncFieldGeometry(el) {
  const page = el.closest('.page');
  if (!page) return fieldLayout(el);
  const pageRect = page.getBoundingClientRect();
  const rect = el.getBoundingClientRect();
  if (!pageRect.width || !pageRect.height) return fieldLayout(el);
  const next = {
    page: Number(page.dataset.page || 1),
    left: clampNum((rect.left - pageRect.left) / pageRect.width * 100, 0, 99),
    top: clampNum(((rect.top - pageRect.top) / pageRect.height * 100) - tableOffsetPctForElement(el), 0, 99),
    width: clampNum(rect.width / pageRect.width * 100, 1, 100),
    height: clampNum(rect.height / pageRect.height * 100, 1, 100)
  };
  next.width = Math.min(next.width, 100 - next.left);
  next.height = Math.min(next.height, 100 - next.top);
  el.dataset.page = String(next.page);
  el.dataset.baseTop = String(next.top);
  el.style.left = next.left + '%';
  el.style.top = (next.top + tableOffsetPctForElement(el)) + '%';
  el.style.width = next.width + '%';
  el.style.height = next.height + '%';
  return next;
}
function autoGrowField(el) {
  const page = el.closest('.page');
  if (!page) return;
  const pageRect = page.getBoundingClientRect();
  if (!pageRect.height) return;
  if (el.scrollHeight > el.clientHeight + 2) {
    const current = parseFloat(el.style.height) || 1;
    const extraPct = (el.scrollHeight - el.clientHeight + 8) / pageRect.height * 100;
    el.style.height = Math.min(100 - (parseFloat(el.style.top) || 0), current + extraPct) + '%';
  }
}
function readToolbar() {
  return normalizeStyle({
    font_family: document.getElementById('fontFamily').value,
    font_size: document.getElementById('fontSize').value,
    bold: document.getElementById('boldBtn').classList.contains('active'),
    align: activeAlign,
    color: document.getElementById('fontColor').value
  });
}
function writeToolbar(st) {
  st = normalizeStyle(st);
  document.getElementById('fontFamily').value = st.font_family;
  document.getElementById('fontSize').value = st.font_size;
  document.getElementById('fontColor').value = st.color;
  document.getElementById('boldBtn').classList.toggle('active', st.bold);
  activeAlign = st.align;
  document.querySelectorAll('[data-align]').forEach(btn => btn.classList.toggle('active', btn.dataset.align === activeAlign));
}
function clearSelection() {
  document.querySelectorAll('.selected').forEach(el => el.classList.remove('selected'));
  selectedFields.forEach(el => el.classList.remove('batch-selected'));
  selectedFields.clear();
  selectedGap = null;
  updateGapButtons();
}
function selectBox(box) {
  clearSelection();
  selectedBox = box;
  activeField = null;
  if (!box) return;
  box.classList.add('selected');
	  if (box.dataset.kind === 'custom' && box.dataset.type === 'text') {
	    writeToolbar(styleOf(box));
	    status('자유 텍스트 박스 편집 중');
	  } else {
	    status('이미지 선택됨. 드래그로 이동하고 모서리로 크기를 조절하세요.');
	  }
}
function selectGap(gap) {
  clearSelection();
  selectedBox = null;
  activeField = null;
  if (!gap) return;
  selectedGap = gap;
  gap.classList.add('selected');
  const target = gap.dataset.beforeTable || '';
  status(target ? target + '번째 표 앞 간격 조절 중' : '표 앞 간격 조절 중');
  updateGapButtons();
}
function selectField(el) {
  clearSelection();
  selectedBox = null;
  activeField = el;
  writeToolbar(styleOf(el));
  status('편집 중: ' + (el.dataset.label || '필드'));
}
function selectFields(fields) {
  clearSelection();
  activeField = null;
  selectedBox = null;
  fields.forEach(el => {
    selectedFields.add(el);
    el.classList.add('batch-selected');
  });
  if (fields.length) {
    writeToolbar(styleOf(fields[0]));
    status(fields.length + '개 칸 선택됨. 글꼴/크기/정렬/색을 한 번에 바꿀 수 있습니다.');
  }
}
function toolbarChanged() {
  if (selectedFields.size) {
    const st = readToolbar();
    selectedFields.forEach(el => {
      el.dataset.style = JSON.stringify(st);
      applyFieldStyle(el);
      scheduleSave(el);
    });
    return;
  }
  if (activeField) {
    activeField.dataset.style = JSON.stringify(readToolbar());
    applyFieldStyle(activeField);
    scheduleSave(activeField);
    return;
  }
  if (selectedBox && selectedBox.dataset.kind === 'custom' && selectedBox.dataset.type === 'text') {
    selectedBox.dataset.style = JSON.stringify(readToolbar());
    applyCustomBoxStyle(selectedBox);
    scheduleOverlaySave();
  }
}
function saveField(el) {
  const fd = new FormData();
  fd.append('id', INSTANCE_ID);
  fd.append('label', el.dataset.label || '');
  const hasTextEdit = el.dataset.dirty === '1' || el.dataset.semantic === '1';
  if (hasTextEdit) fd.append('content', el.value || '');
  else fd.append('skip_content', '1');
  fd.append('style', el.dataset.style || '{}');
  fd.append('layout', JSON.stringify(syncFieldGeometry(el)));
  return fetch(SAVE_FIELD_URL, { method: 'POST', body: fd })
    .then(() => { el.dataset.dirty = '0'; status('저장됨: ' + (el.dataset.label || '필드')); parent.postMessage({type:'wiz-direct-editor-saved'}, '*'); })
    .catch(() => status('저장 실패'));
}
function scheduleSave(el) {
  clearTimeout(el._saveTimer);
  el._saveTimer = setTimeout(() => saveField(el), 420);
}
function renderSyntheticBlock(block) {
  const el = document.createElement('div');
  const type = block.type || 'block';
  el.className = 'synthetic-block synthetic-' + type.replace(/_/g, '-');
  if (block.table_index) el.dataset.tableIndex = block.table_index;
  el.style.left = (Number(block.left) || 0) + '%';
  el.style.top = (Number(block.top) || 0) + '%';
  el.dataset.baseTop = String(Number(block.top) || 0);
  el.style.width = (Number(block.width) || 0) + '%';
  el.style.height = (Number(block.height) || 0) + '%';
  if (block.text) el.textContent = block.text;
  return el;
}
function renderPages() {
  const root = document.getElementById('pages');
  root.innerHTML = '';
  DATA.pages.forEach(page => {
    const pageEl = document.createElement('section');
    pageEl.className = 'page';
    pageEl.dataset.page = page.number;
    pageEl.style.maxWidth = page.width + 'px';
    pageEl.innerHTML = `<img class="page-bg" src="${page.background}" alt="page ${page.number}">`;
    pageEl.addEventListener('pointerdown', startFieldMarquee);

    (page.synthetic_blocks || []).forEach(block => pageEl.appendChild(renderSyntheticBlock(block)));

    page.fields.forEach(field => {
      const el = document.createElement('textarea');
      const classes = ['field'];
      if (field.is_table_cell) classes.push('table-cell');
      if (field.shade) classes.push('table-shade');
      el.className = classes.join(' ');
      el.dataset.label = field.label;
      el.dataset.page = field.page || page.number;
      el.dataset.sourceText = field.source_text || '';
      el.dataset.semantic = field.semantic ? '1' : '0';
      el.dataset.dirty = '0';
      el.dataset.style = JSON.stringify(field.style || {});
      el.dataset.tableIndex = field.table_index || 0;
      el.dataset.localTable = field.local_table || 0;
      el.dataset.rowIndex = field.row_index || 0;
      el.dataset.colIndex = field.col_index || 0;
      el.dataset.baseTop = String(field.top || 0);
      el.value = field.value || '';
      el.title = field.label;
      el.placeholder = field.source_text || '';
      el.style.left = field.left + '%';
      el.style.top = field.top + '%';
      el.style.width = field.width + '%';
      el.style.height = field.height + '%';
      el.addEventListener('focus', () => selectField(el));
      el.addEventListener('input', () => {
        el.dataset.dirty = '1';
        autoGrowField(el);
        document.querySelectorAll('.field').forEach(other => {
          if (other !== el && other.dataset.label === field.label) other.value = el.value;
        });
        scheduleSave(el);
      });
      el.addEventListener('blur', () => { syncFieldGeometry(el); saveField(el); });
      el.addEventListener('mouseup', () => { syncFieldGeometry(el); scheduleSave(el); });
      applyFieldStyle(el);
      pageEl.appendChild(el);
      requestAnimationFrame(() => autoGrowField(el));
    });

    (page.table_gaps || []).forEach(gap => pageEl.appendChild(renderTableGap(gap)));
    (page.custom_overlays || []).forEach(item => pageEl.appendChild(renderCustomOverlay(item)));
    (page.absolute_images || []).forEach(img => pageEl.appendChild(renderAbsImage(img)));
    renderTableResizeHandles(pageEl);
    root.appendChild(pageEl);
  });
  requestAnimationFrame(() => {
    applyTableLayoutOffsets();
    document.querySelectorAll('.page').forEach(page => avoidFieldImageOverlap(page));
  });
}
function tableCells(page, tableIndex) {
  return Array.from(page.querySelectorAll('.field.table-cell'))
    .filter(el => Number(el.dataset.tableIndex || 0) === Number(tableIndex || 0));
}
function tableGroups(page) {
  const groups = new Map();
  Array.from(page.querySelectorAll('.field.table-cell')).forEach(el => {
    const tableIndex = Number(el.dataset.tableIndex || 0);
    if (!tableIndex) return;
    if (!groups.has(tableIndex)) groups.set(tableIndex, []);
    groups.get(tableIndex).push(el);
  });
  return groups;
}
function uniqueSorted(values, epsilon = 0.18) {
  const sorted = values
    .filter(value => Number.isFinite(value))
    .sort((a, b) => a - b);
  const result = [];
  sorted.forEach(value => {
    if (!result.length || Math.abs(result[result.length - 1] - value) > epsilon) {
      result.push(value);
    } else {
      result[result.length - 1] = (result[result.length - 1] + value) / 2;
    }
  });
  return result;
}
function tableBounds(cells) {
  const rects = cells.map(fieldRectPct);
  if (!rects.length) return null;
  const left = Math.min(...rects.map(r => r.left));
  const top = Math.min(...rects.map(r => r.top + tableOffsetPctForElement(cells[0])));
  const right = Math.max(...rects.map(r => r.left + r.width));
  const bottom = Math.max(...rects.map(r => r.top + tableOffsetPctForElement(cells[0]) + r.height));
  return { left, top, right, bottom, width: right - left, height: bottom - top };
}
function clearTableResizeHandles(page) {
  page.querySelectorAll('.table-resize-handle').forEach(handle => handle.remove());
}
function renderTableResizeHandles(page) {
  clearTableResizeHandles(page);
  tableGroups(page).forEach((cells, tableIndex) => {
    const bounds = tableBounds(cells);
    if (!bounds || bounds.width < 3 || bounds.height < 3) return;
    const verticals = uniqueSorted(cells.flatMap(el => {
      const r = fieldRectPct(el);
      return [r.left, r.left + r.width];
    }));
    const horizontals = uniqueSorted(cells.flatMap(el => {
      const r = fieldRectPct(el);
      const offset = tableOffsetPctForElement(el);
      return [r.top + offset, r.top + offset + r.height];
    }));
    verticals
      .filter(x => x > bounds.left + 0.4 && x < bounds.right - 0.4)
      .forEach(x => {
        const handle = document.createElement('div');
        handle.className = 'table-resize-handle col';
        handle.dataset.resizeTableIndex = String(tableIndex);
        handle.dataset.axis = 'col';
        handle.dataset.boundary = String(x);
        handle.style.left = x + '%';
        handle.style.top = bounds.top + '%';
        handle.style.height = bounds.height + '%';
        handle.addEventListener('pointerdown', startTableResize);
        page.appendChild(handle);
      });
    horizontals
      .filter(y => y > bounds.top + 0.35 && y < bounds.bottom - 0.35)
      .forEach(y => {
        const handle = document.createElement('div');
        handle.className = 'table-resize-handle row';
        handle.dataset.resizeTableIndex = String(tableIndex);
        handle.dataset.axis = 'row';
        handle.dataset.boundary = String(y);
        handle.style.left = bounds.left + '%';
        handle.style.top = y + '%';
        handle.style.width = bounds.width + '%';
        handle.addEventListener('pointerdown', startTableResize);
        page.appendChild(handle);
      });
  });
}
function positionTableResizeHandles(page) {
  if (!page || tableResizeState) return;
  renderTableResizeHandles(page);
}
function saveFieldLayoutsBatch(fields) {
  const unique = Array.from(new Set(fields)).filter(el => el && el.dataset && el.dataset.label);
  if (!unique.length) return Promise.resolve();
  const layouts = unique.map(el => ({ label: el.dataset.label || '', layout: fieldLayout(el) }));
  const fd = new FormData();
  fd.append('id', INSTANCE_ID);
  fd.append('layouts', JSON.stringify(layouts));
  return fetch(SAVE_FIELD_LAYOUTS_URL, { method: 'POST', body: fd })
    .then(() => { status(unique.length + '개 칸 크기 저장됨'); parent.postMessage({type:'wiz-direct-editor-saved'}, '*'); parent.postMessage({type:'wiz-refresh-preview'}, '*'); })
    .catch(() => status('표 칸 크기 저장 실패'));
}
function pctRectFromEl(el) {
  return {
    left: parseFloat(el.style.left) || 0,
    top: parseFloat(el.style.top) || 0,
    width: parseFloat(el.style.width) || 0,
    height: parseFloat(el.style.height) || 0
  };
}
function pctOverlap(a, b) {
  return !(a.left + a.width <= b.left || b.left + b.width <= a.left || a.top + a.height <= b.top || b.top + b.height <= a.top);
}
function avoidFieldImageOverlap(pageEl) {
  const images = Array.from(pageEl.querySelectorAll('.abs-img')).map(pctRectFromEl);
  if (!images.length) return;
  Array.from(pageEl.querySelectorAll('.field')).forEach(field => {
    const f = pctRectFromEl(field);
    const blockers = images.filter(img => pctOverlap(f, img) && img.top > f.top + 2);
    if (!blockers.length) return;
    const firstImageTop = Math.min(...blockers.map(img => img.top));
    const newHeight = Math.max(4, firstImageTop - f.top - 0.8);
    if (newHeight < f.height) field.style.height = newHeight + '%';
  });
}
function rectsIntersect(a, b) {
  return !(a.right < b.left || a.left > b.right || a.bottom < b.top || a.top > b.bottom);
}
function startFieldMarquee(ev) {
  if (ev.target.closest('.abs-img') || ev.target.closest('.custom-box') || ev.target.closest('.table-gap') || ev.target.closest('.table-resize-handle')) return;
  if (ev.target.classList.contains('field')) return;
  const page = ev.currentTarget;
  const rect = page.getBoundingClientRect();
  const marker = document.createElement('div');
  marker.className = 'selection-rect';
  page.appendChild(marker);
  selectDrag = {
    page,
    marker,
    rect,
    startX: ev.clientX,
    startY: ev.clientY
  };
  clearSelection();
  ev.preventDefault();
}
function renderCustomOverlay(item) {
  const box = document.createElement('div');
  const kind = 'text';
  box.className = 'custom-box custom-text';
  box.dataset.kind = 'custom';
  box.dataset.type = kind;
  box.dataset.overlayId = item.id || uid();
  box.dataset.page = item.page || 1;
  box.dataset.style = JSON.stringify(item.style || {});
  box.style.left = (Number(item.left) || 8) + '%';
  box.style.top = (Number(item.top) || 8) + '%';
  box.style.width = (Number(item.width) || 28) + '%';
  box.style.height = (Number(item.height) || 8) + '%';
  if (kind === 'text') {
    const area = document.createElement('textarea');
    area.value = item.text || '';
    area.placeholder = '텍스트 입력';
    area.addEventListener('focus', () => selectBox(box));
    area.addEventListener('input', scheduleOverlaySave);
    box.appendChild(area);
    applyCustomBoxStyle(box);
  }
  const resize = document.createElement('div');
  resize.className = 'resize';
  box.appendChild(resize);
  box.addEventListener('pointerdown', startBoxDrag);
  box.addEventListener('click', ev => { selectBox(box); ev.stopPropagation(); });
  return box;
}
function renderTableGap(gap) {
  const box = document.createElement('div');
  box.className = 'table-gap';
  box.dataset.kind = 'table-gap';
  box.dataset.spacingId = gap.id || '';
  box.dataset.page = gap.page || 1;
  box.dataset.beforeTable = gap.before_table || 0;
  box.dataset.afterTable = gap.after_table || 0;
  box.dataset.docxBeforeTable = gap.docx_before_table || 0;
  box.dataset.baseHeight = gap.base_height || gap.height || 0;
  box.dataset.pageHeightPt = gap.page_height_pt || 0;
  box.dataset.pageBreak = gap.page_break ? '1' : '0';
  box.dataset.label = gap.label || (gap.before_table ? gap.before_table + '번째 표 앞' : '표 앞');
  box.dataset.baseTop = String(gap.top || 0);
  box.style.left = gap.left + '%';
  box.style.top = gap.top + '%';
  box.style.width = gap.width + '%';
  box.style.height = gap.height + '%';
  if (gap.page_break) box.classList.add('page-break');
  box.innerHTML = '<div class="gap-resize"></div>';
  box.addEventListener('pointerdown', startGapDrag);
  box.addEventListener('click', ev => { selectGap(box); ev.stopPropagation(); });
  return box;
}
function renderAbsImage(img) {
  const box = document.createElement('div');
  box.className = 'abs-img';
  box.dataset.kind = 'image';
  box.dataset.filename = img.filename;
  box.dataset.page = img.page || 1;
  box.style.left = img.left + '%';
  box.style.top = img.top + '%';
  box.style.width = img.width + '%';
  box.style.height = img.height + '%';
  box.innerHTML = `<img src="${img.data_uri}" alt=""><div class="resize"></div>`;
  box.addEventListener('pointerdown', startBoxDrag);
  box.addEventListener('click', ev => { selectBox(box); ev.stopPropagation(); });
  return box;
}
function boxPct(box) {
  return {
    page: Number(box.dataset.page || 1),
    left: parseFloat(box.style.left) || 0,
    top: parseFloat(box.style.top) || 0,
    width: parseFloat(box.style.width) || 20,
    height: parseFloat(box.style.height) || 20
  };
}
function imagePct(box) {
  const pct = boxPct(box);
  return { page: pct.page, x_pct: pct.left, y_pct: pct.top, w_pct: pct.width, h_pct: pct.height };
}
function saveImageBox(box) {
  const pct = imagePct(box);
  const fd = new FormData();
  fd.append('instance_id', INSTANCE_ID);
  fd.append('filename', box.dataset.filename || '');
  fd.append('position', '__absolute__');
  fd.append('insert_mode', 'absolute');
  fd.append('page', pct.page);
  fd.append('x_pct', pct.x_pct);
  fd.append('y_pct', pct.y_pct);
  fd.append('w_pct', pct.w_pct);
  fd.append('h_pct', pct.h_pct);
  fetch(SAVE_IMAGE_URL, { method: 'POST', body: fd })
    .then(res => res.json().catch(() => ({})).then(body => {
      if (!res.ok || body.code >= 400) throw new Error(body?.data?.message || 'save failed');
      status('이미지 위치 저장됨');
      parent.postMessage({type:'wiz-direct-editor-saved'}, '*');
    }))
    .catch(() => status('이미지 위치 저장 실패'));
}
function serializeOverlays() {
  return Array.from(document.querySelectorAll('.custom-box')).map(box => {
    const pct = boxPct(box);
    const area = box.querySelector('textarea');
    return {
      id: box.dataset.overlayId || uid(),
      type: 'text',
      page: pct.page,
      left: pct.left,
      top: pct.top,
      width: pct.width,
      height: pct.height,
      text: area ? area.value : '',
      style: styleOf(box),
      border: false
    };
  });
}
function saveOverlays() {
  clearTimeout(overlayTimer);
  const fd = new FormData();
  fd.append('id', INSTANCE_ID);
  fd.append('overlays', JSON.stringify(serializeOverlays()));
  return fetch(SAVE_OVERLAYS_URL, { method: 'POST', body: fd })
    .then(() => { status('자유 배치 저장됨'); parent.postMessage({type:'wiz-direct-editor-saved'}, '*'); })
    .catch(() => status('자유 배치 저장 실패'));
}
function scheduleOverlaySave() {
  clearTimeout(overlayTimer);
  overlayTimer = setTimeout(saveOverlays, 420);
}
function updateGapButtons() {
  const pageBreakBtn = document.getElementById('pageBreakBtn');
  const resetGapBtn = document.getElementById('resetGapBtn');
  const gapPanel = document.getElementById('gapPanel');
  const gapMm = document.getElementById('gapMm');
  if (!pageBreakBtn || !resetGapBtn) return;
  const hasGap = !!selectedGap;
  pageBreakBtn.disabled = !hasGap;
  resetGapBtn.disabled = !hasGap;
  pageBreakBtn.classList.toggle('active', hasGap && selectedGap.dataset.pageBreak === '1');
  if (gapPanel) gapPanel.classList.toggle('active', hasGap);
  if (gapMm && hasGap) {
    const pageHeightPt = parseFloat(selectedGap.dataset.pageHeightPt) || 0;
    const extraPt = pageHeightPt ? pageHeightPt * gapExtraPct(selectedGap) / 100 : 0;
    gapMm.value = (extraPt * 0.352777778).toFixed(1);
  }
}
function setSelectedGapExtraMm(mm, shouldSave) {
  if (!selectedGap) return;
  const pageHeightPt = parseFloat(selectedGap.dataset.pageHeightPt) || 0;
  const baseHeight = parseFloat(selectedGap.dataset.baseHeight) || 0.8;
  const extraPt = Math.max(0, Math.min(226.8, Number(mm || 0) / 0.352777778));
  const extraPct = pageHeightPt ? extraPt / pageHeightPt * 100 : 0;
  selectedGap.style.height = Math.max(0.6, Math.min(45, baseHeight + extraPct)) + '%';
  applyTableLayoutOffsets();
  updateGapButtons();
  if (shouldSave) saveTableGap(selectedGap);
}
function nudgeSelectedGap(deltaMm) {
  if (!selectedGap) {
    status('먼저 표 앞 간격 영역을 선택하세요.');
    return;
  }
  const gapMm = document.getElementById('gapMm');
  const current = parseFloat(gapMm?.value || '0') || 0;
  setSelectedGapExtraMm(Math.max(0, current + deltaMm), true);
}
function saveTableGap(box) {
  const baseHeight = parseFloat(box.dataset.baseHeight) || 0;
  const pageHeightPt = parseFloat(box.dataset.pageHeightPt) || 0;
  const extraPct = Math.max(0, gapExtraPct(box));
  const fd = new FormData();
  fd.append('id', INSTANCE_ID);
  fd.append('spacing_id', box.dataset.spacingId || '');
  fd.append('page', box.dataset.page || '1');
  fd.append('before_table', box.dataset.beforeTable || '0');
  fd.append('after_table', box.dataset.afterTable || '0');
  fd.append('docx_before_table', box.dataset.docxBeforeTable || '0');
  fd.append('extra_pct', extraPct);
  fd.append('extra_pt', pageHeightPt ? pageHeightPt * extraPct / 100 : 0);
  fd.append('page_break', box.dataset.pageBreak === '1' ? '1' : '0');
  return fetch(SAVE_TABLE_SPACING_URL, { method: 'POST', body: fd })
    .then(() => { status('표 레이아웃 저장됨'); parent.postMessage({type:'wiz-direct-editor-saved'}, '*'); parent.postMessage({type:'wiz-refresh-preview'}, '*'); })
    .catch(() => status('표 간격 저장 실패'));
}
function toggleSelectedGapPageBreak() {
  if (!selectedGap) {
    status('먼저 표 앞 간격 영역을 선택하세요.');
    return;
  }
  const next = selectedGap.dataset.pageBreak === '1' ? '0' : '1';
  selectedGap.dataset.pageBreak = next;
  selectedGap.classList.toggle('page-break', next === '1');
  updateGapButtons();
  saveTableGap(selectedGap);
}
function resetSelectedGap() {
  if (!selectedGap) {
    status('먼저 표 앞 간격 영역을 선택하세요.');
    return;
  }
  selectedGap.dataset.pageBreak = '0';
  selectedGap.classList.remove('page-break');
  selectedGap.style.height = (parseFloat(selectedGap.dataset.baseHeight) || 0.8) + '%';
  applyTableLayoutOffsets();
  updateGapButtons();
  saveTableGap(selectedGap);
}
function startTableResize(ev) {
  const handle = ev.currentTarget;
  const page = handle.closest('.page');
  const tableIndex = Number(handle.dataset.resizeTableIndex || 0);
  const axis = handle.dataset.axis || '';
  const boundary = Number(handle.dataset.boundary || 0);
  if (!page || !tableIndex || !axis || !Number.isFinite(boundary)) return;
  clearSelection();
  const cells = tableCells(page, tableIndex);
  const epsilon = 0.36;
  const snapshots = cells.map(el => {
    const rect = fieldRectPct(el);
    const offset = tableOffsetPctForElement(el);
    return {
      el,
      left: rect.left,
      top: rect.top,
      visualTop: rect.top + offset,
      width: rect.width,
      height: rect.height,
      right: rect.left + rect.width,
      bottom: rect.top + offset + rect.height,
      offset
    };
  });
  const affected = snapshots.filter(item => {
    if (axis === 'col') {
      return Math.abs(item.right - boundary) <= epsilon || Math.abs(item.left - boundary) <= epsilon;
    }
    return Math.abs(item.bottom - boundary) <= epsilon || Math.abs(item.visualTop - boundary) <= epsilon;
  });
  if (!affected.length) return;
  tableResizeState = {
    handle,
    page,
    tableIndex,
    axis,
    boundary,
    startX: ev.clientX,
    startY: ev.clientY,
    pageRect: page.getBoundingClientRect(),
    snapshots,
    changed: new Set()
  };
  handle.classList.add('active');
  try { handle.setPointerCapture(ev.pointerId); } catch (_) {}
  status(axis === 'col' ? '열 너비 조절 중' : '행 높이 조절 중');
  ev.preventDefault();
  ev.stopPropagation();
}
function resizeTableBoundary(ev) {
  const state = tableResizeState;
  if (!state || !state.pageRect.width || !state.pageRect.height) return;
  const rawDelta = state.axis === 'col'
    ? (ev.clientX - state.startX) / state.pageRect.width * 100
    : (ev.clientY - state.startY) / state.pageRect.height * 100;
  const minSize = state.axis === 'col' ? 1.4 : 0.9;
  let minDelta = -40;
  let maxDelta = 40;
  state.snapshots.forEach(item => {
    if (state.axis === 'col') {
      if (Math.abs(item.right - state.boundary) <= 0.36) {
        minDelta = Math.max(minDelta, minSize - item.width);
      }
      if (Math.abs(item.left - state.boundary) <= 0.36) {
        maxDelta = Math.min(maxDelta, item.width - minSize);
      }
    } else {
      if (Math.abs(item.bottom - state.boundary) <= 0.36) {
        minDelta = Math.max(minDelta, minSize - item.height);
      }
      if (Math.abs(item.visualTop - state.boundary) <= 0.36) {
        maxDelta = Math.min(maxDelta, item.height - minSize);
      }
    }
  });
  const delta = Math.max(minDelta, Math.min(maxDelta, rawDelta));
  state.snapshots.forEach(item => {
    const rect = { left: item.left, top: item.top, width: item.width, height: item.height };
    let changed = false;
    if (state.axis === 'col') {
      if (Math.abs(item.right - state.boundary) <= 0.36) {
        rect.width = item.width + delta;
        changed = true;
      }
      if (Math.abs(item.left - state.boundary) <= 0.36) {
        rect.left = item.left + delta;
        rect.width = item.width - delta;
        changed = true;
      }
    } else {
      if (Math.abs(item.bottom - state.boundary) <= 0.36) {
        rect.height = item.height + delta;
        changed = true;
      }
      if (Math.abs(item.visualTop - state.boundary) <= 0.36) {
        rect.top = item.top + delta;
        rect.height = item.height - delta;
        changed = true;
      }
    }
    if (changed) {
      setFieldRectPct(item.el, rect);
      state.changed.add(item.el);
    }
  });
}
function finishTableResize() {
  const state = tableResizeState;
  if (!state) return;
  state.handle.classList.remove('active');
  const changed = Array.from(state.changed);
  tableResizeState = null;
  renderTableResizeHandles(state.page);
  if (changed.length) saveFieldLayoutsBatch(changed);
}
function startGapDrag(ev) {
  const box = ev.currentTarget;
  selectGap(box);
  const page = box.closest('.page');
  const rect = page.getBoundingClientRect();
  gapState = {
    box,
    page,
    rect,
    startY: ev.clientY,
    height: parseFloat(box.style.height) || 1,
    top: parseFloat(box.style.top) || 0
  };
  box.setPointerCapture(ev.pointerId);
  ev.preventDefault();
}
function startBoxDrag(ev) {
  const box = ev.currentTarget;
  selectBox(box);
  if (ev.target.tagName === 'TEXTAREA') return;
  const page = box.closest('.page');
  const resizing = ev.target.classList.contains('resize');
  const rect = page.getBoundingClientRect();
  dragState = {
    box, page, resizing, rect,
    startX: ev.clientX, startY: ev.clientY,
    left: parseFloat(box.style.left) || 0,
    top: parseFloat(box.style.top) || 0,
    width: parseFloat(box.style.width) || 20,
    height: parseFloat(box.style.height) || 20
  };
  box.setPointerCapture(ev.pointerId);
  ev.preventDefault();
}
document.addEventListener('pointermove', ev => {
  if (tableResizeState) {
    resizeTableBoundary(ev);
    return;
  }
  if (selectDrag) {
    const x1 = Math.min(selectDrag.startX, ev.clientX) - selectDrag.rect.left;
    const y1 = Math.min(selectDrag.startY, ev.clientY) - selectDrag.rect.top;
    const x2 = Math.max(selectDrag.startX, ev.clientX) - selectDrag.rect.left;
    const y2 = Math.max(selectDrag.startY, ev.clientY) - selectDrag.rect.top;
    selectDrag.marker.style.left = x1 + 'px';
    selectDrag.marker.style.top = y1 + 'px';
    selectDrag.marker.style.width = Math.max(1, x2 - x1) + 'px';
    selectDrag.marker.style.height = Math.max(1, y2 - y1) + 'px';
    return;
  }
  if (gapState) {
    const dy = (ev.clientY - gapState.startY) / gapState.rect.height * 100;
    gapState.box.style.height = Math.max(0.6, Math.min(45, gapState.height + dy)) + '%';
    applyTableLayoutOffsets();
    updateGapButtons();
    return;
  }
  if (!dragState) return;
  const dx = (ev.clientX - dragState.startX) / dragState.rect.width * 100;
  const dy = (ev.clientY - dragState.startY) / dragState.rect.height * 100;
  if (dragState.resizing) {
    dragState.box.style.width = Math.max(1, Math.min(100 - dragState.left, dragState.width + dx)) + '%';
    dragState.box.style.height = Math.max(1, Math.min(100 - dragState.top, dragState.height + dy)) + '%';
  } else {
    const w = parseFloat(dragState.box.style.width) || dragState.width;
    const h = parseFloat(dragState.box.style.height) || dragState.height;
    dragState.box.style.left = Math.max(0, Math.min(100 - w, dragState.left + dx)) + '%';
    dragState.box.style.top = Math.max(0, Math.min(100 - h, dragState.top + dy)) + '%';
  }
});
document.addEventListener('pointerup', () => {
  if (tableResizeState) {
    finishTableResize();
    return;
  }
  if (gapState) {
    saveTableGap(gapState.box);
    gapState = null;
    return;
  }
  if (selectDrag) {
    const markerRect = selectDrag.marker.getBoundingClientRect();
    const fields = Array.from(selectDrag.page.querySelectorAll('.field'))
      .filter(el => rectsIntersect(markerRect, el.getBoundingClientRect()));
    selectDrag.marker.remove();
    selectDrag = null;
    selectFields(fields);
    return;
  }
  if (activeField) {
    syncFieldGeometry(activeField);
    scheduleSave(activeField);
  }
  if (!dragState) return;
  if (dragState.box.dataset.kind === 'image') saveImageBox(dragState.box);
  else saveOverlays();
  dragState = null;
});
function firstTargetPage() {
  if (selectedBox) return selectedBox.closest('.page') || document.querySelector('.page');
  if (selectedGap) return selectedGap.closest('.page') || document.querySelector('.page');
  return document.querySelector('.page');
}
function fieldTextDensity(field) {
  const value = String(field.value || '').trim();
  const capacity = Math.max(80, (Number(field.width) || 20) * (Number(field.height) || 8) * 7);
  return Math.min(1, value.length / capacity);
}
function imageTargetScore(field) {
  const label = String(field.label || '');
  let score = 0;
  if (/사진|이미지|그림|첨부|캡처|활동\\s*사진|얼굴/.test(label)) score += 120;
  if (/세부|활동|내용|본문|보고/.test(label)) score += 35;
  score += Math.min(45, (Number(field.width) || 0) * (Number(field.height) || 0) / 10);
  score -= fieldTextDensity(field) * 22;
  return score;
}
function bestImageTarget() {
  let best = null;
  DATA.pages.forEach(page => {
    (page.fields || []).forEach(field => {
      const score = imageTargetScore(field);
      if (!best || score > best.score) best = { page, field, score };
    });
  });
  if (best && best.score >= 35) return best;

  let fallback = null;
  DATA.pages.forEach(page => {
    (page.fields || []).forEach(field => {
      const area = (Number(field.width) || 0) * (Number(field.height) || 0);
      if (!fallback || area > fallback.area) fallback = { page, field, area };
    });
  });
  return fallback ? { page: fallback.page, field: fallback.field, score: 0 } : null;
}
function smartImagePlacement() {
  const target = bestImageTarget();
  if (target && target.field) {
    const f = target.field;
    const density = fieldTextDensity(f);
    const padX = Math.min(2, Math.max(0.8, Number(f.width) * 0.04));
    const padY = Math.min(1.2, Math.max(0.6, Number(f.height) * 0.04));
    let height = Math.max(10, Math.min(24, Number(f.height) * (density > 0.5 ? 0.42 : 0.52)));
    let width = Math.max(18, Math.min(Number(f.width) - padX * 2, height * 1.55));
    if (width > Number(f.width) - padX * 2) {
      width = Math.max(12, Number(f.width) - padX * 2);
      height = Math.max(8, Math.min(height, width / 1.45));
    }
    return {
      page: Number(target.page.number || 1),
      left: Number(f.left) + (Number(f.width) - width) / 2,
      top: Number(f.top) + Math.max(padY, Number(f.height) - height - padY),
      width,
      height
    };
  }
  const page = firstTargetPage();
  return { page: Number(page?.dataset?.page || 1), left: 12, top: 62, width: 42, height: 24 };
}
function addOverlay(type) {
  const page = firstTargetPage();
  if (!page) return;
  const item = {
    id: uid(),
    type: 'text',
    page: Number(page.dataset.page || 1),
    left: 10,
    top: 10,
    width: 34,
    height: 9,
    text: '',
    style: readToolbar()
  };
  const box = renderCustomOverlay(item);
  page.appendChild(box);
  selectBox(box);
  saveOverlays();
  const area = box.querySelector('textarea');
  if (area) area.focus();
}
function deleteSelected() {
  if (!selectedBox) {
    status('삭제할 이미지나 자유 박스를 먼저 선택하세요.');
    return;
  }
  const box = selectedBox;
  selectedBox = null;
  if (box.dataset.kind === 'image') {
    const fd = new FormData();
    fd.append('instance_id', INSTANCE_ID);
    fd.append('filename', box.dataset.filename || '');
    fd.append('position', '__absolute__');
    fetch(REMOVE_IMAGE_URL, { method: 'POST', body: fd })
      .then(() => { box.remove(); status('이미지 배치 삭제됨'); parent.postMessage({type:'wiz-direct-editor-saved'}, '*'); })
      .catch(() => status('이미지 배치 삭제 실패'));
    return;
  }
  box.remove();
  saveOverlays();
}
function renderImages() {
  const list = document.getElementById('imageList');
  list.innerHTML = '';
  if (!DATA.images.length) {
    list.innerHTML = '<div style="font-size:12px;color:#6b7280;">업로드된 이미지가 없습니다.</div>';
    return;
  }
  DATA.images.forEach(img => {
    const item = document.createElement('div');
    item.className = 'image-item';
    item.innerHTML = `<img src="${img.data_uri}" alt=""><div class="image-name">${img.filename}</div><button type="button">알맞은 위치에 넣기</button>`;
    item.querySelector('button').addEventListener('click', () => placeImageSmart(img));
    list.appendChild(item);
  });
}
function findPageByNumber(pageNumber) {
  return Array.from(document.querySelectorAll('.page')).find(page => Number(page.dataset.page || 1) === Number(pageNumber || 1)) || firstTargetPage();
}
function placeImageSmart(img) {
  const placement = smartImagePlacement();
  const page = findPageByNumber(placement.page);
  if (!page) return;
  const box = renderAbsImage({
    filename: img.filename,
    data_uri: img.data_uri,
    page: Number(page.dataset.page || placement.page || 1),
    left: Math.max(0, Math.min(95, placement.left)),
    top: Math.max(0, Math.min(95, placement.top)),
    width: Math.max(1, Math.min(100, placement.width)),
    height: Math.max(1, Math.min(100, placement.height))
  });
  page.appendChild(box);
  selectBox(box);
  saveImageBox(box);
}
document.getElementById('fontFamily').addEventListener('change', toolbarChanged);
document.getElementById('fontSize').addEventListener('input', toolbarChanged);
document.getElementById('fontColor').addEventListener('input', toolbarChanged);
document.getElementById('boldBtn').addEventListener('click', ev => { ev.currentTarget.classList.toggle('active'); toolbarChanged(); });
document.querySelectorAll('[data-align]').forEach(btn => btn.addEventListener('click', ev => { activeAlign = ev.currentTarget.dataset.align; writeToolbar(readToolbar()); toolbarChanged(); }));
document.getElementById('addTextBtn').addEventListener('click', () => addOverlay('text'));
document.getElementById('deleteBtn').addEventListener('click', deleteSelected);
document.getElementById('gapMm').addEventListener('input', ev => setSelectedGapExtraMm(ev.currentTarget.value, false));
document.getElementById('gapMm').addEventListener('change', ev => setSelectedGapExtraMm(ev.currentTarget.value, true));
document.getElementById('gapMinusBtn').addEventListener('click', () => nudgeSelectedGap(-5));
document.getElementById('gapPlusBtn').addEventListener('click', () => nudgeSelectedGap(5));
document.getElementById('pageBreakBtn').addEventListener('click', toggleSelectedGapPageBreak);
document.getElementById('resetGapBtn').addEventListener('click', resetSelectedGap);
document.getElementById('reloadBtn').addEventListener('click', () => parent.postMessage({type:'wiz-refresh-preview'}, '*'));
document.getElementById('pages').addEventListener('click', () => {
  if (selectedFields.size) return;
  selectedBox = null;
  clearSelection();
});
writeToolbar({});
renderPages();
renderImages();
updateGapButtons();
</script>
</body>
</html>"""
        return (
            html_doc
            .replace('__TITLE__', title_html)
            .replace('__INSTANCE_JSON__', instance_json)
            .replace('__DATA_JSON__', data_json)
            .replace('__POST_MESSAGE_GUARD__', self._post_message_origin_guard_script())
        )

    def _render_direct_editor_html(self, instance_id, editor_data):
        data_json = json.dumps(editor_data, ensure_ascii=False)
        instance_json = json.dumps(instance_id, ensure_ascii=False)
        return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{self._post_message_origin_guard_script()}
<style>
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: #f3f4f6; color: #111827; font-family: Arial, "Malgun Gothic", sans-serif; }}
.app {{ min-height: 100vh; display: grid; grid-template-columns: 1fr 280px; }}
.pages {{ padding: 24px; overflow: auto; }}
.page {{ position: relative; margin: 0 auto 24px; background: white; box-shadow: 0 18px 44px rgba(15,23,42,.14); }}
.page-bg {{ display: block; width: 100%; height: auto; user-select: none; pointer-events: none; }}
.field {{ position: absolute; border: 1px solid transparent; background: transparent; color: #080808; padding: 3px 5px; resize: none; overflow: hidden; outline: none; line-height: 1.35; }}
.field:hover {{ border-color: rgba(20,110,245,.45); background: rgba(255,255,255,.08); }}
.field:focus {{ border-color: #146ef5; background: rgba(255,255,255,.12); box-shadow: 0 0 0 2px rgba(20,110,245,.18); z-index: 5; }}
.abs-img {{ position: absolute; border: 1px solid #146ef5; background: rgba(255,255,255,.35); cursor: move; z-index: 4; }}
.abs-img img {{ width: 100%; height: 100%; object-fit: contain; display: block; pointer-events: none; }}
.resize {{ position: absolute; right: -5px; bottom: -5px; width: 11px; height: 11px; background: #146ef5; border: 2px solid white; cursor: nwse-resize; }}
.side {{ border-left: 1px solid #d8d8d8; background: #fff; padding: 16px; overflow: auto; position: sticky; top: 0; height: 100vh; }}
.eyebrow {{ font-size: 11px; letter-spacing: .8px; text-transform: uppercase; color: #6b7280; margin-bottom: 8px; }}
.title {{ font-size: 16px; font-weight: 600; margin-bottom: 16px; }}
.control {{ margin-bottom: 12px; }}
.control label {{ display: block; font-size: 12px; color: #4b5563; margin-bottom: 5px; }}
select,input[type="number"],input[type="color"] {{ width: 100%; border: 1px solid #d8d8d8; border-radius: 4px; padding: 8px; font-size: 13px; background: #fff; }}
.row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }}
.seg {{ display: flex; gap: 6px; }}
button {{ border: 1px solid #d8d8d8; background: #fff; border-radius: 4px; padding: 8px 10px; font-size: 12px; cursor: pointer; }}
button.active, .primary {{ background: #080808; color: #fff; border-color: #080808; }}
.status {{ min-height: 18px; font-size: 12px; color: #6b7280; margin: 8px 0 16px; }}
.image-list {{ display: grid; gap: 8px; }}
.image-item {{ border: 1px solid #e5e7eb; border-radius: 6px; padding: 8px; }}
.image-item img {{ width: 100%; height: 92px; object-fit: contain; background: #f9fafb; border-radius: 4px; }}
.image-name {{ font-size: 11px; color: #4b5563; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; margin: 6px 0; }}
@media (max-width: 900px) {{ .app {{ grid-template-columns: 1fr; }} .side {{ position: static; height: auto; border-left: 0; border-top: 1px solid #d8d8d8; }} .pages {{ padding: 12px; }} }}
</style>
</head>
<body>
<div class="app">
  <main class="pages" id="pages"></main>
  <aside class="side">
    <div class="eyebrow">Direct Editor</div>
    <div class="title">{html.escape(str(editor_data.get('title', '문서')))}</div>
    <div class="control">
      <label>글꼴</label>
      <select id="fontFamily">
        <option value="gothic">고딕</option>
        <option value="myeongjo">명조</option>
        <option value="batang">바탕</option>
        <option value="mono">고정폭</option>
      </select>
    </div>
    <div class="row">
      <div class="control">
        <label>크기(pt)</label>
        <input id="fontSize" type="number" min="5" max="28" step="0.5" value="9">
      </div>
      <div class="control">
        <label>색상</label>
        <input id="fontColor" type="color" value="#080808">
      </div>
    </div>
    <div class="control">
      <label>정렬/굵기</label>
      <div class="seg">
        <button id="boldBtn" type="button">B</button>
        <button data-align="left" type="button">좌</button>
        <button data-align="center" type="button">중</button>
        <button data-align="right" type="button">우</button>
      </div>
    </div>
    <div class="status" id="status">필드를 클릭해서 바로 수정하세요.</div>
    <button class="primary" type="button" id="reloadBtn">저장된 PDF 새로고침</button>
    <hr style="border:0;border-top:1px solid #e5e7eb;margin:18px 0;">
    <div class="eyebrow">Images</div>
    <div class="image-list" id="imageList"></div>
  </aside>
</div>
<script>
const INSTANCE_ID = {instance_json};
const DATA = {data_json};
const SAVE_FIELD_URL = '/wiz/api/page.doc.write.item/save_field_value';
const SAVE_IMAGE_URL = '/wiz/api/page.doc.write.item/save_image_placement';
let activeField = null;
let activeAlign = 'left';
let dragState = null;

function status(text) {{ document.getElementById('status').textContent = text; }}
function styleOf(el) {{
  try {{ return JSON.parse(el.dataset.style || '{{}}'); }} catch (_) {{ return {{}}; }}
}}
function normalizeStyle(st) {{
  return {{
    font_family: st.font_family || 'gothic',
    font_size: Number(st.font_size || 9),
    bold: !!st.bold,
    align: st.align || 'left',
    color: st.color || '#080808'
  }};
}}
function cssFont(family) {{
  if (family === 'myeongjo' || family === 'batang') return '"Nanum Myeongjo","Batang",serif';
  if (family === 'mono') return '"Nanum Gothic Coding","Consolas",monospace';
  return '"Nanum Gothic","Malgun Gothic",sans-serif';
}}
function applyStyle(el) {{
  const st = normalizeStyle(styleOf(el));
  el.style.fontFamily = cssFont(st.font_family);
  el.style.fontSize = st.font_size + 'pt';
  el.style.fontWeight = st.bold ? '600' : '400';
  el.style.textAlign = st.align;
  el.style.color = st.color;
}}
function readToolbar() {{
  return normalizeStyle({{
    font_family: document.getElementById('fontFamily').value,
    font_size: document.getElementById('fontSize').value,
    bold: document.getElementById('boldBtn').classList.contains('active'),
    align: activeAlign,
    color: document.getElementById('fontColor').value
  }});
}}
function writeToolbar(st) {{
  st = normalizeStyle(st);
  document.getElementById('fontFamily').value = st.font_family;
  document.getElementById('fontSize').value = st.font_size;
  document.getElementById('fontColor').value = st.color;
  document.getElementById('boldBtn').classList.toggle('active', st.bold);
  activeAlign = st.align;
  document.querySelectorAll('[data-align]').forEach(btn => btn.classList.toggle('active', btn.dataset.align === activeAlign));
}}
function saveField(el) {{
  const fd = new FormData();
  fd.append('id', INSTANCE_ID);
  fd.append('label', el.dataset.label || '');
  fd.append('content', el.value || '');
  fd.append('style', el.dataset.style || '{{}}');
  return fetch(SAVE_FIELD_URL, {{ method: 'POST', body: fd }})
    .then(() => {{ status('저장됨: ' + (el.dataset.label || '필드')); parent.postMessage({{type:'wiz-direct-editor-saved'}}, '*'); }})
    .catch(() => status('저장 실패'));
}}
function scheduleSave(el) {{
  clearTimeout(el._saveTimer);
  el._saveTimer = setTimeout(() => saveField(el), 420);
}}
function selectField(el) {{
  activeField = el;
  writeToolbar(styleOf(el));
  status('편집 중: ' + (el.dataset.label || '필드'));
}}
function toolbarChanged() {{
  if (!activeField) return;
  activeField.dataset.style = JSON.stringify(readToolbar());
  applyStyle(activeField);
  scheduleSave(activeField);
}}
function renderPages() {{
  const root = document.getElementById('pages');
  root.innerHTML = '';
  DATA.pages.forEach(page => {{
    const pageEl = document.createElement('section');
    pageEl.className = 'page';
    pageEl.dataset.page = page.number;
    pageEl.style.maxWidth = page.width + 'px';
    pageEl.innerHTML = `<img class="page-bg" src="${{page.background}}" alt="page ${{page.number}}">`;
    page.fields.forEach((field, idx) => {{
      const el = document.createElement('textarea');
      el.className = 'field';
      el.dataset.label = field.label;
      el.dataset.style = JSON.stringify(field.style || {{}});
      el.value = field.value || '';
      el.title = field.label;
      el.style.left = field.left + '%';
      el.style.top = field.top + '%';
      el.style.width = field.width + '%';
      el.style.height = field.height + '%';
      el.addEventListener('focus', () => selectField(el));
      el.addEventListener('input', () => {{
        document.querySelectorAll(`textarea[data-label="${{CSS.escape(field.label)}}"]`).forEach(other => {{
          if (other !== el) other.value = el.value;
        }});
        scheduleSave(el);
      }});
      el.addEventListener('blur', () => saveField(el));
      applyStyle(el);
      pageEl.appendChild(el);
    }});
    (page.absolute_images || []).forEach(img => pageEl.appendChild(renderAbsImage(img)));
    root.appendChild(pageEl);
  }});
}}
function renderAbsImage(img) {{
  const box = document.createElement('div');
  box.className = 'abs-img';
  box.dataset.filename = img.filename;
  box.dataset.page = img.page || 1;
  box.style.left = img.left + '%';
  box.style.top = img.top + '%';
  box.style.width = img.width + '%';
  box.style.height = img.height + '%';
  box.innerHTML = `<img src="${{img.data_uri}}" alt=""><div class="resize"></div>`;
  box.addEventListener('pointerdown', startImageDrag);
  return box;
}}
function imagePct(box) {{
  return {{
    page: Number(box.dataset.page || 1),
    x_pct: parseFloat(box.style.left) || 0,
    y_pct: parseFloat(box.style.top) || 0,
    w_pct: parseFloat(box.style.width) || 20,
    h_pct: parseFloat(box.style.height) || 20
  }};
}}
function saveImageBox(box) {{
  const pct = imagePct(box);
  const fd = new FormData();
  fd.append('instance_id', INSTANCE_ID);
  fd.append('filename', box.dataset.filename || '');
  fd.append('position', '__absolute__');
  fd.append('insert_mode', 'absolute');
  fd.append('page', pct.page);
  fd.append('x_pct', pct.x_pct);
  fd.append('y_pct', pct.y_pct);
  fd.append('w_pct', pct.w_pct);
  fd.append('h_pct', pct.h_pct);
  fetch(SAVE_IMAGE_URL, {{ method: 'POST', body: fd }})
    .then(() => {{ status('이미지 위치 저장됨'); parent.postMessage({{type:'wiz-direct-editor-saved'}}, '*'); }})
    .catch(() => status('이미지 위치 저장 실패'));
}}
function startImageDrag(ev) {{
  const box = ev.currentTarget;
  const page = box.closest('.page');
  const resizing = ev.target.classList.contains('resize');
  const rect = page.getBoundingClientRect();
  dragState = {{
    box, page, resizing, rect,
    startX: ev.clientX, startY: ev.clientY,
    left: parseFloat(box.style.left) || 0,
    top: parseFloat(box.style.top) || 0,
    width: parseFloat(box.style.width) || 20,
    height: parseFloat(box.style.height) || 20
  }};
  box.setPointerCapture(ev.pointerId);
  ev.preventDefault();
}}
document.addEventListener('pointermove', ev => {{
  if (!dragState) return;
  const dx = (ev.clientX - dragState.startX) / dragState.rect.width * 100;
  const dy = (ev.clientY - dragState.startY) / dragState.rect.height * 100;
  if (dragState.resizing) {{
    dragState.box.style.width = Math.max(3, Math.min(100 - dragState.left, dragState.width + dx)) + '%';
    dragState.box.style.height = Math.max(3, Math.min(100 - dragState.top, dragState.height + dy)) + '%';
  }} else {{
    dragState.box.style.left = Math.max(0, Math.min(98, dragState.left + dx)) + '%';
    dragState.box.style.top = Math.max(0, Math.min(98, dragState.top + dy)) + '%';
  }}
}});
document.addEventListener('pointerup', () => {{
  if (!dragState) return;
  saveImageBox(dragState.box);
  dragState = null;
}});
function renderImages() {{
  const list = document.getElementById('imageList');
  list.innerHTML = '';
  if (!DATA.images.length) {{
    list.innerHTML = '<div style="font-size:12px;color:#6b7280;">업로드된 이미지가 없습니다.</div>';
    return;
  }}
  DATA.images.forEach(img => {{
    const item = document.createElement('div');
    item.className = 'image-item';
    item.innerHTML = `<img src="${{img.data_uri}}" alt=""><div class="image-name">${{img.filename}}</div><button type="button">1페이지에 놓기</button>`;
    item.querySelector('button').addEventListener('click', () => placeImageOnFirstPage(img));
    list.appendChild(item);
  }});
}}
function placeImageOnFirstPage(img) {{
  const page = document.querySelector('.page');
  if (!page) return;
  const box = renderAbsImage({{ filename: img.filename, data_uri: img.data_uri, page: Number(page.dataset.page || 1), left: 8, top: 8, width: 30, height: 18 }});
  page.appendChild(box);
  saveImageBox(box);
}}
document.getElementById('fontFamily').addEventListener('change', toolbarChanged);
document.getElementById('fontSize').addEventListener('input', toolbarChanged);
document.getElementById('fontColor').addEventListener('input', toolbarChanged);
document.getElementById('boldBtn').addEventListener('click', ev => {{ ev.currentTarget.classList.toggle('active'); toolbarChanged(); }});
document.querySelectorAll('[data-align]').forEach(btn => btn.addEventListener('click', ev => {{ activeAlign = ev.currentTarget.dataset.align; writeToolbar(readToolbar()); toolbarChanged(); }}));
document.getElementById('reloadBtn').addEventListener('click', () => parent.postMessage({{type:'wiz-refresh-preview'}}, '*'));
writeToolbar({{}});
renderPages();
renderImages();
</script>
</body>
</html>"""

    def _template_error_html(self, message):
        return (
            '<!DOCTYPE html><html><head><meta charset="utf-8">'
            '<style>body{margin:0;background:#f8fafc;font-family:Arial,\"Malgun Gothic\",sans-serif;color:#111827;}'
            '.box{margin:32px auto;padding:20px;max-width:720px;border:1px solid #fecaca;background:#fff1f2;border-radius:8px;}'
            '.title{font-weight:600;margin-bottom:8px;color:#991b1b}.msg{font-size:13px;line-height:1.6;color:#7f1d1d}</style>'
            '</head><body><div class="box"><div class="title">원본 양식 렌더링 실패</div>'
            f'<div class="msg">{self._escape_html(message)}</div></div></body></html>'
        )

    def _build_sections_html(self, instance, sections):
        """섹션 기반 fallback HTML 생성"""
        html_parts = [
            '<!DOCTYPE html>',
            '<html><head><meta charset="utf-8">',
            '<style>',
            'body { font-family: "Malgun Gothic", "맑은 고딕", sans-serif; margin: 40px; font-size: 13px; line-height: 1.7; color: #1a1a1a; }',
            'h1 { font-size: 22px; text-align: center; margin-bottom: 4px; }',
            '.meta { text-align: center; color: #888; font-size: 11px; margin-bottom: 30px; }',
            'h2 { font-size: 15px; border-bottom: 1px solid #ddd; padding-bottom: 4px; margin-top: 24px; }',
            'p { margin: 4px 0; }',
            '</style></head><body>',
        ]
        title = self._escape_html(instance.get('title', '문서'))
        html_parts.append(f'<h1>{title}</h1>')
        meta_parts = []
        if instance.get('week_label'):
            meta_parts.append(f"주차: {instance['week_label']}")
        meta_parts.append(f"생성일: {self._safe_date(instance.get('created'))}")
        html_parts.append(f'<div class="meta">{" | ".join(meta_parts)}</div>')
        for sec in sections:
            sec_title = self._escape_html(sec.get('section_title', ''))
            html_parts.append(f'<h2>{sec_title}</h2>')
            content = sec.get('content', '') or ''
            for line in content.split('\n'):
                line = line.strip()
                if line:
                    html_parts.append(f'<p>{self._escape_html(line)}</p>')
        html_parts.append('</body></html>')
        return '\n'.join(html_parts)

    def _render_docx_file_to_html(self, file_path, instance):
        from docx import Document
        document = Document(file_path)
        html_parts = [
            '<!DOCTYPE html>',
            '<html><head><meta charset="utf-8">',
            '<style>',
            'body { font-family: "Malgun Gothic", "맑은 고딕", sans-serif; margin: 32px; font-size: 13px; line-height: 1.7; color: #1a1a1a; }',
            'p { margin: 4px 0; white-space: pre-wrap; }',
            'table { border-collapse: collapse; width: 100%; margin: 12px 0; }',
            'td, th { border: 1px solid #ddd; padding: 6px 8px; vertical-align: top; }',
            'h1 { font-size: 22px; margin-bottom: 4px; }',
            '.meta { color: #888; font-size: 11px; margin-bottom: 16px; }',
            '</style></head><body>'
        ]
        html_parts.append(f"<h1>{self._escape_html(instance.get('title', '문서'))}</h1>")
        html_parts.append(f"<div class=\"meta\">생성일: {self._escape_html(self._safe_date(instance.get('created')))}</div>")
        for para in document.paragraphs:
            text = (para.text or '').strip()
            if text:
                html_parts.append(f"<p>{self._escape_html(text)}</p>")
        for table in document.tables:
            html_parts.append('<table>')
            for row in table.rows:
                html_parts.append('<tr>')
                for cell in row.cells:
                    html_parts.append(f"<td>{self._escape_html(cell.text or '')}</td>")
                html_parts.append('</tr>')
            html_parts.append('</table>')
        html_parts.append('</body></html>')
        return '\n'.join(html_parts)

    # ─── HWP HTML 미리보기 ────────────────────────────────────
    def _inline_hwp_html_assets(self, html_content, css_content, html_dir):
        """hwp5html 산출물의 상대 이미지/CSS 자원을 단일 HTML 안에 data URI로 포함한다."""
        html_dir_abs = os.path.abspath(html_dir)

        def data_uri(rel_path):
            rel_path = str(rel_path or '').strip().strip('"\'')
            if not rel_path or rel_path.startswith(('data:', 'http://', 'https://', '#')):
                return rel_path
            rel_path = unquote(rel_path)
            abs_path = os.path.abspath(os.path.join(html_dir_abs, rel_path))
            if not abs_path.startswith(html_dir_abs + os.sep) or not os.path.exists(abs_path):
                return rel_path
            try:
                with open(abs_path, 'rb') as f:
                    payload = base64.b64encode(f.read()).decode('ascii')
                mime = mimetypes.guess_type(abs_path)[0] or 'application/octet-stream'
                return f'data:{mime};base64,{payload}'
            except Exception:
                return rel_path

        def css_url_repl(match):
            quote = match.group(1) or ''
            path = match.group(2) or ''
            return f'url({quote}{data_uri(path)}{quote})'

        css_content = re.sub(
            r'url\(\s*([\'"]?)([^\'")]+)\1\s*\)',
            css_url_repl,
            css_content or ''
        )

        def attr_repl(match):
            return f'{match.group(1)}{data_uri(match.group(2))}{match.group(3)}'

        html_content = re.sub(
            r'(<(?:img|image)\b[^>]*(?:src|href)=["\'])([^"\']+)(["\'])',
            attr_repl,
            html_content,
            flags=re.IGNORECASE
        )
        return html_content, css_content

    def _preview_hwp_html(self, instance_id, instance, template_file_path, template_id, embed_assets=False):
        """HWP 템플릿을 hwp5html로 변환 후 값을 채워 HTML 반환 (미리보기용)"""
        tpl_fs = wiz.project.fs("data", "uploads", "templates") if template_id else wiz.project.fs("data", "uploads", "instances")
        actual_path = tpl_fs.abspath(template_file_path)
        if not os.path.exists(actual_path):
            return None

        all_values = self._collect_all_values(instance_id, instance)

        tmpdir = tempfile.mkdtemp()
        try:
            html_dir = os.path.join(tmpdir, 'hwp_html')
            result = subprocess.run(
                ['hwp5html', '--output', html_dir, actual_path],
                capture_output=True, text=True, timeout=120
            )
            if result.returncode != 0:
                return None

            xhtml_path = os.path.join(html_dir, 'index.xhtml')
            if not os.path.exists(xhtml_path):
                return None

            with open(xhtml_path, 'r', encoding='utf-8') as f:
                html_content = f.read()

            css_path = os.path.join(html_dir, 'styles.css')
            css_content = ''
            if os.path.exists(css_path):
                with open(css_path, 'r', encoding='utf-8') as f:
                    css_content = f.read()

            if embed_assets:
                html_content, css_content = self._inline_hwp_html_assets(html_content, css_content, html_dir)

            return self._fill_hwp_html(html_content, css_content, all_values, for_pdf=False, instance_id=instance_id)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    # ─── HWP → HTML → WeasyPrint PDF 생성 ────────────────────
    def _generate_pdf_from_hwp_html(self, instance_id, instance, template_file_path, template_id):
        """HWP 템플릿을 hwp5html로 변환 후 값을 채워 WeasyPrint로 PDF 생성"""
        tpl_fs = wiz.project.fs("data", "uploads", "templates") if template_id else wiz.project.fs("data", "uploads", "instances")
        actual_path = tpl_fs.abspath(template_file_path)
        if not os.path.exists(actual_path):
            return None

        all_values = self._collect_all_values(instance_id, instance)

        tmpdir = tempfile.mkdtemp()
        try:
            html_dir = os.path.join(tmpdir, 'hwp_html')
            result = subprocess.run(
                ['hwp5html', '--output', html_dir, actual_path],
                capture_output=True, text=True, timeout=120
            )
            if result.returncode != 0:
                return None

            xhtml_path = os.path.join(html_dir, 'index.xhtml')
            if not os.path.exists(xhtml_path):
                return None

            with open(xhtml_path, 'r', encoding='utf-8') as f:
                html_content = f.read()

            css_path = os.path.join(html_dir, 'styles.css')
            css_content = ''
            if os.path.exists(css_path):
                with open(css_path, 'r', encoding='utf-8') as f:
                    css_content = f.read()

            filled_html = self._fill_hwp_html(html_content, css_content, all_values, for_pdf=True, instance_id=instance_id)

            from weasyprint import HTML as WeasyHTML
            pdf_bytes = WeasyHTML(string=filled_html, base_url=html_dir).write_pdf()
            return pdf_bytes
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    # ─── HWP HTML 값 채우기 (핵심 로직) ──────────────────────
    def _fill_hwp_html(self, html_content, css_content, all_values, for_pdf=False, instance_id=None):
        """HWP에서 변환된 XHTML 테이블 셀에 AI 생성값을 채운다.
        
        구조: <tr>
            <td class="borderfill-8">라벨</td>
            <td class="borderfill-11">값 (비어있거나 플레이스홀더)</td>
        </tr>
        """
        # 이미지 배치 정보 로드
        image_placements = {}
        if instance_id:
            try:
                image_placements = self.struct.graph_gen.get_placements(instance_id, detailed=True)
            except Exception:
                pass
        # CSS를 인라인으로 합치기
        if css_content:
            html_content = re.sub(
                r'<link\s+rel="stylesheet"\s+href="styles\.css"\s+type="text/css"\s*/?>',
                f'<style type="text/css">{css_content}</style>',
                html_content
            )

        if not all_values and not image_placements:
            return self._apply_hwp_css_fixes(html_content, for_pdf)

        # 모든 <td> 태그를 개별 파싱하여 라벨-값 쌍 처리
        # 테이블 행 단위로 처리: <tr>...</tr>
        def process_row(match):
            row_html = match.group(0)
            
            # 행 내 모든 셀 추출: (td_open, td_content, td_close)
            cells = re.findall(r'(<td[^>]*>)(.*?)(</td>)', row_html, re.DOTALL)
            
            if len(cells) < 2:
                return row_html

            # 첫 번째 셀에서 라벨 텍스트 추출
            label_html = cells[0][1]
            label_text = re.sub(r'<[^>]+>', '', label_html)
            label_text = label_text.replace('&#13;', '').replace('\r', '').replace('\n', ' ').strip()
            # 연속 공백 정리
            label_text = re.sub(r'\s+', ' ', label_text).strip()

            if not label_text or len(label_text) > 80:
                return row_html

            value_html = cells[1][1]
            value_text = re.sub(r'<[^>]+>', '', value_html)
            value_text = value_text.replace('&#13;', '').replace('\r', '').replace('\n', ' ').strip()

            # 라벨에 매칭되는 값 찾기
            fill_value = self._find_value_for_label(label_text, all_values)
            has_placeholder = self._is_hwp_placeholder_text(value_text)
            fill_value_for_image = fill_value

            # 이미지 배치 확인 — 라벨에 해당하는 이미지가 있으면 삽입
            matched_images = self._find_images_for_label(label_text, image_placements, instance_id)
            if matched_images:
                if fill_value_for_image:
                    fill_value_for_image = self._strip_image_attachment_text(fill_value_for_image)

                base_html = value_html
                base_text = value_text
                if fill_value_for_image and (has_placeholder or fill_value_for_image.strip() != value_text.strip()):
                    base_html = self._build_hwp_value_html(fill_value_for_image)
                    base_text = fill_value_for_image

                img_content = self._build_image_cell_content(base_html, base_text, matched_images)
                old_cell = cells[1][0] + cells[1][1] + cells[1][2]
                new_cell = cells[1][0] + img_content + cells[1][2]
                row_html = row_html.replace(old_cell, new_cell, 1)
                return row_html

            if not fill_value:
                return row_html

            # 값 셀을 새 내용으로 교체
            new_cell_content = self._build_hwp_value_html(fill_value)

            old_cell = cells[1][0] + cells[1][1] + cells[1][2]
            new_cell = cells[1][0] + new_cell_content + cells[1][2]
            row_html = row_html.replace(old_cell, new_cell, 1)

            return row_html

        # <tr>...</tr> 패턴 매칭으로 각 행 처리
        filled_html = re.sub(r'<tr>.*?</tr>', process_row, html_content, flags=re.DOTALL)

        return self._apply_hwp_css_fixes(filled_html, for_pdf)

    def _apply_hwp_css_fixes(self, html_content, for_pdf=False):
        """HWP HTML에 CSS 수정 적용 — 원본 A4 레이아웃 유지"""
        # 배경색만 흰색으로 (인쇄/미리보기 공통)
        html_content = html_content.replace('background-color: #eee;', 'background-color: #fff;')

        # <td> 요소의 height만 min-height로 변환 (img, div 등은 유지)
        def _td_height_to_min(match):
            tag = match.group(0)
            if tag.strip().startswith('<td'):
                return re.sub(r'height:\s*([\d.]+mm)', r'min-height: \1', tag)
            return tag
        html_content = re.sub(r'<(?:td|img|div)[^>]*style="[^"]*"[^>]*>', _td_height_to_min, html_content, flags=re.DOTALL)

        # 추가 CSS 삽입 (</style> 직전)
        extra_css = """
/* 셀 내용 오버플로우 방지 */
td { overflow: visible !important; word-break: break-word; vertical-align: top; }
td p { margin: 0; }
.wiz-image-stack { display: block; margin-top: 4px; margin-bottom: 4px; }
.wiz-image-item { display: block; margin-top: 4px; margin-bottom: 4px; }
/* 본문 글꼴 */
body { font-family: "바탕", "Batang", "Malgun Gothic", serif; }
"""
        if for_pdf:
            extra_css += """
/* PDF: 페이지가 넘어갈 때 상/하단 여백을 보장 */
@page { size: A4; margin: 18mm 0 18mm 0; }
body { margin: 0; padding: 0; }
.Paper { border: none !important; box-shadow: none !important; margin: 0 auto !important; }
"""
        else:
            extra_css += """
/* 미리보기: A4 용지 모양 */
body { margin: 0; padding: 20px; background: #f5f5f5; display: flex; justify-content: center; }
.Paper { background: #fff; border: 1px solid #ddd; box-shadow: 0 2px 12px rgba(0,0,0,0.1); }
"""

        # </style> 태그 직전에 추가 CSS 삽입
        html_content = html_content.replace('</style>', extra_css + '</style>', 1)

        # NaN 값 제거
        html_content = html_content.replace('NaNmm', '0mm')

        return html_content

    # ─── 라벨 매칭 ────────────────────────────────────────────
    def _find_images_for_label(self, label, image_placements, instance_id):
        """라벨에 매칭되는 배치 이미지 목록을 반환"""
        if not image_placements or not instance_id:
            return []

        def normalize(text):
            return re.sub(r'[\s\.\:：·\-\_\(\)\（\）必]', '', text.lower())

        clean_label = normalize(label)
        matched_items = []

        for pos, items in image_placements.items():
            clean_pos = normalize(pos)
            if clean_pos == clean_label or clean_pos in clean_label or clean_label in clean_pos:
                if isinstance(items, list):
                    matched_items.extend(items)

        results = []
        for item in matched_items:
            fn = item.get('filename') if isinstance(item, dict) else None
            if not fn:
                continue
            try:
                uri = self.struct.graph_gen.get_image_base64(instance_id, fn)
                if uri:
                    results.append({
                        'filename': fn,
                        'data_uri': uri,
                        'insert_mode': item.get('insert_mode', 'auto') if isinstance(item, dict) else 'auto'
                    })
            except Exception:
                pass
        return results

    def _is_empty_image_placeholder_text(self, text):
        if not text:
            return True
        clean = re.sub(r'\s+', ' ', str(text)).strip()
        if not clean:
            return True
        return bool(
            re.match(r'^[※_x○●□■\-\.·…\u3000\s]+$', clean, re.IGNORECASE)
            or re.match(r'^20\d{2}년\s+xx', clean)
            or re.match(r'^[x\s:~\-]+$', clean, re.IGNORECASE)
        )

    def _is_hwp_placeholder_text(self, text):
        clean = re.sub(r'\s+', ' ', str(text or '')).strip()
        if not clean:
            return True
        if self._is_empty_image_placeholder_text(clean):
            return True
        if '참석자 얼굴' in clean:
            return True
        if clean in {'차수별 모임 주제', '차수별 일정 및 활동 내용을 구체적으로 기술'}:
            return True
        if clean.startswith('※'):
            return True
        if re.match(r'^0+$', clean):
            return True
        if re.match(r'^(0{1,2}[:.]0{1,2})(\s*[~\-]\s*0{1,2}[:.]0{1,2})?$', clean):
            return True
        if re.match(r'^(20\d{2}|0000)[년\./-]\s*(0{1,2}|xx)[월\./-]\s*(0{1,2}|xx)[일]?(\s+[가-힣]{1,3})?(\s+0{1,2}:0{1,2}(\s*[~\-]\s*0{1,2}:0{1,2})?)?$', clean, re.IGNORECASE):
            return True
        if re.match(r'^[0\s:~\-\.]+$', clean):
            return True
        return False

    def _resolve_image_insert_mode(self, existing_text, requested_mode='auto'):
        if requested_mode in ['above', 'below', 'only']:
            return requested_mode

        if self._is_empty_image_placeholder_text(existing_text):
            return 'only'

        clean = re.sub(r'\s+', ' ', str(existing_text or '')).strip()

        # 안내 문구/사진 설명이 있으면 텍스트를 남기고 아래에 사진 배치
        if any(keyword in clean for keyword in ['사진', '이미지', '첨부', '얼굴', '유의', '※', '참석자']):
            return 'below'

        return 'below'

    def _build_image_cell_content(self, existing_html, existing_text, matched_images):
        mode = self._resolve_image_insert_mode(existing_text, matched_images[0].get('insert_mode', 'auto'))
        img_html_parts = []
        image_max_height = self._resolve_image_max_height(existing_text, len(matched_images), mode)
        for item in matched_images:
            img_html_parts.append(
                f'<div class="wiz-image-item"><img src="{item["data_uri"]}" style="width:auto; max-width:100%; height:auto; max-height:{image_max_height}; display:block; margin:2px auto; object-fit:contain;" /></div>'
            )
        image_block = f'<div class="wiz-image-stack">{"".join(img_html_parts)}</div>'

        if mode == 'only':
            return image_block
        if mode == 'above':
            return image_block + existing_html
        return existing_html + image_block

    def _resolve_image_max_height(self, existing_text, image_count=1, mode='auto'):
        if mode == 'only':
            base_mm = 88
        else:
            clean = re.sub(r'\s+', ' ', str(existing_text or '')).strip()
            if len(clean) >= 400:
                base_mm = 42
            elif len(clean) >= 220:
                base_mm = 52
            elif len(clean) >= 120:
                base_mm = 60
            else:
                base_mm = 70
        if image_count >= 2:
            base_mm = min(base_mm, 42)
        return f'{base_mm}mm'

    def _strip_image_attachment_text(self, text):
        lines = []
        for raw_line in str(text or '').split('\n'):
            line = raw_line.strip()
            if not line:
                lines.append('')
                continue
            normalized = re.sub(r'\s+', '', line)
            if '[사진첨부영역]' in normalized or '사진첨부영역' in normalized:
                continue
            if re.match(r'^[-•·]\s*.+\.(png|jpg|jpeg|gif|webp|svg)\b', line, re.IGNORECASE):
                continue
            if '크기 조절 후 삽입' in line or '사진 첨부' in line:
                continue
            lines.append(raw_line)
        cleaned = '\n'.join(lines)
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned).strip()
        return cleaned

    def _build_hwp_value_html(self, value):
        escaped_value = self._escape_html(value)
        lines = escaped_value.split('\n')
        value_paragraphs = '<br/>'.join(lines)
        return f'<p class="Normal parashape-25"><span class="lang-ko charshape-21" style="font-size:9pt;">{value_paragraphs}</span></p>'

    def _find_value_for_label(self, label, values):
        """라벨 텍스트에 매칭되는 값을 찾는다.
        
        HWP 셀 라벨 (예: "팀 명 (멘토 이름)")과 
        섹션에서 파싱된 키 (예: "팀 명 (멘토 이름)")를 매칭.
        """
        if not label or not values:
            return ''

        # 라벨 정규화 함수
        def normalize(text):
            return re.sub(r'[\s\.\:：·\-\_\(\)\（\）]', '', text)

        clean_label = normalize(label)
        label_is_signature = '서명' in clean_label or 'sign' in clean_label.lower()
        label_is_indexed_person = bool(re.search(r'\d+$', clean_label)) and any(
            role in clean_label for role in ['멘티', '튜티', '멘토', '튜터']
        )
        if label_is_signature:
            return ''

        def value_allowed_for_label(value):
            raw = str(value or '').strip()
            if not raw:
                return ''
            if '학번' in clean_label:
                nums = re.findall(r'\d{7,12}', raw)
                return nums[0] if nums else ''
            if ('학과' in clean_label or '학부' in clean_label) and re.fullmatch(r'[가-힣]{2,4}', raw):
                return ''
            return raw

        # 1. 정확 매칭
        if label in values:
            return value_allowed_for_label(values[label])

        # 2. 정규화 매칭
        for key, value in values.items():
            if normalize(key) == clean_label:
                return value_allowed_for_label(value)

        if label_is_indexed_person:
            return ''

        # 3. 포함 매칭 — 라벨이 키에 포함되거나 키가 라벨에 포함
        for key, value in values.items():
            if len(key) >= 2 and len(label) >= 2:
                # 라벨 == 키의 앞부분 또는 키 == 라벨의 앞부분
                if label.startswith(key) or key.startswith(label):
                    return str(value)
                # 정규화 후 포함 관계
                clean_key = normalize(key)
                if clean_label.startswith(clean_key) or clean_key.startswith(clean_label):
                    return str(value)

        # 4. 부분 포함 (짧은 쪽이 긴 쪽의 50% 이상)
        for key, value in values.items():
            if len(key) >= 3 and len(label) >= 3:
                shorter = min(len(label), len(key))
                longer = max(len(label), len(key))
                if shorter >= longer * 0.5 and (key in label or label in key):
                    return str(value)

        # 5. 지시사항 키 매칭 (generated_fields 의 "지시사항: 내용" 패턴)
        for key, value in values.items():
            if ':' in key or '：' in key:
                parts = re.split(r'[:：]', key, maxsplit=1)
                if len(parts) == 2:
                    instruction = parts[1].strip()
                    if len(label) >= 3 and label in instruction:
                        return str(value)

        return ''

    # ─── HWPX 다운로드 (원본 HWP → HWPX 변환 후 표 직접 채움) ─────────────
    def _project_root_path(self):
        return os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))

    def _convert_hwp_to_hwpx_bytes(self, hwp_path):
        if not os.path.exists(hwp_path):
            raise Exception("HWP 원본 파일을 찾을 수 없습니다.")
        npx = shutil.which('npx')
        if not npx:
            raise Exception("HWPX 변환 도구(npx)가 설치되어 있지 않습니다.")

        tmpdir = tempfile.mkdtemp()
        try:
            out_path = os.path.join(tmpdir, 'template.hwpx')
            result = subprocess.run(
                [npx, 'hwpx', 'convert:hwp', hwp_path, out_path],
                cwd=self._project_root_path(),
                capture_output=True,
                text=True,
                timeout=180
            )
            if result.returncode != 0 or not os.path.exists(out_path):
                message = (result.stderr or result.stdout or '변환 결과가 없습니다.').strip()
                raise Exception(f"HWP → HWPX 변환 실패: {message[:500]}")
            with open(out_path, 'rb') as f:
                return f.read()
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def _sanitize_hwpx_text(self, value):
        text = str(value or '')
        return re.sub(r'[\x00-\x08\x09\x0b\x0c\x0d\x0e-\x1f\ufffe\uffff]', '', text)

    def _hwpx_attr(self, elem, name, default=None):
        hp_ns = 'http://www.hancom.co.kr/hwpml/2011/paragraph'
        return elem.get(f'{{{hp_ns}}}{name}') or elem.get(name) or default

    def _hwpx_int_attr(self, elem, name, default=1):
        try:
            return int(self._hwpx_attr(elem, name, default))
        except Exception:
            return default

    def _hwpx_cell_text(self, cell, ns):
        parts = []
        for node in cell.xpath('.//hp:t', namespaces=ns):
            if node.text:
                parts.append(node.text)
        return ''.join(parts).replace('\r', '').strip()

    def _hwpx_cell_span(self, cell):
        row_span = self._hwpx_int_attr(cell, 'rowSpan', 1)
        col_span = self._hwpx_int_attr(cell, 'colSpan', 1)
        span = cell.find('{http://www.hancom.co.kr/hwpml/2011/paragraph}cellSpan')
        if span is not None:
            row_span = self._hwpx_int_attr(span, 'rowSpan', row_span)
            col_span = self._hwpx_int_attr(span, 'colSpan', col_span)
        return max(row_span, 1), max(col_span, 1)

    def _build_hwpx_table_grid(self, table, ns):
        rows = []
        active = {}

        for tr in table.xpath('./hp:tr', namespaces=ns):
            grid_row = []
            next_active = {}

            def set_grid(col, cell):
                while len(grid_row) <= col:
                    grid_row.append(None)
                grid_row[col] = cell

            def consume_active(col):
                if col not in active:
                    return
                remaining, active_cell = active[col]
                set_grid(col, active_cell)
                if remaining - 1 > 0:
                    next_active[col] = (remaining - 1, active_cell)

            col = 0
            for tc in tr.xpath('./hp:tc', namespaces=ns):
                while col in active:
                    consume_active(col)
                    col += 1

                row_span, col_span = self._hwpx_cell_span(tc)
                for offset in range(col_span):
                    set_grid(col + offset, tc)
                    if row_span > 1:
                        next_active[col + offset] = (row_span - 1, tc)
                col += col_span

            max_col = max(active.keys()) if active else -1
            while col <= max_col:
                if col in active:
                    consume_active(col)
                col += 1

            rows.append(grid_row)
            active = next_active

        return rows

    def _set_hwpx_cell_text(self, cell, value):
        from lxml import etree

        hp_ns = 'http://www.hancom.co.kr/hwpml/2011/paragraph'
        hp = f'{{{hp_ns}}}'
        value = self._sanitize_hwpx_text(value)

        sublist = cell.find(f'{hp}subList')
        if sublist is None:
            sublist = etree.SubElement(cell, f'{hp}subList')

        paragraphs = sublist.findall(f'{hp}p')
        if paragraphs:
            paragraph = paragraphs[0]
            for extra in paragraphs[1:]:
                sublist.remove(extra)
        else:
            paragraph = etree.SubElement(sublist, f'{hp}p')
            paragraph.set(f'{hp}paraPrIDRef', '5')
            paragraph.set(f'{hp}styleIDRef', '0')
            paragraph.set(f'{hp}pageBreak', '0')
            paragraph.set(f'{hp}columnBreak', '0')
            paragraph.set(f'{hp}merged', '0')

        first_run = paragraph.find(f'{hp}run')
        char_pr = self._hwpx_attr(first_run, 'charPrIDRef', '0') if first_run is not None else '0'
        for child in list(paragraph):
            if child.tag == f'{hp}run':
                paragraph.remove(child)

        run = etree.Element(f'{hp}run')
        run.set(f'{hp}charPrIDRef', str(char_pr or '0'))
        text_node = etree.SubElement(run, f'{hp}t')
        text_node.text = value
        paragraph.insert(0, run)

    def _write_hwpx_zip_preserving_package(self, zin, section_updates, preview_text):
        """원본 HWPX 패키지 구조를 최대한 보존해서 다시 쓴다.

        Hancom은 HWPX 내부 XML/ZIP 배치에 민감하다. 그래서 메타 파일을 새로 만들지 않고,
        `mimetype`과 실제 수정된 section XML, 미리보기 텍스트만 바꾼다.
        """
        out = io.BytesIO()
        original_names = set(zin.namelist())

        def clone_info(info, *, compress_type=None):
            cloned = zipfile.ZipInfo(info.filename, info.date_time)
            cloned.comment = info.comment
            cloned.extra = info.extra
            cloned.internal_attr = info.internal_attr
            cloned.external_attr = info.external_attr
            cloned.create_system = info.create_system
            cloned.compress_type = info.compress_type if compress_type is None else compress_type
            return cloned

        with zipfile.ZipFile(out, 'w') as zout:
            # HWPX 표준상 mimetype은 첫 번째 엔트리이며 무압축이어야 한다.
            mimetype_info = zipfile.ZipInfo('mimetype')
            mimetype_info.compress_type = zipfile.ZIP_STORED
            zout.writestr(mimetype_info, b'application/hwp+zip')

            for info in zin.infolist():
                if info.filename == 'mimetype':
                    continue
                if info.is_dir():
                    zout.writestr(clone_info(info), b'')
                    continue
                data = section_updates.get(info.filename)
                if data is None:
                    data = zin.read(info.filename)
                if info.filename == 'Preview/PrvText.txt' and preview_text:
                    data = preview_text.encode('utf-8')
                zout.writestr(clone_info(info), data)

            if 'Preview/PrvText.txt' not in original_names and preview_text:
                zout.writestr('Preview/PrvText.txt', preview_text.encode('utf-8'))

        return out.getvalue()

    def _find_hwpx_fill_value(self, label, all_values):
        label = str(label or '').strip()
        if not label or not all_values:
            return ''
        compact_label = re.sub(r'[\s\.\:：·\-\_\(\)\（\）>]', '', label)
        indexed_fill = bool(re.search(r'\d+$', compact_label)) and any(token in compact_label for token in [
            '주제', '진행과정', '활동일자', '활동장소', '참여자', '불참자',
            '멘티', '튜티', '멘토', '튜터'
        ])
        if label in all_values and str(all_values.get(label) or '').strip():
            return str(all_values.get(label) or '')

        def normalize(text):
            return re.sub(r'[\s\.\:：·\-\_\(\)\（\）]', '', str(text or ''))

        clean_label = normalize(label)
        for key, direct_value in all_values.items():
            if normalize(key) == clean_label and str(direct_value or '').strip():
                return str(direct_value or '')

        if indexed_fill:
            return ''

        value = self._find_value_for_label(label, all_values)
        if value:
            return value

        candidates = []
        if '>' in label:
            candidates.append(label.split('>')[-1].strip())
        candidates.append(re.sub(r'\s+\d+$', '', label).strip())
        candidates.append(re.sub(r'\s*\([^)]*\)\s*$', '', label).strip())

        for candidate in candidates:
            if candidate and candidate != label:
                value = self._find_value_for_label(candidate, all_values)
                if value:
                    return value
        return ''

    def _make_hwpx_blank_paragraph(self, page_break=False):
        from lxml import etree

        hp_ns = 'http://www.hancom.co.kr/hwpml/2011/paragraph'
        hp = f'{{{hp_ns}}}'
        p = etree.Element(f'{hp}p')
        p.set(f'{hp}paraPrIDRef', '0')
        p.set(f'{hp}styleIDRef', '0')
        p.set(f'{hp}pageBreak', '1' if page_break else '0')
        p.set(f'{hp}columnBreak', '0')
        p.set(f'{hp}merged', '0')
        run = etree.SubElement(p, f'{hp}run')
        run.set(f'{hp}charPrIDRef', '0')
        etree.SubElement(run, f'{hp}t').text = ''
        return p

    def _apply_hwpx_table_spacing_controls(self, root, table_offset, table_count, table_spacings):
        """직접 편집기 표 간격을 HWPX에도 최소한의 빈 문단/쪽 넘김으로 반영한다."""
        if not isinstance(table_spacings, dict) or not table_spacings or table_count <= 0:
            return 0

        hp_ns = 'http://www.hancom.co.kr/hwpml/2011/paragraph'
        hp_p = f'{{{hp_ns}}}p'
        ns = {'hp': hp_ns}
        controls = {}
        for item in table_spacings.values():
            if not isinstance(item, dict):
                continue
            try:
                before_table = int(item.get('before_table') or 0)
                extra_pt = float(item.get('extra_pt') or 0)
            except Exception:
                continue
            if before_table <= table_offset or before_table > table_offset + table_count:
                continue
            page_break = bool(item.get('page_break', False))
            if extra_pt <= 0 and not page_break:
                continue
            local_idx = before_table - table_offset - 1
            current = controls.setdefault(local_idx, {'extra_pt': 0, 'page_break': False})
            current['extra_pt'] = max(float(current.get('extra_pt') or 0), min(extra_pt, 160))
            current['page_break'] = bool(current.get('page_break') or page_break)

        if not controls:
            return 0

        tables = root.xpath('.//hp:tbl', namespaces=ns)
        inserted = 0
        for local_idx, control in sorted(controls.items(), reverse=True):
            if local_idx < 0 or local_idx >= len(tables):
                continue
            table = tables[local_idx]
            target_p = table
            while target_p is not None and target_p.tag != hp_p:
                target_p = target_p.getparent()
            parent = target_p.getparent() if target_p is not None else None
            if parent is None:
                continue

            paragraphs = []
            if control.get('page_break'):
                paragraphs.append(self._make_hwpx_blank_paragraph(page_break=True))
            extra_pt = float(control.get('extra_pt') or 0)
            blank_count = int(round(extra_pt / 12.0)) if extra_pt >= 4 else 0
            blank_count = max(0, min(12, blank_count))
            paragraphs.extend(self._make_hwpx_blank_paragraph(page_break=False) for _ in range(blank_count))
            if not paragraphs:
                continue

            insert_at = parent.index(target_p)
            for paragraph in paragraphs:
                parent.insert(insert_at, paragraph)
                insert_at += 1
                inserted += 1

        return inserted

    def _apply_hwpx_direct_table_cell_layouts(self, root, table_offset, table_count, field_layouts):
        """직접 편집기에서 조절한 표 내부 셀 크기를 HWPX cellSz로 반영한다."""
        if not isinstance(field_layouts, dict) or not field_layouts or table_count <= 0:
            return 0
        from lxml import etree

        hp_ns = 'http://www.hancom.co.kr/hwpml/2011/paragraph'
        hp = f'{{{hp_ns}}}'
        ns = {'hp': hp_ns}
        by_table = {}
        pattern = re.compile(r'^표\s*(\d+)\s+(\d+)\s*행\s+(\d+)\s*열')
        for label, layout in field_layouts.items():
            if not isinstance(layout, dict):
                continue
            match = pattern.match(str(label or '').strip())
            if not match:
                continue
            try:
                table_idx = int(match.group(1)) - 1
                row_idx = int(match.group(2)) - 1
                col_idx = int(match.group(3)) - 1
                width_pct = float(layout.get('width') or 0)
                height_pct = float(layout.get('height') or 0)
            except Exception:
                continue
            if table_idx < table_offset or table_idx >= table_offset + table_count:
                continue
            if row_idx < 0 or col_idx < 0:
                continue
            by_table.setdefault(table_idx, {})[(row_idx, col_idx)] = {
                'width_pct': max(0, min(100, width_pct)),
                'height_pct': max(0, min(100, height_pct)),
            }

        if not by_table:
            return 0

        def ensure_child(cell, child_name):
            child = cell.find(f'{hp}{child_name}')
            if child is not None:
                return child
            child = etree.Element(f'{hp}{child_name}')
            sublist = cell.find(f'{hp}subList')
            if sublist is not None:
                cell.insert(cell.index(sublist), child)
            else:
                cell.append(child)
            return child

        changed = 0
        tables = root.xpath('.//hp:tbl', namespaces=ns)
        page_width_hwp = 59500
        page_height_hwp = 84200
        for local_idx, table in enumerate(tables):
            table_idx = table_offset + local_idx
            layouts = by_table.get(table_idx)
            if not layouts:
                continue
            grid = self._build_hwpx_table_grid(table, ns)
            touched = set()
            for (row_idx, col_idx), layout in layouts.items():
                if row_idx < 0 or row_idx >= len(grid):
                    continue
                if col_idx < 0 or col_idx >= len(grid[row_idx]):
                    continue
                cell = grid[row_idx][col_idx]
                if cell is None or id(cell) in touched:
                    continue
                touched.add(id(cell))
                cell_sz = ensure_child(cell, 'cellSz')
                width = int(page_width_hwp * float(layout.get('width_pct') or 0) / 100)
                height = int(page_height_hwp * float(layout.get('height_pct') or 0) / 100)
                if width > 0:
                    cell_sz.set(f'{hp}width', str(max(500, min(page_width_hwp, width))))
                if height > 0:
                    cell_sz.set(f'{hp}height', str(max(300, min(page_height_hwp, height))))
                changed += 1
        return changed

    def _fill_hwpx_tables(self, root, table_offset, fields_schema, all_values):
        ns = {'hp': 'http://www.hancom.co.kr/hwpml/2011/paragraph'}
        tables = root.xpath('.//hp:tbl', namespaces=ns)
        fills = fields_schema.get('table_fills', []) if isinstance(fields_schema, dict) else []
        by_table = {}
        for item in fills if isinstance(fills, list) else []:
            if not isinstance(item, dict):
                continue
            try:
                table_idx = int(item.get('table_idx'))
                row_idx = int(item.get('row'))
                col_idx = int(item.get('col'))
            except Exception:
                continue
            label = str(item.get('label') or '').strip()
            value = self._find_hwpx_fill_value(label, all_values)
            if not str(value or '').strip():
                continue
            by_table.setdefault(table_idx, {})[(row_idx, col_idx)] = value

        direct_by_table = {}
        direct_pattern = re.compile(r'^표\s*(\d+)\s+(\d+)\s*행\s+(\d+)\s*열')
        for label, value in (all_values or {}).items():
            match = direct_pattern.match(str(label or '').strip())
            if not match:
                continue
            try:
                table_idx = int(match.group(1)) - 1
                row_idx = int(match.group(2)) - 1
                col_idx = int(match.group(3)) - 1
            except Exception:
                continue
            if table_idx < 0 or row_idx < 0 or col_idx < 0:
                continue
            direct_by_table.setdefault(table_idx, {})[(row_idx, col_idx)] = str(value or '')

        changed = 0
        touched = set()
        tables_with_schema_fills = set(by_table.keys())

        for local_idx, table in enumerate(tables):
            table_idx = table_offset + local_idx
            grid = self._build_hwpx_table_grid(table, ns)
            for (row_idx, col_idx), value in direct_by_table.get(table_idx, {}).items():
                if row_idx < 0 or row_idx >= len(grid):
                    continue
                if col_idx < 0 or col_idx >= len(grid[row_idx]):
                    continue
                cell = grid[row_idx][col_idx]
                if cell is None:
                    continue
                self._set_hwpx_cell_text(cell, value)
                touched.add(id(cell))
                changed += 1

            for (row_idx, col_idx), value in by_table.get(table_idx, {}).items():
                if row_idx < 0 or row_idx >= len(grid):
                    continue
                if col_idx < 0 or col_idx >= len(grid[row_idx]):
                    continue
                cell = grid[row_idx][col_idx]
                if cell is None:
                    continue
                cell_id = id(cell)
                if cell_id in touched:
                    continue
                self._set_hwpx_cell_text(cell, value)
                touched.add(cell_id)
                changed += 1

            changed += self._apply_known_report_hwpx_fills(table, grid, all_values, ns, touched)
            self._trim_known_report_hwpx_rows(table, all_values, ns)

            # Fallback: schema coordinates가 없는 새 양식은 라벨 오른쪽/아래 빈칸을 채운다.
            if table_idx in tables_with_schema_fills:
                continue
            for row_idx, row in enumerate(grid):
                seen_in_row = set()
                for col_idx, cell in enumerate(row):
                    if cell is None or id(cell) in seen_in_row:
                        continue
                    seen_in_row.add(id(cell))
                    label = self._hwpx_cell_text(cell, ns)
                    if not label or len(label) > 90:
                        continue
                    value = self._find_hwpx_fill_value(label, all_values)
                    if not str(value or '').strip():
                        continue

                    _, col_span = self._hwpx_cell_span(cell)
                    target = None
                    target_col = col_idx + col_span
                    if target_col < len(row):
                        target = row[target_col]
                    elif row_idx + 1 < len(grid) and col_idx < len(grid[row_idx + 1]):
                        target = grid[row_idx + 1][col_idx]
                    if target is None or target is cell or id(target) in touched:
                        continue
                    target_text = self._hwpx_cell_text(target, ns)
                    if target_text and not self._is_hwp_placeholder_text(target_text):
                        continue
                    self._set_hwpx_cell_text(target, value)
                    touched.add(id(target))
                    changed += 1

        return changed, len(tables)

    def _apply_known_report_hwpx_fills(self, table, grid, all_values, ns, touched):
        """자주 쓰는 튜터링 보고서 표는 좌표 분석이 한 칸 밀려도 의미 기준으로 보정한다."""
        table_text = ' '.join([
            text.strip() for text in table.xpath('.//hp:t/text()', namespaces=ns)
            if str(text or '').strip()
        ])
        compact_table_text = re.sub(r'\s+', '', table_text)
        changed = 0

        def cell_at(row_idx, col_idx):
            if row_idx < 0 or row_idx >= len(grid):
                return None
            if col_idx < 0 or col_idx >= len(grid[row_idx]):
                return None
            return grid[row_idx][col_idx]

        def set_cell(row_idx, col_idx, value):
            nonlocal changed
            if not str(value or '').strip():
                return
            cell = cell_at(row_idx, col_idx)
            if cell is None:
                return
            self._set_hwpx_cell_text(cell, value)
            touched.add(id(cell))
            changed += 1

        if '튜터링전공' in compact_table_text and '외국어및목적' in compact_table_text:
            goal1 = all_values.get('활동 목표 1') or all_values.get('활동목표 1') or ''
            goal2 = (
                all_values.get('활동 목표 > 활동 목표 2')
                or all_values.get('활동 목표 2')
                or all_values.get('활동목표 2')
                or ''
            )
            goal_parts = [str(v).strip() for v in [goal1, goal2] if str(v or '').strip()]
            goal_text = '\n'.join(goal_parts) or all_values.get('활동 목표') or all_values.get('활동목표') or ''
            set_cell(3, 0, '활동 목표')
            set_cell(4, 0, goal_text)

        if '튜터링진행과정' in compact_table_text:
            for week in range(1, 9):
                base_row = 2 + ((week - 1) * 3)
                subject = all_values.get(f'주제 {week}') or all_values.get(f'주제 {week}(4열)')
                process = all_values.get(f'진행 과정 {week}') or all_values.get(f'진행 과정 {week}(4열)')
                set_cell(base_row, 2, subject)
                set_cell(base_row + 1, 2, process)

        if '활동참여내역' in compact_table_text and '활동일자' in compact_table_text:
            # 기존 분석 데이터가 차수 헤더 때문에 1칸 밀린 경우가 있어 첫 값 존재 여부로 보정한다.
            has_week_one = any(
                str(all_values.get(f'3. 활동 참여내역 > {field} 1') or '').strip()
                for field in ['활동일자', '활동 장소', '참여자', '불참자']
            )
            offset = 0 if has_week_one else 1
            columns = [
                (1, '활동일자'),
                (2, '활동 장소'),
                (3, '참여자'),
                (4, '불참자'),
            ]
            for week in range(1, 9):
                source_idx = week + offset
                for col_idx, field in columns:
                    value = (
                        all_values.get(f'3. 활동 참여내역 > {field} {source_idx}')
                        or all_values.get(f'활동 참여내역 > {field} {source_idx}')
                    )
                    set_cell(week + 1, col_idx, value)

        return changed

    def _hwpx_report_max_week(self, all_values):
        progress_max = 0
        attendance_max = 0
        for week in range(1, 25):
            progress_keys = [
                f'주제 {week}',
                f'진행 과정 {week}',
                f'주제 {week}(4열)',
                f'진행 과정 {week}(4열)',
            ]
            attendance_keys = [
                f'3. 활동 참여내역 > 활동일자 {week}',
                f'3. 활동 참여내역 > 활동 장소 {week}',
                f'3. 활동 참여내역 > 참여자 {week}',
                f'3. 활동 참여내역 > 불참자 {week}',
            ]
            if any(str(all_values.get(key) or '').strip() and not self._is_hwp_placeholder_text(all_values.get(key)) for key in progress_keys):
                progress_max = week
            if any(str(all_values.get(key) or '').strip() and not self._is_hwp_placeholder_text(all_values.get(key)) for key in attendance_keys):
                attendance_max = week
        # 진행 과정이 있는 양식은 그 주차가 기준이다. 참여내역은 이전 생성값이 남아도 진행 과정보다 길게 늘리지 않는다.
        return progress_max or attendance_max

    def _trim_known_report_hwpx_rows(self, table, all_values, ns):
        """중간보고서에서 5~8주차 빈 행이 남지 않도록 HWPX 표 행을 제거한다."""
        max_week = self._hwpx_report_max_week(all_values)
        if max_week <= 0 or max_week >= 8:
            return

        table_text = ' '.join([
            text.strip() for text in table.xpath('.//hp:t/text()', namespaces=ns)
            if str(text or '').strip()
        ])
        compact_table_text = re.sub(r'\s+', '', table_text)
        rows = table.xpath('./hp:tr', namespaces=ns)
        remove_indices = []
        if '튜터링진행과정' in compact_table_text:
            for week in range(max_week + 1, 9):
                base = 2 + ((week - 1) * 3)
                remove_indices.extend([base, base + 1, base + 2])
        elif '활동참여내역' in compact_table_text and '활동일자' in compact_table_text:
            for week in range(max_week + 1, 9):
                remove_indices.append(week + 1)
        else:
            return

        for idx in sorted(set(remove_indices), reverse=True):
            if 0 <= idx < len(rows):
                try:
                    table.remove(rows[idx])
                except Exception:
                    pass
        remaining = len(table.xpath('./hp:tr', namespaces=ns))
        hp_ns = 'http://www.hancom.co.kr/hwpml/2011/paragraph'
        if table.get(f'{{{hp_ns}}}rowCnt') is not None:
            table.set(f'{{{hp_ns}}}rowCnt', str(remaining))
        elif table.get('rowCnt') is not None:
            table.set('rowCnt', str(remaining))

    def _hwpx_compatible_content_hpf(self, archive_names, section_names):
        from lxml import etree

        nsmap = {
            'ha': 'http://www.hancom.co.kr/hwpml/2011/app',
            'hp': 'http://www.hancom.co.kr/hwpml/2011/paragraph',
            'hp10': 'http://www.hancom.co.kr/hwpml/2016/paragraph',
            'hs': 'http://www.hancom.co.kr/hwpml/2011/section',
            'hc': 'http://www.hancom.co.kr/hwpml/2011/core',
            'hh': 'http://www.hancom.co.kr/hwpml/2011/head',
            'hhs': 'http://www.hancom.co.kr/hwpml/2011/history',
            'hm': 'http://www.hancom.co.kr/hwpml/2011/master-page',
            'hpf': 'http://www.hancom.co.kr/schema/2011/hpf',
            'dc': 'http://purl.org/dc/elements/1.1/',
            'opf': 'http://www.idpf.org/2007/opf/',
            'ooxmlchart': 'http://www.hancom.co.kr/hwpml/2016/ooxmlchart',
            'hwpunitchar': 'http://www.hancom.co.kr/hwpml/2016/HwpUnitChar',
            'epub': 'http://www.idpf.org/2007/ops',
            'config': 'urn:oasis:names:tc:opendocument:xmlns:config:1.0',
        }
        opf = f'{{{nsmap["opf"]}}}'
        root = etree.Element(f'{opf}package', nsmap=nsmap)
        root.set('version', '')
        root.set('unique-identifier', '')
        root.set('id', '')

        metadata = etree.SubElement(root, f'{opf}metadata')
        etree.SubElement(metadata, f'{opf}title')
        language = etree.SubElement(metadata, f'{opf}language')
        language.text = 'ko'
        for name, value in [
            ('creator', 'docsai'),
            ('subject', ''),
            ('description', ''),
            ('lastsaveby', 'docsai'),
            ('CreatedDate', ''),
            ('ModifiedDate', ''),
            ('date', ''),
            ('keyword', ''),
        ]:
            meta = etree.SubElement(metadata, f'{opf}meta')
            meta.set('name', name)
            meta.set('content', 'text')
            if value:
                meta.text = value

        manifest = etree.SubElement(root, f'{opf}manifest')
        items = [('header', 'Contents/header.xml', 'application/xml')]
        for idx, name in enumerate(section_names):
            items.append((f'section{idx}', name, 'application/xml'))
        if 'settings.xml' in archive_names:
            items.append(('settings', 'settings.xml', 'application/xml'))
        if 'version.xml' in archive_names:
            items.append(('version', 'version.xml', 'application/xml'))
        for name in archive_names:
            if name.startswith('BinData/') and not name.endswith('/'):
                item_id = os.path.splitext(os.path.basename(name))[0]
                mime = mimetypes.guess_type(name)[0] or 'application/octet-stream'
                items.append((item_id, name, mime))

        seen = set()
        for item_id, href, media_type in items:
            if item_id in seen or href not in archive_names:
                continue
            seen.add(item_id)
            item = etree.SubElement(manifest, f'{opf}item')
            item.set('id', item_id)
            item.set('href', href)
            item.set('media-type', media_type)

        spine = etree.SubElement(root, f'{opf}spine')
        for item_id in ['header'] + [f'section{idx}' for idx in range(len(section_names))]:
            if item_id not in seen:
                continue
            itemref = etree.SubElement(spine, f'{opf}itemref')
            itemref.set('idref', item_id)
            itemref.set('linear', 'yes')

        return etree.tostring(root, encoding='UTF-8', xml_declaration=True, standalone=True)

    def _hwpx_compatible_container_xml(self):
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>'
            '<ocf:container xmlns:ocf="urn:oasis:names:tc:opendocument:xmlns:container" '
            'xmlns:hpf="http://www.hancom.co.kr/schema/2011/hpf">'
            '<ocf:rootfiles>'
            '<ocf:rootfile full-path="Contents/content.hpf" media-type="application/hwpml-package+xml"/>'
            '<ocf:rootfile full-path="Preview/PrvText.txt" media-type="text/plain"/>'
            '<ocf:rootfile full-path="META-INF/container.rdf" media-type="application/rdf+xml"/>'
            '</ocf:rootfiles>'
            '</ocf:container>'
        ).encode('utf-8')

    def _hwpx_compatible_container_rdf(self, section_names):
        parts = ['Contents/header.xml'] + list(section_names)
        descriptions = []
        for part in parts:
            rdf_type = 'HeaderFile' if part.endswith('header.xml') else 'SectionFile'
            descriptions.append(
                '<rdf:Description rdf:about="">'
                '<pkg:hasPart xmlns:pkg="http://www.hancom.co.kr/hwpml/2016/meta/pkg#" '
                f'rdf:resource="{html.escape(part)}"/>'
                '</rdf:Description>'
                f'<rdf:Description rdf:about="{html.escape(part)}">'
                f'<rdf:type rdf:resource="http://www.hancom.co.kr/hwpml/2016/meta/pkg#{rdf_type}"/>'
                '</rdf:Description>'
            )
        descriptions.append(
            '<rdf:Description rdf:about="">'
            '<rdf:type rdf:resource="http://www.hancom.co.kr/hwpml/2016/meta/pkg#Document"/>'
            '</rdf:Description>'
        )
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>'
            '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
            + ''.join(descriptions) +
            '</rdf:RDF>'
        ).encode('utf-8')

    def _hwpx_compatible_version_xml(self):
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>'
            '<hv:HCFVersion xmlns:hv="http://www.hancom.co.kr/hwpml/2011/version" '
            'tagetApplication="WORDPROCESSOR" major="5" minor="1" micro="1" '
            'buildNumber="0" os="1" xmlVersion="1.5" '
            'application="Hancom Office Hangul" appVersion="13, 0, 0, 1408"/>'
        ).encode('utf-8')

    def _hwpx_compatible_settings_xml(self):
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>'
            '<ha:HWPApplicationSetting xmlns:ha="http://www.hancom.co.kr/hwpml/2011/app" '
            'xmlns:config="urn:oasis:names:tc:opendocument:xmlns:config:1.0">'
            '<ha:CaretPosition listIDRef="0" paraIDRef="0" pos="0"/>'
            '</ha:HWPApplicationSetting>'
        ).encode('utf-8')

    def _normalize_hwpx_header_xml(self, payload, section_count):
        from lxml import etree

        parser = etree.XMLParser(remove_blank_text=False, recover=True)
        root = etree.fromstring(payload, parser=parser)
        root.set('version', '1.5')
        root.set('secCnt', str(max(section_count, 1)))
        self._strip_hwpx_attribute_namespaces(root)

        hh_ns = 'http://www.hancom.co.kr/hwpml/2011/head'
        for bullets in root.xpath('.//hh:bullets', namespaces={'hh': hh_ns}):
            for bullet in list(bullets):
                if bullet.find(f'{{{hh_ns}}}paraHead') is None:
                    bullets.remove(bullet)
            bullets.set('itemCnt', str(len(bullets.findall(f'{{{hh_ns}}}bullet'))))
        return etree.tostring(root, encoding='UTF-8', xml_declaration=True, standalone=True)

    def _strip_hwpx_attribute_namespaces(self, root):
        from lxml import etree

        for elem in root.iter():
            replacements = {}
            remove_keys = []
            for key, value in elem.attrib.items():
                if not str(key).startswith('{'):
                    continue
                local_name = etree.QName(key).localname
                if local_name not in elem.attrib:
                    replacements[local_name] = value
                remove_keys.append(key)
            for key in remove_keys:
                try:
                    del elem.attrib[key]
                except Exception:
                    pass
            for key, value in replacements.items():
                elem.set(key, value)

    def _ensure_hwpx_header_required_attrs(self, payload, section_count):
        from lxml import etree

        parser = etree.XMLParser(remove_blank_text=False, recover=True)
        root = etree.fromstring(payload, parser=parser)
        if not root.get('version'):
            root.set('version', '1.5')
        if not root.get('secCnt'):
            root.set('secCnt', str(max(section_count, 1)))
        self._repair_hwpx_header_lists(root)
        return etree.tostring(root, encoding='UTF-8', xml_declaration=True, standalone=True)

    def _repair_hwpx_header_lists(self, root):
        """불완전한 글머리표/번호 정의를 제거해 한컴 파서 오류를 막는다."""
        hh_ns = 'http://www.hancom.co.kr/hwpml/2011/head'
        ns = {'hh': hh_ns}
        for bullets in root.xpath('.//hh:bullets', namespaces=ns):
            for bullet in list(bullets):
                if bullet.find(f'{{{hh_ns}}}paraHead') is None:
                    bullets.remove(bullet)
            bullets.set('itemCnt', str(len(bullets.findall(f'{{{hh_ns}}}bullet'))))

    def _fill_hwpx_package(self, hwpx_bytes, instance_id, instance):
        from lxml import etree

        content_json = instance.get('content_json', {}) if instance and isinstance(instance.get('content_json'), dict) else {}
        fields_schema = content_json.get('fields_schema', {}) if isinstance(content_json.get('fields_schema'), dict) else {}
        table_spacings = content_json.get('table_spacings', {}) if isinstance(content_json.get('table_spacings'), dict) else {}
        field_layouts = content_json.get('field_layouts', {}) if isinstance(content_json.get('field_layouts'), dict) else {}
        all_values = self._collect_all_values(instance_id, instance)
        raw_generated = content_json.get('generated_fields', {}) if isinstance(content_json.get('generated_fields'), dict) else {}
        for key, value in raw_generated.items():
            if not str(value or '').strip():
                continue
            if not all_values.get(key) or self._is_hwp_placeholder_text(all_values.get(key)):
                all_values[key] = value

        section_updates = {}
        preview_parts = []
        table_offset = 0
        changed = 0

        source = io.BytesIO(hwpx_bytes)
        with zipfile.ZipFile(source, 'r') as zin:
            section_names = sorted([
                name for name in zin.namelist()
                if re.match(r'^Contents/section\d+\.xml$', name)
            ])
            for name in section_names:
                parser = etree.XMLParser(remove_blank_text=False, recover=True)
                root = etree.fromstring(zin.read(name), parser=parser)
                changed_count, table_count = self._fill_hwpx_tables(root, table_offset, fields_schema, all_values)
                changed += self._apply_hwpx_table_spacing_controls(root, table_offset, table_count, table_spacings)
                changed += self._apply_hwpx_direct_table_cell_layouts(root, table_offset, table_count, field_layouts)
                table_offset += table_count
                changed += changed_count
                for text_node in root.xpath('.//hp:t', namespaces={'hp': 'http://www.hancom.co.kr/hwpml/2011/paragraph'}):
                    if text_node.text:
                        preview_parts.append(text_node.text)
                self._strip_hwpx_attribute_namespaces(root)
                section_updates[name] = etree.tostring(
                    root,
                    encoding='UTF-8',
                    xml_declaration=True,
                    standalone=True
                )
            if 'Contents/header.xml' in zin.namelist():
                header_payload = self._ensure_hwpx_header_required_attrs(
                    zin.read('Contents/header.xml'),
                    len(section_names)
                )
                header_root = etree.fromstring(header_payload, parser=etree.XMLParser(remove_blank_text=False, recover=True))
                self._strip_hwpx_attribute_namespaces(header_root)
                section_updates['Contents/header.xml'] = etree.tostring(
                    header_root,
                    encoding='UTF-8',
                    xml_declaration=True,
                    standalone=True
                )

            preview_text = '\n'.join([part.strip() for part in preview_parts if part and part.strip()])[:20000]
            result = self._write_hwpx_zip_preserving_package(zin, section_updates, preview_text)

        if changed == 0 and all_values:
            # 좌표 분석이 틀어진 새 양식이라도 빈 HWPX를 내려주지는 않도록 조기 감지한다.
            raise Exception("HWPX 표 채움 위치를 찾지 못했습니다. 양식 분석을 다시 실행해 주세요.")
        return result

    def _generate_hwpx_from_sections(self, instance_id, instance):
        try:
            from hwpx import HwpxDocument
        except Exception as e:
            raise Exception(f"HWPX 생성 라이브러리를 불러오지 못했습니다: {str(e)}")

        doc = HwpxDocument.new()
        title = instance.get('title', '문서') if instance else '문서'
        doc.add_paragraph(str(title or '문서'))
        for sec in self.struct.doc.list_sections(instance_id):
            if sec.get('section_title'):
                doc.add_paragraph(str(sec.get('section_title')))
            if sec.get('content'):
                doc.add_paragraph(str(sec.get('content')))
        return doc.to_bytes()

    def generate_hwpx(self, instance_id):
        """원본 양식을 가능한 한 유지한 실제 HWPX 바이트를 생성한다."""
        instance = self.struct.doc.get_instance(instance_id)
        if not instance:
            raise Exception("문서를 찾을 수 없습니다.")

        content_json = instance.get('content_json', {}) if isinstance(instance.get('content_json'), dict) else {}
        file_type, template_file_path, template_id = self._resolve_template_info(instance, content_json)

        if template_file_path and file_type in ('hwp', 'hwpx'):
            actual_path = self._template_abspath(template_file_path, template_id)
            if not os.path.exists(actual_path):
                raise Exception("원본 양식 파일을 찾을 수 없습니다.")
            if file_type == 'hwpx' or actual_path.lower().endswith('.hwpx'):
                with open(actual_path, 'rb') as f:
                    hwpx_bytes = f.read()
            else:
                hwpx_bytes = self._convert_hwp_to_hwpx_bytes(actual_path)
            return self._fill_hwpx_package(hwpx_bytes, instance_id, instance)

        return self._generate_hwpx_from_sections(instance_id, instance)

    # ─── HWP HTML 미리보기/구버전 호환 ─────────────────────────────
    def generate_hwp_html(self, instance_id, embed_assets=False):
        """HWP 원본 양식에 값을 채운 HTML을 생성하여 반환.
        HWP 포맷 직접 생성은 불가하므로, 원본 양식의 HTML 버전을 제공한다.
        """
        instance = self.struct.doc.get_instance(instance_id)
        content_json = instance.get('content_json', {}) if instance and isinstance(instance.get('content_json'), dict) else {}

        file_type = content_json.get('file_type', '')
        template_file_path = content_json.get('template_file_path', '')
        template_id = content_json.get('template_id', '') or (instance.get('template_id', '') if instance else '')

        if not template_file_path and template_id:
            try:
                tpl = self.struct.doc.get_template(template_id)
                if tpl:
                    template_file_path = tpl.get('file_path', '')
                    if not file_type:
                        file_type = tpl.get('file_type', '')
            except Exception:
                pass

        if file_type == 'hwp' and template_file_path:
            html = self._preview_hwp_html(instance_id, instance, template_file_path, template_id, embed_assets=embed_assets)
            if html:
                return html

        # HWP 템플릿이 없으면 섹션 기반 HTML 반환
        sections = self.struct.doc.list_sections(instance_id)
        return self._build_sections_html(instance, sections)

    # ─── 이미지 배치 가능 위치 추출 ─────────────────────────────
    def get_image_positions(self, instance_id):
        """HWP 템플릿에서 이미지를 배치할 수 있는 셀 위치 목록을 반환"""
        instance = self.struct.doc.get_instance(instance_id)
        content_json = instance.get('content_json', {}) if instance and isinstance(instance.get('content_json'), dict) else {}

        file_type = content_json.get('file_type', '')
        template_file_path = content_json.get('template_file_path', '')
        template_id = content_json.get('template_id', '') or (instance.get('template_id', '') if instance else '')

        if not template_file_path and template_id:
            try:
                tpl = self.struct.doc.get_template(template_id)
                if tpl:
                    template_file_path = tpl.get('file_path', '')
                    if not file_type:
                        file_type = tpl.get('file_type', '')
            except Exception:
                pass

        positions = []
        if file_type == 'hwp' and template_file_path:
            try:
                tpl_fs = wiz.project.fs("data", "uploads", "templates") if template_id else wiz.project.fs("data", "uploads", "instances")
                actual_path = tpl_fs.abspath(template_file_path)
                if os.path.exists(actual_path):
                    tmpdir = tempfile.mkdtemp()
                    try:
                        html_dir = os.path.join(tmpdir, 'hwp_html')
                        subprocess.run(['hwp5html', '--output', html_dir, actual_path],
                                        capture_output=True, text=True, timeout=120)
                        xhtml_path = os.path.join(html_dir, 'index.xhtml')
                        if os.path.exists(xhtml_path):
                            with open(xhtml_path, 'r', encoding='utf-8') as f:
                                html_content = f.read()
                            # 이미지 관련 키워드가 있는 라벨 추출
                            rows = re.findall(r'<tr>(.*?)</tr>', html_content, re.DOTALL)
                            for row in rows:
                                cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
                                if len(cells) >= 2:
                                    label = re.sub(r'<[^>]+>', '', cells[0]).replace('&#13;', '').strip()
                                    label = re.sub(r'\s+', ' ', label).strip()
                                    value = re.sub(r'<[^>]+>', '', cells[1]).replace('&#13;', '').strip()
                                    # 사진/이미지/첨부 관련 라벨 또는 큰 빈 셀(112mm+) 감지
                                    if label and ('사진' in label or '이미지' in label or '첨부' in label or
                                                  '참석자' in value or '얼굴' in value):
                                        positions.append(label)
                    finally:
                        shutil.rmtree(tmpdir, ignore_errors=True)
            except Exception:
                pass

        # 기본 위치 (수동 추가용)
        if not positions:
            positions = ['활동 사진']
        return positions

    # ─── 유틸 ─────────────────────────────────────────────────
    def _safe_date(self, value, default=''):
        """datetime 또는 문자열에서 YYYY-MM-DD 추출"""
        if not value:
            return default
        if isinstance(value, datetime.datetime):
            return value.strftime('%Y-%m-%d')
        return str(value)[:10]

    def _escape_xml(self, text):
        if not text:
            return ''
        return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    def _escape_html(self, text):
        if not text:
            return ''
        return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')


Model = DocExport

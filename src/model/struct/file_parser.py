# =============================================================================
# File Parser Sub-Struct
# =============================================================================
# HWP, DOC, DOCX, PDF 파일의 텍스트/구조를 추출하고
# 양식 내 작성 필요 영역을 자동 감지하는 비즈니스 로직
#
# HWP 파일은 LibreOffice를 이용해 DOCX로 변환 후 파싱한다.
# =============================================================================

import os
import re
import json
import subprocess
import tempfile
import shutil
import zipfile
from collections import Counter

class FileParser:
    def __init__(self, root):
        self.root = root

    def _table_col_count(self, table):
        return max((len(row) for row in (table or []) if row), default=0)

    # ─────────────────────────────────────────────
    # HWP / PDF → DOCX 변환 (LibreOffice)
    # ─────────────────────────────────────────────

    def _convert_to_pdf(self, file_path):
        """LibreOffice로 HWP/DOC/DOCX → PDF 변환. 변환된 PDF 절대경로를 반환.
        HWP → PDF 는 HWP → DOCX 보다 레이아웃/텍스트 보존율이 높아 파싱 정확도가 좋다."""
        ext = os.path.splitext(file_path)[1].lower()
        if ext == '.pdf':
            return file_path

        lo_cmd = shutil.which('libreoffice') or shutil.which('soffice')
        if not lo_cmd:
            raise Exception("LibreOffice가 설치되어 있지 않습니다.")

        tmpdir = tempfile.mkdtemp()
        try:
            result = subprocess.run(
                [lo_cmd, '--headless', '--norestore', '--convert-to', 'pdf', '--outdir', tmpdir, file_path],
                capture_output=True, text=True, timeout=180
            )
            all_files = os.listdir(tmpdir) if os.path.exists(tmpdir) else []
            pdf_files = [f for f in all_files if f.lower().endswith('.pdf')]

            if not pdf_files:
                stderr_msg = (result.stderr or '').strip()[:300]
                raise Exception(f"LibreOffice PDF 변환 실패 — PDF 파일 미생성. {stderr_msg}")

            basename = os.path.splitext(os.path.basename(file_path))[0]
            best = next((f for f in pdf_files if os.path.splitext(f)[0].lower() == basename.lower()), pdf_files[0])
            output_path = os.path.join(tmpdir, best)
            dest_dir = os.path.dirname(file_path)
            dest_path = os.path.join(dest_dir, f"{basename}_converted.pdf")
            shutil.copy2(output_path, dest_path)
            return dest_path
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def _convert_with_libreoffice(self, input_path, output_ext, output_dir):
        lo_cmd = shutil.which('libreoffice') or shutil.which('soffice')
        if not lo_cmd:
            raise Exception("LibreOffice가 설치되어 있지 않습니다.")

        result = subprocess.run(
            [lo_cmd, '--headless', '--nologo', '--nofirststartwizard', '--norestore',
             '--convert-to', output_ext, '--outdir', output_dir, input_path],
            capture_output=True, text=True, timeout=180
        )
        wanted = f'.{output_ext.lower().split(":")[0]}'
        all_files = os.listdir(output_dir) if os.path.exists(output_dir) else []
        output_files = [f for f in all_files if f.lower().endswith(wanted)]
        if not output_files:
            stderr_msg = (result.stderr or '').strip()[:400]
            stdout_msg = (result.stdout or '').strip()[:200]
            details = []
            if stderr_msg:
                details.append(f"stderr: {stderr_msg}")
            if stdout_msg:
                details.append(f"stdout: {stdout_msg}")
            if all_files:
                details.append(f"생성된 파일: {', '.join(all_files)}")
            details_str = ' | '.join(details) if details else '출력 없음'
            raise Exception(f"LibreOffice 변환 실패 — {wanted} 파일이 생성되지 않았습니다. ({details_str})")

        basename = os.path.splitext(os.path.basename(input_path))[0]
        best = next((f for f in output_files if os.path.splitext(f)[0].lower() == basename.lower()), output_files[0])
        return os.path.join(output_dir, best)

    def _convert_hwp_to_docx(self, file_path, dest_path):
        """HWP는 hwp5odt로 ODT를 만든 뒤 DOCX로 변환한다. 실패 시 LibreOffice 직변환을 시도한다."""
        hwp5odt = shutil.which('hwp5odt')
        errors = []

        if hwp5odt:
            tmpdir = tempfile.mkdtemp()
            try:
                odt_path = os.path.join(tmpdir, 'source.odt')
                result = subprocess.run(
                    [hwp5odt, '--output', odt_path, file_path],
                    capture_output=True, text=True, timeout=180
                )
                if result.returncode != 0 or not os.path.exists(odt_path):
                    errors.append((result.stderr or result.stdout or 'hwp5odt 출력 없음')[:300])
                else:
                    docx_path = self._convert_with_libreoffice(odt_path, 'docx', tmpdir)
                    shutil.copy2(docx_path, dest_path)
                    return dest_path
            except Exception as e:
                errors.append(str(e)[:300])
            finally:
                shutil.rmtree(tmpdir, ignore_errors=True)

        tmpdir = tempfile.mkdtemp()
        try:
            docx_path = self._convert_with_libreoffice(file_path, 'docx', tmpdir)
            shutil.copy2(docx_path, dest_path)
            return dest_path
        except Exception as e:
            errors.append(str(e)[:300])
            raise Exception('HWP → DOCX 변환 실패: ' + ' | '.join([err for err in errors if err]))
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def _convert_to_docx(self, file_path):
        """HWP/DOC/PDF → DOCX 변환. 변환된 DOCX 절대경로를 반환."""
        ext = os.path.splitext(file_path)[1].lower()
        if ext == '.docx':
            return file_path

        basename = os.path.splitext(os.path.basename(file_path))[0]
        dest_dir = os.path.dirname(file_path)
        dest_path = os.path.join(dest_dir, f"{basename}_converted.docx")
        if os.path.exists(dest_path):
            return dest_path

        if ext == '.hwp':
            return self._convert_hwp_to_docx(file_path, dest_path)

        # DOC/PDF 등 LibreOffice가 읽을 수 있는 형식은 바로 DOCX로 변환한다.
        tmpdir = tempfile.mkdtemp()
        try:
            output_path = self._convert_with_libreoffice(file_path, 'docx', tmpdir)
            shutil.copy2(output_path, dest_path)
            return dest_path
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    # ─────────────────────────────────────────────
    # 통합 파싱 인터페이스
    # ─────────────────────────────────────────────

    def parse(self, file_path):
        """파일 경로를 받아 텍스트와 구조를 추출한다."""
        if not os.path.exists(file_path):
            raise Exception(f"파일이 존재하지 않습니다: {file_path}")

        ext = os.path.splitext(file_path)[1].lower()

        if ext == '.docx':
            result = self.parse_docx(file_path)
            result['editable_docx_path'] = os.path.basename(file_path)
        elif ext == '.pdf':
            # PDF 직접 업로드 시 DOCX 변환도 시도 (채움용)
            docx_path = ''
            try:
                basename = os.path.splitext(file_path)[0]
                candidate = basename + '_converted.docx'
                if os.path.exists(candidate):
                    docx_path = candidate
                else:
                    docx_path = self._convert_to_docx(file_path)
            except Exception:
                docx_path = ''
            result = self.parse_pdf(
                file_path,
                converted_docx_path=os.path.basename(docx_path) if docx_path else ''
            )
            if docx_path:
                result['editable_docx_path'] = os.path.basename(docx_path)
        elif ext == '.hwp':
            result = self.parse_hwp(file_path)
        elif ext == '.doc':
            docx_path = self._convert_to_docx(file_path)
            result = self.parse_docx(docx_path)
            result['file_type'] = 'doc'
            result['converted_docx_path'] = os.path.basename(docx_path)
            result['editable_docx_path'] = os.path.basename(docx_path)
            result['capabilities']['preserve_layout_fill'] = True
            result['capabilities']['preferred_output'] = 'docx'
            result['capabilities']['reason'] = 'DOC → DOCX 변환 후 양식 구조 유지하며 채움 가능'
        else:
            raise Exception(f"지원하지 않는 파일 형식입니다: {ext}")

        if result.get('converted_docx_path') and not result.get('editable_docx_path'):
            result['editable_docx_path'] = result.get('converted_docx_path', '')

        # 필드 자동 감지
        result['fields'] = self.detect_fields(result['text'], result.get('sections', []))

        # 테이블 기반 채움 대상 분석
        result['table_fills'] = self._analyze_table_fills(result.get('tables', []))

        return result

    # ─────────────────────────────────────────────
    # DOCX 파싱
    # ─────────────────────────────────────────────

    def parse_docx(self, file_path):
        """DOCX 파일에서 텍스트, 섹션, 테이블, 플레이스홀더를 추출한다."""
        import docx

        doc = docx.Document(file_path)
        full_text = []
        sections = []
        current_section = None
        metadata = {}
        placeholder_runs = []
        tables_data = []

        # 코어 속성
        try:
            props = doc.core_properties
            metadata = {
                'title': props.title or '',
                'author': props.author or '',
                'subject': props.subject or '',
                'created': str(props.created) if props.created else '',
                'modified': str(props.modified) if props.modified else ''
            }
        except Exception:
            pass

        # 머리말/꼬리말
        for section in doc.sections:
            try:
                for para in section.header.paragraphs:
                    text = para.text.strip()
                    if text:
                        full_text.append(text)
                        placeholder_runs.extend(self._find_docx_placeholders(text, source='header'))
            except Exception:
                pass
            try:
                for para in section.footer.paragraphs:
                    text = para.text.strip()
                    if text:
                        full_text.append(text)
                        placeholder_runs.extend(self._find_docx_placeholders(text, source='footer'))
            except Exception:
                pass

        # 단락 처리
        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                continue

            full_text.append(text)
            placeholder_runs.extend(self._find_docx_placeholders(text, source='paragraph'))

            style_name = para.style.name if para.style else ''
            if style_name.startswith('Heading'):
                if current_section:
                    sections.append(current_section)
                current_section = {
                    'title': text,
                    'content': '',
                    'type': 'heading',
                    'level': self._extract_heading_level(style_name)
                }
            elif current_section:
                if current_section['content']:
                    current_section['content'] += '\n'
                current_section['content'] += text
            else:
                if not sections and not current_section:
                    current_section = {
                        'title': '서두',
                        'content': text,
                        'type': 'preamble',
                        'level': 0
                    }

        if current_section:
            sections.append(current_section)

        # 테이블 처리 (병합 셀 정확히 감지 — tc identity 기반 dedup)
        for table_idx, table in enumerate(doc.tables):
            table_rows = []
            for row_idx, row in enumerate(table.rows):
                row_data = []
                seen_tcs = {}  # tc id → col_idx (가로 병합 셀 중복 추적)
                for col_idx, cell in enumerate(row.cells):
                    tc_id = id(cell._tc)
                    if tc_id in seen_tcs:
                        # 이미 처리된 tc → 가로 병합 계속 셀 (빈 칸으로 표시)
                        row_data.append('')
                    else:
                        seen_tcs[tc_id] = col_idx
                        cell_text = cell.text.strip()
                        row_data.append(cell_text)
                        if cell_text:
                            full_text.append(cell_text)
                            placeholder_runs.extend(self._find_docx_placeholders(cell_text, source=f'table:{table_idx}:{row_idx}:{col_idx}'))
                # 세로 병합(vMerge) 계속 행 감지: 같은 열에 값이 없고 XML에 vMerge 있으면 빈 칸 유지
                try:
                    from docx.oxml.ns import qn
                    for col_idx, cell in enumerate(row.cells):
                        if col_idx >= len(row_data):
                            break
                        tcPr = cell._tc.find(qn('w:tcPr'))
                        if tcPr is not None:
                            vm = tcPr.find(qn('w:vMerge'))
                            if vm is not None:
                                val = vm.get(qn('w:val'), '')
                                if not val or val == 'continue':
                                    # 세로 병합 계속 셀 → 빈 칸으로 명시
                                    if col_idx < len(row_data):
                                        row_data[col_idx] = ''
                except Exception:
                    pass
                table_rows.append(row_data)
            if table_rows:
                tables_data.append(table_rows)

        if not sections and full_text:
            sections = [{'title': '본문', 'content': '\n'.join(full_text), 'type': 'body', 'level': 0}]

        # 채움 가능 여부 결정: 플레이스홀더 또는 빈 테이블 셀이 있으면 가능
        table_fills = self._analyze_table_fills(tables_data)
        fill_supported = len(placeholder_runs) > 0 or len(table_fills) > 0

        return {
            'text': '\n'.join(full_text),
            'sections': sections,
            'tables': tables_data,
            'fields': [],
            'file_type': 'docx',
            'metadata': metadata,
            'placeholders': placeholder_runs,
            'table_fills': table_fills,
            'converted_docx_path': '',
            'editable_docx_path': os.path.basename(file_path),
            'capabilities': {
                'preserve_layout_fill': fill_supported,
                'preferred_output': 'docx' if fill_supported else 'section-text',
                'reason': 'DOCX 원본 양식 구조 유지하며 빈칸 채움 가능' if fill_supported else '명시적 채움 대상이 없어 섹션 기반 생성 모드 사용'
            }
        }

    # ─────────────────────────────────────────────
    # PDF 파싱
    # ─────────────────────────────────────────────

    def parse_pdf(self, file_path, converted_docx_path=''):
        """PDF 파일에서 텍스트, 표, 섹션 구조를 정밀하게 추출한다.

        pdfplumber를 사용해 pdfplumber chars(글자 레벨 정보)로
        폰트 크기/굵기 기반 헤딩 감지, 표 구조 정밀 추출을 수행한다.
        """
        import pdfplumber

        full_text_pages = []
        sections = []
        tables_data = []
        metadata = {}
        current_section = None

        with pdfplumber.open(file_path) as pdf:
            if pdf.metadata:
                metadata = {
                    'title': (pdf.metadata.get('Title') or '').strip(),
                    'author': (pdf.metadata.get('Author') or '').strip(),
                    'subject': (pdf.metadata.get('Subject') or '').strip(),
                    'creator': (pdf.metadata.get('Creator') or '').strip(),
                    'pages': len(pdf.pages)
                }

            # ── camelot으로 표 전체 추출 (페이지 단위가 아닌 파일 단위) ──
            camelot_tables_by_page = {}
            try:
                import camelot
                cam_tables = camelot.read_pdf(file_path, pages='all', flavor='lattice', suppress_stdout=True)
                for ct in cam_tables:
                    p = ct.page  # 1-indexed
                    rows_raw = ct.data  # list of list of str
                    cleaned = []
                    for row in rows_raw:
                        cr = [(c or '').strip().replace('\n', ' ') for c in row]
                        if any(c for c in cr):
                            cleaned.append(cr)
                    if cleaned:
                        camelot_tables_by_page.setdefault(p, []).append(cleaned)
            except Exception:
                camelot_tables_by_page = {}

            for page_idx, page in enumerate(pdf.pages):
                page_num = page_idx + 1
                # ── 표 추출: camelot 결과 우선, 없으면 pdfplumber ──
                page_table_bboxes = []
                if page_num in camelot_tables_by_page:
                    for ct in camelot_tables_by_page[page_num]:
                        tables_data.append(ct)
                    # bbox는 pdfplumber로 별도 취득
                    try:
                        tset = {'vertical_strategy': 'lines', 'horizontal_strategy': 'lines',
                                'snap_tolerance': 4, 'join_tolerance': 4}
                        for finder_table in page.find_tables(tset):
                            page_table_bboxes.append(finder_table.bbox)
                    except Exception:
                        pass
                else:
                    try:
                        tset = {'vertical_strategy': 'lines', 'horizontal_strategy': 'lines',
                                'snap_tolerance': 4, 'join_tolerance': 4}
                        page_tables = page.extract_tables(tset)
                        if page_tables:
                            for t in page_tables:
                                cleaned = []
                                for row in t:
                                    cleaned_row = []
                                    for cell in row:
                                        cleaned_row.append((cell or '').strip().replace('\n', ' '))
                                    cleaned.append(cleaned_row)
                                cleaned = [r for r in cleaned if any(c for c in r)]
                                if cleaned:
                                    tables_data.append(cleaned)
                            try:
                                for finder_table in page.find_tables(tset):
                                    page_table_bboxes.append(finder_table.bbox)
                            except Exception:
                                pass
                    except Exception:
                        pass

                # ── 텍스트 추출 (표 영역 제외하고 본문만 추출) ──
                try:
                    # 표 bbox 영역 제외 후 텍스트 추출
                    text_page = page
                    for bbox in page_table_bboxes:
                        try:
                            text_page = text_page.outside_bbox(bbox)
                        except Exception:
                            pass
                    page_text = text_page.extract_text(x_tolerance=3, y_tolerance=3) or ''
                except Exception:
                    page_text = page.extract_text(x_tolerance=3, y_tolerance=3) or ''

                # 표 텍스트도 full_text에 포함
                table_text_parts = []
                for t in (tables_data[-(len(tables_data)):] if tables_data else []):
                    for row in t:
                        row_str = ' | '.join([c for c in row if c])
                        if row_str.strip():
                            table_text_parts.append(row_str)

                combined_page_text = page_text.strip()
                if table_text_parts:
                    combined_page_text += '\n' + '\n'.join(table_text_parts)

                if combined_page_text:
                    full_text_pages.append(combined_page_text)

                # ── 섹션 구조 파싱 (폰트 크기/굵기 기반 헤딩 감지) ──
                try:
                    chars = page.chars
                    if chars:
                        # 페이지 내 대표 폰트 크기 계산
                        sizes = [c.get('size', 10) for c in chars if c.get('size')]
                        median_size = sorted(sizes)[len(sizes) // 2] if sizes else 10
                        heading_threshold = median_size * 1.15  # 중간값보다 15% 이상 크면 헤딩 후보

                        # 라인별 그룹화
                        lines_by_y = {}
                        for ch in chars:
                            y = round(ch.get('top', 0) / 3) * 3  # 3pt 단위로 그룹
                            if y not in lines_by_y:
                                lines_by_y[y] = []
                            lines_by_y[y].append(ch)

                        for y in sorted(lines_by_y.keys()):
                            line_chars = sorted(lines_by_y[y], key=lambda c: c.get('x0', 0))
                            line_text = ''.join(c.get('text', '') for c in line_chars).strip()
                            if not line_text:
                                continue

                            avg_size = sum(c.get('size', 10) for c in line_chars) / len(line_chars)
                            is_bold = any(
                                'Bold' in (c.get('fontname', '') or '') or
                                'bold' in (c.get('fontname', '') or '').lower()
                                for c in line_chars
                            )
                            is_heading = (
                                avg_size >= heading_threshold or
                                (is_bold and len(line_text) <= 40 and not line_text.endswith(('.', ',', ')', '）')))
                            )

                            # 표 영역 내 텍스트는 헤딩으로 분류하지 않음
                            char_x = line_chars[0].get('x0', 0) if line_chars else 0
                            char_y = line_chars[0].get('top', 0) if line_chars else 0
                            in_table = any(
                                b[0] <= char_x <= b[2] and b[1] <= char_y <= b[3]
                                for b in page_table_bboxes
                            )

                            if is_heading and not in_table and len(line_text) >= 2:
                                if current_section:
                                    sections.append(current_section)
                                current_section = {
                                    'title': line_text,
                                    'content': '',
                                    'type': 'heading',
                                    'level': 1 if avg_size >= heading_threshold * 1.1 else 2,
                                    'page': page_idx + 1
                                }
                            elif current_section and not in_table:
                                if current_section['content']:
                                    current_section['content'] += '\n'
                                current_section['content'] += line_text
                            elif not current_section and not in_table and line_text:
                                current_section = {
                                    'title': f'본문 (p.{page_idx + 1})',
                                    'content': line_text,
                                    'type': 'body',
                                    'level': 0,
                                    'page': page_idx + 1
                                }
                    else:
                        # chars 없으면 extract_text 기반 폴백
                        for line in page_text.split('\n'):
                            line = line.strip()
                            if not line:
                                continue
                            if self._is_pdf_heading(line):
                                if current_section:
                                    sections.append(current_section)
                                current_section = {
                                    'title': line, 'content': '', 'type': 'heading',
                                    'level': 1, 'page': page_idx + 1
                                }
                            elif current_section:
                                if current_section['content']:
                                    current_section['content'] += '\n'
                                current_section['content'] += line
                            else:
                                current_section = {
                                    'title': f'페이지 {page_idx + 1}', 'content': line,
                                    'type': 'page', 'level': 0, 'page': page_idx + 1
                                }
                except Exception:
                    # chars 파싱 실패 시 텍스트 기반 폴백
                    for line in page_text.split('\n'):
                        line = line.strip()
                        if not line:
                            continue
                        if self._is_pdf_heading(line):
                            if current_section:
                                sections.append(current_section)
                            current_section = {
                                'title': line, 'content': '', 'type': 'heading',
                                'level': 1, 'page': page_idx + 1
                            }
                        elif current_section:
                            if current_section['content']:
                                current_section['content'] += '\n'
                            current_section['content'] += line
                        else:
                            current_section = {
                                'title': f'페이지 {page_idx + 1}', 'content': line,
                                'type': 'page', 'level': 0, 'page': page_idx + 1
                            }

        if current_section:
            sections.append(current_section)

        full_text = '\n\n'.join(full_text_pages)

        if not sections and full_text:
            sections = [{'title': '본문', 'content': full_text, 'type': 'body', 'level': 0}]

        # 표 텍스트도 섹션에 반영 (표 전용 섹션 추가)
        if tables_data:
            table_sec_content = []
            for t_idx, t in enumerate(tables_data):
                rows_text = []
                for row in t:
                    row_str = ' | '.join([c for c in row if c])
                    if row_str.strip():
                        rows_text.append(row_str)
                if rows_text:
                    table_sec_content.append(f"[표 {t_idx+1}]\n" + '\n'.join(rows_text))
            if table_sec_content:
                sections.append({
                    'title': '표 데이터',
                    'content': '\n\n'.join(table_sec_content),
                    'type': 'table_summary',
                    'level': 0
                })
                full_text += '\n\n' + '\n\n'.join(table_sec_content)

        table_fills = self._analyze_table_fills(tables_data)
        can_fill = bool(converted_docx_path) and len(table_fills) > 0

        return {
            'text': full_text,
            'sections': sections,
            'tables': tables_data,
            'fields': [],
            'file_type': 'pdf',
            'metadata': metadata,
            'table_fills': table_fills,
            'converted_docx_path': converted_docx_path,
            'editable_docx_path': converted_docx_path,
            'capabilities': {
                'preserve_layout_fill': can_fill,
                'preferred_output': 'docx' if can_fill else 'section-text',
                'reason': 'PDF를 DOCX로 변환하여 양식 채움 가능' if can_fill else 'PDF 텍스트/표 기반 내용 파악 후 섹션 작성 모드 사용'
            }
        }

    # ─────────────────────────────────────────────
    # HWP 파싱 (LibreOffice 변환 → DOCX 파싱)
    # ─────────────────────────────────────────────

    def parse_hwp(self, file_path):
        """HWP 파일 파싱 전략:
        1) HWP → PDF 변환 후 pdfplumber로 정밀 파싱 (내용 이해용)
        2) HWP → DOCX 변환도 별도 시도 (채움용)
        PDF 경로가 내용 파악에 훨씬 정확하므로 파싱 결과는 PDF 기반을 사용한다.
        변환 전부 실패 시 olefile 텍스트 추출 폴백."""
        basename = os.path.splitext(file_path)[0]

        # ── Step 1: HWP → PDF (내용 파악) ──
        pdf_path = ''
        pdf_parse_result = None
        try:
            # 이전에 변환된 PDF가 있으면 재사용
            candidate_pdf = basename + '_converted.pdf'
            if os.path.exists(candidate_pdf):
                pdf_path = candidate_pdf
            else:
                pdf_path = self._convert_to_pdf(file_path)
        except Exception as pdf_err:
            pdf_path = ''
            pdf_err_msg = str(pdf_err)
        else:
            pdf_err_msg = ''

        # ── Step 2: HWP → DOCX (채움용) — 병렬로 시도 ──
        docx_path = ''
        try:
            candidate_docx = basename + '_converted.docx'
            if os.path.exists(candidate_docx):
                docx_path = candidate_docx
            else:
                docx_path = self._convert_to_docx(file_path)
        except Exception:
            docx_path = ''

        # ── Step 3: PDF 기반 파싱 ──
        if pdf_path and os.path.exists(pdf_path):
            try:
                pdf_parse_result = self.parse_pdf(
                    pdf_path,
                    converted_docx_path=os.path.basename(docx_path) if docx_path else ''
                )
                pdf_parse_result['file_type'] = 'hwp'
                pdf_parse_result['source_pdf_path'] = os.path.basename(pdf_path)
                if docx_path:
                    try:
                        docx_result = self.parse_docx(docx_path)
                        if docx_result.get('tables'):
                            pdf_parse_result['tables'] = docx_result.get('tables', [])
                            pdf_parse_result['table_fills'] = docx_result.get('table_fills', [])
                        if docx_result.get('placeholders'):
                            pdf_parse_result['placeholders'] = docx_result.get('placeholders', [])
                        if docx_result.get('fields'):
                            pdf_parse_result['fields'] = docx_result.get('fields', [])
                        docx_text = str(docx_result.get('text', '') or '').strip()
                        current_text = str(pdf_parse_result.get('text', '') or '').strip()
                        if docx_text and docx_text not in current_text:
                            pdf_parse_result['text'] = (current_text + '\n\n' + docx_text).strip()
                    except Exception:
                        pass
                    pdf_parse_result['converted_docx_path'] = os.path.basename(docx_path)
                    pdf_parse_result['editable_docx_path'] = os.path.basename(docx_path)
                    pdf_parse_result['capabilities']['preserve_layout_fill'] = True
                    pdf_parse_result['capabilities']['preferred_output'] = 'docx'
                    pdf_parse_result['capabilities']['reason'] = (
                        'HWP → PDF로 내용을 정밀 파악 후, 별도 DOCX 변환본으로 양식 채움'
                    )
                else:
                    pdf_parse_result['capabilities']['reason'] = (
                        'HWP → PDF로 내용을 정밀 파악 (DOCX 변환 실패 — 섹션 기반으로 출력)'
                    )
                return pdf_parse_result
            except Exception as parse_err:
                pass  # PDF 파싱도 실패 시 DOCX 파싱 시도

        # ── Step 4: DOCX 기반 파싱 폴백 ──
        if docx_path and os.path.exists(docx_path):
            try:
                result = self.parse_docx(docx_path)
                result['file_type'] = 'hwp'
                result['converted_docx_path'] = os.path.basename(docx_path)
                result['editable_docx_path'] = os.path.basename(docx_path)
                result['capabilities']['preserve_layout_fill'] = True
                result['capabilities']['preferred_output'] = 'docx'
                result['capabilities']['reason'] = 'HWP → DOCX 변환 후 파싱 (PDF 변환 실패 폴백)'
                return result
            except Exception:
                pass

        # ── Step 5: olefile 텍스트 추출 최종 폴백 ──
        err_summary = pdf_err_msg or 'HWP → PDF/DOCX 변환 모두 실패'
        return self._parse_hwp_fallback(file_path, err_summary)

    def _parse_hwp_fallback(self, file_path, convert_error=''):
        """olefile을 사용한 HWP 텍스트 추출 (폴백)."""
        import olefile

        full_text = []
        metadata = {}

        try:
            ole = olefile.OleFileIO(file_path)
            try:
                meta = ole.get_metadata()
                metadata = {
                    'title': (meta.title or b'').decode('utf-8', errors='ignore') if isinstance(meta.title, bytes) else str(meta.title or ''),
                    'author': (meta.author or b'').decode('utf-8', errors='ignore') if isinstance(meta.author, bytes) else str(meta.author or ''),
                    'subject': (meta.subject or b'').decode('utf-8', errors='ignore') if isinstance(meta.subject, bytes) else str(meta.subject or ''),
                }
            except Exception:
                pass

            if ole.exists('PrvText'):
                encoded = ole.openstream('PrvText').read()
                text = encoded.decode('utf-16-le', errors='ignore')
                text = text.replace('\r\n', '\n').replace('\r', '\n')
                full_text.append(text)
            elif ole.exists('BodyText'):
                for entry in ole.listdir():
                    entry_path = '/'.join(entry)
                    if entry_path.startswith('BodyText/'):
                        try:
                            stream = ole.openstream(entry)
                            data = stream.read()
                            text = self._extract_hwp_body_text(data)
                            if text:
                                full_text.append(text)
                        except Exception:
                            pass
            ole.close()
        except Exception as e:
            raise Exception(f"HWP 파일 파싱 실패: {str(e)}")

        combined_text = '\n'.join(full_text)
        sections = self._split_text_to_sections(combined_text)

        return {
            'text': combined_text,
            'sections': sections,
            'tables': [],
            'fields': [],
            'table_fills': [],
            'file_type': 'hwp',
            'metadata': metadata,
            'converted_docx_path': '',
            'editable_docx_path': '',
            'capabilities': {
                'preserve_layout_fill': False,
                'preferred_output': 'section-text',
                'reason': f'HWP DOCX 변환 실패({convert_error[:100]}), 텍스트 추출 모드로 처리'
            }
        }

    # ─────────────────────────────────────────────
    # 테이블 채움 대상 분석
    # ─────────────────────────────────────────────

    # ─────────────────────────────────────────────
    # 표 → 마크다운 변환 (AI 이해 최적화)
    # ─────────────────────────────────────────────

    def _table_to_markdown(self, table, max_rows=30):
        """테이블 데이터를 AI가 이해하기 쉬운 Markdown 표 형식으로 변환한다."""
        if not table:
            return '(빈 표)'
        max_cols = self._table_col_count(table)
        if max_cols == 0:
            return '(빈 표)'

        def normalize(val, width=14):
            v = str(val or '').strip().replace('|', '｜').replace('\n', ' ')
            return v[:40] if v else ''

        lines = []
        for r_idx, row in enumerate(table[:max_rows]):
            padded = [normalize(row[c] if c < len(row) else '') for c in range(max_cols)]
            lines.append('| ' + ' | '.join(padded) + ' |')
            if r_idx == 0:  # 헤더 구분선
                lines.append('|' + '|'.join(['---'] * max_cols) + '|')
        if len(table) > max_rows:
            lines.append(f'| ... (총 {len(table)}행) |')
        return '\n'.join(lines)

    def _table_to_markdown_with_target(self, table, target_row, target_col, window=3):
        """특정 셀을 [여기에 작성] 으로 표시한 Markdown 표를 반환한다 (주변 window행만)."""
        if not table:
            return '(빈 표)'
        max_cols = self._table_col_count(table)
        if max_cols == 0:
            return '(빈 표)'

        # 헤더 행 항상 포함 + target 주변 window행
        header_rows = set(range(min(2, len(table))))  # 첫 2행은 항상 포함
        context_rows = set(range(
            max(0, target_row - window),
            min(len(table), target_row + window + 1)
        ))
        included = sorted(header_rows | context_rows)

        lines = []
        prev_idx = -1
        for r_idx in included:
            if prev_idx >= 0 and r_idx > prev_idx + 1:
                lines.append('| ... |')  # 생략 표시
            row = table[r_idx] if r_idx < len(table) else []
            cells = []
            for c_idx in range(max_cols):
                val = str(row[c_idx] if c_idx < len(row) else '').strip().replace('|', '｜').replace('\n', ' ')
                if r_idx == target_row and c_idx == target_col:
                    cells.append('**[여기에 작성]**')
                else:
                    cells.append(val[:40] if val else '')
            lines.append('| ' + ' | '.join(cells) + ' |')
            if r_idx == 0:
                lines.append('|' + '|'.join(['---'] * max_cols) + '|')
            prev_idx = r_idx
        return '\n'.join(lines)

    def _analyze_table_fills(self, tables_data):
        """테이블에서 채워야 하는 빈 셀을 분석한다.

        Returns:
            list: [{'table_idx': int, 'row': int, 'col': int, 'label': str,
                     'type': str, 'context': str}]
        """
        fills = []
        if not tables_data:
            return fills

        for t_idx, table in enumerate(tables_data):
            if not table:
                continue

            max_cols = self._table_col_count(table)
            if max_cols == 0:
                continue
            row_groups = [self._base_row_group_label(table, idx) for idx in range(len(table))]
            row_group_counts = Counter([group for group in row_groups if group])
            row_group_orders = []
            row_group_seen = {}
            same_row_label_seen = set()
            for group in row_groups:
                if not group:
                    row_group_orders.append(0)
                    continue
                row_group_seen[group] = row_group_seen.get(group, 0) + 1
                row_group_orders.append(row_group_seen[group])

            for r_idx, row in enumerate(table):
                row_non_empty = [
                    self._normalize_table_text(cell)
                    for cell in (row or [])
                    if self._normalize_table_text(cell)
                ]
                if r_idx == 0 and len(row_non_empty) <= 1:
                    continue
                if self._is_structural_header_row(table, r_idx):
                    continue
                for c_idx in range(max_cols):
                    cell = self._table_cell(table, r_idx, c_idx)
                    left_label = self._find_left_label(table, r_idx, c_idx)
                    top_label = self._find_top_label(table, r_idx, c_idx)
                    row_label = self._find_row_label(table, r_idx, c_idx)
                    section_label = self._find_section_label(table, r_idx)
                    row_group = row_groups[r_idx] if r_idx < len(row_groups) else ''
                    row_index = row_group_orders[r_idx] if r_idx < len(row_group_orders) else 0

                    if not self._is_fill_candidate_cell(table, r_idx, c_idx, cell, left_label, top_label, row_label, section_label):
                        continue

                    label = self._compose_table_fill_label(left_label, top_label, row_label, section_label, row_group, row_index, row_group_counts.get(row_group, 0))
                    if max_cols == 2 and c_idx == 1 and left_label:
                        if r_idx == 0 and not cell:
                            continue
                        label = self._normalize_table_text(left_label)
                    first_cell = self._normalize_table_text(self._table_cell(table, r_idx, 0))
                    if c_idx > 0 and re.fullmatch(r'\d{1,2}', first_cell or ''):
                        line_label = self._normalize_table_text(left_label or row_label)
                        line_compact = re.sub(r'\s+', '', line_label)
                        if line_compact in {'주제', '진행과정', '활동사진'}:
                            label = f"{line_label} {first_cell}".strip()
                        elif top_label:
                            prefix = f"{section_label} > " if section_label else ''
                            label = f"{prefix}{top_label} {int(first_cell) + 1}".strip()
                    if not label:
                        continue
                    same_row_key = (t_idx, r_idx, label)
                    if same_row_key in same_row_label_seen:
                        continue
                    same_row_label_seen.add(same_row_key)

                    fill_type = 'table_data'
                    if max_cols == 2 and c_idx == 1 and left_label:
                        fill_type = 'key_value'
                    elif left_label and not top_label:
                        fill_type = 'key_value'
                    elif top_label and row_label:
                        fill_type = 'matrix'

                    context, answer_type_info = self._build_table_fill_context(table, t_idx, r_idx, c_idx, left_label, top_label, row_label, section_label)
                    fills.append({
                        'table_idx': t_idx,
                        'row': r_idx,
                        'col': c_idx,
                        'label': label,
                        'type': fill_type,
                        'context': context,
                        'answer_type': answer_type_info,
                        'nearby': self._table_context_excerpt(table, r_idx, c_idx),
                        'left_label': left_label,
                        'top_label': top_label,
                        'row_label': row_label,
                        'section_label': section_label,
                    })

        deduped = []
        seen = set()
        for item in fills:
            key = (item.get('table_idx'), item.get('row'), item.get('col'), item.get('label'))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)

        return deduped

    # ─────────────────────────────────────────────
    # 필드 자동 감지
    # ─────────────────────────────────────────────

    def detect_fields(self, text, sections=None):
        """양식 내 작성 필요 영역을 자동 감지한다."""
        fields = []
        seen = set()

        patterns = [
            (r'\[([^\[\]]{1,30})\]', 'bracket'),
            (r'[《【]([^》】]{1,30})[》】]', 'special_bracket'),
            (r'_{3,}(?:\(([^)]{1,30})\))?', 'underline'),
            (r'[□☐]\s*([^\s□☐]{1,30})', 'checkbox'),
            (r'\[\s*\]\s*([^\[\]\n]{1,30})', 'text_checkbox'),
            (r'\(\s{3,}\)', 'paren_blank'),
            (r'([가-힣a-zA-Z]{1,15})\s*[:\uff1a]\s*$', 'colon_blank'),
            (r'[※\*]\s*(.{1,30}(?:기입|작성|입력|기재|표기))', 'instruction'),
        ]

        for pattern, ftype in patterns:
            for match in re.finditer(pattern, text, re.MULTILINE):
                name = match.group(1) if match.lastindex and match.group(1) else match.group(0)
                name = name.strip()
                if not name or name in seen:
                    continue
                seen.add(name)

                hint = ''
                if ftype == 'bracket':
                    hint = f'[{name}] 필드를 채워주세요'
                elif ftype == 'underline':
                    hint = '빈칸을 채워주세요'
                    if match.group(1) if match.lastindex else None:
                        name = match.group(1)
                        hint = f'{name}을(를) 입력하세요'
                elif ftype == 'checkbox':
                    hint = f'체크박스: {name}'
                elif ftype == 'colon_blank':
                    hint = f'{name} 항목을 입력하세요'
                elif ftype == 'instruction':
                    hint = f'지시사항: {name}'

                fields.append({
                    'name': name, 'type': ftype,
                    'hint': hint, 'position': match.start()
                })

        if sections:
            for sec in sections:
                content = sec.get('content', '').strip()
                title = sec.get('title', '').strip()
                if title and not content:
                    key = f'section:{title}'
                    if key not in seen:
                        seen.add(key)
                        fields.append({
                            'name': title, 'type': 'empty_section',
                            'hint': f'"{title}" 섹션의 내용을 작성해주세요',
                            'position': -1
                        })

        fields.sort(key=lambda f: f['position'])
        return fields

    # ─────────────────────────────────────────────
    # 양식 구조 설명 생성 (AI 프롬프트용)
    # ─────────────────────────────────────────────

    def build_form_description(self, tables, sections, fields, raw_text=''):
        """양식의 전체 구조를 AI가 이해할 수 있는 텍스트로 변환한다."""
        parts = []
        table_fills = self._analyze_table_fills(tables)

        if tables:
            for t_idx, table in enumerate(tables):
                if not table:
                    continue
                parts.append(f"\n### 테이블 {t_idx + 1} ({len(table)}행 × {self._table_col_count(table)}열)")
                parts.append(self._table_to_markdown(table, max_rows=25))

        if table_fills:
            parts.append("\n### 테이블에서 실제로 채워야 하는 칸 추정")
            for fill in table_fills[:40]:
                answer_type = fill.get('answer_type', {})
                constraint = answer_type.get('constraint', '') if isinstance(answer_type, dict) else ''
                choices = answer_type.get('choices', []) if isinstance(answer_type, dict) else []
                # context 첫 줄만 사용 (마크다운 스니펫은 표 전체 섹션에 이미 포함됨)
                context_summary = str(fill.get('context', '')).split('\n')[0].strip()
                line = f"- {fill.get('label', '')} ({fill.get('type', '')}): {context_summary}"
                if constraint:
                    line += f" ⚠ {constraint}"
                if choices:
                    line += f" [선택지: {', '.join(choices)}]"
                parts.append(line)

        if sections:
            parts.append("\n### 문서 섹션")
            for sec in sections:
                title = sec.get('section_title', sec.get('title', ''))
                content = (sec.get('content', '') or '').strip()
                if content:
                    preview = content[:300].replace('\n', ' ')
                    parts.append(f"- [{title}]: {preview}{'...' if len(content) > 300 else ''}")
                else:
                    parts.append(f"- [{title}]: **[내용 작성 필요]**")

        if fields:
            parts.append("\n### 감지된 필드/빈칸")
            for f in fields[:30]:
                parts.append(f"- {f.get('name', '')} ({f.get('type', '')}): {f.get('hint', '')}")

        if not tables and not sections and raw_text:
            parts.append("\n### 원문 텍스트 (일부)")
            parts.append(raw_text[:2500])

        return '\n'.join(parts) if parts else '(양식 구조 정보를 추출할 수 없음)'

    def _table_cell(self, table, row_idx, col_idx):
        if row_idx < 0 or row_idx >= len(table):
            return ''
        row = table[row_idx] or []
        if col_idx < 0 or col_idx >= len(row):
            return ''
        return str(row[col_idx] or '').strip()

    def _normalize_table_text(self, text):
        return re.sub(r'\s+', ' ', str(text or '')).strip()

    def _is_blank_like_cell(self, text):
        clean = self._normalize_table_text(text)
        if not clean:
            return True
        if re.match(r'^[\-_\.·•※○◯□☐Xx\s]{2,}$', clean):
            return True
        if re.match(r'^[\(\[]?[\s_\-]{2,}[\)\]]?$', clean):
            return True
        if re.match(r'^(미정|추후작성|작성예정|입력필요|기재)$', clean):
            return True
        return False

    def _is_generic_placeholder_value(self, text):
        clean = self._normalize_table_text(text).lower()
        if not clean:
            return False
        if 'xx' in clean or '○○' in clean or 'ㅇㅇ' in clean:
            return True
        if any(token in clean for token in ['활동 계획에 따라', '참석자 얼굴', '첨부 필', '기재하세요']):
            return True
        placeholder_tokens = [
            '성명', '이름', '학과', '학과(부)', '학번', '서명', '전공', '소속', '직책',
            '예시', '예)', 'sample', '샘플', '입력', '작성', '기재', '멘토 이름', '멘티 이름'
        ]
        return clean in placeholder_tokens or any(token in clean for token in ['예시', 'sample', '샘플'])

    def _is_replaceable_sample_cell(self, table, row_idx, col_idx, text, left_label, top_label, row_label, section_label):
        clean = self._normalize_table_text(text)
        if not clean:
            return False
        if col_idx == 0:
            return False
        if self._is_structural_header_row(table, row_idx):
            return False
        if row_idx > 1 and col_idx > 0 and left_label and clean == self._normalize_table_text(left_label):
            # 병합된 섹션 제목 행은 python-docx에서 같은 텍스트가 여러 셀처럼 보인다.
            # 이런 행을 값 셀로 오인하면 "활동 목표" 같은 구분 제목이 본문으로 덮인다.
            row_values = {
                self._normalize_table_text(cell)
                for cell in (table[row_idx] or [])
                if self._normalize_table_text(cell)
            }
            if len(row_values) == 1:
                return False
            return True
        return self._is_generic_placeholder_value(clean)

    def _can_overwrite_cell_text(self, text):
        clean = self._normalize_table_text(text)
        if not clean:
            return True
        if self._is_blank_like_cell(clean) or self._is_generic_placeholder_value(clean):
            return True
        if re.search(r'(\[[^\]]{1,30}\]|[《【][^》】]{1,30}[》】]|_{3,})', clean):
            return True
        return False

    def _is_fill_candidate_cell(self, table, row_idx, col_idx, text, left_label='', top_label='', row_label='', section_label=''):
        clean = self._normalize_table_text(text)
        if self._is_structural_header_row(table, row_idx):
            return False
        if col_idx == 0 and clean and self._is_label_like_cell(clean):
            return False
        return self._is_blank_like_cell(text) or self._is_replaceable_sample_cell(table, row_idx, col_idx, text, left_label, top_label, row_label, section_label)

    def _is_structural_header_row(self, table, row_idx):
        """성명/학과/학번/서명 같은 열 제목 행은 작성 대상에서 제외한다."""
        if row_idx < 0 or row_idx >= len(table):
            return False
        row = table[row_idx] or []
        cells = [self._normalize_table_text(cell) for cell in row]
        non_empty = [cell for cell in cells if cell]
        if len(non_empty) < 2:
            return False

        def compact(text):
            return re.sub(r'[\s\.\:：·\-\_\(\)\[\]<>|│/]', '', str(text or '')).lower()

        header_keys = {
            '구분', '성명', '이름', '학과부', '학과', '전공', '학번', '서명',
            '차수', '활동내용', '내용', '비고', '날짜', '시간', '장소'
        }
        structural = 0
        for cell in non_empty:
            c = compact(cell)
            if c in header_keys:
                structural += 1
            elif any(key in c for key in ['성명', '학과', '학번', '서명']):
                structural += 1
        return structural >= 2

    def _is_label_like_cell(self, text):
        clean = self._normalize_table_text(text)
        if not clean or self._is_blank_like_cell(clean):
            return False
        if len(clean) > 60:
            return False
        if re.match(r'^[0-9\-\.:/ ]+$', clean):
            return False
        return True

    def _find_left_label(self, table, row_idx, col_idx):
        for idx in range(col_idx - 1, -1, -1):
            cell = self._table_cell(table, row_idx, idx)
            if self._is_label_like_cell(cell):
                return cell
        return ''

    def _find_top_label(self, table, row_idx, col_idx):
        for idx in range(row_idx - 1, -1, -1):
            cell = self._table_cell(table, idx, col_idx)
            if self._is_label_like_cell(cell):
                return cell
        return ''

    def _find_row_label(self, table, row_idx, col_idx):
        row = table[row_idx] if row_idx < len(table) else []
        for idx, cell in enumerate(row):
            if idx == col_idx:
                continue
            if self._is_label_like_cell(cell):
                return self._normalize_table_text(cell)
        return ''

    def _find_section_label(self, table, row_idx):
        for idx in range(row_idx, -1, -1):
            row = table[idx] if idx < len(table) else []
            non_empty = [self._normalize_table_text(cell) for cell in row if self._normalize_table_text(cell)]
            if len(non_empty) == 1 and self._is_label_like_cell(non_empty[0]):
                return non_empty[0]
        return ''

    def _base_row_group_label(self, table, row_idx):
        row = table[row_idx] if row_idx < len(table) else []
        for cell in row:
            cell_text = self._normalize_table_text(cell)
            if self._is_label_like_cell(cell_text):
                return cell_text
        return self._find_section_label(table, row_idx)

    def _compose_table_fill_label(self, left_label, top_label, row_label, section_label, row_group='', row_index=0, row_group_count=0):
        left_label = self._normalize_table_text(left_label)
        top_label = self._normalize_table_text(top_label)
        row_label = self._normalize_table_text(row_label)
        section_label = self._normalize_table_text(section_label)
        row_group = self._normalize_table_text(row_group)

        row_prefix = row_group or row_label or left_label or section_label

        # ── 반복 행 처리: "구분 > 헤더 N" 형식 ──
        # 같은 row_prefix가 여러 번 등장 → 번호 붙이기
        if row_group_count > 1 and row_prefix:
            # "멘티 > 성명 1" 처럼 top_label 뒤에 번호 붙이기
            if top_label:
                return f"{row_prefix} > {top_label} {row_index}".strip()
            else:
                return f"{row_prefix} {row_index}".strip()

        primary = ''
        if top_label and row_prefix:
            primary = f"{row_prefix} > {top_label}".strip()
        elif left_label and top_label:
            primary = f"{left_label} > {top_label}".strip()
        elif row_prefix:
            primary = row_prefix
        elif top_label:
            primary = top_label

        extras = []
        for item in [left_label, top_label, row_label, section_label]:
            if not item or item == primary or item in primary or primary in item:
                continue
            if item not in extras:
                extras.append(item)
        if extras:
            return f"{primary} ({' / '.join(extras)})".strip()
        return primary.strip()

    def _infer_answer_type_from_label(self, label_text):
        """레이블 텍스트를 분석해 기대하는 답변 타입과 제약을 추론한다."""
        label = self._normalize_table_text(label_text).strip()
        if not label:
            return {}

        result = {}

        # (A/B/C) 패턴 → 선택지
        choice_match = re.search(r'[(\[（【]([^)\]）】]{1,40})[)\]）】]', label)
        if choice_match:
            inner = choice_match.group(1)
            # 슬래시로 구분된 선택지가 있으면
            if '/' in inner or '·' in inner or ',' in inner:
                sep = '/' if '/' in inner else ('·' if '·' in inner else ',')
                choices = [c.strip() for c in inner.split(sep) if c.strip()]
                if 2 <= len(choices) <= 6:
                    result['type'] = 'choice'
                    result['choices'] = choices
                    result['constraint'] = f"반드시 다음 중 하나만 선택해 기입: {', '.join(choices)}"
                    return result

        lower = label.lower()
        compact = re.sub(r'\s+', '', lower)

        # 날짜 관련
        date_keywords = ['날짜', '일자', '작성일', '보고일', '제출일', '방문일', '기간', '일시', '연월일']
        if any(k in compact for k in date_keywords):
            result['type'] = 'date'
            result['constraint'] = '날짜 형식으로 기입 (예: 2026년 4월 21일 또는 2026-04-21)'
            return result

        # 과목/강의명
        course_keywords = ['교과목', '과목명', '과목', '강의', '수업명', '교과']
        if any(k in compact for k in course_keywords):
            result['type'] = 'course_name'
            result['constraint'] = '수강 과목명 또는 강의명을 기입 (사람 이름이 아님)'
            return result

        # 팀명은 괄호 안 멘토 이름까지 함께 쓸 수 있으므로 사람 이름 칸과 분리한다.
        if '팀명' in compact or compact.endswith('팀'):
            result['type'] = 'team_name'
            result['constraint'] = '팀명 또는 팀명(대표/멘토 이름)을 기입'
            return result

        # 사람 이름
        name_keywords = ['성명', '이름', '담당자', '작성자', '멘토명', '멘티명', '지도교수', '학생명']
        if any(k in compact for k in name_keywords):
            result['type'] = 'person_name'
            result['constraint'] = '사람 이름을 기입'
            return result

        # 학번/번호
        id_keywords = ['학번', '사원번호', '학생번호', '번호']
        if any(k in compact for k in id_keywords):
            result['type'] = 'student_id'
            result['constraint'] = '학번 또는 ID 번호를 기입 (숫자)'
            return result

        # 학과/전공
        dept_keywords = ['학과', '전공학과', '소속', '부서', '학과(부)']
        if any(k in compact for k in dept_keywords):
            result['type'] = 'department'
            result['constraint'] = '학과명 또는 부서명을 기입'
            return result

        # 서명 영역
        if '서명' in compact or '사인' in compact:
            result['type'] = 'signature'
            result['constraint'] = '서명란 — 빈칸으로 두거나 "서명 예정" 표기'
            return result

        # 숫자/점수
        score_keywords = ['점수', '점', '성적', '평점', '횟수', '시간', '시수', '학점']
        if any(k in compact for k in score_keywords):
            result['type'] = 'number'
            result['constraint'] = '숫자 값을 기입'
            return result

        return result

    def _build_table_fill_context(self, table, table_idx, row_idx, col_idx, left_label, top_label, row_label, section_label):
        header_parts = []
        if section_label:
            header_parts.append(f"구역: {section_label}")
        if top_label:
            header_parts.append(f"열 헤더: {top_label}")
        if left_label:
            header_parts.append(f"행 레이블: {left_label}")
        if row_label and row_label not in [left_label, top_label, section_label]:
            header_parts.append(f"행 값: {row_label}")
        position = f"테이블{table_idx + 1} [{row_idx + 1}행/{col_idx + 1}열]"
        context_summary = position + ((' | ' + ' > '.join(header_parts)) if header_parts else '')

        # 표 내 위치 마크다운 스니펫 (AI가 공간 구조 파악)
        md_snippet = self._table_to_markdown_with_target(table, row_idx, col_idx, window=2)

        # 레이블 기반 답변 타입 추론
        candidate_labels = [left_label, top_label, row_label, section_label]
        type_info = {}
        for lbl in candidate_labels:
            if lbl:
                info = self._infer_answer_type_from_label(lbl)
                if info:
                    type_info = info
                    break

        if type_info.get('constraint'):
            context_summary += f" | 기입 규칙: {type_info['constraint']}"

        if md_snippet:
            context_summary += f"\n{md_snippet}"

        return context_summary, type_info

    def _table_context_excerpt(self, table, row_idx, col_idx):
        snippets = []
        start = max(0, row_idx - 1)
        end = min(len(table), row_idx + 2)
        for idx in range(start, end):
            row = table[idx] if idx < len(table) else []
            trimmed = []
            for c_idx, cell in enumerate(row[:8]):
                cell_text = self._normalize_table_text(cell)
                if c_idx == col_idx and idx == row_idx:
                    trimmed.append('[현재 빈칸]')
                else:
                    trimmed.append(cell_text or '[빈칸]')
            snippets.append(f"{idx + 1}행: {' | '.join(trimmed)}")
        return ' || '.join(snippets)

    # ─────────────────────────────────────────────
    # 섹션/파싱 유틸리티
    # ─────────────────────────────────────────────

    def create_sections_from_template(self, template_id):
        """템플릿의 파일을 파싱하여 섹션 목록을 반환한다."""
        doc_struct = self.root.doc
        template = doc_struct.get_template(template_id)
        if not template:
            raise Exception("템플릿을 찾을 수 없습니다")

        file_path = template.get('file_path', '')
        if not file_path or not os.path.exists(file_path):
            return [{'section_key': 'main', 'section_title': '본문', 'content': '', 'sort_order': 0}]

        result = self.parse(file_path)
        sections = []
        for idx, sec in enumerate(result.get('sections', [])):
            key = re.sub(r'[^a-zA-Z0-9가-힣]', '_', sec['title']).lower()
            key = re.sub(r'_+', '_', key).strip('_')
            if not key:
                key = f'section_{idx}'
            sections.append({
                'section_key': key,
                'section_title': sec['title'],
                'content': sec.get('content', ''),
                'sort_order': idx
            })

        # table_fills가 있으면 섹션을 보완한다
        table_fills = result.get('table_fills', [])
        if table_fills:
            extra = self.infer_sections_from_table_fills(table_fills)
            existing_titles = {s['section_title'] for s in sections}
            for sec in extra:
                if sec['section_title'] not in existing_titles:
                    sections.append(sec)
                    existing_titles.add(sec['section_title'])

        return sections or [{'section_key': 'main', 'section_title': '본문', 'content': '', 'sort_order': 0}]

    def infer_sections_from_table_fills(self, table_fills):
        """table_fills 라벨 목록으로부터 본문/결론 섹션을 도출한다.

        라벨 패턴:
          "멘토 > 성명"        → [서두] (헤더 → 건너뜀)
          "1주차 > 수업내용 1" → prefix=1주차 → 본문 섹션 "1주차 활동"
          "종합평가"           → [결론] 섹션
        """
        HEADER_KEYWORDS = re.compile(
            r'멘토|멘티|참여자|팀원|성명|학번|학과|학부|서명|구분|날짜|기간|시간|장소|교수|지도'
        )
        CONCLUSION_KEYWORDS = re.compile(
            r'종합|총평|소견|성취|평가|결론|결과|피드백|특이|비고'
        )
        BODY_KEYWORDS = re.compile(
            r'주차|회차|차시|활동|내용|수업|학습|진행|일지|보고|계획|이슈|논의'
        )

        # 1. prefix별 그룹핑
        groups = {}   # prefix → [label, ...]
        for fill in table_fills:
            label = (fill.get('label') or '').strip()
            if not label:
                continue
            # "A > B" 형태이면 A가 prefix
            if ' > ' in label:
                prefix = label.split(' > ')[0].strip()
            else:
                prefix = label
            # 번호 제거: "1주차 1" → "1주차"
            prefix_base = re.sub(r'\s+\d+$', '', prefix).strip()
            groups.setdefault(prefix_base, []).append(label)

        # 2. 그룹별 섹션 분류
        header_groups = set()
        body_groups   = []  # (prefix, sort_key)
        conclusion_groups = []
        seen_body = set()

        for prefix, labels in groups.items():
            if HEADER_KEYWORDS.search(prefix):
                header_groups.add(prefix)
                continue
            if CONCLUSION_KEYWORDS.search(prefix):
                if prefix not in seen_body:
                    conclusion_groups.append(prefix)
                    seen_body.add(prefix)
                continue
            if BODY_KEYWORDS.search(prefix) or any(BODY_KEYWORDS.search(l) for l in labels):
                if prefix not in seen_body:
                    # 정렬 키: 앞에 숫자가 있으면 숫자 순, 아니면 문자 순
                    num = re.match(r'^(\d+)', prefix)
                    sort_key = (int(num.group(1)) if num else 999, prefix)
                    body_groups.append((prefix, sort_key))
                    seen_body.add(prefix)

        body_groups.sort(key=lambda x: x[1])

        # 3. section_def 생성
        sections = []
        sort_order = 100  # 서두(0~99) 이후로 배치

        for prefix, _ in body_groups:
            # 해당 prefix에 속하는 라벨로 hint 구성
            related = [l for l in groups.get(prefix, [])]
            body_labels = [re.sub(r'.+?\s*>\s*', '', l).strip() for l in related]
            body_labels_unique = list(dict.fromkeys(body_labels))[:6]
            hint = f"{prefix} 활동 항목: " + ', '.join(body_labels_unique)

            key = re.sub(r'[^a-zA-Z0-9가-힣]', '_', prefix).lower()
            key = re.sub(r'_+', '_', key).strip('_') or f'section_{sort_order}'

            sections.append({
                'section_key': key,
                'section_title': prefix,
                'content': hint,
                'sort_order': sort_order,
                'source': 'table_fill'
            })
            sort_order += 1

        for prefix in conclusion_groups:
            key = re.sub(r'[^a-zA-Z0-9가-힣]', '_', prefix).lower()
            key = re.sub(r'_+', '_', key).strip('_') or f'conclusion_{sort_order}'
            sections.append({
                'section_key': key,
                'section_title': prefix,
                'content': f'{prefix}: 전체 활동에 대한 종합 평가 및 소견',
                'sort_order': sort_order + 50,
                'source': 'table_fill'
            })

        return sections

    def parse_uploaded_file(self, file_path):
        """업로드된 파일을 파싱하여 섹션, 필드, 테이블 채움 정보를 반환."""
        result = self.parse(file_path)

        fields_schema = json.dumps(result.get('fields', []), ensure_ascii=False)
        sections = []
        for idx, sec in enumerate(result.get('sections', [])):
            key = re.sub(r'[^a-zA-Z0-9가-힣]', '_', sec['title']).lower()
            key = re.sub(r'_+', '_', key).strip('_')
            if not key:
                key = f'section_{idx}'
            sections.append({
                'section_key': key,
                'section_title': sec['title'],
                'content': sec.get('content', ''),
                'sort_order': idx
            })

        return {
            'sections': sections,
            'fields': result.get('fields', []),
            'fields_schema': fields_schema,
            'text': result.get('text', ''),
            'capabilities': result.get('capabilities', {}),
            'placeholders': result.get('placeholders', []),
            'table_fills': result.get('table_fills', []),
            'tables': result.get('tables', []),
            'metadata': result.get('metadata', {}),
            'converted_docx_path': result.get('converted_docx_path', ''),
            'editable_docx_path': result.get('editable_docx_path', '')
        }

    # ─────────────────────────────────────────────
    # 템플릿 채우기 (DOCX 원본 유지)
    # ─────────────────────────────────────────────

    def fill_template_document(self, template_path, output_path, field_values=None, section_values=None, preserve_layout=True, layout_options=None):
        """양식 파일에 값을 채워서 출력 DOCX를 생성한다.
        HWP/PDF인 경우 DOCX 변환본을 사용한다."""
        ext = os.path.splitext(template_path)[1].lower()

        # HWP/PDF → 변환된 DOCX 찾기
        if ext in ('.hwp', '.pdf', '.doc'):
            basename = os.path.splitext(template_path)[0]
            converted = basename + '_converted.docx'
            if os.path.exists(converted):
                template_path = converted
            else:
                template_path = self._convert_to_docx(template_path)

        return self._fill_docx_template(
            template_path, output_path, field_values or {}, section_values or {},
            preserve_layout=preserve_layout, layout_options=layout_options
        )

    def _fill_docx_template(self, template_path, output_path, field_values, section_values, preserve_layout=True, layout_options=None):
        """DOCX 파일의 빈칸을 채운다. 서식을 최대한 보존."""
        import docx

        document = docx.Document(template_path)

        # 1. 단락/머리말/꼬리말의 텍스트 치환
        for para in document.paragraphs:
            self._replace_runs_in_paragraph(para, field_values, section_values)

        for sec in document.sections:
            try:
                for para in sec.header.paragraphs:
                    self._replace_runs_in_paragraph(para, field_values, section_values)
            except Exception:
                pass
            try:
                for para in sec.footer.paragraphs:
                    self._replace_runs_in_paragraph(para, field_values, section_values)
            except Exception:
                pass

        # 2. 테이블 셀 채우기
        for table in document.tables:
            # 2a. 셀 내 텍스트 치환 (bracket, underline 등)
            for row in table.rows:
                for cell in row.cells:
                    for para in cell.paragraphs:
                        self._replace_runs_in_paragraph(para, field_values, {})

            table_matrix = [[cell.text.strip() for cell in row.cells] for row in table.rows]
            fill_candidates = self._analyze_table_fills([table_matrix])
            for fill in fill_candidates:
                row_idx = int(fill.get('row', -1))
                col_idx = int(fill.get('col', -1))
                if row_idx < 0 or col_idx < 0:
                    continue
                if row_idx >= len(table.rows) or col_idx >= len(table.rows[row_idx].cells):
                    continue
                fill_val = self._find_field_value(fill.get('label', ''), field_values)
                if not fill_val:
                    fill_val = self._find_field_value(fill.get('label', ''), section_values)
                if not fill_val:
                    continue
                current_text = table.rows[row_idx].cells[col_idx].text.strip()
                label_echo_placeholder = (
                    row_idx > 1 and col_idx > 0
                    and current_text
                    and fill.get('left_label')
                    and self._normalize_table_text(current_text) == self._normalize_table_text(fill.get('left_label'))
                )
                if not self._can_overwrite_cell_text(current_text) and not label_echo_placeholder:
                    continue
                # 컬럼 타입별 값 정제 (성명 칸에 학번 혼입 방지)
                top_label = (fill.get('label', '') or '').split('>')[-1].strip()
                fill_val = self._sanitize_cell_value_by_header(top_label, fill_val)
                if not fill_val:
                    continue
                self._set_cell_text(table.rows[row_idx].cells[col_idx], fill_val)

            if fill_candidates:
                continue

            # 2b. Key-Value 패턴: 라벨 셀 옆 값 셀에 삽입
            # 원본에 실제 값이 있는 셀은 보존하고, 빈칸/플레이스홀더만 채운다.
            for row in table.rows:
                cells = row.cells
                for c_idx in range(len(cells) - 1):
                    label_text = cells[c_idx].text.strip()
                    if label_text and 1 < len(label_text) < 60:
                        fill_val = self._find_field_value(label_text, field_values)
                        if fill_val and self._can_overwrite_cell_text(cells[c_idx + 1].text):
                            self._set_cell_text(cells[c_idx + 1], fill_val)

            # 2c. 헤더 행 기반: 헤더 텍스트로 매칭하여 데이터 셀 채우기
            if len(table.rows) > 1:
                header_cells = table.rows[0].cells
                headers = [c.text.strip() for c in header_cells]
                any_header = sum(1 for h in headers if h)
                if any_header >= max(1, len(headers) * 0.5):
                    # ── 같은 row_label이 반복되는 경우: 인덱스 카운터 준비 ──
                    row_label_occurrence = {}  # row_label → 누적 등장 횟수
                    for r_idx in range(1, len(table.rows)):
                        row_cells = table.rows[r_idx].cells
                        row_label_raw = row_cells[0].text.strip() if row_cells else ''
                        # 병합된 셀의 경우 이전 다른 행에서 이어지는 row_label 추적
                        if row_label_raw:
                            row_label_occurrence[row_label_raw] = row_label_occurrence.get(row_label_raw, 0) + 1
                    # row_label 총 등장 횟수: 여러 번 나오는 라벨만 인덱싱
                    row_label_multi = {k for k, v in row_label_occurrence.items() if v > 1}
                    row_label_cur_idx = {}  # row_label → 현재까지 채운 인덱스

                    for r_idx in range(1, len(table.rows)):
                        row_cells = table.rows[r_idx].cells
                        row_label_raw = row_cells[0].text.strip() if row_cells else ''
                        row_label = row_label_raw
                        if row_label_raw in row_label_multi:
                            row_label_cur_idx[row_label_raw] = row_label_cur_idx.get(row_label_raw, 0) + 1
                        cur_idx = row_label_cur_idx.get(row_label_raw, 1)

                        for c_idx in range(len(row_cells)):
                            if c_idx == 0 and row_label:
                                continue
                            if c_idx >= len(headers) or not headers[c_idx]:
                                continue
                            header_key = headers[c_idx]

                            fill_val = ''
                            if row_label and c_idx > 0:
                                # ① 인덱스 포함 키 먼저 시도: "성명(멘티) 1"
                                if row_label in row_label_multi:
                                    fill_val = self._find_field_value(
                                        f"{header_key}({row_label}) {cur_idx}", field_values)
                                # ② 기본 복합 키: "성명(멘티)"
                                if not fill_val:
                                    fill_val = self._find_field_value(
                                        f"{header_key}({row_label})", field_values)
                                    # ② 복합키 값이 여러 명인 경우 → 인덱스로 분할
                                    if fill_val and row_label in row_label_multi:
                                        parts = self._split_multi_person_value(fill_val)
                                        if len(parts) >= cur_idx:
                                            fill_val = parts[cur_idx - 1]
                            # ③ 단순 헤더 키
                            if not fill_val:
                                fill_val = self._find_field_value(header_key, field_values)

                            if fill_val:
                                if not self._can_overwrite_cell_text(row_cells[c_idx].text):
                                    continue
                                # 컬럼 타입별 값 정제
                                fill_val = self._sanitize_cell_value_by_header(header_key, fill_val)
                                if fill_val:
                                    self._set_cell_text(row_cells[c_idx], fill_val)

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        self._apply_docx_template_fidelity(document, template_path, layout_options or {}, field_values)
        self._apply_direct_table_cell_values(document, field_values)
        self._apply_default_report_page_breaks(document, layout_options or {})
        self._apply_table_spacing_controls(document, (layout_options or {}).get('table_spacings', {}))
        self._apply_direct_table_cell_layouts(document, (layout_options or {}).get('field_layouts', {}))
        # 행이 페이지 중간에서 잘리지 않게 하는 보호는 원본 레이아웃 보존 모드에서도 필요하다.
        self._postprocess_docx_tables(document)
        self._ensure_min_top_margin(document)
        if not preserve_layout:
            # 선택적 보정 모드: 원본 양식을 새로 꾸미는 상황에서만 사용한다.
            self._normalize_docx_margins(document)
        document.save(output_path)
        return output_path

    def apply_images_to_docx(self, docx_path, output_path, instance_id, placements=None):
        """저장된 이미지 배치를 DOCX에도 반영한다.

        DOCX는 PDF처럼 페이지 좌표를 안정적으로 고정하기 어렵기 때문에 라벨 배치는
        대응되는 표 값 셀에 넣고, 절대 좌표 배치는 문서 끝에 포함한다.
        """
        import docx
        from docx.shared import Inches

        if not instance_id or not os.path.exists(docx_path):
            return docx_path

        if placements is None:
            try:
                placements = self.root.graph_gen.get_placements(instance_id, detailed=True)
            except Exception:
                placements = {}
        if not placements:
            if output_path != docx_path:
                shutil.copy2(docx_path, output_path)
            return output_path

        document = docx.Document(docx_path)

        def norm(text):
            return re.sub(r'[\s\.\:：·\-\_\(\)\（\）]', '', str(text or ''))

        def image_path(filename):
            try:
                fs = wiz.project.fs("data", "uploads", "images", instance_id)
                path = fs.abspath(filename)
                return path if os.path.exists(path) else ''
            except Exception:
                return ''

        def add_picture_to_cell(cell, path):
            try:
                para = cell.add_paragraph()
                run = para.add_run()
                run.add_picture(path, width=Inches(4.0))
                return True
            except Exception:
                return False

        used = set()
        for position, items in placements.items():
            if position == '__absolute__' or not items:
                continue
            target_norm = norm(position)
            if not target_norm:
                continue
            for table in document.tables:
                matched = False
                for row in table.rows:
                    cells = row.cells
                    for c_idx, cell in enumerate(cells):
                        if target_norm not in norm(cell.text):
                            continue
                        target_cell = cells[c_idx + 1] if c_idx + 1 < len(cells) else cell
                        for item in items:
                            filename = item.get('filename') if isinstance(item, dict) else str(item)
                            path = image_path(filename)
                            if path and add_picture_to_cell(target_cell, path):
                                used.add(filename)
                        matched = True
                        break
                    if matched:
                        break
                if matched:
                    break

        absolute_items = placements.get('__absolute__', []) or []
        remaining = []
        for items in placements.values():
            for item in items:
                filename = item.get('filename') if isinstance(item, dict) else str(item)
                if filename and filename not in used and item not in absolute_items:
                    remaining.append(item)
        for item in list(absolute_items) + remaining:
            filename = item.get('filename') if isinstance(item, dict) else str(item)
            path = image_path(filename)
            if not path or filename in used:
                continue
            try:
                para = document.add_paragraph()
                run = para.add_run()
                run.add_picture(path, width=Inches(4.8))
                used.add(filename)
            except Exception:
                pass

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        document.save(output_path)
        return output_path

    def _apply_docx_template_fidelity(self, document, template_path='', layout_options=None, field_values=None):
        """HWP 변환 DOCX에서 자주 깨지는 부분을 보정한다.

        LibreOffice/HWP 변환본은 표 구조는 비교적 잘 남지만 그림 누락, 병합 제목 덮어쓰기,
        중간보고서의 빈 후반 주차 잔존 문제가 반복되어 다운로드용 DOCX에서만 후처리한다.
        """
        layout_options = layout_options if isinstance(layout_options, dict) else {}
        field_values = field_values if isinstance(field_values, dict) else {}
        self._restore_missing_template_images(document, template_path, layout_options)
        self._repair_activity_goal_rows(document, field_values)
        self._trim_empty_week_rows(document)
        self._fit_docx_tables_to_page(document)

    def _restore_missing_template_images(self, document, template_path='', layout_options=None):
        """HWP→DOCX 변환 중 빠진 첫 이미지를 문서 상단에 복구한다."""
        try:
            if getattr(document, 'inline_shapes', None) and len(document.inline_shapes) > 0:
                return
        except Exception:
            pass

        source_path = self._resolve_original_template_path(template_path, layout_options or {})
        if not source_path or not os.path.exists(source_path):
            return
        if os.path.splitext(source_path)[1].lower() != '.hwp':
            return

        tmpdir = tempfile.mkdtemp()
        try:
            image_path = self._extract_first_hwpx_image(source_path, tmpdir)
            if not image_path or not os.path.exists(image_path):
                return

            try:
                from PIL import Image
                converted = os.path.join(tmpdir, 'template-image.png')
                with Image.open(image_path) as im:
                    im.save(converted)
                image_path = converted
            except Exception:
                pass

            if not document.paragraphs:
                return
            from docx.enum.text import WD_ALIGN_PARAGRAPH
            from docx.shared import Mm, Pt
            para = document.paragraphs[0].insert_paragraph_before()
            para.alignment = WD_ALIGN_PARAGRAPH.LEFT
            try:
                para.paragraph_format.space_before = Pt(0)
                para.paragraph_format.space_after = Pt(0)
                para.paragraph_format.line_spacing = 1
            except Exception:
                pass
            para.add_run().add_picture(image_path, width=Mm(28))
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def _resolve_original_template_path(self, template_path='', layout_options=None):
        layout_options = layout_options if isinstance(layout_options, dict) else {}
        candidates = []
        raw = layout_options.get('template_file_path') or layout_options.get('uploaded_file') or ''
        if raw:
            if os.path.isabs(raw):
                candidates.append(raw)
            else:
                for parts in [
                    ("data", "uploads", "templates"),
                    ("data", "uploads", "instances"),
                    ("data", "uploads", "references")
                ]:
                    try:
                        candidates.append(wiz.project.fs(*parts).abspath(raw))
                    except Exception:
                        pass

        if template_path:
            base, ext = os.path.splitext(template_path)
            if ext.lower() == '.docx' and base.endswith('_converted'):
                original_base = base[:-10]
                for original_ext in ['.hwp', '.doc', '.pdf', '.docx']:
                    candidates.append(original_base + original_ext)

        for candidate in candidates:
            if candidate and os.path.exists(candidate):
                return candidate
        return ''

    def _extract_first_hwpx_image(self, hwp_path, tmpdir):
        hwpx_path = os.path.join(tmpdir, 'template.hwpx')
        project_root = self._project_root_for_node_tools()
        commands = []
        local_hwpx = os.path.join(project_root, 'node_modules', '.bin', 'hwpx') if project_root else ''
        if local_hwpx and os.path.exists(local_hwpx):
            commands.append([local_hwpx, 'convert:hwp', hwp_path, hwpx_path])
        npx_cmd = shutil.which('npx')
        if npx_cmd:
            commands.append([npx_cmd, 'hwpx', 'convert:hwp', hwp_path, hwpx_path])
        if not commands:
            return ''

        converted = False
        for cmd in commands:
            try:
                subprocess.run(
                    cmd,
                    cwd=project_root or os.getcwd(), capture_output=True, text=True, timeout=60
                )
                if os.path.exists(hwpx_path):
                    converted = True
                    break
            except Exception:
                continue
        if not converted:
            return ''
        if not os.path.exists(hwpx_path):
            return ''

        try:
            with zipfile.ZipFile(hwpx_path) as zf:
                names = [
                    name for name in zf.namelist()
                    if name.lower().startswith('bindata/')
                    and os.path.splitext(name)[1].lower() in ['.png', '.jpg', '.jpeg', '.gif', '.bmp']
                ]
                if not names:
                    return ''
                names.sort(key=lambda name: zf.getinfo(name).file_size, reverse=True)
                name = names[0]
                ext = os.path.splitext(name)[1].lower() or '.png'
                out_path = os.path.join(tmpdir, f'first-image{ext}')
                with zf.open(name) as src, open(out_path, 'wb') as dst:
                    shutil.copyfileobj(src, dst)
                return out_path
        except Exception:
            return ''

    def _project_root_for_node_tools(self):
        candidates = []
        try:
            candidates.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))
        except Exception:
            pass
        candidates.extend([os.getcwd(), '/opt/app/project/main', '/mnt/data/wiz/project/main'])
        for candidate in candidates:
            if candidate and os.path.exists(os.path.join(candidate, 'package.json')):
                return candidate
        return os.getcwd()

    def _repair_activity_goal_rows(self, document, field_values):
        """병합 제목인 '활동 목표'가 본문 값으로 덮이는 경우를 복구한다."""
        if not isinstance(field_values, dict) or not field_values:
            return

        goal_text = self._compose_activity_goal_text(field_values)
        if not goal_text:
            return

        for table in document.tables:
            try:
                table_text = re.sub(r'\s+', '', table.cell(0, 0).text or '')
            except Exception:
                table_text = ''
            if '튜터링전공' not in table_text and '외국어및목적' not in table_text:
                continue

            label_idx = None
            for idx, row in enumerate(table.rows):
                row_text = re.sub(r'\s+', '', ' '.join(cell.text for cell in row.cells))
                if '멘토링교과목' in row_text:
                    label_idx = idx + 1
                    break
            if label_idx is None or label_idx >= len(table.rows):
                continue

            self._set_unique_row_text(table.rows[label_idx], '활동 목표')
            if label_idx + 1 < len(table.rows):
                self._set_unique_row_text(table.rows[label_idx + 1], goal_text)
            break

    def _compose_activity_goal_text(self, field_values):
        goal1 = str(field_values.get('활동 목표 1') or field_values.get('활동목표 1') or '').strip()
        goal2 = str(
            field_values.get('활동 목표 > 활동 목표 2')
            or field_values.get('활동 목표 2')
            or field_values.get('활동목표 2')
            or ''
        ).strip()
        combined = str(field_values.get('활동 목표') or field_values.get('활동목표') or '').strip()
        parts = []
        for value in [goal1, goal2]:
            if value and value not in parts:
                parts.append(value)
        if parts:
            return '\n'.join(parts)
        return combined

    def _set_unique_row_text(self, row, text):
        try:
            from docx.enum.text import WD_ALIGN_PARAGRAPH
            from docx.shared import Pt
        except Exception:
            WD_ALIGN_PARAGRAPH = None
            Pt = None
        seen = set()
        for idx, cell in enumerate(row.cells):
            key = id(cell._tc)
            if key in seen:
                continue
            seen.add(key)
            self._set_cell_text(cell, text if idx == 0 else '')
            for para in cell.paragraphs:
                try:
                    if WD_ALIGN_PARAGRAPH is not None:
                        para.alignment = WD_ALIGN_PARAGRAPH.LEFT
                    if Pt is not None:
                        para.paragraph_format.space_before = Pt(0)
                        para.paragraph_format.space_after = Pt(0)
                except Exception:
                    pass

    def _trim_empty_week_rows(self, document):
        """중간보고서처럼 1~4주차만 작성된 경우 5~8주차 빈 블록을 제거한다."""
        max_week = 0
        progress_tables = []
        attendance_tables = []

        for table in document.tables:
            try:
                title = re.sub(r'\s+', '', table.cell(0, 0).text or '')
            except Exception:
                title = ''
            if '튜터링진행과정' in title:
                progress_tables.append(table)
                for row in table.rows:
                    week = self._row_week_number(row)
                    if not week:
                        continue
                    if self._row_meaningful_text(row, start_col=2):
                        max_week = max(max_week, week)
            elif '활동참여내역' in title:
                attendance_tables.append(table)
                for row in table.rows:
                    week = self._row_week_number(row)
                    if not week:
                        continue
                    if self._row_meaningful_text(row, start_col=1):
                        max_week = max(max_week, week)

        if max_week <= 0:
            return

        for table in progress_tables:
            self._remove_rows_after_week(table, max_week, content_start_col=2)
        for table in attendance_tables:
            self._remove_rows_after_week(table, max_week, content_start_col=1)

    def _row_week_number(self, row):
        try:
            text = self._normalize_table_text(row.cells[0].text)
        except Exception:
            return 0
        match = re.fullmatch(r'\d{1,2}', text or '')
        return int(match.group(0)) if match else 0

    def _row_meaningful_text(self, row, start_col=1):
        values = []
        seen = set()
        for cell in row.cells[start_col:]:
            key = id(cell._tc)
            if key in seen:
                continue
            seen.add(key)
            text = self._normalize_table_text(cell.text)
            if text:
                values.append(text)
        return ' '.join(values).strip()

    def _remove_rows_after_week(self, table, max_week, content_start_col=1):
        for idx in range(len(table.rows) - 1, -1, -1):
            row = table.rows[idx]
            week = self._row_week_number(row)
            if not week or week <= max_week:
                continue
            # 후반 주차가 실제로 작성되어 있으면 보존한다.
            if self._row_meaningful_text(row, start_col=content_start_col):
                continue
            try:
                row._tr.getparent().remove(row._tr)
            except Exception:
                pass

    def _fit_docx_tables_to_page(self, document):
        """표 폭이 페이지 본문 폭을 넘지 않게 보정한다."""
        try:
            from docx.oxml import OxmlElement
            from docx.oxml.ns import qn
        except Exception:
            return
        try:
            section = document.sections[0]
            available_twips = int((section.page_width - section.left_margin - section.right_margin) / 635)
        except Exception:
            available_twips = 0
        if available_twips <= 0:
            return

        for table in document.tables:
            try:
                tblPr = table._tbl.tblPr
                tblW = tblPr.find(qn('w:tblW'))
                if tblW is None:
                    tblW = OxmlElement('w:tblW')
                    tblPr.append(tblW)
                current = int(tblW.get(qn('w:w'), '0') or 0)
                if current <= 0 or current > available_twips:
                    tblW.set(qn('w:w'), str(available_twips))
                    tblW.set(qn('w:type'), 'dxa')
                layout = tblPr.find(qn('w:tblLayout'))
                if layout is None:
                    layout = OxmlElement('w:tblLayout')
                    tblPr.append(layout)
                layout.set(qn('w:type'), 'fixed')
                table.autofit = False
            except Exception:
                pass

    def _normalize_docx_margins(self, document):
        """모든 섹션에 일관된 여백 적용. 부재/불일치 여백으로 인한 레이아웃 이상 방지."""
        try:
            from docx.shared import Mm
        except Exception:
            return
        for section in document.sections:
            try:
                # 여백이 0이거나 비정상적으로 작은(< 5mm) 경우에만 보정
                if not section.left_margin or section.left_margin < 1800000:  # 약 1.9cm 이하
                    section.left_margin = Mm(20)
                if not section.right_margin or section.right_margin < 1800000:
                    section.right_margin = Mm(20)
                if not section.top_margin or section.top_margin < 1800000:
                    section.top_margin = Mm(25)
                if not section.bottom_margin or section.bottom_margin < 1800000:
                    section.bottom_margin = Mm(20)
            except Exception:
                pass

    def _ensure_min_top_margin(self, document):
        """페이지 상/하단 여백이 너무 작으면 표가 붙어 보이므로 최소값을 보장한다."""
        try:
            from docx.shared import Mm
            minimum = Mm(22)
        except Exception:
            return
        for section in document.sections:
            try:
                if not section.top_margin or section.top_margin < minimum:
                    section.top_margin = minimum
            except Exception:
                pass
            try:
                if not section.bottom_margin or section.bottom_margin < minimum:
                    section.bottom_margin = minimum
            except Exception:
                pass

    def _apply_default_report_page_breaks(self, document, layout_options=None):
        """결론 표가 앞 표 끝에 애매하게 걸리지 않도록 기본 페이지 넘김을 적용한다."""
        try:
            from docx.oxml import OxmlElement
            from docx.oxml.ns import qn
        except Exception:
            return

        layout_options = layout_options if isinstance(layout_options, dict) else {}
        explicit_break_targets = set()
        raw_spacings = layout_options.get('table_spacings', {})
        if isinstance(raw_spacings, dict):
            for item in raw_spacings.values():
                if not isinstance(item, dict) or not item.get('page_break'):
                    continue
                try:
                    before_table = int(item.get('before_table') or 0)
                except Exception:
                    before_table = 0
                if before_table:
                    explicit_break_targets.add(before_table)

        def page_break_paragraph():
            p = OxmlElement('w:p')
            r = OxmlElement('w:r')
            br = OxmlElement('w:br')
            br.set(qn('w:type'), 'page')
            r.append(br)
            p.append(r)
            return p

        inserted_targets = set()
        for idx, table in enumerate(document.tables, start=1):
            try:
                first_text = table.cell(0, 0).text.strip()
            except Exception:
                first_text = ''
            compact = re.sub(r'\s+', '', first_text)
            should_break = idx > 1 and ('활동참여내역' in compact or '결론' in compact)
            if not should_break:
                continue
            if idx in explicit_break_targets:
                continue
            if idx in inserted_targets:
                continue
            try:
                table._tbl.addprevious(page_break_paragraph())
                inserted_targets.add(idx)
            except Exception:
                pass

    def _apply_table_spacing_controls(self, document, table_spacings):
        """직접 편집기에서 저장한 표 앞 간격/페이지 넘김을 DOCX에 반영한다."""
        if not isinstance(table_spacings, dict) or not table_spacings:
            return
        try:
            from docx.oxml import OxmlElement
            from docx.oxml.ns import qn
        except Exception:
            return

        by_table = {}
        for item in table_spacings.values():
            if not isinstance(item, dict):
                continue
            try:
                after_table = int(item.get('after_table') or 0)
                before_table = int(item.get('docx_before_table') or item.get('before_table') or 0)
                extra_pt = float(item.get('extra_pt') or 0)
            except Exception:
                continue
            page_break = bool(item.get('page_break', False))
            if before_table < 1 or (extra_pt <= 0 and not page_break):
                continue
            current = by_table.setdefault(before_table, {'extra_pt': 0, 'page_break': False})
            current['extra_pt'] = max(current.get('extra_pt', 0), min(extra_pt, 160))
            current['page_break'] = bool(current.get('page_break', False) or page_break)

        if not by_table:
            return

        def _spacing_paragraph(extra_pt):
            p = OxmlElement('w:p')
            pPr = OxmlElement('w:pPr')
            spacing = OxmlElement('w:spacing')
            spacing.set(qn('w:before'), str(int(extra_pt * 20)))
            spacing.set(qn('w:after'), '0')
            pPr.append(spacing)
            p.append(pPr)
            return p

        def _page_break_paragraph():
            p = OxmlElement('w:p')
            r = OxmlElement('w:r')
            br = OxmlElement('w:br')
            br.set(qn('w:type'), 'page')
            r.append(br)
            p.append(r)
            return p

        for before_table, control in sorted(by_table.items(), reverse=True):
            table_index = before_table - 1
            if table_index < 0 or table_index >= len(document.tables):
                continue
            try:
                tbl = document.tables[table_index]._tbl
                if control.get('page_break'):
                    tbl.addprevious(_page_break_paragraph())
                extra_pt = float(control.get('extra_pt') or 0)
                if extra_pt > 0:
                    tbl.addprevious(_spacing_paragraph(extra_pt))
            except Exception:
                pass

    def _apply_direct_table_cell_layouts(self, document, field_layouts):
        """직접 편집기에서 행/열 경계선을 드래그한 결과를 DOCX 표 크기에 반영한다."""
        if not isinstance(field_layouts, dict) or not field_layouts:
            return
        try:
            from docx.shared import Pt
            from docx.enum.table import WD_ROW_HEIGHT_RULE
        except Exception:
            return

        table_specs = {}
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
            if table_idx < 0 or row_idx < 0 or col_idx < 0:
                continue
            spec = table_specs.setdefault(table_idx, {'rows': {}, 'cols': {}})
            if height_pct > 0:
                spec['rows'].setdefault(row_idx, []).append(height_pct)
            if width_pct > 0:
                spec['cols'].setdefault(col_idx, []).append(width_pct)

        if not table_specs:
            return

        try:
            section = document.sections[0]
            page_width_pt = float(section.page_width.pt)
            page_height_pt = float(section.page_height.pt)
        except Exception:
            page_width_pt = 595.0
            page_height_pt = 842.0

        for table_idx, spec in table_specs.items():
            if table_idx < 0 or table_idx >= len(document.tables):
                continue
            table = document.tables[table_idx]
            try:
                table.autofit = False
                table.allow_autofit = False
            except Exception:
                pass

            for row_idx, heights in spec.get('rows', {}).items():
                if row_idx < 0 or row_idx >= len(table.rows) or not heights:
                    continue
                height_pt = page_height_pt * (sum(heights) / len(heights)) / 100
                height_pt = max(8, min(280, height_pt))
                try:
                    row = table.rows[row_idx]
                    row.height = Pt(height_pt)
                    row.height_rule = WD_ROW_HEIGHT_RULE.EXACTLY
                except Exception:
                    pass

            for col_idx, widths in spec.get('cols', {}).items():
                if col_idx < 0 or not widths:
                    continue
                width_pt = page_width_pt * (sum(widths) / len(widths)) / 100
                width_pt = max(10, min(page_width_pt, width_pt))
                try:
                    if col_idx < len(table.columns):
                        table.columns[col_idx].width = Pt(width_pt)
                except Exception:
                    pass
                for row in table.rows:
                    if col_idx >= len(row.cells):
                        continue
                    try:
                        row.cells[col_idx].width = Pt(width_pt)
                    except Exception:
                        pass

    def _apply_direct_table_cell_values(self, document, field_values):
        """직접 편집기에서 일반 표 셀을 수정한 값을 DOCX 표 셀에 반영한다."""
        if not isinstance(field_values, dict) or not field_values:
            return
        pattern = re.compile(r'^표\s*(\d+)\s+(\d+)\s*행\s+(\d+)\s*열')
        for label, value in field_values.items():
            match = pattern.match(str(label or '').strip())
            if not match:
                continue
            try:
                table_idx = int(match.group(1)) - 1
                row_idx = int(match.group(2)) - 1
                col_idx = int(match.group(3)) - 1
            except Exception:
                continue
            if table_idx < 0 or table_idx >= len(document.tables):
                continue
            table = document.tables[table_idx]
            if row_idx < 0 or row_idx >= len(table.rows):
                continue
            row = table.rows[row_idx]
            if col_idx < 0 or col_idx >= len(row.cells):
                continue
            cell = row.cells[col_idx]
            text = str(value or '')
            try:
                if text.strip():
                    self._set_cell_text(cell, text)
                else:
                    for para in cell.paragraphs:
                        for run in para.runs:
                            run.text = ''
            except Exception:
                pass

    def _postprocess_docx_tables(self, document):
        """표 처리 후 품질 개선:
        1. 각 행에 cantSplit 추가 (행이 페이지에 걸쳐 잘리지 않도록)
        2. 내용이 있는 셀의 단락 여백 정규화
        """
        try:
            from docx.oxml.ns import qn
            from docx.oxml import OxmlElement
            from docx.shared import Pt
        except Exception:
            return

        for table in document.tables:
            for row in table.rows:
                # 1. cantSplit: 행이 페이지에 걸쳐 잘리지 않도록
                try:
                    tr = row._tr
                    trPr = tr.find(qn('w:trPr'))
                    if trPr is None:
                        trPr = OxmlElement('w:trPr')
                        tr.insert(0, trPr)
                    if trPr.find(qn('w:cantSplit')) is None:
                        cantSplit = OxmlElement('w:cantSplit')
                        # 높이가 큰 행에만 적용 (작은 행에는 적용하면 레이아웃 문제)
                        row_h_el = trPr.find(qn('w:trHeight'))
                        row_h = 0
                        if row_h_el is not None:
                            try:
                                row_h = int(row_h_el.get(qn('w:val'), 0))
                            except Exception:
                                row_h = 0
                        # 행 높이가 2540 (약 4.4cm, 페이지 절반 이하) 이하일 때만 cantSplit 적용
                        if row_h == 0 or row_h < 5670:
                            trPr.append(cantSplit)
                except Exception:
                    pass

                # 2. 셀 내 단락 여백 정규화 (내용이 있는 셀에 한해서)
                for cell in row.cells:
                    cell_text = cell.text.strip()
                    if not cell_text:
                        continue
                    for para in cell.paragraphs:
                        try:
                            pf = para.paragraph_format
                            # 이미 템플릿에서 설정된 spacing이 있으면 유지, 없을 때만 0으로
                            if pf.space_before is None:
                                pf.space_before = Pt(0)
                            if pf.space_after is None:
                                pf.space_after = Pt(0)
                        except Exception:
                            pass


    def _set_cell_text(self, cell, value):
        text = str(value or '').strip()
        if not text:
            return
        if cell.paragraphs:
            first_para = cell.paragraphs[0]
            for idx, para in enumerate(cell.paragraphs):
                if idx == 0:
                    self._write_text_to_paragraph(para, text)
                else:
                    self._write_text_to_paragraph(para, '')
        else:
            cell.text = text

    def _write_text_to_paragraph(self, para, text):
        """기존 paragraph/run 서식은 유지하고 텍스트만 교체한다."""
        text = str(text or '')
        if not para.runs:
            para.add_run()
        for idx, run in enumerate(para.runs):
            if idx == 0:
                run.text = ''
                parts = text.split('\n')
                if parts:
                    run.text = parts[0]
                    for part in parts[1:]:
                        run.add_break()
                        run.add_text(part)
            else:
                run.text = ''

    def _replace_runs_in_paragraph(self, para, field_values, section_values):
        """단락의 run에서 필드를 치환. 서식 보존."""
        full_text = para.text
        if not full_text:
            return
        new_full = self._apply_field_replacements(full_text, field_values, section_values)
        if new_full == full_text:
            return

        # run 단위 치환 시도 (서식 보존)
        for run in para.runs:
            if run.text:
                replaced = self._apply_field_replacements(run.text, field_values, section_values)
                if replaced != run.text:
                    run.text = replaced

        # run 단위로 안 되면 (플레이스홀더가 run 경계에 걸린 경우) 전체 교체
        if para.text != new_full:
            if para.runs:
                self._write_text_to_paragraph(para, new_full)
            else:
                para.add_run(new_full)

    def _apply_field_replacements(self, text, field_values, section_values):
        """텍스트에서 필드 패턴을 값으로 치환한다."""
        if not text:
            return text

        replaced = text
        for key, value in field_values.items():
            safe_value = str(value or '').strip()
            if not safe_value:
                continue
            # 대괄호/특수괄호 치환
            replaced = replaced.replace(f'[{key}]', safe_value)
            replaced = replaced.replace(f'《{key}》', safe_value)
            replaced = replaced.replace(f'【{key}】', safe_value)
            # 콜론+밑줄 패턴
            pattern = re.compile(rf'({re.escape(key)}\s*[:：]\s*)_{{3,}}')
            replaced = pattern.sub(lambda match, value=safe_value: match.group(1) + value, replaced)

        for key, value in section_values.items():
            safe_value = str(value or '').strip()
            if not safe_value:
                continue
            pattern = re.compile(rf'(\b{re.escape(key)}\b\s*[:：]?\s*)$')
            if pattern.search(replaced.strip()):
                replaced = replaced + ('\n' if '\n' not in replaced[-2:] else '') + safe_value

        return replaced

    def _find_field_value(self, label, field_values):
        """필드 사전에서 라벨에 매칭되는 값을 유연하게 찾는다."""
        if not label or not field_values:
            return ''

        normalized_label = re.sub(r'[\s\.\:：·\-\_\(\)>/]', '', label)
        label_has_index = bool(re.search(r'\d+$', normalized_label))
        label_is_signature = '서명' in normalized_label or 'sign' in normalized_label.lower()
        label_is_repeated_person = label_has_index and any(key in normalized_label for key in ['멘티', '튜티', '멘토', '튜터'])
        if '활동목표' in normalized_label:
            goal2_keys = ['활동 목표 2', '활동목표 2', '활동 목표 > 활동 목표 2']
            goal1_keys = ['활동 목표 1', '활동목표 1', '활동 목표']
            wanted = goal2_keys if re.search(r'2$', normalized_label) or '활동목표2' in normalized_label else goal1_keys
            for key in wanted:
                if key in field_values and str(field_values[key]).strip():
                    return str(field_values[key])
            for key, value in field_values.items():
                key_norm = re.sub(r'[\s\.\:：·\-\_\(\)>/]', '', key)
                if key_norm and key_norm in {'활동목표1', '활동목표2'} and str(value).strip():
                    if ('2' in key_norm) == (wanted is goal2_keys):
                        return str(value)

        # 1. 정확 매칭
        if label in field_values:
            return str(field_values[label])

        # 2. 정규화 매칭 (공백/구분자 무시)
        normalized = re.sub(r'[\s\.\:：·\-\_\(\)>]', '', label)
        for key, value in field_values.items():
            key_norm = re.sub(r'[\s\.\:：·\-\_\(\)>]', '', key)
            if normalized == key_norm:
                return str(value)

        label_tokens = self._label_tokens(label)
        for key, value in field_values.items():
            key_tokens = self._label_tokens(key)
            if label_tokens and key_tokens and label_tokens == key_tokens:
                return str(value)

        # 3. "A > B N" ↔ "A B N" 형태 상호 매칭
        label_no_arrow = re.sub(r'\s*>\s*', ' ', label).strip()
        label_no_arrow_norm = re.sub(r'[\s\.\:：·\-\_\(\)]', '', label_no_arrow)
        for key, value in field_values.items():
            key_no_arrow = re.sub(r'\s*>\s*', ' ', key).strip()
            key_no_arrow_norm = re.sub(r'[\s\.\:：·\-\_\(\)]', '', key_no_arrow)
            if label_no_arrow_norm and label_no_arrow_norm == key_no_arrow_norm:
                return str(value)

        if label_is_signature or label_is_repeated_person:
            return ''

        # 4. 부분 매칭 (label이 key를 포함하거나 그 반대) — 짧은 키는 스킵
        for key, value in field_values.items():
            if len(key) >= 3 and (key in label or label in key):
                return str(value)

        return ''

    def _label_tokens(self, text):
        tokens = re.split(r'[\s\(\)\[\]\-_/]+', str(text or '').strip())
        tokens = [re.sub(r'[^0-9A-Za-z가-힣]', '', token) for token in tokens]
        tokens = [token for token in tokens if token]
        return tuple(sorted(tokens))

    def _split_multi_person_value(self, value):
        """한 칸에 여러 명이 합쳐진 값을 각 사람별로 분리한다.
        예: "홍길동, 김철수, 이영희" → ["홍길동", "김철수", "이영희"]
        """
        if not value:
            return [value]
        # 콤마·슬래시·줄바꿈으로 우선 분리
        parts = re.split(r'[,/\n]', str(value))
        # 각 파트에서 괄호 안 학번/학과 제거하여 이름만 추출 시도
        cleaned = []
        for p in parts:
            p = p.strip()
            if p:
                # 괄호 안 숫자열(학번) 또는 '학과/공학/학부' 포함 부분 제거
                p_clean = re.sub(r'\([\d\s]+\)', '', p).strip()         # (학번) 제거
                p_clean = re.sub(r'\([^)]*(?:학과|공학|학부|학원|전공)[^)]*\)', '', p_clean).strip()
                cleaned.append(p_clean if p_clean else p)
        return [c for c in cleaned if c]

    def _sanitize_cell_value_by_header(self, header_key, value):
        """헤더 컬럼 타입에 따라 값을 정제한다.
        - 성명/이름 컬럼: 이름만 (괄호 안 학번/학과/괄호 제거)
        - 학번 컬럼: 숫자만
        - 학과 컬럼: 학과명만 (이름/학번 제거)
        - 서명 컬럼: 빈 문자열
        """
        if not value or not header_key:
            return value
        h = header_key.strip()
        v = str(value).strip()
        h_compact = re.sub(r'\s+', '', h.lower())

        # 팀명 칸은 "A만받자 (변기국)"처럼 팀명과 멘토명을 함께 보존한다.
        if '팀명' in h_compact or h_compact.endswith('팀'):
            return v

        # 서명란: 항상 빈칸
        if '서명' in h_compact or 'sign' in h_compact:
            return ''

        # 학번란: 숫자만 추출
        if '학번' in h_compact or '학호' in h_compact or re.search(r'student.?id', h, re.IGNORECASE):
            nums = re.findall(r'\d{7,12}', v)
            return nums[0] if nums else re.sub(r'[^\d]', '', v)[:12]

        # 학과/전공란: 학과명만
        if any(key in h_compact for key in ['학과', '전공학과', '전공명', '학부', '학원', '부서']) or 'department' in h_compact:
            # "지능형반도체공학과"처럼 공백 없는 학과명 앞부분을 이름으로 오인하지 않는다.
            v = re.sub(r'^[가-힣]{2,4}\s+', '', v).strip()
            # 학번(7자리 이상 숫자) 제거
            v = re.sub(r'\d{7,12}', '', v).strip()
            # 괄호 제거
            v = re.sub(r'[\(\)]', '', v).strip()
            return v if v else value

        # 성명/이름란: 이름만
        if any(key in h_compact for key in ['성명', '이름', '담당', '멘토', '멘티']) or 'name' in h_compact:
            # 괄호 안 내용(학번/학과) 제거
            v = re.sub(r'\([^)]*\)', '', v).strip()
            # 남은 학번(숫자열) 제거
            v = re.sub(r'\s*\d{7,12}\s*', ' ', v).strip()
            # 학과명 제거 (공학과/학부/전공 포함 단어)
            v = re.sub(r'[가-힣]+(?:학과|공학과|학부|전공|학원)\s*', '', v).strip()
            # 쉼표 앞 첫 번째 이름만 (여러 명인 경우 건너뜀 - 이미 split에서 처리)
            if ',' in v:
                v = v.split(',')[0].strip()
            return v if v else value

        return value

    # ─────────────────────────────────────────────
    # 내부 헬퍼
    # ─────────────────────────────────────────────

    def _extract_heading_level(self, style_name):
        match = re.search(r'\d+', style_name)
        return int(match.group()) if match else 1

    def _find_docx_placeholders(self, text, source='paragraph'):
        placeholders = []
        if not text:
            return placeholders

        for match in re.finditer(r'\[([^\[\]]{1,40})\]', text):
            name = (match.group(1) or '').strip()
            if name:
                placeholders.append({'name': name, 'pattern': match.group(0), 'type': 'bracket', 'source': source})

        for match in re.finditer(r'[《【]([^》】]{1,40})[》】]', text):
            name = (match.group(1) or '').strip()
            if name:
                placeholders.append({'name': name, 'pattern': match.group(0), 'type': 'special_bracket', 'source': source})

        for match in re.finditer(r'([가-힣a-zA-Z0-9\s]{1,30})[:：]\s*_{3,}', text):
            name = (match.group(1) or '').strip()
            if name:
                placeholders.append({'name': name, 'pattern': match.group(0), 'type': 'colon_underline', 'source': source})

        return placeholders

    def _is_pdf_heading(self, line):
        line = line.strip()
        if not line or len(line) > 80:
            return False
        heading_patterns = [
            r'^(\d+\.)\s+', r'^(\d+\))\s+', r'^(제\s*\d+\s*[장절항])',
            r'^([IVXivx]+\.)\s+', r'^([가-힣]\.)\s+', r'^(\d+\.\d+\.?)\s+',
            r'^\[.{1,30}\]$',
        ]
        for pat in heading_patterns:
            if re.match(pat, line):
                return True
        return False

    def _extract_hwp_body_text(self, data):
        text_parts = []
        i = 0
        while i < len(data) - 1:
            try:
                char = data[i:i+2].decode('utf-16-le', errors='ignore')
                if char and (char.isprintable() or char in '\n\r\t'):
                    text_parts.append(char)
            except Exception:
                pass
            i += 2
        text = ''.join(text_parts)
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    def _split_text_to_sections(self, text):
        if not text.strip():
            return [{'title': '본문', 'content': '', 'type': 'body', 'level': 0}]

        sections = []
        current_section = None
        lines = text.split('\n')

        for line in lines:
            stripped = line.strip()
            if not stripped:
                if current_section:
                    current_section['content'] += '\n'
                continue
            is_heading = self._is_pdf_heading(stripped)
            if is_heading:
                if current_section:
                    current_section['content'] = current_section['content'].strip()
                    sections.append(current_section)
                current_section = {'title': stripped, 'content': '', 'type': 'heading', 'level': 1}
            elif current_section:
                if current_section['content']:
                    current_section['content'] += '\n'
                current_section['content'] += stripped
            else:
                current_section = {'title': '서두', 'content': stripped, 'type': 'preamble', 'level': 0}

        if current_section:
            current_section['content'] = current_section['content'].strip()
            sections.append(current_section)

        return sections or [{'title': '본문', 'content': text.strip(), 'type': 'body', 'level': 0}]


Model = FileParser

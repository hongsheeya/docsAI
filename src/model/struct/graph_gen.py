# =============================================================================
# graph_gen Sub-Struct — 이미지 업로드 및 그래프 생성
# =============================================================================
import io
import os
import uuid
import json
import csv

class GraphGen:
    def __init__(self, struct):
        self.struct = struct

    def _normalize_placements(self, placements):
        """구/신 포맷 배치 데이터를 상세 포맷으로 정규화한다.

        상세 포맷:
        {
            "활동 사진": [
                {"filename": "a.png", "insert_mode": "auto"}
            ]
        }
        """
        normalized = {}
        if not isinstance(placements, dict):
            return normalized

        for position, items in placements.items():
            normalized[position] = []
            if not isinstance(items, list):
                continue

            for item in items:
                if isinstance(item, str):
                    normalized[position].append({
                        'filename': item,
                        'insert_mode': 'auto'
                    })
                elif isinstance(item, dict) and item.get('filename'):
                    entry = {
                        'filename': item.get('filename'),
                        'insert_mode': item.get('insert_mode', 'auto') or 'auto'
                    }
                    for key in ['page', 'x_pct', 'y_pct', 'w_pct', 'h_pct']:
                        if key in item:
                            entry[key] = item.get(key)
                    normalized[position].append(entry)

            if not normalized[position]:
                del normalized[position]

        return normalized

    def _to_legacy_placements(self, placements):
        """프론트 호환용 {position: [filename, ...]} 포맷으로 변환"""
        legacy = {}
        normalized = self._normalize_placements(placements)
        for position, items in normalized.items():
            filenames = []
            for item in items:
                filename = item.get('filename')
                if filename and filename not in filenames:
                    filenames.append(filename)
            if filenames:
                legacy[position] = filenames
        return legacy

    # ─── 이미지 업로드 ────────────────────────────────────────
    def upload_image(self, file, instance_id):
        """이미지를 업로드하고 저장 경로를 반환"""
        fs = wiz.project.fs("data", "uploads", "images", instance_id)
        fs.makedirs("")

        file_id = str(uuid.uuid4())[:8]
        ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else 'png'
        if ext not in ['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp']:
            ext = 'png'
        saved_name = f"{file_id}.{ext}"
        filepath = fs.abspath(saved_name)
        file.save(filepath)

        return {
            'file_id': file_id,
            'filename': saved_name,
            'original_name': file.filename,
            'path': filepath,
            'relative_path': f"images/{instance_id}/{saved_name}"
        }

    def list_images(self, instance_id):
        """인스턴스에 업로드된 이미지 목록"""
        fs = wiz.project.fs("data", "uploads", "images", instance_id)
        if not fs.exists(""):
            return []
        files = fs.files()
        result = []
        for f in files:
            ext = f.rsplit('.', 1)[-1].lower() if '.' in f else ''
            if ext in ['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp']:
                result.append({
                    'filename': f,
                    'path': fs.abspath(f),
                    'relative_path': f"images/{instance_id}/{f}"
                })
        return result

    def get_image_bytes(self, instance_id, filename):
        """이미지 바이트 반환"""
        fs = wiz.project.fs("data", "uploads", "images", instance_id)
        filepath = fs.abspath(filename)
        if not os.path.exists(filepath):
            return None, None
        ext = filename.rsplit('.', 1)[-1].lower()
        mime_map = {
            'png': 'image/png', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg',
            'gif': 'image/gif', 'svg': 'image/svg+xml', 'webp': 'image/webp'
        }
        mimetype = mime_map.get(ext, 'image/png')
        with open(filepath, 'rb') as f:
            return f.read(), mimetype

    def delete_image(self, instance_id, filename):
        """이미지 삭제"""
        fs = wiz.project.fs("data", "uploads", "images", instance_id)
        filepath = fs.abspath(filename)
        if os.path.exists(filepath):
            os.remove(filepath)
            # 해당 이미지가 배치된 경우 배치 정보도 삭제
            placements = self.get_placements(instance_id, detailed=True)
            changed = False
            for pos, items in list(placements.items()):
                filtered = [item for item in items if item.get('filename') != filename]
                if len(filtered) != len(items):
                    placements[pos] = filtered
                    changed = True
                if not placements.get(pos):
                    placements.pop(pos, None)
            if changed:
                self._save_placements(instance_id, placements)
            return True
        return False

    # ─── 이미지 배치 관리 ─────────────────────────────────────
    def get_placements(self, instance_id, detailed=False):
        """이미지 배치 정보 조회

        detailed=False -> { "활동 사진": ["abc.jpg"] }
        detailed=True  -> { "활동 사진": [{"filename":"abc.jpg","insert_mode":"auto"}] }
        """
        fs = wiz.project.fs("data", "uploads", "images", instance_id)
        if not fs.exists("placements.json"):
            return {}
        try:
            raw = fs.read.json("placements.json", default={})
            normalized = self._normalize_placements(raw)
            if detailed:
                return normalized
            return self._to_legacy_placements(normalized)
        except Exception:
            return {}

    def _save_placements(self, instance_id, placements):
        """배치 정보 저장"""
        fs = wiz.project.fs("data", "uploads", "images", instance_id)
        fs.makedirs("")
        normalized = self._normalize_placements(placements)
        fs.write.json("placements.json", normalized)

    def save_placement(self, instance_id, filename, position, insert_mode='auto',
                       page=None, x_pct=None, y_pct=None, w_pct=None, h_pct=None):
        """이미지를 특정 위치에 배치"""
        placements = self.get_placements(instance_id, detailed=True)

        # 한 이미지는 하나의 위치만 갖도록 정리
        for pos, items in list(placements.items()):
            filtered = [item for item in items if item.get('filename') != filename]
            if filtered:
                placements[pos] = filtered
            else:
                placements.pop(pos, None)

        if position not in placements:
            placements[position] = []

        entry = {
            'filename': filename,
            'insert_mode': insert_mode or 'auto'
        }
        if (insert_mode or '') == 'absolute' or position == '__absolute__':
            entry.update({
                'insert_mode': 'absolute',
                'page': self._safe_number(page, 1, 1, 999, as_int=True),
                'x_pct': self._safe_number(x_pct, 8, 0, 95),
                'y_pct': self._safe_number(y_pct, 8, 0, 95),
                'w_pct': self._safe_number(w_pct, 32, 1, 100),
                'h_pct': self._safe_number(h_pct, 20, 1, 100),
            })
            position = '__absolute__'
            if position not in placements:
                placements[position] = []

        placements[position].append(entry)
        self._save_placements(instance_id, placements)
        return self._to_legacy_placements(placements)

    def _safe_number(self, value, default, min_value, max_value, as_int=False):
        try:
            number = float(value)
        except Exception:
            number = float(default)
        number = max(float(min_value), min(float(max_value), number))
        if as_int:
            return int(round(number))
        return round(number, 3)

    def remove_placement(self, instance_id, filename, position=None):
        """이미지 배치 해제"""
        placements = self.get_placements(instance_id, detailed=True)
        if position:
            if position in placements:
                placements[position] = [item for item in placements[position] if item.get('filename') != filename]
                if not placements[position]:
                    del placements[position]
        else:
            for pos, items in list(placements.items()):
                filtered = [item for item in items if item.get('filename') != filename]
                if filtered:
                    placements[pos] = filtered
                else:
                    del placements[pos]
        self._save_placements(instance_id, placements)
        return self._to_legacy_placements(placements)

    def get_image_base64(self, instance_id, filename):
        """이미지를 data URI(base64)로 반환"""
        import base64
        img_bytes, mimetype = self.get_image_bytes(instance_id, filename)
        if not img_bytes:
            return None
        b64 = base64.b64encode(img_bytes).decode('utf-8')
        return f"data:{mimetype};base64,{b64}"

    # ─── 그래프 생성 (matplotlib) ─────────────────────────────
    def generate_chart(self, chart_type, data, options=None):
        """
        차트를 생성하고 PNG 바이트를 반환
        chart_type: 'bar', 'line', 'pie', 'scatter', 'horizontal_bar'
        data: { labels: [...], values: [...], title: '...', xlabel: '...', ylabel: '...', series: [...] }
        options: { width: 8, height: 5, colors: [...] }
        """
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import matplotlib.font_manager as fm

        if options is None:
            options = {}

        width = options.get('width', 8)
        height = options.get('height', 5)
        colors = options.get('colors', None)

        # 한글 폰트 설정
        self._setup_korean_font(plt)

        fig, ax = plt.subplots(figsize=(width, height))

        labels = data.get('labels', [])
        values = data.get('values', [])
        series = data.get('series', [])
        title = data.get('title', '')
        xlabel = data.get('xlabel', '')
        ylabel = data.get('ylabel', '')
        matlab_colors = colors or ['#0072BD', '#D95319', '#EDB120', '#7E2F8E', '#77AC30', '#4DBEEE', '#A2142F']

        if chart_type == 'bar':
            if series:
                positions = list(range(len(labels)))
                series_count = max(1, len(series))
                width = 0.8 / series_count
                offset_base = (series_count - 1) / 2
                for idx, item in enumerate(series):
                    offset = (idx - offset_base) * width
                    shifted = [x + offset for x in positions]
                    ax.bar(shifted, item.get('values', []), width=width, label=item.get('name', f'시리즈 {idx+1}'), color=matlab_colors[idx % len(matlab_colors)])
                ax.set_xticks(positions)
                ax.set_xticklabels(labels)
                if len(series) > 1:
                    ax.legend()
            else:
                ax.bar(labels, values, color=matlab_colors[0])
            ax.set_xlabel(xlabel)
            ax.set_ylabel(ylabel)
        elif chart_type == 'horizontal_bar':
            if series:
                first = series[0]
                ax.barh(labels, first.get('values', []), color=matlab_colors[0], label=first.get('name', '시리즈 1'))
                if len(series) > 1:
                    ax.legend()
            else:
                ax.barh(labels, values, color=matlab_colors[0])
            ax.set_xlabel(ylabel)
            ax.set_ylabel(xlabel)
        elif chart_type == 'line':
            if series:
                for idx, item in enumerate(series):
                    ax.plot(labels, item.get('values', []), marker='o', color=matlab_colors[idx % len(matlab_colors)], linewidth=2, label=item.get('name', f'시리즈 {idx+1}'))
                if len(series) > 1:
                    ax.legend()
            else:
                ax.plot(labels, values, marker='o', color=matlab_colors[0], linewidth=2)
            ax.set_xlabel(xlabel)
            ax.set_ylabel(ylabel)
            ax.grid(True, alpha=0.35, linestyle='--')
        elif chart_type == 'pie':
            pie_colors = colors or plt.cm.Set3.colors[:len(labels)]
            ax.pie(values, labels=labels, colors=pie_colors, autopct='%1.1f%%', startangle=90)
            ax.axis('equal')
        elif chart_type == 'scatter':
            x_vals = data.get('x', values)
            y_vals = data.get('y', values)
            ax.scatter(x_vals, y_vals, color=matlab_colors[0], alpha=0.7)
            ax.set_xlabel(xlabel)
            ax.set_ylabel(ylabel)
            ax.grid(True, alpha=0.35, linestyle='--')

        if title:
            ax.set_title(title, fontsize=14, fontweight='bold', pad=12)

        if chart_type in ['bar', 'line', 'scatter', 'horizontal_bar']:
            for spine in ['top', 'right']:
                ax.spines[spine].set_visible(False)

        plt.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        plt.close(fig)
        buf.seek(0)
        return buf.getvalue()

    def generate_chart_and_save(self, chart_type, data, instance_id, options=None):
        """차트를 생성하고 파일로 저장, 경로 반환"""
        png_bytes = self.generate_chart(chart_type, data, options)

        fs = wiz.project.fs("data", "uploads", "images", instance_id)
        fs.makedirs("")

        file_id = str(uuid.uuid4())[:8]
        filename = f"chart_{file_id}.png"
        filepath = fs.abspath(filename)

        with open(filepath, 'wb') as f:
            f.write(png_bytes)

        return {
            'file_id': file_id,
            'filename': filename,
            'path': filepath,
            'relative_path': f"images/{instance_id}/{filename}",
            'size': len(png_bytes)
        }

    def ai_generate_chart(self, instance_id, prompt, user_id=None):
        """AI가 프롬프트를 분석해서 적절한 차트를 생성"""
        agent = self.struct.ai_agent
        config = agent.get_config()
        if not config:
            raise Exception("AI 설정이 없습니다.")

        system = """당신은 데이터 시각화 전문가입니다. 사용자의 요청을 분석하여 차트 데이터를 JSON으로 반환하세요.
반드시 다음 JSON 형식만 반환하세요 (설명 텍스트 없이):
{
    "chart_type": "bar|line|pie|scatter|horizontal_bar",
    "data": {
        "labels": ["항목1", "항목2", ...],
        "values": [10, 20, ...],
        "title": "차트 제목",
        "xlabel": "X축 라벨",
        "ylabel": "Y축 라벨"
    }
}"""

        try:
            result = agent._call_llm(config, system, prompt)
            # JSON 추출
            result = result.strip()
            if result.startswith('```'):
                lines = result.split('\n')
                result = '\n'.join(lines[1:-1])
            chart_config = json.loads(result)

            chart_type = chart_config.get('chart_type', 'bar')
            data = chart_config.get('data', {})

            return self.generate_chart_and_save(chart_type, data, instance_id)
        except json.JSONDecodeError:
            raise Exception("AI가 유효한 차트 데이터를 생성하지 못했습니다.")

    def _save_csv_file(self, file, instance_id):
        fs = wiz.project.fs("data", "uploads", "datasets", instance_id)
        fs.makedirs("")
        file_id = str(uuid.uuid4())[:8]
        ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else 'csv'
        if ext != 'csv':
            ext = 'csv'
        saved_name = f"dataset_{file_id}.{ext}"
        filepath = fs.abspath(saved_name)
        file.save(filepath)
        return {
            'filename': saved_name,
            'original_name': file.filename,
            'path': filepath,
            'relative_path': f"datasets/{instance_id}/{saved_name}"
        }

    def _read_csv_dataset(self, file_path):
        with open(file_path, 'r', encoding='utf-8-sig', newline='') as f:
            sample = f.read(2048)
            f.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample)
            except Exception:
                dialect = csv.excel
            rows = list(csv.reader(f, dialect))

        rows = [row for row in rows if any(str(cell).strip() for cell in row)]
        if not rows:
            raise Exception('CSV 데이터가 비어 있습니다.')

        def to_number(value):
            text = str(value or '').strip().replace(',', '')
            if text == '':
                return None
            try:
                return float(text)
            except Exception:
                return None

        first_row = rows[0]
        second_row = rows[1] if len(rows) > 1 else []
        header_like = False
        if second_row:
            first_numeric = sum(1 for cell in first_row if to_number(cell) is not None)
            second_numeric = sum(1 for cell in second_row if to_number(cell) is not None)
            if first_numeric < second_numeric:
                header_like = True

        if header_like:
            headers = [str(cell or '').strip() or f'col_{idx+1}' for idx, cell in enumerate(first_row)]
            data_rows = rows[1:]
        else:
            headers = [f'col_{idx+1}' for idx in range(len(first_row))]
            data_rows = rows

        normalized_rows = []
        for row in data_rows:
            padded = list(row) + [''] * (len(headers) - len(row))
            normalized_rows.append({headers[idx]: str(padded[idx]).strip() for idx in range(len(headers))})

        numeric_columns = []
        for header in headers:
            parsed = [to_number(row.get(header, '')) for row in normalized_rows]
            numeric_count = sum(1 for value in parsed if value is not None)
            if numeric_count >= max(2, int(len(normalized_rows) * 0.6)):
                numeric_columns.append(header)

        return {
            'headers': headers,
            'rows': normalized_rows,
            'numeric_columns': numeric_columns
        }

    def _build_default_chart_from_csv(self, dataset, prompt=''):
        headers = dataset.get('headers', [])
        rows = dataset.get('rows', [])
        numeric_columns = dataset.get('numeric_columns', [])
        if not numeric_columns:
            raise Exception('숫자 데이터 열을 찾지 못했습니다.')

        x_header = headers[0] if headers else numeric_columns[0]
        lower_prompt = str(prompt or '').lower()

        def to_number(value):
            text = str(value or '').strip().replace(',', '')
            try:
                return float(text)
            except Exception:
                return None

        chart_type = 'line'
        if any(keyword in lower_prompt for keyword in ['bar', '막대', '히스토그램']):
            chart_type = 'bar'
        elif any(keyword in lower_prompt for keyword in ['scatter', '산점도']):
            chart_type = 'scatter'
        elif any(keyword in lower_prompt for keyword in ['pie', '파이']):
            chart_type = 'pie'

        x_values = [row.get(x_header, '') for row in rows]
        if x_header in numeric_columns and len(headers) > 1:
            fallback = [header for header in headers if header not in numeric_columns]
            if fallback:
                x_header = fallback[0]
                x_values = [row.get(x_header, '') for row in rows]

        series_headers = [header for header in numeric_columns if header != x_header]
        if not series_headers:
            series_headers = numeric_columns[:1]

        series = []
        for header in series_headers[:4]:
            values = []
            labels = []
            for idx, row in enumerate(rows):
                number = to_number(row.get(header, ''))
                if number is None:
                    continue
                label = row.get(x_header, '') if x_header else ''
                label = label if label != '' else str(idx + 1)
                labels.append(label)
                values.append(number)
            if values:
                series.append({'name': header, 'values': values, 'labels': labels})

        if not series:
            raise Exception('플롯 가능한 숫자 시리즈를 찾지 못했습니다.')

        labels = series[0].get('labels', [])
        title = str(prompt or '').strip() or f"{os.path.basename(str(x_header))} 기반 실험 그래프"

        if chart_type == 'pie':
            first_series = series[0]
            return chart_type, {
                'labels': labels,
                'values': first_series.get('values', []),
                'title': title,
                'xlabel': x_header,
                'ylabel': first_series.get('name', '')
            }

        if chart_type == 'scatter':
            first_series = series[0]
            x_axis = list(range(1, len(first_series.get('values', [])) + 1))
            if x_header in numeric_columns:
                parsed_x = []
                for row in rows:
                    number = to_number(row.get(x_header, ''))
                    if number is not None:
                        parsed_x.append(number)
                if parsed_x:
                    x_axis = parsed_x[:len(first_series.get('values', []))]
            return chart_type, {
                'x': x_axis,
                'y': first_series.get('values', []),
                'title': title,
                'xlabel': x_header,
                'ylabel': first_series.get('name', '')
            }

        return chart_type, {
            'labels': labels,
            'series': [{'name': item.get('name', ''), 'values': item.get('values', [])} for item in series],
            'title': title,
            'xlabel': x_header,
            'ylabel': ', '.join([item.get('name', '') for item in series[:2]])
        }

    def generate_chart_from_csv_upload(self, file, instance_id, prompt='', user_id=None):
        saved = self._save_csv_file(file, instance_id)
        dataset = self._read_csv_dataset(saved['path'])
        chart_type, chart_data = self._build_default_chart_from_csv(dataset, prompt)
        result = self.generate_chart_and_save(chart_type, chart_data, instance_id, options={'width': 9, 'height': 5})
        result['source_csv'] = {
            'filename': saved.get('filename', ''),
            'original_name': saved.get('original_name', ''),
            'headers': dataset.get('headers', []),
            'numeric_columns': dataset.get('numeric_columns', [])
        }
        return result

    # ─── 유틸 ─────────────────────────────────────────────────
    def _setup_korean_font(self, plt):
        """matplotlib 한글 폰트 설정"""
        import matplotlib.font_manager as fm
        font_paths = [
            "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
            "/usr/share/fonts/truetype/noto/NotoSansKR-Regular.ttf",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
        ]
        for fp in font_paths:
            if os.path.exists(fp):
                try:
                    fm.fontManager.addfont(fp)
                    font_prop = fm.FontProperties(fname=fp)
                    plt.rcParams['font.family'] = font_prop.get_name()
                    break
                except Exception:
                    pass
        plt.rcParams['axes.unicode_minus'] = False


Model = GraphGen

# =============================================================================
# AI Agent Sub-Struct
# =============================================================================
# LLM API 연동, 양식 분석, 필드/섹션 생성, 채팅 등
# 양식의 구조를 이해하고 빈칸을 정확하게 채우는 전문 에이전트
# =============================================================================

import json
import datetime
import re

class AIAgent:
    def __init__(self, root):
        self.root = root

    def _openai_uses_completion_limit(self, model_name):
        normalized = (model_name or "").lower()
        return normalized.startswith(("gpt-5", "o1", "o3", "o4"))

    def _openai_token_limit_param(self, model_name, value):
        if self._openai_uses_completion_limit(model_name):
            return {"max_completion_tokens": value}
        return {"max_tokens": value}

    # ─────────────────────────────────────────────
    # 커스텀 인스트럭션 빌더
    # ─────────────────────────────────────────────

    def _build_instruction_text(self, user_id, category=None, instruction_ids=None):
        """활성 커스텀 인스트럭션을 텍스트로 조합"""
        try:
            instructions = self.root.ai.get_active_instructions(
                user_id, category, instruction_ids
            )
            if not instructions:
                return ''
            parts = []
            for inst in instructions:
                parts.append(f"- {inst['title']}: {inst['content']}")
            return '\n'.join(parts)
        except Exception:
            return ''

    # ─────────────────────────────────────────────
    # AI 설정 로드
    # ─────────────────────────────────────────────

    def get_config(self):
        """활성 AI 설정을 반환한다. 없으면 None."""
        return self.root.ai.get_active_config()

    def _task_model_name(self, task):
        return 'gpt-5.4-mini'

    def _text_is_concise(self, text):
        text = str(text or '')
        markers = ('간결', '요점만', '핵심 내용만', '짧고 명확', '짧게')
        return any(marker in text for marker in markers)

    def _is_concise_mode(self, system_prompt='', messages=None):
        parts = [str(system_prompt or '')]
        for msg in messages or []:
            if isinstance(msg, dict):
                parts.append(str(msg.get('content', '') or ''))
        return self._text_is_concise('\n'.join(parts))

    def _task_token_limit(self, task='default', concise=False):
        task = str(task or 'default').lower()
        if concise:
            limits = {
                'form_analysis': 500,
                'table_fill': 1200,
                'field_fill': 900,
                'section': 500,
                'question': 350,
                'profile': 450,
                'chat': 800,
                'default': 900,
            }
        else:
            limits = {
                'form_analysis': 900,
                'table_fill': 1800,
                'field_fill': 1400,
                'section': 900,
                'question': 500,
                'profile': 600,
                'chat': 1200,
                'default': 1200,
            }
        return limits.get(task, limits['default'])

    def _append_user_instructions(self, system, instruction_text):
        if instruction_text:
            system += f"\n\n## 사용자 커스텀 지시사항\n{instruction_text}"
            if self._text_is_concise(instruction_text):
                system += (
                    "\n\n## 간결 모드 강제 규칙\n"
                    "- 문서 칸에 바로 넣을 핵심만 씁니다.\n"
                    "- 서술형 칸과 본문 섹션은 기본 1~2문장으로 끝냅니다.\n"
                    "- 배경 설명, 반복 문장, 과한 완성도 보강은 생략합니다."
                )
        return system

    def _select_model_config(self, config, task='default'):
        """OpenAI 설정은 작업 성격에 맞춰 모델만 자동 라우팅한다."""
        if not isinstance(config, dict) or config.get('provider') != 'openai':
            return config

        target_model = self._task_model_name(task)
        if not target_model or config.get('model_name') == target_model:
            return config

        try:
            for row in self.root.ai.list_configs():
                if row.get('provider') == 'openai' and row.get('model_name') == target_model:
                    routed = self.root.ai.get_config(row.get('id', ''))
                    if routed and routed.get('api_key'):
                        return routed
        except Exception:
            pass

        routed = dict(config)
        routed['model_name'] = target_model
        return routed

    # ─────────────────────────────────────────────
    # 컨텍스트 빌드
    # ─────────────────────────────────────────────

    def build_context(self, instance_id, user_id=None):
        """문서 + 사용자 프로필 기반 컨텍스트를 조합한다."""
        instance = self.root.doc.get_instance(instance_id)
        if not instance:
            raise Exception("문서를 찾을 수 없습니다.")

        content_json = instance.get('content_json', {})
        settings_json = instance.get('settings_json', {})
        fields_schema = content_json.get('fields_schema', {})
        template_context = content_json.get('template_description', '')

        if not template_context and instance.get('template_id'):
            try:
                template = self.root.doc.get_template(instance.get('template_id'))
                if template:
                    template_context = template.get('description', '')
            except Exception:
                pass

        # 섹션 컨텍스트
        sections = self.root.doc.list_sections(instance_id)
        sections_ctx = ""
        for s in sections:
            sections_ctx += f"[{s['section_title']}]\n{s['content'][:300]}\n\n"

        # 사용자 프로필
        user_ctx = ""
        if user_id:
            try:
                profile = self.root.ai.get_profile(user_id)
                if profile and profile.get('profile_data'):
                    user_ctx = json.dumps(profile['profile_data'], ensure_ascii=False)[:1000]
            except Exception:
                pass

        # 필드 정보
        fields_info = ""
        fields = fields_schema.get('fields', []) if isinstance(fields_schema, dict) else []
        if fields:
            fields_info = ", ".join([f.get('name', '') for f in fields[:20]])

        raw_text_excerpt = ''
        if isinstance(fields_schema, dict):
            raw_text_excerpt = str(fields_schema.get('raw_text', '') or '').strip()[:5000]

        section_titles = []
        if isinstance(fields_schema, dict):
            for sec in fields_schema.get('sections', [])[:30]:
                title = str(sec.get('section_title', sec.get('title', '')) or '').strip()
                if title:
                    section_titles.append(title)

        table_fills = fields_schema.get('table_fills', []) if isinstance(fields_schema, dict) else []
        table_fill_info = []
        for fill in table_fills[:40]:
            label = str(fill.get('label', '')).strip()
            context = str(fill.get('context', '')).strip()
            # context는 위치 요약 + 마크다운 표 스니펫 포함 가능 → 첫 줄만 brief summary용으로 사용
            context_brief = context.split('\n')[0] if context else ''
            answer_type = fill.get('answer_type', {})
            constraint = answer_type.get('constraint', '') if isinstance(answer_type, dict) else ''
            choices = answer_type.get('choices', []) if isinstance(answer_type, dict) else []
            if label:
                line = f"{label}: {context_brief}"
                if constraint:
                    line += f" [규칙: {constraint}"
                    if choices:
                        line += f" → {' / '.join(choices)}"
                    line += "]"
                table_fill_info.append(line)

        return {
            'doc_title': instance.get('title', ''),
            'template_title': content_json.get('template_title', ''),
            'template_context': template_context,
            'guide_notes': settings_json.get('guide_notes', ''),
            'report_items': settings_json.get('report_items', []) if isinstance(settings_json, dict) else [],
            'reference_text': settings_json.get('reference_text', ''),
            'style_reference': settings_json.get('style_reference', ''),
            'sections_context': sections_ctx[:3000],
            'user_profile': user_ctx,
            'fields_info': fields_info,
            'table_fill_info': table_fill_info,
            'raw_text_excerpt': raw_text_excerpt,
            'section_titles': section_titles,
            'week_label': instance.get('week_label', ''),
            'deadline': instance.get('deadline', ''),
            'instruction_ids': settings_json.get('instruction_ids', []),
        }

    def _form_inference_protocol(self, concise=False):
        if concise:
            return """## 간결 작성 규칙
1. 각 칸의 역할만 빠르게 판단하고 바로 채울 값을 작성한다.
2. 짧은 칸은 단어/구 단위로, 서술형 칸은 1~2문장으로 작성한다.
3. 추가 설명, 배경 설명, 반복 표현은 생략한다."""

        return """## 비정형 양식 해석 프로토콜
1. 먼저 이 문서가 어떤 종류의 양식인지 스스로 가설을 세운다. 예: 활동보고서, 상담일지, 실험기록, 평가표, 신청서, 결과보고서.
2. 제목이 불명확해도 표의 행/열 제목, 상위 구역 제목, 반복되는 사람/항목 행, 예시값을 근거로 칸의 역할을 추론한다.
3. 빈칸이 아니어도 예시 텍스트·샘플 값·기재 예시가 있으면 실제 작성 대상일 수 있다고 본다.
4. 섹션명이 일반적이지 않아도 문서 전체 구조 안에서 역할을 판단한다. 예: 개요/현황/활동내용/평가/향후계획/특이사항/서명·확인.
5. 결과는 일반적인 서두가 아니라, 해당 칸이나 섹션에 바로 들어갈 실무형 내용으로 작성한다.
6. 분량은 양식의 칸 크기와 선택된 작성 지시에 맞춘다. 짧은 칸은 간결하게, 서술형 영역도 불필요하게 늘리지 않는다.
7. 확신이 낮아도 주변 단서를 종합해 가장 그럴듯한 초안을 만들고, 정말 핵심 정보가 빠진 경우에만 추가 질문 대상으로 남긴다."""

    def _format_field_values(self, field_values, limit=25):
        if not isinstance(field_values, dict) or not field_values:
            return '(없음)'
        lines = []
        for key, value in list(field_values.items())[:limit]:
            key = str(key or '').strip()
            value = str(value or '').strip()
            if not key or not value:
                continue
            lines.append(f"- {key}: {value[:120]}")
        return '\n'.join(lines) if lines else '(없음)'

    def _combined_reference_text(self, ctx):
        parts = []
        ref = str(ctx.get('reference_text', '') or '').strip()
        style = str(ctx.get('style_reference', '') or '').strip()
        if ref:
            parts.append(ref)
        if style:
            parts.append("[선택한 기존 문서/참고자료]\n" + style)
        return "\n\n".join(parts).strip()

    def _target_terms(self, targets):
        terms = []
        stopwords = {
            '구분', '서명', '내용', '비고', '기타', '작성', '입력', '미정',
            '활동', '튜터링', '멘토', '멘티', '주차', '차수'
        }
        for target in targets or []:
            if isinstance(target, dict):
                label = str(target.get('label') or target.get('name') or target.get('title') or '')
            else:
                label = str(target or '')
            label = label.replace('>', ' ').replace('|', ' ').replace('│', ' ')
            label = label.replace('(', ' ').replace(')', ' ')
            for token in label.split():
                token = token.strip(' :：-_0123456789')
                if len(token) < 2 or token in stopwords:
                    continue
                if token not in terms:
                    terms.append(token)
        return terms[:24]

    def _reference_excerpt_for_targets(self, ctx, targets=None, limit=2200):
        text = self._combined_reference_text(ctx)
        if not text:
            return ''
        if len(text) <= limit:
            return text

        terms = self._target_terms(targets)
        snippets = []
        used_ranges = []
        for term in terms:
            pos = text.find(term)
            if pos < 0:
                continue
            start = max(0, pos - 260)
            end = min(len(text), pos + 520)
            if any(not (end < s or start > e) for s, e in used_ranges):
                continue
            snippets.append(text[start:end].strip())
            used_ranges.append((start, end))
            if sum(len(s) for s in snippets) >= limit:
                break

        if not snippets:
            return text[:limit]

        excerpt = "\n\n...\n\n".join(snippets)
        if len(excerpt) < limit * 0.6:
            excerpt = (excerpt + "\n\n...\n\n" + text[:limit - len(excerpt)]).strip()
        return excerpt[:limit]

    def _is_usable_generated_value(self, label, value):
        val = str(value or '').strip()
        if not val:
            return False
        compact = val.replace(' ', '')
        lowered = compact.lower()
        label_compact = str(label or '').replace(' ', '')
        if any(key in label_compact for key in ['활동사진', '사진첨부']):
            return False
        if '서명' in label_compact and lowered in {'서명예정', '서명', '첨부'}:
            return False
        if lowered in {'차수', '활동내용', '진행과정', '활동사진', '서명예정'}:
            return False
        invalid_tokens = (
            '[미정]', '[추가정보필요]', '미정', '미상', '정보없음', '알수없음',
            '추가정보필요', '확인필요', 'n/a', 'none', 'null'
        )
        if lowered in invalid_tokens or any(token in lowered for token in invalid_tokens[:8]):
            return False
        if val == '0' and any(key in label_compact for key in ['학번', '번호', '전화']):
            return False
        return True

    def _compact_label(self, text):
        return re.sub(r'[\s\.\:：·\-\_\(\)\[\]<>|│/]', '', str(text or '').lower())

    def sanitize_generated_fields(self, values):
        """구조 라벨/오염된 반복 인원 값을 제거해 같은 오류가 재발하지 않게 한다."""
        if not isinstance(values, dict):
            return {}

        cleaned = {}
        structural_terms = ['튜터링', '결과보고서', '구분', '성명', '학과', '학번', '서명', '차수', '활동내용']
        role_words = ['멘티', '튜티', '멘토', '튜터']

        def role_of(compact):
            if '멘토링' in compact or '튜터링' in compact:
                return ''
            for role in role_words:
                if compact.startswith(role):
                    return role
            return ''

        def is_structural_key(key, compact):
            base = re.sub(r'\d+$', '', compact)
            if base in set(role_words):
                return True
            if len(key) > 100 and sum(1 for term in structural_terms if term in compact) >= 4:
                return True
            if '서명' in compact:
                return True
            return False

        for raw_key, raw_value in values.items():
            key = str(raw_key or '').strip()
            value = str(raw_value or '').strip()
            compact = self._compact_label(key)
            if not key or not value:
                continue
            if is_structural_key(key, compact):
                continue
            if '학번' in compact and not re.search(r'\d{7,12}', value):
                continue
            detected_role = role_of(compact)
            if detected_role and not any(
                part in compact for part in ['성명', '이름', '학과', '학부', '학번', '단과대학', '학년']
            ):
                continue
            cleaned[key] = value

        indexed = {}
        for key, value in cleaned.items():
            compact = self._compact_label(key)
            m = re.search(r'(\d+)$', compact)
            role = role_of(compact)
            if not role or not m:
                continue
            idx = int(m.group(1))
            item = indexed.setdefault(role, {}).setdefault(idx, {})
            if '학번' in compact:
                item['student_no'] = value
            elif '성명' in compact or '이름' in compact:
                item['name'] = value
            elif '학과' in compact or '학부' in compact:
                item['department'] = value

        valid_index = {}
        for role, by_idx in indexed.items():
            valid = set()
            for idx, item in by_idx.items():
                has_student_no = bool(re.search(r'\d{7,12}', item.get('student_no', '')))
                has_name_and_dept = bool(item.get('name') and item.get('department'))
                if has_student_no or has_name_and_dept:
                    valid.add(idx)
            if valid:
                valid_index[role] = valid

        result = {}
        for key, value in cleaned.items():
            compact = self._compact_label(key)
            role = role_of(compact)
            m = re.search(r'(\d+)$', compact)
            if role and m and role in valid_index:
                if int(m.group(1)) not in valid_index[role]:
                    continue
            result[key] = value
        return result

    def _is_structural_fill_target(self, fill):
        label = str(fill.get('label', '') if isinstance(fill, dict) else fill or '').strip()
        if not label:
            return True
        fill_type = str(fill.get('type', '') if isinstance(fill, dict) else '')
        compact = self._compact_label(label)
        base = re.sub(r'\d+$', '', compact)
        role_labels = {'멘토', '멘티', '튜터', '튜티'}
        if base in role_labels:
            return True
        if base in {a + b for a in role_labels for b in role_labels}:
            return True
        if '멘토링교과목' in compact and '멘토링구분' in compact:
            return True
        if '활동목표' in compact and '멘토링교과목' in compact:
            return True
        if compact.startswith('차수') and any(key in compact for key in ['활동내용', '튜터링진행과정', '진행과정']):
            return True
        if compact.startswith('활동내용') and any(key in compact for key in ['튜터링진행과정', '진행과정']):
            return True
        if fill_type == 'key_value' and base in {'참석자', '참여자'}:
            return False
        if '>' not in label and base in {
            '차수', '활동내용', '참석자', '참여자', '비고', '서명',
            '성명', '학번', '학과', '학과부', '단과대학', '학년', '활동사진'
        }:
            return True
        if '>' not in label and re.match(r'^\d+\s*[^>]+$', compact):
            return True
        return False

    def _is_ignorable_missing_target(self, label, values, ctx):
        compact = self._compact_label(label)
        if not compact:
            return True
        if self._is_out_of_report_scope(label, values, ctx):
            return True
        base = re.sub(r'\d+$', '', compact)
        role_labels = {'멘토', '멘티', '튜터', '튜티'}
        if base in role_labels or base in {a + b for a in role_labels for b in role_labels}:
            return True
        if '멘토링교과목' in compact and '멘토링구분' in compact:
            return True
        if '활동목표' in compact and '멘토링교과목' in compact:
            return True
        if any(key in compact for key in ['서명', '활동사진', '사진첨부']):
            return True
        if compact in {'차수', '활동내용', '진행과정', '불참자', '비고'}:
            return True
        if compact.startswith('차수') and any(key in compact for key in ['활동내용', '튜터링진행과정', '진행과정']):
            return True
        if compact.startswith('활동내용') and any(key in compact for key in ['튜터링진행과정', '진행과정']):
            return True

        index_match = re.search(r'(\d+)$', compact)
        if index_match and any(key in compact for key in ['멘티', '튜티']):
            target_index = int(index_match.group(1))
            people = self._people_from_reference_text(self._combined_reference_text(ctx))
            mentees = [p for p in people if p.get('role') in ['멘티', '튜티']]
            if mentees and target_index > len(mentees):
                return True

        parts = [
            re.sub(r'\d+$', '', self._compact_label(part))
            for part in re.split(r'>|/|\(|\)', str(label or ''))
        ]
        parts = [part for part in parts if len(part) >= 2]
        for key, value in (values or {}).items():
            if not str(value or '').strip():
                continue
            key_compact = re.sub(r'\d+$', '', self._compact_label(key))
            for part in parts:
                if key_compact == part or key_compact.endswith(part):
                    return True
        return False

    def _report_stage(self, values, ctx):
        for key, value in (values or {}).items():
            key_text = str(key or '')
            value_text = str(value or '').strip()
            if '(중간/최종)' in key_text or '결과보고서' in key_text:
                if value_text in {'중간', '최종'}:
                    return value_text
        guide = str((ctx or {}).get('guide_notes', '') or '')
        doc_title = str((ctx or {}).get('doc_title', '') or '')
        template_title = str((ctx or {}).get('template_title', '') or '')
        combined = '\n'.join([doc_title, template_title, guide])
        if '최종' in doc_title and '중간' not in doc_title:
            return '최종'
        if '중간' in doc_title or re.search(r'1\s*[~\-]\s*4\s*주차.{0,40}중간', combined):
            return '중간'
        return ''

    def _middle_report_week_limit(self, ctx):
        guide = str((ctx or {}).get('guide_notes', '') or '')
        for pattern in [
            r'1\s*[~\-]\s*(\d+)\s*주차.{0,40}중간',
            r'중간.{0,40}?1\s*[~\-]\s*(\d+)\s*주차',
        ]:
            m = re.search(pattern, guide)
            if m:
                try:
                    return max(1, int(m.group(1)))
                except Exception:
                    pass
        return 4

    def _is_out_of_report_scope(self, label, values, ctx):
        if self._report_stage(values, ctx) != '중간':
            return False
        compact = self._compact_label(label)
        match = re.search(r'(\d+)$', compact)
        if not match:
            return False
        index = int(match.group(1))
        limit = self._middle_report_week_limit(ctx)
        if any(key in compact for key in ['주제', '진행과정', '활동사진']):
            return index > limit
        if any(key in compact for key in ['활동일자', '활동장소', '참여자', '불참자']):
            # 활동 참여내역 표는 헤더 행 때문에 첫 데이터 행 라벨이 2로 잡히는 양식이 많다.
            return index > limit + 1
        return False

    def _value_echoes_target_label(self, label, value, targets=None):
        value_compact = self._compact_label(value)
        if not value_compact or len(value_compact) > 30:
            return False
        label_compact = self._compact_label(label)
        if value_compact == label_compact:
            return True
        for target in targets or []:
            target_label = target.get('label', '') if isinstance(target, dict) else str(target or '')
            target_compact = self._compact_label(target_label)
            if target_compact and value_compact == target_compact:
                return True
        return False

    def _canonical_target_label(self, label, targets=None):
        raw = str(label or '').strip()
        if not raw:
            return raw
        label_compact = self._compact_label(raw)
        matches = []
        for target in targets or []:
            if isinstance(target, dict):
                target_label = target.get('label') or target.get('name') or ''
            else:
                target_label = str(target or '')
            target_label = str(target_label or '').strip()
            target_compact = self._compact_label(target_label)
            if not target_label or not target_compact:
                continue
            if target_compact == label_compact:
                return target_label
            if target_compact.endswith(label_compact):
                matches.append(target_label)
        return matches[0] if len(matches) == 1 else raw

    def _people_from_reference_text(self, text):
        normalized = re.sub(r'\s+', ' ', str(text or '')).strip()
        if not normalized:
            return []
        people = []
        seen_student_numbers = set()
        pattern = re.compile(
            r'(?<!\d)(\d{1,2})\s+([가-힣]{2,4})\s+(20\d{6,})\s+'
            r'(\d)\s+([가-힣A-Za-z]+대학)\s+'
            r'([가-힣A-Za-z]+(?:공학과|학과|전공|학부))'
            r'.{0,80}?(튜터|튜티|멘토|멘티)',
            re.S
        )
        for match in pattern.finditer(normalized):
            name = match.group(2).strip()
            student_no = match.group(3).strip()
            department = match.group(6).strip()
            role = match.group(7).strip()
            if not name or not student_no or student_no in seen_student_numbers:
                continue
            seen_student_numbers.add(student_no)
            people.append({
                'row': int(match.group(1)),
                'name': name,
                'student_no': student_no,
                'grade': match.group(4).strip(),
                'college': match.group(5).strip(),
                'department': department,
                'role': role
            })
        return people

    def _guess_from_reference_text(self, label, ctx):
        text = self._combined_reference_text(ctx)
        if not text:
            return ''
        label_compact = self._compact_label(label)
        index_match = re.search(r'(\d+)$', label_compact)
        target_index = int(index_match.group(1)) if index_match else 0

        def first(pattern, source_text=None):
            m = re.search(pattern, source_text if source_text is not None else text, re.MULTILINE)
            if not m:
                return ''
            return str(m.group(1)).strip(' \t:：,，/|')

        def clean_value(value):
            value = re.sub(r'\s+', ' ', str(value or '')).strip(' \t:：,，/|')
            return value.strip()

        def week_number():
            for source in [ctx.get('week_label', ''), ctx.get('doc_title', '')]:
                m = re.search(r'(\d+)\s*주차', str(source or ''))
                if m:
                    return int(m.group(1))
            return 0

        def normalized_time(value):
            return re.sub(r'\s*[:：]\s*', ':', str(value or '').strip())

        def format_activity_time(match, apply_week_offset=False):
            try:
                year = int(match.group(1))
                month = int(match.group(2))
                day = int(match.group(3))
                date_value = datetime.date(year, month, day)
                if apply_week_offset:
                    week = week_number()
                    if week > 1:
                        date_value += datetime.timedelta(days=(week - 1) * 7)
                weekdays = ['월요일', '화요일', '수요일', '목요일', '금요일', '토요일', '일요일']
                start_idx = 5 if (match.lastindex or 0) >= 6 else 4
                start = normalized_time(match.group(start_idx))
                end = normalized_time(match.group(start_idx + 1))
                return f"{date_value.year}년 {date_value.month}월 {date_value.day}일 {weekdays[date_value.weekday()]} {start} ~ {end}"
            except Exception:
                return clean_value(match.group(0))

        if '팀명' in label_compact or label_compact.endswith('팀'):
            for pattern in [
                r'팀\s*명\s*\(\s*멘토\s*이름\s*\)\s*(?:\||[:：]|\n)\s*([^\n,，]{2,80})',
                r'팀\s*명\s*(?:\||[:：]|\n)\s*([^\n,，]{2,80})',
                r'팀명\s*(?:\||[:：]|\n)\s*([^\n,，]{2,80})',
            ]:
                value = clean_value(first(pattern))
                if value:
                    return value

        people = self._people_from_reference_text(text)

        is_participant_label = (
            (label_compact in {'참여자', '참석자'} or label_compact.endswith('참여자') or label_compact.endswith('참석자'))
            and not any(key in label_compact for key in ['활동내용', '세부활동', '활동사진', '사진첨부'])
        )
        if is_participant_label:
            value = clean_value(first(r'(?:참여자|참석자)\s*(?:\||[:：]|\n)\s*([^\n]{2,120})'))
            if value and not any(skip in value for skip in ['전원이', '사진', '첨부', '필']):
                return value
            if people:
                names = [p.get('name', '') for p in people if p.get('name')]
                if names:
                    return ', '.join(names)

        if '활동시간' in label_compact or '시간' in label_compact:
            week = week_number()
            if week:
                scoped_week_pattern = (
                    rf'{week}\s*주차.{{0,120}}?'
                    r'(20\d{2})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일?'
                    r'(?:\s*[월화수목금토일]\s*요일)?\s*'
                    r'(\d{1,2}\s*[:：]\s*\d{2})\s*~\s*(\d{1,2}\s*[:：]\s*\d{2})'
                )
                m = re.search(scoped_week_pattern, text, re.S)
                if m:
                    return format_activity_time(m)
            date_pattern = (
                r'(20\d{2})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일?'
                r'(?:\s*[월화수목금토일]\s*요일)?\s*'
                r'(\d{1,2}\s*[:：]\s*\d{2})\s*~\s*(\d{1,2}\s*[:：]\s*\d{2})'
            )
            m = re.search(date_pattern, text)
            if m:
                return format_activity_time(m, apply_week_offset=True)
            return first(r'(20\d{2}[년\-.]\s*\d{1,2}[월\-.]\s*\d{1,2}일?.{0,30}\d{1,2}\s*[:：]\s*\d{2}.{0,20}\d{1,2}\s*[:：]\s*\d{2})')

        if people and any(key in label_compact for key in ['멘토', '멘티', '튜터', '튜티', '성명', '학번', '학과', '학부', '단과대학', '학년']):
            if any(key in label_compact for key in ['멘토', '튜터']):
                candidates = [p for p in people if p.get('role') in ['멘토', '튜터']]
            elif any(key in label_compact for key in ['멘티', '튜티']):
                candidates = [p for p in people if p.get('role') in ['멘티', '튜티']]
            else:
                candidates = people

            person = None
            if target_index:
                if len(candidates) >= target_index:
                    person = candidates[target_index - 1]
                else:
                    return ''
            elif candidates:
                person = candidates[0]

            if person:
                if '학번' in label_compact:
                    return person.get('student_no', '')
                if '단과대학' in label_compact:
                    return person.get('college', '')
                if '학년' in label_compact:
                    return person.get('grade', '')
                if '학과' in label_compact or '학부' in label_compact:
                    return person.get('department', '')
                if '성명' in label_compact or '이름' in label_compact:
                    return person.get('name', '')

        if '멘토링구분' in label_compact or '튜터링구분' in label_compact or '튜터링영역' in label_compact:
            if re.search(r'전공\s*교과목|전공교과목|회로이론|전기회로', text):
                return '전공'
            if re.search(r'외국어|영어|토익|토플|회화', text):
                return '외국어'

        if '교과목' in label_compact or '강의명' in label_compact:
            for pattern in [
                r'전공\s*교과목\s*[\(\[]\s*([^\)\]\n]{2,60})\s*[\)\]]',
                r'전공교과목\s*[\(\[]\s*([^\)\]\n]{2,60})\s*[\)\]]',
                r'튜터링\s*영역.{0,120}?전공\s*교과목\s*[\(\[]\s*([^\)\]\n]{2,60})\s*[\)\]]',
                r'멘토링\s*교과목[^\n]{0,40}\n\s*([^\n]{2,60})',
            ]:
                value = clean_value(first(pattern))
                if value and not any(skip in value for skip in ['외국어', '생략', '교과목']):
                    return value

        if '활동목표' in label_compact or '학습목표' in label_compact:
            goals = []
            match = re.search(
                r'학습\s*목표\s*(.*?)(?:운영\s*방법|주차별|시간\s*&\s*장소|$)',
                text,
                re.S
            )
            if match:
                for line in match.group(1).splitlines():
                    line = clean_value(line)
                    if len(line) >= 6 and line not in goals:
                        goals.append(line)
            if goals:
                if target_index and len(goals) >= target_index:
                    return goals[target_index - 1]
                return ' '.join(goals[:2])

        if any(key in label_compact for key in ['결론', '종합평가', '소감', '성과', '향후계획']):
            course = ''
            for pattern in [
                r'전공\s*교과목\s*[\(\[]\s*([^\)\]\n]{2,60})\s*[\)\]]',
                r'전공교과목\s*[\(\[]\s*([^\)\]\n]{2,60})\s*[\)\]]',
                r'(?:멘토링|튜터링)\s*교과목[^\n]{0,40}\n\s*([^\n]{2,60})',
                r'교과목\s*(?:\||[:：])\s*([^\n,，]{2,60})',
            ]:
                course = clean_value(first(pattern))
                if course and not any(skip in course for skip in ['외국어', '생략', '교과목']):
                    break
            if not course:
                course = '해당 교과목'

            stage = self._report_stage({}, ctx)
            limit = self._middle_report_week_limit(ctx) if stage == '중간' else 0
            topic_source = text
            if limit:
                next_week = re.search(rf'{limit + 1}\s*주차', text)
                if next_week:
                    topic_source = text[:next_week.start()]
            weeks = sorted({int(m.group(1)) for m in re.finditer(r'(\d+)\s*주차', topic_source)})
            if limit:
                weeks = [week for week in weeks if week <= limit]
            if weeks:
                week_phrase = f"{min(weeks)}~{max(weeks)}주차 동안" if min(weeks) != max(weeks) else f"{weeks[0]}주차 활동을 통해"
            elif limit:
                week_phrase = f"1~{limit}주차 동안"
            else:
                week_phrase = '이번 활동을 통해'

            topics = []
            topic_map = [
                ('회로 기본 개념', '회로 기본 개념'),
                ('전압', '전압·전류·저항의 관계'),
                ('옴의 법칙', '옴의 법칙'),
                ('직렬', '직렬·병렬 회로'),
                ('병렬', '직렬·병렬 회로'),
                ('등가저항', '등가저항 계산'),
                ('kcl', 'KCL·KVL'),
                ('kvl', 'KCL·KVL'),
                ('노드 전압', '노드 전압법'),
                ('메쉬 전류', '메쉬 전류법'),
                ('문제풀이', '문제 풀이 전략'),
                ('오답', '오답 점검'),
            ]
            compact_topic_source = topic_source.lower()
            for needle, display in topic_map:
                if needle.lower() in compact_topic_source and display not in topics:
                    topics.append(display)
            focus = ', '.join(topics[:5]) if topics else '핵심 개념과 문제 풀이 절차'
            return (
                f"{week_phrase} {course}의 {focus}를 단계적으로 학습하며 기본 개념과 회로 해석 절차에 대한 이해도를 높였다. "
                "멘티들은 개념 정리 후 예제 풀이와 반복 연습을 병행하면서 계산 과정에서 자주 발생하는 실수를 줄이고, 문제 유형에 맞는 접근 방법을 익혔다. "
                "특히 풀이 과정을 함께 검토하며 막히는 지점을 바로 확인한 점이 중간 활동의 주요 성과였다. "
                "이후 활동에서는 심화 문제 풀이와 오답 정리를 통해 해석 능력을 더 안정적으로 강화할 계획이다."
            )

        scoped_text = text
        if '멘티' in label_compact:
            m = re.search(r'멘\s*티', text)
            if m:
                scoped_text = text[m.start():]
        elif '멘토' in label_compact:
            m = re.search(r'멘\s*토', text)
            if m:
                scoped_text = text[m.start():m.start() + 600]

        if '학번' in label_compact:
            numbers = re.findall(r'20\d{6,}', scoped_text)
            if target_index and len(numbers) >= target_index:
                return numbers[target_index - 1]
            return numbers[0] if numbers else ''
        if '학과' in label_compact or '학부' in label_compact:
            m = re.search(r'([가-힣A-Za-z]+(?:공학과|학과|전공|학부))', scoped_text, re.MULTILINE)
            return str(m.group(1)).strip() if m else ''
        if '활동장소' in label_compact or '장소' in label_compact:
            for pattern in [
                r'활동\s*장소\s*(?:\||[:：])\s*([^\n,，]{2,60})',
                r'활동\s*장소\s*\n\s*([^\n,，]{2,60})',
                r'(?<!&\s)장소\s*(?:\||[:：])\s*([^\n,，]{2,60})',
                r'(?<!&\s)장소\s*\n\s*(?!시간\b)([^\n,，]{2,60})',
            ]:
                value = clean_value(first(pattern))
                if value and value not in {'시간', '장소'}:
                    return value
            return ''
        if '멘토' in label_compact and ('성명' in label_compact or '이름' in label_compact):
            return first(r'멘\s*토.{0,30}?([가-힣]{2,4})(?:\s|/|,|，|\n)')
        return ''

    # ─────────────────────────────────────────────
    # 양식 필드 값 생성 (핵심 기능)
    # ─────────────────────────────────────────────

    def generate_field_values(self, instance_id, user_id=None, events=None,
                              include_sections=True, precomputed_form_analysis=None,
                              precomputed_form_desc=None):
        """양식의 모든 빈칸을 분석하여 AI로 채울 값을 생성한다.

        Flow:
        0. 양식 전체 원문 분석 (form intent analysis) — 표 구조·칸 역할 선행 파악
        1. 자동 추정 (날짜, 이름 등)
        2. 테이블별 분리 AI 호출 — 표 하나씩 모든 빈 셀 채우기
        3. 비테이블 텍스트 필드 AI 호출
        4. 빈 섹션 서술형 생성 (include_sections=True일 때만)
        """
        instance = self.root.doc.get_instance(instance_id)
        if not instance:
            raise Exception("문서를 찾을 수 없습니다.")

        content_json = instance.get('content_json', {})
        settings_json = instance.get('settings_json', {})
        fields_schema = content_json.get('fields_schema', {}) if isinstance(content_json.get('fields_schema'), dict) else {}
        fields = fields_schema.get('fields', []) if isinstance(fields_schema, dict) else []
        tables = fields_schema.get('tables', []) if isinstance(fields_schema, dict) else []
        sections = fields_schema.get('sections', []) if isinstance(fields_schema, dict) else []
        raw_text = fields_schema.get('raw_text', '') if isinstance(fields_schema, dict) else ''
        table_fills_raw = fields_schema.get('table_fills', []) if isinstance(fields_schema, dict) else []

        ctx = self.build_context(instance_id, user_id)
        config = self.get_config()

        # 모든 table_fills (DB 저장본 우선, 없으면 재분석)
        table_fills = table_fills_raw if table_fills_raw else self.root.file_parser._analyze_table_fills(tables)
        table_fills = [
            fill for fill in table_fills
            if isinstance(fill, dict)
            and not self._is_structural_fill_target(fill)
            and not self._is_ignorable_missing_target(fill.get('label', ''), {}, ctx)
        ]

        # ── Phase 0: 양식 전체 분석 (선행) ──
        form_desc = precomputed_form_desc
        if form_desc is None:
            form_desc = self.root.file_parser.build_form_description(tables, sections, fields, raw_text)
        form_analysis = precomputed_form_analysis if precomputed_form_analysis is not None else ''
        if precomputed_form_analysis is None and config and (tables or raw_text):
            form_analysis = self._analyze_form_intent(config, ctx, raw_text, form_desc, events)

        # ── Phase 1: 자동 추정 ──
        values = {}
        for field in fields:
            name = (field.get('name', '') or '').strip()
            if not name:
                continue
            value = self._guess_field_value(name, instance, settings_json, ctx)
            if value:
                values[name] = value

        for fill in table_fills:
            label = fill.get('label', '')
            if label and label not in values:
                guessed = self._guess_field_value(label, instance, settings_json, ctx)
                if guessed:
                    values[label] = guessed

        if events is not None:
            auto_filled = [name for name in values if values[name]]
            if auto_filled:
                events.append({
                    'type': 'detail', 'phase': 'auto_guess',
                    'message': f"자동 추정 완료 ({len(auto_filled)}개): {', '.join(auto_filled[:8])}"
                })

        # ── Phase 2: 테이블별 분리 AI 호출 ──
        if config and tables:
            # table_fills를 table_idx별로 그룹핑
            fills_by_table = {}
            for fill in table_fills:
                t_idx = fill.get('table_idx', 0)
                fills_by_table.setdefault(t_idx, []).append(fill)

            for t_idx, table in enumerate(tables):
                table_fills_for_this = fills_by_table.get(t_idx, [])
                # 미채움 항목만
                pending = [
                    f for f in table_fills_for_this
                    if f.get('label', '') and f.get('label', '') not in values
                    and not self._is_out_of_report_scope(f.get('label', ''), values, ctx)
                ]
                if not pending:
                    continue

                if events is not None:
                    events.append({
                        'type': 'detail', 'phase': f'table_{t_idx+1}',
                        'message': f'테이블 {t_idx+1} 분석 중 ({len(pending)}개 빈 칸)...'
                    })

                table_values = self._fill_table_cells(
                    config, ctx, t_idx, table, pending, form_analysis, form_desc, values, events,
                    user_id=user_id
                )
                values.update(table_values)

        # ── Phase 3: 비테이블 텍스트 필드 AI 호출 ──
        if config:
            text_targets = []
            for field in fields:
                name = (field.get('name', '') or '').strip()
                if name and name not in values:
                    answer_type = self.root.file_parser._infer_answer_type_from_label(name)
                    text_targets.append({
                        'name': name, 'type': field.get('type', 'unknown'),
                        'hint': field.get('hint', ''),
                        'context': f"양식 필드: {field.get('hint', name)}",
                        'answer_type': answer_type
                    })

            if text_targets:
                instruction_text = self._build_instruction_text(user_id, 'fill', ctx.get('instruction_ids'))
                concise_mode = self._text_is_concise(instruction_text)
                prompt = self._build_fill_prompt(ctx, form_desc, text_targets, values, form_analysis, concise=concise_mode)
                system = self._get_fill_system_prompt(concise=concise_mode)
                system = self._append_user_instructions(system, instruction_text)

                if events is not None:
                    events.append({'type': 'prompt', 'phase': 'text_fields',
                                   'title': '텍스트 필드 채우기', 'system': system, 'user': prompt[:6000]})
                try:
                    result = self._call_llm(config, system, prompt, task='field_fill').strip()
                    if events is not None:
                        events.append({'type': 'ai_response', 'phase': 'text_fields',
                                       'title': '텍스트 필드', 'content': result[:3000]})
                    llm_values = self._parse_json_response(result)
                    if isinstance(llm_values, dict):
                        for k, v in llm_values.items():
                            canonical_key = self._canonical_target_label(k, text_targets)
                            val = str(v or '').strip()
                            if self._is_ignorable_missing_target(canonical_key, {}, ctx):
                                continue
                            if self._is_usable_generated_value(canonical_key, val) and not self._value_echoes_target_label(canonical_key, val, text_targets):
                                values[str(canonical_key).strip()] = val
                except Exception:
                    pass

        # ── Phase 4: 빈 섹션 서술형 내용 생성 ──
        section_values = {}
        if include_sections and config:
            for sec in sections:
                title = sec.get('section_title', sec.get('title', ''))
                content = (sec.get('content', '') or '').strip()
                if title and not content:
                    try:
                        sec_content = self.generate_section(instance_id, {
                            'title': title, 'hint': '', 'key': title
                        }, user_id, events=events, field_values=values,
                            form_desc=form_desc, form_analysis=form_analysis)
                        if sec_content and sec_content.strip():
                            section_values[title] = sec_content.strip()
                    except Exception:
                        pass

        # 미해결 항목: table_fills + text fields 중 채워지지 않은 것
        all_expected = set()
        for fill in table_fills:
            lbl = fill.get('label', '')
            if lbl:
                all_expected.add(lbl)
        for field in fields:
            name = (field.get('name', '') or '').strip()
            if name:
                all_expected.add(name)

        unresolved = [
            name for name in all_expected
            if not str(values.get(name, '')).strip()
            and not self._is_ignorable_missing_target(name, values, ctx)
        ]
        followup_questions = []
        if unresolved:
            followup_questions = self.ask_question(instance_id, user_id=user_id, missing_fields=unresolved)

        return {
            'values': values,
            'section_values': section_values,
            'missing_fields': unresolved,
            'followup_questions': followup_questions or []
        }

    # ─────────────────────────────────────────────
    # AI 프롬프트 빌더
    # ─────────────────────────────────────────────

    def _parse_json_response(self, text):
        """LLM 응답에서 JSON 객체를 추출한다."""
        text = text.strip()
        if text.startswith('```'):
            text = text.split('\n', 1)[-1].rsplit('```', 1)[0].strip()
        # 첫 { ~ 마지막 } 추출
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1 and end > start:
            text = text[start:end+1]
        try:
            return json.loads(text)
        except Exception:
            return {}

    def _analyze_form_intent(self, config, ctx, raw_text, form_desc, events=None):
        """Phase 0: 양식 전체 원문을 읽고 구조·목적·각 칸의 역할을 먼저 분석한다.
        반환값: 분석 요약 문자열 (이후 fill 프롬프트에 삽입)"""
        full_text = str(raw_text or '').strip()
        if not full_text and not form_desc:
            return ''

        system = """당신은 한국 업무 문서 양식 분석 전문가입니다.
주어진 양식 원문과 구조를 읽고, 다음을 한국어로 분석합니다:
1. 이 문서의 종류와 목적 (1~2문장)
2. 표/섹션별 역할 요약 (각 표가 무엇을 기록하는지, 반복 행이 있다면 몇 개인지)
3. 각 표에서 열(column) 헤더 목록 — **각 열이 무엇을 의미하는지 명시**
   - 예: "표1 열: [구분|성명|학과(부)|학번|서명] → 성명에는 이름만, 학과에는 학과명만, 학번에는 학번만"
4. 반복 참여자(멘토/멘티, 팀원 등) 행 구조 파악
5. 서두/본문/결론 섹션 구분:
   - 서두: 참여자 정보, 날짜, 과목, 목표 등 고정 데이터 표
   - 본문: N주차/N회차 등 반복 활동 기록 표
   - 결론: 종합평가/소견/성취도/결과 섹션
6. 특이사항 (선택지, 날짜 형식, 서명 위치 등)

분석은 간결하게, 사실 위주로만 작성하세요. 작성 방법 조언이나 서두는 생략합니다."""

        prompt = f"""## 양식 구조
{form_desc[:5000]}

## 양식 원문 전체
{full_text[:8000]}

## 문서 정보
- 제목: {ctx.get('doc_title', '')}
- 양식명: {ctx.get('template_title', '')}
- 프로젝트 설명: {ctx.get('template_context', '')}

위 양식을 분석해주세요."""

        try:
            analysis = self._call_llm(config, system, prompt, task='form_analysis').strip()
            if events is not None:
                events.append({
                    'type': 'detail', 'phase': 'form_analysis',
                    'message': f'양식 분석 완료 ({len(analysis)}자)'
                })
                events.append({
                    'type': 'ai_response', 'phase': 'form_analysis',
                    'title': '양식 구조 분석', 'content': analysis[:3000]
                })
            return analysis
        except Exception:
            return ''

    def _fill_table_cells(self, config, ctx, t_idx, table, pending_fills, form_analysis, form_desc, already_filled, events=None, user_id=None):
        """특정 테이블의 빈 셀을 AI로 채운다. 배치 처리로 큰 표도 전부 채운다."""
        if not pending_fills:
            return {}

        instruction_text = self._build_instruction_text(
            user_id, 'fill', ctx.get('instruction_ids')
        )
        concise_mode = self._text_is_concise(instruction_text)
        table_md = self.root.file_parser._table_to_markdown(table, max_rows=35 if concise_mode else 60)
        BATCH_SIZE = 30  # 한 번에 처리할 최대 셀 수

        filled = {}
        batches = [pending_fills[i:i+BATCH_SIZE] for i in range(0, len(pending_fills), BATCH_SIZE)]

        for batch_idx, batch in enumerate(batches):
            prompt = self._build_table_fill_prompt(
                ctx, t_idx, table_md, batch, form_analysis, already_filled | filled,
                batch_idx, len(batches), concise=concise_mode
            )
            system = self._get_fill_system_prompt(concise=concise_mode)
            system = self._append_user_instructions(system, instruction_text)

            if events is not None:
                label = f'테이블{t_idx+1} 배치{batch_idx+1}/{len(batches)}'
                events.append({'type': 'prompt', 'phase': f'table_{t_idx+1}_batch{batch_idx+1}',
                               'title': label, 'system': system, 'user': prompt[:6000]})

            try:
                result = self._call_llm(config, system, prompt, task='table_fill').strip()
                if events is not None:
                    events.append({'type': 'ai_response', 'phase': f'table_{t_idx+1}_batch{batch_idx+1}',
                                   'title': f'테이블{t_idx+1} 채우기 결과', 'content': result[:3000]})
                llm_values = self._parse_json_response(result)
                if isinstance(llm_values, dict):
                    for k, v in llm_values.items():
                        canonical_key = self._canonical_target_label(k, batch)
                        val = str(v or '').strip()
                        if self._is_ignorable_missing_target(canonical_key, {}, ctx):
                            continue
                        if self._is_usable_generated_value(canonical_key, val) and not self._value_echoes_target_label(canonical_key, val, batch):
                            filled[str(canonical_key).strip()] = val
            except Exception:
                pass

        return filled

    def _section_field_updates(self, instance_id, section_title, content):
        """채팅으로 바뀐 섹션 내용을 관련 표 칸 값에도 반영한다."""
        instance = self.root.doc.get_instance(instance_id)
        if not instance:
            return {}
        content_json = instance.get('content_json', {}) if isinstance(instance.get('content_json'), dict) else {}
        fields_schema = content_json.get('fields_schema', {}) if isinstance(content_json.get('fields_schema'), dict) else {}
        generated = content_json.get('generated_fields', {}) if isinstance(content_json.get('generated_fields'), dict) else {}
        labels = set(str(k) for k in generated.keys())
        for fill in fields_schema.get('table_fills', []) or []:
            if isinstance(fill, dict) and fill.get('label'):
                labels.add(str(fill.get('label')))

        title_compact = self._compact_label(section_title)
        text = str(content or '').strip()
        if not text:
            return {}

        updates = {}

        def week_chunks():
            matches = list(re.finditer(r'(\d+)\s*주차[^\n]*', text))
            chunks = {}
            for idx, match in enumerate(matches):
                week = int(match.group(1))
                start = match.start()
                end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
                chunk = text[start:end].strip()
                chunk = re.sub(r'\n{2,}', '\n', chunk)
                if chunk:
                    chunks[week] = chunk
            if chunks:
                return chunks
            paragraphs = [p.strip() for p in re.split(r'\n+', text) if p.strip()]
            return {idx + 1: para for idx, para in enumerate(paragraphs)}

        if any(key in title_compact for key in ['진행과정', '활동내용', '튜터링진행']):
            chunks = week_chunks()
            for label in labels:
                compact = self._compact_label(label)
                if any(skip in compact for skip in ['활동사진', '사진첨부']):
                    continue
                if not any(key in compact for key in ['진행과정', '활동내용']):
                    continue
                m = re.search(r'(?:진행과정|활동내용)(\d+)', compact) or re.search(r'(\d+)$', compact)
                if not m:
                    continue
                week = int(m.group(1))
                if week in chunks:
                    updates[label] = chunks[week]

        if any(key in title_compact for key in ['결론', '종합평가', '소감', '성과']):
            for label in labels:
                compact = self._compact_label(label)
                if any(key in compact for key in ['결론', '종합평가', '소감', '성과', '향후계획']):
                    updates[label] = text

        return updates

    def _build_table_fill_prompt(self, ctx, t_idx, table_md, targets, form_analysis, already_filled,
                                 batch_idx=0, total_batches=1, concise=False):
        """테이블 전용 채우기 프롬프트 빌더."""
        batch_note = f' (배치 {batch_idx+1}/{total_batches})' if total_batches > 1 else ''
        context_limit = 700 if concise else 2000
        analysis_limit = 900 if concise else 3000
        snippet_limit = 3 if concise else 8

        prompt = f"""테이블 {t_idx+1}의 빈칸을 채워주세요{batch_note}.

## 문서 정보
- 제목: {ctx['doc_title']}
- 양식명: {ctx['template_title']}
- 주차/기간: {ctx.get('week_label', '') or '(미지정)'}
- 작성일: {datetime.datetime.now().strftime('%Y-%m-%d')}

## 프로젝트/업무 설명
{str(ctx.get('template_context', '(없음)'))[:context_limit]}

## 이번 문서 추가 설명 (반드시 반영)
{str(ctx.get('guide_notes', '(없음)'))[:context_limit]}

## 사용자 정보
{ctx.get('user_profile', '(없음)')}
"""
        if form_analysis:
            prompt += f"\n## 양식 전체 분석 결과 (참고)\n{form_analysis[:analysis_limit]}\n"

        if already_filled:
            filled_lines = [f"- {k}: {str(v)[:80]}" for k, v in list(already_filled.items())[:20]]
            prompt += f"\n## 이미 채워진 항목 (참고)\n" + '\n'.join(filled_lines) + '\n'

        prompt += f"""
## 현재 테이블 전체 구조 (Markdown)
{table_md}

## ★ 채우기 규칙 (표 칸 분리 필수) ★
- 아래 각 항목은 표의 **서로 다른 칸**입니다. 각 칸에는 해당 칸에만 맞는 단일 값을 넣으세요.
- [성명] 칸 → 이름만 / [학과(부)] 칸 → 학과명만 / [학번] 칸 → 숫자 학번만 / [서명] 칸 → 빈칸
- 여러 사람의 이름+학과+학번을 하나의 셀에 합치는 것은 **절대 금지**
- 교과목 칸에 사람 이름을 넣는 것도 **금지**
- [진행과정]/[활동내용] 칸 → 너무 짧게 쓰지 말고, 해당 주차에 한 일을 2문장 안팎으로 구체적으로 씁니다.

## 채워야 하는 항목 ({len(targets)}개)
"""
        for i, fill in enumerate(targets):
            label = fill.get('label', '')
            context_full = fill.get('context', '')
            context_lines = context_full.split('\n', 1) if context_full else ['']
            context_summary = context_lines[0].strip()
            context_md_snip = context_lines[1].strip() if len(context_lines) > 1 else ''

            prompt += f"\n{i+1}. **{label}**"
            if context_summary:
                prompt += f" — {context_summary}"

            answer_type = fill.get('answer_type', {})
            if not isinstance(answer_type, dict) or not answer_type:
                answer_type = self.root.file_parser._infer_answer_type_from_label(label)
            if isinstance(answer_type, dict) and answer_type.get('constraint'):
                prompt += f"\n   ⚠️ 기입 규칙: {answer_type['constraint']}"
                if answer_type.get('choices'):
                    prompt += f" (선택지: {' / '.join(answer_type['choices'])})"

            if context_md_snip and i < snippet_limit:
                prompt += f"\n   ```\n   {context_md_snip.replace(chr(10), chr(10) + '   ')}\n   ```"

        ref_limit = 1800 if concise else 3200
        ref_excerpt = self._reference_excerpt_for_targets(ctx, targets, limit=ref_limit)
        if ref_excerpt:
            prompt += f"\n\n## 참고자료/이전 작성 문서에서 찾은 관련 내용\n{ref_excerpt}"

        if concise:
            prompt += "\n\nJSON 객체만 반환해주세요. 일반 사실 칸은 짧게 쓰되, 진행과정/활동내용 칸은 2문장 안팎으로 구체적으로 작성하세요."
        else:
            prompt += "\n\n위 항목들의 값을 JSON 객체로 반환해주세요. 키는 항목명 그대로, 값은 실제 채울 내용입니다."
        return prompt

    def _get_fill_system_prompt(self, concise=False):
        if concise:
            return """당신은 한국어 문서 양식의 빈칸을 빠르게 채우는 어시스턴트입니다.

규칙:
1. 반드시 JSON 객체만 반환합니다.
2. 각 키는 요청된 항목명을 그대로 사용합니다.
3. 표의 각 칸에는 그 칸에 해당하는 단일 값만 씁니다.
4. 성명은 이름만, 학번은 숫자만, 학과는 학과명만, 서명란은 빈 문자열로 씁니다.
5. 진행과정/활동내용 칸은 2문장 안팎으로 구체적으로 씁니다. 그 외 서술형은 1~2문장으로 간결하게 씁니다.
6. 설명, 마크다운, 주석, 인사말은 출력하지 않습니다."""

        return """당신은 한국어 업무 문서 양식 작성 전문가입니다.

## 역할
주간보고, 업무일지, 튜터링/멘토링 보고서, 프로젝트 계획서, 회의록 등의 양식에서 빈칸을 정확하게 채웁니다.

## ★ 최우선 규칙: 각 칸은 오직 그 칸에 해당하는 단일 값만 기입 ★
표에서 한 행이 [구분 | 성명 | 학과(부) | 학번 | 서명] 형태로 나뉘어 있으면:
- "멘토 > 성명" 칸 → 이름만: "홍길동" (학번/학과 포함 금지)
- "멘토 > 학과(부)" 칸 → 학과명만: "컴퓨터공학과" (이름/학번 포함 금지)
- "멘토 > 학번" 칸 → 학번만: "2021271507" (이름/학과 포함 금지)
- "멘토 > 서명" 칸 → "" 또는 "서명 예정"
절대로 "홍길동 (2021271507, 컴퓨터공학과)" 처럼 여러 정보를 한 칸에 합치지 마세요.

## ★★ 반복 행 (멘티 여러 명 등) 처리 규칙 ★★
"멘티 > 성명 1", "멘티 > 성명 2", "멘티 > 성명 3" 처럼 번호가 붙은 경우:
- 각 번호에 해당하는 사람의 값을 따로 기입하세요.
- 멘티가 3명이라면 → 성명1=첫 번째 멘티 이름, 성명2=두 번째, 성명3=세 번째
- 학번/학과도 동일하게 각 번호에 맞는 사람 것만 기입
- 한 칸에 여러 명을 합쳐 쓰거나, 모든 칸에 같은 사람 이름을 반복하면 안 됩니다.

예시 (멘티 3명: 정해인/2025271465/지능형반도체공학과, 김태린/2025271466/지능형반도체공학과, 김현지/2025271477/지능형반도체공학과):
{
  "멘티 > 성명 1": "정해인",
  "멘티 > 학과(부) 1": "지능형반도체공학과",
  "멘티 > 학번 1": "2025271465",
  "멘티 > 서명 1": "",
  "멘티 > 성명 2": "김태린",
  "멘티 > 학과(부) 2": "지능형반도체공학과",
  "멘티 > 학번 2": "2025271466",
  "멘티 > 서명 2": "",
  "멘티 > 성명 3": "김현지",
  "멘티 > 학과(부) 3": "지능형반도체공학과",
  "멘티 > 학번 3": "2025271477",
  "멘티 > 서명 3": ""
}

## 라벨 해석 (A > B 구조)
- "A > B" 형식에서 B가 실제 들어갈 정보 종류를 결정합니다
- "멘토 > 성명" → B = 이름(성명)
- "멘토링 구분(전공/외국어)" → 전공 또는 외국어 중 택일
- "1주차 > 수업내용" → 1주차 진행된 수업 내용 서술
- "종합평가" → 전체 활동에 대한 교사/멘토의 평가 서술

## ⚠️ 유형별 기입 규칙
- 선택지(A/B/C 등)가 있으면: 반드시 그 중 하나만.
- 서명란: "" (빈칸) 또는 "서명 예정".
- 날짜 칸: "2026-04-23" 또는 "2026년 4월 23일" 형식.
- 학번 칸: 숫자 학번만.
- 교과목 칸: 교수명이 아닌 과목명.
- 성명 칸: 이름만. 괄호 안에 학번/학과 포함 금지.

## 섹션 역할 구분
- **서두**: 이름, 학번, 학과, 날짜, 참여자 정보 → 사실 정보 기입
- **본문**: N주차/N회차 수업 내용, 진행 활동, 학습 항목 → 구체적 활동 서술
- **결론**: 종합소견, 평가, 성취도, 특이사항, 다음 계획 → 평가/요약

## 일반 규칙
1. 반드시 JSON 객체만 반환합니다. 설명/마크다운/주석 없이 순수 JSON만 출력합니다.
2. 각 키는 요청된 항목명을 정확히 그대로 사용합니다.
3. 정보가 제공된 경우 그 정보를 정확히 사용, 제공 안 된 경우 문맥에서 합리적으로 추정.
4. 제공된 추가설명/guide_notes/참고자료를 최우선으로 반영합니다.
5. 서술형 칸(활동내용, 소견 등): 기본 1~2문장, 필요한 경우에만 조금 더 구체화.
6. 가능한 한 추정해서 채웁니다. [미정]은 절대 불가능한 경우에만.
7. 인사말/서론 없이 해당 칸에 직접 들어갈 내용만 씁니다.
8. 답변 전 내부적으로 각 칸의 역할과 규칙을 확인하고, 최종 JSON만 출력합니다."""

    def _build_fill_prompt(self, ctx, form_desc, targets, already_filled, form_analysis='', concise=False):
        raw_limit = 1800 if concise else 5000
        table_hint_limit = 10 if concise else 20
        analysis_limit = 900 if concise else 2500
        form_limit = 2500 if concise else 6000
        snippet_limit = 2 if concise else 5
        prompt = f"""다음 문서 양식의 빈칸을 채워주세요.

## 문서 정보
- 문서 제목: {ctx['doc_title']}
- 양식명: {ctx['template_title']}
- 주차/기간: {ctx.get('week_label', '') or '(미지정)'}
- 마감일: {ctx.get('deadline', '') or '(미지정)'}
- 작성일: {datetime.datetime.now().strftime('%Y-%m-%d')}

## 프로젝트/업무 설명
{str(ctx.get('template_context', '(설명 없음)'))[:900 if concise else 3000]}

## 이번 문서에 대한 추가 설명 (중요 — 반드시 반영)
{str(ctx.get('guide_notes', '(없음)'))[:900 if concise else 3000]}

## 레포트 항목 구조
{', '.join(ctx.get('report_items', [])) if ctx.get('report_items') else '(미지정)'}

## 사용자 정보
{ctx.get('user_profile', '(없음)')}

## 양식 원문 일부
{str(ctx.get('raw_text_excerpt', '(없음)'))[:raw_limit]}

## 감지된 섹션 제목
{', '.join(ctx.get('section_titles', [])) if ctx.get('section_titles') else '(없음)'}

## 표 기반 채움 힌트
{chr(10).join(['- ' + item for item in ctx.get('table_fill_info', [])[:table_hint_limit]]) if ctx.get('table_fill_info') else '(없음)'}

## 이미 채워진 항목 (참고용)
{json.dumps(already_filled, ensure_ascii=False, indent=2) if already_filled else '(없음)'}
"""
        if form_analysis:
            prompt += f"\n## 양식 구조 분석 결과\n{form_analysis[:analysis_limit]}\n"

        prompt += f"""
{self._form_inference_protocol(concise=concise)}

## 양식 전체 구조
{form_desc[:form_limit]}

## 채워야 하는 항목 ({len(targets)}개)
"""
        for i, target in enumerate(targets):
            prompt += f"\n{i+1}. **{target['name']}**"
            context_full = target.get('context', '')
            # context는 첫 줄(위치 요약) + 나머지(마크다운 표 스니펫)로 구성됨
            context_lines = context_full.split('\n', 1) if context_full else ['']
            context_summary = context_lines[0].strip()
            context_md = context_lines[1].strip() if len(context_lines) > 1 else ''
            if context_summary:
                prompt += f" — {context_summary}"
            hint = target.get('hint', '')
            hint_first = hint.split('\n')[0].strip() if hint else ''
            if hint_first and hint_first != context_summary:
                prompt += f" (힌트: {hint_first})"
            # 타입 제약 강조
            answer_type = target.get('answer_type', {})
            if isinstance(answer_type, dict) and answer_type.get('constraint'):
                prompt += f"\n   ⚠️ 기입 규칙: {answer_type['constraint']}"
                if answer_type.get('choices'):
                    prompt += f" (선택지: {' / '.join(answer_type['choices'])})"
            # 마크다운 표 스니펫 — 표 내 위치 시각화 (최초 5개만 포함)
            if context_md and i < snippet_limit:
                prompt += f"\n   ```\n   {context_md.replace(chr(10), chr(10) + '   ')}\n   ```"

        ref_excerpt = self._reference_excerpt_for_targets(ctx, targets, limit=2200 if concise else 3600)
        if ref_excerpt:
            prompt += f"\n\n## 참고자료/이전 작성 문서에서 찾은 관련 내용\n{ref_excerpt}"

        if concise:
            prompt += "\n\n각 값은 가능한 짧게 작성하세요. 서술형도 1~2문장으로 JSON 객체만 반환해주세요."
        else:
            prompt += "\n\n위 항목들의 값을 JSON 객체로 반환해주세요. 키는 항목명 그대로, 값은 실제 채울 내용입니다."
        return prompt

    # ─────────────────────────────────────────────
    # 섹션 생성
    # ─────────────────────────────────────────────

    def generate_section(self, instance_id, sec_def, user_id=None, events=None,
                         field_values=None, form_desc=None, form_analysis=None):
        """AI로 단일 섹션 콘텐츠를 생성한다."""
        config = self.get_config()
        if not config:
            return sec_def.get('hint', '내용을 작성해주세요. (AI 설정 필요)')

        ctx = self.build_context(instance_id, user_id)
        instruction_text = self._build_instruction_text(user_id, 'section', ctx.get('instruction_ids'))
        concise_mode = self._text_is_concise(instruction_text)
        context_limit = 900 if concise_mode else 5000
        analysis_limit = 900 if concise_mode else 2500
        reference_limit = 900 if concise_mode else 2000
        style_limit = 700 if concise_mode else 1500
        table_hint_limit = 8 if concise_mode else 20
        section_length_rule = (
            "1~2문장, 총 150자 안팎으로 간결하게 작성하세요."
            if concise_mode else
            "양식의 칸 크기에 맞춰 기본 1~3문장으로 작성하세요."
        )

        # 양식 전체 구조 가져오기
        instance = self.root.doc.get_instance(instance_id)
        content_json = instance.get('content_json', {}) if instance else {}
        fields_schema = content_json.get('fields_schema', {}) if isinstance(content_json, dict) else {}
        tables = fields_schema.get('tables', []) if isinstance(fields_schema, dict) else []
        sections_list = fields_schema.get('sections', []) if isinstance(fields_schema, dict) else []
        raw_text = fields_schema.get('raw_text', '') if isinstance(fields_schema, dict) else ''

        if not form_desc:
            form_desc = self.root.file_parser.build_form_description(tables, sections_list, [], raw_text)
        existing_hint = sec_def.get('hint', '')

        prompt = f"""다음 문서 양식의 '{sec_def['title']}' 섹션에 들어갈 내용을 작성해주세요.

## 문서 정보
- 문서 제목: {ctx['doc_title']}
- 양식명: {ctx['template_title']}
- 주차/기간: {ctx.get('week_label', '') or '(미지정)'}
- 프로젝트/업무 설명: {str(ctx.get('template_context', '(없음)'))[:context_limit]}
- 이번 문서 추가 설명: {str(ctx.get('guide_notes', '(없음)'))[:context_limit]}
- 레포트 항목 구조: {', '.join(ctx.get('report_items', [])) if ctx.get('report_items') else '(미지정)'}

## 이미 추정되거나 채워진 항목
{self._format_field_values(field_values)}

## 표 기반 채움 힌트
{chr(10).join(['- ' + item for item in ctx.get('table_fill_info', [])[:table_hint_limit]]) if ctx.get('table_fill_info') else '(없음)'}

## 양식 원문 일부
{str(ctx.get('raw_text_excerpt', '(없음)'))[:context_limit]}

## 양식의 전체 구조 (이 섹션의 맥락 파악용)
{form_desc[:context_limit]}
"""

        if form_analysis:
            prompt += f"""
## 양식 구조 분석 결과
{form_analysis[:analysis_limit]}
"""

        prompt += f"""
## 작성 대상 섹션
- 섹션명: {sec_def['title']}
- 기존 내용/힌트: {existing_hint[:500] if existing_hint else '(없음 — 새로 작성 필요)'}

## 지시사항
0. 먼저 이 섹션이 문서 전체에서 어떤 역할인지 내부적으로 판단하세요. 단, 최종 답변에는 추론 과정 설명을 쓰지 마세요.
1. 이 섹션에 실제로 들어갈 내용만 작성하세요.
2. 분량: {section_length_rule}
3. 프로젝트 설명과 문서별 추가 설명을 적극 반영하세요.
4. 전문적이고 업무적인 어조를 사용하세요.
5. 마크다운 없이 순수 텍스트로 작성하세요.
6. 서론/인사말 없이 바로 핵심 내용을 작성하세요.
7. 사진이 함께 들어가는 섹션이어도 본문 설명을 생략하지 말고, 사진 때문에 내용을 짧게 줄이지 마세요.
8. 섹션명이 모호하거나 일반적이지 않더라도 표, 주변 항목, 다른 섹션 제목을 함께 보고 실제 요구 내용을 추론하세요.
9. 일반적인 보고서 서두나 추상적 개요로 때우지 말고, 해당 양식 칸에 바로 들어갈 사실·활동·평가·계획을 작성하세요.
10. 만약 이 섹션이 사람별/항목별 기록이라면 필요한 차이만 짧게 드러내세요.

{self._form_inference_protocol(concise=concise_mode)}"""

        ref_excerpt = self._reference_excerpt_for_targets(ctx, [sec_def], limit=reference_limit + style_limit)
        if ref_excerpt:
            prompt += f"\n\n## 참고자료/이전 작성 문서에서 찾은 관련 내용\n{ref_excerpt}"

        if ctx['user_profile']:
            prompt += f"\n\n## 사용자 정보\n{ctx['user_profile']}"

        system = """당신은 한국어 업무 문서 작성 전문가입니다.
    주간보고, 프로젝트 계획서, 업무일지뿐 아니라 형식이 낯선 비정형 양식도 구조를 해석하여 적절한 내용을 작성합니다.
    서론이나 인사말 없이 바로 핵심 내용을 작성합니다.
    제공된 프로젝트 설명과 문서별 설명을 반드시 반영합니다.
    문서 전체 구조를 먼저 해석한 뒤, 현재 섹션이 실제로 요구하는 내용의 종류를 판단하여 씁니다.
    섹션명이 모호해도 표/항목/반복행/주변 레이블을 근거로 역할을 추론합니다.
    최종 답변에는 완성된 섹션 본문만 작성합니다.
    한국어로 답변합니다."""

        system = self._append_user_instructions(system, instruction_text)

        if events is not None:
            events.append({
                'type': 'prompt',
                'phase': 'section',
                'title': sec_def.get('title', ''),
                'system': system,
                'user': prompt[:6000]
            })

        result = self._call_llm(config, system, prompt, task='section')

        if events is not None:
            events.append({
                'type': 'ai_response',
                'phase': 'section',
                'title': sec_def.get('title', ''),
                'content': result[:5000] if result else ''
            })

        return result

    def regenerate_section(self, instance_id, section_id, user_id=None, instruction=''):
        """기존 섹션을 AI로 재작성한다."""
        section = self.root.doc.get_section(section_id)
        if not section:
            raise Exception("섹션을 찾을 수 없습니다.")

        config = self.get_config()
        if not config:
            raise Exception("AI 설정이 필요합니다.")

        ctx = self.build_context(instance_id, user_id)

        prompt = f"""다음 문서의 '{section['section_title']}' 섹션을 재작성해주세요.

문서 제목: {ctx['doc_title']}
양식명: {ctx['template_title']}
프로젝트 설명: {ctx.get('template_context', '')[:800]}

현재 섹션 내용:
{section.get('content', '')[:1500]}"""

        if instruction:
            prompt += f"\n\n수정 요청: {instruction}"
        if ctx['guide_notes']:
            prompt += f"\n\n문서별 참고 설명: {ctx['guide_notes']}"
        ref_excerpt = self._reference_excerpt_for_targets(ctx, [section.get('section_title', ''), instruction], limit=2600)
        if ref_excerpt:
            prompt += f"\n\n참고자료/이전 작성 문서에서 찾은 관련 내용:\n{ref_excerpt}"
        if ctx['user_profile']:
            prompt += f"\n\n사용자 정보: {ctx['user_profile']}"

        if self._text_is_concise(instruction):
            prompt += "\n\n기존 내용을 1~2문장으로 간결하게 재작성해주세요. 한국어로 작성합니다."
        else:
            prompt += "\n\n기존 내용을 개선하여 기본 1~3문장으로 재작성해주세요. 한국어로 작성합니다."

        system = "당신은 전문 문서 작성 어시스턴트입니다. 기존 내용을 기반으로 개선된 버전을 작성합니다."
        return self._call_llm(config, system, prompt, task='section')

    # ─────────────────────────────────────────────
    # 채팅
    # ─────────────────────────────────────────────

    def chat(self, instance_id, message, user_id=None, section_id=None):
        """AI와 대화하여 문서 수정 답변을 반환한다.
        
        Returns:
            dict: { 'reply': str, 'content_modified': bool, 'modified_sections': list }
        """
        config = self.get_config()
        if not config:
            return {'reply': "AI 설정이 없어 응답할 수 없습니다. AI 설정 페이지에서 설정해주세요.", 'content_modified': False}

        ctx = self.build_context(instance_id, user_id)

        chats = self.root.ai.list_chats(instance_id)
        history = [
            {"role": c['role'], "content": str(c.get('content', '') or '')[:900]}
            for c in chats[-6:]
        ]

        # 섹션 컨텍스트 로드
        target_section = None
        if section_id:
            try:
                target_section = self.root.doc.get_section(section_id)
            except Exception:
                pass

        system = f"""당신은 문서 수정 어시스턴트입니다. 사용자의 문서 수정 요청에 구체적으로 답변합니다.

현재 문서 제목: {ctx['doc_title']}"""

        if ctx['template_context']:
            system += f"\n프로젝트 설명: {ctx['template_context'][:800]}"
        if ctx['sections_context']:
            system += f"\n\n현재 문서 내용:\n{ctx['sections_context'][:1200]}"
        if target_section:
            system += f"\n\n현재 선택된 섹션: [{target_section['section_title']}]\n{target_section.get('content', '')[:800]}"
        if ctx['style_reference']:
            system += f"\n\n이전 문서 스타일:\n{ctx['style_reference'][:600]}"
        ref_excerpt = self._reference_excerpt_for_targets(ctx, [message], limit=1200)
        if ref_excerpt:
            system += f"\n\n참고자료/이전 작성 문서의 관련 내용:\n{ref_excerpt}"
        if ctx.get('report_items'):
            system += f"\n\n권장 레포트 항목: {', '.join(ctx.get('report_items', []))}"
        try:
            inst = self.root.doc.get_instance(instance_id)
            content_json = inst.get('content_json', {}) if inst else {}
            generated_fields = content_json.get('generated_fields', {}) if isinstance(content_json, dict) else {}
            if isinstance(generated_fields, dict) and generated_fields:
                system += "\n\n현재 양식 채움 값:\n" + self._format_field_values(generated_fields, limit=24)
        except Exception:
            pass

        system += """

[중요 규칙] 
사용자가 문서 내용의 수정을 요청하면, 수정된 전체 내용을 아래 형식으로 감싸서 반환하세요:
[SECTION_UPDATE:섹션제목]
수정된 전체 내용
[/SECTION_UPDATE]
수정 마커 외에 간단한 설명도 함께 작성하세요.
만약 단순 질문이나 조언 요청이면 마커 없이 자연스럽게 답변하세요.
이미지/사진이 첨부되더라도 기존 본문 서술을 지우지 말고 유지하세요. 사진 관련 문구는 필요하면 마지막에 1~2줄만 간단히 남기고, 실제 사진 삽입은 별도 시스템이 처리한다고 가정하세요.
사용자가 "~ 레포트 작성해줘"처럼 전체 보고서 작성을 요청하면, 현재 문서의 섹션 제목 또는 레포트 항목 구조에 맞춰 여러 개의 [SECTION_UPDATE:...] 블록으로 나누어 작성하세요.
일반 채팅 답변은 기본 2~4문장으로 짧게 답하고, 문서 수정 블록도 필요한 내용만 간결하게 작성하세요.
한국어로 답변합니다."""

        messages = history + [{"role": "user", "content": message}]

        try:
            reply = self._call_llm_with_history(config, system, messages, task='chat')
        except Exception as e:
            return {'reply': f"AI 응답 오류: {str(e)}", 'content_modified': False}
        reply = str(reply or '').strip()
        if not reply:
            return {'reply': 'AI 응답이 비어 있습니다. 잠시 후 다시 시도해주세요.', 'content_modified': False}

        # 섹션 수정 마커 파싱 및 자동 적용
        content_modified = False
        modified_sections = []
        import re
        pattern = r'\[SECTION_UPDATE:([^\]]+)\]\s*\n(.*?)\n\[/SECTION_UPDATE\]'
        matches = re.findall(pattern, reply, re.DOTALL)

        if matches:
            sections = self.root.doc.list_sections(instance_id)
            section_map = {s['section_title']: s for s in sections}
            field_updates = {}

            for sec_title, new_content in matches:
                sec_title = sec_title.strip()
                new_content = new_content.strip()
                matched_section = section_map.get(sec_title)
                if not matched_section:
                    # 부분 매칭 시도
                    for st, sec in section_map.items():
                        if sec_title in st or st in sec_title:
                            matched_section = sec
                            break
                if matched_section and new_content:
                    try:
                        self.root.doc.update_section(matched_section['id'], content=new_content)
                        field_updates.update(self._section_field_updates(
                            instance_id, matched_section['section_title'], new_content
                        ))
                        content_modified = True
                        modified_sections.append(matched_section['section_title'])
                    except Exception:
                        pass

            if field_updates:
                try:
                    inst = self.root.doc.get_instance(instance_id)
                    content_json = inst.get('content_json', {}) if inst and isinstance(inst.get('content_json'), dict) else {}
                    generated_fields = content_json.get('generated_fields', {}) if isinstance(content_json.get('generated_fields'), dict) else {}
                    generated_fields.update({k: v for k, v in field_updates.items() if str(v or '').strip()})
                    content_json['generated_fields'] = self.sanitize_generated_fields(generated_fields)
                    content_json['generated_output_file'] = ''
                    self.root.doc.update_instance(instance_id, content_json=content_json)
                except Exception:
                    pass

            # 마커를 응답에서 제거하고 사용자 친화 메시지로 대체
            clean_reply = re.sub(pattern, '', reply, flags=re.DOTALL).strip()
            if content_modified:
                sec_names = ', '.join(modified_sections)
                clean_reply = f"✅ [{sec_names}] 섹션이 수정되었습니다.\n\n{clean_reply}" if clean_reply else f"✅ [{sec_names}] 섹션이 수정되었습니다."
            reply = clean_reply

        else:
            # 마커가 없는 채팅이라도 기존 오염 필드는 즉시 정리한다.
            try:
                inst = self.root.doc.get_instance(instance_id)
                content_json = inst.get('content_json', {}) if inst and isinstance(inst.get('content_json'), dict) else {}
                generated_fields = content_json.get('generated_fields', {}) if isinstance(content_json.get('generated_fields'), dict) else {}
                cleaned = self.sanitize_generated_fields(generated_fields)
                if cleaned != generated_fields:
                    content_json['generated_fields'] = cleaned
                    content_json['generated_output_file'] = ''
                    self.root.doc.update_instance(instance_id, content_json=content_json)
                    content_modified = True
            except Exception:
                pass

        return {'reply': reply, 'content_modified': content_modified, 'modified_sections': modified_sections}

    def ask_question(self, instance_id, section_title='', user_id=None, missing_fields=None):
        """정보 부족 시 사용자에게 물어볼 질문을 생성한다."""
        config = self.get_config()
        ctx = self.build_context(instance_id, user_id)

        if not missing_fields:
            missing_fields = []

        if not config:
            return self._fallback_questions(missing_fields)

        prompt = f"""다음 문서를 작성하기 위해 사용자에게 추가로 물어봐야 할 정보가 있습니까?

문서 제목: {ctx['doc_title']}
양식명: {ctx['template_title']}
작성 가이드: {ctx['guide_notes']}"""

        if section_title:
            prompt += f"\n현재 작성 섹션: {section_title}"
        if ctx['fields_info']:
            prompt += f"\n양식 필드: {ctx['fields_info']}"
        if ctx.get('table_fill_info'):
            prompt += f"\n표 빈칸 힌트: {'; '.join(ctx.get('table_fill_info', [])[:12])}"
        if missing_fields:
            prompt += f"\n현재 비어 있는 핵심 항목: {', '.join(missing_fields[:12])}"
        if ctx['user_profile']:
            prompt += f"\n이미 알고 있는 사용자 정보: {ctx['user_profile']}"

        prompt += "\n\n부족한 정보가 있다면, 사용자에게 물어볼 질문을 JSON으로 반환해주세요.\n형식: {\"questions\": [\"질문1\", \"질문2\"]}\n정보가 충분하다면 {\"questions\": []} 로만 답해주세요.\n한국어로 답변합니다."

        system = "당신은 문서 작성을 돕는 어시스턴트입니다. 사용자에게 필요한 정보를 정중하게 물어봅니다. 질문은 구체적이고 답하기 쉽게 작성하고, 꼭 필요한 정보만 요청합니다. 반드시 JSON만 반환합니다."

        try:
            result = self._call_llm(config, system, prompt, task='question').strip()
            if result.startswith('```'):
                result = result.split('\n', 1)[-1].rsplit('```', 1)[0].strip()
            data = json.loads(result)
            questions = data.get('questions', []) if isinstance(data, dict) else []
            return self._normalize_questions(questions)
        except Exception:
            return self._fallback_questions(missing_fields)

    def _normalize_questions(self, questions):
        if not isinstance(questions, list):
            return []
        result = []
        for item in questions:
            text = str(item or '').strip()
            if not text:
                continue
            if text.startswith('- '):
                text = text[2:].strip()
            if text not in result:
                result.append(text)
        return result[:5]

    def _fallback_questions(self, missing_fields):
        if not missing_fields:
            return []
        questions = []
        for field in missing_fields[:5]:
            field_name = str(field or '').strip()
            if not field_name:
                continue
            questions.append(f"'{field_name}' 항목에 들어갈 구체적인 내용이나 수치를 알려주세요.")
        return questions

    # ─────────────────────────────────────────────
    # 자동 추정 헬퍼
    # ─────────────────────────────────────────────

    def _guess_field_value(self, name, instance, settings_json, ctx):
        """필드명으로부터 자동 추정 가능한 값을 반환한다."""
        lowered = str(name or '').strip().lower()
        compact = lowered.replace(' ', '').replace('\t', '')
        session = getattr(self.root, 'session', None)
        reference_guess = self._guess_from_reference_text(name, ctx)
        if reference_guess and self._is_usable_generated_value(name, reference_guess):
            return reference_guess

        # 날짜 관련
        now_str = datetime.datetime.now().strftime('%Y-%m-%d')
        now_korean = datetime.datetime.now().strftime('%Y년 %m월 %d일')

        if any(w in compact for w in ['작성일', '작성일자', '보고일', '보고일자', '제출일', '제출일자', '신청일', '신청일자', '확인일', '확인일자']):
            return now_korean

        if '불참자' in compact:
            return '없음'

        if any(w in compact for w in ['주차', '주차라벨', '기간', '보고기간']):
            return instance.get('week_label', '') or ctx.get('week_label', '')

        if any(w in compact for w in ['마감일', '마감일자', '완료예정일']):
            return instance.get('deadline', '') or ctx.get('deadline', '')

        # 문서 제목
        if any(w in compact for w in ['문서명', '문서제목', '제목', '보고서명']):
            return instance.get('title', '')

        # 프로젝트명
        if any(w in compact for w in ['프로젝트명', '프로젝트이름', '프로젝트', '사업명']):
            return ctx.get('template_context', '')[:80] if ctx.get('template_context') else ''

        # 사용자 정보
        if any(w in compact for w in ['작성자', '담당자', '보고자', '기안자']):
            try:
                return session.get('name') or session.get('username') or session.get('email') or ''
            except Exception:
                return ''

        if any(w in compact for w in ['이메일', '메일', 'email']):
            try:
                return session.get('email') or ''
            except Exception:
                return ''

        if any(w in compact for w in ['부서', '직책', '회사', '조직', '소속', '직위', '직급']):
            profile = {}
            try:
                p = self.root.ai.get_profile(instance.get('user_id', ''))
                if p:
                    profile = p.get('profile_data', {}) or {}
            except Exception:
                pass
            for key, value in profile.items():
                kn = key.replace(' ', '').lower()
                if kn in compact or compact in kn:
                    return str(value)

        return ''

    # ─────────────────────────────────────────────
    # 프로필 학습
    # ─────────────────────────────────────────────

    def learn_from_conversation(self, instance_id, user_id):
        """대화 및 문서 내용에서 사용자 정보를 추출하여 프로필에 학습한다."""
        config = self.get_config()
        if not config or not user_id:
            return

        chats = self.root.ai.list_chats(instance_id)
        if not chats:
            return

        user_messages = [c['content'] for c in chats if c['role'] == 'user'][-5:]
        if not user_messages:
            return

        existing = {}
        try:
            profile = self.root.ai.get_profile(user_id)
            if profile:
                existing = profile.get('profile_data', {})
        except Exception:
            pass

        conversation_text = "\n".join(user_messages)

        prompt = f"""다음 대화에서 사용자의 개인정보, 회사정보, 직책 등 나중에 문서 작성에 유용할 정보를 JSON으로 추출해주세요.

대화 내용:
{conversation_text[:2000]}

기존 프로필:
{json.dumps(existing, ensure_ascii=False)[:500]}

JSON 형식으로만 답해주세요. 새로운 정보가 없으면 빈 객체 {{}}를 반환하세요.
키는 한국어로 작성합니다. 예: {{"회사명": "ABC", "직책": "팀장", "부서": "개발팀"}}"""

        system = "사용자의 대화에서 정보를 추출하는 어시스턴트입니다. 반드시 JSON만 반환합니다."

        try:
            result = self._call_llm(config, system, prompt, task='profile')
            result = result.strip()
            if result.startswith('```'):
                result = result.split('\n', 1)[-1].rsplit('```', 1)[0].strip()
            new_data = json.loads(result)
            if new_data and isinstance(new_data, dict):
                merged = {**existing, **new_data}
                self.root.ai.save_profile(user_id, profile_data=merged)
        except Exception:
            pass

    # ─────────────────────────────────────────────
    # LLM 호출 (내부)
    # ─────────────────────────────────────────────

    def _call_llm(self, config, system_prompt, user_prompt, task='default'):
        messages = [{"role": "user", "content": user_prompt}]
        return self._call_llm_with_history(config, system_prompt, messages, task=task)

    def _call_llm_with_history(self, config, system_prompt, messages, task='default'):
        config = self._select_model_config(config, task)
        provider = config.get('provider', '')
        api_key = config.get('api_key', '')
        model_name = config.get('model_name', '')
        endpoint = config.get('endpoint', '')
        concise_mode = self._is_concise_mode(system_prompt, messages)
        token_limit = self._task_token_limit(task, concise=concise_mode)

        if provider == 'openai':
            import openai
            client = openai.OpenAI(api_key=api_key, base_url=endpoint or None)
            params = {
                "model": model_name,
                "messages": [{"role": "system", "content": system_prompt}] + messages
            }
            if not self._openai_uses_completion_limit(model_name):
                params["temperature"] = 0.7
            params.update(self._openai_token_limit_param(model_name, token_limit))
            resp = client.chat.completions.create(**params)
            return resp.choices[0].message.content

        elif provider == 'anthropic':
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            if endpoint:
                client.base_url = endpoint
            resp = client.messages.create(
                model=model_name,
                max_tokens=token_limit,
                system=system_prompt,
                messages=messages
            )
            return resp.content[0].text

        elif provider == 'google':
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(model_name)
            full_prompt = system_prompt + "\n\n"
            for msg in messages:
                role_label = "사용자" if msg['role'] == 'user' else "어시스턴트"
                full_prompt += f"{role_label}: {msg['content']}\n\n"
            resp = model.generate_content(full_prompt)
            return resp.text

        elif provider == 'custom':
            import requests as req
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            payload = {
                "model": model_name,
                "messages": [{"role": "system", "content": system_prompt}] + messages,
                "max_tokens": token_limit
            }
            resp = req.post(endpoint, json=payload, headers=headers, timeout=120)
            data = resp.json()
            return data.get('choices', [{}])[0].get('message', {}).get('content', '')

        raise Exception(f"지원하지 않는 AI 프로바이더: {provider}")

    def _call_llm_stream(self, config, system_prompt, user_prompt, task='default'):
        config = self._select_model_config(config, task)
        provider = config.get('provider', '')
        api_key = config.get('api_key', '')
        model_name = config.get('model_name', '')
        endpoint = config.get('endpoint', '')
        messages = [{"role": "user", "content": user_prompt}]
        concise_mode = self._is_concise_mode(system_prompt, messages)
        token_limit = self._task_token_limit(task, concise=concise_mode)

        if provider == 'openai':
            import openai
            client = openai.OpenAI(api_key=api_key, base_url=endpoint or None)
            params = {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "stream": True
            }
            if not self._openai_uses_completion_limit(model_name):
                params["temperature"] = 0.7
            params.update(self._openai_token_limit_param(model_name, token_limit))
            stream = client.chat.completions.create(**params)
            for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    yield delta.content

        elif provider == 'anthropic':
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            if endpoint:
                client.base_url = endpoint
            with client.messages.stream(
                model=model_name,
                max_tokens=token_limit,
                system=system_prompt,
                messages=messages
            ) as stream:
                for text in stream.text_stream:
                    yield text

        elif provider == 'google':
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(model_name)
            resp = model.generate_content(
                system_prompt + "\n\n" + user_prompt,
                stream=True
            )
            for chunk in resp:
                if chunk.text:
                    yield chunk.text

        elif provider == 'custom':
            import requests as req
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            payload = {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "max_tokens": token_limit,
                "stream": True
            }
            resp = req.post(endpoint, json=payload, headers=headers, timeout=120, stream=True)
            for line in resp.iter_lines():
                if line:
                    decoded = line.decode('utf-8')
                    if decoded.startswith('data: ') and decoded != 'data: [DONE]':
                        try:
                            data = json.loads(decoded[6:])
                            content = data.get('choices', [{}])[0].get('delta', {}).get('content', '')
                            if content:
                                yield content
                        except Exception:
                            pass
        else:
            raise Exception(f"지원하지 않는 AI 프로바이더: {provider}")


Model = AIAgent

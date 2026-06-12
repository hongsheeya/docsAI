# =============================================================================
# AI Sub-Struct (AI 설정 및 채팅 비즈니스 로직)
# =============================================================================
import datetime
import json

class AI:
    def __init__(self, core):
        self.core = core
        self.db_config = core.orm.use("ai_config")
        self.db_chat = core.orm.use("ai_chat")
        self.db_profile = core.orm.use("user_profile")
        self.db_instruction = core.orm.use("ai_instruction")

    # ── AI Config CRUD ──

    def create_config(self, data):
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        data['created'] = now
        data['updated'] = now
        if data.get('is_active'):
            for c in self.db_config.rows():
                self.db_config.update({'is_active': False, 'updated': now}, id=c['id'])
        if isinstance(data.get('extra_json'), (dict, list)):
            data['extra_json'] = json.dumps(data['extra_json'], ensure_ascii=False)
        return self.db_config.insert(data)

    def get_config(self, id):
        cfg = self.db_config.get(id=id)
        if cfg:
            try:
                cfg['extra_json'] = json.loads(cfg.get('extra_json', '{}'))
            except Exception:
                pass
        return cfg

    def get_active_config(self):
        cfg = self.db_config.get(is_active=True)
        if cfg:
            try:
                cfg['extra_json'] = json.loads(cfg.get('extra_json', '{}'))
            except Exception:
                pass
        return cfg

    def list_configs(self):
        rows = self.db_config.rows(orderby="created", order="DESC")
        for r in rows:
            try:
                r['extra_json'] = json.loads(r.get('extra_json', '{}'))
            except Exception:
                pass
            # API KEY 마스킹
            if r.get('api_key'):
                key = r['api_key']
                r['api_key_masked'] = key[:8] + '...' + key[-4:] if len(key) > 12 else '****'
        return rows

    def update_config(self, id, **fields):
        fields['updated'] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if fields.get('is_active'):
            for c in self.db_config.rows():
                if c.get('id') != id:
                    self.db_config.update({'is_active': False, 'updated': fields['updated']}, id=c['id'])
        if isinstance(fields.get('extra_json'), (dict, list)):
            fields['extra_json'] = json.dumps(fields['extra_json'], ensure_ascii=False)
        self.db_config.update(fields, id=id)

    def delete_config(self, id):
        self.db_config.delete(id=id)

    def set_active(self, id):
        """특정 설정을 활성화 (나머지 비활성화)"""
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        all_configs = self.db_config.rows()
        for c in all_configs:
            self.db_config.update({'is_active': False, 'updated': now}, id=c['id'])
        self.db_config.update({'is_active': True, 'updated': now}, id=id)

    # ── AI Chat ──

    def add_chat(self, data):
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        data['created'] = now
        data.setdefault('section_id', '')
        return self.db_chat.insert(data)

    def list_chats(self, instance_id, section_id=None):
        kwargs = {'instance_id': instance_id}
        if section_id:
            kwargs['section_id'] = section_id
        return self.db_chat.rows(orderby="created", order="ASC", **kwargs)

    def clear_chats(self, instance_id):
        chats = self.db_chat.rows(instance_id=instance_id)
        for c in chats:
            self.db_chat.delete(id=c['id'])

    # ── User Profile ──

    def get_profile(self, user_id):
        profile = self.db_profile.get(user_id=user_id)
        if profile:
            for key in ['profile_data', 'preferences']:
                try:
                    profile[key] = json.loads(profile.get(key, '{}'))
                except Exception:
                    pass
        return profile

    def save_profile(self, user_id, **fields):
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        fields['updated'] = now
        for key in ['profile_data', 'preferences']:
            if isinstance(fields.get(key), (dict, list)):
                fields[key] = json.dumps(fields[key], ensure_ascii=False)

        existing = self.db_profile.get(user_id=user_id)
        if existing:
            self.db_profile.update(fields, id=existing['id'])
        else:
            fields['user_id'] = user_id
            self.db_profile.insert(fields)

    def update_profile_data(self, user_id, key, value):
        """프로필 데이터의 특정 키를 업데이트"""
        profile = self.get_profile(user_id)
        if profile is None:
            data = {key: value}
            self.save_profile(user_id, profile_data=data)
        else:
            pdata = profile.get('profile_data', {})
            if not isinstance(pdata, dict):
                pdata = {}
            pdata[key] = value
            self.save_profile(user_id, profile_data=pdata)

    # ── AI Instructions ──

    def create_instruction(self, data):
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        data['created'] = now
        data['updated'] = now
        data.setdefault('is_active', False)
        data.setdefault('sort_order', 0)
        data.setdefault('category', 'general')
        return self.db_instruction.insert(data)

    def list_instructions(self, user_id=None, category=None):
        kwargs = {}
        if user_id is not None:
            kwargs['user_id'] = user_id
        rows = self.db_instruction.rows(orderby='sort_order', order='ASC', **kwargs)
        if category:
            rows = [r for r in rows if r.get('category') == category]
        return rows

    def list_all_instructions(self, user_id):
        """시스템 프리셋 + 사용자 인스트럭션 모두 반환"""
        system_rows = self.db_instruction.rows(user_id='system', orderby='sort_order', order='ASC')
        user_rows = []
        if user_id:
            user_rows = self.db_instruction.rows(user_id=user_id, orderby='sort_order', order='ASC')
        return system_rows + user_rows

    def get_instruction(self, id):
        return self.db_instruction.get(id=id)

    def update_instruction(self, id, **fields):
        fields['updated'] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.db_instruction.update(fields, id=id)

    def delete_instruction(self, id):
        self.db_instruction.delete(id=id)

    def toggle_instruction(self, id):
        inst = self.db_instruction.get(id=id)
        if inst:
            new_active = not inst.get('is_active', False)
            self.db_instruction.update({
                'is_active': new_active,
                'updated': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }, id=id)
            return new_active
        return False

    def get_active_instructions(self, user_id, category=None, instruction_ids=None):
        """문서 생성 시 적용할 인스트럭션 목록 반환"""
        if instruction_ids:
            results = []
            for iid in instruction_ids:
                inst = self.db_instruction.get(id=iid)
                if inst:
                    results.append(inst)
            return results

        results = []
        system_active = self.db_instruction.rows(user_id='system', is_active=True, orderby='sort_order', order='ASC')
        results.extend(system_active)
        if user_id:
            user_active = self.db_instruction.rows(user_id=user_id, is_active=True, orderby='sort_order', order='ASC')
            results.extend(user_active)
        if category:
            results = [r for r in results if r.get('category') in [category, 'general']]
        return results

Model = AI

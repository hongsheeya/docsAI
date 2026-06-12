import json

struct = wiz.model("struct")

def openai_uses_completion_limit(model_name):
    normalized = (model_name or "").lower()
    return normalized.startswith(("gpt-5", "o1", "o3", "o4"))

def openai_token_limit_param(model_name, value):
    if openai_uses_completion_limit(model_name):
        return {"max_completion_tokens": value}
    return {"max_tokens": value}

def list():
    configs = struct.ai.list_configs()
    for cfg in configs:
        if isinstance(cfg, dict):
            cfg.pop('api_key', None)
    wiz.response.status(200, configs)

def create():
    data = wiz.request.query()
    try:
        if data.get('extra_json'):
            data['extra_json'] = json.loads(data['extra_json']) if isinstance(data['extra_json'], str) else data['extra_json']
        data['is_active'] = data.get('is_active', 'false') in [True, 'true', '1']
        struct.ai.create_config(data)
    except Exception as e:
        wiz.response.status(400, message=str(e))
    wiz.response.status(200)

def update():
    data = wiz.request.query()
    id = data.get('id', '')
    if not id:
        wiz.response.status(400, message="ID가 필요합니다.")
    try:
        fields = {}
        for key in ['provider', 'model_name', 'api_key', 'endpoint', 'is_active', 'extra_json']:
            if key in data and data[key] != '':
                fields[key] = data[key]
        if 'is_active' in fields:
            fields['is_active'] = fields['is_active'] in [True, 'true', '1']
        if 'extra_json' in fields and isinstance(fields['extra_json'], str):
            fields['extra_json'] = json.loads(fields['extra_json'])
        struct.ai.update_config(id, **fields)
    except Exception as e:
        wiz.response.status(400, message=str(e))
    wiz.response.status(200)

def delete():
    id = wiz.request.query("id", True)
    try:
        struct.ai.delete_config(id)
    except Exception as e:
        wiz.response.status(400, message=str(e))
    wiz.response.status(200)

def set_active():
    id = wiz.request.query("id", True)
    try:
        struct.ai.set_active(id)
    except Exception as e:
        wiz.response.status(400, message=str(e))
    wiz.response.status(200)

def toggle_active():
    id = wiz.request.query("id", True)
    try:
        cfg = struct.ai.get_config(id)
        if not cfg:
            wiz.response.status(404, message="AI 설정을 찾을 수 없습니다.")
        if cfg.get('is_active'):
            struct.ai.update_config(id, is_active=False)
            wiz.response.status(200, is_active=False)
        else:
            struct.ai.set_active(id)
            wiz.response.status(200, is_active=True)
    except Exception as e:
        wiz.response.status(400, message=str(e))
    wiz.response.status(200)

def test_connection():
    provider = wiz.request.query("provider", "")
    model_name = wiz.request.query("model_name", "")
    api_key = wiz.request.query("api_key", "")
    endpoint = wiz.request.query("endpoint", "")
    config_id = wiz.request.query("config_id", "")

    # 수정 모드에서 api_key가 빈 경우 기존 설정에서 가져옴
    if not api_key and config_id:
        try:
            existing = struct.ai.get_config(config_id)
            if existing:
                api_key = existing.get('api_key', '')
        except Exception:
            pass

    if not api_key:
        wiz.response.status(400, message="API Key가 필요합니다.")

    try:
        success_message = "연결 성공"
        if provider == 'openai':
            import openai
            client = openai.OpenAI(api_key=api_key, base_url=endpoint or None)
            params = {
                "model": model_name,
                "messages": [{"role": "user", "content": "Hello"}]
            }
            params.update(openai_token_limit_param(model_name, 5))
            client.chat.completions.create(**params)
            success_message = f"연결 성공 — {model_name}"

        elif provider == 'anthropic':
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            if endpoint:
                client.base_url = endpoint
            client.messages.create(
                model=model_name,
                max_tokens=5,
                messages=[{"role": "user", "content": "Hello"}]
            )
            success_message = f"연결 성공 — {model_name}"

        elif provider == 'google':
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(model_name)
            model.generate_content("Hello")
            success_message = f"연결 성공 — {model_name}"

        elif provider == 'custom':
            import requests as req
            if not endpoint:
                wiz.response.status(400, message="Custom provider는 Endpoint가 필요합니다.")
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            payload = {
                "model": model_name,
                "messages": [{"role": "user", "content": "Hello"}],
                "max_tokens": 5
            }
            resp = req.post(endpoint, json=payload, headers=headers, timeout=10)
            if resp.status_code != 200:
                wiz.response.status(400, message=f"연결 실패 — HTTP {resp.status_code}")
            success_message = f"연결 성공 — {model_name or 'custom'}"
        else:
            wiz.response.status(400, message="지원하지 않는 Provider입니다.")
    except Exception as e:
        wiz.response.status(400, message=f"연결 실패: {str(e)}")
    wiz.response.status(200, message=success_message)

# ── 프로필 메모리 관리 ──

def get_profile():
    user_id = wiz.session.get("id")
    if not user_id:
        wiz.response.status(401, message="로그인이 필요합니다.")
    try:
        profile = struct.ai.get_profile(user_id)
    except Exception as e:
        wiz.response.status(400, message=str(e))
    if profile:
        wiz.response.status(200, profile_data=profile.get('profile_data', {}), preferences=profile.get('preferences', {}))
    wiz.response.status(200, profile_data={}, preferences={})

def update_profile_key():
    user_id = wiz.session.get("id")
    if not user_id:
        wiz.response.status(401, message="로그인이 필요합니다.")
    key = wiz.request.query("key", True)
    value = wiz.request.query("value", True)
    try:
        struct.ai.update_profile_data(user_id, key, value)
    except Exception as e:
        wiz.response.status(400, message=str(e))
    wiz.response.status(200)

def delete_profile_key():
    user_id = wiz.session.get("id")
    if not user_id:
        wiz.response.status(401, message="로그인이 필요합니다.")
    key = wiz.request.query("key", True)
    try:
        profile = struct.ai.get_profile(user_id)
        if profile:
            pdata = profile.get('profile_data', {})
            if isinstance(pdata, dict) and key in pdata:
                del pdata[key]
                struct.ai.save_profile(user_id, profile_data=pdata)
    except Exception as e:
        wiz.response.status(400, message=str(e))
    wiz.response.status(200)

def clear_profile():
    user_id = wiz.session.get("id")
    if not user_id:
        wiz.response.status(401, message="로그인이 필요합니다.")
    try:
        struct.ai.save_profile(user_id, profile_data={}, preferences={})
    except Exception as e:
        wiz.response.status(400, message=str(e))
    wiz.response.status(200)

def save_profile_bulk():
    user_id = wiz.session.get("id")
    if not user_id:
        wiz.response.status(401, message="로그인이 필요합니다.")
    profile_data_str = wiz.request.query("profile_data", "{}")
    try:
        profile_data = json.loads(profile_data_str) if isinstance(profile_data_str, str) else profile_data_str
        if not isinstance(profile_data, dict):
            wiz.response.status(400, message="유효하지 않은 데이터 형식입니다.")
        struct.ai.save_profile(user_id, profile_data=profile_data)
    except Exception as e:
        wiz.response.status(400, message=str(e))
    wiz.response.status(200)

# ── 인스트럭션 관리 ──

def list_instructions():
    user_id = wiz.session.get("id")
    try:
        rows = struct.ai.list_all_instructions(user_id)
    except Exception as e:
        wiz.response.status(400, message=str(e))
    wiz.response.status(200, rows)

def create_instruction():
    user_id = wiz.session.get("id")
    if not user_id:
        wiz.response.status(401, message="로그인이 필요합니다.")
    title = wiz.request.query("title", True)
    content = wiz.request.query("content", True)
    category = wiz.request.query("category", "general")
    is_active = wiz.request.query("is_active", "false") in [True, 'true', '1']

    try:
        struct.ai.create_instruction({
            'user_id': user_id,
            'title': title,
            'content': content,
            'category': category,
            'is_active': is_active,
            'sort_order': 0
        })
    except Exception as e:
        wiz.response.status(400, message=str(e))
    wiz.response.status(200)

def update_instruction():
    id = wiz.request.query("id", True)
    title = wiz.request.query("title", "")
    content = wiz.request.query("content", "")
    category = wiz.request.query("category", "")

    fields = {}
    if title:
        fields['title'] = title
    if content:
        fields['content'] = content
    if category:
        fields['category'] = category

    try:
        struct.ai.update_instruction(id, **fields)
    except Exception as e:
        wiz.response.status(400, message=str(e))
    wiz.response.status(200)

def delete_instruction():
    id = wiz.request.query("id", True)
    try:
        struct.ai.delete_instruction(id)
    except Exception as e:
        wiz.response.status(400, message=str(e))
    wiz.response.status(200)

def toggle_instruction():
    id = wiz.request.query("id", True)
    try:
        new_state = struct.ai.toggle_instruction(id)
    except Exception as e:
        wiz.response.status(400, message=str(e))
    wiz.response.status(200, is_active=new_state)

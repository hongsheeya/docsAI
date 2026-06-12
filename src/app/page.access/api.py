import traceback
session = wiz.model("portal/season/session").use()
struct = wiz.model("struct")

def login():
    login_id = wiz.request.query("login_id", "")
    password = wiz.request.query("password", "")

    if not login_id or not password:
        wiz.response.status(400, message="아이디와 비밀번호를 입력해주세요. (login_id: '{}', password 길이: {})".format(login_id, len(password)))

    try:
        user = struct.user.authenticate(login_id, password)
    except Exception as e:
        tb = traceback.format_exc()
        wiz.response.status(500, message="인증 처리 중 서버 오류가 발생했습니다.\n에러 타입: {}\n에러 내용: {}\n상세:\n{}".format(type(e).__name__, str(e), tb))

    if user is None:
        wiz.response.status(401, message="아이디 또는 비밀번호가 올바르지 않습니다. (입력한 아이디: '{}')".format(login_id))

    try:
        session.set(id=user['id'], email=user['email'], name=user['name'], role=user['role'])
    except Exception as e:
        tb = traceback.format_exc()
        wiz.response.status(500, message="세션 설정 중 오류가 발생했습니다.\n에러 타입: {}\n에러 내용: {}\n상세:\n{}".format(type(e).__name__, str(e), tb))

    wiz.response.status(200)

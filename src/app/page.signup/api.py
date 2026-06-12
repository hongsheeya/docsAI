import re
import traceback
struct = wiz.model("struct")

def signup():
    username = wiz.request.query("username", "")
    email = wiz.request.query("email", "")
    name = wiz.request.query("name", "")
    password = wiz.request.query("password", "")

    # 유효성 검사
    if not username or len(username) < 4:
        wiz.response.status(400, message="아이디는 4자 이상이어야 합니다. (현재 입력: '{}', 길이: {})".format(username, len(username)))
    if not re.match(r'^[a-zA-Z0-9_]+$', username):
        wiz.response.status(400, message="아이디는 영문, 숫자, 밑줄(_)만 사용 가능합니다. (입력값: '{}')".format(username))
    if not email or '@' not in email:
        wiz.response.status(400, message="올바른 이메일 주소를 입력해주세요. (입력값: '{}')".format(email))
    if not name:
        wiz.response.status(400, message="이름을 입력해주세요.")
    if not password or len(password) < 8:
        wiz.response.status(400, message="비밀번호는 8자 이상이어야 합니다. (현재 길이: {})".format(len(password)))

    # 중복 확인
    try:
        if struct.user.exists_username(username):
            wiz.response.status(409, message="이미 사용 중인 아이디입니다. ('{}')".format(username))
    except Exception as e:
        wiz.response.status(500, message="아이디 중복 확인 중 오류: {} - {}".format(type(e).__name__, str(e)))

    try:
        if struct.user.exists_email(email):
            wiz.response.status(409, message="이미 등록된 이메일입니다. ('{}')".format(email))
    except Exception as e:
        wiz.response.status(500, message="이메일 중복 확인 중 오류: {} - {}".format(type(e).__name__, str(e)))

    # 사용자 생성
    try:
        struct.user.create({
            'username': username,
            'email': email,
            'name': name,
            'password': password,
            'role': 'user'
        })
    except Exception as e:
        tb = traceback.format_exc()
        wiz.response.status(500, message="회원가입 처리 중 오류가 발생했습니다.\n에러 타입: {}\n에러 내용: {}\n상세:\n{}".format(type(e).__name__, str(e), tb))

    wiz.response.status(200)

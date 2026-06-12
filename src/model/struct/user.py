# =============================================================================
# User Sub-Struct (사용자 비즈니스 로직)
# =============================================================================

import datetime
import bcrypt
import traceback

class User:
    def __init__(self, core):
        self.core = core
        self.db = core.orm.use("user")

    def _hash_password(self, password):
        """비밀번호 bcrypt 해시"""
        if isinstance(password, str):
            password = password.encode('utf-8')
        return bcrypt.hashpw(password, bcrypt.gensalt()).decode('utf-8')

    def _check_password(self, password, hashed):
        """비밀번호 검증"""
        if isinstance(password, str):
            password = password.encode('utf-8')
        if isinstance(hashed, str):
            hashed = hashed.encode('utf-8')
        return bcrypt.checkpw(password, hashed)

    def _has_username_column(self):
        """user 테이블에 username 컬럼이 있는지 확인"""
        try:
            database = self.db.orm._meta.database
            columns = [c.name for c in database.get_columns("user")]
            return "username" in columns
        except Exception:
            return False

    def authenticate(self, login_id, password):
        """아이디(username) 또는 이메일로 인증"""
        user = None
        has_username = self._has_username_column()

        # 1) username으로 시도 (컬럼이 있을 때만)
        if has_username:
            try:
                user = self.db.get(username=login_id)
            except Exception:
                pass

        # 2) email로 시도
        if user is None:
            try:
                user = self.db.get(email=login_id)
            except Exception:
                pass

        if user is None:
            return None
        if not self._check_password(password, user.get('password', '')):
            return None

        user.pop('password', None)
        return user

    def get(self, id=None):
        """사용자 단건 조회 (비밀번호 제외)"""
        user = self.db.get(id=id)
        if user:
            user.pop('password', None)
        return user

    def get_by_username(self, username):
        """username으로 사용자 조회"""
        if not self._has_username_column():
            return None
        user = self.db.get(username=username)
        if user:
            user.pop('password', None)
        return user

    def get_by_email(self, email):
        """email로 사용자 조회"""
        user = self.db.get(email=email)
        if user:
            user.pop('password', None)
        return user

    def list(self, text="", role=""):
        """사용자 목록 조회"""
        kwargs = dict()
        like = None

        if role:
            kwargs['role'] = role
        if text:
            kwargs['name'] = text
            like = "name"

        rows = self.db.rows(
            orderby="created", order="ASC",
            like=like,
            **kwargs
        )
        for r in rows:
            r.pop('password', None)
        return rows

    def create(self, data):
        """사용자 생성 — 에러 발생 시 상세 메시지 포함"""
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        data['password'] = self._hash_password(data['password'])
        data['created'] = now
        data['updated'] = now
        if not data.get('role'):
            data['role'] = 'user'

        has_username = self._has_username_column()
        if has_username:
            if not data.get('username'):
                data['username'] = data.get('email', '')
        else:
            data.pop('username', None)

        try:
            return self.db.insert(data)
        except Exception as e:
            raise Exception("사용자 생성 실패 (DB insert 오류): {} - {}. 입력 데이터 키: {}".format(
                type(e).__name__, str(e), list(data.keys())
            ))

    def update_profile(self, id, **fields):
        """프로필 업데이트"""
        fields['updated'] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.db.update(fields, id=id)

    def change_password(self, id, current_password, new_password):
        """비밀번호 변경"""
        user = self.db.get(id=id)
        if user is None:
            return False
        if not self._check_password(current_password, user.get('password', '')):
            return False
        hashed = self._hash_password(new_password)
        self.db.update(dict(
            password=hashed,
            updated=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ), id=id)
        return True

    def count(self, **kwargs):
        """사용자 수 조회"""
        return self.db.count(**kwargs) or 0

    def exists_username(self, username):
        """username 중복 확인"""
        if not self._has_username_column():
            return False
        user = self.db.get(username=username)
        return user is not None

    def exists_email(self, email):
        """email 중복 확인"""
        user = self.db.get(email=email)
        return user is not None

Model = User

# =============================================================================
# 프로젝트 루트 Struct (Composite Struct / Singleton)
# =============================================================================

import importlib.util
import sys

class Struct:
    def __init__(self):
        self.orm = wiz.model("portal/season/orm")
        self.session = wiz.model("portal/season/session").use()

        # 프로젝트 고유 Sub-Struct 클래스 로드
        self._User = wiz.model("struct/user")
        self._Doc = wiz.model("struct/doc")
        self._AI = wiz.model("struct/ai")
        self._FileParser = wiz.model("struct/file_parser")
        self._AIAgent = wiz.model("struct/ai_agent")
        self._DocExport = wiz.model("struct/doc_export")
        self._GraphGen = wiz.model("struct/graph_gen")

        # 패키지 Struct 캐시
        self._packages = {}

        # 테이블 자동 생성 + 마이그레이션
        self._init_tables()
        self._migrate()
        self._seed_instruction_presets()

    def _init_tables(self):
        """DB 테이블이 없으면 자동 생성"""
        tables = [
            "user",
            "doc_template", "doc_folder", "doc_instance", "doc_section",
            "ai_config", "user_profile", "ai_chat",
            "ai_instruction"
        ]
        for name in tables:
            try:
                db = self.orm.use(name)
                db.orm.create_table(safe=True)
            except Exception:
                pass

    def _migrate(self):
        """기존 테이블에 새 컬럼 추가 (마이그레이션)"""
        try:
            db = self.orm.use("user")
            database = db.orm._meta.database
            columns = [col.name for col in database.get_columns("user")]

            # username 컬럼이 없으면 추가
            if "username" not in columns:
                try:
                    database.execute_sql('ALTER TABLE `user` ADD COLUMN `username` VARCHAR(64) DEFAULT ""')
                    database.execute_sql('UPDATE `user` SET `username` = `email` WHERE `username` = "" OR `username` IS NULL')
                except Exception:
                    pass

            # avatar 컬럼이 없으면 추가
            if "avatar" not in columns:
                try:
                    database.execute_sql('ALTER TABLE `user` ADD COLUMN `avatar` VARCHAR(500) DEFAULT ""')
                except Exception:
                    pass
        except Exception:
            pass

        try:
            db = self.orm.use("doc_instance")
            database = db.orm._meta.database
            columns = [col.name for col in database.get_columns("doc_instance")]

            if "folder_id" not in columns:
                try:
                    database.execute_sql('ALTER TABLE `doc_instance` ADD COLUMN `folder_id` VARCHAR(32) DEFAULT ""')
                    database.execute_sql('CREATE INDEX `doc_instance_folder_id` ON `doc_instance` (`folder_id`)')
                except Exception:
                    pass
        except Exception:
            pass

    def db(self, name):
        """ORM Wrapper 반환"""
        return self.orm.use(name)

    def _seed_instruction_presets(self):
        """시스템 기본 인스트럭션 프리셋 시딩"""
        import datetime
        try:
            db = self.orm.use("ai_instruction")
            existing_titles = {
                row.get('title', '')
                for row in db.rows(user_id='system')
            }

            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            presets = [
                {
                    'title': '전문적/공식 어조',
                    'content': '전문적이고 공식적인 문서 어조를 사용하세요. 존칭과 격식체를 유지하고, 업무 문서에 적합한 표현을 사용합니다. 약어나 구어체는 피합니다.',
                    'category': 'general',
                    'sort_order': 1
                },
                {
                    'title': '간결하게 요점만',
                    'content': '불필요한 수식어나 반복 없이 핵심 내용만 간결하게 작성하세요. 서술형 본문도 기본 1~2문장으로 짧게 끝내고, 배경 설명이나 과한 완성도 보강은 생략합니다.',
                    'category': 'general',
                    'sort_order': 2
                },
                {
                    'title': '데이터/수치 중심',
                    'content': '가능한 한 구체적인 수치, 통계, 데이터를 포함하여 작성하세요. 정량적 근거를 제시하고, 추상적 표현보다 구체적 수치를 우선합니다.',
                    'category': 'general',
                    'sort_order': 3
                },
                {
                    'title': '창의적/자유로운 문체',
                    'content': '딱딱한 업무 문서 형식에 얽매이지 않고, 읽기 쉽고 생동감 있는 문체로 작성하세요. 비유나 예시를 적극 활용합니다.',
                    'category': 'general',
                    'sort_order': 4
                },
                {
                    'title': '공대 실험/프로젝트 레포트',
                    'content': '공학계열 레포트 형식으로 작성하세요. 목적, 이론적 배경, 실험/구현 방법, 결과, 그래프/표 해석, 오차 원인 또는 한계, 결론 순서가 드러나게 구성합니다. 수식, 단위, 변수명, 측정 조건, 실험 환경은 제공된 정보 안에서 정확히 쓰고, 없는 수치나 결과는 지어내지 않습니다. 그래프가 필요한 구간은 축 이름, 단위, 추세, 피크/변곡점, 비교군 차이를 함께 설명합니다. 문체는 감상문이 아니라 결과 중심의 공학 보고서 톤으로 유지합니다.',
                    'category': 'general',
                    'sort_order': 5
                }
            ]

            for preset in presets:
                if preset['title'] in existing_titles:
                    continue
                preset['user_id'] = 'system'
                preset['is_active'] = False
                preset['created'] = now
                preset['updated'] = now
                db.insert(preset)
        except Exception:
            pass

    def _load_struct_class_fresh(self, relative_path, module_name):
        fs = wiz.project.fs()
        module_path = fs.abspath(relative_path)
        cache_key = f"wiz_dynamic_{module_name}"
        if cache_key in sys.modules:
            del sys.modules[cache_key]
        spec = importlib.util.spec_from_file_location(cache_key, module_path)
        module = importlib.util.module_from_spec(spec)
        module.wiz = wiz
        spec.loader.exec_module(module)
        return module.Model

    @property
    def user(self):
        return self._User(self)

    @property
    def doc(self):
        return self._Doc(self)

    @property
    def ai(self):
        return self._AI(self)

    @property
    def file_parser(self):
        return self._load_struct_class_fresh("src/model/struct/file_parser.py", "file_parser")(self)

    @property
    def ai_agent(self):
        return self._load_struct_class_fresh("src/model/struct/ai_agent.py", "ai_agent")(self)

    @property
    def doc_export(self):
        return self._load_struct_class_fresh("src/model/struct/doc_export.py", "doc_export")(self)

    @property
    def graph_gen(self):
        return self._load_struct_class_fresh("src/model/struct/graph_gen.py", "graph_gen")(self)

    def __getattr__(self, name):
        if name.startswith('_'):
            raise AttributeError(name)
        if name not in self._packages:
            try:
                self._packages[name] = wiz.model(f"portal/{name}/struct")
            except Exception:
                raise AttributeError(f"Package '{name}' not found")
        return self._packages[name]

Model = Struct()

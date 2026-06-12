import peewee as pw

orm = wiz.model("portal/season/orm")
base = orm.base("base")

class Model(base):
    class Meta:
        db_table = "ai_config"

    id = pw.CharField(max_length=32, primary_key=True)
    provider = pw.CharField(max_length=50, default="openai")
    model_name = pw.CharField(max_length=100, default="gpt-4")
    api_key = pw.CharField(max_length=500, default="")
    endpoint = pw.CharField(max_length=500, default="")
    is_active = pw.BooleanField(default=False, index=True)
    extra_json = pw.TextField(default="{}")
    created = pw.DateTimeField(index=True)
    updated = pw.DateTimeField()

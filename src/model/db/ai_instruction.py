import peewee as pw

orm = wiz.model("portal/season/orm")
base = orm.base("base")

class MediumTextField(pw.TextField):
    field_type = "MEDIUMTEXT"

class Model(base):
    class Meta:
        db_table = "ai_instruction"

    id = pw.CharField(max_length=32, primary_key=True)
    user_id = pw.CharField(max_length=32, default="", index=True)
    title = pw.CharField(max_length=200, default="")
    content = MediumTextField(default="")
    category = pw.CharField(max_length=20, default="general", index=True)
    is_active = pw.BooleanField(default=False, index=True)
    sort_order = pw.IntegerField(default=0)
    created = pw.DateTimeField(index=True)
    updated = pw.DateTimeField()

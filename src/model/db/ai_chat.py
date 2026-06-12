import peewee as pw

orm = wiz.model("portal/season/orm")
base = orm.base("base")

class MediumTextField(pw.TextField):
    field_type = "MEDIUMTEXT"

class Model(base):
    class Meta:
        db_table = "ai_chat"

    id = pw.CharField(max_length=32, primary_key=True)
    instance_id = pw.CharField(max_length=32, index=True)
    section_id = pw.CharField(max_length=32, default="", index=True)
    role = pw.CharField(max_length=20, default="user")
    content = MediumTextField(default="")
    created = pw.DateTimeField(index=True)

import peewee as pw

orm = wiz.model("portal/season/orm")
base = orm.base("base")

class MediumTextField(pw.TextField):
    field_type = "MEDIUMTEXT"

class Model(base):
    class Meta:
        db_table = "doc_template"

    id = pw.CharField(max_length=32, primary_key=True)
    title = pw.CharField(max_length=200)
    description = pw.TextField(default="")
    file_path = pw.CharField(max_length=500, default="")
    file_type = pw.CharField(max_length=20, default="")
    fields_schema = MediumTextField(default="{}")
    created = pw.DateTimeField(index=True)
    updated = pw.DateTimeField()

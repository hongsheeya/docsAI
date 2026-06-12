import peewee as pw

orm = wiz.model("portal/season/orm")
base = orm.base("base")

class MediumTextField(pw.TextField):
    field_type = "MEDIUMTEXT"

class Model(base):
    class Meta:
        db_table = "doc_instance"

    id = pw.CharField(max_length=32, primary_key=True)
    folder_id = pw.CharField(max_length=32, index=True, default="")
    template_id = pw.CharField(max_length=32, index=True, default="")
    user_id = pw.CharField(max_length=32, index=True)
    title = pw.CharField(max_length=300)
    status = pw.CharField(max_length=20, default="draft", index=True)
    source_type = pw.CharField(max_length=20, default="template")
    content_json = MediumTextField(default="{}")
    settings_json = MediumTextField(default="{}")
    week_label = pw.CharField(max_length=50, default="")
    deadline = pw.CharField(max_length=20, default="")
    created = pw.DateTimeField(index=True)
    updated = pw.DateTimeField()

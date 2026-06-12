import peewee as pw

orm = wiz.model("portal/season/orm")
base = orm.base("base")

class MediumTextField(pw.TextField):
    field_type = "MEDIUMTEXT"

class Model(base):
    class Meta:
        db_table = "doc_section"

    id = pw.CharField(max_length=32, primary_key=True)
    instance_id = pw.CharField(max_length=32, index=True)
    section_key = pw.CharField(max_length=100, default="")
    section_title = pw.CharField(max_length=300, default="")
    content = MediumTextField(default="")
    sort_order = pw.IntegerField(default=0)
    status = pw.CharField(max_length=20, default="pending")
    created = pw.DateTimeField(index=True)
    updated = pw.DateTimeField()

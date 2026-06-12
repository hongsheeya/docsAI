import peewee as pw

orm = wiz.model("portal/season/orm")
base = orm.base("base")

class Model(base):
    class Meta:
        db_table = "doc_folder"

    id = pw.CharField(max_length=32, primary_key=True)
    user_id = pw.CharField(max_length=32, index=True)
    name = pw.CharField(max_length=120)
    sort_order = pw.IntegerField(default=0)
    created = pw.DateTimeField(index=True)
    updated = pw.DateTimeField()

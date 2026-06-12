import peewee as pw

orm = wiz.model("portal/season/orm")
base = orm.base("base")

class Model(base):
    class Meta:
        db_table = "user_profile"

    id = pw.CharField(max_length=32, primary_key=True)
    user_id = pw.CharField(max_length=32, index=True, unique=True)
    profile_data = pw.TextField(default="{}")
    preferences = pw.TextField(default="{}")
    memo = pw.TextField(default="")
    updated = pw.DateTimeField()

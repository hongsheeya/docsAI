import peewee as pw

orm = wiz.model("portal/season/orm")
base = orm.base("base")

class Model(base):
    class Meta:
        db_table = "user"

    id = pw.CharField(max_length=32, primary_key=True)
    username = pw.CharField(max_length=64, default="")
    email = pw.CharField(max_length=128)
    password = pw.CharField(max_length=200)
    name = pw.CharField(max_length=50)
    mobile = pw.CharField(max_length=20, default="")
    role = pw.CharField(max_length=16, default="user", index=True)
    avatar = pw.CharField(max_length=500, null=True, default="")
    created = pw.DateTimeField(index=True)
    updated = pw.DateTimeField()

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('pipeline', '0001_initial')]
    operations = [
        migrations.AddField(model_name='job', name='executor', field=models.CharField(default='server', max_length=16)),
        migrations.AddField(model_name='job', name='relay_lease', field=models.CharField(blank=True, max_length=64)),
        migrations.AddField(model_name='job', name='relay_run', field=models.CharField(blank=True, max_length=64)),
        migrations.CreateModel(name='DesktopService', fields=[
            ('id', models.PositiveSmallIntegerField(default=1, editable=False, primary_key=True, serialize=False)),
            ('enabled', models.BooleanField(default=False)),
            ('token_digest', models.CharField(blank=True, max_length=64)),
            ('capabilities', models.JSONField(default=dict)),
            ('heartbeat', models.DateTimeField(null=True)),
        ]),
    ]

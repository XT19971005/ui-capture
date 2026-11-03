import uuid
from django.conf import settings
from django.db import models


class Job(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    mode = models.CharField(max_length=32)
    title = models.CharField(max_length=160)
    status = models.CharField(max_length=16, default='queued')
    progress = models.FloatField(default=0)
    message = models.CharField(max_length=600, default='等待处理')
    partial_revision = models.PositiveIntegerField(default=0)
    cancel_requested = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    heartbeat = models.DateTimeField(null=True)
    started_at = models.DateTimeField(null=True)
    finished_at = models.DateTimeField(null=True)

    class Meta:
        indexes = [models.Index(fields=['status', 'created_at']), models.Index(fields=['owner', 'created_at'])]


class Audit(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    action = models.CharField(max_length=80)
    target = models.CharField(max_length=160)
    detail = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

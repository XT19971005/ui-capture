from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    email = models.EmailField(unique=True)
    display_name = models.CharField(max_length=80, blank=True)
    codex_model = models.CharField(max_length=120, blank=True)
    oidc_issuer = models.CharField(max_length=255, blank=True)
    oidc_subject = models.CharField(max_length=255, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['oidc_issuer', 'oidc_subject'], condition=~models.Q(oidc_subject=''), name='unique_oidc_identity')]

class LoginRequest(models.Model):
    digest = models.CharField(max_length=64, unique=True)
    session_key = models.CharField(max_length=64)
    verifier = models.CharField(max_length=128)
    next_url = models.CharField(max_length=2048)
    expires_at = models.DateTimeField()

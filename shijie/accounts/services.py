import hashlib
from django.conf import settings
from django.contrib.auth.models import Group
from django.db import transaction
from django.db.models import Q
from .models import User

ROLES = ('超级管理员','平台管理员','制作管理员','运维人员','使用者')

def roles(user):
    return set(user.groups.values_list('name',flat=True)) if user.is_authenticated and user.is_active else set()

def is_superadmin(user):
    return bool(user.is_authenticated and user.is_active and (user.is_superuser or '超级管理员' in roles(user)))

def is_admin(user):
    return bool(user.is_authenticated and user.is_active and (user.is_superuser or roles(user)&{'超级管理员','平台管理员'}))

def can_operate(user):
    return is_admin(user) or '运维人员' in roles(user)

def allowed(user):
    return bool(user.is_authenticated and user.is_active and (user.is_superuser or roles(user)&set(ROLES)))

def assignable_roles(user):
    if not is_admin(user):return ()
    return ROLES if user.is_superuser or '超级管理员' in roles(user) else ROLES[2:]

def can_manage_user(actor, target):
    return bool(is_admin(actor) and actor.pk!=target.pk and not target.is_superuser and
                ('超级管理员' in assignable_roles(actor) or not is_admin(target)))

@transaction.atomic
def provision(claims):
    email, issuer, sub = claims['email'], claims['issuer'], claims['subject']
    query=Q(email__iexact=email)
    if sub:query |= Q(oidc_issuer=issuer,oidc_subject=sub)
    candidates=list(User.objects.select_for_update().filter(query)[:2])
    if len(candidates)>1:raise ValueError('身份与邮箱登记冲突')
    new=not candidates
    user=candidates[0] if candidates else User(username='oidc-'+hashlib.sha256(email.encode()).hexdigest()[:24])
    if user.oidc_subject and (user.oidc_issuer,user.oidc_subject)!=(issuer,sub):
        raise ValueError('邮箱已绑定另一身份')
    user.email=email;user.display_name=claims['name'];user.oidc_issuer=issuer;user.oidc_subject=sub
    # Preserve the password hash used to validate sessions on other devices.
    if new or user.has_usable_password():user.set_unusable_password()
    user.full_clean(exclude=['password']);user.save()
    if new and email in {e.casefold() for e in settings.OIDC.get('bootstrap_admin_emails',[])}:
        user.groups.add(Group.objects.get_or_create(name='超级管理员')[0])
    return user

@transaction.atomic
def grant(actor, target, role):
    locked={u.pk:u for u in User.objects.select_for_update().filter(pk__in=[actor.pk,target.pk]).order_by('pk')}
    actor,target=locked[actor.pk],locked[target.pk]
    if not can_manage_user(actor,target):raise ValueError('无权修改此账号')
    if role is not None and role not in assignable_roles(actor):
        raise ValueError('不能越权授权管理员')
    target.groups.remove(*Group.objects.filter(name__in=ROLES))
    if role:target.groups.add(Group.objects.get_or_create(name=role)[0])
    from shijie.pipeline.models import Audit
    if role is None:
        from shijie.pipeline.models import Job
        Job.objects.filter(owner=target,status__in=['queued','running']).update(cancel_requested=True)
    Audit.objects.create(actor=actor,action='role.grant',target=str(target.pk),detail={'role':role})

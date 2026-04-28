from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from assets.models import Namespace, PhysicalHost, QualificationManagement, VirtualMachine
from bsecp.models import AuthorizationRecord, Module
from logs.utils import serialize_instance, log_resource_change
from mappings.models import PortMapping

TRACKED_MODELS = (
    VirtualMachine,
    PhysicalHost,
    Namespace,
    QualificationManagement,
    PortMapping,
    Module,
    AuthorizationRecord,
)


@receiver(pre_save)
def store_previous_snapshot(sender, instance, **kwargs):
    if sender not in TRACKED_MODELS or not instance.pk:
        return
    try:
        previous = sender.objects.get(pk=instance.pk)
        instance._audit_before = serialize_instance(previous)
    except sender.DoesNotExist:
        instance._audit_before = {}


@receiver(post_save)
def create_change_log(sender, instance, created, **kwargs):
    if sender not in TRACKED_MODELS:
        return
    before = getattr(instance, "_audit_before", {})
    after = serialize_instance(instance)
    changed_fields = [field for field, value in after.items() if before.get(field) != value]
    if created:
        changed_fields = list(after.keys())
    if not changed_fields and not created:
        return
    log_resource_change(
        instance=instance,
        action="created" if created else "updated",
        before_snapshot=before,
        after_snapshot=after,
        changed_fields=changed_fields,
    )


@receiver(post_delete)
def create_delete_log(sender, instance, **kwargs):
    if sender not in TRACKED_MODELS:
        return
    before = serialize_instance(instance)
    log_resource_change(
        instance=instance,
        action="deleted",
        before_snapshot=before,
        after_snapshot={},
        changed_fields=list(before.keys()),
    )

from core.models import EncryptedSecret
from core.security import decrypt_secret, encrypt_secret


MASKED_SECRET_PLACEHOLDER = "[ENCRYPTED]"


def _object_id_text(instance):
    if not instance or instance.pk in (None, ""):
        return ""
    return str(instance.pk)


def set_instance_secret(instance, field_name, plain_text):
    object_id = _object_id_text(instance)
    if not object_id:
        return
    namespace = instance._meta.label
    text = str(plain_text or "").strip()
    if not text:
        EncryptedSecret.objects.filter(namespace=namespace, object_id=object_id, field_name=field_name).delete()
        return
    ciphertext = encrypt_secret(text)
    if not ciphertext:
        return
    EncryptedSecret.objects.update_or_create(
        namespace=namespace,
        object_id=object_id,
        field_name=field_name,
        defaults={"ciphertext": ciphertext},
    )


def get_instance_secret(instance, field_name):
    object_id = _object_id_text(instance)
    if not object_id:
        return ""
    namespace = instance._meta.label
    payload = (
        EncryptedSecret.objects.filter(namespace=namespace, object_id=object_id, field_name=field_name)
        .values_list("ciphertext", flat=True)
        .first()
    )
    if not payload:
        return ""
    return decrypt_secret(payload)


def has_instance_secret(instance, field_name):
    object_id = _object_id_text(instance)
    if not object_id:
        return False
    return EncryptedSecret.objects.filter(
        namespace=instance._meta.label,
        object_id=object_id,
        field_name=field_name,
    ).exists()

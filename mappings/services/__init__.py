from .h3c_nat_sync import H3CNatSyncError, sync_h3c_nat_mappings
from .h3c_nat_apply import H3CNatApplyError, apply_h3c_nat_mapping, remove_h3c_nat_mapping

__all__ = [
    "H3CNatSyncError",
    "sync_h3c_nat_mappings",
    "H3CNatApplyError",
    "apply_h3c_nat_mapping",
    "remove_h3c_nat_mapping",
]

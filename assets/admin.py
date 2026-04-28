from django.contrib import admin

from assets.models import Namespace, PhysicalHost, PurchaseDetail, QualificationManagement, VirtualMachine

admin.site.register(VirtualMachine)
admin.site.register(PhysicalHost)
admin.site.register(Namespace)
admin.site.register(QualificationManagement)
admin.site.register(PurchaseDetail)

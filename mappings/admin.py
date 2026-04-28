from django.contrib import admin

from mappings.models import DomainMapping, PortMapping

admin.site.register(PortMapping)
admin.site.register(DomainMapping)


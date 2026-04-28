from django.contrib import admin

from bsecp.models import AuthorizationRecord, AuthorizationScope, Module

admin.site.register(Module)
admin.site.register(AuthorizationScope)
admin.site.register(AuthorizationRecord)


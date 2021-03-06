from django.contrib import admin
from django.utils.translation import ungettext

from nodeconductor.core.models import SynchronizationStates
from nodeconductor.quotas.admin import QuotaInline
from nodeconductor.structure.admin import ProtectedModelMixin
from nodeconductor.iaas import models
from nodeconductor.iaas import tasks


# Inspired by Django Snippet https://djangosnippets.org/snippets/2629/
class ReadonlyInlineMixin(object):
    can_delete = False
    extra = 0

    def has_add_permission(self, request):
        return False


class FlavorInline(admin.TabularInline):
    model = models.Flavor
    extra = 1


# noinspection PyMethodMayBeStatic
class CloudAdmin(admin.ModelAdmin):
    inlines = (
        FlavorInline,
    )
    list_display = ('name', 'customer', 'state')
    ordering = ('name', 'customer')

    actions = ['sync_services']

    def sync_services(self, request, queryset):
        queryset = queryset.filter(state=SynchronizationStates.IN_SYNC)
        service_uuids = list(queryset.values_list('uuid', flat=True))
        tasks_scheduled = queryset.count()

        tasks.sync_services.delay(service_uuids)

        message = ungettext(
            'One cloud account scheduled for update',
            '%(tasks_scheduled)d cloud accounts scheduled for update',
            tasks_scheduled
        )
        message = message % {
            'tasks_scheduled': tasks_scheduled,
        }

        self.message_user(request, message)

    sync_services.short_description = "Update selected cloud accounts from backend"


# noinspection PyMethodMayBeStatic
class CloudProjectMembershipAdmin(admin.ModelAdmin):
    readonly_fields = ('cloud', 'project')
    list_display = ('get_cloud_name', 'get_customer_name', 'get_project_name', 'state', 'tenant_id')
    ordering = ('cloud__customer__name', 'project__name', 'cloud__name')
    list_display_links = ('get_cloud_name',)
    search_fields = ('cloud__customer__name', 'project__name', 'cloud__name')
    inlines = [QuotaInline]

    actions = ['pull_cloud_memberships']

    def get_queryset(self, request):
        queryset = super(CloudProjectMembershipAdmin, self).get_queryset(request)
        return queryset.select_related('cloud', 'project', 'project__customer')

    def pull_cloud_memberships(self, request, queryset):
        # TODO: Extract to a service

        queryset = queryset.filter(state=SynchronizationStates.IN_SYNC)

        tasks_scheduled = 0

        for membership in queryset.iterator():
            membership.schedule_syncing()
            membership.save()

            tasks.pull_cloud_membership.delay(membership.pk)
            tasks_scheduled += 1

        message = ungettext(
            'One cloud project membership scheduled for update',
            '%(tasks_scheduled)d cloud project memberships scheduled for update',
            tasks_scheduled
        )
        message = message % {
            'tasks_scheduled': tasks_scheduled,
        }

        self.message_user(request, message)

    pull_cloud_memberships.short_description = "Update selected cloud project memberships from backend"

    def get_cloud_name(self, obj):
        return obj.cloud.name

    get_cloud_name.short_description = 'Cloud'

    def get_project_name(self, obj):
        return obj.project.name

    get_project_name.short_description = 'Project'

    def get_customer_name(self, obj):
        return obj.cloud.customer.name

    get_customer_name.short_description = 'Customer'


class InstanceLicenseInline(admin.TabularInline):
    model = models.InstanceLicense
    extra = 1


class InstanceAdmin(ProtectedModelMixin, admin.ModelAdmin):
    inlines = (
        InstanceLicenseInline,
    )

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return ['template']
        return []
    ordering = ('name',)
    list_display = ['name', 'uuid', 'backend_id', 'state', 'get_project_name', 'template']
    search_fields = ['name', 'uuid']
    list_filter = ['state', 'cloud_project_membership__project', 'template']

    def get_project_name(self, obj):
        return obj.cloud_project_membership.project.name

    get_project_name.short_description = 'Project'


class ImageInline(ReadonlyInlineMixin, admin.TabularInline):
    model = models.Image
    fields = ('get_cloud_name', 'get_customer_name', 'backend_id')
    readonly_fields = ('get_cloud_name', 'get_customer_name', 'backend_id')
    ordering = ('cloud__name', 'cloud__customer__name')
    verbose_name_plural = 'Connected cloud images'

    def get_cloud_name(self, obj):
        return obj.cloud.name
    get_cloud_name.short_description = 'Cloud'

    def get_customer_name(self, obj):
        return obj.cloud.customer.name
    get_customer_name.short_description = 'Customer'


class TemplateMappingInline(admin.TabularInline):
    model = models.TemplateMapping
    fields = ('description', 'backend_image_id')
    ordering = ('description', )
    extra = 3


class LicenseInline(admin.TabularInline):
    model = models.TemplateLicense.templates.through
    verbose_name_plural = 'Connected licenses'
    extra = 1


class TemplateAdmin(admin.ModelAdmin):
    inlines = (
        TemplateMappingInline,
        ImageInline,
        LicenseInline,
    )
    ordering = ('name', )
    list_display = ['name', 'uuid', 'sla_level']


class FlavorInline(admin.TabularInline):
    model = models.Flavor
    extra = 1


class SecurityGroupRuleInline(admin.TabularInline):
    model = models.SecurityGroupRule
    extra = 1


class SecurityGroupAdmin(admin.ModelAdmin):
    inlines = (
        SecurityGroupRuleInline,
    )
    list_display = ('cloud_project_membership', 'name')
    ordering = ('cloud_project_membership', 'name')


class InstanceSlaHistoryEventsInline(admin.TabularInline):
    model = models.InstanceSlaHistoryEvents
    fields = ('timestamp', 'state')
    ordering = ('timestamp', )
    extra = 1


class InstanceSlaHistoryAdmin(admin.ModelAdmin):
    inlines = (
        InstanceSlaHistoryEventsInline,
    )
    list_display = ('instance', 'period',  'value')
    list_filter = ('instance', 'period')


class FloatingIPAdmin(admin.ModelAdmin):
    list_display = ('cloud_project_membership', 'address', 'status')


admin.site.register(models.Cloud, CloudAdmin)
admin.site.register(models.CloudProjectMembership, CloudProjectMembershipAdmin)
admin.site.register(models.Instance, InstanceAdmin)
admin.site.register(models.SecurityGroup, SecurityGroupAdmin)
admin.site.register(models.Template, TemplateAdmin)
admin.site.register(models.TemplateLicense)
admin.site.register(models.InstanceSlaHistory, InstanceSlaHistoryAdmin)
admin.site.register(models.FloatingIP, FloatingIPAdmin)
admin.site.register(models.IpMapping)
admin.site.register(models.OpenStackSettings)

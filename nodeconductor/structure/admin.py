from django.contrib import admin
from django import forms

from nodeconductor.structure import models
from nodeconductor.cloud.models import Cloud


class CloudAdminForm(forms.ModelForm):
    clouds = forms.ModelMultipleChoiceField(Cloud.objects.all(),
                                            required=False)

    def __init__(self, *args, **kwargs):
        super(CloudAdminForm, self).__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial['clouds'] = self.instance.clouds.values_list('pk', flat=True)

    def save(self, *args, **kwargs):
        instance = super(CloudAdminForm, self).save(*args, **kwargs)
        if instance.pk:
            instance.clouds.clear()
            instance.clouds.add(*self.cleaned_data['clouds'])
        return instance


class ProjectAdmin(admin.ModelAdmin):
    form = CloudAdminForm

    list_display = ['name', 'uuid']
    search_fields = ['name', 'uuid']


admin.site.register(models.Customer)
admin.site.register(models.Project, ProjectAdmin)
admin.site.register(models.ProjectGroup)
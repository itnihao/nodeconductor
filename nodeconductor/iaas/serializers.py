from django.core.exceptions import ValidationError
from django.http import Http404

from rest_framework import serializers

from nodeconductor.core import models as core_models
from nodeconductor.cloud import models as cloud_models
from nodeconductor.backup import serializers as backup_serializers
from nodeconductor.core.serializers import PermissionFieldFilteringMixin, RelatedResourcesFieldMixin, IPsField
from nodeconductor.iaas import models
from nodeconductor.structure import serializers as structure_serializers


class InstanceSecurityGroupSerializer(serializers.ModelSerializer):

    protocol = serializers.CharField(read_only=True)
    from_port = serializers.CharField(read_only=True)
    to_port = serializers.CharField(read_only=True)
    ip_range = serializers.CharField(read_only=True)

    class Meta(object):
        model = models.InstanceSecurityGroup
        fields = ('name', 'protocol', 'from_port', 'to_port', 'ip_range')

    def validate_name(self, attrs, attr_name):
        name = attrs[attr_name]
        if not name in cloud_models.SecurityGroups.groups_names:
            raise ValidationError('There is no group with name %s' % name)
        return attrs


class InstanceCreateSerializer(PermissionFieldFilteringMixin,
                               serializers.HyperlinkedModelSerializer):

    security_groups = InstanceSecurityGroupSerializer(
        many=True, required=False, allow_add_remove=True, read_only=False)

    class Meta(object):
        model = models.Instance
        fields = ('url', 'hostname', 'description',
                  'template', 'flavor', 'project', 'security_groups', 'ssh_public_key')
        lookup_field = 'uuid'
        # TODO: Accept ip address count and volumes

    def __init__(self, *args, **kwargs):
        super(InstanceCreateSerializer, self).__init__(*args, **kwargs)
        self.user = kwargs['context']['user']

    def get_filtered_field_names(self):
        return 'project', 'flavor'

    def validate_security_groups(self, attrs, attr_name):
        if attr_name in attrs and attrs[attr_name] is None:
            del attrs[attr_name]
        return attrs

    def validate_ssh_public_key(self, attrs, attr_name):
        key = attrs[attr_name]
        if key.user != self.user:
            raise Http404
        return attrs


class InstanceSerializer(RelatedResourcesFieldMixin,
                         PermissionFieldFilteringMixin,
                         serializers.HyperlinkedModelSerializer):
    state = serializers.ChoiceField(choices=models.Instance.States.CHOICES, source='get_state_display')
    project_groups = structure_serializers.BasicProjectGroupSerializer(
        source='project.project_groups', many=True, read_only=True)
    ips = IPsField(source='ips', read_only=True)
    ssh_public_key_name = serializers.Field(source='ssh_public_key.name')
    backups = backup_serializers.BackupSerializer()
    backup_schedules = backup_serializers.BackupScheduleSerializer()

    security_groups = InstanceSecurityGroupSerializer(read_only=True)

    class Meta(object):
        model = models.Instance
        fields = (
            'url', 'uuid', 'hostname', 'description', 'start_time',
            'template', 'template_name',
            'cloud', 'cloud_name',
            'flavor', 'flavor_name',
            'project', 'project_name',
            'customer', 'customer_name',
            'ssh_public_key', 'ssh_public_key_name',
            'project_groups',
            'security_groups',
            'ips',
            'state',
            'backups', 'backup_schedules'
        )

        lookup_field = 'uuid'

    def get_filtered_field_names(self):
        return 'project', 'flavor'

    def get_related_paths(self):
        return 'flavor.cloud', 'template', 'project', 'flavor', 'project.customer'


class LicenseSerializer(serializers.HyperlinkedModelSerializer):

    projects_groups = structure_serializers.BasicProjectGroupSerializer(
        source='projects_groups', many=True, read_only=True)

    projects = structure_serializers.BasicProjectSerializer(
        source='projects', many=True, read_only=True)

    class Meta(object):
        model = models.License
        fields = (
            'url', 'uuid', 'name', 'license_type', 'service_type', 'setup_fee', 'monthly_fee',
            'projects', 'projects_groups',
        )
        lookup_field = 'uuid'


class TemplateSerializer(serializers.HyperlinkedModelSerializer):

    licenses = LicenseSerializer()

    class Meta(object):
        model = models.Template
        fields = (
            'url', 'uuid',
            'name', 'description', 'icon_url',
            'os',
            'is_active',
            'setup_fee',
            'monthly_fee',
            'licenses'
        )
        lookup_field = 'uuid'

    def get_fields(self):
        fields = super(TemplateSerializer, self).get_fields()

        try:
            user = self.context['request'].user
        except (KeyError, AttributeError):
            return fields

        if not user.is_staff:
            del fields['is_active']

        return fields


class SshKeySerializer(serializers.HyperlinkedModelSerializer):
    class Meta(object):
        model = core_models.SshPublicKey
        fields = ('url', 'uuid', 'name', 'public_key')
        lookup_field = 'uuid'


class PurchaseSerializer(RelatedResourcesFieldMixin, serializers.HyperlinkedModelSerializer):
    user = serializers.HyperlinkedRelatedField(
        source='user',
        view_name='user-detail',
        lookup_field='uuid',
        read_only=True,
    )
    user_full_name = serializers.Field(source='user.full_name')
    user_native_name = serializers.Field(source='user.native_name')

    class Meta(object):
        model = models.Purchase
        fields = (
            'url', 'uuid', 'date',
            'user', 'user_full_name', 'user_native_name',
            'customer', 'customer_name',
            'project', 'project_name',
        )
        lookup_field = 'uuid'

    def get_related_paths(self):
        return 'project.customer', 'project'


class ImageSerializer(RelatedResourcesFieldMixin,
                      PermissionFieldFilteringMixin,
                      serializers.HyperlinkedModelSerializer):
    architecture = serializers.ChoiceField(choices=models.Image.ARCHITECTURE_CHOICES, source='get_architecture_display')

    class Meta(object):
        model = models.Image
        fields = (
            'url', 'uuid', 'name', 'description',
            'cloud', 'cloud_name',
            'architecture',
        )
        lookup_field = 'uuid'

    def get_filtered_field_names(self):
        return 'cloud',

    def get_related_paths(self):
        return 'cloud',

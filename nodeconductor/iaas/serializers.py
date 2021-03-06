from __future__ import unicode_literals

from django.core.urlresolvers import reverse
from django.core.validators import MaxLengthValidator
from django.db import IntegrityError
from django.db.models import Max
from rest_framework import serializers, status, exceptions

from nodeconductor.backup import serializers as backup_serializers
from nodeconductor.core import models as core_models, serializers as core_serializers
from nodeconductor.core.fields import MappedChoiceField
from nodeconductor.iaas import models
from nodeconductor.monitoring.zabbix.db_client import ZabbixDBClient
from nodeconductor.quotas import serializers as quotas_serializers
from nodeconductor.structure import serializers as structure_serializers, models as structure_models
from nodeconductor.structure import filters as structure_filters


class BasicCloudSerializer(core_serializers.BasicInfoSerializer):
    class Meta(core_serializers.BasicInfoSerializer.Meta):
        model = models.Cloud


class BasicFlavorSerializer(core_serializers.BasicInfoSerializer):
    class Meta(core_serializers.BasicInfoSerializer.Meta):
        model = models.Flavor


class FlavorSerializer(serializers.HyperlinkedModelSerializer):
    class Meta(object):
        model = models.Flavor
        fields = ('url', 'uuid', 'name', 'ram', 'disk', 'cores')
        extra_kwargs = {
            'url': {'lookup_field': 'uuid'},
        }


class CloudSerializer(structure_serializers.PermissionFieldFilteringMixin,
                      core_serializers.AugmentedSerializerMixin,
                      serializers.HyperlinkedModelSerializer):
    flavors = FlavorSerializer(many=True, read_only=True)
    projects = structure_serializers.BasicProjectSerializer(many=True, read_only=True)
    customer_native_name = serializers.ReadOnlyField(source='customer.native_name')

    class Meta(object):
        model = models.Cloud
        fields = (
            'uuid',
            'url',
            'name',
            'customer', 'customer_name', 'customer_native_name',
            'flavors', 'projects', 'auth_url', 'dummy'
        )
        extra_kwargs = {
            'url': {'lookup_field': 'uuid'},
            'customer': {'lookup_field': 'uuid'},
        }

    def get_fields(self):
        # TODO: Extract to a proper mixin
        fields = super(CloudSerializer, self).get_fields()

        try:
            method = self.context['view'].request.method
        except (KeyError, AttributeError):
            return fields

        if method in ('PUT', 'PATCH'):
            fields['auth_url'].read_only = True
            fields['customer'].read_only = True

        return fields

    def get_filtered_field_names(self):
        return 'customer',

    def get_related_paths(self):
        return 'customer',


class UniqueConstraintError(exceptions.APIException):
    status_code = status.HTTP_302_FOUND
    default_detail = 'Entity already exists.'


class CloudProjectMembershipSerializer(structure_serializers.PermissionFieldFilteringMixin,
                                       core_serializers.AugmentedSerializerMixin,
                                       serializers.HyperlinkedModelSerializer):

    quotas = quotas_serializers.QuotaSerializer(many=True, read_only=True)
    state = MappedChoiceField(
        choices=[(v, k) for k, v in core_models.SynchronizationStates.CHOICES],
        choice_mappings={v: k for k, v in core_models.SynchronizationStates.CHOICES},
        read_only=True,
    )

    class Meta(object):
        model = models.CloudProjectMembership
        fields = (
            'url',
            'project', 'project_name', 'project_uuid',
            'cloud', 'cloud_name', 'cloud_uuid',
            'quotas',
            'state',
        )
        view_name = 'cloudproject_membership-detail'
        extra_kwargs = {
            'cloud': {'lookup_field': 'uuid'},
            'project': {'lookup_field': 'uuid'},
        }

    def get_filtered_field_names(self):
        return 'project', 'cloud'

    def get_related_paths(self):
        return 'project', 'cloud'

    def save(self, **kwargs):
        try:
            return super(CloudProjectMembershipSerializer, self).save(**kwargs)
        except IntegrityError:
            # unique constraint validation
            # TODO: Should be done on a higher level
            raise UniqueConstraintError()


class BasicSecurityGroupRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.SecurityGroupRule
        fields = ('protocol', 'from_port', 'to_port', 'cidr')


class SecurityGroupSerializer(serializers.HyperlinkedModelSerializer):

    rules = BasicSecurityGroupRuleSerializer(many=True, read_only=True)
    cloud_project_membership = CloudProjectMembershipSerializer()

    class Meta(object):
        model = models.SecurityGroup
        fields = ('url', 'uuid', 'name', 'description', 'rules', 'cloud_project_membership')
        extra_kwargs = {
            'url': {'lookup_field': 'uuid'},
        }
        view_name = 'security_group-detail'


class IpMappingSerializer(serializers.HyperlinkedModelSerializer):

    class Meta:
        model = models.IpMapping
        fields = ('url', 'uuid', 'public_ip', 'private_ip', 'project')
        extra_kwargs = {
            'url': {'lookup_field': 'uuid'},
            'project': {'lookup_field': 'uuid', 'view_name': 'project-detail'}
        }
        view_name = 'ip_mapping-detail'


class InstanceSecurityGroupSerializer(serializers.ModelSerializer):

    name = serializers.ReadOnlyField(source='security_group.name')
    rules = BasicSecurityGroupRuleSerializer(
        source='security_group.rules',
        many=True,
        read_only=True,
    )
    url = serializers.HyperlinkedRelatedField(
        source='security_group',
        lookup_field='uuid',
        view_name='security_group-detail',
        queryset=models.SecurityGroup.objects.all(),
    )
    description = serializers.ReadOnlyField(source='security_group.description')

    class Meta(object):
        model = models.InstanceSecurityGroup
        fields = ('url', 'name', 'rules', 'description')
        extra_kwargs = {
            'url': {'lookup_field': 'uuid'},
        }
        view_name = 'security_group-detail'


class IpCountValidator(MaxLengthValidator):
    message = 'Only %(limit_value)s ip address is supported.'


class InstanceCreateSerializer(structure_serializers.PermissionFieldFilteringMixin,
                               serializers.HyperlinkedModelSerializer):

    security_groups = InstanceSecurityGroupSerializer(
        many=True, required=False, read_only=False)
    project = serializers.HyperlinkedRelatedField(
        view_name='project-detail',
        lookup_field='uuid',
        queryset=structure_models.Project.objects.all(),
        required=True,
        write_only=True,
    )
    flavor = serializers.HyperlinkedRelatedField(
        view_name='flavor-detail',
        lookup_field='uuid',
        queryset=models.Flavor.objects.all(),
        required=True,
        write_only=True,
    )
    ssh_public_key = serializers.HyperlinkedRelatedField(
        view_name='sshpublickey-detail',
        lookup_field='uuid',
        queryset=core_models.SshPublicKey.objects.all(),
        required=False,
        write_only=True,
    )
    template = serializers.HyperlinkedRelatedField(
        view_name='iaastemplate-detail',
        lookup_field='uuid',
        queryset=models.Template.objects.all(),
        required=True,
    )

    external_ips = serializers.ListField(
        child=core_serializers.IPAddressField(),
        allow_null=True,
        required=False,
        validators=[IpCountValidator(1)],
    )

    class Meta(object):
        model = models.Instance
        fields = (
            'url', 'uuid',
            'name', 'description',
            'template',
            'project',
            'security_groups', 'flavor', 'ssh_public_key', 'external_ips',
            'system_volume_size', 'data_volume_size', 'user_data',
            'type',
        )
        extra_kwargs = {
            'url': {'lookup_field': 'uuid'},
        }

    def get_fields(self):
        fields = super(InstanceCreateSerializer, self).get_fields()
        fields['system_volume_size'].required = False

        try:
            request = self.context['view'].request
            user = request.user
        except (KeyError, AttributeError):
            return fields

        fields['ssh_public_key'].queryset = fields['ssh_public_key'].queryset.filter(user=user)

        clouds = structure_filters.filter_queryset_for_user(models.Cloud.objects.all(), user)
        fields['template'].queryset = fields['template'].queryset.filter(images__cloud__in=clouds).distinct()

        return fields

    def get_filtered_field_names(self):
        return 'project', 'flavor'

    def validate(self, attrs):
        flavor = attrs['flavor']
        membership = attrs.get('cloud_project_membership')

        external_ips = attrs.get('external_ips')
        if external_ips:
            ip_exists = models.FloatingIP.objects.filter(
                address=external_ips,
                status='DOWN',
                cloud_project_membership=membership,
            ).exists()
            if not ip_exists:
                raise serializers.ValidationError("External IP is not from the list of available floating IPs.")

        template = attrs['template']

        max_min_disk = (
            models.Image.objects
            .filter(template=template, cloud=flavor.cloud)
            .aggregate(Max('min_disk'))
        )['min_disk__max']

        if max_min_disk is None:
            raise serializers.ValidationError("Template %s is not available on cloud %s"
                                              % (template, flavor.cloud))

        system_volume_size = attrs['system_volume_size'] if 'system_volume_size' in attrs else flavor.disk
        if max_min_disk > system_volume_size:
            raise serializers.ValidationError("System volume size has to be greater than %s" % max_min_disk)

        data_volume_size = attrs.get('data_volume_size', models.Instance.DEFAULT_DATA_VOLUME_SIZE)

        instance_quota_usage = {
            'storage': data_volume_size + system_volume_size,
            'vcpu': flavor.cores,
            'ram': flavor.ram,
            'max_instances': 1
        }
        quota_errors = membership.validate_quota_change(instance_quota_usage)
        if quota_errors:
            raise serializers.ValidationError(
                'One or more quotas are over limit: \n' + '\n'.join(quota_errors))

        return attrs

    def create(self, validated_data):
        del validated_data['project']

        key = validated_data.pop('ssh_public_key', None)
        if key:
            validated_data['key_name'] = key.name
            validated_data['key_fingerprint'] = key.fingerprint

        flavor = validated_data.pop('flavor')
        validated_data['cores'] = flavor.cores
        validated_data['ram'] = flavor.ram

        if 'system_volume_size' not in validated_data:
            validated_data['system_volume_size'] = flavor.disk

        security_groups = [data['security_group'] for data in validated_data.pop('security_groups', [])]
        instance = super(InstanceCreateSerializer, self).create(validated_data)
        for security_group in security_groups:
            models.InstanceSecurityGroup.objects.create(instance=instance, security_group=security_group)

        # XXX: dirty fix - we need it because first provisioning looks for key and flavor as instance attributes
        instance.flavor = flavor
        instance.key = key
        instance.cloud = flavor.cloud

        return instance

    def to_internal_value(self, data):
        if 'external_ips' in data and not data['external_ips']:
            data['external_ips'] = []
        internal_value = super(InstanceCreateSerializer, self).to_internal_value(data)
        if 'external_ips' in internal_value:
            if not internal_value['external_ips']:
                internal_value['external_ips'] = None
            else:
                internal_value['external_ips'] = internal_value['external_ips'][0]

        try:
            internal_value['cloud_project_membership'] = models.CloudProjectMembership.objects.get(
                project=internal_value['project'],
                cloud=internal_value['flavor'].cloud,
            )
        except models.CloudProjectMembership.DoesNotExist:
            raise serializers.ValidationError({"flavor": "Flavor is not within project's clouds."})

        return internal_value


class InstanceUpdateSerializer(serializers.HyperlinkedModelSerializer):

    security_groups = InstanceSecurityGroupSerializer(
        many=True, required=False, read_only=False)

    class Meta(object):
        model = models.Instance
        fields = ('url', 'name', 'description', 'security_groups')
        extra_kwargs = {
            'url': {'lookup_field': 'uuid'},
        }

    def update(self, instance, validated_data):
        security_groups = validated_data.pop('security_groups', [])
        security_groups = [data['security_group'] for data in security_groups]
        instance = super(InstanceUpdateSerializer, self).update(instance, validated_data)
        models.InstanceSecurityGroup.objects.filter(instance=instance).delete()
        for security_group in security_groups:
            models.InstanceSecurityGroup.objects.create(instance=instance, security_group=security_group)
        return instance


class InstanceSecurityGroupsInlineUpdateSerializer(serializers.Serializer):
    security_groups = InstanceSecurityGroupSerializer(
        many=True, required=False, read_only=False)


class CloudProjectMembershipLinkSerializer(serializers.Serializer):
    id = serializers.CharField(required=True)
    template = serializers.HyperlinkedRelatedField(
        view_name='iaastemplate-detail',
        lookup_field='uuid',
        queryset=models.Template.objects.all(),
        required=False,
    )

    def validate_id(self, attrs, name):
        backend_id = attrs[name]
        cpm = self.context['membership']
        if models.Instance.objects.filter(cloud_project_membership=cpm,
                                          backend_id=backend_id).exists():
            raise serializers.ValidationError(
                "Instance with a specified backend ID already exists.")
        return attrs


class CloudProjectMembershipQuotaSerializer(serializers.Serializer):
    storage = serializers.IntegerField(min_value=1, required=False)
    max_instances = serializers.IntegerField(min_value=1, required=False)
    ram = serializers.IntegerField(min_value=1, required=False)
    vcpu = serializers.IntegerField(min_value=1, required=False)


class InstanceResizeSerializer(structure_serializers.PermissionFieldFilteringMixin,
                               serializers.Serializer):
    flavor = serializers.HyperlinkedRelatedField(
        view_name='flavor-detail',
        lookup_field='uuid',
        queryset=models.Flavor.objects.all(),
        required=False,
    )
    disk_size = serializers.IntegerField(min_value=1, required=False)

    def __init__(self, instance, *args, **kwargs):
        self.resized_instance = instance
        super(InstanceResizeSerializer, self).__init__(*args, **kwargs)

    def get_filtered_field_names(self):
        return 'flavor',

    def validate(self, attrs):
        flavor = attrs.get('flavor')
        disk_size = attrs.get('disk_size')

        if flavor is not None and disk_size is not None:
            raise serializers.ValidationError("Cannot resize both disk size and flavor simultaneously")
        if flavor is None and disk_size is None:
            raise serializers.ValidationError("Either disk_size or flavor is required")

        membership = self.resized_instance.cloud_project_membership
        # TODO: consider abstracting the validation below and merging with the InstanceCreateSerializer one
        # check quotas in advance

        # If disk size was changed - we need to check if it fits quotas
        if disk_size is not None:
            old_size = self.resized_instance.data_volume_size
            new_size = disk_size
            quota_usage = {
                'storage': new_size - old_size
            }

        # Validate flavor modification
        else:
            old_cores = self.resized_instance.cores
            old_ram = self.resized_instance.ram
            quota_usage = {
                'vcpu': flavor.cores - old_cores,
                'ram': flavor.ram - old_ram,
            }

        quota_errors = membership.validate_quota_change(quota_usage)
        if quota_errors:
            raise serializers.ValidationError(
                'One or more quotas are over limit: \n' + '\n'.join(quota_errors))

        return attrs


class InstanceLicenseSerializer(serializers.ModelSerializer):

    name = serializers.ReadOnlyField(source='template_license.name')
    license_type = serializers.ReadOnlyField(source='template_license.license_type')
    service_type = serializers.ReadOnlyField(source='template_license.service_type')

    class Meta(object):
        model = models.InstanceLicense
        fields = (
            'uuid', 'name', 'license_type', 'service_type', 'setup_fee', 'monthly_fee',
        )
        extra_kwargs = {
            'url': {'lookup_field': 'uuid'},
        }


class InstanceSerializer(core_serializers.AugmentedSerializerMixin,
                         serializers.HyperlinkedModelSerializer):
    state = serializers.ReadOnlyField(source='get_state_display')
    project_groups = structure_serializers.BasicProjectGroupSerializer(
        source='cloud_project_membership.project.project_groups', many=True, read_only=True)
    external_ips = serializers.ListField(
        child=core_serializers.IPAddressField(),
    )
    internal_ips = serializers.ListField(
        child=core_serializers.IPAddressField(),
        read_only=True,
    )
    backups = backup_serializers.BackupSerializer(many=True)
    backup_schedules = backup_serializers.BackupScheduleSerializer(many=True)

    security_groups = InstanceSecurityGroupSerializer(many=True, read_only=True)
    instance_licenses = InstanceLicenseSerializer(many=True, read_only=True)
    # project
    project = serializers.HyperlinkedRelatedField(
        source='cloud_project_membership.project',
        view_name='project-detail',
        read_only=True,
        lookup_field='uuid',
    )
    project_name = serializers.ReadOnlyField(source='cloud_project_membership.project.name')
    project_uuid = serializers.ReadOnlyField(source='cloud_project_membership.project.uuid')
    # cloud
    cloud = serializers.HyperlinkedRelatedField(
        source='cloud_project_membership.cloud',
        view_name='cloud-detail',
        read_only=True,
        lookup_field='uuid',
    )
    cloud_name = serializers.ReadOnlyField(source='cloud_project_membership.cloud.name')
    cloud_uuid = serializers.ReadOnlyField(source='cloud_project_membership.cloud.uuid')
    # customer
    customer = serializers.HyperlinkedRelatedField(
        source='cloud_project_membership.project.customer',
        view_name='customer-detail',
        read_only=True,
        lookup_field='uuid',
    )
    customer_name = serializers.ReadOnlyField(source='cloud_project_membership.project.customer.name')
    customer_abbreviation = serializers.ReadOnlyField(source='cloud_project_membership.project.customer.abbreviation')
    customer_native_name = serializers.ReadOnlyField(source='cloud_project_membership.project.customer.native_name')
    # template
    template = serializers.HyperlinkedRelatedField(
        view_name='iaastemplate-detail',
        read_only=True,
        lookup_field='uuid',
    )
    template_name = serializers.ReadOnlyField(source='template.name')
    template_os = serializers.ReadOnlyField(source='template.os')

    created = serializers.DateTimeField()

    class Meta(object):
        model = models.Instance
        fields = (
            'url', 'uuid', 'name', 'description', 'start_time',
            'template', 'template_name', 'template_os',
            'cloud', 'cloud_name', 'cloud_uuid',
            'project', 'project_name', 'project_uuid',
            'customer', 'customer_name', 'customer_native_name', 'customer_abbreviation',
            'key_name', 'key_fingerprint',
            'project_groups',
            'security_groups',
            'external_ips', 'internal_ips',
            'state',
            'backups', 'backup_schedules',
            'instance_licenses',
            'agreed_sla',
            'system_volume_size',
            'data_volume_size',
            'cores', 'ram',
            'created',
            'user_data',
            'type',
        )
        read_only_fields = (
            'key_name',
            'system_volume_size',
            'data_volume_size',
        )
        extra_kwargs = {
            'url': {'lookup_field': 'uuid'},
        }

    def to_representation(self, instance):
        # We need this hook, because ips have to be represented as list
        instance.external_ips = [instance.external_ips] if instance.external_ips else []
        instance.internal_ips = [instance.internal_ips] if instance.internal_ips else []
        return super(InstanceSerializer, self).to_representation(instance)


class TemplateLicenseSerializer(serializers.HyperlinkedModelSerializer):

    projects_groups = structure_serializers.BasicProjectGroupSerializer(
        source='get_projects_groups', many=True, read_only=True)

    projects = structure_serializers.BasicProjectSerializer(
        source='get_projects', many=True, read_only=True)

    class Meta(object):
        model = models.TemplateLicense
        fields = (
            'url', 'uuid', 'name', 'license_type', 'service_type', 'setup_fee', 'monthly_fee',
            'projects', 'projects_groups',
        )
        extra_kwargs = {
            'url': {'lookup_field': 'uuid'},
        }


class TemplateImageSerializer(core_serializers.AugmentedSerializerMixin, serializers.ModelSerializer):

    cloud = serializers.HyperlinkedRelatedField(
        view_name='cloud-detail', lookup_field='uuid', read_only=True)

    class Meta(object):
        model = models.Image
        fields = ('cloud', 'cloud_uuid', 'min_disk', 'min_ram', 'backend_id')
        related_paths = ('cloud',)


class TemplateSerializer(serializers.HyperlinkedModelSerializer):

    template_licenses = TemplateLicenseSerializer(many=True)
    images = serializers.SerializerMethodField()

    class Meta(object):
        view_name = 'iaastemplate-detail'
        model = models.Template
        fields = (
            'url', 'uuid',
            'name', 'description', 'icon_url', 'icon_name',
            'os', 'os_type',
            'is_active',
            'sla_level',
            'setup_fee',
            'monthly_fee',
            'template_licenses', 'images',
            'type', 'application_type',
        )
        extra_kwargs = {
            'url': {'lookup_field': 'uuid'},
            'template_licenses': {'lookup_field': 'uuid'},
        }

    def get_images(self, obj):
        try:
            user = self.context['request'].user
        except (KeyError, AttributeError):
            return None

        queryset = structure_filters.filter_queryset_for_user(obj.images.all(), user)
        images_serializer = TemplateImageSerializer(
            queryset, many=True, read_only=True, context=self.context)

        return images_serializer.data

    def get_fields(self):
        fields = super(TemplateSerializer, self).get_fields()

        try:
            user = self.context['request'].user
        except (KeyError, AttributeError):
            return fields

        if not user.is_staff:
            del fields['is_active']

        return fields


class TemplateCreateSerializer(serializers.HyperlinkedModelSerializer):

    class Meta(object):
        view_name = 'iaastemplate-detail'
        model = models.Template
        fields = (
            'url', 'uuid',
            'name', 'description', 'icon_url',
            'os',
            'sla_level',
            'setup_fee',
            'monthly_fee',
            'template_licenses',
            'type', 'application_type',
            'is_active',
        )
        extra_kwargs = {
            'url': {'lookup_field': 'uuid'},
            'template_licenses': {'lookup_field': 'uuid'},
        }


class FloatingIPSerializer(serializers.HyperlinkedModelSerializer):
    cloud_project_membership = CloudProjectMembershipSerializer()

    class Meta:
        model = models.FloatingIP
        fields = ('url', 'uuid', 'status', 'address', 'cloud_project_membership')
        extra_kwargs = {
            'url': {'lookup_field': 'uuid'},
        }
        view_name = 'floating_ip-detail'


class SshKeySerializer(serializers.HyperlinkedModelSerializer):
    user_uuid = serializers.ReadOnlyField(source='user.uuid')

    class Meta(object):
        model = core_models.SshPublicKey
        fields = ('url', 'uuid', 'name', 'public_key', 'fingerprint', 'user_uuid')
        read_only_fields = ('fingerprint',)
        extra_kwargs = {
            'url': {'lookup_field': 'uuid'},
        }

    def get_fields(self):
        fields = super(SshKeySerializer, self).get_fields()

        try:
            user = self.context['request'].user
        except (KeyError, AttributeError):
            return fields

        if not user.is_staff:
            del fields['user_uuid']

        return fields


class ServiceSerializer(serializers.Serializer):
    url = serializers.SerializerMethodField('get_service_url')
    service_type = serializers.SerializerMethodField()
    state = serializers.ReadOnlyField(source='get_state_display')
    name = serializers.ReadOnlyField()
    uuid = serializers.ReadOnlyField()
    agreed_sla = serializers.ReadOnlyField()
    actual_sla = serializers.SerializerMethodField()
    template_name = serializers.ReadOnlyField(source='template.name')
    customer_name = serializers.ReadOnlyField(source='cloud_project_membership.project.customer.name')
    customer_native_name = serializers.ReadOnlyField(source='cloud_project_membership.project.customer.native_name')
    customer_abbreviation = serializers.ReadOnlyField(source='cloud_project_membership.project.customer.abbreviation')
    project_name = serializers.ReadOnlyField(source='cloud_project_membership.project.name')
    project_uuid = serializers.ReadOnlyField(source='cloud_project_membership.project.uuid')
    project_url = serializers.SerializerMethodField()
    project_groups = serializers.SerializerMethodField()
    access_information = serializers.ListField(
        source='external_ips',
        child=core_serializers.IPAddressField(),
        read_only=True,
    )

    class Meta(object):
        fields = (
            'url',
            'uuid',
            'state',
            'name', 'template_name',
            'customer_name',
            'customer_native_name',
            'customer_abbreviation',
            'project_name', 'project_uuid', 'project_url',
            'project_groups',
            'agreed_sla', 'actual_sla',
            'service_type',
            'access_information',
        )
        view_name = 'service-detail'
        extra_kwargs = {
            'url': {'lookup_field': 'uuid'},
        }

    def get_project_url(self, obj):
        try:
            request = self.context['request']
        except AttributeError:
            raise AttributeError('ServiceSerializer have to be initialized with `request` in context')
        return request.build_absolute_uri(
            reverse('project-detail', kwargs={'uuid': obj.cloud_project_membership.project.uuid}))

    def get_service_type(self, obj):
        return 'IaaS'

    def get_actual_sla(self, obj):
        try:
            period = self.context['period']
        except (KeyError, AttributeError):
            raise AttributeError('ServiceSerializer has to be initialized with `request` in context')
        try:
            return models.InstanceSlaHistory.objects.get(instance=obj, period=period).value
        except models.InstanceSlaHistory.DoesNotExist:
            return None

    def get_service_url(self, obj):
        try:
            request = self.context['request']
        except (KeyError, AttributeError):
            raise AttributeError('ServiceSerializer has to be initialized with `request` in context')

        # TODO: this could use something similar to backup's generic model for all resources
        view_name = 'service-detail'
        service_instance = obj
        hyperlinked_field = serializers.HyperlinkedRelatedField(
            view_name=view_name,
            lookup_field='uuid',
            read_only=True,
        )
        return hyperlinked_field.get_url(service_instance, view_name, request, format=None)

    # TODO: this shouldn't come from this endpoint, but UI atm depends on it
    def get_project_groups(self, obj):
        try:
            request = self.context['request']
        except (KeyError, AttributeError):
            raise AttributeError('ServiceSerializer has to be initialized with `request` in context')

        service_instance = obj
        groups = structure_serializers.BasicProjectGroupSerializer(
            service_instance.cloud_project_membership.project.project_groups.all(),
            many=True,
            read_only=True,
            context={'request': request}
        )
        return groups.data

    def to_representation(self, instance):
        # We need this hook, because ips have to be represented as list
        instance.external_ips = [instance.external_ips] if instance.external_ips else []
        instance.internal_ips = [instance.internal_ips] if instance.internal_ips else []
        return super(ServiceSerializer, self).to_representation(instance)


class UsageStatsSerializer(serializers.Serializer):
    segments_count = serializers.IntegerField(min_value=0)
    start_timestamp = serializers.IntegerField(min_value=0)
    end_timestamp = serializers.IntegerField(min_value=0)
    item = serializers.CharField()

    def validate_item(self, value):
        if not value in ZabbixDBClient.items:
            raise serializers.ValidationError(
                "GET parameter 'item' have to be from list: %s" % ZabbixDBClient.items.keys())
        return value

    def get_stats(self, instances):
        self.attrs = self.data
        zabbix_db_client = ZabbixDBClient()
        return zabbix_db_client.get_item_stats(
            instances, self.data['item'],
            self.data['start_timestamp'], self.data['end_timestamp'], self.data['segments_count'])


class SlaHistoryEventSerializer(serializers.Serializer):
    timestamp = serializers.IntegerField()
    state = serializers.CharField()


class StatsAggregateSerializer(serializers.Serializer):
    MODEL_NAME_CHOICES = (('project', 'project'), ('customer', 'customer'), ('project_group', 'project_group'))
    MODEL_CLASSES = {
        'project': structure_models.Project,
        'customer': structure_models.Customer,
        'project_group': structure_models.ProjectGroup,
    }

    model_name = serializers.ChoiceField(choices=MODEL_NAME_CHOICES)
    uuid = serializers.CharField(allow_null=True)

    def get_projects(self, user):
        model = self.MODEL_CLASSES[self.data['model_name']]
        queryset = structure_filters.filter_queryset_for_user(model.objects.all(), user)

        if 'uuid' in self.data and self.data['uuid']:
            queryset = queryset.filter(uuid=self.data['uuid'])

        if self.data['model_name'] == 'project':
            return queryset.all()
        elif self.data['model_name'] == 'project_group':
            projects = structure_models.Project.objects.filter(project_groups__in=list(queryset))
            return structure_filters.filter_queryset_for_user(projects, user)
        else:
            projects = structure_models.Project.objects.filter(customer__in=list(queryset))
            return structure_filters.filter_queryset_for_user(projects, user)

    def get_memberships(self, user):
        projects = self.get_projects(user)
        return models.CloudProjectMembership.objects.filter(project__in=projects).all()

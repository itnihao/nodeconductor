from decimal import Decimal
from random import randint

from django.core.urlresolvers import reverse
from django.utils import timezone
import factory
import factory.fuzzy

from nodeconductor.iaas import models
from nodeconductor.core import models as core_models
from nodeconductor.structure.tests import factories as structure_factories


class CloudFactory(factory.DjangoModelFactory):
    class Meta(object):
        model = models.Cloud

    name = factory.Sequence(lambda n: 'cloud%s' % n)
    customer = factory.SubFactory(structure_factories.CustomerFactory)


class FlavorFactory(factory.DjangoModelFactory):
    class Meta(object):
        model = models.Flavor

    name = factory.Sequence(lambda n: 'flavor%s' % n)
    cloud = factory.SubFactory(CloudFactory)

    cores = 4 * 1024
    ram = 2 * 1024
    disk = 10 * 1024

    flavor_id = factory.Sequence(lambda n: 'flavor-id%s' % n)


class CloudProjectMembershipFactory(factory.DjangoModelFactory):
    class Meta(object):
        model = models.CloudProjectMembership

    cloud = factory.SubFactory(CloudFactory)
    project = factory.SubFactory(structure_factories.ProjectFactory)
    tenant_id = factory.Sequence(lambda n: 'tenant_id_%s' % n)

    @classmethod
    def get_url(cls, membership=None):
        if membership is None:
            membership = CloudProjectMembershipFactory()
        return 'http://testserver' + reverse('cloudproject_membership-detail', kwargs={'pk': membership.pk})

    @classmethod
    def get_list_url(cls):
        return 'http://testserver' + reverse('cloudproject_membership-list')


class SecurityGroupFactory(factory.DjangoModelFactory):
    class Meta(object):
        model = models.SecurityGroup

    cloud_project_membership = factory.SubFactory(CloudProjectMembershipFactory)
    name = factory.Sequence(lambda n: 'group%s' % n)
    description = factory.Sequence(lambda n: 'very good group %s' % n)

    @classmethod
    def get_url(cls, security_group=None):
        if security_group is None:
            security_group = CloudProjectMembershipFactory()
        return 'http://testserver' + reverse('security_group-detail', kwargs={'uuid': security_group.uuid})


class SecurityGroupRuleFactory(factory.DjangoModelFactory):
    class Meta(object):
        model = models.SecurityGroupRule

    security_group = factory.SubFactory(SecurityGroupFactory)
    protocol = models.SecurityGroupRule.tcp
    from_port = factory.fuzzy.FuzzyInteger(1, 65535)
    to_port = factory.fuzzy.FuzzyInteger(1, 65535)
    cidr = factory.LazyAttribute(lambda o: '.'.join('%s' % randint(1, 255) for i in range(4)) + '/24')


class IpMappingFactory(factory.DjangoModelFactory):
    class Meta(object):
        model = models.IpMapping

    public_ip = factory.LazyAttribute(lambda o: '84.%s' % '.'.join(
        '%s' % randint(0, 255) for _ in range(3)))
    private_ip = factory.LazyAttribute(lambda o: '10.%s' % '.'.join(
        '%s' % randint(0, 255) for _ in range(3)))
    project = factory.SubFactory(structure_factories.ProjectFactory)

    @classmethod
    def get_url(cls, ip_mapping=None):
        ip_mapping = ip_mapping or IpMappingFactory()

        return 'http://testserver' + reverse('ip_mapping-detail', kwargs={'uuid': ip_mapping.uuid})

    @classmethod
    def get_list_url(cls):
        return 'http://testserver' + reverse('ip_mapping-list')


class TemplateFactory(factory.DjangoModelFactory):
    class Meta(object):
        model = models.Template

    name = factory.Sequence(lambda n: 'template%s' % n)
    description = factory.Sequence(lambda n: 'description %d' % n)
    icon_url = factory.Sequence(lambda n: 'http://example.com/%d.png' % n)
    is_active = True
    sla_level = factory.LazyAttribute(lambda o: Decimal('99.9'))
    setup_fee = factory.fuzzy.FuzzyDecimal(10.0, 50.0, 3)
    monthly_fee = factory.fuzzy.FuzzyDecimal(0.5, 20.0, 3)


class TemplateMappingFactory(factory.DjangoModelFactory):
    class Meta(object):
        model = models.TemplateMapping

    template = factory.SubFactory(TemplateFactory)
    backend_image_id = factory.Sequence(lambda n: 'image-id-%s' % n)


class TemplateLicenseFactory(factory.DjangoModelFactory):
    class Meta(object):
        model = models.TemplateLicense

    name = factory.Sequence(lambda n: 'License%s' % n)
    license_type = factory.Sequence(lambda n: 'LicenseType%s' % n)
    service_type = models.TemplateLicense.Services.IAAS
    setup_fee = factory.fuzzy.FuzzyDecimal(10.0, 50.0, 3)
    monthly_fee = factory.fuzzy.FuzzyDecimal(0.5, 20.0, 3)


class ImageFactory(factory.DjangoModelFactory):
    class Meta(object):
        model = models.Image

    cloud = factory.SubFactory(CloudFactory)
    template = factory.SubFactory(TemplateFactory)
    backend_id = factory.Sequence(lambda n: 'id%s' % n)


class SshPublicKeyFactory(factory.DjangoModelFactory):
    class Meta(object):
        model = core_models.SshPublicKey

    user = factory.SubFactory(structure_factories.UserFactory)
    name = factory.Sequence(lambda n: 'ssh_public_key%s' % n)
    public_key = (
        "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDDURXDP5YhOQUYoDuTxJ84DuzqMJYJqJ8+SZT28"
        "TtLm5yBDRLKAERqtlbH2gkrQ3US58gd2r8H9jAmQOydfvgwauxuJUE4eDpaMWupqquMYsYLB5f+vVGhdZbbzfc6DTQ2rY"
        "dknWoMoArlG7MvRMA/xQ0ye1muTv+mYMipnd7Z+WH0uVArYI9QBpqC/gpZRRIouQ4VIQIVWGoT6M4Kat5ZBXEa9yP+9du"
        "D2C05GX3gumoSAVyAcDHn/xgej9pYRXGha4l+LKkFdGwAoXdV1z79EG1+9ns7wXuqMJFHM2KDpxAizV0GkZcojISvDwuh"
        "vEAFdOJcqjyyH4FOGYa8usP1 test"
    )

    @classmethod
    def get_url(self, key):
        if key is None:
            key = SshPublicKeyFactory()
        return 'http://testserver' + reverse('sshpublickey-detail', kwargs={'uuid': str(key.uuid)})

    @classmethod
    def get_list_url(self):
        return 'http://testserver' + reverse('sshpublickey-list')


class InstanceFactory(factory.DjangoModelFactory):
    class Meta(object):
        model = models.Instance

    hostname = factory.Sequence(lambda n: 'host%s' % n)
    template = factory.SubFactory(TemplateFactory)
    flavor = factory.SubFactory(FlavorFactory)
    start_time = factory.LazyAttribute(lambda o: timezone.now())
    external_ips = factory.LazyAttribute(lambda o: ','.join('.'.join(
        '%s' % randint(0, 255) for _ in range(4)) for _ in range(3)))
    internal_ips = factory.LazyAttribute(lambda o: ','.join(
        '10.%s' % '.'.join('%s' % randint(0, 255) for _ in range(3)) for _ in range(3)))
    ssh_public_key = factory.SubFactory(SshPublicKeyFactory)

    system_volume_id = factory.Sequence(lambda n: 'sys-vol-id-%s' % n)
    system_volume_size = factory.LazyAttribute(lambda o: o.flavor.disk)
    data_volume_id = factory.Sequence(lambda n: 'dat-vol-id-%s' % n)
    data_volume_size = 20

    @factory.lazy_attribute
    def project(self):
        project = structure_factories.ProjectFactory()
        CloudProjectMembershipFactory(project=project, cloud=self.flavor.cloud)
        return project

    @classmethod
    def get_url(self, instance=None, action=None):
        if instance is None:
            instance = InstanceFactory()
        url = 'http://testserver' + reverse('instance-detail', kwargs={'uuid': instance.uuid})
        return url if action is None else url + action + '/'

    @classmethod
    def get_list_url(self):
        return 'http://testserver' + reverse('instance-list')


class InstanceLicenseFactory(factory.DjangoModelFactory):
    class Meta(object):
        model = models.InstanceLicense

    instance = factory.SubFactory(InstanceFactory)
    template_license = factory.SubFactory(TemplateLicenseFactory)
    setup_fee = factory.fuzzy.FuzzyDecimal(10.0, 50.0, 3)
    monthly_fee = factory.fuzzy.FuzzyDecimal(0.5, 20.0, 3)


class PurchaseFactory(factory.DjangoModelFactory):
    class Meta(object):
        model = models.Purchase

    date = factory.LazyAttribute(lambda o: timezone.now())
    user = factory.SubFactory(structure_factories.UserFactory)
    project = factory.SubFactory(structure_factories.ProjectFactory)


class InstanceSecurityGroupFactory(factory.DjangoModelFactory):
    class Meta(object):
        model = models.InstanceSecurityGroup

    instance = factory.SubFactory(InstanceFactory)
    security_group = factory.SubFactory(SecurityGroupFactory)

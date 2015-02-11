from django.contrib.contenttypes import fields as ct_fields
from django.contrib.contenttypes import models as ct_models
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Sum

from nodeconductor.quotas import exceptions, managers
from nodeconductor.core.models import UuidMixin


class Quota(UuidMixin, models.Model):
    """
    Abstract quota for any resource
    """
    class Meta:
        unique_together = (('name', 'content_type', 'object_id'),)

    name = models.CharField(max_length=31)
    limit = models.FloatField(default=0)
    usage = models.FloatField(default=0)

    content_type = models.ForeignKey(ct_models.ContentType)
    object_id = models.PositiveIntegerField()
    owner = ct_fields.GenericForeignKey('content_type', 'object_id')

    objects = managers.QuotaManager()

    def is_exceeded(self, delta):
        return self.usage + delta > self.limit


class QuotaModelMixin(object):
    """
    Add general fields and methods to model for quotas usage
    """
    QUOTAS_NAMES = []  # this list has to be overridden

    def set_quota_limit(self, quota_name, limit):
        self.quotas.filter(name=quota_name).update(limit=limit)

    def set_quota_usage(self, quota_name, usage):
        self.quotas.filter(name=quota_name).update(usage=usage)

    def change_quota_usage(self, quota_name, usage_delta):
        """
        Add to usage_delta to current quota usage
        """
        quota = self.quotas.get(name=quota_name)
        quota.usage += usage_delta
        quota.save()

    def get_quota_errors(self, quota_deltas):
        """
        Get error messages about quotas that will be existed if quota_delta will be added to them

        quota_deltas - dictionary of quotas deltas, example:
        {
            'ram': 1024,
            'storage': 2048,
            ...
        }
        """
        errors = []
        for name, delta in quota_deltas.iteritems():
            quota = self.quotas.get(name=name)
            if quota.is_exceeded(delta):
                errors.append('%s quota limit: %s, requires %s (%s)\n' % (
                    quota.name, quota.limit, quota.usage + delta, quota.owner))
        # for parent in self.get_quota_parents():
        #     errors += parent.get_quota_errors(quota_deltas)
        return errors

    def get_quota_parents(self):
        """
        Return list of other quota owners that contain quotas of current owner.

        Example: Customer quotas contain quotas of all customers projects.
        """
        raise NotImplementedError('This method have to be defined for each quota owner separately')

    def can_user_update_quotas(self, user):
        """
        Return True if user has permission to update quota
        """
        raise NotImplementedError('This method have to be defined for each quota owner separately')

    @classmethod
    def get_sum_of_quotas_as_dict(cls, owners, quota_names=None, fields=['usage', 'limit']):
        """
        Return dictionary with sum of all owners quotas.

        Dictionary format:
        {
            'quota_name1': 'sum of limits for quotas with such quota_name1',
            'quota_name1_usage': 'sum of usages for quotas with such quota_name1',
            ...
        }
        All `owners` have to be instances of the same model.
        `fields` keyword argument defines sum of which fields of quotas will present in result.
        """
        if quota_names is None:
            quota_names = cls.QUOTAS_NAMES

        owner_models = set([owner._meta.model for owner in owners])
        if len(owner_models) > 1:
            raise exceptions.QuotaError('All owners have to be instances of the same model')

        annotate_kwars = dict((field, Sum(field)) for field in fields)
        filter_kwargs = {
            'content_type': ct_models.ContentType.objects.get_for_model(owners[0]),
            'object_id__in': [owner.id for owner in owners],
            'name__in': quota_names
        }

        quota_sums = Quota.objects.filter(**filter_kwargs).values('name').annotate(**annotate_kwars)

        result = {}
        if 'usage' in fields:
            for quota_sum in quota_sums:
                result[quota_sum['name'] + '_usage'] = quota_sum['usage']

        if 'limit' in fields:
            for quota_sum in quota_sums:
                result[quota_sum['name']] = quota_sum['limit']

        return result


# Mixin is better for quotas logic, but Django do not handle GenericRelation fields in Mixins
# Question on SO: http://stackoverflow.com/questions/28115239/django-genericrelation-in-model-mixin
class AbstractModelWithQuotas(QuotaModelMixin, models.Model):
    class Meta:
        abstract = True

    quotas = ct_fields.GenericRelation('quotas.Quota', related_query_name='quotas')

import pytz

from django.utils import timezone as django_timezone

from rest_framework import serializers

from nodeconductor.backup import models, utils
from nodeconductor.core.serializers import GenericRelatedField


class BackupScheduleSerializer(serializers.HyperlinkedModelSerializer):
    backup_source = GenericRelatedField(related_models=utils.get_backupable_models())
    timezone = serializers.ChoiceField(choices=[(t, t) for t in pytz.all_timezones],
                                       default=django_timezone.get_current_timezone_name)

    class Meta(object):
        model = models.BackupSchedule
        fields = ('url', 'description', 'backups', 'retention_time', 'timezone',
                  'backup_source', 'maximal_number_of_backups', 'schedule', 'is_active')
        read_only_fields = ('is_active', 'backups')
        extra_kwargs = {
            'url': {'lookup_field': 'uuid'},
            'backups': {'lookup_field': 'uuid'},
        }


class BackupSerializer(serializers.HyperlinkedModelSerializer):
    backup_source = GenericRelatedField(related_models=utils.get_backupable_models())
    state = serializers.ReadOnlyField(source='get_state_display')

    class Meta(object):
        model = models.Backup
        fields = ('url', 'description', 'created_at', 'kept_until', 'backup_source', 'state', 'backup_schedule')
        read_only_fields = ('created_at', 'kept_until', 'backup_schedule')
        extra_kwargs = {
            'url': {'lookup_field': 'uuid'},
            'backup_schedule': {'lookup_field': 'uuid'},
        }

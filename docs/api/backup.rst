Introduction
------------

NC supports backups in a generic way - if a model (like VM Instance, Project, Customer) implements a backup strategy,
it can be used as a source of backup data.

The backups can be created either manually or by setting a schedule for regular automatic backups.


Backup
------

To create a backup, issue

.. code-block:: http

    POST /api/backups/ HTTP/1.1
    Content-Type: application/json
    Accept: application/json
    Authorization: Token c84d653b9ec92c6cbac41c706593e66f567a7fa4
    Host: example.com

    {
        "backup_source": "http://example.com/api/instances/a04a26e46def4724a0841abcb81926ac/",
        "description": "a new manual backup"
    }

Example of a created backup representation:

.. code-block:: http

    GET /api/backups/7441df421d5443118af257da0f719533/ HTTP/1.1
    Content-Type: application/json
    Accept: application/json
    Authorization: Token c84d653b9ec92c6cbac41c706593e66f567a7fa4
    Host: example.com

    {
        "url": "http://example.com/api/backups/7441df421d5443118af257da0f719533/",
        "backup_source": "http://example.com/api/instances/a04a26e46def4724a0841abcb81926ac/",
        "description": "a new manual backup",
        "created_at": "2014-10-19T20:43:37.370Z",
        "kept_until": null,
        "state": "Backing up"
    }

Backup has a state, currently supported states are:

- Ready
- Backing up
- Restoring
- Deleting
- Erred
- Deleted

Backup schedules
----------------

To perform backups on a regular basis, it is possible to define a backup schedule. Example of a request:

.. code-block:: http

    POST /api/backup-schedules/ HTTP/1.1
    Content-Type: application/json
    Accept: application/json
    Authorization: Token c84d653b9ec92c6cbac41c706593e66f567a7fa4
    Host: example.com

    {
        "backup_source": "/api/instances/430abd492a384f9bbce5f6b999ac766c/",
        "description": "schedule description",
        "retention_time": 0,
        "maximal_number_of_backups": 10,
        "schedule": "1 1 1 1 1",
        "is_active": true
    }

For schedule to work, it should be activated - it's flag is_active set to true. If it's not, it won't be used
for triggering the next backups.

- **retention time** is a duration in days during which backup is preserved.
- **maximal_number_of_backups** is a maximal number of active backups connected to this schedule.
- **schedule** is a backup schedule defined in a cron format.
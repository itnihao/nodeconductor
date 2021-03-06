Quotas application
==================

Overview
--------

``quotas`` - django application, that provides implementation of per object resource limits and usages.


Base model with quotas
----------------------

Base model with quotas have to inherit ``QuotaModelMixin`` and define ``QUOTAS_NAMES`` attribute as list of all object
quotas names. Also ``add_quotas_to_scope`` handler has to be connected to object post save signal for quotas creation.

.. code-block:: python

    # in models.py

    class MyModel(QuotaModelMixin, models.Model):
        # ...
        QUOTAS_NAMES = ['quotaA', 'quotaB' ...]

    # in apps.py

    signals.post_save.connect(
            quotas_handlers.add_quotas_to_scope,
            sender=MyModel,
            dispatch_uid='nodeconductor.myapp.handlers.add_quotas_to_mymodel',
        )

Notice: quotas can be created only in ``add_quotas_to_scope`` handler. They can not be added anywhere else in the code.
This guarantee that objects of the same model will have same quotas.


Change object quotas usage and limit
------------------------------------

To edit objects quotas use:

 - ``set_quota_limit`` - replace old quota limit with new one
 - ``set_quota_usage`` - replace old quota usage with new one
 - ``add_quota_usage`` - add value to quota usage

Do not edit quotas manually, because this will break quotas in objects ancestors.


Parents for object with quotas
------------------------------

Object with quotas can have quota-parents. If usage in child was increased - it will be increased in parent too.
Method ``get_quota_parents`` have to be overridden to return list of quota-parents if object has any of them.
Only first level of ancestors has be added as parents, for example if membership is child of project and project
is child if customer - memberships ``get_quota_parents`` has to return only project, not customer.
It is not necessary for parents to have the same quotas as children, but logically they should have at least one
common quota.


Check is quota exceeded
-----------------------

To check is one separate quota exceeded - use ``is_exceeded`` method of quota.  It can receive usage delta or
threshold and check is quota exceeds considering delta and/or threshold.

To check is any of object or his ancestors quotas exceeded - use ``validate_quota_change`` method of object with quotas.
This method receive dictionary of quotas usage deltas and returns errors if one or more quotas of object or his
quota-ancestors exceeded.


Get sum of quotas
-----------------

``QuotasModelMixin`` provides ``get_sum_of_quotas_as_dict`` methods which calculates sum of each quotas for given
scopes.


Allow user to edit quotas
-------------------------

Will be implemented soon.


Add quotas to quota scope serializer
------------------------------------

``QuotaSerializer`` can be used as quotas serializer in quotas scope controller.


Sort objects by quotas with django_filters.FilterSet
----------------------------------------------------

Inherit your ``FilterSet`` from ``QuotaFilterMixin`` and follow next steps to enable ordering by quotas.

Usage:
    1. Add ``quotas__limit`` and ``-quotas__limit`` to filter meta ``order_by`` attribute if you want order by quotas
    limits and ``quotas__usage``, ``-quota__usage`` if you want to order by quota usage.

    2. Add ``quotas__<limit or usage>__<quota_name>`` to meta ``order_by`` attribute if you want to allow user
    to order ``<quota_name>``. For example ``quotas__limit__ram`` will enable ordering by ``ram`` quota.

Ordering can be done only by one quota at a time.


QuotaInline for admin models
----------------------------

``quotas.admin`` contains generic inline model``QuotaInline``, which can be used for as inline model for any quota
scope.

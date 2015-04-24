from __future__ import unicode_literals

import re
import random
import logging
import datetime

from jira import JIRA, JIRAError

from django.conf import settings
from django.utils import six


now = lambda: datetime.datetime.now() - datetime.timedelta(minutes=random.randint(0, 60))
logger = logging.getLogger(__name__)


class JiraClientError(Exception):
    pass


class JiraResource(object):
    """ Generic JIRA resource """

    def __init__(self, client):
        self.client = client


class JiraClient(object):
    """ NodeConductor interface to JIRA """

    class Issue(JiraResource):
        """ JIRA issues resource """

        class IssueQuerySet(object):
            """ Issues queryset acceptable by django paginator """

            def filter(self, term):
                if term:
                    escaped_term = re.sub(r'([\^~*?\\:\(\)\[\]\{\}|!#&"+-])', r'\\\\\1', term)
                    self.query_string = self.base_query_string + ' AND text ~ "%s"' % escaped_term
                return self

            def _fetch_items(self, offset=0, limit=1):
                # Default limit is 1 because this extra query required
                # only to determine the total number of items
                try:
                    self.items = self.query_func(
                        self.query_string,
                        fields=self.fields,
                        startAt=offset,
                        maxResults=limit)
                except JIRAError as e:
                    logger.exception(
                        'Failed to perform issues search with query "%s"', self.query_string)
                    six.reraise(JiraClientError, e)

            def __init__(self, jira, query_string, fields=None):
                self.fields = fields
                self.query_func = jira.search_issues
                self.query_string = self.base_query_string = query_string

            def __len__(self):
                if not hasattr(self, 'items'):
                    self._fetch_items()
                return self.items.total

            def __iter__(self):
                if not hasattr(self, 'items'):
                    self._fetch_items()
                return self.items

            def __getitem__(self, val):
                self._fetch_items(offset=val.start, limit=val.stop - val.start)
                return self.items

        def create(self, summary, description='', reporter=None, assignee=None):
            # Validate reporter & assignee before actual issue creation
            if reporter:
                reporter = self.client.users.get(reporter)
            if assignee:
                assignee = self.client.users.get(assignee)

            try:
                issue = self.client.jira.create_issue(
                    summary=summary,
                    description=description,
                    project={'key': self.client.core_project},
                    issuetype={'name': 'Task'})

                if reporter:
                    issue.update(reporter={'name': reporter.name})
                if assignee:
                    self.client.jira.assign_issue(issue, assignee.key)

            except JIRAError as e:
                logger.exception('Failed to create issue with summary "%s"', summary)
                six.reraise(JiraClientError, e)

            return issue

        def get_by_user(self, username, user_key):
            reporter = self.client.users.get(username)

            try:
                issue = self.client.jira.issue(user_key)
            except JIRAError:
                raise JiraClientError("Can't find issue %s" % user_key)

            if issue.fields.reporter.key != reporter.key:
                raise JiraClientError("Access denied to issue %s for user %s" % (user_key, username))

            return issue

        def list_by_user(self, username):
            query_string = "project = {} AND reporter = {}".format(
                self.client.core_project, username)

            return self.IssueQuerySet(self.client.jira, query_string)

    class Comment(JiraResource):
        """ JIRA issue comments resource """

        def list(self, issue_key):
            return self.client.jira.comments(issue_key)

        def create(self, issue_key, comment):
            return self.client.jira.add_comment(issue_key, comment)

    class User(JiraResource):
        """ JIRA users resource """

        def get(self, username):
            try:
                return self.client.jira.user(username)
            except JIRAError:
                raise JiraClientError("Unknown JIRA user %s" % username)

    def __init__(self, server=None, auth=None):
        self.core_project = None
        verify_ssl = True

        if not server:
            try:
                base_config = settings.NODECONDUCTOR['JIRA']
                server = base_config['server']
            except (KeyError, AttributeError):
                raise JiraClientError(
                    "Missed JIRA server. It must be supplied explicitly or defined "
                    "within settings.NODECONDUCTOR.JIRA")

            try:
                self.core_project = base_config['project']
            except KeyError:
                raise JiraClientError(
                    "Missed JIRA project key. Please define it as "
                    "settings.NODECONDUCTOR.JIRA['project']")

            if not auth:
                auth = base_config.get('auth')

            if 'verify' in base_config:
                verify_ssl = base_config['verify']

        if settings.NODECONDUCTOR.get('JIRA_DUMMY'):
            logger.warn(
                "Dummy client for JIRA is used, "
                "set JIRA_DUMMY to False to disable dummy client")
            self.jira = JiraDummyClient()
        else:
            self.jira = JIRA(
                {'server': server, 'verify': verify_ssl},
                basic_auth=auth, validate=False)

        self.users = self.User(self)
        self.issues = self.Issue(self)
        self.comments = self.Comment(self)


class JiraDummyClient(object):
    """ Dummy JIRA client """

    class DataSet(object):
        USERS = (
            {'key': 'alice', 'displayName': 'Alice', 'emailAddress': 'alice@example.com'},
            {'key': 'bob', 'displayName': 'Bob', 'emailAddress': 'bob@example.com'},
        )

        ISSUES = (
            {
                'key': 'TST-1',
                'fields': {'summary': 'Bake a cake', 'description': 'Angel food please'},
                'created': now(),
            },
            {
                'key': 'TST-2',
                'fields': {'summary': 'Pet a cat', 'assignee': 'bob'},
                'created': now(),
            },
            {
                'key': 'TST-3',
                'fields': {
                    'summary': 'Take a nap',
                    'comments': [
                        {'author': 'bob', 'body': 'Just a reminder -- this is a high priority task.', 'created': now()},
                        {'author': 'alice', 'body': 'sweet dreams ^_^', 'created': now()},
                    ],
                },
                'created': now(),
            },
        )

    class Resource(object):
        def __init__(self, client, **kwargs):
            self._client = client
            self.__dict__.update(kwargs)

        def __repr__(self):
            reprkeys = sorted(k for k in self.__dict__.keys())
            info = ", ".join("%s='%s'" % (k, getattr(self, k)) for k in reprkeys if not k.startswith('_'))
            return "<JIRA {}: {}>".format(self.__class__.__name__, info)

    class ResultSet(list):
        total = 0

        def __getslice__(self, start, stop):
            data = self.__class__(list.__getslice__(self, start, stop))
            data.total = len(self)
            return data

    class Issue(Resource):
        def update(self, reporter=()):
            self.fields.reporter = self._client.user(reporter['name'])

    class Comment(Resource):
        pass

    class User(Resource):
        pass

    def __init__(self):
        users = {data['key']: self.User(self, **data) for data in self.DataSet.USERS}
        self._current_user = users.get('alice')
        self._users = users.values()
        self._issues = []
        for data in self.DataSet.ISSUES:
            issue = self.Issue(self, **data)

            comments = []
            comments_data = data['fields'].get('comments', [])
            for data in comments_data:
                comment = self.Comment(self, **data)
                comment.author = users[data.get('author')]
                comments.append(comment)

            issue.fields = self.Resource(self, **issue.fields)
            issue.fields.comments = comments
            issue.fields.reporter = self._current_user
            if hasattr(issue.fields, 'assignee'):
                issue.fields.assignee = users.get(issue.fields.assignee)

            self._issues.append(issue)

    def current_user(self):
        return self.current_user.emailAddress

    def user(self, user_key):
        return self._current_user

    def issue(self, issue_key):
        for issue in self._issues:
            if issue.key == issue_key:
                return issue
        raise JIRAError("Issue %s not found" % issue_key)

    def assign_issue(self, issue, user_key):
        issue.assignee = self.user(user_key)

    def create_issue(self, **kwargs):
        issue = self.Issue(
            self,
            key='TST_{}'.format(len(self._issues) + 1),
            created=now(),
            fields=kwargs)

        self._issues.append(issue)
        return issue

    def search_issues(self, query, startAt=0, maxResults=50, **kwargs):
        term = None
        for param in query.split(' AND '):
            if param.startswith('text'):
                term = param.replace('text ~ ', '').strip('"')
        if term:
            results = []
            for issue in self._issues:
                if term in getattr(issue.fields, 'summary', '') + getattr(issue.fields, 'description', ''):
                    results.append(issue)
                    continue
                for comment in issue.fields.comments:
                    if term in comment.body:
                        results.append(issue)
                        break
        else:
            results = self._issues

        return self.ResultSet(results)[startAt:startAt + maxResults]

    def comments(self, issue_key):
        return self.issue(issue_key).fields.comments

    def add_comment(self, issue_key, body):
        comment = self.Comment(self, author=self._current_user, created=now, body=body)
        self.issue(issue_key).fields.comments.append(comment)
        return comment

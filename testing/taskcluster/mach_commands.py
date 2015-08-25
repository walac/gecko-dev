# -*- coding: utf-8 -*-

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from __future__ import absolute_import

import os
import json
import copy
import sys
import pystache

from mach.decorators import (
    CommandArgument,
    CommandProvider,
    Command,
)


ROOT = os.path.dirname(os.path.realpath(__file__))
GECKO = os.path.realpath(os.path.join(ROOT, '..', '..'))
DOCKER_ROOT = os.path.join(ROOT, '..', 'docker')
MOZHARNESS_CONFIG = os.path.join(GECKO, 'testing', 'mozharness', 'mozharness.json')

# XXX: If/when we have the taskcluster queue use construct url instead
ARTIFACT_URL = 'https://queue.taskcluster.net/v1/task/{}/artifacts/{}'
REGISTRY = open(os.path.join(DOCKER_ROOT, 'REGISTRY')).read().strip()

DEFINE_TASK = 'queue:define-task:aws-provisioner-v1/{}'

TREEHERDER_ROUTE_PREFIX = 'tc-treeherder-stage'
TREEHERDER_ROUTES = {
    'staging': 'tc-treeherder-stage',
    'production': 'tc-treeherder'
}

DEFAULT_TRY = 'try: -b do -p all -u all'
DEFAULT_JOB_PATH = os.path.join(
    ROOT, 'tasks', 'branches', 'base_jobs.yml'
)

def load_mozharness_info():
    with open(MOZHARNESS_CONFIG) as content:
        return json.load(content)

def docker_image(name):
    ''' Determine the docker tag/revision from an in tree docker file '''
    repository_path = os.path.join(DOCKER_ROOT, name, 'REGISTRY')
    repository = REGISTRY

    version = open(os.path.join(DOCKER_ROOT, name, 'VERSION')).read().strip()

    if os.path.isfile(repository_path):
        repository = open(repository_path).read().strip()

    return '{}/{}:{}'.format(repository, name, version)

def get_task(task_id):
    import urllib2
    return json.load(urllib2.urlopen("https://queue.taskcluster.net/v1/task/" + task_id))


def gaia_info():
    '''
    Fetch details from in tree gaia.json (which links this version of
    gecko->gaia) and construct the usual base/head/ref/rev pairing...
    '''
    gaia = json.load(open(os.path.join(GECKO, 'b2g', 'config', 'gaia.json')))

    if gaia['git'] is None or \
       gaia['git']['remote'] == '' or \
       gaia['git']['git_revision'] == '' or \
       gaia['git']['branch'] == '':

       # Just use the hg params...
       return {
         'gaia_base_repository': 'https://hg.mozilla.org/{}'.format(gaia['repo_path']),
         'gaia_head_repository': 'https://hg.mozilla.org/{}'.format(gaia['repo_path']),
         'gaia_ref': gaia['revision'],
         'gaia_rev': gaia['revision']
       }

    else:
        # Use git
        return {
            'gaia_base_repository': gaia['git']['remote'],
            'gaia_head_repository': gaia['git']['remote'],
            'gaia_rev': gaia['git']['git_revision'],
            'gaia_ref': gaia['git']['branch'],
        }

def decorate_task_treeherder_routes(task, suffix):
    """
    Decorate the given task with treeherder routes.

    Uses task.extra.treeherderEnv if available otherwise defaults to only
    staging.

    :param dict task: task definition.
    :param str suffix: The project/revision_hash portion of the route.
    """

    if 'extra' not in task:
        return

    if 'routes' not in task:
        task['routes'] = []

    treeheder_env = task['extra'].get('treeherderEnv', ['staging'])

    for env in treeheder_env:
        task['routes'].append('{}.{}'.format(TREEHERDER_ROUTES[env], suffix))

def decorate_task_json_routes(build, task, json_routes, parameters):
    """
    Decorate the given task with routes.json routes.

    :param dict task: task definition.
    :param json_routes: the list of routes to use from routes.json
    :param parameters: dictionary of parameters to use in route templates
    """
    fmt = parameters.copy()
    fmt.update({
        'build_product': task['extra']['build_product'],
        'build_name': build['build_name'],
        'build_type': build['build_type'],
    })
    routes = task.get('routes', [])
    for route in json_routes:
        routes.append(route.format(**fmt))

    task['routes'] = routes

def configure_dependent_task(task_path, parameters, taskid, templates, build_treeherder_config):
    """
    Configure a build dependent task. This is shared between post-build and test tasks.

    :param task_path: location to the task yaml
    :param parameters: parameters to load the template
    :param taskid: taskid of the dependent task
    :param templates: reference to the template builder
    :param build_treeherder_config: parent treeherder config
    :return: the configured task
    """
    task = templates.load(task_path, parameters)
    task['taskId'] = taskid

    if 'requires' not in task:
        task['requires'] = []

    task['requires'].append(parameters['build_slugid'])

    if 'treeherder' not in task['task']['extra']:
        task['task']['extra']['treeherder'] = {}

    # Copy over any treeherder configuration from the build so
    # tests show up under the same platform...
    treeherder_config = task['task']['extra']['treeherder']

    treeherder_config['collection'] = \
        build_treeherder_config.get('collection', {})

    treeherder_config['build'] = \
        build_treeherder_config.get('build', {})

    treeherder_config['machine'] = \
        build_treeherder_config.get('machine', {})

    if 'routes' not in task['task']:
        task['task']['routes'] = []

    if 'scopes' not in task['task']:
        task['task']['scopes'] = []

    return task


class TaskGraphManager(object):
    r"""Manage tasks."""

    def __init__(
        self,
        graph,
        templates,
        build_parameters,
        global_parameters,
        cmdline_params):
        r"""Initialize the object.

        :param build: the build configuration
        :param graph: the task graph
        :param templates: reference to the template builder
        :param build_parameters: parameters to load the template
        :param global_parameters: the global parameters dict specified in the branch config
        :param cmdline_params: command line parameters
        """
        from taskcluster_graph.slugid import slugid
        self.slugid = slugid

        self.graph = graph
        self.build_parameters = build_parameters
        self.global_parameters = global_parameters
        self.templates = templates
        self.cmdline_params = cmdline_params

        routes_file = os.path.join(ROOT, 'routes.json')
        with open(routes_file) as f:
            contents = json.load(f)
            self.json_routes = contents['routes']
            # TODO: Nightly and/or l10n routes

        self.treeherder_route = '{}.{}'.format(
            cmdline_params['project'],
            cmdline_params.get('revision_hash', ''))

    def configure(self, build):
        r"""Configure tasks dependency.

        :param build: the configuration for build task
        """
        import taskcluster_graph
        build_parameters = copy.copy(self.build_parameters)
        build_parameters["build_slugid"] = self.slugid()
        build_task = self.templates.load(build['task'], build_parameters)

        if self.cmdline_params['revision_hash']:
            decorate_task_treeherder_routes(build_task['task'],
                                            self.treeherder_route)
            decorate_task_json_routes(build,
                                      build_task['task'],
                                      self.json_routes,
                                      build_parameters)

        # Ensure each build graph is valid after construction.
        taskcluster_graph.build_task.validate(build_task)
        self.graph['tasks'].append(build_task)

        define_task = DEFINE_TASK.format(build_task['task']['workerType'])

        self.graph['scopes'].append(define_task)
        self.graph['scopes'].extend(build_task['task'].get('scopes', []))
        route_scopes = map(lambda route: 'queue:route:' + route, build_task['task'].get('routes', []))
        self.graph['scopes'].extend(route_scopes)

        # Treeherder symbol configuration for the graph required for each
        # build so tests know which platform they belong to.
        build_treeherder_config = build_task['task']['extra']['treeherder']

        if 'machine' not in build_treeherder_config:
            message = '({}), extra.treeherder.machine required for all builds'
            raise ValueError(message.format(build['task']))

        if 'build' not in build_treeherder_config:
            build_treeherder_config['build'] = \
                build_treeherder_config['machine']

        if 'collection' not in build_treeherder_config:
            build_treeherder_config['collection'] = { 'opt': True }

        if len(build_treeherder_config['collection'].keys()) != 1:
            message = '({}), extra.treeherder.collection must contain one type'
            raise ValueError(message.fomrat(build['task']))

        self.base_post_parameters = build_parameters
        self.base_post_parameters.update(self._dict2parameters(build_task, "root"))
        self.build_treeherder_config = build_treeherder_config

        post_tasks = build.get("post-tasks", {})
        self._post_tasks_walker(build_task, post_tasks)

    def _post_tasks_walker(self, parent_task, post_tasks):
        r"""Helper function to configure.

        :param parent_task: the parent of post_tasks
        :param post_tasks: the list of the dependent tasks
        """
        parameters = copy.copy(self.base_post_parameters)
        parameters.update(self._dict2parameters(parent_task, "parent"))

        for task_name, params in post_tasks.items():
            if params is None:
                params = {}

            post_parameters = copy.copy(parameters)
            post_parameters.update(self._render_parameters(
                params.get("parameters", {}), post_parameters))

            for p in params.get("inherit-parameters", []):
                post_parameters.update(self._render_parameters(
                    self.global_parameters[p], post_parameters))

            pre_task = self.templates.load(params["task"], {})
            extra = pre_task["task"]["extra"]

            if "chunks" in extra:
                total_chunks = extra["chunks"]["total"]
                if "total_chunks" not in post_parameters:
                    post_parameters["total_chunks"] = total_chunks

                for chunk in range(1, post_parameters["total_chunks"] + 1):
                    post_parameters["chunk"] = chunk
                    task = configure_dependent_task(
                            params["task"],
                            post_parameters,
                            self.slugid(),
                            self.templates,
                            self.build_treeherder_config)

                    if self.cmdline_params['revision_hash']:
                        decorate_task_treeherder_routes(
                                task, self.treeherder_route)

                    self.graph["tasks"].append(task)

                    define_task = DEFINE_TASK.format(task['task']['workerType'])

                    self.graph['scopes'].append(define_task)
                    self.graph['scopes'].extend(task.get('scopes', []))
            else:
                task = configure_dependent_task(
                        params["task"],
                        post_parameters,
                        self.slugid(),
                        self.templates,
                        self.build_treeherder_config)

                self.graph["tasks"].append(task)
                self.graph['scopes'].extend(task.get('scopes', []))

            self._post_tasks_walker(task, params.get("post-tasks", {}))

    @staticmethod
    def _render_parameters(parameters, meta):
        r"""Render text with alternate delimiters.

        :param parameters: the parameters whose value are are rendering
        :param meta: the meta parameters we are going to use in rendering
        """
        def render(text):
            return str(pystache.render(pystache.parse(
                    unicode(text), delimiters=("<%", "%>")), meta))
        return {key:render(value) for key, value in parameters.items()}

    @staticmethod
    def _dict2parameters(d, index=""):
        r"""Return a parameters form of a dictionary.

        :param d: the target dictionary.
        :param index: the root index namespace.

        >>> dict2parameters({})
        {}
        >>> dict2parameters({'a':'b'})
        {'a': 'b'}
        >>> dict2parameters({'a': {'b':'c'}})
        {'a.b': 'c'}
        >>> dict2parameters({'a': {'b':'c'}, 'd':'e'})
        {'d': 'e', 'a.b': 'c'}
        >>> dict2parameters({'a': {'b': {'c': 'd'}}})
        {'a.b.c': 'd'}
        >>> dict2parameters({'a': ['b', 'c']})
        {'a': ['b', 'c']}
        >>> dict2parameters({'a': ['b', 'c'], 'd': 'e'})
        {'a': ['b', 'c'], 'd': 'e'}
        """
        def closure(d_, index_):
            params = {}

            for key, value in d_.items():
                newkey = (index_ + "." if index_ else "") + str(key)
                if type(value) is dict:
                    params.update(closure(value, newkey))
                else:
                    params[newkey] = value

            return params
        return closure(d, index)

@CommandProvider
class DecisionTask(object):
    @Command('taskcluster-decision', category="ci",
        description="Build a decision task")
    @CommandArgument('--project',
        required=True,
        help='Treeherder project name')
    @CommandArgument('--url',
        required=True,
        help='Gecko repository to use as head repository.')
    @CommandArgument('--revision',
        required=True,
        help='Revision for this project')
    @CommandArgument('--revision-hash',
        help='Treeherder revision hash')
    @CommandArgument('--comment',
        required=True,
        help='Commit message for this revision')
    @CommandArgument('--owner',
        required=True,
        help='email address of who owns this graph')
    @CommandArgument('task', help="Path to decision task to run.")
    def run_task(self, **params):
        from taskcluster_graph.slugidjar import SlugidJar
        from taskcluster_graph.from_now import (
            json_time_from_now,
            current_json_time,
        )
        from taskcluster_graph.templates import Templates

        templates = Templates(ROOT)
        # Template parameters used when expanding the graph
        parameters = dict(gaia_info().items() + {
            'source': 'http://todo.com/soon',
            'project': params['project'],
            'comment': params['comment'],
            'url': params['url'],
            'revision': params['revision'],
            'revision_hash': params.get('revision_hash', ''),
            'owner': params['owner'],
            'as_slugid': SlugidJar(),
            'from_now': json_time_from_now,
            'now': current_json_time()
        }.items())
        task = templates.load(params['task'], parameters)
        print(json.dumps(task, indent=4))

@CommandProvider
class Graph(object):
    @Command('taskcluster-graph', category="ci",
        description="Create taskcluster task graph")
    @CommandArgument('--base-repository',
        default=os.environ.get('GECKO_BASE_REPOSITORY'),
        help='URL for "base" repository to clone')
    @CommandArgument('--head-repository',
        default=os.environ.get('GECKO_HEAD_REPOSITORY'),
        help='URL for "head" repository to fetch revision from')
    @CommandArgument('--head-ref',
        default=os.environ.get('GECKO_HEAD_REF'),
        help='Reference (this is same as rev usually for hg)')
    @CommandArgument('--head-rev',
        default=os.environ.get('GECKO_HEAD_REV'),
        help='Commit revision to use from head repository')
    @CommandArgument('--message',
        help='Commit message to be parsed. Example: "try: -b do -p all -u all"')
    @CommandArgument('--revision-hash',
            required=False,
            help='Treeherder revision hash to attach results to')
    @CommandArgument('--project',
        required=True,
        help='Project to use for creating task graph. Example: --project=try')
    @CommandArgument('--pushlog-id',
        dest='pushlog_id',
        required=False,
        default=0)
    @CommandArgument('--owner',
        required=True,
        help='email address of who owns this graph')
    @CommandArgument('--extend-graph',
        action="store_true", dest="ci", help='Omit create graph arguments')
    def create_graph(self, **params):
        from taskcluster_graph.commit_parser import parse_commit
        from taskcluster_graph.slugid import slugid
        from taskcluster_graph.from_now import (
            json_time_from_now,
            current_json_time,
        )
        from taskcluster_graph.templates import Templates
        import taskcluster_graph.build_task

        project = params['project']
        message = params.get('message', '') if project == 'try' else DEFAULT_TRY

        # Message would only be blank when not created from decision task
        if project == 'try' and not message:
            sys.stderr.write(
                    "Must supply commit message when creating try graph. " \
                    "Example: --message='try: -b do -p all -u all'"
            )
            sys.exit(1)

        templates = Templates(ROOT)
        job_path = os.path.join(ROOT, 'tasks', 'branches', project, 'job_flags.yml')
        job_path = job_path if os.path.exists(job_path) else DEFAULT_JOB_PATH

        jobs = templates.load(job_path, {})

        job_graph = parse_commit(message, jobs)
        mozharness = load_mozharness_info()

        # Template parameters used when expanding the graph
        parameters = dict(gaia_info().items() + {
            'index': 'index.garbage.staging.mshal-testing', #TODO
            'project': project,
            'pushlog_id': params.get('pushlog_id', 0),
            'docker_image': docker_image,
            'base_repository': params['base_repository'] or \
                params['head_repository'],
            'head_repository': params['head_repository'],
            'head_ref': params['head_ref'] or params['head_rev'],
            'head_rev': params['head_rev'],
            'owner': params['owner'],
            'from_now': json_time_from_now,
            'now': current_json_time(),
            'mozharness_repository': mozharness['repo'],
            'mozharness_rev': mozharness['revision'],
            'mozharness_ref':mozharness.get('reference', mozharness['revision']),
            'revision_hash': params['revision_hash']
        }.items())

        treeherder_route = '{}.{}'.format(
            params['project'],
            params.get('revision_hash', '')
        )

        routes_file = os.path.join(ROOT, 'routes.json')
        with open(routes_file) as f:
            contents = json.load(f)
            json_routes = contents['routes']
            # TODO: Nightly and/or l10n routes

        # Task graph we are generating for taskcluster...
        graph = {
            'tasks': [],
            'scopes': []
        }

        if params['revision_hash']:
            for env in TREEHERDER_ROUTES:
                graph['scopes'].append('queue:route:{}.{}'.format(TREEHERDER_ROUTES[env], treeherder_route))

        graph['metadata'] = {
            'source': 'http://todo.com/what/goes/here',
            'owner': params['owner'],
            # TODO: Add full mach commands to this example?
            'description': 'Task graph generated via ./mach taskcluster-graph',
            'name': 'task graph local'
        }

        task_manager = TaskGraphManager(graph,
                                        templates,
                                        parameters,
                                        jobs.get('parameters', {}),
                                        params)

        for build in job_graph:
            task_manager.configure(build)

        graph['scopes'] = list(set(graph['scopes']))

        # When we are extending the graph remove extra fields...
        if params['ci'] is True:
            graph.pop('scopes', None)
            graph.pop('metadata', None)

        print(json.dumps(graph, indent=4))

@CommandProvider
class CIBuild(object):
    @Command('taskcluster-build', category='ci',
        description="Create taskcluster try server build task")
    @CommandArgument('--base-repository',
        help='URL for "base" repository to clone')
    @CommandArgument('--head-repository',
        required=True,
        help='URL for "head" repository to fetch revision from')
    @CommandArgument('--head-ref',
        help='Reference (this is same as rev usually for hg)')
    @CommandArgument('--head-rev',
        required=True,
        help='Commit revision to use')
    @CommandArgument('--owner',
        default='foobar@mozilla.com',
        help='email address of who owns this graph')
    @CommandArgument('build_task',
        help='path to build task definition')
    def create_ci_build(self, **params):
        from taskcluster_graph.templates import Templates
        import taskcluster_graph.build_task

        templates = Templates(ROOT)
        # TODO handle git repos
        head_repository = params['head_repository']
        if not head_repository:
            head_repository = get_hg_url()

        head_rev = params['head_rev']
        if not head_rev:
            head_rev = get_latest_hg_revision(head_repository)

        head_ref = params['head_ref'] or head_rev

        from taskcluster_graph.from_now import (
            json_time_from_now,
            current_json_time,
        )
        build_parameters = dict(gaia_info().items() + {
            'docker_image': docker_image,
            'owner': params['owner'],
            'from_now': json_time_from_now,
            'now': current_json_time(),
            'base_repository': params['base_repository'] or head_repository,
            'head_repository': head_repository,
            'head_rev': head_rev,
            'head_ref': head_ref,
        }.items())

        try:
            build_task = templates.load(params['build_task'], build_parameters)
        except IOError:
            sys.stderr.write(
                "Could not load build task file.  Ensure path is a relative " \
                "path from testing/taskcluster"
            )
            sys.exit(1)

        taskcluster_graph.build_task.validate(build_task)

        print(json.dumps(build_task['task'], indent=4))

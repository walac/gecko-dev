# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""
S3 uploader creates a task that mozharness will use to upload artifacts to.
"""

from __future__ import absolute_import, print_function, unicode_literals

from taskgraph.transforms.base import TransformSequence


transforms = TransformSequence()


@transforms.add
def make_s3_uploader(config, tasks):
    for task in tasks:
        task['label'] = 's3-uploader'
        if config.params['project'] == 'try':
            task['worker-type'] = 'buildbot/buildbot-try'
        else:
            task['worker-type'] = 'buildbot/buildbot'

        task['worker'] = {
            'implementation': 'buildbot',
        }

        # clear out the stuff that's not part of a task description
        del task['build-label']
        del task['build-platform']
        del task['build-task']

        yield task


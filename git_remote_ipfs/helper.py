import os
import sys
import logging

import git_remote_ipfs.fastexport
from git_remote_ipfs.exc import *

LOG = logging.getLogger(__name__)


class Helper(object):
    def __init__(self, repo, fd=sys.stdin):
        self.fd = fd
        self.done = False
        self.repo = repo
        self.importing = False

    def lines(self):
        while not self.done:
            line = self.fd.readline()
            if not line:
                break

            line = line.rstrip()
            LOG.debug('line = %s', line)
            yield line

    def run(self):
        for line in self.lines():
            if not line:
                if self.importing:
                    print 'done'
                    sys.stdout.flush()
                    self.importing = False
                continue

            try:
                command, args = line.split(' ', 1)
            except ValueError:
                command, args = line, ''

            try:
                handler = getattr(self, 'do_%s' % command)
            except AttributeError:
                raise CommandNotImplemented(command)

            handler(command, args)
            sys.stdout.flush()

    def do_capabilities(self, command, args):
        print 'import'
        print 'export'
        print 'refspec refs/heads/*:%s/heads/*' % self.repo.prefix
        print 'refspec refs/tags/*:%s/tags/*' % self.repo.prefix
        print 'export-marks %s' % self.repo.markpath
        if os.path.isfile(self.repo.markpath):
            print 'import-marks %s' % self.repo.markpath
        print

    def do_list(self, command, args):
        for ref in self.repo.marks.refs:
            print '? %s' % ref
        print '@refs/heads/master HEAD'
        print

    def do_option(self, command, args):
        print 'unsupported'

    def do_export(self, command, args):
        for obj in git_remote_ipfs.fastexport.FastExportParser():
            if obj['kind'] == 'blob':
                self.repo.put_blob(obj)
            elif obj['kind'] == 'commit':
                self.repo.put_commit(obj)
            elif obj['kind'] == 'reset':
                self.repo.set_ref(obj)
            elif obj['kind'] == 'tag':
                self.repo.put_tag(obj)

            if 'ref' in obj['content']:
                print 'ok %s' % obj['content']['ref']

        print

        self.repo.commit()
        self.done = True

    def do_import(self, command, args):
        if not self.importing:
            print 'feature done'
            if os.path.exists(self.repo.markpath):
                print 'feature import-marks=%s' % self.repo.markpath
            print 'feature export-marks=%s' % self.repo.markpath
            print 'feature force'
            self.importing = True

        self.repo.export(args)

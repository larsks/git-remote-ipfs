import os
import sys
import logging

import fastimport.parser
import git_remote_ipfs.importer
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
                    LOG.debug('finishing imports')
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
        print '*export-marks %s' % self.repo.markpath
        if os.path.isfile(self.repo.markpath):
            print '*import-marks %s' % self.repo.markpath
        print

    def do_list(self, command, args):
        for ref in self.repo.marks.refs:
            print '? %s' % ref
        print '@refs/heads/master HEAD'
        print

    def do_option(self, command, args):
        print 'unsupported'

    def do_export(self, command, args):
        importer = git_remote_ipfs.importer.ImportProcessor(self.repo)
        parser = fastimport.parser.ImportParser(self.fd)
        importer.process(parser.iter_commands)
        self.done = True

    def do_import(self, command, args):
        if not self.importing:
            print 'feature done'
            print 'feature export-marks=%s' % self.repo.markpath
            if os.path.isfile(self.repo.markpath):
                print 'feature import-marks=%s' % self.repo.markpath
            print 'feature force'

        self.importing = True
        exporter = git_remote_ipfs.importer.ExportProcessor(self.repo)
        exporter.export(args)
        self.repo.commit()

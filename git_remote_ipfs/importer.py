import sys
import StringIO
import fastimport.parser
import fastimport.processor
import logging

from git_remote_ipfs.exc import *

LOG = logging.getLogger(__name__)


class ImportProcessor(fastimport.processor.ImportProcessor):
    def __init__(self, repo):
        self.repo = repo
        self.refs = set()
        super(ImportProcessor, self).__init__()

    def blob_handler(self, cmd):
        self.repo.add_blob(cmd)

    def commit_handler(self, cmd):
        self.repo.add_commit(cmd)
        self.refs.add(cmd.ref)

    def feature_handler(self, cmd):
        LOG.debug('ignoring feature %s', cmd)
        pass

    def reset_handler(self, cmd):
        self.repo.set_ref(cmd)
        self.refs.add(cmd.ref)

    def post_process(self):
        self.repo.export_complete()

        for ref in self.refs:
            LOG.debug('confirming %s', ref)
            print 'ok %s' % ref
        print


class ExportProcessor(object):
    def __init__(self, repo):
        self.repo = repo
        self.marks = repo.marks
        self.api = self.repo.api
        self.exported = set()

    def parse_str(self, str):
        str = str.encode('utf-8')
        buf = StringIO.StringIO(str)
        parser = fastimport.parser.ImportParser(buf)
        return parser.iter_commands().next()

    def export_files(self, commit):
        for fspec in commit.file_iter:
            if hasattr(fspec, 'dataref'):
                hash = fspec.dataref
                data = self.parse_str(self.api.cat(hash))
                mark = self.marks.add_rev(hash)
                fspec.dataref = mark
                data.mark = mark[1:]
                print data

    def resolve_parents(self, commit):
        if commit.from_:
            commit.from_ = self.marks.from_rev(commit.from_)

        merges = []
        for merge in commit.merges:
            merges.append(self.marks.from_rev(merge))

        commit.merges = merges

    def export_commit(self, ref, hash):
        LOG.debug('export_commit %s %s', ref, hash)
        if self.marks.is_marked(hash):
            return

        commit = self.parse_str(self.api.cat(hash))
        if commit.from_:
            self.export_commit(ref, commit.from_)

        self.export_files(commit)
        self.resolve_parents(commit)

        self.marks.set_ref(ref, hash)
        mark = self.marks.add_rev(hash)
        commit.mark = mark[1:]

        if not ref in self.exported:
            print 'reset %s' % self.repo.adjust_ref(ref)
            self.exported.add(ref)

        commit.ref = self.repo.adjust_ref(commit.ref)
        print commit

    def export(self, ref):
        self.repo.refresh()
        self.exported = set()

        if ref == 'HEAD':
            ref = self.repo.default_branch

        try:
            start = self.marks.get_ref(ref)
        except KeyError:
            raise UnknownReference(ref)

        LOG.debug('exporting %s from %s', ref, start)
        self.export_commit(ref, start)
        mark = self.marks.from_rev(self.marks.refs[ref])
        print 'reset %s' % self.repo.adjust_ref(ref)
        print 'from %s' % mark
        print

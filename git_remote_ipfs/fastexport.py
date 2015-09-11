import sys
import shlex
import logging

from git_remote_ipfs.exc import *

LOG = logging.getLogger(__name__)


class FastExportParser(object):
    def __init__(self, fd=sys.stdin):
        self.fd = fd
        self.done = False
        self.cur = None
        self.objs = []

    def lines(self):
        while not self.done:
            line = self.fd.readline()
            if not line:
                break

            line = line.rstrip()
            LOG.debug('line = %s', line)
            yield line

    def wrapper_iter(self):
        for line in self.lines():
            if not line:
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

            while self.objs:
                yield self.objs.pop(0)

        if self.cur:
            yield self.cur

    def __iter__(self):
        try:
            for obj in self.wrapper_iter():
                yield obj
        except:
            LOG.debug('failed with cur = %s', self.cur)
            raise

    def do_mark(self, command, args):
        self.cur['mark'] = args

    def do_data(self, command, args):
        self.cur['content']['data'] = self.fd.read(int(args))

    def do_blob(self, command, args):
        if self.cur:
            self.objs.append(self.cur)
        self.cur = {'kind': 'blob', 'content': {}}

    def do_reset(self, command, args):
        if self.cur:
            self.objs.append(self.cur)
        self.cur = {'kind': 'reset',
                    'content': {'ref': args}}

    def do_commit(self, command, args):
        if self.cur:
            self.objs.append(self.cur)
        self.cur = {'kind': 'commit',
                    'content': {
                        'ref': args,
                        'files': [],
                        'parents': [],
                    }}

    def do_author(self, command, args):
        self.cur['content']['author'] = args

    def do_committer(self, command, args):
        self.cur['content']['committer'] = args

    def do_from(self, command, args):
        self.cur['content']['parent'] = args

    def do_merge(self, command, args):
        self.cur['content']['parents'].append(args)

    def do_M(self, command, args):
        mode, markref, path = shlex.split(args)
        self.cur['content']['files'].append({
            'action': command,
            'mode': mode,
            'markref': markref,
            'path': path,
        })

    def do_C(self, command, args):
        srcpath, dstpath = shlex.split(args)
        self.cur['content']['files'].append({
            'action': command,
            'srcpath': srcpath,
            'dstpath': dstpath,
        })

    do_R = do_C

    def do_D(self, command, args):
        path = shlex.split(args)[0]
        self.cur['content']['files'].append({
            'action': command,
            'path': path,
        })

    def do_feature(self, command, args):
        if self.cur:
            self.objs.append(self.cur)
            self.cur = None
        if args != 'done':
            raise FeatureNotImplemented(args)

    def do_done(self, command, args):
        self.done = True

    def do_tag(self, command, args):
        if self.cur:
            self.objs.append(self.cur)
        self.cur = {'kind': 'tag', 'content': {}}

    def do_tagger(self, command, args):
        self.cur['content']['tagger'] = args

if __name__ == '__main__':
    import pprint
    logging.basicConfig(level='INFO')
    for obj in FastExportParser():
        pprint.pprint(obj)

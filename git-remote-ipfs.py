#!/usr/bin/env python

import pprint
import os
import sys
import argparse
import hashlib
import logging
import json

import ipfsApi

LOG = logging.getLogger('git-remote-ipfs')


class NotImplemented (Exception):
    pass


class HeadlessHorseman(Exception):
    pass


class FastExportReader(object):
    commands = (
        'blob',
        'commit',
        'done',
        'feature',
    )

    def __init__(self, fd=None):
        self.fd = fd if fd else sys.stdin
        self.done = False

    def readlines(self):
        while not self.done:
            line = self.fd.readline()
            LOG.debug('fastexport line = %s', line)
            if not line:
                break
            yield line.strip().split(None, 1)

    def __iter__(self):
        LOG.debug('starting fastexport')
        for line in self.readlines():
            if not line:
                continue

            command = line[0]
            if command not in self.commands:
                continue

            handler = getattr(self, 'do_%s' % command)
            obj = handler(*line)
            if obj is not None:
                yield(obj)

        LOG.debug('finished fastexport')

    def do_blob(self, command, *args):
        LOG.debug('handling blob')
        for line in self.readlines():
            if line[0] == 'mark':
                mark = line[1]
            elif line[0] == 'data':
                data = self.fd.read(int(line[1]))
                break

        return ('blob', mark, data)

    def do_commit(self, command, branch, *args):
        LOG.debug('handling commit')
        data = {'branch': branch, 'ops': []}
        for line in self.readlines():
            if not line:
                break
            elif line[0] == 'mark':
                mark = line[1]
            elif line[0] == 'data':
                data['message'] = self.fd.read(int(line[1]))
            elif line[0] == 'from':
                data['parent'] = line[1]
            elif line[0] == 'merge':
                data['merge'] = line[1]
            elif line[0] in ('author', 'committer'):
                data[line[0]] = line[1]
            elif line[0] == 'M':
                mode, dataref, path = line[1].split(' ', 3)
                data['ops'].append({'op': line[0],
                                    'dataref': dataref,
                                    'mode': mode,
                                    'path': path})
            elif line[0] == 'D':
                path = line[1]
                data['ops'].append({'op': line[0],
                                    'path': path})
            elif line[0] in ['R', 'C']:
                srcpath, dstpath = line[1].split(' ', 2)
                data['ops'].append({'op': line[0],
                                    'srcpath': srcpath,
                                    'dstpath': dstpath})
            else:
                raise NotImplemented(line[0])

        return ('commit', mark, data)

    def do_done(self, command, *args):
        LOG.debug('handling done')
        self.done = True

    def do_feature(self, command, feature, *args):
        LOG.debug('handling feature')
        if feature not in ['done']:
            raise NotImplemented('feature %s' % feature)


class CommandReader(object):
    def __init__(self, fd=None):
        if fd is None:
            fd = sys.stdin

        self.fd = fd

    def __iter__(self):
        while True:
            line = self.fd.readline()
            parts = line.split()
            yield (parts[0], parts[1:])

class IPFSRemote (object):
    def __init__(self, dir, alias, url,
                 ipfs_host=None,
                 ipfs_port=None):

        self.git_dir = dir
        self.alias = alias
        self.url = url
        self.temporary = False
        self.ipfs_host = ipfs_host
        self.ipfs_port = ipfs_port
        self.marks = {}
        self.refs = {}

        if self.alias == self.url:
            self.temporary = True
            self.alias = hashlib.sha1(self.alias).hexdigest()

        self.pvt_dir = os.path.join(self.git_dir, 'ipfs', self.alias)
        self.markpath = os.path.join(self.pvt_dir, 'marks-git')
        self.tocpath = os.path.join(self.pvt_dir, 'toc')

        self.init_dir()
        self.init_api()
        self.init_toc()

    def init_toc(self):
        if os.path.isfile(self.tocpath):
            with open(self.tocpath) as fd:
                toc = json.load(fd)

            self.marks = toc['marks']
            self.refs = toc['refs']

    def update_toc(self):
        with open(self.tocpath, 'w') as fd:
            json.dump({
                'marks': self.marks,
                'refs': self.refs
            }, fd, indent=2)

    def init_dir(self):
        if not os.path.isdir(self.pvt_dir):
            os.makedirs(self.pvt_dir)

    def init_api(self):
        self.api = ipfsApi.Client(host=self.ipfs_host,
                                  port=self.ipfs_port)

        # fail early if ipfs is not available
        self.id = self.api.id()
        LOG.debug('client id = %s', self.id['ID'])

    def loop(self):
        self.done = False

        for command, args in CommandReader():
            LOG.debug('command = %s', command)
            handler = getattr(self, 'do_%s' % command, None)
            if handler:
                handler(command, args)
                sys.stdout.flush()
            else:
                raise NotImplemented(command)

            if self.done:
                break

    def do_list(self, command, args):
        for ref in self.refs:
            LOG.debug('found ref = %s', ref)
            print '? %s' % ref

        print '@refs/heads/master HEAD'
        print

    def do_capabilities(self, command, args):
        print 'import'
        print 'export'
        print 'refspec refs/heads/*:refs/ipfs/%s/heads/*' % self.alias
        print 'refspec refs/tags/*:refs/ipfs/%s/tags/*' % self.alias
        if os.path.isfile(self.markpath):
            print '*import-marks %s' % self.markpath
        print '*export-marks %s' % self.markpath
        print 'option'
        print

    def do_option(self, command, args):
        print 'unsupported'

    def do_export(self, command, args):
        for kind, mark, data in FastExportReader():
            if kind == 'blob':
                hash = self.api.add_str(data)
                self.marks[mark] = hash
            elif kind == 'commit':
                if 'parent' in data:
                    data['parent'] = self.marks[data['parent']]
                for op in data['ops']:
                    if 'dataref' in op:
                        op['dataref'] = self.marks[op['dataref']]
                hash = self.api.add_json(data)
                self.marks[mark] = hash
                self.refs[data['branch']] = hash
                print 'ok %s' % data['branch']
        print

        self.update_toc()
        self.done = True


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--git-dir',
                   default=os.environ.get('GIT_DIR'))
    p.add_argument('alias')
    p.add_argument('url')
    p.set_defaults(loglevel=os.environ.get('GIT_REMOTE_IPFS_LOGLEVEL',
                                           'INFO'))
    return p.parse_args()


def main():
    global args

    args = parse_args()
    logging.basicConfig(level=args.loglevel)

    if not args.git_dir:
        LOG.error('GIT_DIR is not set')
        sys.exit(1)

    LOG.debug('alias = %s', args.alias)
    LOG.debug('url = %s', args.url)

    ipfs = IPFSRemote(args.git_dir, args.alias, args.url)
    ipfs.loop()

if __name__ == '__main__':
    main()


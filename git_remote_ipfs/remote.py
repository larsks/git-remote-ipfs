import sys
import os
import urlparse
import logging
import hashlib
import json

import ipfsApi

import git_remote_ipfs.marks
from git_remote_ipfs.exc import *

LOG = logging.getLogger(__name__)

repo_format_version = 1


def quote_filename(f):
    return '"%s"' % f.replace('"', '\\"')


class IPFSRemote (object):
    def __init__(self, git_dir, alias, url,
                 ipfs_gateway=None):
        self.git_dir = git_dir
        self.alias = alias
        self.url = url
        self.ipfs_gateway = ipfs_gateway
        self.temporary = False

        if self.alias == self.url:
            self.alias = hashlib.sha1(self.alias).hexdigest()
            self.temporary = True

        self.prefix = 'refs/ipfs/%s' % self.alias
        self.pvt_dir = os.path.join(git_dir, 'ipfs', self.alias)
        self.tocpath = os.path.join(self.pvt_dir, 'toc')
        self.markpath = os.path.join(self.pvt_dir, 'marks')
        self.repopath = os.path.join(self.pvt_dir, 'repo')
        self.marks = git_remote_ipfs.marks.Marks(self.tocpath)

        self.init_api()
        self.init_dir()
        self.init_refs()

    def __repr__(self):
        return '<repo %s at %s>' % (
            self.alias, self.url)

    __str__ = __repr__

    def init_api(self):
        if self.ipfs_gateway is not None:
            if ':' in self.ipfs_gateway:
                host, port = self.ipfs_gateway.split(':')
            else:
                host, port = self.ipfs_gateway, 5001

            port = int(port)
        else:
            host = None
            port = None

        self.api = ipfsApi.Client(host=host, port=port)

        # fail quickly if we're not able to contact ipfs
        self.id = self.api.id()

    def init_dir(self):
        if not os.path.isdir(self.pvt_dir):
            LOG.debug('creating directory %s', self.pvt_dir)
            os.makedirs(self.pvt_dir)

    def init_refs(self):
        # Do nothing if we were able to load refs from a
        # toc file earlier.
        if self.marks.refs:
            return

        # We have no refs! See if we can find some in ipfs.
        if self.url.startswith('ipfs://'):
            hash = self.get_repo_from_url()
        elif self.url.startswith('/ipfs'):
            hash = self.url
        elif self.url.startswith('/ipns'):
            hash = self.get_repo_from_ipns(self.url)
        else:
            hash = None

        if not hash:
            return

        LOG.debug('found repo ipfs hash = %s', hash)
        self.repo = self.api.get_json(hash)

        if self.repo.get('version') != repo_format_version:
            raise IPFSError('incompatible repository format')

        for ref, hash in self.repo['refs'].items():
            LOG.debug('found ref %s = %s', ref, hash)
            self.marks.set_ref(ref, hash)

    def update_repo(self):
        self.repo = self.api.add_json({
            'version': repo_format_version,
            'refs': self.marks.refs,
        })

        with open(self.repopath, 'w') as fd:
            fd.write(self.repo + '\n')

        LOG.info('ipfs repository hash = %s', self.repo)

    def get_repo_from_ipns(self, name):
        try:
            hash = self.api.name_resolve(name)['Path']
        except KeyError:
            raise IPFSError('failed to resolve name "%s"' % (
                            url.netloc))

        return hash

    def get_repo_from_url(self):
        LOG.info('reading refs from %s', self.url)
        url = urlparse.urlparse(self.url)

        # resolve via ipns
        if url.netloc:
            return self.get_repo_from_ipns(url.netloc)
        else:
            hash = url.path[1:]

        return hash

    def commit(self):
        self.marks.store()
        self.update_repo()

    def cleanup(self):
        if self.temporary:
            if os.path.isdir(self.pvt_dir):
                LOG.debug('removing directory %s', self.pvt_dir)
                os.removedirs(self.pvt_dir)

    def put_blob(self, obj):
        hash = self.api.add_str(obj['content']['data'])
        LOG.debug('added blob %s as %s', obj['mark'], hash)
        self.marks.add_mark(obj['mark'], hash)

    def set_ref(self, obj):
        mark = obj['content'].get('parent')
        if mark:
            hash = self.marks.from_mark(mark)
        else:
            hash = None
        self.marks.set_ref(obj['content']['ref'], hash)

    def resolve_markrefs(self, commit):
        for file in commit['files']:
            file['markref'] = self.marks.from_mark(file['markref'])

        parents = []
        for parent in commit['parents']:
            parents.append(self.marks.from_mark(parent))

        if 'parent' in commit:
            commit['parent'] = self.marks.from_mark(commit['parent'])

    def put_commit(self, obj):
        self.resolve_markrefs(obj['content'])
        hash = self.api.add_str(json.dumps(obj['content'], sort_keys=True))
        LOG.debug('added commit %s as %s', obj['mark'], hash)
        self.marks.add_mark(obj['mark'], hash)
        self.marks.set_ref(obj['content']['ref'], hash)

    def export_commit(self, ref, hash):
        if self.marks.is_marked(hash):
            return

        commit = self.api.get_json(hash)
        if 'parent' in commit:
            self.export_commit(ref, commit['parent'])

        for fspec in commit['files']:
            self.export_file(fspec)

        LOG.debug('exporting commit %s', hash)
        if ref not in self.exported:
            print 'reset %s' % ref
            self.exported.add(ref)

        print 'commit %s' % ref
        mark = self.marks.add_rev(hash)
        print 'mark :%d' % mark
        if 'author' in commit:
            print 'author %s' % commit['author']
        if 'committer' in commit:
            print 'committer %s' % commit['committer']
        print 'data %d' % len(commit['data'])
        print commit['data']
        if 'parent' in commit:
            print 'from :%d' % self.marks.from_rev(commit['parent'])
        for parent in commit['parents']:
            print 'merge %s' % parent
        for fspec in commit['files']:
            if fspec['action'] == 'M':
                print 'M %s :%d %s' % (
                    fspec['mode'],
                    self.marks.from_rev(fspec['markref']),
                    quote_filename(fspec['path']))
            elif fspec['action'] == 'D':
                print 'D %s' % (
                    quote_filename(fspec['path']))
            else:
                raise ValueError(fspec)
        print

        self.marks.set_ref(ref, hash)

    def export_file(self, fspec):
        hash = fspec['markref']
        LOG.debug('exporting file %s from %s', fspec['path'], hash)
        data = self.api.cat(hash)
        mark = self.marks.add_rev(hash)
        print 'blob'
        print 'mark :%d' % mark
        print 'data %d' % (len(data))
        print data

    def export(self, ref):
        self.exported = set()

        try:
            start = self.marks.get_ref(ref)
        except KeyError:
            raise UnknownReference(ref)

        LOG.debug('exporting %s from %s', ref, start)
        self.export_commit(ref, start)

        last_mark = self.marks.from_rev(self.marks.refs[ref])
        print 'reset %s' % ref
        print 'from :%d' % last_mark
        print

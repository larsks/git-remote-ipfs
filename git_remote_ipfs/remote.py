import sys
import os
import urlparse
import logging
import hashlib
import json

import ipfsApi
import fastimport.commands

import git_remote_ipfs.marks
from git_remote_ipfs.exc import *

LOG = logging.getLogger(__name__)

repo_format_version = 2


def quote_filename(f):
    return '"%s"' % f.replace('"', '\\"')


class IPFSRemote (object):
    default_branch = 'refs/heads/master'

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
        self.init_path()
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
            host = 'localhost'
            port = 5001

        self.api = ipfsApi.Client(host=host, port=port)

        # fail quickly if we're not able to contact ipfs
        self.id = self.api.id()
        LOG.debug('initialized ipfs api')

    def init_dir(self):
        if not os.path.isdir(self.pvt_dir):
            LOG.debug('creating directory %s', self.pvt_dir)
            os.makedirs(self.pvt_dir)

    def get_path_from_url(self):
        if not self.url:
            path = None
        elif self.url.startswith('ipfs://'):
            path = self.get_repo_from_url()
        elif self.url[:5] in ['/ipfs', '/ipns']:
            path = self.url
        else:
            raise InvalidURL(self.url)

        return path

    def init_path(self):
        self.path = self.get_path_from_url()
        if self.path:
            LOG.debug('found repo ipfs path = %s', self.path)

    def init_refs(self):
        # Do nothing if we were able to load refs from a
        # toc file earlier.
        if self.marks.refs:
            LOG.debug('found existing toc')
            return

        if not self.path:
            LOG.debug('unable to find repository path in ipfs')
            return

        self.refresh()

    def refresh(self):
        self.repo = self.api.cat(self.path)
        self.repo_check_version()
        self.repo_discover_refs()

    def repo_check_version(self):
        found_version = self.repo.get('version')
        if found_version != repo_format_version:
            raise IPFSError(
                'incompatible repository format (want %s, found %s)' % (
                    repo_format_version, found_version))

    def repo_discover_refs(self):
        for ref, hash in self.repo['refs'].items():
            LOG.debug('found ref %s = %s', ref, hash)
            self.marks.set_ref(ref, hash)

    def get_repo_from_url(self):
        url = urlparse.urlparse(self.url)

        # resolve via ipns
        if url.netloc:
            return '/ipns/%s' % url.netloc
        else:
            path = '/ipfs/%s' % url.path[1:]

        return path

    def update(self):
        LOG.debug('updating repository toc in ipfs')
        self.repo = self.api.add_json({
            'version': repo_format_version,
            'refs': self.marks.refs,
        })

        with open(self.repopath, 'w') as fd:
            fd.write(self.repo + '\n')

        LOG.warn('new repository hash = %s', self.repo)

        if self.path.startswith('/ipns/%s' % self.id['ID']):
            LOG.info('publishing new hash to %s', self.path)
            self.api.name_publish(self.repo)

    def commit(self):
        LOG.debug('committing repository to disk')
        self.marks.store()

    def export_complete(self):
        self.commit()
        self.update()

    def cleanup(self):
        if self.temporary:
            if os.path.isdir(self.pvt_dir):
                LOG.debug('removing directory %s', self.pvt_dir)
                os.removedirs(self.pvt_dir)

    def add_blob(self, obj):
        mark = obj.id
        obj.mark = None
        hash = self.api.add_str(str(obj))
        LOG.debug('added blob %s as %s', mark, hash)
        self.marks.add_mark(mark, hash)

    def set_ref(self, obj):
        mark = obj.from_
        if mark:
            hash = self.marks.from_mark(mark)
        else:
            hash = None
        self.marks.set_ref(obj.ref, hash)

    def resolve_marks(self, commit):
        for fspec in commit.file_iter:
            if hasattr(fspec, 'dataref'):
                fspec.dataref = self.marks.from_mark(fspec.dataref)

        merges = []
        for parent in commit.merges:
            parents.append(self.marks.from_mark(parent))

        commit.merges = merges

        if commit.from_:
            commit.from_ = self.marks.from_mark(commit.from_)

    def add_commit(self, obj):
        self.resolve_marks(obj)
        mark = obj.id
        obj.mark = None
        hash = self.api.add_str(str(obj) + '\n')
        LOG.debug('added commit %s as %s', mark, hash)
        self.marks.add_mark(mark, hash)
        self.marks.set_ref(obj.ref, hash)

    def adjust_ref(self, ref):
        if ref.startswith('refs/heads/'):
            return '%s/heads/%s' % (
                self.prefix,
                ref[len('refs/heads/'):])

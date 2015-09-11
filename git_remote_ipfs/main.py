#!/usr/bin/python

import atexit
import os
import sys
import argparse
import logging

import git_remote_ipfs.remote
import git_remote_ipfs.helper
from git_remote_ipfs.exc import *

LOG = logging.getLogger(__name__)


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--ipfs-gateway', '-g',
                   default=os.environ.get('GIT_IPFS_GATEWAY'))
    p.add_argument('--debug',
                   action='store_const',
                   const='DEBUG',
                   dest='loglevel')
    p.add_argument('--verbose',
                   action='store_const',
                   const='INFO',
                   dest='loglevel')
    p.add_argument('--git-dir', '-d',
                   default=os.environ.get('GIT_DIR'))
    p.add_argument('alias')
    p.add_argument('url')

    p.set_defaults(loglevel=os.environ.get('GIT_IPFS_LOGLEVEL', 'WARN'))
    return p.parse_args()


def main():
    args = parse_args()
    logging.basicConfig(level=args.loglevel)
    logging.getLogger('requests').setLevel('WARN')

    try:
        if args.git_dir is None:
            raise CLIError('GIT_DIR is undefined')

        repo = git_remote_ipfs.remote.IPFSRemote(
            args.git_dir, args.alias, args.url,
            ipfs_gateway=args.ipfs_gateway)
        helper = git_remote_ipfs.helper.Helper(repo=repo)

        atexit.register(repo.cleanup)
        helper.run()
    except IPFSError as err:
        LOG.error(err)
        sys.exit(1)

if __name__ == '__main__':
    main()

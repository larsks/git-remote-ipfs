#!/usr/bin/python

import os
import sys
import argparse
import hashlib


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('alias')
    p.add_argument('url')
    return p.parse_args()

def do_capabilities(alias, url):
    print 'import'
    print 'export'
    print 'refspec refs/heads/*:refs/ipfs/%s/heads/*' % alias
    print 'option'
    print

def main():
    args = parse_args()

    if args.alias == args.url:
        args.alias = hashlib.sha1(alias).hexdigest()

    for line in sys.stdin:
        parts = line.split()
        if parts[0] == 'capabilities':
            do_capabilities(args.alias, args.url)


if __name__ == '__main__':
    main()


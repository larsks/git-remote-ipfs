from setuptools import setup, find_packages

setup(name='git-remote-ipfs',
      author='Lars Kellogg-Stedman',
      author_email='lars@oddbit.com',
      url='https://github.com/larsks/git-remote-ipfs',
      version='0.1',
      packages=find_packages(),
      install_requires=[
          'ipfs-api',
      ],
      entry_points={
          'console_scripts':
          ['git-remote-ipfs = git_remote_ipfs.main:main'],
      })

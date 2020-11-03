#!/usr/bin/env python

import pathlib
from setuptools import setup, find_packages

with open('VERSION') as version_file:
    version = version_file.read()

with open('README.md') as readme_file:
    long_description = readme_file.read()

with open('requirements.txt') as requirements_file:
    install_requires = requirements_file.read().splitlines()

classifiers = [
    'Development Status :: 3 - Alpha',
    'Intended Audience :: System Administrators',
    'License :: OSI Approved :: Apache Software License',
    'Programming Language :: Python',
    'Programming Language :: Python :: 3',
    'Programming Language :: Python :: 3.0',
    'Programming Language :: Python :: 3.1',
    'Programming Language :: Python :: 3.2',
    'Programming Language :: Python :: 3.3',
    'Programming Language :: Python :: 3.4',
    'Programming Language :: Python :: 3.5',
    'Programming Language :: Python :: 3.6',
    'Programming Language :: Python :: 3.7',
    'Programming Language :: Python :: 3.8',
    'Topic :: System :: Clustering',
    'Topic :: System :: Networking',
    'Topic :: Utilities',
]

# The directory containing this file
HERE = pathlib.Path(__file__).parent

setup(
    name="sshecs",
    version=version,
    description="CLI tool to access ECS conntainers",
    long_description=long_description,
    url="https://github.com/antoiner77/ssh-ecs",
    author="Antoine Roy",
    author_email="antoine.roy77@gmail.com",
    license='GNU GENERAL PUBLIC LICENSE V3',
    packages=find_packages(exclude=('tests',)),
    include_package_data=True,
    install_requires=install_requires,
    classifiers=classifiers,
    dependency_links=[],
    entry_points={"console_scripts": ["sshecs=sshecs.client:main"]},
)

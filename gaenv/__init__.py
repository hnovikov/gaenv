#!/usr/bin/env python
'''
Utility to create python package symlinks for deployment in GAE. Before running this script, you must run pip install <requirements>.

Usage: gaenv [options]

Options:
    -r --requirements=FILE		Specify the requirements  [default: requirements.txt]
    -l --lib=DIR                        Change the the output dir [default: gaenv_lib]
    -n --no-import			Will not add import statement to appengine_config.py
'''
from distutils.sysconfig import get_python_lib
from docopt import docopt
import os
import inspect
import re
import pkg_resources
import sys
import ctypes

SYS_PATH_BUILD = """# Auto generated by gaenv
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))"""

def main():
    args = docopt(__doc__, version='gaenv 1.0')
    current_path = os.getcwd()
    requirement_path = get_requirements_path(current_path, args['--requirements'])
    pypi_requirements, cvs_requirements = compute_requirements(requirement_path)
    requirements = parse_requirements(pypi_requirements, cvs_requirements)

    links = compute_package_links(requirements)
    if links:
        libs_directory = create_libs_directory(current_path, args['--lib'])
        create_package_links(libs_directory, links)
        if not args['--no-import']:
            appengine_config_path = os.path.join(current_path, 'appengine_config.py')
            config_source = get_appengine_config(appengine_config_path)
            add_import(appengine_config_path, config_source, args['--lib'])

def get_requirements_path(current_path, requirements_file):
    requirement_path = os.path.join(current_path, requirements_file)
    if not os.path.exists(requirement_path):
        print 'requirements file %s not found' % requirement_path
        sys.exit(1)
    return requirement_path

def compute_requirements(requirement_path):
    pypi_requirements = []
    cvs_requirements = []
    with open(requirement_path, 'r') as requirements:
        for requirement in requirements:
            if requirement.startswith('-r') or requirement.startswith('--requirement'):
                extra_pypi_requirements, extra_cvs_requirements = compute_requirements(requirement.split(" ")[1].strip())
                pypi_requirements += extra_pypi_requirements
                cvs_requirements += extra_cvs_requirements
            elif requirement.startswith('--'):
                # Ignore other pip options
                continue
            elif requirement.find('+') == -1:
                pypi_requirements.append(requirement.strip())
            else:
                cvs_requirements.append(requirement.strip())
    return pypi_requirements, cvs_requirements

def parse_requirements(pypi_requirements, cvs_requirements):
    requirements = [req for req in pkg_resources.parse_requirements(os.linesep.join(pypi_requirements))]

    # todo temp fix until https://github.com/pypa/pip/issues/1083 issue is fixed
    if cvs_requirements:
        for requirement in cvs_requirements:
            egg = re.findall('egg=([^&]+)', requirement)
            if egg:
                try:
                    requirements.append(pkg_resources.get_distribution(egg.pop()))
                except pkg_resources.DistributionNotFound:
                    print 'Please install [%s]' % requirement
    # end repo temp fix
    return requirements

def compute_package_links(requirements):
    links = []
    for requirement in requirements:
        try:
            if isinstance(requirement, pkg_resources.Distribution):
                dist = requirement
            else:
                dist = pkg_resources.get_provider(requirement)
        except pkg_resources.DistributionNotFound:
            print 'Please install [%s]' % requirement
            continue
        except pkg_resources.VersionConflict:
            print 'Version don\'t match [%s] - create virtualenv or match the version' % requirement
            continue

        if dist.has_metadata('top_level.txt'):
            links.extend(dist.get_metadata_lines('top_level.txt'))

        if dist.has_metadata('dependency_links.txt'):
            links.extend(dist.get_metadata_lines('dependency_links.txt'))
    return links

def create_libs_directory(current_path, lib_directory):
    libs_directory = os.path.join(current_path, lib_directory)
    if not os.path.exists(libs_directory):
        os.makedirs(libs_directory)
    else:
        # delete contents
        for lib in os.listdir(libs_directory):
            os.unlink(os.path.join(libs_directory, lib))

    with open(os.path.join(libs_directory, '__init__.py'), 'w') as init_file:
        init_file.write(SYS_PATH_BUILD)
    return libs_directory

def create_package_links(libs, links):
    package_path = get_python_lib()
    for link in links:
        link = link.strip()
        symlink = os.path.join(package_path, link)
        if not os.path.exists(symlink) and os.path.exists(symlink + '.py'):
            symlink += '.py'
            dest = os.path.join(libs, link + '.py')
        else:
            dest = os.path.join(libs, link)

        if os.path.exists(symlink) and not os.path.exists(dest):
            create_symlink(symlink, dest)

        print 'Linked: {}'.format(link)

def get_appengine_config(config_path):
    if not os.path.exists(config_path):
        print 'Created {}'.format(config_path)
        source_code = ''
    else:
        print 'Updated {}'.format(config_path)
        source_code = read_file(config_path)
    return source_code

def add_import(appengine_config, config_source, libs):
    '''Adds import statement to libs module if it doesn't exist'''

    import_statement = 'import {}'.format(libs)
    if import_statement not in config_source:
        with open(appengine_config, 'w') as config:
            config.write(import_statement + '\n' + config_source)
            print 'Added [{}] in [{}]'.format(import_statement, appengine_config)
    else:
        print 'Skipped import on [{}] exists'.format(appengine_config)

def create_symlink(source, link_name):
    os_symlink = getattr(os, "symlink", None)
    if callable(os_symlink):
        os_symlink(source, link_name)
    else:
        csl = ctypes.windll.kernel32.CreateSymbolicLinkW
        csl.argtypes = (ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32)
        csl.restype = ctypes.c_ubyte
        flags = 1 if os.path.isdir(source) else 0
        if csl(link_name, source, flags) == 0:
            raise ctypes.WinError()

def read_file(filename):
    with open(filename, 'r') as input_file:
        return input_file.read()

if __name__ == "__main__":
    main()

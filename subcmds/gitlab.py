# Copyright (C) 2011 The Android Open Source Project
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os

import errno
import gitlab
import re
import time
import sys
import pprint
from urllib.parse import urlparse

_ROOT_GROUP = "scos"
#scos gitlab url
_GITLAB_URL = 'http://zhjsyf.ruijie.com.cn/gitlab'
#chunhuachen gitlab private token
_PRIVATE_TOKEN = 'ZsVaJXRGGi_cKVgDyaKu'
_PROTECTED_BRANCH = "master"

__XML_HEADER__="""<?xml version="1.0" encoding="UTF-8"?>
<!--
  author:chunhuachen
  repo gitlab to_manifest
-->
<manifest>
  <remote  name="rg"
           fetch="../.." />
  <default revision="master"
           remote="rg"
           sync-j="4" />
"""
__XML_HEADER_END__="""</manifest>"""

from command import Command, MirrorSafeCommand

class PathExistError(Exception):
  """A specified project is not suitable for the specified groups
  """

  def __init__(self, name=None):
    super().__init__(name)
    self.name = name

  def __str__(self):
    if self.name is None:
      return 'in current directory'
    return self.name


class Gitlab(Command, MirrorSafeCommand):
  COMMON = True
  helpSummary = "Create Empty projects of gitlab in manifests"
  helpUsage = """
%prog [-f] [<project>...]
%prog [-f] -r str1 [str2]...
"""
  helpDescription = """
List all projects; pass '.' to list the project for the cwd.

By default, only projects that currently exist in the checkout are shown.  If
you want to list all projects (using the specified filter settings), use the
--all option.  If you want to show all projects regardless of the manifest
groups, then also pass --groups all.

This is similar to running: repo forall -c 'echo "$REPO_PATH : $REPO_PROJECT"'.
"""

  def _Options(self, p):
    p.add_option('--create',
                 dest='create_projects',
                 action='store_true',
                 help='create project in gitlab group on the manifest')
    p.add_option('--tag', dest='gitlab_tag', #default=_PROTECTED_BRANCH,
                 help='Protected tags. create tags or delete tags. ')
    p.add_option('--branch', dest='gitlab_branch',
                 help='Protected branches. create branch. or delele branch. protected branch on the specified branch or wildcard expression.')
    g = p.add_option_group('Branch protect and merge_method options')
    g.add_option('--skip', action='store_true',
                 help='skip always exits branches or protected.')
    g.add_option('--unprotect', action='store_true',
                 help='Unprotect Branches. Keep stable branches unsecure and force developers to use merge requests.')
    g.add_option('--protect', action='store_true',
                 help='Protected Branches in gitlab group. Keep stable branches secure and force developers to use merge requests.')
    g.add_option('--merge-method',
                 dest='gitlab_merge_method',
                 action='store',# default='rebase_merge',
                 help='merge method (ff/merge/rebase_merge) set to project in gitlab on the manifest')
    g.add_option('--allowed-to-merge', dest='allowed_to_merge',
                 default=gitlab.const.MAINTAINER_ACCESS,
                 help='Protected Branches. allow to merge 40=Maintainer(default) or 30=Maintainer+Developers 0=No one. default:40')
    g.add_option('--allowed-to-push', dest='allowed_to_push',
                 default=gitlab.const.NO_ACCESS,
                 help='Protected Branches. Allowed to push: 40=Maintainer(default) or 30=Maintainer+Developers 0=No one. default:40')

    p.add_option('--mirror_push', action='store_true',
                 help='Mirror a repository from GitLab to another location. https://docs.gitlab.com/ee/user/project/repository/mirror/push.html')
    p.add_option('--to_manifest', action='store_true',
            help='to manifest in gitlab group to_manifest.')
    g = p.add_option_group('filter in manifest options')
    g.add_option('-r', '--regex',
                 dest='regex', action='store_true',
                 help='execute the gitlab command only on the project list based on regex or wildcard matching of strings')
    g.add_option(
            "-i",
            "--inverse-regex",
            dest="inverse_regex",
            action="store_true",
            help="execute the gitlab command only on projects not matching regex or "
            "wildcard expression",
        )
    g.add_option('-g', '--groups',
                 dest='groups',
                 help='filter the project list based on the groups the project is in')

    p.add_option('-n', '--dry-run', dest='dry_run',action='store_true',
                 help='Don\'t actually run any action; just print them.')
    g.add_option('-a', '--all',
                 action='store_true',
                 help='show projects regardless of checkout state')
    p.add_option('--relative-to', metavar='PATH',
                 help='display paths relative to this one (default: top of repo client checkout)')
    m = p.add_option_group('gitlab restrict options')
    m.add_option('--gitlab-groups',
                 dest='gitlab_groups',
                 action='store',
                 help='groups in gitlab group. all action in the group or subgroups. all:\"\",scos')
    m.add_option('--gitlab-url',
                 dest='gitlab_url',
                 action='store', default=_GITLAB_URL,
                 help="gitlab url. default: {0}".format(_GITLAB_URL))
    m.add_option('--private-token',
                 dest='private_token',
                 action='store',
                 help='gitlab private token')

  def ValidateOptions(self, opt, args):
    if opt.protect and opt.unprotect:
      self.OptionParser.error('cannot combine --protect and -unprotect')

    # Resolve any symlinks so the output is stable.
    if opt.relative_to:
      opt.relative_to = os.path.realpath(opt.relative_to)

  def _get_project_path(self, arg):
    _parsed_project_url = urlparse(arg.remote.url)
    if _parsed_project_url.path[0] == os.path.sep:
      project_path_with_namespace = _parsed_project_url.path[1:]
    else:
      project_path_with_namespace = _parsed_project_url.path
    return project_path_with_namespace

  def _unprotect_project(self, opt, gitlab_project):
    if opt.dry_run:
      print(gitlab_project.path_with_namespace)
    else:
      print(gitlab_project.path_with_namespace)
      try:
        p_branch = gitlab_project.protectedbranches.delete(opt.gitlab_branch)
      except Exception as e:
        if e.response_code == 404:
          print("not found protected branches:" + opt.gitlab_branch)
          return
        raise e

  def _branches(self, opt, gl, projects):
    def my_fork_project_callback(arg):
        self._create_project_branch(opt, project, gl.projects.get(arg.id))
    if opt.gitlab_groups:
      self._walkgroup(gl, opt, opt.gitlab_groups, project, my_fork_project_callback)
      return
    for project in projects:
      try:
        gitlab_project = gl.projects.get(self._get_project_path(project))
      except Exception as e:
        raise e

      self._create_project_branch(opt, project, gitlab_project)

  def _tags(self, opt, gl, projects):
    def my_tag_project_callback(arg):
        self._tag_project(opt, project, gl.projects.get(arg.id))
    if opt.gitlab_groups:
      self._walkgroup(gl, opt, opt.gitlab_groups, project, my_tag_project_callback)
      return
    for project in projects:
      try:
        gitlab_project = gl.projects.get(self._get_project_path(project))
      except Exception as e:
        raise e

      self._tag_project(opt, project, gitlab_project)

  def _unprotect(self, opt, gl, projects):
    def my_unprotect_project_callback(arg):
        self._unprotect_project(opt, gl.projects.get(arg.id))
    if opt.gitlab_groups:
      self._walkgroup(gl, opt, opt.gitlab_groups, my_unprotect_project_callback)
      return
    for project in projects:
      try:
        gitlab_project = gl.projects.get(self._get_project_path(project))
      except Exception as e:
        if e.response_code == 404:
          print("not found:" + self._get_project_path(project))
          continue
        raise e
      self._unprotect_project(opt, gitlab_project)

  def _protect_project(self, opt, gitlab_project):
    if opt.dry_run:
      print(gitlab_project.path_with_namespace)
    else:
      """
      0  => No access
      30 => Developer access
      40 => Maintainer access
      gitlab.const.DEVELOPER_ACCESS,
      gitlab.const.MAINTAINER_ACCESS,
      """
      print(gitlab_project.path_with_namespace)

      if opt.gitlab_merge_method:
        gitlab_project.merge_method = opt.gitlab_merge_method
        gitlab_project.save()
      try:
        p_branch = gitlab_project.protectedbranches.get(opt.gitlab_branch)
        done = p_branch.push_access_levels[0]['access_level'] == int(opt.allowed_to_push) and \
        p_branch.merge_access_levels[0]['access_level']  == int(opt.allowed_to_merge)
        if done:
          return
        else:
          p_branch = gitlab_project.protectedbranches.delete(opt.gitlab_branch)
      except gitlab.exceptions.GitlabGetError as e:
        if e.response_code == 404:
          pass
        else:
          raise e
      try:
        p_branch = gitlab_project.protectedbranches.create({
            'name': opt.gitlab_branch,
            'push_access_level': opt.allowed_to_push,
            'merge_access_level': opt.allowed_to_merge,
            })
      except gitlab.exceptions.GitlabCreateError as e:
        if e.response_code == 409:
          print(e.error_message)
        else:
          raise e

  def _create_project_branch(self, opt, project, gitlab_project):
    if opt.dry_run:
      print(gitlab_project.path_with_namespace)
    else:
      print(gitlab_project.path_with_namespace)

      try:
        p_branch = gitlab_project.branches.create({'branch': opt.gitlab_branch,
                                    'ref': project.revisionExpr})
      except gitlab.exceptions.GitlabCreateError as e:
        if e.response_code == 400:
          print(e.error_message)
        else:
          raise e

  def _tag_project(self, opt, project, gitlab_project):
    if opt.dry_run:
      print(gitlab_project.path_with_namespace)
    else:
      print(gitlab_project.path_with_namespace)

      try:
        p_tag = gitlab_project.tags.create({'tag_name': opt.gitlab_tag,
                                    'ref': project.revisionExpr})
      except gitlab.exceptions.GitlabCreateError as e:
        if e.response_code == 400:
          print(e.error_message)
        else:
          raise e

  def _walksubgroup(self, gl, opt, gp, callback):
    gp = gl.groups.get(gp.id)
    pjs = gp.projects.list(all=True, iterator=True)
    for p in pjs:
      callback(p)
    gps = gp.subgroups.list(all=True, iterator=True)
    for gp in gps:
      self._walksubgroup(gl, opt, gp, callback)

  def _getgroup(self, gl, opt, path):
    groups = path.split(os.sep)
    groups = [x for  x in groups if x]
    gp = gl.groups.get(groups[0])
    for g in groups[1:]:
      for x in gp.subgroups.list():
        gp = gl.groups.get(x.id)
        if gp.path == g:
          break
      if gp.path == g:
        continue
      else:
        return None
    if gp.path == groups[-1]:
      return gp

  def _walkgroup(self, gl, opt, groups, callback):
    if opt.gitlab_groups:
      groups = re.split(r'[,\s]+', groups)
      groups = [x for  x in groups if x]
      for group in groups:
        gp = self._getgroup(gl, opt, group)
        if not gp:
          return
        gps = gp.subgroups.list(all=True, iterator=True, with_shared=False)
        for subg in gps:
          self._walksubgroup(gl, opt, subg, callback)
        for p in gp.projects.list(all=True, iterator=True, with_shared=False):
          callback(p)
      return

  def _protect(self, opt, gl, projects):
    # Get a project by name with namespace
    def my_protect_project_callback(arg):
      self._protect_project(opt, gl.projects.get(arg.id))
    if opt.gitlab_groups:
      self._walkgroup(gl, opt, opt.gitlab_groups, my_protect_project_callback)
      return
    for project in projects:
      try:
        gitlab_project = gl.projects.get(self._get_project_path(project))
      except Exception as e:
        if e.response_code == 404:
          print("not found:" + self._get_project_path(project))
          continue
        raise e
      self._protect_project(opt, gitlab_project)

  def _create_project(self, opt, gl, projects):
    errlines = []
    rc = 0
    for project in projects:
      try:
        self.create_group_and_project(opt, gl, project)
      except KeyboardInterrupt as e:
        # Catch KeyboardInterrupt raised inside and outside of workers
        rc = rc or errno.EINTR
        print(e)
        raise e
      except PathExistError as e:
        errlines.append("%s : %s" % (_getpath(project), project.name))
      except Exception as ex:
        print(ex)
        raise ex
      #sys.exit(1)

    if errlines:
      print("err projects:")
      errlines.sort()
      print('\n'.join(errlines))

  def create_group_and_project(self, opt, gl, project):
    project_name_with_namespace = self._get_project_path(project)
    if opt.dry_run:
      print(project_name_with_namespace)
      return
    if not project_name_with_namespace.startswith(opt.gitlab_groups):
      print("skip:" + project.remote.url)
      return
    try:
      if gl.projects.get(id=project_name_with_namespace):
        print("exist:" + project_name_with_namespace)
      return
    except Exception as e:
      if e.response_code == 404:
        pass
      else:
        raise e

    if opt.dry_run:
      print(project_name_with_namespace)
      return

    print("name=" + project.name)
    print("project name with namespace=" + project_name_with_namespace)
    all_groups = gl.groups.get(id=opt.gitlab_groups)
    print("root group=" + str(all_groups.full_path))
    group_parent = None
    if all_groups.full_path == opt.gitlab_groups:
      group_parent = all_groups
    if not group_parent:
      print("not found scos")
      sys.exit(1)
    print("group parent=" + str(group_parent.full_name))

    print("name=" + str(project.remote.url))
    rootgrouplen = 0 
    if opt.gitlab_groups.endswith(os.path.sep):
      rootgrouplen = len(opt.gitlab_groups)
    else:
      rootgrouplen = len(opt.gitlab_groups) + 1
    will_create_path=project_name_with_namespace[rootgrouplen:]
    paths = will_create_path.split(os.path.sep)
    print("will_create_path=" + str(paths))

    last_path_index = len(paths) - 1

    group = group_parent
    for index in range(0, last_path_index):
      p = paths[index]
      print("sub path=" + p)
      #is the group exist
      print("parent group=" + group.name)
      try:
        all_groups = group.subgroups.list(all=True)
      except AttributeError as e:
        all_groups = []
        print("AttributeError: clear all subgroups")

      is_group_exist = False
      for g in all_groups:
        if g.name == p:
          is_group_exist = True
          group = g
          print("group exist=" + g.name)
          break
      if is_group_exist:
        continue
      # create gitlab_groups
      data = {
          "name": p,
          "path": p,
          "parent_id": group.id
      }

      try:
        group = gl.groups.create(data)
        print("group create success name=" + p)
        time.sleep(1)
      except gitlab.exceptions.GitlabCreateError as e:
        if e.response_code == 400:
          print("group:" + p + " has already been created")

          #query_groups = gl.groups.get(data)
          query_groups = gl.groups.list(id=group.id)
          print("query_groups:" + str(query_groups))
          for query_group in query_groups:
            if query_group.name == p and query_group.parent_id == group.id:
              group = query_group
              print("update exit group:" + group.name)
              break
        else:
            raise e

    project_base_name = paths[last_path_index]
    print("group project list group=" + group.name)
    real_group = gl.groups.get(group.id, lazy=True)
    all_projects = real_group.projects.list(all=True)
    print("group all projects=" + str(all_projects))
    is_project_exist = False
    for p in all_projects:
      if p.name == project_base_name:
        is_project_exist = True
        print("project exist=" + p.name)
        break
    if not is_project_exist:
      print("create project=" + project_base_name)
      try:
        gl.projects.create({'name': project_base_name, 'path': project_base_name,
            'namespace_id': group.id, 'merge_method': opt.gitlab_merge_method})
      except Exception as e:
        if e.response_code == 400:
          print("project:" + project_base_name + " has already been created")
          #raise PathExistError(e)
        else:
          raise e

      print("project create success name=" + project.name)
      time.sleep(1)

  def _mirror_push(self, opt, gl, projects):
    # Get a project by name with namespace
    for project in projects:
      try:
        gitlab_project = gl.projects.get(self._get_project_path(project))
      except Exception as e:
        if e.response_code == 404:
          print("not found:" + self._get_project_path(project))
          continue
        raise e
      if opt.dry_run:
        print(gitlab_project.path_with_namespace)
        print(os.path.join('http://root@zhjsyf1.ruijie.com.cn', gitlab_project.path_with_namespace))
      else:
        """
        0  => No access
        30 => Developer access
        40 => Maintainer access
        gitlab.const.DEVELOPER_ACCESS,
        gitlab.const.MAINTAINER_ACCESS,
        """
        print(gitlab_project.path_with_namespace)
        mirrors = None
        try:
          mirrors = gitlab_project.remote_mirrors.list()
        except Exception as e:
          if e.response_code == 404:
            pass
          else:
            raise e
        if mirrors:
          print("mirror exists")
          print(mirrors)
          for mirror in mirrors:
            mirror.enabled = True
            #mirror.only_protected_branches = True
            mirror.save()
        else:
          mirror_git_url = os.path.join('http://root:/XIpEIrMTGjM/HQbkNSHw+j0YsJsOOI62Lb9DXSNiFw=@zhjsyf1.ruijie.com.cn/gitlab', gitlab_project.path_with_namespace)
          #mirror_git_url = os.path.join('http://root:gitlab87654321@zhjsyf.ruijie.com.cn', gitlab_project.path_with_namespace)
          mirror_git_url += '.git'
          print(mirror_git_url)
          print(gitlab_project.remote_mirrors.__dict__)
          mirror = gitlab_project.remote_mirrors.create({'url': mirror_git_url,
                                                      'mirror': True})
          sys.exit(1)

  def _to_manifest(self, opt, gl):
    print(__XML_HEADER__)
    def my_xml_callback(arg):
      #pprint.pprint(arg._attrs)
      if arg.empty_repo:
        if opt.verbose:
          print("empty project:%s" % arg.path_with_namespace)
        return
      print('  <project name="{0}" />'.format(arg.path_with_namespace.removeprefix("scos/")))
    if opt.gitlab_groups == "":
      count=0
      while True:
        count = count + 1
        for p in gl.projects.list(pagination="keyset", per_page=5, page=count):
          if p.empty_repo:
            if opt.verbose:
              print("empty project:%s" % p.path_with_namespace)
            continue
          print('  <project name="{0}" />'.format(p.path_with_namespace.removeprefix("scos/")))
        #TODO debug
        #break
    else:
      self._walkgroup(gl, opt, opt.gitlab_groups, my_xml_callback)
    print(__XML_HEADER_END__)

  def Execute(self, opt, args):
    """List all projects and the associated directories.

    This may be possible to do with 'repo forall', but repo newbies have
    trouble figuring that out.  The idea here is that it should be more
    discoverable.

    Args:
      opt: The options.
      args: Positional args.  Can be a list of projects to list, or empty.
    """

    gl = None
    if opt.private_token:
      gl = gitlab.Gitlab(opt.gitlab_url, opt.private_token)
    else:
      gl = gitlab.Gitlab.from_config('git')
    gl.auth()
    if opt.verbose:
      gl.enable_debug()

    if opt.to_manifest:
      return self._to_manifest(opt, gl)

    projects=list()
    if opt.regex:
      projects = self.FindProjects(args, missing_ok=opt.all, all_manifests=not opt.this_manifest_only)
    elif opt.inverse_regex:
      projects = self.FindProjects(args, inverse=True, missing_ok=opt.all, all_manifests=not opt.this_manifest_only)
    else:
      projects = self.GetProjects(args, groups=opt.groups, missing_ok=opt.all,
                                    all_manifests=not opt.this_manifest_only)

    def _getpath(x):
      if opt.fullpath:
        return x.worktree
      if opt.relative_to:
        return os.path.relpath(x.worktree, opt.relative_to)
      return x.RelPath(local=opt.this_manifest_only)

    print(opt)
    if opt.create_projects:
      self._create_project(opt, gl, projects)
    elif opt.gitlab_branch:
      if opt.unprotect:
        self._unprotect(opt, gl, projects)
      elif opt.protect:
        self._protect(opt, gl, projects)
      else:
        self._branches(opt, gl, projects)
    elif opt.gitlab_tag:
      self._tags(opt, gl, projects)
    elif opt.mirror_push:
      self._mirror_push(opt, gl, projects)

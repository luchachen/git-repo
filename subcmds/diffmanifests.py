# Copyright (C) 2014 The Android Open Source Project
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

from color import Coloring
from command import PagedCommand
from manifest_xml import RepoClient
#ruijie add
import os
import sys
import gitlab
import pprint
from urllib.parse import *
from datetime import datetime
import json
import csv
_GITLAB_URL = 'http://zhjsyf.ruijie.com.cn/gitlab'
#ruijie



class _Coloring(Coloring):
    def __init__(self, config):
        Coloring.__init__(self, config, "status")


class Diffmanifests(PagedCommand):
    """A command to see logs in projects represented by manifests

    This is used to see deeper differences between manifests. Where a simple
    diff would only show a diff of sha1s for example, this command will display
    the logs of the project between both sha1s, allowing user to see diff at a
    deeper level.
    """

    COMMON = True
    helpSummary = "Manifest diff utility"
    helpUsage = """%prog manifest1.xml [manifest2.xml] [options]"""

    helpDescription = """
The %prog command shows differences between project revisions of manifest1 and
manifest2. if manifest2 is not specified, current manifest.xml will be used
instead. Both absolute and relative paths may be used for manifests. Relative
paths start from project's ".repo/manifests" folder.

The --raw option Displays the diff in a way that facilitates parsing, the
project pattern will be <status> <path> <revision from> [<revision to>] and the
commit pattern will be <status> <onelined log> with status values respectively :

  A = Added project
  R = Removed project
  C = Changed project
  U = Project with unreachable revision(s) (revision(s) not found)

for project, and

   A = Added commit
   R = Removed commit

for a commit.

Only changed projects may contain commits, and commit status always starts with
a space, and are part of last printed project.
Unreachable revisions may occur if project is not up to date or if repo has not
been initialized with all the groups, in which case some projects won't be
synced and their revisions won't be found.

"""

    def _Options(self, p):
        p.add_option(
            "--gitlab", dest="gitlab", action="store_true", help="display diff base on gitlab api"
        )

        m = p.add_option_group('gitlab restrict options')
        m.add_option(
            "-o",
            "--output-file",
            dest="output_file",
            default="-",
            help="file to save the manifest to. (Filename prefix for "
            "multi-tree.)",
            metavar="-|NAME.xml",
        )
        m.add_option('--gitlab-url',
                     dest='gitlab_url',
                     action='store', default=_GITLAB_URL,
                     help="gitlab url. default: {0}".format(_GITLAB_URL))
        m.add_option('--private-token',
                     dest='private_token',
                     action='store',
                     help='gitlab private token')
        p.add_option(
            "--raw", dest="raw", action="store_true", help="display raw diff"
        )
        p.add_option(
            "--no-color",
            dest="color",
            action="store_false",
            default=True,
            help="does not display the diff in color",
        )
        p.add_option(
            "--pretty-format",
            dest="pretty_format",
            action="store",
            metavar="<FORMAT>",
            help="print the log using a custom git pretty format string. csv or feishu_msg.json for gitlab",
        )

    def _printRawDiff(self, diff, pretty_format=None, local=False):
        _RelPath = lambda p: p.RelPath(local=local)
        for project in diff["added"]:
            self.printText(
                "A %s %s" % (_RelPath(project), project.revisionExpr)
            )
            self.out.nl()

        for project in diff["removed"]:
            self.printText(
                "R %s %s" % (_RelPath(project), project.revisionExpr)
            )
            self.out.nl()

        for project, otherProject in diff["changed"]:
            self.printText(
                "C %s %s %s"
                % (
                    _RelPath(project),
                    project.revisionExpr,
                    otherProject.revisionExpr,
                )
            )
            self.out.nl()
            self._printLogs(
                project,
                otherProject,
                raw=True,
                color=False,
                pretty_format=pretty_format,
            )

        for project, otherProject in diff["unreachable"]:
            self.printText(
                "U %s %s %s"
                % (
                    _RelPath(project),
                    project.revisionExpr,
                    otherProject.revisionExpr,
                )
            )
            self.out.nl()

    def _printDiff(self, diff, color=True, pretty_format=None, local=False):
        _RelPath = lambda p: p.RelPath(local=local)
        if diff["added"]:
            self.out.nl()
            self.printText("added projects : \n")
            self.out.nl()
            for project in diff["added"]:
                self.printProject("\t%s" % (_RelPath(project)))
                self.printText(" at revision ")
                self.printRevision(project.revisionExpr)
                self.out.nl()

        if diff["removed"]:
            self.out.nl()
            self.printText("removed projects : \n")
            self.out.nl()
            for project in diff["removed"]:
                self.printProject("\t%s" % (_RelPath(project)))
                self.printText(" at revision ")
                self.printRevision(project.revisionExpr)
                self.out.nl()

        if diff["missing"]:
            self.out.nl()
            self.printText("missing projects : \n")
            self.out.nl()
            for project in diff["missing"]:
                self.printProject("\t%s" % (_RelPath(project)))
                self.printText(" at revision ")
                self.printRevision(project.revisionExpr)
                self.out.nl()

        if diff["changed"]:
            self.out.nl()
            self.printText("changed projects : \n")
            self.out.nl()
            for project, otherProject in diff["changed"]:
                self.printProject("\t%s" % (_RelPath(project)))
                self.printText(" changed from ")
                self.printRevision(project.revisionExpr)
                self.printText(" to ")
                self.printRevision(otherProject.revisionExpr)
                self.out.nl()
                self._printLogs(
                    project,
                    otherProject,
                    raw=False,
                    color=color,
                    pretty_format=pretty_format,
                )
                self.out.nl()

        if diff["unreachable"]:
            self.out.nl()
            self.printText("projects with unreachable revisions : \n")
            self.out.nl()
            for project, otherProject in diff["unreachable"]:
                self.printProject("\t%s " % (_RelPath(project)))
                self.printRevision(project.revisionExpr)
                self.printText(" or ")
                self.printRevision(otherProject.revisionExpr)
                self.printText(" not found")
                self.out.nl()

    def _printDiff_gitlab(self, diff, color=True, pretty_format=None, local=False):
        _RelPath = lambda p: p.RelPath(local=local)
        if diff["added"]:
            self.out.nl()
            self.printText("added projects : \n")
            self.out.nl()
            for project in diff["added"]:
                self.printProject("\t%s" % (_RelPath(project)))
                self.printText(" at revision ")
                self.printRevision(project.revisionExpr)
                self.out.nl()

        if diff["removed"]:
            self.out.nl()
            self.printText("removed projects : \n")
            self.out.nl()
            for project in diff["removed"]:
                self.printProject("\t%s" % (_RelPath(project)))
                self.printText(" at revision ")
                self.printRevision(project.revisionExpr)
                self.out.nl()

        if diff["missing"]:
            self.out.nl()
            self.printText("missing projects : \n")
            self.out.nl()
            for project in diff["missing"]:
                self.printProject("\t%s" % (_RelPath(project)))
                self.printText(" at revision ")
                self.printRevision(project.revisionExpr)
                self.out.nl()

        if diff["changed"]:
            self.out.nl()
            self.printText("changed projects : \n")
            self.out.nl()
            commits= list()
            for project, otherProject in diff["changed"]:
                _ci  = self.getAddedAndRemovedLogs_gitlab(
                    project,
                    otherProject,
                    oneline=(pretty_format is None),
                    color=color,
                    pretty_format=pretty_format,
                )
                commits.extend(_ci)

            sorted_commmits = sorted(commits, key=lambda commit: datetime.strptime(commit['created_at'], "%Y-%m-%dT%H:%M:%S.%f%z"))
            self._printLogs_gitlab(
                sorted_commmits,
                raw=False,
                color=color,
                pretty_format=pretty_format,
            )
            self.out.nl()

        if diff["unreachable"]:
            self.out.nl()
            self.printText("projects with unreachable revisions : \n")
            self.out.nl()
            for project, otherProject in diff["unreachable"]:
                self.printProject("\t%s " % (_RelPath(project)))
                self.printRevision(project.revisionExpr)
                self.printText(" or ")
                self.printRevision(otherProject.revisionExpr)
                self.printText(" not found")
                self.out.nl()

    def _get_project_path(self, arg):
      _parsed_project_url = urlparse(arg.remote.url)
      if _parsed_project_url.path[0] == os.path.sep:
          project_path_with_namespace = _parsed_project_url.path[1:]
      else:
          project_path_with_namespace = _parsed_project_url.path
      return project_path_with_namespace

    def getAddedAndRemovedLogs_gitlab(
        self, fromProject, toProject, oneline=False, color=True, pretty_format=None
    ):
        """Get the list of logs from this revision to given revisionId"""
        all_refs = {}
        try:
            gitlab_project = self.gl.projects.get(self._get_project_path(fromProject))
        except Exception as e:
            raise e
        for tag in gitlab_project.tags.list():
            #pprint.pprint(tag.__dict__)
            all_refs["refs/tags/%s" % tag.name] =  tag.commit['id']
        for br in gitlab_project.branches.list():
            #pprint.pprint(tag.__dict__)
            all_refs["refs/heads/%s" % br.name] =  br.commit['id']
        to_all_refs = {}
        try:
            to_gitlab_project = self.gl.projects.get(self._get_project_path(toProject))
        except Exception as e:
            raise e
        for tag in to_gitlab_project.tags.list():
            #pprint.pprint(tag.__dict__)
            to_all_refs["refs/tags/%s" % tag.name] =  tag.commit['id']
        for br in to_gitlab_project.branches.list():
            #pprint.pprint(tag.__dict__)
            to_all_refs["refs/heads/%s" % br.name] =  br.commit['id']
        selfId = fromProject.GetRevisionId(all_refs, gitlab_api=True)
        toId = toProject.GetRevisionId(to_all_refs, gitlab_api=True)
        try:
            added = gitlab_project.repository_compare(selfId+'^0', toId+'^0')
        except gitlab.exceptions.GitlabGetError as e:
            print(f"{fromProject.name} vs {toProject.name}")
            pprint.pprint(all_refs)
            print(selfId + ' vs ' + toId)
            raise e
        try:
            removed = gitlab_project.repository_compare(toId, selfId)
        except gitlab.exceptions.GitlabGetError as e:
            print(f"from: {toProject.name} vs {fromProject.name}")
            pprint.pprint(to_all_refs)
            print(toId + ' vs ' + selfId)
            raise e

        commits = list()
        if pretty_format == 'csv':
            if not added['diffs'] and not removed['diffs']:
                return list()
            author_emails = set()

            web_url  = urlparse(to_gitlab_project.web_url)
            compare_url = web_url._replace(path = os.path.sep.join([web_url.path, '-', 'compare', f"{selfId}...{toId}"]))
            commit = dict()
            if added['diffs']:
                commit = added['commit']
                for ci in added['commits']:
                    author_emails.add(ci['author_email'])
            if removed['diffs']:
                commit = removed['commit']
                for ci in removed['commits']:
                    author_emails.add(ci['author_email'])
            for email in author_emails:
                author = email.split('@')[0]
                commits.append({'author_email': email, 'web_url': urlunparse(compare_url), 'created_at': commit['created_at'], 'author_name': f"@{author}"})
        else:
            for ci in added['commits']:
                ci['added'] = True
                commits.append(ci)

            for ci in removed['commits']:
                ci['added'] = False
                commits.append(ci)
        return commits

    def _printLogs_gitlab(
        self, logs, raw=False, color=True, pretty_format=None,
    ):
        json_logs = []
        output_dir= os.path.dirname(pretty_format) if pretty_format else ''
        __COMMITS_CSV=os.path.join(output_dir, 'commits.csv')
        csvfile = open(__COMMITS_CSV, 'w')
        __THRESHOLD=32
        count=0
        for ci in logs:
            log = None
            csv_log = None
            if pretty_format == 'csv':
                __fieldnames=['project_name', 'created_at', 'web_url', 'author_email', 'author_name' ]
                csvwriter = csv.DictWriter(csvfile, fieldnames=__fieldnames)
                csvwriter.writeheader()

                datetime_obj =  datetime.strptime(ci['created_at'], "%Y-%m-%dT%H:%M:%S.%f%z")
                formatted_datetime = datetime_obj.strftime("%Y-%m-%d %H:%M:%S ")

                weburl = urlparse(ci['web_url'])
                ci['project_name'] = weburl.path.split(os.path.sep)[-4]
                sorted_dict = {k: ci[k] for k in __fieldnames}
                sorted_dict['created_at'] = formatted_datetime
                csvwriter.writerow(sorted_dict)
            elif pretty_format:
                __fieldnames=['added', 'short_id', 'project_name', 'created_at', 'author_email', 'title', 'committed_date', 'web_url', 'id']
                csvwriter = csv.DictWriter(csvfile, fieldnames=__fieldnames)
                csvwriter.writeheader()
                datetime_obj =  datetime.strptime(ci['created_at'], "%Y-%m-%dT%H:%M:%S.%f%z")
                formatted_datetime = datetime_obj.strftime("%Y-%m-%d %H:%M:%S ")
                #fix project_name
                weburl = urlparse(ci['web_url'])
                ci['project_name'] = weburl.path.split(os.path.sep)[-4]
                sorted_dict = {k: ci[k] for k in __fieldnames}
                sorted_dict['added'] = '[+]' if ci['added'] else '[-]'
                sorted_dict['created_at'] = formatted_datetime
                csvwriter.writerow(sorted_dict)

                log = [{'tag':'text', 'text': '[+]'}] if ci['added'] else [{'tag':'text', 'text': '[-]'}]
                log.append({'tag': 'a', 'text': ci['short_id'], 'href': ci['web_url']})
                log.append({'tag': 'text', 'text': ci['project_name']})
                log.append({"tag" : "at", "user_id" : ci['author_email']})
                log.append({'tag': 'text', 'text': formatted_datetime})
                log.append({'tag': 'text', 'text': ci['title'] + '\n'})
                count+=1
                if count  < __THRESHOLD:
                    json_logs.extend(log)
            else:
                datetime_obj =  datetime.strptime(ci['created_at'], "%Y-%m-%dT%H:%M:%S.%f%z")
                formatted_datetime = datetime_obj.strftime("%Y-%m-%d %H:%M:%S ")
                log = '['+ci['short_id']+'](' + ci['web_url'] + ')' + ':' + formatted_datetime  + ' ' \
                + ci['committer_name'] + ':' + ci['title']
                log.strip()
                if raw:
                    self.printText((" R " if ci['added']  else " A ") + log)
                    self.out.nl()
                else:
                    if ci['added']:
                        self.printAdded("\t\t[+] ")
                    else:
                        self.printRemoved("\t\t[-] ")
                    self.printText(log)
                    self.out.nl()

        csvfile.close()
        print(csvfile.name)
        if pretty_format == 'csv':
            return
        if len(json_logs) != 0:
            data = None
            with open(pretty_format) as file:
                # Load the JSON data
                #"content" : {
                data = json.load(file)
            feishu_json_file=os.path.join(output_dir, 'feishu_'+os.path.basename(pretty_format))
            with open(feishu_json_file, 'w') as file:
                csv_url = ''
                for k in data['content']['post']['zh_cn']['content'][0]:
                    value = k.get('text')
                    if value and value == 'browser':
                        href = urlparse(k['href'])
                        href_path = []
                        for comp in href.path.split(os.path.sep):
                            if comp == 'browse':
                                href_path.append('file')
                            else:
                                href_path.append(comp)
                        href_path.append(os.path.basename(__COMMITS_CSV))
                        href = href._replace(path = os.path.sep.join(href_path))
                        csv_url = urlunparse(href)
                        break

                morenotice = []
                if len(logs) >= __THRESHOLD:
                    short_ids = [ci['short_id'] for ci in logs[__THRESHOLD:__THRESHOLD+3]]
                    morenotice = [{'tag': 'a', 'text': ','.join(short_ids) + ',...'}]
                morenotice.append({'tag': 'a', 'text': 'There are a total of ' + str(len(logs)) + '. FYI.', 'href': csv_url})
                json_logs.extend(morenotice)

                data['content']['post']['zh_cn']['content'][0].extend(json_logs)
                json_string = json.dumps(data)
                # Write the JSON string to the file
                file.write(json_string)
            self.printText(feishu_json_file)
            self.out.nl()


    def _printLogs(
        self, project, otherProject, raw=False, color=True, pretty_format=None
    ):
        logs = project.getAddedAndRemovedLogs(
            otherProject,
            oneline=(pretty_format is None),
            color=color,
            pretty_format=pretty_format,
        )
        if logs["removed"]:
            removedLogs = logs["removed"].split("\n")
            for log in removedLogs:
                if log.strip():
                    if raw:
                        self.printText(" R " + log)
                        self.out.nl()
                    else:
                        self.printRemoved("\t\t[-] ")
                        self.printText(log)
                        self.out.nl()

        if logs["added"]:
            addedLogs = logs["added"].split("\n")
            for log in addedLogs:
                if log.strip():
                    if raw:
                        self.printText(" A " + log)
                        self.out.nl()
                    else:
                        self.printAdded("\t\t[+] ")
                        self.printText(log)
                        self.out.nl()

    def ValidateOptions(self, opt, args):
        if not args or len(args) > 2:
            self.OptionParser.error("missing manifests to diff")
        if opt.this_manifest_only is False:
            raise self.OptionParser.error(
                "`diffmanifest` only supports the current tree"
            )

    def Execute(self, opt, args):
        self.out = _Coloring(self.client.globalConfig)
        self.printText = self.out.nofmt_printer("text")
        if opt.color:
            self.printProject = self.out.nofmt_printer("project", attr="bold")
            self.printAdded = self.out.nofmt_printer(
                "green", fg="green", attr="bold"
            )
            self.printRemoved = self.out.nofmt_printer(
                "red", fg="red", attr="bold"
            )
            self.printRevision = self.out.nofmt_printer("revision", fg="yellow")
        else:
            self.printProject = (
                self.printAdded
            ) = self.printRemoved = self.printRevision = self.printText

        manifest1 = RepoClient(self.repodir)
        manifest1.Override(args[0], load_local_manifests=False)
        if len(args) == 1:
            manifest2 = self.manifest
        else:
            manifest2 = RepoClient(self.repodir)
            manifest2.Override(args[1], load_local_manifests=False)

        diff = manifest1.projectsDiff(manifest2, opt.gitlab)
        if opt.raw:
            self._printRawDiff(
                diff,
                pretty_format=opt.pretty_format,
                local=opt.this_manifest_only,
            )
        if opt.gitlab:
            if opt.private_token:
                self.gl = gitlab.Gitlab(opt.gitlab_url, opt.private_token)
            else:
                self.gl = gitlab.Gitlab.from_config('git')
            self.gl.auth()
            if opt.verbose:
                self.gl.enable_debug()
            self._printDiff_gitlab(
                diff,
                color=opt.color,
                pretty_format=opt.pretty_format,
                local=opt.this_manifest_only,
            )
        else:
            self._printDiff(
                diff,
                color=opt.color,
                pretty_format=opt.pretty_format,
                local=opt.this_manifest_only,
            )

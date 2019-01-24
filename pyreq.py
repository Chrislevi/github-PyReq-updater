#!/usr/bin/python
import os
import yaml
import subprocess
from github import GithubException
from github import Github
import argparse
import base64
import re
import json
import datetime
import tempfile

parser = argparse.ArgumentParser()
parser.add_argument('--token', help='Please provide a valid GH Access Token')
parser.add_argument('--repo', help='Target Repo (e.g example/project)')
parser.add_argument('--branch', help='Master Branch (default: master)')
parser.add_argument('-p', '--purge', action='store_true', help='Delete current PyReq PullBranches')
args = parser.parse_args()


if args.repo:
    r = args.repo.split("/")[1]
    o = args.repo.split("/")[0]
elif os.environ.get('GH_REPO'):
    r = os.environ['GH_REPO'].split("/")[1]
    o = os.environ['GH_REPO'].split("/")[0]
else:
    raise ValueError("Must provide a target repo, ENV_VAR('GH_REPO') or ARG('--repo')")

if args.token:
    t = args.token
elif os.environ.get('GH_TOKEN'):
    t = os.environ['GH_TOKEN']
else:
    raise ValueError("Must provide a Github Token, either ENV_VAR('GH_TOKEN') or ARG('--token')")

if args.branch:
    b = args.branch
elif os.environ.get('GH_BRANCH'):
    b = os.environ['GH_BRANCH']
else:
    raise ValueError("Must provide master branch, either ENV_VAR('GH_BRANCH') or ARG('--branch')")


p = False
if args.purge:
    p = args.purge
elif os.environ.get('GH_PURGE'):
    p = os.environ['GH_PURGE']


# Connect to GitHub Repo
gh = Github(t)
org = gh.get_organization(o)
repo = org.get_repo(r)

cfg = yaml.load(base64.b64decode(repo.get_file_contents('/.pyup.yml', ref=b).content).decode())
master = repo.get_branch(cfg['master'])
ci_trig = cfg['ci_phrase']
merge_branch = cfg['merge_branch']
pr_list = []
mb_pb = None
venv = "~/pyreq-venv"
proccesed_prs = 0
now = datetime.datetime.now()

labels = [
    {
        "name": "PyReq-REVERT",
        "color": "a50310"
    },
    {
        "name": "PyReq",
        "color": "65daf2"
    }
]


class PullBranch(object):
    def __init__(self, branch, pr=None):
        self.branch = branch
        self.pr = pr
        self.reqs = []
        self.pkg = None
        self.version = None
        self.old_version = None
        self.files = None
        self.last_comment = None
        self.desc = None
        self.ci = None
        self.current_meta = []
        self.is_merge_branch = merge_branch in self.branch.name

        if self.pr:
            self.pop_meta()
        else:
            self.match_pull()

        if merge_branch in self.branch.name and self.pr:
            self.mb_last_comment()
            self.current_meta = json.loads(self.pr.body)
            self.add_label(labels[1]['name'])

    # Merge branch's state is determined through its last comment as a state.
    def mb_last_comment(self):
        if self.pr.comments != 0:
            self.last_comment = self.pr.get_issue_comments().get_page(-1)[-1]
            return self.last_comment

    # Populate class after initiation
    def pop_meta(self):
        self.pkg = self.pr.title.split(' ')[1]
        self.version = self.pr.title.split(' ')[3]
        self.old_version = re.search(r'\-([\d.]+)', self.branch.name).group(1)
        self.files = self.pr.get_files()
        self.get_reqs()
        self.desc = "{}:{}:{}:{}:{}".format(self.pkg,
                                            self.old_version,
                                            self.version,
                                            json.dumps(self.reqs),
                                            self.branch.name)

    def get_content(self, file):
        return base64.b64decode(repo.get_file_contents(file, ref='heads/' + self.branch.name).content).decode()

    def delete(self):
        try:
            if self.pr:
                print("Deleting PR:     {}".format(self.pr.title))
                self.pr.edit(state="closed")
            print("Deleting Branch: {}".format(self.branch.name))
            repo.get_git_ref(ref='heads/' + self.branch.name).delete()

        except GithubException as e:
            print(e.data['message'])

    # Trigger PB's CI
    def trigger_ci(self):
        self.pr.create_issue_comment(ci_trig)
        print("{}: CI triggered".format(self.pr.title))

    # PB's list of all *CHANGED* req files
    def get_reqs(self):
        for file in self.files:
            if 'global-reqs.txt' in file.filename:
                self.reqs.append(file.filename)

    # Matches branches with their PR's.
    def match_pull(self):
        match = None

        # Update branch last commit sha
        self.branch = repo.get_branch(self.branch.name)
        if self.is_merge_branch:
            try:
                for pull in repo.get_pulls(head=merge_branch, base=master.name):
                    is_pyreq = any(labels[1]["name"] in lbl.name for lbl in pull.labels)
                    if is_pyreq and merge_branch in pull.title:
                        self.pr = pull
                        break

            except GithubException as e:
                if e.status == 404:
                    pass

            except IndexError as e:
                if "out of range" in str(e):
                    pass

        else:
            for pull in repo.get_pulls(base=merge_branch):
                is_pyreq = any(labels[1]["name"] in lbl.name for lbl in pull.labels)
                if self.branch.commit.sha in pull.head.sha and is_pyreq:
                    match = pull
                    break

                elif pull.title.split(' ')[1] in self.branch.name and is_pyreq and pull.title.split(' ')[3] in self.branch.name:

                    # TODO FIXME GitHub pull request bug, temp commit in order to update PR COMMITS
                    sha = repo.get_file_contents("README.md", ref='heads/' + self.branch.name).sha
                    repo.update_file("/README.md",
                                     "Fix Microsoft-Github pull bug",
                                     "TEMP CHANGE",
                                     sha,
                                     branch=self.branch.name)

                    self.branch = repo.get_branch(self.branch.name)
                    self.branch.commit.create_status('success')
                    self.match_pull()
                    # raise Exception("Branch PR: {} not found".format(self.branch.name))

            if match:
                self.pr = match
                self.pop_meta()

            else:
                print("{}: No match found".format(self.branch.name))

    def add_label(self, label):
        self.pr.add_to_labels(label)


def create_labels():
    for label in labels:
        try:
            repo.create_label(label["name"], label["color"])

        except GithubException as e:
            if e.status == 422:
                pass


# Creates new branch, params: source branch name, target branch name
def create_branch(src_branch, target_branch):
    sb = repo.get_branch(src_branch)
    try:
        repo.create_git_ref(ref='refs/heads/' + target_branch, sha=sb.commit.sha)

    except GithubException as e:
        if e.status == 422:
            print("Already exists {}".format(target_branch))
            return repo.get_branch(target_branch)
    else:
        print("{}: Branch created.".format(target_branch))
        return repo.get_branch(target_branch)


# Validates and creates Final_Merge_branch which aggregates all package updates.
def create_merge_branch():
    # Check if merge_branch exists. (branch + PullRequest)
    global mb_pb
    try:
        b = repo.get_branch(merge_branch)

    except GithubException as e:
        if e.status == 404:
            b = create_branch(master.name, merge_branch)
            mb_pb = PullBranch(branch=b)
    else:
        # print("Final merge branch already exists")
        mb_pb = PullBranch(branch=b)

    if mb_pb.branch.commit.sha != master.commit.sha:
        try:
            p = repo.create_pull(merge_branch, "STAB", master.name, merge_branch, True)

        except GithubException as e:
            if e.status == 422:
                # print("merge branch PR already exists")
                pass

        else:
            mb_pb.pr = p
            mb_pb.add_label(labels[1]['name'])


# PyUp bot - creates/deletes branch/PR's according to package updates on the internet.
def run_pyup():
    create_merge_branch()
    bashcmd = 'pyup --repo={} --user-token={} --branch {}'.format(repo.full_name, t, merge_branch)
    subprocess.check_output(bashcmd, shell=True)


# Parses global-reqs into a pip freeze list
# TODO FIXME Run with pip-compile, URL packages unsupported https://github.com/jazzband/pip-tools/issues/272
def run_venv(pb, global_file):
    # Set PATH Defaults
    os.environ.setdefault('PATH', '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin')
    # tmpdir = tempfile.mkdtemp()
    tmp_req = '/tmp/req.txt'
    no_internal = '/tmp/reqs-no-internal.txt'

    # Command sequence
    bashcmd = [
        "rm -rf {} || /bin/true".format(venv),
        "virtualenv -p python3 {}".format(venv),
        "grep -ivE '{}|^#' {} | tee {}".format(r, tmp_req, no_internal),
        "{}/bin/pip3 install --prefer-binary -r {}".format(venv, no_internal),
        "{}/bin/pip3 freeze".format(venv)
    ]

    if not os.path.exists(tmp_req):
        os.mknod(tmp_req)

    cur_req = pb.get_content(global_file)
    with open(tmp_req, 'w+') as req:
        req.write(cur_req)

    for cmd in bashcmd[:-1]:
        subprocess.call(cmd, shell=True)#, stdout=subprocess.DEVNULL)
    freeze = subprocess.check_output(bashcmd[-1], shell=True).decode()

    # if os.path.dirname(global_file) == "":
    #     print("Updating Main reqs")
    #     external_packages = re.findall(r'(git\+\S*\.git)', cur_req)
    #     for ext_pkg in external_packages:
    #         pkg_name = str(ext_pkg.split('/')[4]).split('.')[0]
    #         freeze = re.sub(pkg_name + r'(==([\d.]+))', ext_pkg, freeze)

    try:
        internal_packages = subprocess.check_output("cat {} | grep -i {}".format(tmp_req, r),
                                                    shell=True).decode()

    except subprocess.CalledProcessError as e:
        if e.returncode == 1:
            pass

    else:
        freeze += internal_packages

    return freeze


# Updates lower-reqs using `run_venv`
def update_lower_deps(pb, branch, req):
    try:
        lower_reqs = repo.get_file_contents(os.path.dirname(req) + "/requirements.txt", ref=branch)
        new_content = run_venv(pb, req)
        repo.update_file("/" + lower_reqs.path,
                         "lower-reqs updated -> {}:{}".format(pb.pkg, pb.version),
                         new_content,
                         lower_reqs.sha,
                         branch=branch)

    except GithubException as e:
        print("Could not update file: {} \nError: {}".format(pb.branch.name, lower_reqs.path, e.data['message']))


# Populates all Open PyReq PR/Branch into a list
def create_pb_list():
    global pr_list
    for b in repo.get_branches():
        if 'PyReq/update' in b.name:
            pb = PullBranch(branch=b)
            pr_list.append(pb)

    for pr in pr_list:
        if not pr.pr:
            print(pr.branch.name + "NO PR!?!")


# Check single package CI's
def check_pb_ci_status():
    check_mb_ci_status()
    ci_running = False
    global proccesed_prs
    for pb in pr_list:
        ci_state = pb.pr.get_commits().get_page(0)[-1].get_combined_status()
        is_failed = 'failure' in ci_state.state
        is_pending = 'pending' in ci_state.state
        is_success = 'success' in ci_state.state

        try:
            comments = pb.pr.get_issue_comments()

        except Exception:
            raise Exception("Failed to find PR for {} branch".format(pb.branch.name))

        if is_failed:
            print("CI Failed {}".format(pb.pr.title))
            proccesed_prs += 1

        elif is_success:
            merged = False
            proccesed_prs += 1

            # Check if 'Merged' in comments
            for com in comments:
                if 'Merged' in com.body:
                    merged = True

            if merged:
                is_pkg = True if pb.pkg in mb_pb.current_meta[-1].split(":")[0] else False
                is_version = True if pb.version in mb_pb.current_meta[-1].split(":")[1] else False
                is_revert = any(labels[0]["name"] in lbl.name for lbl in pb.pr.labels)
                if is_pkg and is_version and not is_revert:
                    print("{} -> {}:{}".format(pb.pkg, is_pkg, is_version))
            else:
                check_mb_ci_status()
                if 'failure' not in mb_pb.ci and 'pending' not in mb_pb.ci:
                    merge_pkg_to_mb(pb)

        elif is_pending and ci_state.statuses:
                print("CI still PENDING".format(pb.branch.name))

        else:
            candidate = pb

    print("Proccesed PullRequests: {}/{}".format(proccesed_prs, len(pr_list)))
    if not ci_running and len(pr_list) > proccesed_prs:
        try:
            for req in candidate.reqs:
                update_lower_deps(candidate, candidate.branch.name, req)
            candidate.trigger_ci()
        except UnboundLocalError as e:
            if "referenced before assignment" in e.data:
                pass


# Merging single package branch into Final_merge_branch after a success in CI
def merge_pkg_to_mb(pb):
    merged = False
    for req in pb.reqs:
        merge_branch_global = base64.b64decode(
                              repo.get_file_contents(req, ref='heads/' + merge_branch).content
                              ).decode()

        merge_branch_sha = repo.get_file_contents(req, ref=merge_branch).sha
        merge_branch_global = merge_branch_global.replace("{}=={}".format(pb.pkg, pb.old_version),
                                                          "{}=={}".format(pb.pkg, pb.version))
        try:
            repo.update_file("/" + req, "global-reqs updated -> {}:{}".format(pb.pkg, pb.version),
                             merge_branch_global,
                             merge_branch_sha,
                             branch=merge_branch)

        except GithubException as e:
            print("Could not update file: {} \nError: {}".format(req, e.data['message']))

        else:
            update_lower_deps(pb, merge_branch, req)
            merged = True

    create_merge_branch()
    if merged:
        pb.pr.create_issue_comment("Merged")
        mb_pb.trigger_ci()
        mb_pb.current_meta.append(pb.desc)
        mb_pb.pr.edit(body=json.dumps(mb_pb.current_meta))


# Check all successful single packages combined into one branch.
def check_mb_ci_status():
    global mb_pb

    try:
        mb_ci_state = mb_pb.pr.get_commits().get_page(0)[-1].get_combined_status()
    except AttributeError:
        mb_ci_state = ""
        is_failed = False
        is_pending = False
        is_success = False
        pass

    else:
        is_failed = 'failure' in mb_ci_state.state
        is_pending = 'pending' in mb_ci_state.state
        is_success = 'success' in mb_ci_state.state

    if is_failed:
        mb_pb.ci = "failure"
        if 'Reverted' not in mb_pb.last_comment.body:
            mb_pb.pkg = mb_pb.current_meta[-1].split(":")[0]
            mb_pb.old_version = mb_pb.current_meta[-1].split(":")[1]
            mb_pb.version = mb_pb.current_meta[-1].split(":")[2]
            mb_pb.reqs = json.loads(mb_pb.current_meta[-1].split(":")[3])

            pb_name = mb_pb.current_meta[-1].split(":")[4]
            pb = repo.get_branch(pb_name)
            pb = PullBranch(branch=pb)

            for req in mb_pb.reqs:
                revert_global = base64.b64decode(
                                repo.get_file_contents(req, ref='heads/' + merge_branch).content
                                ).decode()

                revert_global = revert_global.replace("{}=={}".format(mb_pb.pkg, mb_pb.version),
                                                      "{}=={}".format(mb_pb.pkg, mb_pb.old_version))

                try:
                    revert_global_sha = repo.get_file_contents(req, ref=merge_branch).sha
                    repo.update_file("/" + req, "global-reqs updated -> {}:{}".format(mb_pb.pkg, mb_pb.old_version),
                                     revert_global,
                                     revert_global_sha,
                                     branch=merge_branch)

                except GithubException as e:
                    print("Could not revert file: {} \nError: {}".format(req, e.data['message']))

                else:
                    update_lower_deps(mb_pb, merge_branch, req)
                    pb.add_label(labels[0]['name'])
                    del mb_pb.current_meta[-1]
                    mb_pb.pr.edit(body=json.dumps(mb_pb.current_meta))
                    mb_pb.pr.create_issue_comment("Reverted")
                    mb_pb.pr.get_commits().get_page(0)[-1].create_status('success')
                    mb_pb.ci = "Reverted"

    elif is_success:
        mb_pb.ci = 'success'

        try:
            last_pb_name = mb_pb.current_meta[-1].split(":")[4]
            last_pb = repo.get_branch(last_pb_name)
        except GithubException as e:
            if e.status == 404:
                pass

        except IndexError as e:
            if 'list index out of range' in e.data:
                pass
        else:
            last_pb = PullBranch(branch=last_pb)
            last_pb.delete()

    elif is_pending and mb_ci_state.statuses:
        mb_pb.ci = 'pending'

    else:
        mb_pb.ci = 'no-ci'


def clean_prs():
    global pr_list
    create_pb_list()
    for pb in pr_list:
        pb.delete()

    pr_list = []
    try:
        b = repo.get_branch(merge_branch)

    except GithubException as e:
        if e.status == 404:
            pass

    else:
        mb_pb = PullBranch(branch=b)
        mb_pb.delete()


def main():
    if 'True' in p:
        print("------------------ Purge -------------------")
        clean_prs()
    # clean_prs() # DEBUG
    create_labels()
    print("------------------ PyUp -------------------")
    run_pyup()
    create_pb_list()
    print("------------------ Check CI -------------------")
    check_pb_ci_status()


if __name__ == '__main__':
    main()

print("Done")

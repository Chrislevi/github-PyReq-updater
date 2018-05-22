#!/usr/bin/python


import os
import yaml
# import time
import subprocess
import base64
from github import GithubException
from github import Github
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--check', action='store_true', help='Run pyreq PullRequest updater')
parser.add_argument('--update', action='store_true', help='Run pyreq PullRequest updater')
args = parser.parse_args()

# Get GitHub API Credentials.
with open("config.yaml", "r") as config:
    cfg = yaml.load(config)

try:
    gh_user = str(os.environ['GH_USER'])
    gh_pass = str(os.environ['GH_PASS'])

except KeyError:
    print "No ENV credentials, rolling to config.yaml"
    try:
        gh_user = cfg['user']
        gh_pass = cfg['pass']

    except KeyError:
        print "Please provide any credentials. (config/ENV)"
        exit()


git = Github(gh_user, gh_pass)
org = git.get_organization(cfg['org'])
orig_repo = org.get_repo(cfg['repo'])
repo = git.get_user().get_repo(cfg['repo'])
owner = repo.owner.login
master = repo.get_branch(cfg['master'])
ci_trig = cfg['ci_phrase']
final_branch = cfg['pyreq_master']
skip_pkg = cfg['skip_packages']

req_list = []
#req_list = ["requirements.txt"]
pr_list = []


class PullBranch(object):
    def __init__(self, branch=None, pr=None):
        self.branch = branch
        self.pr = pr


def ensure_finalbranch():
    if check_pr(final_branch):
        print "PR {} Already exists!".format(final_branch)
    else:
        try:
            cb = repo.get_branch(final_branch)
            print "{} exists".format(cb.name)

        except GithubException as e:
            if 'Branch not found' in e.data['message']:
                create_branch(master, final_branch)
                print "creating Merge branch {}".format(final_branch)
            else:
                print e.data['message']


def recurse_check(dir_list, rlist):
    for f in dir_list:
        if 'file' in f.type and 'requirements.txt' in f.path:
            rlist.append(f.path)

        elif 'dir' in f.type:
            dir = repo.get_dir_contents(f.path)
            recurse_check(dir, rlist)


def create_branch(sbranch, tbranch):
    sb = repo.get_branch(sbranch.name)
    try:
        repo.create_git_ref(ref='refs/heads/' + tbranch, sha=sb.commit.sha)
        print "{}: Branch created.".format(tbranch)
        return repo.get_branch(tbranch)

    except GithubException as e:
        if e.status == 422:
            print "Already exists {}".format(tbranch)
            return repo.get_branch(tbranch)


def alter_file(src_path, tbranch, package, version, newversion):
    old_req = repo.get_file_contents(src_path)
    new_req = repo.get_file_contents(src_path, ref=tbranch)
    new_content = str(base64.b64decode(old_req.content).replace("{}=={}".format(package, version),
                                                                "{}=={}".format(package, newversion)))

    pkg_info = "Update: {} {} -> {}".format(package, version, newversion)
    try:
        repo.update_file("/" + old_req.path,
                         pkg_info,
                         new_content,
                         new_req.sha,
                         branch=tbranch)

        print "{}: {} file changed!".format(tbranch, src_path)

    except GithubException as e:
        print "Could not update file: {} \nError: {}".format(old_req.path, e.data['message'])


def create_pr(tbranch, ci_trigger, owner):
    try:
        cpr = repo.create_pull(tbranch,
                               "",
                               merge_branch.name,
                               '{}:{}'.format(owner, tbranch),
                               True)

        print "{}: PR created ".format(tbranch)
        pr = repo.get_pull(cpr.number)
        pr.create_issue_comment(ci_trigger)

    except GithubException as e:
        print "Could not create PR: {} \nError: {}".format(tbranch, e.data['message'])


def check_pr(tbranch, repo=repo):
    exist = False
    for pr in repo.get_pulls():
        if tbranch in pr.title:
            exist = True
    return exist


def run_pur(git_src):
    tmp_req_dir = '/tmp/req.txt'
    bashcmd = 'pur -s "{}" -r {}'.format(skip_pkg, tmp_req_dir)

    # GET master branch req.txt file content
    curr_req = repo.get_file_contents(git_src)
    with open(tmp_req_dir, 'w+') as req:
        req.write(str(base64.decodestring(curr_req.content)))

    # Run Pur to check for updates
    return subprocess.check_output(bashcmd, shell=True)


def check_pr_id(pb):
    for pr in repo.get_pulls():
        if pb.branch.name in pr.title:
            pb.pr = pr


# Populate PullBranch Class
def pr_dict():
    for b in repo.get_branches():
        if 'PyReq' in b.name:
            pr = PullBranch(branch=b)
            check_pr_id(pr)
            pr_list.append(pr)


def del_prbranch(pb):
    try:
        print "Deleting PR: {}".format(pb.pr.title)
        pb.pr.edit(state="closed")
        print "Deleting Branch: {}".format(pb.branch.name)
        repo.get_git_ref(ref='heads/' + pb.branch.name).delete()

    except GithubException as e:
        print e.message


def check_ci(b):
    ci_state = b.branch.commit.get_combined_status().state
    print "Checking {}, {}".format(b.pr.title, b.pr.mergeable)
    if 'failure' in ci_state:
        del_prbranch(b)

    elif 'pending' in ci_state:
        print "{} CI still PENDING".format(b.branch.name)

    elif 'success' in ci_state:
        try:
            b.pr.merge()
            # repo.merge(merge_branch.name, b.branch.name, commit_message="Pyreq-Updater -> {}".format(b.branch.name))
            print "Merged {}".format(b.pr.title)

        except GithubException as e:
            print e.data['message']

        else:
            del_prbranch(b)


def pyreq_push():
    dc = repo.get_dir_contents("/")
    recurse_check(dc, req_list)

    print "Updating these files:"
    for f in req_list:
        print f

    for reqfile in req_list:
        output = run_pur(reqfile)
        if len(output.split('\n')) > 1:
            for line in output.split('\n')[:-2]:
                pkg = (line.split(' ')[1])[:-1]
                ver = line.split(' ')[2]
                newver = line.split(' ')[4]

                if len(reqfile.split('/')) > 1:
                    target_branch = 'PyReq/{}_{}_{}'.format(reqfile.split('/')[-2], pkg, newver)
                else:
                    target_branch = 'PyReq/{}_{}_{}'.format("main", pkg, newver)

                if check_pr(target_branch):
                    print "PullRequest: {} already created!".format(target_branch)
                else:
                    cb = create_branch(merge_branch, target_branch)
                    alter_file(reqfile, cb.name, pkg, ver, newver)
                    create_pr(cb.name, ci_trig, owner)


def pyreq_check():
    pr_dict()
    for b in pr_list:
        check_ci(b)
    try:
        orig_master = orig_repo.get_branch(cfg['master'])
        orig_repo.create_pull("Final PyReq Updates",
                         "",
                         '{}'.format(orig_master.name),
                         '{}:{}'.format(owner, merge_branch.name),
                         True)
        print "Weekly PR created"
    except GithubException as e:
        if 'Validation Failed' in e.data['message'] and check_pr("Weekly PyReq Updates", repo=orig_repo):
            print "Final Merge request already exists!"


def pyreq_update():
    try:
        orig_master = orig_repo.get_branch(cfg['master'])
        dev_pr = repo.create_pull("devel update",
                         "",
                         '{}'.format(master.name),
                         '{}:{}'.format(cfg['org'], orig_master.name),
                         True)
        print "Updating {}".format(master.name)
    except GithubException as e:
        if 'Validation Failed' in e.data['message']:
            print e.data['message']
    else:
        dev_pr.merge()
        print "Merged"

# MAIN() - Switch case
ensure_finalbranch()
merge_branch = repo.get_branch(cfg['pyreq_master'])
if args.check:
    print "Check Pullrequests!"
    pyreq_check()

elif args.update:
    print cfg['org']
    pyreq_update()

else:
    print "Creating required PullRequests!"
    pyreq_push()

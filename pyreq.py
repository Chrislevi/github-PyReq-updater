#!/usr/bin/python

import os
import subprocess
import base64
from github import Github
import random
import string

gh_user = str(os.environ['GH_USER'])
gh_pass = str(os.environ['GH_PASS'])
git = Github(gh_user, gh_pass)
repo = git.get_user().get_repo('github-PyReq-updater')
owner = repo.owner.login
master = repo.get_branch('master')
ci_trig = "Automatically generated PR" # I personally use PR Comments to trigger CI
req_list = []


def recurse_check(dir_list, rlist):
    for f in dir_list:
        if 'file' in f.type and 'requirements.txt' in f.path:
            rlist.append(f.path)
        elif 'dir' in f.type:
            dir = repo.get_dir_contents(f.path)
            recurse_check(dir, rlist)


def random_string(length):
    pool = string.letters + string.digits
    return ''.join(random.choice(pool) for i in xrange(length))


def create_branch(sbranch, tbranch, src_path, pkg, ver, newver):
    sb = repo.get_branch(sbranch.name)
    try:
        repo.create_git_ref(ref='refs/heads/' + tbranch, sha=sb.commit.sha)
        print "{}: Branch created.".format(tbranch)
        alter_file(src_path, tbranch, pkg, ver, newver)
    except:
        print "{}: Branch already exists.".format(tbranch)
    return repo.get_branch(tbranch)


def alter_file(src_path, tbranch, package, version, newversion):
    old_req = repo.get_file_contents(src_path)
    new_content = str(base64.b64decode(old_req.content).replace("{}=={}".format(package, version), "{}=={}".format(package, newversion)))
    try:
        repo.update_file("/" + old_req.path, "Update: {} {} -> {}".format(package, version, newversion), new_content, old_req.sha, branch=tbranch)
        print "{}: {} file changed!".format(tbranch, src_path)
    except:
        print "Could not update file: {}".format(old_req.path)


def create_pr(tbranch, ci_trigger, owner):
    try:
        cpr = repo.create_pull(tbranch, "", master.name, '{}:{}'.format(owner, tbranch), True)
        print "{}: PR created ".format(tbranch)
        pr = repo.get_pull(cpr.number)
        pr.create_issue_comment(ci_trigger)
    except:
        print "{}: PR already exists.".format(tbranch)


def run_pur(git_src):
    tmp_req_dir = '/tmp/req.txt'
    bashcmd = 'pur -r {}'.format(tmp_req_dir)

    # GET master branch req.txt file content
    curr_req = repo.get_file_contents(git_src)
    with open(tmp_req_dir, 'w+') as req:
        req.write(str(base64.decodestring(curr_req.content)))

    # Run Pur to check for updates
    return subprocess.check_output(bashcmd, shell=True)


# Main
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
                target_branch = 'PyReq/{}-{}_{}'.format(reqfile.split('/')[-2], pkg, newver)
            else:
                target_branch = 'PyReq/{}-{}_{}'.format("main", pkg, newver)

            cb = create_branch(master, target_branch, reqfile, pkg, ver, newver)
            create_pr(cb.name, ci_trig, owner)

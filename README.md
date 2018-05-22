# github-PyReq-updater
PyReq updates your GitHub repo requirements.txt files and opens a PullRequest per available package update

fork with `user` the requested repository for PyReq to update. (Fork due to PullRequest SPAM isolation)

### Config.yaml
`user: 'USER'     # Github User credentials. Forked USER
pass: 'PASSWORD'  #
org: 'ORG'        # repository ORG owner.
repo: 'REPO'      # repo name
master: 'master'  # default branch
pyreq_master: 'pyreq_merge_branch' # concentrated branch for all passing deps
ci_phrase: 'Raus!'                 # Using GHPRB trigger phase
skip_packages: 'celery, requests'  # Comma seperated example`

### Args
pyreq without any args runs through the desired repo and searches for stale deps(i.e requests==2.4.1) in each requirements.txt
and opens a pullrequest between each new dep package found towards a concentrating branch `pyreq_master`

- `--check` -> iterates over PullRequests for passing CI commit status and acts accordingly()
- `--update` -> update origin master to forked master to keep master up-to-date.

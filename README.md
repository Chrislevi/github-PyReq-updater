# github-PyReq-updater
* PyReq updates your GitHub repo requirements.txt files and opens a PullRequest per available package update including CI check.

* All packages are tested in individual branches initially, After checking CI it updates `pyreq_master` with the desired changes(globals and Low reqs)
according to the CI's results. 

* Each `pyreq_master` branch update ci is initialized once again with all the passing individual package updates.

* If a newer package is out there and there's already an open PullRequest with the same package, it will reopen the package's PR with the latest package version.

# Branch FLOW
```
                                                                                                                      *merge_branch: Revert last update, open issue
                                                                                                                **dependency_branch: Waiting for new release
                                                                                                                                          
                                                                                                                                         ^ 
                                                                       CI_Phrase                                                         |
                                        +----------------------------------------------------------------------------------------+       |
                                        |                                                                                        |       |
                                        |                                                                                        |       |
                                        |                                                                                        |       |
                                        |                              redis 2.0.1 -> 2.10.6                                     |       |
                                        |                              +-----------------+                                       |       |
                                        |                              |                 |                                       |       |
                                        +                              |                 |                                       |       |
                                    merge_branch                       |                 |    CI_Phrase                          |       |
 +-----------------+             +-----------------+       +---------> |                 +----------------+                      |       |
 |                 |             |                 |       |           |                 |                |                      |       |
 |      FORK       |             |                 |       |           |                 |                |                      |       |
 |                 |             |                 |       |           |                 |                |                      |     Failed
 |   Development   +---------->  |                 |       |           +-----------------+                |                      v       |
 |     Branch      |             |                 +-------+                                              |                              |
 |                 |             |                 |       |           idna 2.6 -> 2.7                    |               +--------------+--+
 |                 |             |                 |       |           +-----------------+                |               |                 |
 +-------+---------+             +-----------------+       |           |                 |                |               |                 |
         ^                                                 |           |                 |    CI_Phrase   |               |                 | <------+
         |                              ^                  |           |                 +------------------------------> |     Jenkins     |          Pending
         |                              |                  +-------->  |                 |                |               |                 | +------>
     --update                           |                  |           |                 |                |               |                 |
         |                              |                  |           |                 |                |               |                 |
         |                              |                  |           |                 |                |               +-------+---------+
         |                              |                  |           +-----------------+                |                       |
         V                              |                  |                                              |                       |
+--------+--------+                     |                  |            requiests 2.4 -> 2.4.2            |                       |
|                 |                     |                  |           +-----------------+                |                       |
|     ORIGIN      |                     |                  |           |                 |                |                     Success
|                 |                     |                  |           |                 |                |                       |
|  Development    |                     |                  |           |                 |    CI_Phrase   |                       |
|    Branch       |                     |                  |           |                 +----------------+                       |
|                 |                     |                  +---------> |                 |                                        |
|                 |                     |                              |                 |                                        |
+-----------------+                     |                              |                 |                                        |
                                        |                              +-----------------+                                        |
                                        |                                                                                         |
                                        |                                                                                         |
                                        |                                 Updating global-reqs.txt                                | 
                                        +-----------------------------------------------------------------------------------------+ 
```

### Configuration
* `.pyup.yml` is PyReq's configuration file located at the repository's root directory. each section is self explainatory

* Skipping packages use `# pyup: ignore` right after the package name (i.e `redis==2.10.6 # pyup: ignore`)
```
# configure updates globally
# default: all
# allowed: all, insecure, False
update: all

# configure dependency pinning globally - auto pins unpinned dependency packages
# default: True
# allowed: True, False
pin: False

# set the default merge branch name
merge_branch: "PyReq-Final-Updates"

# set the master branch
# default: empty, the default branch on GitHub
master: "master"

# search for requirement files - searches for every file/dir named 'requirements'
# default: True
# allowed: True, False
search: False

# A list of requirements files instead of auto discovery
requirements:
  - global-reqs.txt:
      update: all
      pin: False
  - packages/global-reqs.txt:
      update: all
      pin: False

# configure the branch prefix the bot is using
# default: pyup-
branch_prefix: PyReq/

# allow to close stale PRs
# default: True
close_prs: True

# CI trigger phrase
ci_phrase: 'test this please'

```

### Args(ENV vars)
pyreq without any args runs through the desired repo and searches for stale deps(i.e requests==2.4.1) in each requirements.txt
and opens a pullrequest between each new dep package found towards a concentrating branch `pyreq_master`

- `--token`(GH_TOKEN) -> (***Mandatory***)  Personal Access Token, required to operate the Bot. (Scopes: repo:all, read:user, user:email)
- `--repo`(GH_REPO) -> (***Mandatory***) Target repo (i.e mubi/docker)
- `--branch`(GH_BRANCH) -> (***Mandatory***) Target branch (i.e dev) 
- `--purge`(GH_PURGE) -> Purge existing PyReq PullBranchs

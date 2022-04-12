from __future__ import annotations

import base64
import json
import subprocess
import urllib
from typing import Any
from typing import NamedTuple

from all_repos import autofix_lib
from all_repos import bitbucket_server_api
from all_repos import git
from all_repos.util import hide_api_key_repr


class Settings(NamedTuple):
    username: str
    app_password: str
    base_url: str
    default_reviewers: bool = False

    @property
    def auth_header(self) -> dict[str, str]:
        value = f'{self.username}:{self.app_password}'
        return {'Authorization': base64.b64encode(value.encode()).decode()}

    def __repr__(self) -> str:
        return hide_api_key_repr(self, key='app_password')


def _get_default_reviewers(
        base_url: str,
        auth_header: dict[str, str],
        project: str,
        repo_slug: str,
        branch: str,
        default_reviewers: bool = False,
) -> list[dict[str, dict[str, Any]]]:

    if not default_reviewers:
        return []

    repo_end_point = f'projects/{project}/repos/{repo_slug}'

    resp = urllib.request.urlopen(
        urllib.request.Request(
            f'https://{base_url}/rest/api/1.0/{repo_end_point}',
            headers=auth_header, method='GET',
        ),
    )
    repo = json.load(resp)
    repo_id = repo['id']

    default_reviewers_end_point = (
        f'https://{base_url}/rest'
        f'/default-reviewers/1.0/projects/{project}'
        f'/repos/{repo_slug}/reviewers?sourceRepoId={repo_id}'
        f'&sourceRefId={branch}'
        f'&targetRepoId={repo_id}&targetRefId={branch}'
    )

    resp = urllib.request.urlopen(
        urllib.request.Request(
            default_reviewers_end_point,
            headers=auth_header, method='GET',
        ),
    )

    reviewers = json.load(resp)

    return [
        {'user': {'name': reviewer['name']}}
        for reviewer in reviewers
    ]


def make_pull_request(
        base_url: str,
        auth_header: dict[str, str],
        branch_name: str,
        target_branch_name: str,
        default_reviewers: bool = False,
) -> bitbucket_server_api.Response:
    headers = {
        'Content-Type': 'application/json',
        **auth_header,
    }

    remote = git.remote('.')
    remote_url = remote[:-len('.git')] if remote.endswith('.git') else remote
    *prefix, project, repo_slug = remote_url.split('/')
    head = branch_name

    autofix_lib.run('git', 'push', 'origin', f'HEAD:{branch_name}', '--quiet')

    title = subprocess.check_output(('git', 'log', '-1', '--format=%s'))
    body = subprocess.check_output(('git', 'log', '-1', '--format=%b'))

    reviewers = _get_default_reviewers(
        base_url, auth_header, project, repo_slug, branch_name,
        default_reviewers,
    )

    data = json.dumps({
        'title': title.decode().strip(),
        'description': body.decode().strip(),
        'state': 'OPEN',
        'open': True,
        'closed': False,
        'fromRef': {
            'id': head,
            'repository': {
                'slug': repo_slug,
                'project': {
                    'key': project,
                },
            },
        },
        'toRef': {
            'id': target_branch_name,
            'repository': {
                'slug': repo_slug,
                'project': {
                    'key': project,
                },
            },
        },
        'locked': False,
        'reviewers': reviewers,
    }).encode()

    end_point = f'projects/{project}/repos/{repo_slug}/pull-requests'
    return bitbucket_server_api.req(
        f'https://{base_url}/rest/api/1.0/{end_point}',
        data=data, headers=headers, method='POST',
    )


def push_and_create_pr(
        base_url: str,
        auth_header: dict[str, str],
        branch_name: str,
        target_branch_name: str,
        default_reviewers: bool = False,
        file_obj = None
) -> None:
    resp = make_pull_request(
        base_url, auth_header, branch_name, target_branch_name,
        default_reviewers,
    )
    url = resp.links['self'][0]['href'] if resp.links else ''
    if file_obj is None:
        f = open("/opt/aruba/central/apps/all-repos-animesh/PRlist.txt", "a")
        f.write(url+"\n")
        f.close()
    else:
        file_obj.write(url+"\n")
    print(f'Pull request created at {url}')


def push(settings: Settings, branch_name: str, target_branch_name: str) -> None:
    push_and_create_pr(settings.base_url, settings.auth_header, branch_name, target_branch_name)

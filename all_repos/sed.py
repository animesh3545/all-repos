from __future__ import annotations

import argparse
import functools
import os.path
import shlex
import subprocess
from typing import Generator
from typing import Sequence

from identify.identify import tags_from_path

from all_repos import autofix_lib
from all_repos.config import Config
from all_repos.util import zsplit


def find_repos(
        config: Config,
        *,
        ls_files_cmd: Sequence[str],
) -> Generator[str, None, None]:
    for repo in config.get_cloned_repos():
        repo_dir = os.path.join(config.output_dir, repo)
        # print(f"subprocess - {subprocess.run(subprocess.run, check=True, stdout=subprocess.PIPE).stdout}")
        # if subprocess.run(
        #     # ('git', '-C', repo_dir, *ls_files_cmd[1:]),
        #     ls_files_cmd,
        #     check=True, stdout=subprocess.PIPE,
        # ).stdout:
        #     print(f'repo_dir - {repo_dir}')
        #     file = ls_files_cmd[1:]
        #     print(f'*ls_files_cmd[1:] - {file}')
        yield repo_dir


def apply_fix(
        *,
        ls_files_cmd: Sequence[str],
        sed_cmd: Sequence[str],
) -> None:
    filenames_b = zsplit(subprocess.check_output(ls_files_cmd))
    filenames = [f.decode() for f in filenames_b]
    filenames_list = []
    for filename in filenames:
        filename = filename.replace("./", "")
        filenames_list.extend(filename.split('\n')[:-1])
    filenames = [f for f in filenames_list if tags_from_path(f) & {'file', 'text'}]
    autofix_lib.run(*sed_cmd, *filenames)


def _quote_cmd(cmd: tuple[str, ...]) -> str:
    return ' '.join(shlex.quote(arg) for arg in cmd)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            'Similar to a distributed '
            '`git ls-files -z -- FILENAMES | xargs -0 sed -i EXPRESSION`.'
        ),
        usage='%(prog)s [options] EXPRESSION FILENAMES',
    )
    autofix_lib.add_fixer_args(parser)
    parser.add_argument(
        '-r', '--regexp-extended',
        action='store_true',
        help='use extended regular expressions in the script.',
    )
    parser.add_argument(
        '--branch-name', default='all-repos-sed',
        help='override the autofixer branch name (default `%(default)s`).',
    )
    parser.add_argument(
        '--commit-msg',
        help=(
            'override the autofixer commit message.  (default '
            '`git ls-files -z -- FILENAMES | xargs -0 sed -i ... EXPRESSION`).'
        ),
    )
    parser.add_argument(
        '--prlistfile',
        help=(
            'Provide the file name to add PR URLs, this will help for tracking Raised PRs'
        )
    )
    parser.add_argument(
        'expression', help='sed program. For example: `s/hi/hello/g`.',
    )
    parser.add_argument(
        'filenames', help='filenames glob (passed to `git ls-files`).',
    )
    args = parser.parse_args(argv)

    # https://github.com/python/mypy/issues/4975
    dash_r: tuple[str, ...]
    if args.regexp_extended:
        dash_r = ('-r',)
    else:
        dash_r = ()
    sed_cmd = ('sed', '-i', *dash_r, args.expression)
    # ls_files_cmd = ('git', 'ls-files', '-z', '--', args.filenames)
    ls_files_cmd = ('find', '.', '-name', args.filenames)

    msg = f'{_quote_cmd(ls_files_cmd)} | xargs -0 {_quote_cmd(sed_cmd)}'
    msg = args.commit_msg or msg

    prlist_filename = args.prlistfile
    if os.path.exists(prlist_filename):
        append_write = 'a'  # append if already exists
    else:
        append_write = 'w'  # make a new file if not
    file_object = open(prlist_filename, append_write)

    repos, config, commit, autofix_settings = autofix_lib.from_cli(
        args,
        find_repos=functools.partial(find_repos, ls_files_cmd=ls_files_cmd),
        msg=msg, branch_name=args.branch_name,
    )

    autofix_lib.fix(
        repos,
        apply_fix=functools.partial(
            apply_fix, ls_files_cmd=ls_files_cmd, sed_cmd=sed_cmd,
        ),
        config=config, commit=commit, autofix_settings=autofix_settings,
        file_object=file_object
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

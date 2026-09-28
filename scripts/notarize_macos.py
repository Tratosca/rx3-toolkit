#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Notarize a signed app, staple its ticket, and archive the validated result."""
import argparse
import json
import pathlib
import subprocess
import tempfile


def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('app', type=pathlib.Path)
    parser.add_argument('--profile', required=True, help='Existing notarytool Keychain profile; never a password')
    parser.add_argument('--output', type=pathlib.Path, required=True)
    args = parser.parse_args()
    app = args.app.resolve()
    if app.suffix != '.app' or not app.is_dir():
        parser.error('app must be an existing .app bundle')
    if args.output.suffix != '.zip' or args.output.exists():
        parser.error('output must be a new .zip path')
    run('codesign', '--verify', '--deep', '--strict', '--verbose=2', str(app))
    identity = run('codesign', '-dvv', str(app), capture_output=True, text=True).stderr
    if 'Authority=Developer ID Application:' not in identity or 'runtime' not in identity:
        parser.error('bundle needs Developer ID Application signing and hardened runtime')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = args.output.with_suffix('.notary.json')
    with tempfile.TemporaryDirectory(prefix='rx3-notary-') as temp:
        archive = pathlib.Path(temp) / 'submission.zip'
        run('ditto', '-c', '-k', '--sequesterRsrc', '--keepParent', str(app), str(archive))
        submission = subprocess.run(['xcrun', 'notarytool', 'submit', str(archive), '--keychain-profile', args.profile,
                         '--wait', '--output-format', 'json'], capture_output=True, text=True)
        try:
            result = json.loads(submission.stdout)
        except ValueError:
            raise SystemExit(submission.stderr or submission.stdout or 'Notarization returned no result')
        report.write_text(json.dumps(result, indent=2) + '\n')
        if result.get('id'):
            run('xcrun', 'notarytool', 'log', result['id'], '--keychain-profile', args.profile,
                str(args.output.with_suffix('.notary-log.json')))
        if result.get('status') != 'Accepted':
            raise SystemExit(f"Notarization {result.get('status')}: see {report}")
    run('xcrun', 'stapler', 'staple', str(app))
    run('xcrun', 'stapler', 'validate', str(app))
    run('codesign', '--verify', '--deep', '--strict', str(app))
    run('spctl', '--assess', '--type', 'execute', '--verbose=2', str(app))
    # ditto retains the ticket and framework symlinks in the shipped archive.
    with tempfile.TemporaryDirectory(prefix='rx3-distribution-') as temp:
        staging = pathlib.Path(temp)
        run('ditto', str(app), str(staging / app.name))
        root = pathlib.Path(__file__).resolve().parents[1]
        for name in ('LICENSE', 'THIRD_PARTY_NOTICES.md'):
            run('ditto', str(root / name), str(staging / name))
        run('ditto', '-c', '-k', '--sequesterRsrc', str(staging), str(args.output.resolve()))
    print(f'Notarized archive: {args.output}')


if __name__ == '__main__':
    main()

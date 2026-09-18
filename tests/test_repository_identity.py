"""Guards the repository's own identity in its shipped documentation.

The failure this exists to prevent: the project was renamed to Cool-Academic
across the documentation before the GitHub repository itself was renamed, so nine
internal links pointed at a repository that does not exist yet and returned 404.
The offline link checker could not catch it, because it skips absolute http(s)
URLs by design.

So the rule is now explicit: every internal GitHub URL must use the slug recorded
in config/repository.json, which is the slug that exists today. GitHub redirects
the old slug to the new one after a rename, but never the reverse, so the old
slug is the safe choice before and after.

When the repository is finally renamed, change config/repository.json and run this
file; it will list every remaining URL that needs updating.
"""
from pathlib import Path
import json
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / 'config' / 'repository.json').read_text(encoding='utf-8'))
OWNER = CONFIG['owner']
CANONICAL = CONFIG['repo']
# Repositories of the same owner that may legitimately appear in the docs, e.g.
# the legacy source this project was migrated from. Declared in config, not
# hardcoded here, so the reason travels with the entry.
RELATED = set(CONFIG.get('related_repositories', {}))

URL = re.compile(r'https?://github\.com/([\w.-]+)/([\w.-]+)')
PROMPT = re.compile(r'@GitHub\s*(?:请)?读取\s*([\w.-]+)/([\w.-]+)')
# A user-facing instruction must not pin an exact build artefact version: it goes
# stale every release. Changelogs are history and are allowed to name old builds.
CHANGELOG = re.compile(r'docs/CHANGELOG_.*\.md$')
PINNED_ASSET = re.compile(r'Cool-Academic-v\d+\.\d+\.\d+-skill\.zip')


def shipped_markdown():
    manifest = json.loads((ROOT / 'config' / 'distribution-files.json').read_text(encoding='utf-8'))
    out = []
    for name in manifest['files']:
        if name.endswith('.md'):
            out.append((name, ROOT.joinpath(*name.split('/'))))
    return out


class ConfigTests(unittest.TestCase):
    def test_config_has_the_required_fields(self):
        for key in ('owner', 'repo', 'display_name', 'note'):
            self.assertIn(key, CONFIG)

    def test_canonical_slug_is_the_one_that_exists(self):
        """The recorded slug must match the real repository, not the display name."""
        self.assertEqual(CONFIG['repo'], 'Ku-academic')
        self.assertEqual(CONFIG['display_name'], 'Cool-Academic')

    def test_note_explains_why_the_old_slug_is_used(self):
        self.assertIn('redirect', CONFIG['note'].lower())


class InternalUrlTests(unittest.TestCase):
    def test_every_internal_url_uses_the_canonical_slug(self):
        offenders = []
        for name, path in shipped_markdown():
            text = path.read_text(encoding='utf-8')
            for owner, slug in URL.findall(text):
                if owner != OWNER:
                    continue
                slug = re.sub(r'\.git$', '', slug)
                if slug == CANONICAL or slug in RELATED:
                    continue
                offenders.append('%s: %s/%s' % (name, owner, slug))
        self.assertEqual(offenders, [],
                         'internal URLs must use %r until the repository is renamed; '
                         'update config/repository.json and then these files'
                         % CANONICAL)

    def test_every_github_prompt_uses_the_canonical_slug(self):
        offenders = []
        for name, path in shipped_markdown():
            text = path.read_text(encoding='utf-8')
            for owner, slug in PROMPT.findall(text):
                if owner != OWNER or slug in RELATED:
                    continue
                if slug != CANONICAL:
                    offenders.append('%s: %s/%s' % (name, owner, slug))
        self.assertEqual(offenders, [])

    def test_related_repositories_are_documented(self):
        for slug, reason in CONFIG.get('related_repositories', {}).items():
            self.assertTrue(reason.strip(), 'related repo %s needs a reason' % slug)

    def test_no_reference_to_the_nonexistent_repository(self):
        """A URL naming the display name as a repo is the exact original bug."""
        pattern = re.compile(r'github\.com/%s/%s' % (re.escape(OWNER),
                                                     re.escape(CONFIG['display_name'])))
        offenders = []
        for name, path in shipped_markdown():
            if pattern.search(path.read_text(encoding='utf-8')):
                offenders.append(name)
        self.assertEqual(offenders, [])


class VersionPinningTests(unittest.TestCase):
    def test_user_facing_docs_do_not_pin_a_build_version(self):
        offenders = []
        for name, path in shipped_markdown():
            if CHANGELOG.search(name):
                continue
            for match in PINNED_ASSET.findall(path.read_text(encoding='utf-8')):
                offenders.append('%s: %s' % (name, match))
        self.assertEqual(offenders, [], 'describe the artefact name as a pattern '
                                        'instead of pinning a version that goes stale')

    def test_release_links_are_still_present_somewhere(self):
        text = (ROOT / 'README.md').read_text(encoding='utf-8')
        self.assertIn('/releases/latest', text)


class ManifestTests(unittest.TestCase):
    def test_repository_config_is_shipped(self):
        manifest = json.loads((ROOT / 'config' / 'distribution-files.json').read_text(encoding='utf-8'))
        self.assertIn('config/repository.json', manifest['files'])


if __name__ == '__main__':
    unittest.main()

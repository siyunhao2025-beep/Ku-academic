"""Synthetic fixtures only. No fixture is a scientific result or an actual journal corpus."""
import copy
import io
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import research as r
import corpus
import upstream


def _can_create_symlink():
    """Return True only if this process can really create a usable symlink.

    On Windows a symlink needs SeCreateSymbolicLinkPrivilege (administrator or
    Developer Mode). Without it os.symlink/Path.symlink_to can return without
    error while creating nothing, so a test that assumes a symlink exists would
    pass or fail for the wrong reason. Probe for a real, listable link.
    """
    try:
        with tempfile.TemporaryDirectory() as t:
            base = Path(t)
            target = base / 'target'
            target.mkdir()
            link = base / 'link'
            link.symlink_to(target, target_is_directory=True)
            return link.is_symlink() and link.exists()
    except (OSError, NotImplementedError):
        return False


HAS_SYMLINK = _can_create_symlink()


class CoreTests(unittest.TestCase):
    def test_doi_prefix(self):
        self.assertEqual(r.doi(' https://doi.org/10.1234/ABC '), '10.1234/abc')

    def test_doi_encoded(self):
        self.assertEqual(r.doi('doi:10.1234%2FABC'), '10.1234/abc')

    def test_missing_doi(self):
        self.assertEqual(r.doi(None), '')

    def test_partial_date(self):
        record = r.normalise({'title': ['Synthetic fixture'], 'issued': {'date-parts': [[2026, 8]]}})
        self.assertEqual(record['dates']['issued'], '2026-08')
        self.assertEqual(record['evidence_level'], 'metadata_only')

    def test_online_print_separate(self):
        record = r.normalise({'published-online': {'date-parts': [[2026, 8, 1]]},
                              'published-print': {'date-parts': [[2026, 10]]}})
        self.assertEqual(record['dates']['published-online'], '2026-08-01')
        self.assertEqual(record['dates']['published-print'], '2026-10')

    def test_path_traversal(self):
        with self.assertRaises(ValueError): r.safe_path('/tmp/work', '../secrets')

    def test_absolute_path(self):
        with self.assertRaises(ValueError): r.safe_path('/tmp/work', '/etc/passwd')

    def test_windows_separator(self):
        with self.assertRaises(ValueError): r.safe_path('/tmp/work', '..\\secret')

    @unittest.skipUnless(HAS_SYMLINK, "platform cannot create usable symlinks")
    def test_symlink_escape(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t) / 'root'; root.mkdir()
            (root / 'outside').symlink_to(Path(t), target_is_directory=True)
            with self.assertRaises(ValueError): r.safe_path(root, 'outside/secret')

    def test_symlink_escape_when_link_not_creatable(self):
        """Even without symlink support, traversal out of the root must fail."""
        with tempfile.TemporaryDirectory() as t:
            root = Path(t) / 'root'; root.mkdir()
            with self.assertRaises(ValueError): r.safe_path(root, '../secret')
            with self.assertRaises(ValueError): r.safe_path(root, 'a/../../secret')

    def test_checkpoint_transitive_invalidation(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t) / 'p'
            r.init_project(root, r.ROOT / 'domains/example-domain/domain.json', 'original')
            for name in ['inputs/data.csv', 'analysis/result.csv', 'manuscript/result.md']:
                (root / name).write_text('fixture', encoding='utf8')
            r.checkpoint(root, 'analysis', ['inputs/data.csv'], ['analysis/result.csv'])
            r.checkpoint(root, 'writing', ['analysis/result.csv'], ['manuscript/result.md'])
            self.assertEqual(r.check_project(root)['status'], 'hashes_current')
            (root / 'inputs/data.csv').write_text('changed', encoding='utf8')
            report = r.check_project(root)
            self.assertEqual(report['status'], 'stale')
            self.assertEqual({x['stage'] for x in report['invalidated']}, {'analysis', 'writing'})

    def test_init_no_overwrite(self):
        with tempfile.TemporaryDirectory() as t:
            r.init_project(t, r.ROOT / 'domains/example-domain/domain.json', 'review')
            with self.assertRaises(FileExistsError):
                r.init_project(t, r.ROOT / 'domains/example-domain/domain.json', 'review')

    def test_overlap(self):
        text = 'This synthetic sentence contains enough distinct words to demonstrate copied span flagging only'
        self.assertTrue(r.overlap(text, text))
        self.assertFalse(r.overlap('different', text))

    def test_registry_pins(self):
        sources = r.read(r.ROOT / 'config/upstream.lock.json')['sources']
        self.assertEqual(len(sources), 5)
        for source in sources:
            self.assertRegex(source['commit'], r'^[a-f0-9]{40}$')
            self.assertNotIn(source['status'], ['installed', 'verified'])

    def test_domain_not_event_hardcoded(self):
        domain = r.read(r.ROOT / 'domains/example-domain/domain.json')
        self.assertTrue(all(x is None for x in domain['project_parameters'].values()))
        self.assertEqual(domain['learned_capability_cards'], [])


class SearchTests(unittest.TestCase):
    def test_paging_and_dedup(self):
        replies = iter([{'message': {'items': [{'DOI': '10.1/A'}, {'DOI': '10.1/B'}], 'next-cursor': 'opaque'}},
                        {'message': {'items': [{'DOI': '10.1/A'}]}}])
        with tempfile.TemporaryDirectory() as t:
            result = r.search('fixture', '2026-08-01', '2026-09-01', Path(t) / 'search',
                              pages=2, rows=2, fetch=lambda _: next(replies))
            self.assertEqual(len(result['records']), 2)
            self.assertTrue(result['provider_query_exhausted'])
            self.assertFalse(result['truncated'])
            self.assertEqual(len(result['requests']), 2)

    def test_pagination_cap_not_exhaustive(self):
        with tempfile.TemporaryDirectory() as t:
            result = r.search('fixture', '2026-08-01', '2026-09-01', Path(t) / 'search', pages=1, rows=1,
                fetch=lambda _: {'message': {'items': [{'DOI': '10.1/A'}], 'next-cursor': 'next'}})
            self.assertTrue(result['truncated'])
            self.assertFalse(result['provider_query_exhausted'])

    def test_empty_distinct_from_failed(self):
        with tempfile.TemporaryDirectory() as t:
            result = r.search('fixture', '2026-08-01', '2026-09-01', Path(t) / 'search',
                              fetch=lambda _: {'message': {'items': []}})
            self.assertEqual(result['status'], 'ok')
            self.assertEqual(result['records'], [])

    def test_error_persists(self):
        with tempfile.TemporaryDirectory() as t:
            out = Path(t) / 'search'
            def fail(_): raise urllib.error.URLError('synthetic offline')
            with self.assertRaises(urllib.error.URLError):
                r.search('fixture', '2026-08-01', '2026-09-01', out, fetch=fail)
            self.assertEqual(r.read(out / 'search.json')['status'], 'error')

    def test_indexed_query(self):
        seen = []
        with tempfile.TemporaryDirectory() as t:
            def fetch(url):
                seen.append(url)
                return {'message': {'items': []}}
            r.search('fixture', '2026-08-01', '2026-09-01', Path(t) / 's', mode='indexed', fetch=fetch)
        self.assertIn('from-index-date', seen[0])

    def test_invalid_date_range(self):
        with self.assertRaises(ValueError):
            r.search('fixture', '2026-09-01', '2026-08-01', 'unused')

    def test_search_never_overwrites(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(FileExistsError): r.search('x', '2026-01-01', '2026-02-01', t)


class SearchProgressTests(unittest.TestCase):
    def round(self, number, matrix_changing, gaps=None):
        return {'round': number, 'queries': [f'fixture-{number}'],
                'new_deduped_records': matrix_changing + 2,
                'admitted_sources': matrix_changing,
                'matrix_changing_sources': matrix_changing,
                'open_required_gaps': gaps or []}

    def test_stops_after_configured_dry_streak(self):
        rounds = [self.round(0, 5), self.round(1, 1), self.round(2, 0)]
        out = r.assess_search_progress(rounds, budget=6, patience=2, min_new=2)
        self.assertEqual(out['decision'], 'STOP_SATURATED')
        self.assertEqual(out['dry_streak'], 2)
        self.assertEqual(out['trajectory'], [5, 1, 0])
        self.assertFalse(out['exhaustiveness_claim_allowed'])

    def test_required_gap_prevents_false_saturation(self):
        rounds = [self.round(0, 1), self.round(1, 0, ['undercovered population'])]
        out = r.assess_search_progress(rounds, budget=4, patience=2, min_new=2)
        self.assertEqual(out['decision'], 'CONTINUE_FOR_COVERAGE')

    def test_budget_with_required_gap_needs_human_decision(self):
        rounds = [self.round(0, 3), self.round(1, 0, ['missing comparator'])]
        out = r.assess_search_progress(rounds, budget=2, patience=2, min_new=2)
        self.assertEqual(out['decision'], 'AUTHOR_ACTION_REQUIRED')

    def test_invalid_ledger_is_rejected(self):
        bad = [self.round(0, 1)]
        bad[0]['queries'] = []
        with self.assertRaises(ValueError):
            r.assess_search_progress(bad, budget=3, patience=2, min_new=1)

    def test_cli_writes_an_auditable_decision(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            ledger = root / 'rounds.json'
            output = root / 'progress.json'
            r.write(ledger, {'rounds': [self.round(0, 4), self.round(1, 0)]})
            code = r.main(['search-progress', '--ledger', str(ledger), '--out', str(output),
                           '--budget', '5', '--patience', '1', '--min-new', '2'])
            self.assertEqual(code, 0)
            self.assertEqual(r.read(output)['decision'], 'STOP_SATURATED')


class SeedCoverageTests(unittest.TestCase):
    def payload(self):
        return {
            'required_chain_directions': ['backward', 'forward'],
            'seeds': [
                {'id': 'S1', 'identity_status': 'VERIFIED', 'search_status': 'FOUND',
                 'locator': 'doi:10.0000/synthetic'},
            ],
            'citation_chains': [
                {'seed_id': 'S1', 'direction': 'backward', 'status': 'COMPLETE',
                 'new_deduped_records': 3, 'source': 'synthetic fixture'},
                {'seed_id': 'S1', 'direction': 'forward', 'status': 'ZERO_HITS',
                 'new_deduped_records': 0, 'source': 'synthetic fixture'},
            ],
        }

    def test_verified_seed_and_completed_channels_pass(self):
        out = r.assess_seed_coverage(self.payload())
        self.assertEqual(out['decision'], 'PASS')
        self.assertEqual(out['zero_hit_channels'], [{'seed_id': 'S1', 'direction': 'forward'}])
        self.assertEqual(out['failed_channels'], [])
        self.assertFalse(out['exhaustiveness_claim_allowed'])

    def test_missing_verified_seed_is_a_search_gap(self):
        payload = self.payload()
        payload['seeds'][0]['search_status'] = 'NOT_FOUND'
        out = r.assess_seed_coverage(payload)
        self.assertEqual(out['decision'], 'SEARCH_GAP')
        self.assertEqual(out['missing_verified_seeds'], ['S1'])

    def test_identity_problem_is_not_counted_as_coverage(self):
        payload = self.payload()
        payload['seeds'][0]['identity_status'] = 'UNRESOLVED'
        out = r.assess_seed_coverage(payload)
        self.assertEqual(out['decision'], 'IDENTITY_REVIEW_REQUIRED')
        self.assertEqual(out['identity_review_seeds'], ['S1'])

    def test_failed_channel_is_distinct_from_zero_hits(self):
        payload = self.payload()
        payload['citation_chains'][0]['status'] = 'FAILED'
        payload['citation_chains'][0]['new_deduped_records'] = 0
        out = r.assess_seed_coverage(payload)
        self.assertEqual(out['decision'], 'AUTHOR_ACTION_REQUIRED')
        self.assertEqual(out['failed_channels'], [{'seed_id': 'S1', 'direction': 'backward'}])
        self.assertEqual(out['zero_hit_channels'], [{'seed_id': 'S1', 'direction': 'forward'}])

    def test_missing_required_direction_continues_search(self):
        payload = self.payload()
        payload['citation_chains'].pop()
        out = r.assess_seed_coverage(payload)
        self.assertEqual(out['decision'], 'CONTINUE')
        self.assertEqual(out['missing_required_channels'], [{'seed_id': 'S1', 'direction': 'forward'}])

    def test_invalid_and_duplicate_records_are_rejected(self):
        payload = self.payload()
        payload['seeds'].append(copy.deepcopy(payload['seeds'][0]))
        with self.assertRaises(ValueError):
            r.assess_seed_coverage(payload)

    def test_cli_writes_a_new_audit_file(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            ledger = root / 'seed-ledger.json'
            output = root / 'seed-audit.json'
            r.write(ledger, self.payload())
            code = r.main(['seed-coverage', '--ledger', str(ledger), '--out', str(output)])
            self.assertEqual(code, 0)
            self.assertEqual(r.read(output)['decision'], 'PASS')
            self.assertEqual(r.read(output)['scope'], 'seed_and_declared_citation_chain_audit')


class ScreeningRoundTests(unittest.TestCase):
    def payload(self):
        codebook_hash = 'a' * 64
        source_manifest_hash = 'b' * 64
        source_hash = 'c' * 64
        ballot = lambda reviewer: {
            'reviewer_id': reviewer,
            'round_id': 'screen-v2',
            'codebook_sha256': codebook_hash,
            'source_sha256': source_hash,
            'decision': 'INCLUDE',
            'rationale': 'The full-text fixture satisfies the declared population and design rules.',
            'evidence_locator': 'PDF p.4, Methods',
            'review_mode': 'independent',
        }
        return {
            'schema_version': '1.0',
            'protocol_id': 'synthetic-review',
            'codebook': {
                'version': '2.0',
                'sha256': codebook_hash,
                'origin': 'human_led',
                'provided_by': 'Synthetic review team',
            },
            'round': {
                'id': 'screen-v2',
                'mode': 'independent',
                'minimum_reviewers': 2,
                'source_manifest_sha256': source_manifest_hash,
            },
            'records': [{
                'record_id': 'R1',
                'source_sha256': source_hash,
                'ballots': [ballot('reviewer-a'), ballot('reviewer-b')],
            }],
            'release': {
                'human_authorized': True,
                'authorized_by': 'Synthetic adjudicator',
                'authorized_at': '2026-10-08T00:00:00Z',
                'rationale': 'Synthetic contract fixture only.',
                'round_id': 'screen-v2',
                'codebook_sha256': codebook_hash,
                'source_manifest_sha256': source_manifest_hash,
            },
        }

    def test_bound_independent_concordance_and_human_release_pass(self):
        out = r.assess_screening_round(self.payload())
        self.assertEqual(out['decision'], 'PASS')
        self.assertEqual(out['records'][0]['state'], 'CONCORDANT')
        self.assertEqual(out['counts']['included'], 1)
        self.assertFalse(out['scientific_correctness_implied'])

    def test_disagreement_requires_adjudication_not_majority_vote(self):
        payload = self.payload()
        payload['records'][0]['ballots'][1].update(
            decision='EXCLUDE', primary_reason_code='WRONG_DESIGN')
        payload.pop('release')
        out = r.assess_screening_round(payload)
        self.assertEqual(out['decision'], 'AUTHOR_ACTION_REQUIRED')
        self.assertEqual(out['records'][0]['state'], 'ADJUDICATION_REQUIRED')

        payload['records'][0]['adjudication'] = {
            'decision': 'EXCLUDE',
            'primary_reason_code': 'WRONG_DESIGN',
            'rationale': 'The full text uses an ineligible design.',
            'evidence_locator': 'PDF p.4, Methods',
            'human_authorized': True,
            'authorized_by': 'Synthetic adjudicator',
            'round_id': payload['round']['id'],
            'codebook_sha256': payload['codebook']['sha256'],
            'source_sha256': payload['records'][0]['source_sha256'],
        }
        payload['release'] = self.payload()['release']
        out = r.assess_screening_round(payload)
        self.assertEqual(out['decision'], 'PASS')
        self.assertEqual(out['records'][0]['state'], 'ADJUDICATED')
        self.assertEqual(out['counts']['excluded'], 1)

    def test_source_or_codebook_drift_blocks_stale_ballots(self):
        payload = self.payload()
        payload['records'][0]['ballots'][0]['source_sha256'] = 'd' * 64
        out = r.assess_screening_round(payload)
        self.assertEqual(out['decision'], 'BLOCKED')
        self.assertEqual(out['records'][0]['state'], 'STALE_RESCREEN_REQUIRED')

    def test_coverage_is_project_defined_and_incomplete_round_continues(self):
        payload = self.payload()
        payload['records'][0]['ballots'].pop()
        payload.pop('release')
        out = r.assess_screening_round(payload)
        self.assertEqual(out['decision'], 'CONTINUE')
        self.assertEqual(out['records'][0]['state'], 'PENDING_COVERAGE')

    def test_exclusion_needs_one_primary_reason_and_source_location(self):
        payload = self.payload()
        for ballot in payload['records'][0]['ballots']:
            ballot['decision'] = 'EXCLUDE'
            ballot.pop('evidence_locator')
        with self.assertRaises(ValueError):
            r.assess_screening_round(payload)

        payload = self.payload()
        for ballot in payload['records'][0]['ballots']:
            ballot['decision'] = 'EXCLUDE'
        with self.assertRaises(ValueError):
            r.assess_screening_round(payload)

    def test_release_is_bound_and_timestamped(self):
        payload = self.payload()
        payload['release']['source_manifest_sha256'] = 'd' * 64
        out = r.assess_screening_round(payload)
        self.assertEqual(out['decision'], 'BLOCKED')
        self.assertTrue(out['release_errors'])

        payload = self.payload()
        payload['release']['authorized_at'] = '2026-10-08T00:00:00'
        out = r.assess_screening_round(payload)
        self.assertEqual(out['decision'], 'BLOCKED')
        self.assertTrue(any('timezone' in item for item in out['release_errors']))

    def test_cli_preserves_prior_screening_audit(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            ledger = root / 'screening.json'
            output = root / 'screening-audit.json'
            r.write(ledger, self.payload())
            self.assertEqual(r.main(['screening-round', '--ledger', str(ledger),
                                     '--out', str(output)]), 0)
            first = output.read_bytes()
            self.assertEqual(r.main(['screening-round', '--ledger', str(ledger),
                                     '--out', str(output)]), 2)
            self.assertEqual(output.read_bytes(), first)


class ChangeTests(unittest.TestCase):
    def setUp(self):
        self.change = {'id': 'C', 'location': 'Discussion', 'before': 'old', 'after': 'new',
                       'contribution': 'comparison', 'reason': 'substantive difference', 'evidence_ids': ['E'],
                       'claim_level': 'inference', 'decision': 'accept', 'semantic_review': 'passed'}
        self.evidence = {'id': 'E', 'source': 'synthetic fixture', 'locator': 'p.2', 'evidence_level': 'full_text'}

    def test_valid_contract_not_science_claim(self):
        self.assertEqual(r.validate_changes([self.change], [self.evidence])['status'], 'contract_pass')

    def test_abstract_not_fulltext(self):
        self.evidence['evidence_level'] = 'abstract_only'
        self.assertEqual(r.validate_changes([self.change], [self.evidence])['status'], 'fail')

    def test_metadata_not_mechanism(self):
        self.evidence['evidence_level'] = 'metadata_only'
        self.assertEqual(r.validate_changes([self.change], [self.evidence])['status'], 'fail')

    def test_metadata_can_support_identity(self):
        self.evidence['evidence_level'] = 'metadata_only'; self.change['claim_level'] = 'bibliographic'
        self.assertEqual(r.validate_changes([self.change], [self.evidence])['status'], 'contract_pass')

    def test_boilerplate_category_rejected(self):
        self.change['contribution'] = 'generic_defensive_limitations'
        self.assertEqual(r.validate_changes([self.change], [self.evidence])['status'], 'fail')

    def test_semantic_review_required(self):
        self.change['semantic_review'] = 'not_done'
        self.assertEqual(r.validate_changes([self.change], [self.evidence])['status'], 'fail')

    def test_duplicate_evidence_ids(self):
        with self.assertRaises(ValueError): r.validate_changes([self.change], [self.evidence, self.evidence])


class JournalTests(unittest.TestCase):
    def cards(self):
        cards = []
        for i in range(4):
            cards.append({'id': str(i), 'journal': 'Fixture journal', 'article_type': 'research-article',
                          'author_group': 'team-' + str(i), 'split': 'train' if i < 3 else 'heldout',
                          'source': 'synthetic fixture', 'sha256': 'a' * 64, 'metadata_verified': True,
                          'full_text_read': True, 'visual_checked': True,
                          'patterns': [{'id': 'p', 'description': 'synthetic pattern', 'locator': 'p.2'}]})
        return cards

    def compile(self, cards):
        return r.compile_journal(cards, 'Fixture journal', 'research-article', minimum=3)

    def test_draft_never_validated(self):
        out = self.compile(self.cards())
        self.assertEqual(out['status'], 'draft_needs_heldout_evaluation')
        self.assertEqual(out['rules'][0]['support_papers'], 3)
        self.assertEqual(out['rules'][0]['train_denominator'], 3)

    def test_group_leakage(self):
        cards = self.cards(); cards[3]['author_group'] = cards[0]['author_group']
        with self.assertRaises(ValueError): self.compile(cards)

    def test_mixed_journals(self):
        cards = self.cards(); cards[1]['journal'] = 'Other journal'
        with self.assertRaises(ValueError): self.compile(cards)

    def test_unread_card(self):
        cards = self.cards(); cards[0]['full_text_read'] = False
        with self.assertRaises(ValueError): self.compile(cards)

    def test_no_visual_check(self):
        cards = self.cards(); cards[0]['visual_checked'] = False
        with self.assertRaises(ValueError): self.compile(cards)

    def test_duplicate_versions(self):
        cards = self.cards(); cards[2]['id'] = cards[1]['id']
        with self.assertRaises(ValueError): self.compile(cards)

    def test_missing_pattern_location(self):
        cards = self.cards(); cards[0]['patterns'][0].pop('locator')
        with self.assertRaises(ValueError): self.compile(cards)

    def test_conflicting_pattern_definition(self):
        cards = self.cards(); cards[0]['patterns'][0]['description'] = 'different meaning'
        with self.assertRaises(ValueError): self.compile(cards)

    def test_no_heldout(self):
        with self.assertRaises(ValueError): self.compile(self.cards()[:3])


class CorpusAndArchiveTests(unittest.TestCase):
    def test_url_requires_https(self):
        with self.assertRaises(ValueError): corpus.public_url('http://example.com/x.pdf', {'example.com'})

    def test_url_requires_allowlist(self):
        with self.assertRaises(ValueError): corpus.public_url('https://example.com/x.pdf', set())

    def test_private_ip(self):
        with patch('corpus.socket.getaddrinfo', return_value=[(2, 1, 6, '', ('127.0.0.1', 443))]):
            with self.assertRaises(ValueError): corpus.public_url('https://example.com/x.pdf', {'example.com'})

    def test_zip_traversal(self):
        b = io.BytesIO()
        with zipfile.ZipFile(b, 'w') as z: z.writestr('../escape', 'bad')
        with zipfile.ZipFile(b) as z:
            with self.assertRaises(ValueError): upstream.check_members(z)

    def test_zip_symlink(self):
        b = io.BytesIO()
        with zipfile.ZipFile(b, 'w') as z:
            entry = zipfile.ZipInfo('link'); entry.external_attr = (stat.S_IFLNK | 0o777) << 16
            z.writestr(entry, '/etc/passwd')
        with zipfile.ZipFile(b) as z:
            with self.assertRaises(ValueError): upstream.check_members(z)

    def test_blank_pdf_not_read(self):
        from pypdf import PdfWriter
        with tempfile.TemporaryDirectory() as t:
            root = Path(t); writer = PdfWriter(); writer.add_blank_page(width=300, height=300)
            with (root / 'blank.pdf').open('wb') as f: writer.write(f)
            r.write(root / 'manifest.json', [{'id': 'blank', 'path': 'blank.pdf'}])
            report = corpus.ingest(root / 'manifest.json', root / 'out')
            self.assertEqual(report[0]['status'], 'failed')

    def test_corrupt_pdf_failure_is_visible(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t); (root / 'bad.pdf').write_text('not a PDF')
            r.write(root / 'manifest.json', [{'id': 'bad', 'path': 'bad.pdf'}])
            self.assertEqual(corpus.ingest(root / 'manifest.json', root / 'out')[0]['status'], 'failed')

    def test_source_zip_is_repeatable(self):
        with tempfile.TemporaryDirectory() as t:
            first = r.package(Path(t) / 'a.zip'); second = r.package(Path(t) / 'b.zip')
            self.assertEqual(first['sha256'], second['sha256'])
            with zipfile.ZipFile(first['file']) as z:
                self.assertIn('research-mother/SKILL.md', z.namelist())
                self.assertFalse(any('/runs/' in n or '/private-corpus/' in n or n.endswith('.pdf') for n in z.namelist()))


if __name__ == '__main__':
    unittest.main()

"""Shipped navigation must point at installed app pages and record types."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'whatsapp_messaging' / 'whatsapp_messaging'


class TestNavigation(unittest.TestCase):
    def test_all_shipped_shortcuts_and_sidebar_links_resolve(self):
        registries = {kind: {json.loads(file.read_text())['name'] for file in (ROOT / folder).glob('*/*.json')}
            for kind, folder in [('DocType', 'doctype'), ('Page', 'page'), ('Workspace', 'workspace')]}
        for folder in ('workspace', 'sidebar'):
            for file in (ROOT / folder).glob('*/*.json'):
                doc = json.loads(file.read_text())
                for row in doc.get('shortcuts', []) + doc.get('items', []):
                    kind = row.get('link_type') if folder == 'sidebar' else row.get('type')
                    if kind in registries and row.get('link_to'):
                        self.assertIn(row['link_to'], registries[kind], (file.name, row.get('label')))
                labels = {row['label'] for row in doc.get('shortcuts', [])}
                for block in json.loads(doc.get('content') or '[]'):
                    if block.get('type') == 'shortcut':
                        self.assertIn(block['data']['shortcut_name'], labels, file.name)

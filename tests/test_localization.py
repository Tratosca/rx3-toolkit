# SPDX-License-Identifier: MPL-2.0
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from app.localization import Message, LocalizedError, catalogs, translate, wire
from app.ui.bridge import Bridge
from app.runtime.metadata import module_messages, categories
from app.runtime.build import discover_patches
from app.runtime.scaffold import scaffold

ROOT = pathlib.Path(__file__).resolve().parents[1]


def leaves(value):
    return list(value.values()) if isinstance(value, dict) else [value]


def parameters(value):
    return set(re.findall(r"\{(\w+)\}", " ".join(leaves(value))))


class LocalizationTests(unittest.TestCase):
    def test_catalog_keys_and_parameters_match(self):
        english = catalogs()['en']
        for locale, catalog in catalogs().items():
            self.assertEqual(set(catalog), set(english), locale)
            for key, value in catalog.items():
                self.assertTrue(all(isinstance(item, str) and item for item in leaves(value)), key)
                self.assertEqual(parameters(value), parameters(english[key]), f'{locale}:{key}')
                if isinstance(value, dict):
                    self.assertIn('other', value, key)
            # Duplicate JSON keys would silently hide a translator's work.
            path = ROOT / 'app/localization' / f'{locale}.json'
            def unique(pairs):
                result = {}
                for key, value in pairs:
                    self.assertNotIn(key, result)
                    result[key] = value
                return result
            json.loads(path.read_text(), object_pairs_hook=unique)

    def test_literal_ui_keys_exist(self):
        sources = list((ROOT / 'app/ui/web').glob('*.js')) + list((ROOT / 'app/ui/web').glob('*.html'))
        for source in sources:
            for key in re.findall(r'(?:\bt\(|data-t(?:-label|-title|-placeholder)?=)"([\w.-]+)"', source.read_text()):
                if not key.endswith('.'):
                    self.assertIn(key, catalogs()['en'], f'{source.name}:{key}')

    def test_modules_have_localized_metadata(self):
        shared = json.loads((ROOT / 'app/localization/en.json').read_text())
        self.assertFalse(any(key.startswith(('module.', 'modules.category.', 'keyshift.', 'keyMatch.', 'browseColumn.')) for key in shared))
        definitions = categories(ROOT)
        for manifest in (ROOT / 'mod/modules').glob('*/manifest.json'):
            data = json.loads(manifest.read_text())
            category = data.get('category')
            if data.get('selectable', True):
                self.assertIsInstance(category, str)
                self.assertIn(category, definitions)
            self.assertNotEqual(category, 'performance')
            for locale, messages in module_messages(data).items():
                for key, value in messages.items():
                    self.assertEqual(catalogs()[locale][key], value)

    def test_packaged_module_text_and_new_category(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = pathlib.Path(directory)
            shutil.copytree(ROOT / 'app/localization', bundle / 'localization', ignore=shutil.ignore_patterns('__pycache__'))
            modules = bundle / 'resources/mod/modules'
            scaffold(bundle / 'resources', 'test-new-category', 'New category', ['1.19'], False, 'test-new-category')
            path = modules / 'test-new-category/manifest.json'
            data = json.loads(path.read_text())
            data['name']['fr'] = 'Module de test'
            data['category'] = 'test-new-category'
            registry = json.loads((ROOT / 'mod/categories.json').read_text())
            registry.append({'id': 'test-new-category', 'order': 15, 'name': {'en': 'New category', 'fr': 'Nouvelle categorie'}})
            (bundle / 'resources/mod/categories.json').write_text(json.dumps(registry))
            path.write_text(json.dumps(data))
            definitions = discover_patches(bundle / 'resources', '1.19')
            module = next(item for item in definitions if item.patch_id == data['id'])
            self.assertEqual(module.name, 'New category')
            self.assertEqual(module.category_ui['name']['fr'], 'Nouvelle categorie')
            for source in (ROOT / 'mod/modules').glob('*/manifest.json'):
                target = modules / source.parent.name / source.name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
            catalogs.cache_clear()
            try:
                with patch.object(sys, '_MEIPASS', str(bundle), create=True):
                    self.assertEqual(translate('module.test-new-category.name', 'fr'), 'Module de test')
                    self.assertEqual(translate('modules.category.test-new-category', 'fr'), 'Nouvelle categorie')
                    self.assertEqual(translate('module.keyshift.name', 'en'), json.loads((modules / 'keyshift/manifest.json').read_text())['name']['en'])
            finally:
                catalogs.cache_clear()

    def test_fallback_plural_and_structured_messages(self):
        self.assertEqual(translate('drive.trackCount', 'fr-FR', count=1), '1 morceau')
        self.assertEqual(translate('drive.trackCount', 'fr', count=2), '2 morceaux')
        self.assertEqual(translate('drive.trackCount', 'de', count=0), '0 tracks')
        value = Message('job.sound', done=2, count=8)
        self.assertEqual(str(value), 'Preparing sample 2 of 8')
        self.assertEqual(wire(value), {'key':'job.sound', 'params':{'done':2, 'count':8}})
        response = Bridge().mod_build('1.19', [], '', '')
        self.assertFalse(response['ok'])
        self.assertEqual(response['errorMessage']['key'], 'error.selection')

    @unittest.skipUnless(shutil.which('node'), 'Node checks browser localization')
    def test_browser_locale_switching_and_fallback(self):
        script = r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const data={en:JSON.parse(fs.readFileSync('app/localization/en.json')),fr:JSON.parse(fs.readFileSync('app/localization/fr.json'))};
let saved='fr-CA';
const window={pywebview:{api:{async localization_catalogs(){return {ok:true,value:data}},localization_language(){}}},dispatchEvent(){}};
vm.runInNewContext(fs.readFileSync('app/ui/web/i18n.js','utf8'),{window,Intl,navigator:{language:'en'},document:{documentElement:{},querySelectorAll(){return []}},CustomEvent:class {},localStorage:{getItem(){return saved},setItem(k,v){saved=v}}});
(async()=>{await window.i18n.load();const i=window.i18n;
assert.equal(i.current(),'fr');assert.equal(i.t('drive.trackCount',{count:2}),'2 morceaux');
assert.equal(i.message({key:'job.sound',params:{done:2,count:8}}),'Préparation du sample 2 sur 8');
assert.equal(i.number(1.5),'1,5');i.setLanguage('en-GB');
assert.equal(i.t('drive.trackCount',{count:1}),'1 track');assert.equal(i.number(1.5),'1.5');
i.setLanguage('zz');assert.equal(i.current(),'en');assert.equal(i.t('nonexistent'),'nonexistent');
assert.equal(i.missing().length,0);
delete data.fr['drive.trackCount'];i.setLanguage('fr');
assert.equal(i.t('drive.trackCount',{count:0}),'0 tracks');
})().catch(e=>{console.error(e);process.exitCode=1});
'''
        result = subprocess.run(['node', '-e', script], cwd=ROOT, capture_output=True,
                                text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

# SPDX-License-Identifier: MPL-2.0
import copy
import pathlib
import tempfile
import unittest
from unittest.mock import patch
from app.samples import drafts
from app.services import samples
from test_sample_banks import tone

class DraftTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=pathlib.Path(temp.name);self.drive=self.root/'usb';self.drive.mkdir()
        patcher=patch.object(drafts,'root',return_value=self.root/'local');patcher.start();self.addCleanup(patcher.stop)
        source=tone(self.root/'sound.wav');self.asset=drafts.asset(source);source.unlink()
    def entry(self,name,identifier):
        pads=[dict(source=None,audioPath=None,keep=False,present=False,colour='#FFFFFF',name='',mode=0,gain=100,start=0,seconds=0) for _ in range(8)]
        pads[0].update(source=self.asset,present=True,seconds=.25)
        return dict(id=identifier,value=dict(name=name,pads=pads,volume=50,shiftSilence=False,onDrive=False,settingsOk=True),saved=None)
    def project(self):
        return dict(version=1,entries=[self.entry('One','a'),self.entry('Two','b')],active='b',savedActive=None,deleted=[],selected='a')
    def test_local_banks_survive_restart_and_source_removal_without_usb_writes(self):
        project=self.project();drafts.store(self.drive,project)
        self.assertEqual(list(self.drive.iterdir()),[])
        self.assertEqual(drafts.load(self.drive)['project'],project)
        self.assertTrue(pathlib.Path(self.asset).is_file())
        self.assertEqual(drafts.asset(self.asset),self.asset)
        other=self.root/'other';other.mkdir();self.assertIsNone(drafts.load(other)['project'])
    def test_publish_all_banks_active_rename_and_delete_only_at_export(self):
        project=self.project();drafts.store(self.drive,project);synced=drafts.push(self.drive,project)
        self.assertEqual(samples.read(self.drive).names,('One','Two'))
        self.assertEqual(samples.read(self.drive).active,'Two')
        self.assertEqual(drafts.load(self.drive)['project'],synced)
        for entry in synced['entries']:self.assertEqual(entry['value'],entry['saved'])
        synced['entries'][0]['value']['name']='Renamed'
        synced['deleted']=['Two'];synced['entries'].pop();synced['active']='a'
        drafts.store(self.drive,synced)
        self.assertEqual(samples.read(self.drive).names,('One','Two'))
        drafts.push(self.drive,synced)
        self.assertEqual(samples.read(self.drive).names,('Renamed',));self.assertEqual(samples.read(self.drive).active,'Renamed')
    def test_invalid_names_prevent_partial_export(self):
        project=self.project();project['entries'][1]['value']['name']='../escape'
        drafts.store(self.drive,project) # incomplete typing is a valid local draft
        with self.assertRaises(Exception):drafts.push(self.drive,project)
        self.assertEqual(list(self.drive.iterdir()),[])
    def test_export_failure_keeps_unsent_local_project(self):
        project=self.project();drafts.store(self.drive,project)
        with patch.object(samples,'save',side_effect=OSError('removed USB')):
            with self.assertRaises(OSError):drafts.push(self.drive,project)
        self.assertEqual(drafts.load(self.drive)['project'],project)
    def test_failed_local_save_keeps_previous_revision(self):
        project=self.project();drafts.store(self.drive,project)
        changed=copy.deepcopy(project);changed['entries'][0]['value']['name']='Change'
        with patch.object(drafts.os,'fsync',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):drafts.store(self.drive,changed)
        self.assertEqual(drafts.load(self.drive)['project'],project)
    def test_newer_local_edits_are_not_erased_by_export(self):
        project=self.project();drafts.store(self.drive,project)
        newer=copy.deepcopy(project);newer['entries'][0]['value']['name']='Later'
        drafts.store(self.drive,newer);drafts.push(self.drive,project)
        self.assertEqual(drafts.load(self.drive)['project'],newer)
    def test_loading_usb_copies_audio_locally(self):
        project=self.project();drafts.push(self.drive,project)
        drafts.project_file(self.drive).unlink()
        answer=drafts.load(self.drive)
        path=pathlib.Path(answer['banks'][0]['pads'][0]['path'])
        self.assertTrue(path.is_relative_to((self.root/'local').resolve()))
        samples.remove(self.drive,'One');self.assertTrue(path.is_file())

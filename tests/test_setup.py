import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from context_engine.setup import initialize

ROOT=Path(__file__).resolve().parents[1]


def read_config(path):
    servers={}; current=None
    for line in path.read_text().splitlines():
        if line.startswith('[mcp_servers.'):
            current=line[len('[mcp_servers.'):-1];servers[current]={}
        elif ' = ' in line:
            k,v=line.split(' = ',1); servers[current][k]=json.loads(v)
    return servers


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='context setup ')
        self.root=Path(self.tmp.name).resolve()
        self.team=self.root/'team code'; self.team.mkdir()
        self.personal=self.root/'personal notes'; self.personal.mkdir()
        (self.team/'tasks.py').write_text('TEAM_SENTINEL = "queued"\n')
        (self.personal/'memory.md').write_text('PERSONAL_SENTINEL\n')
        self.output=self.root/'generated'

    def tearDown(self):self.tmp.cleanup()

    def setup(self, **kwargs):
        return initialize(self.output,'team','feature',['api='+str(self.team)],['scratch='+str(self.personal)],**kwargs)

    def test_generated_dual_servers_tasks_and_isolation(self):
        result=self.setup(); self.assertEqual(result,self.setup())
        self.assertFalse((self.output/'state').exists())
        config=read_config(self.output/'.codex/config.toml')
        self.assertEqual(set(config),{'context_engine_team','context_engine_personal'})
        tasks=json.loads((self.output/'.vscode/tasks.json').read_text())['tasks']
        self.assertEqual(len(tasks),8)
        self.assertEqual(len([t for t in tasks if t.get('runOptions',{}).get('runOn')=='folderOpen']),2)
        for scope in ['team','personal']:
            t=next(t for t in tasks if t['label']=='Context Engine '+scope+': index')
            subprocess.run([t['command']]+t['args'],cwd=t['options']['cwd'],capture_output=True,check=True)
            launch=config['context_engine_'+scope]
            requests=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{}},
                {'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'index_status','arguments':{}}},
                {'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'search_context','arguments':{'query':'PERSONAL_SENTINEL','token_budget':8000}}}]
            r=subprocess.run([launch['command']]+launch['args'],cwd=launch['cwd'],input='\n'.join(map(json.dumps,requests))+'\n',text=True,capture_output=True,check=True)
            responses=[json.loads(line) for line in r.stdout.splitlines()]
            status=json.loads(responses[1]['result']['content'][0]['text'])
            self.assertEqual(set(status['coverage']),{'api'} if scope=='team' else {'scratch'})
            found=json.loads(responses[2]['result']['content'][0]['text'])['items']
            self.assertEqual(bool(found),scope=='personal')
        self.assertIn('personal evidence',(self.output/'AGENTS.md').read_text())

    def test_cli_semantic_setup_is_offline_and_captures_interpreter(self):
        r=subprocess.run([sys.executable,'-m','context_engine','init','--environment','demo','--repo','api='+str(self.team),
             '--semantic','--output',str(self.output)],cwd=ROOT,text=True,capture_output=True,check=True)
        self.assertIn('workspace_file',json.loads(r.stdout))
        self.assertFalse((self.output/'models').exists())
        self.assertFalse((self.output/'state').exists())
        config=read_config(self.output/'.codex/config.toml')
        self.assertEqual(config['context_engine_team']['command'],str(Path(sys.executable).absolute()))
        self.assertEqual(json.loads((self.output/'team.json').read_text())['embeddings']['cache_folder'],str(self.output/'models'))
        self.assertNotIn('context_engine_personal',config)
        prefix=subprocess.run([config['context_engine_team']['command'],'-c','import sys; print(sys.prefix)'],capture_output=True,text=True,check=True).stdout.strip()
        self.assertEqual(prefix,sys.prefix)

    def test_invalid_or_overlapping_sources_write_nothing(self):
        for repos,personal in [(['invalid'],[]),(['a='+str(self.root/'missing')],[]),
                               (['a='+str(self.team)],['p='+str(self.team)]),
                               (['a='+str(self.root)],['p='+str(self.personal)]),
                               (['a='+str(self.team),'a='+str(self.personal)],[])]:
            with self.assertRaises(ValueError): initialize(self.output,'demo','work',repos,personal)
            self.assertFalse(self.output.exists())
        with self.assertRaises(ValueError): initialize(self.team/'generated','demo','work',['a='+str(self.team)])
        self.assertFalse((self.team/'generated').exists())

    def test_conflicts_preflight_and_preserve_edits(self):
        self.output.mkdir();(self.output/'AGENTS.md').write_text('my rules')
        with self.assertRaises(ValueError):self.setup()
        self.assertEqual(list(self.output.iterdir()),[self.output/'AGENTS.md'])
        self.assertEqual((self.output/'AGENTS.md').read_text(),'my rules')

    def test_symlink_output_rejected(self):
        actual=self.root/'actual';actual.mkdir(); self.output.symlink_to(actual,target_is_directory=True)
        with self.assertRaises(ValueError):self.setup()
        self.assertEqual(list(actual.iterdir()),[])

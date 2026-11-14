"""Bounded local ChimeraX worker; never invokes a shell or a public REST server."""
import concurrent.futures
import json
import os
import platform
import shutil
import subprocess
import threading
import time
from pathlib import Path
from . import visualization_store as store

SCRIPT_VERSION='molecular-evidence-2'
OUTPUTS={'monomer.png','complex.png','target.png','monomer.mp4','complex.mp4','target.mp4','render.cxc','metadata.json'}


class ChimeraXRenderer:
    def __init__(self):
        self.executor=concurrent.futures.ThreadPoolExecutor(max_workers=1,thread_name_prefix='chimerax')
        self.slots=threading.BoundedSemaphore(4)
        self.lock=threading.RLock()
        self.jobs={}
        self.capability=None

    def check(self, refresh=False):
        with self.lock:
            if self.capability and not refresh: return self.capability
            configured=os.environ.get('CHIMERAX_EXECUTABLE')
            executable=configured or shutil.which('ChimeraX') or shutil.which('chimerax')
            if not executable and Path('/Applications/ChimeraX.app/Contents/MacOS/ChimeraX').is_file(): executable='/Applications/ChimeraX.app/Contents/MacOS/ChimeraX'
            if not executable or not Path(executable).is_file() or not os.access(executable,os.X_OK):
                self.capability={'state':'not_installed','available':False,'version':None,'reason':'ChimeraX is not installed. Set CHIMERAX_EXECUTABLE to an installed official executable.'};return self.capability
            self.executable=str(Path(executable).resolve())
            self.flags=['--offscreen'] if platform.system()=='Linux' else []
            try:
                version=subprocess.run([self.executable,'--version'],capture_output=True,text=True,timeout=30,check=True).stdout.strip()
                if not version: raise ValueError('Version probe returned no version')
                probe=store.ROOT/'_capability';probe.mkdir(parents=True,exist_ok=True)
                image=probe/'probe.png';image.unlink(missing_ok=True)
                (probe/'probe.cxc').write_text('set bgColor white\nsave probe.png width 128 height 128\n')
                result=subprocess.run([self.executable,*self.flags,'--exit','probe.cxc'],cwd=probe,capture_output=True,text=True,timeout=60)
                if result.returncode or not image.is_file() or image.read_bytes()[:8]!=b'\x89PNG\r\n\x1a\n': raise ValueError('OpenGL image capability check failed')
                self.capability={'state':'ready','available':True,'version':version[:500],'reason':None}
            except Exception as exc:
                self.capability={'state':'graphics_unavailable','available':False,'version':None,'reason':f'ChimeraX capability check failed: {type(exc).__name__}. Check local installation/OpenGL; see worker setup.'}
            return self.capability

    def prepare(self, run, candidate, preset='cartoon'):
        store.identifier(run);store.identifier(candidate)
        if preset not in store.PRESETS: raise ValueError('Unsupported representation')
        m=store.manifest(run);target_only=candidate=='target'
        roles=['target'] if target_only else ['monomer','complex']
        inputs={role:store.structure_path(run,candidate,role).read_bytes() for role in roles}
        entry=m.get('candidates',{}).get(candidate,{})
        parameters={'preset':preset,'size':[960,720],'fps':30,'script_version':SCRIPT_VERSION,'target_chains':entry.get('target_chains',[]),'binder_chains':entry.get('binder_chains',[]),'interface':entry.get('interface',{}).get('residues',[])}
        for chain in parameters['target_chains']+parameters['binder_chains']:store.chain_id(chain)
        capability=self.check()
        hashes={role:store.sha(content) for role,content in inputs.items()}
        key=store.sha(json.dumps({'input_hashes':hashes,'parameters':parameters,'version':capability['version']},sort_keys=True).encode())
        folder=store.directory(run)/candidate/'renders'/key;folder.mkdir(parents=True,exist_ok=True)
        for role,content in inputs.items():(folder/(role+'.cif')).write_bytes(content)
        if not target_only:
            complex_s=store.read_structure(inputs['complex'].decode())
            actual={c.name for c in complex_s[0]}
            if not parameters['binder_chains'] or not parameters['target_chains'] or not set(parameters['binder_chains']+parameters['target_chains']).issubset(actual): raise ValueError('Chain mapping missing or invalid')
            if set(parameters['binder_chains']) & set(parameters['target_chains']):raise ValueError('Target and binder chains overlap')
            for name,keep in [('pose-target',parameters['target_chains']),('pose-binder',parameters['binder_chains'])]:
                part=complex_s.clone()
                for c in list(part[0]):
                    if c.name not in keep:del part[0][c.name]
                (folder/(name+'.cif')).write_text(part.make_mmcif_document().as_string())
        script=self.script(parameters,target_only)
        (folder/'render.cxc').write_text(script)
        return folder, {'run_id':run,'candidate_id':candidate,'cache_key':key,'input_hashes':hashes,'parameters':parameters,'chimerax_version':capability['version'],'transition_label':store.TRANSITION_LABEL,'media_type':'illustrative_media','source_job_id':store.asset(run,candidate,roles[-1]).get('source_job_id'),'script_sha256':store.sha(script.encode())}

    @staticmethod
    def script(p, target_only=False):
        preset=p['preset']
        if preset not in store.PRESETS:raise ValueError('Unsupported representation')
        lines=['set bgColor white','lighting soft','graphics silhouettes true','windowsize 960 720']
        def appearance(model,color):
            lines.extend([f'hide #{model} atoms',f'cartoon #{model}',f'color #{model} {color}'])
            if preset=='surface':lines.extend([f'surface #{model}',f'transparency #{model} 35 target s'])
        if target_only:
            lines.append('open target.cif id 1');appearance(1,'teal');lines.extend(['view #1 pad 0.25 clip false','save target.png width 960 height 720 supersample 2','movie record size 960,720 supersample 2','turn y 2 180 models #1','wait 180','movie encode target.mp4 framerate 30']);return '\n'.join(lines)+'\n'
        for c in p['target_chains']+p['binder_chains']:store.chain_id(c)
        lines.append('open monomer.cif id 1');appearance(1,'lime')
        lines.extend(['view #1 pad 0.25 clip false','save monomer.png width 960 height 720 supersample 2','movie record size 960,720 supersample 2','turn y 2 180 models #1','wait 180','movie encode monomer.mp4 framerate 30','close #1','open complex.cif id 1'])
        appearance(1,'teal')
        for chain in p['binder_chains']:lines.append(f'color #1/{chain} lime')
        highlights=[]
        for r in p['interface']:
            chain=store.chain_id(r['chain']);number=r['number']
            if type(number) is not int or not -9999<=number<=999999:raise ValueError('Invalid interface residue number')
            highlights.append(f'#1/{chain}:{number}')
        if highlights:lines.extend(['show '+ '|'.join(highlights)+' atoms','style '+'|'.join(highlights)+' stick'])
        if preset in ('target_only','binder_only'):
            keep=p['target_chains'] if preset=='target_only' else p['binder_chains']
            other=p['binder_chains'] if preset=='target_only' else p['target_chains']
            for c in other: lines.extend([f'hide #1/{c} cartoons',f'hide #1/{c} atoms',f'hide #1/{c} surfaces'])
        lines.extend(['view #1 pad 0.25 clip false','save complex.png width 960 height 720 supersample 2','hide #1 models','open pose-target.cif id 2','open pose-binder.cif id 3'])
        appearance(2,'teal');appearance(3,'lime')
        # These copies share the complex coordinate frame, so no matchmaker/morph is needed.
        lines.extend(['hide #2,3 models','open monomer.cif id 4','hide #4 atoms','cartoon #4','color #4 lime','view #4 pad 0.25 clip false','movie record size 960,720 supersample 2','turn y 2 180 models #4','wait 180','hide #4 models','show #2,3 models','move x 35 models #3','view #2,3 pad 0.25 clip false','wait 30','move x -0.5 70 models #3','wait 70','hide #2,3 models','show #1 models','view #1 pad 0.25 clip false','wait 20','turn y 2 180 models #1','wait 180','wait 30','movie encode complex.mp4 framerate 30'])
        return '\n'.join(lines)+'\n'

    def get_status(self,run,candidate,preset='cartoon'):
        folder,meta=self.prepare(run,candidate,preset)
        key=meta['cache_key']
        with self.lock:
            job_key=(run,candidate,key)
            if job_key in self.jobs:return dict(self.jobs[job_key])
        paths=[folder/'metadata.json']
        # A viewing machine need not install the renderer that produced these media.
        if not self.check()['available']:
            paths.extend(sorted(folder.parent.glob('*/metadata.json'),reverse=True))
        expected={'target.png','target.mp4'} if candidate=='target' else {'monomer.png','complex.png','monomer.mp4','complex.mp4'}
        for path in paths:
            if not path.is_file() or path.is_symlink():continue
            try:saved=json.loads(path.read_text())
            except (ValueError,OSError):continue
            if any(saved.get(k)!=meta[k] for k in ('run_id','candidate_id','input_hashes','parameters')):continue
            if saved.get('cache_key')!=path.parent.name:continue
            checksums=saved.get('checksums',{})
            if saved.get('state')=='ready' and expected.issubset(checksums) and all(n in OUTPUTS and (path.parent/n).is_file() and not (path.parent/n).is_symlink() and store.sha((path.parent/n).read_bytes())==digest for n,digest in checksums.items()):
                saved['artifacts']=self.links(saved,list(expected)+['render.cxc','metadata.json'])
                return saved
        return {**meta,'state':'not_rendered' if self.check()['available'] else 'render_unavailable','reason':self.check().get('reason'),'artifacts':self.links(meta,['render.cxc'])}

    @staticmethod
    def links(meta,names):
        base=f"/api/visualizations/{meta['run_id']}/{meta['candidate_id']}/renders/{meta['cache_key']}/"
        return {name:base+name for name in names}

    def submit(self,run,candidate,preset='cartoon'):
        folder,meta=self.prepare(run,candidate,preset)
        with self.lock:
            previous=self.get_status(run,candidate,preset)
            if previous['state'] in ('ready','queued','running'):return previous
            if not self.check()['available']:return previous
            if not self.slots.acquire(blocking=False):raise ValueError('Renderer queue full; retry after a current job completes')
            status={**meta,'state':'queued','reason':None,'artifacts':self.links(meta,['render.cxc'])};self.jobs[(run,candidate,meta['cache_key'])]=status
            self.executor.submit(self._run,folder,status)
            return dict(status)

    def _run(self,folder,status):
        try:
            status['state']='running'
            names=['target.png','target.mp4'] if status['candidate_id']=='target' else ['monomer.png','complex.png','monomer.mp4','complex.mp4']
            for name in names:(folder/name).unlink(missing_ok=True)
            result=subprocess.run([self.executable,*self.flags,'--exit','render.cxc'],cwd=folder,capture_output=True,text=True,timeout=300)
            (folder/'worker.log').write_text((result.stdout+result.stderr)[-100000:])
            names=['target.png','target.mp4'] if status['candidate_id']=='target' else ['monomer.png','complex.png','monomer.mp4','complex.mp4']
            if result.returncode or any(not (folder/n).is_file() or (folder/n).stat().st_size<100 for n in names):raise ValueError('ChimeraX did not produce all expected images and videos')
            if any((folder/n).read_bytes()[:8]!=b'\x89PNG\r\n\x1a\n' for n in names if n.endswith('.png')):raise ValueError('Invalid PNG output')
            if any(b'ftyp' not in (folder/n).read_bytes()[:64] for n in names if n.endswith('.mp4')):raise ValueError('Invalid MP4 output')
            status.update(state='ready',checksums={n:store.sha((folder/n).read_bytes()) for n in names},artifacts=self.links(status,names+['render.cxc','metadata.json']),completed_at=time.time())
        except Exception as exc:
            status.update(state='render_failed',reason=f'{type(exc).__name__}: {str(exc)[:300]}')
        finally:
            (folder/'metadata.json').write_text(json.dumps(status,indent=2))
            self.slots.release()

    render_monomer=submit
    render_complex=submit
    render_complex_animation=submit
    get_artifacts=get_status


renderer=ChimeraXRenderer()

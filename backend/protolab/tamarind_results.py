"""Read actual BoltzProt archives and map designs to sequence-matched chains."""
import csv
import hashlib
import io
import json
import math
import tarfile
import tempfile
import zipfile
from pathlib import PurePosixPath
from urllib.parse import quote, urlparse
import gemmi
import httpx
from . import tamarind

METRICS = ('binding_confidence', 'structure_confidence', 'iptm', 'min_interaction_pae')


def jobs():
    data = tamarind.api('jobs')
    return {'jobs': [{'name': j['JobName'], 'state': j['JobStatus'], 'created': j.get('Created'), 'type': j.get('Type')} for j in data.get('jobs', []) if j.get('Type') == 'boltzprot']}


def job_info(name):
    if not isinstance(name, str) or not name or len(name) > 200:
        raise ValueError('Invalid job name')
    job = tamarind.api('jobs?jobName=' + quote(name, safe=''))
    if job.get('Type') != 'boltzprot':
        raise ValueError('Select a BoltzProt design task')
    return job


def unpack(raw):
    files = {}
    total = 0
    def keep(name, size, read):
        nonlocal total
        p = PurePosixPath(name)
        if p.is_absolute() or '..' in p.parts:
            raise ValueError('Unsafe archive path')
        total += size
        if total > 250_000_000 or size > 25_000_000:
            raise ValueError('Archive exceeds local size limit')
        if p.suffix.lower() in ('.csv', '.cif', '.mmcif', '.pdb'):
            if name in files: raise ValueError('Duplicate archive path')
            files[name] = read().decode('utf-8-sig')
    stream = io.BytesIO(raw)
    if zipfile.is_zipfile(stream):
        with zipfile.ZipFile(stream) as z:
            for item in z.infolist():
                if not item.is_dir(): keep(item.filename, item.file_size, lambda i=item: z.read(i))
    else:
        stream.seek(0)
        with tarfile.open(fileobj=stream, mode='r:*') as z:
            for item in z:
                if item.isfile(): keep(item.name, item.size, lambda i=item: z.extractfile(i).read())
    return files


def number(value, key):
    try: n = float(value)
    except (ValueError, TypeError): return None
    if not math.isfinite(n) or n < 0 or (key != 'min_interaction_pae' and n > 1): return None
    return n


def parse_results(files):
    metrics = [name for name in files if PurePosixPath(name).name == 'metrics.csv']
    if len(metrics) != 1: raise ValueError('Expected one metrics.csv in BoltzProt results')
    reader = csv.DictReader(io.StringIO(files[metrics[0]]))
    if not {'sequence', 'structure_file'}.issubset(reader.fieldnames or []):
        raise ValueError('Results are missing sequence or structure_file fields')
    candidates, structures = [], {}
    for i, row in enumerate(reader):
        if i >= 1000: raise ValueError('Too many candidates for local viewer')
        key = f'design-{i + 1}'
        sequence = ''.join(row['sequence'].split()).upper()
        item = {'id': key, 'design_id': row.get('id') or key, 'sequence': sequence,
                'metrics': {k: number(row.get(k), k) for k in METRICS}, 'structure_state': 'missing', 'reason': ''}
        path = row['structure_file'].replace('\\', '/')
        exact = [p for p in files if p == path or p == str(PurePosixPath(metrics[0]).parent / path)]
        matches = exact or [p for p in files if PurePosixPath(p).name == PurePosixPath(path).name]
        try:
            if len(matches) != 1: raise ValueError('Structure file missing or ambiguous')
            name = matches[0]; text = files[name]
            s = gemmi.read_pdb_string(text) if name.endswith('.pdb') else gemmi.make_structure_from_block(gemmi.cif.read_string(text).sole_block())
            if len(s) != 1: raise ValueError('Expected one structural model')
            chain_sequences = {}
            for chain in s[0]:
                chain_sequences[chain.name] = ''.join(gemmi.find_tabulated_residue(r.name).one_letter_code.upper() for r in chain if r.find_atom('CA', '*'))
            matched = [chain for chain, seq in chain_sequences.items() if seq == sequence and seq]
            if len(matched) != 1: raise ValueError('Cannot uniquely match binder sequence to a chain')
            binder_chain = matched[0]
            if not any(seq for chain, seq in chain_sequences.items() if chain != binder_chain):
                raise ValueError('Target chain not present in structure')
            complex_text = s.make_mmcif_document().as_string()
            for chain in list(s[0]):
                if chain.name != binder_chain: del s[0][chain.name]
            binder_text = s.make_mmcif_document().as_string()
            structures[key] = {'binder': {'name': key + '-binder.cif', 'text': binder_text, 'format': 'cif'},
                'complex': {'name': name, 'text': complex_text, 'format': 'cif', 'chains': list(chain_sequences)},
                'chain': binder_chain, 'live': True}
            item['structure_state'] = 'ready'
            item['binder_chain'] = binder_chain
            item['source_file'] = name
        except Exception as exc:
            item['reason'] = str(exc)
        candidates.append(item)
    if not candidates: raise ValueError('No candidates found in metrics.csv')
    return candidates, structures


def cache_path(name):
    return tamarind.RUNS / ('results-' + hashlib.sha256(name.encode()).hexdigest() + '.json')


def load(name):
    path = cache_path(name)
    if path.is_file(): return json.loads(path.read_text())
    job = job_info(name)
    if job['JobStatus'] != 'Complete':
        return {'jobName': name, 'state': job['JobStatus'], 'candidates': []}
    url = tamarind.api('result', {'jobName': name})
    if not isinstance(url, str) or urlparse(url).scheme != 'https':
        raise ValueError('Unexpected result download URL')
    with httpx.Client(timeout=120) as client:
        with client.stream('GET', url) as response:
            response.raise_for_status()
            chunks, size = [], 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > 100_000_000: raise ValueError('Results archive exceeds 100 MB')
                chunks.append(chunk)
    candidates, structures = parse_results(unpack(b''.join(chunks)))
    settings = job.get('Settings', {})
    if isinstance(settings, str): settings = json.loads(settings)
    data = {'jobName': name, 'state': 'Complete', 'candidates': candidates, 'structures': structures,
            'target_sequence': settings.get('sequence'), 'provider': 'Tamarind / BoltzProt-1',
            'protein_view': 'Binder chain extracted from predicted complex; not an independent unbound prediction'}
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, suffix='.tmp', delete=False) as stream:
        json.dump(data, stream)
        temporary = stream.name
    from pathlib import Path
    Path(temporary).replace(path)
    return data


def results(name):
    return {k: v for k, v in load(name).items() if k != 'structures'}


def structure(name, candidate):
    data = load(name)
    if candidate not in data.get('structures', {}): raise ValueError('Candidate structure is unavailable')
    return data['structures'][candidate]

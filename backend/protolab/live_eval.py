"""Retrieve an existing live Boltz job and evaluate 1BRS A/D against A/B.

Never submits or retries a paid job. Uses numpy and gemmi for structure parsing
and Kabsch alignment. This old known complex is a smoke test, not a held-out test.
"""
import json
import urllib.request
from pathlib import Path
from .settings import boltz_api_key

RUN = Path(__file__).resolve().parents[2] / 'runs/1brs-live'
BASE = 'https://api.boltz.bio/compute/v1/predictions/structure-and-binding/'


def save(path, data):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, indent=2, allow_nan=False))
    temporary.replace(path)


def public_status():
    if (RUN / 'evaluation.json').is_file():
        return json.loads((RUN / 'evaluation.json').read_text())
    path = RUN / 'latest.json' if (RUN / 'latest.json').exists() else RUN / 'submission.json'
    if not path.exists():
        return {'status': 'not_started', 'mode': 'live'}
    data = json.loads(path.read_text())
    return {'id': data['id'], 'status': 'awaiting_analysis' if data['status'] == 'succeeded' else data['status'], 'mode': 'live',
            'model': data.get('model'), 'livemode': data.get('livemode'),
            'reference': '1BRS, experimental chains A/D', 'samples': []}


def ca_chain(structure, chain_name):
    out = {}
    for residue in structure[0][chain_name]:
        for atom in residue:
            if atom.name == 'CA' and atom.altloc in ('\x00', ' ', 'A'):
                out[residue.seqid.num] = (residue.name, [atom.pos.x, atom.pos.y, atom.pos.z])
                break
    return out


def evaluate(sample_path, reference_path):
    import gemmi
    import numpy as np
    predicted = gemmi.read_structure(str(sample_path))
    reference = gemmi.read_structure(str(reference_path))
    groups = []
    coverage = []
    for pchain, rchain in [('A', 'A'), ('B', 'D')]:
        p, r = ca_chain(predicted, pchain), ca_chain(reference, rchain)
        ids = sorted(set(p) & set(r))
        if len(ids) < 3 or any(p[i][0] != r[i][0] for i in ids):
            raise ValueError('Residue mapping mismatch; cannot evaluate by sequence position')
        groups.append((np.array([p[i][1] for i in ids]), np.array([r[i][1] for i in ids])))
        coverage.append({'predicted_chain': pchain, 'reference_chain': rchain,
                         'matched_ca': len(ids), 'predicted_ca': len(p), 'reference_ca': len(r)})
    def fit(p, r):
        pc, rc = p.mean(axis=0), r.mean(axis=0)
        u, _, vt = np.linalg.svd((p - pc).T @ (r - rc))
        sign = np.eye(3); sign[-1, -1] = np.linalg.det(u @ vt)
        rotation = u @ sign @ vt
        return rotation, pc, rc
    p, r = np.concatenate([g[0] for g in groups]), np.concatenate([g[1] for g in groups])
    rot, pc, rc = fit(p, r)
    complex_rmsd = np.sqrt(np.mean(np.sum(((p-pc)@rot+rc-r)**2, axis=1)))
    rot, pc, rc = fit(*groups[0])
    binder_rmsd = np.sqrt(np.mean(np.sum(((groups[1][0]-pc)@rot+rc-groups[1][1])**2, axis=1)))
    def contacts(a,b):
        return np.linalg.norm(a[:,None,:]-b[None,:,:],axis=2) < 8.0
    pred_contacts = contacts(groups[0][0], groups[1][0])
    ref_contacts = contacts(groups[0][1], groups[1][1])
    shared = int((pred_contacts & ref_contacts).sum())
    return {'complex_ca_rmsd_angstrom': float(complex_rmsd),
            'binder_ca_rmsd_after_target_alignment_angstrom': float(binder_rmsd),
            'ca_contact_cutoff_angstrom': 8.0,
            'reference_ca_contacts': int(ref_contacts.sum()), 'predicted_ca_contacts': int(pred_contacts.sum()),
            'ca_contact_recall': shared / int(ref_contacts.sum()) if ref_contacts.any() else None,
            'ca_contact_precision': shared / int(pred_contacts.sum()) if pred_contacts.any() else None,
            'mapping': coverage}


def refresh():
    submission = json.loads((RUN / 'submission.json').read_text())
    req = urllib.request.Request(BASE + submission['id'], headers={'x-api-key': boltz_api_key()})
    with urllib.request.urlopen(req, timeout=30) as response:
        data = json.load(response)
    save(RUN / 'latest.json', data)
    print('Live job:', data['id'], data['status'], flush=True)
    if data['status'] != 'succeeded':
        return
    if data.get('livemode') is not True:
        raise ValueError('Refusing non-live results')
    import gemmi
    samples = []
    for i, sample in enumerate(data['output']['all_sample_results']):
        path = RUN / f'sample_{i}.cif'
        if not path.exists():
            # Signed artifact URL is used without forwarding the API credential.
            url = sample['structure']['url']
            if not url.startswith('https://'):
                raise ValueError('Expected HTTPS artifact URL')
            with urllib.request.urlopen(url, timeout=45) as response:
                path.write_bytes(response.read())
        st = gemmi.read_structure(str(path))
        st.write_pdb(str(RUN / f'sample_{i}.pdb'))
        samples.append({'index': i, 'metrics': sample['metrics'],
                        'evaluation': evaluate(path, RUN / 'reference.pdb'),
                        'structure_url': f'/api/live/structure/{i}'})
    result = {'id': data['id'], 'status': 'succeeded', 'mode': 'live', 'livemode': True,
              'model': data['model'], 'reference': '1BRS, experimental chains A/D',
              'reference_url': 'https://www.rcsb.org/structure/1BRS',
              'binding_metrics': data['output'].get('binding_metrics'), 'samples': samples,
              'estimated_cost_usd': json.loads((RUN / 'cost.json').read_text())['estimated_cost_usd'],
              'limitations': ['Known historical complex; may overlap training data. Not a held-out benchmark.',
                              'One positive complex, no negative controls; no selectivity or developability claims.',
                              'C-alpha contacts at 8 Angstrom are a coarse proxy, not DockQ or atom-level contacts.',
                              'Independent predictions are not MD trajectory frames.']}
    save(RUN / 'evaluation.json', result)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    refresh()

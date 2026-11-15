"""Tamarind BoltzProt design jobs. Credentials remain server-side."""
import json
import re
import uuid
from pathlib import Path
import httpx
from .settings import tamarind_api_key

RUNS = Path(__file__).resolve().parents[2] / 'runs/tamarind'
BASE = 'https://app.tamarind.bio/api/'

def api(path, body=None):
    key = tamarind_api_key()
    if not key:
        raise ValueError('TAMARIND_API_KEY is not configured')
    try:
        with httpx.Client(timeout=45) as client:
            response = client.request('POST' if body is not None else 'GET', BASE + path,
                                      headers={'x-api-key': key}, json=body)
        if not response.is_success:
            try:
                detail=response.json()
                message=detail.get('error') or detail.get('message') or '' if isinstance(detail,dict) else ''
                if not isinstance(message,str):message=''
                message=re.sub(r'[ACDEFGHIKLMNPQRSTVWY]{20,}','[sequence]',message,flags=re.I)
                message=message.replace(key,'[redacted]')[:300]
            except Exception:message=''
            raise ValueError(f'Tamarind HTTP {response.status_code}'+(': '+message if message else '; inspect account access and settings'))
        if path == 'submit-job':
            return {'accepted': True}
        return response.json()
    except httpx.RequestError as exc:
        raise ValueError('Tamarind connection failed; inspect job status before retrying submission') from exc

def prepare(data):
    sequence = re.sub(r'\s+', '', data.get('sequence', '')).upper()
    if not re.fullmatch('[ACDEFGHIKLMNPQRSTVWY]{10,2000}', sequence):
        raise ValueError('Provide 10–2000 canonical amino acids as the target sequence')
    count, length = int(data.get('count', 10)), int(data.get('length', 80))
    if not 10 <= count <= 100 or not 10 <= length <= 300:
        raise ValueError('Count must be 10–100 and binder length 10–300')
    settings = {'binderModality': 'miniprotein', 'targetInputType': 'sequence',
                'sequence': sequence, 'numProteins': count, 'binderLength': length}
    validation = api('validate-job', {'type': 'boltzprot', 'settings': settings})
    if validation.get('valid') is not True:
        raise ValueError('Tamarind validation rejected settings: ' + str(validation.get('error', 'invalid settings')))
    normalized = validation.get('normalized')
    if not isinstance(normalized, dict):
        raise ValueError('Tamarind did not return normalized settings')
    name = 'protolab-' + uuid.uuid4().hex
    RUNS.mkdir(parents=True, exist_ok=True)
    record = {'jobName': name, 'type': 'boltzprot', 'settings': normalized}
    (RUNS / (name + '.json')).write_text(json.dumps(record))
    return {'jobName': name, 'state': 'READY', 'settings': normalized,
            'note': 'Submission uses Tamarind compute credits. Generated designs require further validation.'}

def record_for(name):
    if not re.fullmatch(r'protolab-[0-9a-f]{32}', name):
        raise ValueError('Invalid local job name')
    path = RUNS / (name + '.json')
    return path, json.loads(path.read_text())

def submit(data):
    if data.get('confirmed') is not True:
        raise ValueError('Confirm compute usage first')
    path, record = record_for(data.get('jobName', ''))
    # Exclusive marker prevents duplicate charges, including concurrent requests.
    with path.with_suffix('.attempt').open('x') as marker:
        marker.write('submission_started')
    api('submit-job', record)
    return {'jobName': record['jobName'], 'state': 'SUBMITTED'}

def status(name):
    record_for(name)
    job = api('jobs?jobName=' + name)
    return {'jobName': name, 'state': job.get('JobStatus', 'UNKNOWN')}

def results(name):
    if status(name)['state'] != 'Complete':
        raise ValueError('Job has not completed')
    url = api('result', {'jobName': name})
    if not isinstance(url, str) or not url.startswith('https://'):
        raise ValueError('Unexpected Tamarind result response')
    return {'jobName': name, 'download_url': url}

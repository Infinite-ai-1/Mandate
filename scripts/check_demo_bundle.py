"""Validate a demo ZIP in a clean source copy, without credentials or networking."""
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECK = r'''
import json, hashlib, socket
from pathlib import Path
from unittest.mock import patch
from mandate import config as C
from mandate.web import create_app
assert C.DEMO_MODE and not C.API_KEY and not C.ANTHROPIC_API_KEY
assert not any(C.MODELS.values())
manifest=json.loads(Path('demo-manifest.json').read_text())
for name,digest in manifest['files'].items():
    assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,name
with patch.object(socket.socket,'connect',side_effect=AssertionError('NETWORK ATTEMPT')) as network:
    app=create_app(); client=app.test_client(); ws=app.config['MANDATE_WORKSPACE']
    for cid in manifest['charities']:
        response=client.post(f'/api/charities/{cid}/run',json={})
        assert response.status_code==202,response.json
        ws.executor.submit(lambda:None).result(timeout=30)
        job=client.get('/api/jobs/'+response.json['job_id']).json
        assert job['status']=='done',job
        assert job['result']['holdings'],cid
        ticker=ws.run(cid)['decisions'][0]['ticker']
        assert client.get(f'/api/charities/{cid}/companies/{ticker}').status_code==200
        assert client.get(f'/api/charities/{cid}/account').status_code==200
        with client.get('/') as response: assert response.status_code==200
        print(cid+': PASS keyless assessment, company, portfolio, account and React')
    assert not network.called
    ws.executor.shutdown()
print('PASS: no credentials, no model configuration, no network attempts; checksums verified')
'''


def main():
    archive = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "results/mandate-keyless-demo.zip").resolve()
    results = ROOT / "results"
    results.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="bundle-check-", dir=results) as temp:
        clean = Path(temp)
        names = subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True).splitlines()
        for name in names:
            path = ROOT / name
            if path.is_file() and not name.startswith(".env"):
                destination = clean / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, destination)
        shutil.copytree(ROOT / "frontend/dist", clean / "frontend/dist", dirs_exist_ok=True)
        with zipfile.ZipFile(archive) as bundle:
            for name in bundle.namelist():
                if not (clean / name).resolve().is_relative_to(clean.resolve()):
                    raise ValueError("Archive path escapes the workspace")
            bundle.extractall(clean)
        env = {k: v for k, v in os.environ.items() if not any(term in k.upper() for term in ("KEY", "TOKEN", "SECRET", "MODEL_", "DEPLOY_", "ENDPOINT"))}
        env.update(DEMO_MODE="1", PYTHONPATH=str(clean))
        result = subprocess.run([sys.executable, "-c", CHECK], cwd=clean, env=env)
        return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())

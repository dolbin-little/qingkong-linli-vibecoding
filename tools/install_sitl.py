"""Restore the exact locally verified official binaries; reject moving upstream replacements."""
from pathlib import Path
import json,hashlib,urllib.request,concurrent.futures
ROOT=Path(__file__).resolve().parents[1]
VENDOR=ROOT/'third_party/ardupilot_sitl'

def install():
    rows=json.loads((VENDOR/'manifest.json').read_text(encoding='utf8'))
    def fetch(row):
        target=VENDOR/row['name']
        if target.parent!=VENDOR or not row['url'].startswith(('https://firmware.ardupilot.org/','https://raw.githubusercontent.com/ArduPilot/')):
            raise ValueError('不受信任的依赖路径或来源')
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()==row['sha256']:return row['name']+' 已校验'
        with urllib.request.urlopen(row['url'],timeout=90) as response:data=response.read()
        if hashlib.sha256(data).hexdigest()!=row['sha256']:
            raise ValueError(row['name']+' 上游版本已改变，拒绝替换已验收版本；需要单独重新验证')
        target.write_bytes(data);return row['name']+' 已下载并校验'
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for result in pool.map(fetch,rows):print(result,flush=True)

if __name__=='__main__':install()

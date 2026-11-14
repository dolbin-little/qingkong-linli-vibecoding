"""One entry point for official SITL, fixed synthetic tests, and regenerated visual report."""
from pathlib import Path
import sys,subprocess
ROOT=Path(__file__).resolve().parents[1]

if __name__=='__main__':
    results=[]
    for file in ('install_sitl.py','sitl_acceptance.py','benchmark.py'):
        if file=='sitl_acceptance.py' and results[0]!=0:
            results.append(1);continue
        r=subprocess.run([sys.executable,'-X','utf8','-B',str(ROOT/'tools'/file)],cwd=ROOT)
        results.append(r.returncode)
    print('评测报告：',ROOT/'reports/evaluation.html')
    sys.exit(1 if any(results) else 0)

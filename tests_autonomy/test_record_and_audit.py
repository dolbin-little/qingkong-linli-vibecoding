import json
from pathlib import Path
import pytest
from autonomy.engine import FlightEngine
from autonomy.research import AuditChain


def test_snapshot_verification_reuses_unchanged_file(tmp_path,monkeypatch):
    chain=AuditChain(tmp_path/'audit.jsonl');chain.append('start',{})
    calls=[];verify=AuditChain.verify
    monkeypatch.setattr(AuditChain,'verify',staticmethod(lambda p:(calls.append(p),verify(p))[1]))
    for _ in range(100):assert chain.verified()
    assert not calls
    chain.append('next',{})
    assert chain.verified() and not calls


def test_external_tamper_is_detected_and_append_rejected(tmp_path):
    chain=AuditChain(tmp_path/'audit.jsonl');chain.append('start',{})
    old_count,old_head=chain.count,chain.head
    chain.path.write_text(chain.path.read_text().replace('start','other'),encoding='utf8')
    assert not chain.verified()
    with pytest.raises(ValueError,match='外部变化'):chain.append('next',{})
    assert (chain.count,chain.head)==(old_count,old_head)


def test_deleted_audit_does_not_silently_start_new_chain(tmp_path):
    chain=AuditChain(tmp_path/'audit.jsonl');chain.append('start',{});chain.path.unlink()
    assert not chain.verified()
    with pytest.raises(ValueError):chain.append('next',{})


def test_second_writer_is_not_allowed_to_fork_a_chain(tmp_path):
    first=AuditChain(tmp_path/'audit.jsonl');first.append('start',{})
    second=AuditChain(first.path);second.append('external',{})
    assert AuditChain.verify(first.path)  # Valid file, but different from this writer's known head.
    assert not first.verified()
    with pytest.raises(ValueError):first.append('fork',{})


def test_failed_serialization_does_not_advance_head(tmp_path):
    chain=AuditChain(tmp_path/'audit.jsonl');chain.append('start',{})
    before=(chain.count,chain.head,chain.path.read_bytes())
    with pytest.raises(ValueError):chain.append('bad',{'x':float('nan')})
    assert (chain.count,chain.head,chain.path.read_bytes())==before
    chain.append('next',{});assert AuditChain.verify(chain.path)


def test_valid_prefix_truncation_is_detected(tmp_path):
    chain=AuditChain(tmp_path/'audit.jsonl');chain.append('start',{})
    prefix=chain.path.read_bytes();chain.append('second',{})
    chain.path.write_bytes(prefix)
    assert AuditChain.verify(chain.path) and not chain.verified()


@pytest.mark.parametrize('content',['null\n','[]\n','{"unexpected":1}\n'])
def test_malformed_record_is_reported_as_failed_verification(tmp_path,content):
    p=tmp_path/'audit.jsonl';p.write_text(content,encoding='utf8')
    assert not AuditChain.verify(p)


def test_failed_open_does_not_advance_head(tmp_path,monkeypatch):
    chain=AuditChain(tmp_path/'audit.jsonl');chain.append('start',{})
    before=(chain.count,chain.head);original=Path.open
    def denied(path,mode='r',*args,**kwargs):
        if path==chain.path and mode=='a':raise OSError('disk failure')
        return original(path,mode,*args,**kwargs)
    monkeypatch.setattr(Path,'open',denied)
    with pytest.raises(OSError):chain.append('next',{})
    assert (chain.count,chain.head)==before


def test_export_includes_whole_retained_trace_without_aliasing(tmp_path):
    e=FlightEngine(tmp_path)
    e.trace=[{'t':i,'p':[i,0,1],'v':[1,0,0]} for i in range(1200)]
    assert len(e.snapshot()['trace'])==300
    record=e.record();assert len(record['trace'])==1200
    assert record['trace_scope']=='full_retained_window'
    record['trace'][0]['p'][0]=-1
    assert e.trace[0]['p'][0]==0


def test_help_routes_are_whitelisted_and_available():
    from fastapi.testclient import TestClient
    from sky_platform import app
    # No lifespan: this read-only check must not start the business simulator.
    c=TestClient(app)
    for name in ('manual','intro'):
        response=c.get('/help/'+name);assert response.status_code==200
        assert '晴空邻里' in response.text
    assert c.get('/help/unknown').status_code==404

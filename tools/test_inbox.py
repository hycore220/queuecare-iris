"""Exercise the running IRIS file adapter, including one actual AI Hub call.

Run on this Windows host with WSL Docker: python tools/test_inbox.py --wsl-distro Ubuntu-24.04
Inputs are synthetic; the test leaves files, receipts and records for inspection.
"""
import argparse
import base64
import json
import subprocess
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INBOX = '/home/irisowner/queuecare/inbox'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wsl-distro')
    args = parser.parse_args()
    prefix = ['wsl', '-d', args.wsl_distro, '--'] if args.wsl_distro else []
    compose = prefix + ['docker', 'compose']

    def execute(argv, data=None):
        result = subprocess.run(argv, input=data, capture_output=True, cwd=ROOT, timeout=190)
        if result.returncode:
            raise RuntimeError(result.stderr.decode(errors='replace'))
        return result.stdout.decode(errors='replace')

    def iris(expression):
        script = f'zn "QUEUECARE"\nset result={expression}\nwrite !,"RESULT_BEGIN",!,result,!,"RESULT_END",!\nhalt\n'
        output = execute(compose + ['exec', '-T', 'iris', 'iris', 'session', 'IRIS'], script.encode())
        text = output.split('RESULT_BEGIN\n', 1)[1].split('\nRESULT_END', 1)[0].strip()
        return json.loads(text)

    def python(code):
        return execute(compose + ['exec', '-T', 'iris', 'python3', '-c', code])

    def publish(text):
        encoded = base64.b64encode(text.encode()).decode()
        return python(f"import base64; from queuecare.inbox import publish; print(publish({INBOX!r},base64.b64decode({encoded!r}).decode()))").strip()

    def receipt(filename, seconds=120):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            code = f"import json,pathlib; files=list(pathlib.Path({INBOX!r}).joinpath('receipts').glob('*__'+{filename!r}+'.json')); print(files[0].read_text() if files else 'null')"
            value = json.loads(python(code))
            if value is not None:
                return value
            time.sleep(1)
        raise TimeoutError('No receipt. Inspect the live adapter and its processing directory; do not blindly resubmit.')

    checks = []
    evidence = {}
    report = {'evidence_kind': 'actual-polling-inbound-adapter-through-IRIS-production',
              'external_delivery': False, 'checks': checks, 'evidence': evidence}

    def check(condition, name):
        checks.append({'name': name, 'passed': bool(condition)})
        if not condition:
            raise AssertionError(name)

    try:
        check(iris('##class(QueueCare.Setup).Start()') == 1, 'IRIS production running')
        event = {'id': 'inbox-test-' + uuid.uuid4().hex[:10], 'source': 'warehouse-file',
                 'order_id': 'ORD-42', 'sku': 'legacy-blue', 'quantity': 2, 'status': 'failed', 'retry_count': 0}
        filename = publish(json.dumps(event))
        print('Published synthetic file; waiting for the actual polling worker.', flush=True)
        first = receipt(filename)
        evidence['first_receipt'] = first
        check(first['disposition'] == 'processed', 'adapter consumed a file without manual OnTask invocation')
        result = first['result']
        check(result.get('agent_call_completed') == 1, 'actual AI Hub inference completed')
        check(result.get('state') == 'awaiting_approval', 'file event waits for reviewer approval')
        detail = iris(f'##class(QueueCare.Demo).Detail("{event["id"]}","warehouse-file")')
        check(detail['sink_record_count'] == 0, 'file ingestion does not apply action before approval')
        approved = iris(f'##class(QueueCare.API).Approve("warehouse-file","{event["id"]}",1,"inbox-integration-test")')
        check(approved['state'] == 'delivered_local', 'reviewer can approve file event through production')
        duplicate = receipt(publish(json.dumps(event)))
        evidence['duplicate_receipt'] = duplicate
        check(duplicate['result'].get('duplicate') == 1, 'duplicate file recognized by stable event identity')
        check(duplicate['result']['agent_metrics'] == result['agent_metrics'], 'duplicate reused recorded inference')
        detail = iris(f'##class(QueueCare.Demo).Detail("{event["id"]}","warehouse-file")')
        check(detail['sink_record_count'] == 1, 'duplicate produced no second sink row')
        check(sum(x['event']=='received' for x in detail['journal']) == 1, 'duplicate produced no second receive journal entry')
        check(detail['delivery']['sku']=='SKU-100' and detail['delivery']['quantity']==2, 'approved output changes only the intended SKU')
        conflict = dict(event, quantity=999)
        rejected = receipt(publish(json.dumps(conflict)))
        check(rejected['disposition']=='rejected' and rejected['result']['error']=='identity_conflict', 'changed payload under same identity is rejected')
        for label, text in [('malformed JSON', '{'), ('duplicate JSON keys', '{"id":"a","id":"b","source":"warehouse-file","order_id":"ORD-42"}'),
                            ('wrong transport source', json.dumps(dict(event, id='wrong-source-'+event['id'], source='web-demo'))),
                            ('oversized file', 'x'*16385)]:
            rejected = receipt(publish(text))
            check(rejected['disposition']=='rejected' and rejected['result']['ok'] is False, label+' retained with rejection receipt')
        report['passed'] = True
        evidence['final_detail'] = detail
    except Exception as error:
        report.update(passed=False, error=str(error))
    report['checks_run'] = len(checks)
    path = ROOT / 'reports/inbox-integration.json'
    path.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'passed': report['passed'], 'checks': len(checks), 'error': report.get('error'), 'report': str(path)}), flush=True)
    if not report['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Validate the existing device probe and API; no optical CUDA benchmark."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'benchmarks'))
from cases import api


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expect-devices', type=int, required=True)
    parser.add_argument('--repeats', type=int, default=10)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.repeats < 1 or args.expect_devices < 0:
        parser.error('Counts must be valid and repeats must be positive')
    cp = api()
    count = cp.cuda_device_count()
    available = cp.cuda_available()
    if count != args.expect_devices or available != (count > 0):
        raise AssertionError(f'Unexpected CUDA availability/count: {available}/{count}')
    context = cp.data_create()
    if not context:
        raise AssertionError('Context creation failed')
    report = {'cuda_available': available, 'cuda_device_count': count,
              'probe_expected_value': 42, 'probe_validation': 'not run',
              'probe_source_sha256': hashlib.sha256((ROOT / 'ssc/solarpilot/CudaProbe.cu').read_bytes()).hexdigest(),
              'timing_scope': 'device selection + allocation + trivial kernel + synchronization + readback + cleanup',
              'optical_cuda_implemented': False}
    try:
        assert cp.get_compute_backend(context) == 'cpu'
        assert cp.set_compute_backend(context, 'cpu')
        if count:
            timings = []
            for _ in range(args.repeats):
                start = time.perf_counter()
                assert cp.set_cuda_device(context, 0)
                timings.append(time.perf_counter() - start)
            report['probe_validation'] = 'PASS: the existing C++ probe checks copied-back value == 42 before returning success'
            report['probe_samples_s'] = timings
            report['probe_statistics_s'] = {'count': len(timings), 'first': timings[0],
                'median': statistics.median(timings), 'minimum': min(timings), 'maximum': max(timings)}
            invalid_device = count
        else:
            invalid_device = 0
        try:
            cp.set_cuda_device(context, invalid_device)
        except RuntimeError as error:
            report['invalid_device_error'] = str(error)
        else:
            raise AssertionError('Unavailable/out-of-range device must fail')
        try:
            cp.set_compute_backend(context, 'cuda')
        except RuntimeError as error:
            report['optical_cuda_selection_error'] = str(error)
            assert 'not implemented' in str(error)
        else:
            raise AssertionError('Optical CUDA selection must remain unimplemented')
        assert cp.get_compute_backend(context) == 'cpu'
        report['backend_after_rejected_cuda'] = 'cpu'
    finally:
        assert cp.data_free(context)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()

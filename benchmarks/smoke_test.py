#!/usr/bin/env python3
"""Exercise the original API including generated layout and all result exports."""
import json
from cases import api, configure, collect


def main():
    cp = api()
    r = cp.data_create()
    assert r, 'Context creation failed'
    try:
        configure(cp, r, 'small')
        assert cp.data_set_number(r, 'solarfield.0.des_sim_detail', 1)
        assert cp.data_set_number(r, 'land.0.max_fixed_rad', 850.)
        assert cp.generate_layout(r, nthreads=1), 'Layout generation failed'
        count = len(cp.get_layout_info(r, restype='dictionary')['id'])
        assert count > 0, 'Empty field'
        assert cp.simulate(r, nthreads=1), 'Simulation failed'
        result, _ = collect(cp, r)
        print(json.dumps({'smoke': 'PASS', 'heliostats': count, 'metrics': result['metrics']}, indent=2))
    finally:
        assert cp.data_free(r), 'Free failed'


if __name__ == '__main__':
    main()

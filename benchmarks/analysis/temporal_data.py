"""Validate CPU temporal strategy group medians against retained attempts."""
import statistics
from .common import need, close


def audit(summary):
    raw=summary['raw_attempts']
    for group in summary['strategy_groups']+summary['commercial_long_groups']:
        population=[r for r in raw if r['identifier'] in group['campaign_ids']]
        need(len(population)==group['clean_repetitions'] and len({r['identifier'] for r in population})==len(population),
             'temporal strategy population')
        for field in ['states_per_s','evaluation_wall_s','total_wall_s','setup_wall_s','load_balance_efficiency','output_bytes']:
            if field in group:
                close(group[field],statistics.median(r[field] for r in population),'CPU temporal group '+field)
    for row in raw:
        need(row['total_wall_s']>=row['evaluation_wall_s']>0,'CPU temporal wall boundary')
        close(row['states_per_s'],row['completed']/row['evaluation_wall_s'],'CPU evaluation denominator')
        close(row['total_states_per_s'],row['completed']/row['total_wall_s'],'CPU total denominator')
    return summary['strategy_groups']

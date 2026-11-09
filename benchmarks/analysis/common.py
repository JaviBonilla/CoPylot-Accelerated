"""Shared numerical evidence checks and CSV serialization."""
import csv
import io
import math
import statistics

def csv_text(rows):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()

def need(ok, message):
    if not ok:
        raise ValueError(message)


def close(actual, expected, message):
    need(isinstance(actual,(int,float)) and not isinstance(actual,bool) and
         math.isfinite(actual) and math.isclose(actual,expected,rel_tol=3e-12,abs_tol=3e-12),message)


def timing_statistics(values):
    need(bool(values) and all(isinstance(x,(int,float)) and not isinstance(x,bool) and
         math.isfinite(x) and x>0 for x in values),'invalid timing samples')
    return dict(median=statistics.median(values),minimum=min(values),maximum=max(values),mean=statistics.mean(values),
                stdev=statistics.stdev(values) if len(values)>1 else 0,
                coefficient_of_variation=statistics.stdev(values)/statistics.mean(values) if len(values)>1 else 0)

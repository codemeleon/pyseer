# Copyright 2017 Marco Galardini and John Lees

'''Utilities'''

import os
import contextlib
from decimal import Decimal


# thanks to Laurent LAPORTE on SO
@contextlib.contextmanager
def set_env(**environ):
    """
    Temporarily set the process environment variables.

    >>> with set_env(PLUGINS_DIR=u'test/plugins'):
    ...   "PLUGINS_DIR" in os.environ
    True

    >>> "PLUGINS_DIR" in os.environ
    False
    """
    old_environ = dict(os.environ)
    os.environ.update(environ)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(old_environ)


# avoid numpy taking up more than one thread
with set_env(MKL_NUM_THREADS='1',
             NUMEXPR_NUM_THREADS='1',
             OMP_NUM_THREADS='1'):
    import numpy as np


def format_output(item, lineage_dict, lmm=False, print_samples=False):
    out = '%s' % item.kmer
    out += '\t' + '\t'.join(['%.2E' % Decimal(x)
                             if np.isfinite(x)
                             else ''
                             for x in (item.af,
                                       item.prep,
                                       item.pvalue,
                                       item.kbeta,
                                       item.bse)])
    if lmm:
        out += item.variant_h2
    else:
        out += '\t' + '%.2E' % Decimal(item.intercept) + '\t'.join(['%.2E' % Decimal(x)
                                                                    if np.isfinite(x)
                                                                    else ''
                                                                    for x in item.betas])

    if item.max_lineage is not None:
        if item.max_lineage is not "NA":
            out += '\t' + lineage_dict[item.max_lineage]
        else:
            out += '\tNA'
    if print_samples:
        out += '\t' + '\t'.join((','.join(item.kstrains),
                                 ','.join(item.nkstrains)))
    if not lmm:
        out += '\t%s' % ','.join(item.notes)

    return out

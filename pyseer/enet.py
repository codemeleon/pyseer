# Copyright 2018 Marco Galardini and John Lees

'''Elastic net model implementations'''

import os
import sys
from .utils import set_env
# avoid numpy taking up more than one thread
with set_env(MKL_NUM_THREADS='1',
             NUMEXPR_NUM_THREADS='1',
             OMP_NUM_THREADS='1'):
    import numpy as np
from scipy.sparse import csr_matrix
import math
import pandas as pd
from decimal import Decimal
from glmnet import LogitNet
from glmnet import ElasticNet

import pyseer.classes as var_obj
from .input import read_variant
from .model import fit_lineage_effect

# Loads all variants into memory for use with elastic net
def load_all_vars(var_type, p, burden, burden_regions, infile,
                   all_strains, sample_order, min_af, max_af,
                   uncompressed, quantile_filter = 0.25):
    """Make in iterable to load blocks of variants for LMM

    Args:
        var_type (str)
            Variants type (one of: kmers, vcf or Rtab)
        p (pandas.DataFrame)
            Phenotype vector (n, 1)
        burden (bool)
            Whether to slice a vcf file by burden regions
        burden_regions (collections.deque)
            Burden regions to slice the vcf with
        infile (opened file)
            Handle to opened variant file
        all_strains (set-like)
            All sample labels that should be present
        sample_order
            Sampes order to interpret each Rtab line
        min_af (float)
            Minimum allele frequency (inclusive)
        max_af (bool)
            maximum allele frequency (inclusive)
        uncompressed (bool)
            Whether the kmers file is uncompressed
        block_size (int)
            How many variants to be loaded at once

    Returns:
        variants (iterable)
            A collection of pyseer.classes.LMM objects describing the
            loaded variants (n,)
        variant_mat (numpy.array)
            Variant bloack presence/absence matrix (n, block_size)
        eof (bool)
            Whether we are at the end of the file
    """
    #TODO add covariates

    # For building sparse matrix
    data = []
    indices = []
    indptr = [0]
    selected_vars = []
    var_idx = 0

    # For correlation calculation
    correlations = []
    b = p.values - np.mean(p.values)
    sum_b_squared = np.sum(np.power(b, 2))
    while True:
        eof, k, var_name, kstrains, nkstrains, af = read_variant(
                                        infile, p, var_type,
                                        burden, burden_regions,
                                        uncompressed, all_strains,
                                        sample_order)

        # check for EOF
        if eof:
            break

        if k is not None and af > min_af and af < max_af:
            # Calculate correlation
            a = k - np.mean(k)
            cor = np.abs(np.dot(a, b) / np.sqrt(np.sum(np.power(a, 2)) * sum_b_squared))
            correlations.append(cor)

            # Minor allele encoding - most efficient use of sparse structure
            if af > 0.5:
                pres = 0
            else:
                pres = 1

            for idx, obs in enumerate(k):
                if obs == pres:
                    indices.append(idx)
                    data.append(1)
            indptr.append(len(indices))

            selected_vars.append(var_idx)

        var_idx += 1

    # construct sparse matrix, then filter out correlations
    variants = csr_matrix((data, indices, indptr), dtype=float)
    cor_filter = np.nonzero(correlations > np.percentile(correlations, quantile_filter*100))[0]
    variants = variants[cor_filter, :].transpose()
    selected_vars = np.array(selected_vars)[cor_filter]

    return(variants, selected_vars, var_idx, len(selected_vars))

def fit_enet(p, variants, continuous, alpha, n_folds = 10, n_cpus = 1):
    if continuous:
        regr = ElasticNet(alpha = alpha, n_splits = n_folds, n_jobs = n_cpus)
    else:
        regr = LogitNet(alpha = alpha, n_splits = n_folds, n_jobs = n_cpus)

    fitted = regr.fit(variants, p.values)

    sys.stderr.write("Best penalty from cross-validation: " + '%.2E' % Decimal(fitted.lambda_max_) + "\n")
    if continuous:
        betas = regr.coef_
    else:
        betas = regr.coef_.reshape(-1, )
    return(betas)

def find_enet_selected(enet_betas, var_indices, p, c, var_type, burden,
                       burden_regions, infile, all_strains, sample_order,
                       find_lineage, lin, uncompressed):

    current_var = 0
    for beta, var_idx in zip(enet_betas, var_indices):
        # Only need to process selected variants
        if beta == 0:
            continue
        while current_var < var_idx:
            eof, k, var_name, kstrains, nkstrains, af = read_variant(
                                        infile, p, var_type,
                                        burden, burden_regions,
                                        uncompressed, all_strains,
                                        sample_order, noparse=True)
            current_var += 1

        eof, k, var_name, kstrains, nkstrains, af = read_variant(
                                        infile, p, var_type,
                                        burden, burden_regions,
                                        uncompressed, all_strains,
                                        sample_order)
        current_var += 1
        if af > 0.5:
            beta *= -1

        notes = []
        if find_lineage:
            max_lineage = fit_lineage_effect(lin, c, k)
        else:
            max_lineage = None

        yield var_obj.Enet(var_name, af, beta, max_lineage, kstrains, nkstrains, notes)

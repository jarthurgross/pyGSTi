import unittest
import time
import sys
import numpy as np
from mpinoseutils import *

import pygsti
from pygsti.construction import std1Q_XYI as std

g_maxLengths = [0,1,2]
g_numSubTrees = 3

def runOneQubit_Tutorial():
    from pygsti.construction import std1Q_XYI
    gs_target = std1Q_XYI.gs_target
    fiducials = std1Q_XYI.fiducials
    germs = std1Q_XYI.germs
    maxLengths = [0,1,2,4,8,16,32,64,128,256,512,1024,2048]
    
    gs_datagen = gs_target.depolarize(gate_noise=0.1, spam_noise=0.001)
    listOfExperiments = pygsti.construction.make_lsgst_experiment_list(
        gs_target.gates.keys(), fiducials, fiducials, germs, maxLengths)
    ds = pygsti.construction.generate_fake_data(gs_datagen, listOfExperiments,
                                                nSamples=1000,
                                                sampleError="binomial",
                                                seed=1234)

    results = pygsti.do_long_sequence_gst(ds, gs_target, fiducials, fiducials,
                                          germs, maxLengths, comm=comm)

    #results.create_full_report_pdf(confidenceLevel=95,
    #    filename="tutorial_files/MyEvenEasierReport.pdf",verbosity=2)


def runAnalysis(obj, myspecs, mygerms, gsTarget, seed,
                maxLs = [1,2,4,8],
                nSamples=1000, useFreqWeightedChiSq=False,
                minProbClipForWeighting=1e-4, fidPairList=None,
                comm=None, distributeMethod="gatestrings"):
    rhoStrs, EStrs = pygsti.construction.get_spam_strs(myspecs)
    lgstStrings = pygsti.construction.list_lgst_gatestrings(
        myspecs, gsTarget.gates.keys())
    lsgstStrings = pygsti.construction.make_lsgst_lists(
            gsTarget.gates.keys(), rhoStrs, EStrs, mygerms, maxLs, fidPairList )

    print len(myspecs[0]), " rho specifiers"
    print len(myspecs[1]), " effect specifiers"
    print len(mygerms), " germs"
    print len(lgstStrings), " total LGST gate strings"
    print len(lsgstStrings[-1]), " LSGST strings before thinning"
    
    lsgstStringsToUse = lsgstStrings
    allRequiredStrs = pygsti.remove_duplicates(lgstStrings + lsgstStrings[-1])
     
    
    gs_dataGen = gsTarget.depolarize(gate_noise=0.1)
    dsFake = pygsti.construction.generate_fake_data(
        gs_dataGen, allRequiredStrs, nSamples, sampleError="multinomial",
        seed=seed)

    #Run LGST to get starting gate set
    gs_lgst = pygsti.do_lgst(dsFake, myspecs, gsTarget,
                             svdTruncateTo=gsTarget.dim, verbosity=3)
    gs_lgst_go = pygsti.optimize_gauge(gs_lgst,"target",
                                       targetGateset=gs_dataGen)
    
    #Run full iterative LSGST
    tStart = time.time()
    if obj == "chi2":
        all_gs_lsgst = pygsti.do_iterative_mc2gst(
            dsFake, gs_lgst_go, lsgstStringsToUse,
            minProbClipForWeighting=minProbClipForWeighting,
            probClipInterval=(-1e5,1e5),
            verbosity=1, memLimit=3*(1024)**3, returnAll=True, 
            useFreqWeightedChiSq=useFreqWeightedChiSq, comm=comm,
            distributeMethod=distributeMethod)
    elif obj == "logl":
        all_gs_lsgst = pygsti.do_iterative_mlgst(
            dsFake, gs_lgst_go, lsgstStringsToUse,
            minProbClip=minProbClipForWeighting,
            probClipInterval=(-1e5,1e5),
            verbosity=1, memLimit=3*(1024)**3, returnAll=True, 
            useFreqWeightedChiSq=useFreqWeightedChiSq, comm=comm,
            distributeMethod=distributeMethod)

    tEnd = time.time()
    print "Time = ",(tEnd-tStart)/3600.0,"hours"
    
    return all_gs_lsgst, gs_dataGen
    
    
def runOneQubit(obj, comm=None, distributeMethod="gatestrings"):
    maxLengths = [0,1,2,4,8,16] #still need to define this manually
    specs = pygsti.construction.build_spam_specs(
        std.fiducials, prep_labels=std.gs_target.get_prep_labels(),
        effect_labels=std.gs_target.get_effect_labels())

    gsets, dsGen = runAnalysis(obj, specs, std.germs, std.gs_target,
                               1234, maxLengths, nSamples=1000,
                               comm=comm, distributeMethod=distributeMethod)
    return gsets


@mpitest(4)
def test_MPI_products(comm):

    #Create some gateset
    gs = std.gs_target.copy()
    gs.kick(0.1,seed=1234)

    #Get some gate strings
    maxLengths = [0,1,2,4,8]
    gstrs = pygsti.construction.make_lsgst_experiment_list(
        std.gs_target.gates.keys(), std.fiducials, std.fiducials, std.germs, maxLengths)
    tree = gs.bulk_evaltree(gstrs)
    split_tree = tree.copy()
    split_tree.split(numSubTrees=g_numSubTrees)


    # Check wrtFilter functionality in dproduct
    some_wrtFilter = [0,2,3,5,10]
    for s in gstrs[0:20]:
        result = gs._calc().dproduct(s, wrtFilter=some_wrtFilter)
        chk_result = gs.dproduct(s) #no filtering
        for ii,i in enumerate(some_wrtFilter):
            assert(np.linalg.norm(chk_result[i]-result[ii]) < 1e-6)
        taken_chk_result = chk_result.take( some_wrtFilter, axis=0 )
        assert(np.linalg.norm(taken_chk_result-result) < 1e-6)


    #Check bulk products

      #bulk_product - no parallelization unless tree is split
    serial = gs.bulk_product(tree, bScale=False)
    parallel = gs.bulk_product(tree, bScale=False, comm=comm)
    assert(np.linalg.norm(serial-parallel) < 1e-6)
    
    serial_scl, sscale = gs.bulk_product(tree, bScale=True)
    parallel, pscale = gs.bulk_product(tree, bScale=True, comm=comm)
    assert(np.linalg.norm(serial_scl*sscale[:,None,None] - 
                          parallel*pscale[:,None,None]) < 1e-6)
    
      # will use a split tree to parallelize
    parallel = gs.bulk_product(split_tree, bScale=False, comm=comm)
    assert(np.linalg.norm(serial-parallel) < 1e-6)

    parallel, pscale = gs.bulk_product(split_tree, bScale=True, comm=comm)
    assert(np.linalg.norm(serial_scl*sscale[:,None,None] - 
                          parallel*pscale[:,None,None]) < 1e-6)

    
      #bulk_dproduct - no split tree => parallel by col
    serial = gs.bulk_dproduct(tree, bScale=False)
    parallel = gs.bulk_dproduct(tree, bScale=False, comm=comm)
    assert(np.linalg.norm(serial-parallel) < 1e-6)

    serial_scl, sscale = gs.bulk_dproduct(tree, bScale=True)
    parallel, pscale = gs.bulk_dproduct(tree, bScale=True, comm=comm)
    assert(np.linalg.norm(serial_scl*sscale[:,None,None,None] - 
                          parallel*pscale[:,None,None,None]) < 1e-6)

      # will just ignore a split tree for now (just parallel by col)
    parallel = gs.bulk_dproduct(split_tree, bScale=False, comm=comm)
    assert(np.linalg.norm(serial-parallel) < 1e-6)

    parallel, pscale = gs.bulk_dproduct(split_tree, bScale=True, comm=comm)
    assert(np.linalg.norm(serial_scl*sscale[:,None,None,None] - 
                          parallel*pscale[:,None,None,None]) < 1e-6)


      #bulk_hproduct - no split tree => parallel by col
    serial = gs.bulk_hproduct(tree, bScale=False)
    parallel = gs.bulk_hproduct(tree, bScale=False, comm=comm)
    assert(np.linalg.norm(serial-parallel) < 1e-6)
    
    serial_scl, sscale = gs.bulk_hproduct(tree, bScale=True)
    parallel, pscale = gs.bulk_hproduct(tree, bScale=True, comm=comm)
    assert(np.linalg.norm(serial_scl*sscale[:,None,None,None,None] - 
                          parallel*pscale[:,None,None,None,None]) < 1e-6)
    
      # will just ignore a split tree for now (just parallel by col)
    parallel = gs.bulk_hproduct(split_tree, bScale=False, comm=comm)
    assert(np.linalg.norm(serial-parallel) < 1e-6)
    
    parallel, pscale = gs.bulk_hproduct(split_tree, bScale=True, comm=comm)
    assert(np.linalg.norm(serial_scl*sscale[:,None,None,None,None] - 
                          parallel*pscale[:,None,None,None,None]) < 1e-6)



@mpitest(4)
def test_MPI_pr(comm):

    #Create some gateset
    gs = std.gs_target.copy()
    gs.kick(0.1,seed=1234)

    #Get some gate strings
    maxLengths = [0,1,2]
    maxLengths = g_maxLengths
    gstrs = pygsti.construction.make_lsgst_experiment_list(
        std.gs_target.gates.keys(), std.fiducials, std.fiducials, std.germs, maxLengths)
    tree = gs.bulk_evaltree(gstrs)
    split_tree = tree.copy()
    split_tree.split(numSubTrees=g_numSubTrees)

    #Check single-spam-label bulk probabilities

    # non-split tree => automatically adjusts wrtBlockSize to accomodate
    #                    the number of processors
    serial = gs.bulk_pr('plus', tree, clipTo=(-1e6,1e6))
    parallel = gs.bulk_pr('plus', tree, clipTo=(-1e6,1e6), comm=comm)
    assert(np.linalg.norm(serial-parallel) < 1e-6)

    serial = gs.bulk_dpr('plus', tree, clipTo=(-1e6,1e6))
    parallel = gs.bulk_dpr('plus', tree, clipTo=(-1e6,1e6), comm=comm)
    assert(np.linalg.norm(serial-parallel) < 1e-6)

    serial, sp = gs.bulk_dpr('plus', tree, returnPr=True, clipTo=(-1e6,1e6))
    parallel, pp = gs.bulk_dpr('plus', tree, returnPr=True, clipTo=(-1e6,1e6), comm=comm)
    assert(np.linalg.norm(serial-parallel) < 1e-6)
    assert(np.linalg.norm(sp-pp) < 1e-6)

    serial, sdp, sp = gs.bulk_hpr('plus', tree, returnPr=True, returnDeriv=True,
                             clipTo=(-1e6,1e6))
    parallel, pdp, pp = gs.bulk_hpr('plus', tree, returnPr=True,
                                 returnDeriv=True, clipTo=(-1e6,1e6), comm=comm)
    assert(np.linalg.norm(serial-parallel) < 1e-6)
    assert(np.linalg.norm(sdp-pdp) < 1e-6)
    assert(np.linalg.norm(sp-pp) < 1e-6)


    # split tree =>  distribures on sub-trees prior to adjusting
    #                wrtBlockSize to accomodate remaining processors
    serial = gs.bulk_pr('plus', tree, clipTo=(-1e6,1e6))
    parallel = gs.bulk_pr('plus', split_tree, clipTo=(-1e6,1e6), comm=comm)
    assert(np.linalg.norm(serial-parallel) < 1e-6)

    serial = gs.bulk_dpr('plus', tree, clipTo=(-1e6,1e6))
    parallel = gs.bulk_dpr('plus', split_tree, clipTo=(-1e6,1e6), comm=comm)
    assert(np.linalg.norm(serial-parallel) < 1e-6)

    serial, sp = gs.bulk_dpr('plus', tree, returnPr=True, clipTo=(-1e6,1e6))
    parallel, pp = gs.bulk_dpr('plus', split_tree, returnPr=True, clipTo=(-1e6,1e6), comm=comm)
    assert(np.linalg.norm(serial-parallel) < 1e-6)
    assert(np.linalg.norm(sp-pp) < 1e-6)

    serial, sdp, sp = gs.bulk_hpr('plus', tree, returnPr=True, returnDeriv=True,
                             clipTo=(-1e6,1e6))
    parallel, pdp, pp = gs.bulk_hpr('plus', split_tree, returnPr=True,
                                 returnDeriv=True, clipTo=(-1e6,1e6), comm=comm)
    assert(np.linalg.norm(serial-parallel) < 1e-6)
    assert(np.linalg.norm(sdp-pdp) < 1e-6)
    assert(np.linalg.norm(sp-pp) < 1e-6)



@mpitest(4)
def test_MPI_probs(comm):

    #Create some gateset
    gs = std.gs_target.copy()
    gs.kick(0.1,seed=1234)

    #Get some gate strings
    maxLengths = [0,1,2]
    maxLengths = g_maxLengths
    gstrs = pygsti.construction.make_lsgst_experiment_list(
        std.gs_target.gates.keys(), std.fiducials, std.fiducials, std.germs, maxLengths)
    tree = gs.bulk_evaltree(gstrs)
    split_tree = tree.copy()
    split_tree.split(numSubTrees=g_numSubTrees)

    #Check all-spam-label bulk probabilities

    # non-split tree => automatically adjusts wrtBlockSize to accomodate
    #                    the number of processors
    serial = gs.bulk_probs(tree, clipTo=(-1e6,1e6))
    parallel = gs.bulk_probs(tree, clipTo=(-1e6,1e6), comm=comm)
    for sl in serial:
        assert(np.linalg.norm(serial[sl]-parallel[sl]) < 1e-6)

    serial = gs.bulk_dprobs(tree, clipTo=(-1e6,1e6))
    parallel = gs.bulk_dprobs(tree, clipTo=(-1e6,1e6), comm=comm)
    for sl in serial:
        assert(np.linalg.norm(serial[sl]-parallel[sl]) < 1e-6)

    serial = gs.bulk_dprobs(tree, returnPr=True, clipTo=(-1e6,1e6))
    parallel = gs.bulk_dprobs(tree, returnPr=True, clipTo=(-1e6,1e6), comm=comm)
    for sl in serial:
        assert(np.linalg.norm(serial[sl][0]-parallel[sl][0]) < 1e-6)
        assert(np.linalg.norm(serial[sl][1]-parallel[sl][1]) < 1e-6)

    serial = gs.bulk_hprobs(tree, returnPr=True, returnDeriv=True,
                             clipTo=(-1e6,1e6))
    parallel = gs.bulk_hprobs(tree, returnPr=True,
                                 returnDeriv=True, clipTo=(-1e6,1e6), comm=comm)
    for sl in serial:
        assert(np.linalg.norm(serial[sl][0]-parallel[sl][0]) < 1e-6)
        assert(np.linalg.norm(serial[sl][1]-parallel[sl][1]) < 1e-6)
        assert(np.linalg.norm(serial[sl][2]-parallel[sl][2]) < 1e-6)

    # split tree =>  distribures on sub-trees prior to adjusting
    #                wrtBlockSize to accomodate remaining processors
    serial = gs.bulk_probs(tree, clipTo=(-1e6,1e6))
    parallel = gs.bulk_probs(split_tree, clipTo=(-1e6,1e6), comm=comm)
    for sl in serial:
        assert(np.linalg.norm(serial[sl]-parallel[sl]) < 1e-6)

    serial = gs.bulk_dprobs(tree, clipTo=(-1e6,1e6))
    parallel = gs.bulk_dprobs(split_tree, clipTo=(-1e6,1e6), comm=comm)
    for sl in serial:
        assert(np.linalg.norm(serial[sl]-parallel[sl]) < 1e-6)

    serial = gs.bulk_dprobs(tree, returnPr=True, clipTo=(-1e6,1e6))
    parallel = gs.bulk_dprobs(split_tree, returnPr=True, clipTo=(-1e6,1e6), comm=comm)
    for sl in serial:
        assert(np.linalg.norm(serial[sl][0]-parallel[sl][0]) < 1e-6)
        assert(np.linalg.norm(serial[sl][1]-parallel[sl][1]) < 1e-6)

    serial = gs.bulk_hprobs(tree, returnPr=True, returnDeriv=True,
                            clipTo=(-1e6,1e6))
    parallel = gs.bulk_hprobs(split_tree, returnPr=True,
                              returnDeriv=True, clipTo=(-1e6,1e6), comm=comm)
    for sl in serial:
        assert(np.linalg.norm(serial[sl][0]-parallel[sl][0]) < 1e-6)
        assert(np.linalg.norm(serial[sl][1]-parallel[sl][1]) < 1e-6)
        assert(np.linalg.norm(serial[sl][2]-parallel[sl][2]) < 1e-6)



@mpitest(4)
def test_MPI_fills(comm):

    #Create some gateset
    gs = std.gs_target.copy()
    gs.kick(0.1,seed=1234)

    #Get some gate strings
    maxLengths = [0,1,2]
    maxLengths = g_maxLengths
    gstrs = pygsti.construction.make_lsgst_experiment_list(
        std.gs_target.gates.keys(), std.fiducials, std.fiducials, std.germs, maxLengths)
    tree = gs.bulk_evaltree(gstrs)
    split_tree = tree.copy()
    split_tree.split(numSubTrees=g_numSubTrees)


    #Check fill probabilities

    spam_label_rows = { 'plus': 0, 'minus': 1 }
    nGateStrings = tree.num_final_strings()
    nDerivCols = gs.num_params()
    nSpamLabels = len(spam_label_rows)

    #Get serial results
    vhp_serial = np.empty( (nSpamLabels,nGateStrings,nDerivCols,nDerivCols),'d')
    vdp_serial = np.empty( (nSpamLabels,nGateStrings,nDerivCols), 'd' )
    vp_serial = np.empty( (nSpamLabels,nGateStrings), 'd' )

    vhp_serial2 = np.empty( (nSpamLabels,nGateStrings,nDerivCols,nDerivCols),'d')
    vdp_serial2 = np.empty( (nSpamLabels,nGateStrings,nDerivCols), 'd' )
    vp_serial2 = np.empty( (nSpamLabels,nGateStrings), 'd' )

    gs.bulk_fill_probs(vp_serial, spam_label_rows, tree,
                       (-1e6,1e6), comm=None)

    gs.bulk_fill_dprobs(vdp_serial, spam_label_rows, tree,
                        vp_serial2, (-1e6,1e6), comm=None,
                        wrtBlockSize=None)
    assert(np.linalg.norm(vp_serial2-vp_serial) < 1e-6)
    
    gs.bulk_fill_hprobs(vhp_serial, spam_label_rows, tree,
                        vp_serial2, vdp_serial2, (-1e6,1e6), comm=None,
                        wrtBlockSize=None)
    assert(np.linalg.norm(vp_serial2-vp_serial) < 1e-6)
    assert(np.linalg.norm(vdp_serial2-vdp_serial) < 1e-6)


    #Check serial results with a split tree, just to be sure
    gs.bulk_fill_probs(vp_serial2, spam_label_rows, split_tree,
                       (-1e6,1e6), comm=None)
    assert(np.linalg.norm(vp_serial2-vp_serial) < 1e-6)

    gs.bulk_fill_dprobs(vdp_serial2, spam_label_rows, split_tree,
                        vp_serial2, (-1e6,1e6), comm=None,
                        wrtBlockSize=None)
    assert(np.linalg.norm(vp_serial2-vp_serial) < 1e-6)
    assert(np.linalg.norm(vdp_serial2-vdp_serial) < 1e-6)
    
    gs.bulk_fill_hprobs(vhp_serial2, spam_label_rows, split_tree,
                        vp_serial2, vdp_serial2, (-1e6,1e6), comm=None,
                        wrtBlockSize=None)
    assert(np.linalg.norm(vp_serial2-vp_serial) < 1e-6)
    assert(np.linalg.norm(vdp_serial2-vdp_serial) < 1e-6)
    assert(np.linalg.norm(vhp_serial2-vhp_serial) < 1e-6)


    #Get parallel results - with and without split tree
    vhp_parallel = np.empty( (nSpamLabels,nGateStrings,nDerivCols,nDerivCols),'d')
    vdp_parallel = np.empty( (nSpamLabels,nGateStrings,nDerivCols), 'd' )
    vp_parallel = np.empty( (nSpamLabels,nGateStrings), 'd' )

    for tstTree in [tree, split_tree]:

        gs.bulk_fill_probs(vp_parallel, spam_label_rows, tstTree,
                           (-1e6,1e6), comm=comm)
        assert(np.linalg.norm(vp_parallel-vp_serial) < 1e-6)

        for blkSize in [None, 4]:
            gs.bulk_fill_dprobs(vdp_parallel, spam_label_rows, tstTree,
                                vp_parallel, (-1e6,1e6), comm=comm,
                                wrtBlockSize=blkSize)
            assert(np.linalg.norm(vp_parallel-vp_serial) < 1e-6)
            assert(np.linalg.norm(vdp_parallel-vdp_serial) < 1e-6)    

            gs.bulk_fill_hprobs(vhp_parallel, spam_label_rows, tstTree,
                                vp_parallel, vdp_parallel, (-1e6,1e6), comm=comm,
                                wrtBlockSize=blkSize)
            assert(np.linalg.norm(vp_parallel-vp_serial) < 1e-6)
            assert(np.linalg.norm(vdp_parallel-vdp_serial) < 1e-6)
            assert(np.linalg.norm(vhp_parallel-vhp_serial) < 1e-6)


    #Test Serial vs Parallel use of wrtFilter
    some_wrtFilter = [0,2,3,5,10]
    vhp_parallelF = np.empty( (nSpamLabels,nGateStrings,nDerivCols,len(some_wrtFilter)),'d')
    vdp_parallelF = np.empty( (nSpamLabels,nGateStrings,len(some_wrtFilter)), 'd' )

    for tstTree in [tree, split_tree]:

        gs._calc().bulk_fill_dprobs(vdp_parallelF, spam_label_rows, tstTree,
                            None, (-1e6,1e6), comm=comm,
                            wrtFilter=some_wrtFilter, wrtBlockSize=None)
        for ii,i in enumerate(some_wrtFilter):
            assert(np.linalg.norm(vdp_serial[:,:,i]-vdp_parallelF[:,:,ii]) < 1e-6)
        taken_result = vdp_serial.take( some_wrtFilter, axis=2 )
        assert(np.linalg.norm(taken_result-vdp_parallelF) < 1e-6)

        gs._calc().bulk_fill_hprobs(vhp_parallelF, spam_label_rows, tstTree,
                        None, None, (-1e6,1e6), comm=comm,
                        wrtFilter=some_wrtFilter, wrtBlockSize=None)

        for ii,i in enumerate(some_wrtFilter):
            assert(np.linalg.norm(vhp_serial[:,:,:,i]-vhp_parallelF[:,:,:,ii]) < 1e-6)
        taken_result = vhp_serial.take( some_wrtFilter, axis=3 )
        assert(np.linalg.norm(taken_result-vhp_parallelF) < 1e-6)


@mpitest(4)
def test_MPI_by_columns(comm):

    #Create some gateset
    gs = std.gs_target.copy()
    gs.kick(0.1,seed=1234)

    #Get some gate strings
    maxLengths = g_maxLengths
    gstrs = pygsti.construction.make_lsgst_experiment_list(
        std.gs_target.gates.keys(), std.fiducials, std.fiducials, std.germs, maxLengths)
    tree = gs.bulk_evaltree(gstrs)
    split_tree = tree.copy()
    split_tree.split(numSubTrees=g_numSubTrees)

    #Check that "by column" matches standard "at once" methods:

    spam_label_rows = { 'plus': 0, 'minus': 1 }
    nGateStrings = tree.num_final_strings()
    nDerivCols = gs.num_params()
    nSpamLabels = len(spam_label_rows)

    #Get serial results
    vhp_serial = np.empty( (nSpamLabels,nGateStrings,nDerivCols,nDerivCols),'d')
    vdp_serial = np.empty( (nSpamLabels,nGateStrings,nDerivCols), 'd' )
    vp_serial = np.empty( (nSpamLabels,nGateStrings), 'd' )


    gs.bulk_fill_hprobs(vhp_serial, spam_label_rows, tree,
                        vp_serial, vdp_serial, (-1e6,1e6), comm=None)
    dprobs12_serial = vdp_serial[:,:,:,None] * vdp_serial[:,:,None,:]

    for tstTree in [tree]: # currently no split trees allowed (ValueError), split_tree]:
        hcols = []
        d12cols = []
        for hprobs, dprobs12 in gs.bulk_hprobs_by_column(
            spam_label_rows, tstTree, True, clipTo=(-1e6,1e6) ):
            hcols.append(hprobs)
            d12cols.append(dprobs12)

        all_hcols = np.concatenate( hcols, axis=3 )
        all_d12cols = np.concatenate( d12cols, axis=3 )
        

        #print "SHAPES:"
        #print "hcols[0] = ",hcols[0].shape
        #print "all_hcols = ",all_hcols.shape
        #print "all_d12cols = ",all_d12cols.shape
        #print "vhp_serial = ",vhp_serial.shape
        #print "dprobs12_serial = ",dprobs12_serial.shape

        #for i in range(all_hcols.shape[3]):
        #    print "Diff(%d) = " % i, np.linalg.norm(all_hcols[0,:,8:,i]-vhp_serial[0,:,8:,i])
        #    if np.linalg.norm(all_hcols[0,:,8:,i]-vhp_serial[0,:,8:,i]) > 1e-6:
        #        for j in range(all_hcols.shape[3]):
        #            print "Diff(%d,%d) = " % (i,j), np.linalg.norm(all_hcols[0,:,8:,i]-vhp_serial[0,:,8:,j])
        #    assert(np.linalg.norm(all_hcols[0,:,8:,i]-vhp_serial[0,:,8:,i]) < 1e-6)

        assert(np.linalg.norm(all_hcols-vhp_serial) < 1e-6)

        #for i in range(all_d12cols.shape[3]):
        #    print "Diff(%d) = " % i, np.linalg.norm(all_d12cols[0,:,8:,i]-dprobs12_serial[0,:,8:,i])
        #    if np.linalg.norm(all_d12cols[0,:,8:,i]-dprobs12_serial[0,:,8:,i]) > 1e-6:
        #        for j in range(all_d12cols.shape[3]):
        #            print "Diff(%d,%d) = " % (i,j), np.linalg.norm(all_d12cols[0,:,8:,i]-dprobs12_serial[0,:,8:,j])
        assert(np.linalg.norm(all_d12cols-dprobs12_serial) < 1e-6)
        
        




#SCRATCH
#if np.linalg.norm(chk_ret[0]-dGs) >= 1e-6:
#    #if bScale:
#    #    print "SCALED"
#    #    print chk_ret[-1]
#
#    rank = comm.Get_rank()
#    if rank == 0:
#        print "DEBUG: parallel mismatch"
#        print "len(all_results) = ",len(all_results)
#        print "diff = ",np.linalg.norm(chk_ret[0]-dGs)
#        for row in range(dGs.shape[0]):
#            rowA = my_results[0][row,:].flatten()
#            rowB = all_results[rank][0][row,:].flatten()
#            rowC = dGs[row,:].flatten()
#            chk_C = chk_ret[0][row,:].flatten()
#
#            def sp(ar):
#                for i,x in enumerate(ar):
#                    if abs(x) > 1e-4:
#                        print i,":", x
#            def spc(ar1,ar2):
#                for i,x in enumerate(ar1):
#                    if (abs(x) > 1e-4 or abs(ar2[i]) > 1e-4): # and abs(x-ar2[i]) > 1e-6:
#                        print i,":", x, ar2[i], "(", (x-ar2[i]), ")", "[",x/ar2[i],"]"
#
#            assert( _np.linalg.norm(rowA-rowB) < 1e-6)
#            assert( _np.linalg.norm(rowC[0:len(rowA)]-rowA) < 1e-6)
#            #if _np.linalg.norm(rowA) > 1e-6:
#            if _np.linalg.norm(rowC - chk_C) > 1e-6:
#                print "SCALE for row%d = %g" % (row,rest_of_result[-1][row])
#                print "CHKSCALE for row%d = %g" % (row,chk_ret[-1][row])
#                print "row%d diff = " % row, _np.linalg.norm(rowC - chk_C)
#                print "row%d (rank%d)A = " % (row,rank)
#                sp(rowA)
#                print "row%d (all vs check) = " % row
#                spc(rowC, chk_C)
#
#                assert(False)
#    assert(False)





@mpitest(4)
def test_MPI_gatestrings_chi2(comm):
    #Individual processors
    my1ProcResults = runOneQubit("chi2")

    #Using all processors
    myManyProcResults = runOneQubit("chi2",comm,"gatestrings")

    #compare on root proc
    if comm.Get_rank() == 0:
        for gs1,gs2 in zip(my1ProcResults,myManyProcResults):
            gs2_go = pygsti.optimize_gauge(gs2, "target", targetGateset=gs1,
                                           gateWeight=1.0, spamWeight=1.0)
            print "Frobenius distance = ", gs1.frobeniusdist(gs2_go)
            assert(gs1.frobeniusdist(gs2_go) < 1e-5)
    return


@mpitest(4)
def test_MPI_gatestrings_logl(comm):
    #Individual processors
    my1ProcResults = runOneQubit("logl")

    #Using all processors
    myManyProcResults = runOneQubit("logl",comm,"gatestrings")

    #compare on root proc
    if comm.Get_rank() == 0:
        for gs1,gs2 in zip(my1ProcResults,myManyProcResults):
            gs2_go = pygsti.optimize_gauge(gs2, "target", targetGateset=gs1,
                                           gateWeight=1.0, spamWeight=1.0)
            print "Frobenius distance = ", gs1.frobeniusdist(gs2_go)
            assert(gs1.frobeniusdist(gs2_go) < 1e-5)
    return

@mpitest(4)
def test_MPI_derivcols(comm):
    #Individual processors
    my1ProcResults = runOneQubit("chi2")

    #Using all processors
    myManyProcResults = runOneQubit("chi2",comm,"deriv")

    #compare on root proc
    if comm.Get_rank() == 0:
        for gs1,gs2 in zip(my1ProcResults,myManyProcResults):
            gs2_go = pygsti.optimize_gauge(gs2, "target", targetGateset=gs1,
                                           gateWeight=1.0, spamWeight=1.0)
            print "Frobenius distance = ", gs1.frobeniusdist(gs2_go)
            assert(gs1.frobeniusdist(gs2_go) < 1e-5)
    return



if __name__ == "__main__":
    unittest.main(verbosity=2)

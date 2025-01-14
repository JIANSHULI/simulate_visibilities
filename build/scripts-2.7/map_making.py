import simulate_visibilities.Bulm as Bulm
import simulate_visibilities.simulate_visibilities as sv
import numpy as np
import numpy.linalg as la
import scipy.linalg as sla
import time, ephem, sys, os, resource
import aipy as ap
import matplotlib.pyplot as plt
import healpy as hp
import healpy.pixelfunc as hpf
import healpy.visufunc as hpv
import scipy.interpolate as si
import omnical.calibration_omni as omni

def pinv_sym(M, rcond = 1.e-15, verbose = True):
    eigvl,eigvc = la.eigh(M)
    max_eigv = max(eigvl)
    if verbose and min(eigvl) < 0 and np.abs(min(eigvl)) > max_eigv * rcond:
        print "!WARNING!: negative eigenvalue %.2e is smaller than the added identity %.2e! min rcond %.2e needed."%(min(eigvl), max_eigv * rcond, np.abs(min(eigvl))/max_eigv)
    eigvli = 1 / (max_eigv * rcond + eigvl)
    #for i in range(len(eigvli)):
        #if eigvl[i] < max_eigv * rcond:
            #eigvli[i] = 0
        #else:
            #eigvli[i] = 1/eigvl[i]
    return (eigvc*eigvli).dot(eigvc.transpose())

tag = "q3_abscalibrated"
datatag = '_seccasa_polcor.rad'
vartag = '_seccasa_polcor'
datadir = '/home/omniscope/data/GSM_data/absolute_calibrated_data/'
nt = 440
nf = 1
nUBL = 75
nside = 32
S_scale = 2
S_thresh = 1000#Kelvin
S_type = 'gsm%irm%i'%(S_scale,S_thresh)
plotcoord = 'C'
bnside = 8
lat_degree = 45.2977

plot_data_error = True
remove_additive = False
plot_projection = True
force_recompute = False
force_recompute_AtNiAi = False
force_recompute_S = False
force_recompute_SEi = False

C = 299.792458
kB = 1.3806488* 1.e-23

#deal with beam: create a dictionary for 'x' and 'y' each with a callable function of the form y(freq) in MHz
local_beam = {}
for p in ['x', 'y']:
    freqs = range(150,170,10)
    beam_array = np.zeros((len(freqs), 12*bnside**2))
    for f in range(len(freqs)):
        beam_array[f] = np.fromfile('/home/omniscope/simulate_visibilities/data/MWA_beam_in_healpix_horizontal_coor/nside=%i_freq=%i_%s%s.bin'%(bnside, freqs[f], p, p), dtype='float32')
    local_beam[p] = si.interp1d(freqs, beam_array, axis=0)

A = {}
data = {}
Ni = {}
data_shape = {}
ubl_sort = {}
for p in ['x', 'y']:
    pol = p+p

    #tf file
    tf_filename = datadir + tag + '_%s%s_%i_%i.tf'%(p, p, nt, nf)
    tflist = np.fromfile(tf_filename, dtype='complex64').reshape((nt,nf))
    tlist = np.real(tflist[:, 0])
    flist = np.imag(tflist[0, :])
    freq = flist[0]
    print freq

    #tf mask file, 0 means flagged bad data
    try:
        tfm_filename = datadir + tag + '_%s%s_%i_%i.tfm'%(p, p, nt, nf)
        tfmlist = np.fromfile(tfm_filename, dtype='float32').reshape((nt,nf))
        tmask = np.array(tfmlist[:,0].astype('bool'))
        #print tmask
    except:
        print "No mask file found"
        tmask = np.zeros_like(tlist).astype(bool)
    #print freq, tlist

    #ubl file
    ubl_filename = datadir + tag + '_%s%s_%i_%i.ubl'%(p, p, nUBL, 3)
    ubls = np.fromfile(ubl_filename, dtype='float32').reshape((nUBL, 3))
    print "%i UBLs to include"%len(ubls)


    #compute A matrix
    A_filename = datadir + tag + '_%s%s_%i_%i.A'%(p, p, len(tlist)*len(ubls), 12*nside**2)

    if os.path.isfile(A_filename) and not force_recompute:
        print "Reading A matrix from %s"%A_filename
        sys.stdout.flush()
        A[p] = np.fromfile(A_filename, dtype='complex64').reshape((len(ubls), len(tlist), 12*nside**2))[:,tmask].reshape((len(ubls)*len(tlist[tmask]), 12*nside**2))
    else:
        #beam
        beam_healpix = local_beam[p](freq)
        #hpv.mollview(beam_healpix, title='beam %s'%p)
        #plt.show()

        vs = sv.Visibility_Simulator()
        vs.initial_zenith = np.array([0, lat_degree*np.pi/180])#self.zenithequ
        beam_heal_equ = np.array(sv.rotate_healpixmap(beam_healpix, 0, np.pi/2 - vs.initial_zenith[1], vs.initial_zenith[0]))
        print "Computing A matrix for %s pol..."%p
        sys.stdout.flush()
        timer = time.time()
        A[p] = np.empty((len(tlist)*len(ubls), 12*nside**2), dtype='complex64')
        for i in range(12*nside**2):
            dec, ra = hpf.pix2ang(nside, i)#gives theta phi
            dec = np.pi/2 - dec
            print "\r%.1f%% completed, %f minutes left"%(100.*float(i)/(12.*nside**2), (12.*nside**2-i)/(i+1)*(float(time.time()-timer)/60.)),
            sys.stdout.flush()

            A[p][:, i] = np.array([vs.calculate_pointsource_visibility(ra, dec, d, freq, beam_heal_equ = beam_heal_equ, tlist = tlist) for d in ubls]).flatten()

        print "%f minutes used"%(float(time.time()-timer)/60.)
        sys.stdout.flush()
        A[p].tofile(A_filename)
        A[p] = A[p].reshape((len(ubls), len(tlist), 12*nside**2))[:,tmask].reshape((len(ubls)*len(tlist[tmask]), 12*nside**2))

    #get Ni (1/variance) and data
    var_filename = datadir + tag + '_%s%s_%i_%i%s.var'%(p, p, nt, nUBL,vartag)
    Ni[p] = 1./(np.fromfile(var_filename, dtype='float32').reshape((nt, nUBL))[tmask].transpose().flatten() * (1.e-26*(C/freq)**2/2/kB/(4*np.pi/(12*nside**2)))**2)
    data_filename = datadir + tag + '_%s%s_%i_%i'%(p, p, nt, nUBL) + datatag
    data[p] = (np.fromfile(data_filename, dtype='complex64').reshape((nt, nUBL))[tmask].transpose().flatten()*1.e-26*(C/freq)**2/2/kB/(4*np.pi/(12*nside**2))).conjugate()#there's a conjugate convention difference
    data_shape[p] = (nUBL, np.sum(tmask))
    ubl_sort[p] = np.argsort(la.norm(ubls, axis = 1))
print "Memory usage: %.3fMB"%(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1000)
sys.stdout.flush()
data = np.concatenate((data['x'],data['y']))
data = np.concatenate((np.real(data), np.imag(data))).astype('float32')
#plt.plot(Ni['x'][::nt])
#plt.show()
Ni = np.concatenate((Ni['x'],Ni['y']))
Ni = np.concatenate((Ni * 2, Ni * 2))

pix_mask_filename = datadir + tag + '_%i.pixm'%(len(A['x'][0]))
pix_mask = la.norm(A['x'],axis=0) != 0
pix_mask.astype('float32').tofile(pix_mask_filename)
print "Memory usage: %.3fMB"%(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1000)
npix = np.sum(pix_mask)

A = np.concatenate((np.real(A['x'][:, pix_mask]), np.real(A['y'][:, pix_mask]), np.imag(A['x'][:, pix_mask]), np.imag(A['y'][:, pix_mask]))).astype('float32') / 2 #factor of 2 for polarization: each pol only receives half energy
print "Memory usage: %.3fMB"%(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1000)

#compute AtNi
AtNi = A.transpose() * Ni
print "Memory usage: %.3fMB"%(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1000)
sys.stdout.flush()


#simulate
nside_standard = nside
pca1 = hp.fitsfunc.read_map('/home/omniscope/simulate_visibilities/data/gsm1.fits' + str(nside_standard))
pca2 = hp.fitsfunc.read_map('/home/omniscope/simulate_visibilities/data/gsm2.fits' + str(nside_standard))
pca3 = hp.fitsfunc.read_map('/home/omniscope/simulate_visibilities/data/gsm3.fits' + str(nside_standard))
gsm_standard = 422.952*(0.307706*pca1+-0.281772*pca2+0.0123976*pca3)
equatorial_GSM_standard = np.zeros(12*nside_standard**2,'float')
#rotate sky map
print "Rotating GSM_standard...",
sys.stdout.flush()
equ2013_to_gal_matrix = hp.rotator.Rotator(coord='cg').mat.dot(sv.epoch_transmatrix(2000,stdtime=2013.8))
ang0, ang1 =hp.rotator.rotateDirection(equ2013_to_gal_matrix, hpf.pix2ang(nside_standard, range(12*nside_standard**2)))
equatorial_GSM_standard = hpf.get_interp_val(gsm_standard, ang0, ang1)
print "done."
sys.stdout.flush()

sim_data_clean = A.dot(equatorial_GSM_standard[pix_mask])
noise_data = np.random.randn(len(data))/Ni**.5
sim_data = sim_data_clean + noise_data

vis_normalization = np.median(data / sim_data)
print "Normalization from visibilities", vis_normalization
diff_data = (sim_data * vis_normalization - data).reshape(2, len(data) / 2)
diff_data = diff_data[0] + 1j * diff_data[1]
diff_norm = {}
diff_norm['x'] = la.norm(diff_data[:data_shape['x'][0] * data_shape['x'][1]].reshape(*data_shape['x']), axis = 1)
diff_norm['y'] = la.norm(diff_data[data_shape['x'][0] * data_shape['x'][1]:].reshape(*data_shape['y']), axis = 1)

if plot_data_error:
        plt.plot(diff_norm['x'][ubl_sort['x']])
        plt.plot(diff_norm['y'][ubl_sort['y']])

if remove_additive:
    niter = 0
    additive = {'x':0, 'y':0}
    additive_inc = {'x':0, 'y':0}
    while niter == 0 or (abs(vis_normalization - np.median(data / sim_data)) > 1e-2 and niter < 20):
        niter += 1
        vis_normalization = np.median(data / sim_data)
        print "Normalization from visibilities", vis_normalization
        diff_data = (sim_data * vis_normalization - data).reshape(2, len(data) / 2)
        diff_data = diff_data[0] + 1j * diff_data[1]
        diff_norm = {}
        diff_norm['x'] = la.norm(diff_data[:data_shape['x'][0] * data_shape['x'][1]].reshape(*data_shape['x']), axis = 1)
        diff_norm['y'] = la.norm(diff_data[data_shape['x'][0] * data_shape['x'][1]:].reshape(*data_shape['y']), axis = 1)
        additive_inc['x'] = np.repeat(np.mean(diff_data[:data_shape['x'][0] * data_shape['x'][1]].reshape(*data_shape['x']), axis = 1, keepdims = True), data_shape['x'][1], axis = 1)
        additive_inc['y'] = np.repeat(np.mean(diff_data[data_shape['x'][0] * data_shape['x'][1]:].reshape(*data_shape['y']), axis = 1, keepdims = True), data_shape['y'][1], axis = 1)
        additive['x'] = additive['x'] + additive_inc['x']
        additive['y'] = additive['y'] + additive_inc['y']
        data = data + np.concatenate((np.real(np.concatenate((additive_inc['x'].flatten(), additive_inc['y'].flatten()))), np.imag(np.concatenate((additive_inc['x'].flatten(), additive_inc['y'].flatten())))))

if plot_data_error:
    vis_normalization = np.median(data / sim_data)
    print "Normalization from visibilities", vis_normalization
    diff_data = (sim_data * vis_normalization - data).reshape(2, len(data) / 2)
    diff_data = diff_data[0] + 1j * diff_data[1]
    diff_norm = {}
    diff_norm['x'] = la.norm(diff_data[:data_shape['x'][0] * data_shape['x'][1]].reshape(*data_shape['x']), axis = 1)
    diff_norm['y'] = la.norm(diff_data[data_shape['x'][0] * data_shape['x'][1]:].reshape(*data_shape['y']), axis = 1)
    plt.plot(diff_norm['x'][ubl_sort['x']])
    plt.plot(diff_norm['y'][ubl_sort['y']])
    plt.show()

#compute eigen stuff for AtNiAi
eigvl_filename = datadir + tag + '_%i%s.AtNiAel'%(npix, vartag)
eigvc_filename = datadir + tag + '_%i_%i%s.AtNiAev'%(npix, npix, vartag)

if os.path.isfile(eigvl_filename) and os.path.isfile(eigvc_filename):
    print "Reading eigen system of AtNiA from %s and %s"%(eigvl_filename, eigvc_filename)
    #del(AtNi)
    #del(A)
    eigvl = np.fromfile(eigvl_filename, dtype='float32')
    eigvc = np.fromfile(eigvc_filename, dtype='float32').reshape((npix, npix))
else:
    print "Computing AtNiA eigensystem...",
    sys.stdout.flush()
    timer = time.time()
    eigvl, eigvc = sla.eigh(AtNi.dot(A))
    print "%f minutes used"%(float(time.time()-timer)/60.)
    sys.stdout.flush()
    #del(AtNi)
    #del(A)
    if la.norm(eigvl) == 0:
        print "ERROR: Eigensistem calculation failed...matrix %i by %i is probably too large."%(npix, npix)
    print "%f minutes used"%(float(time.time()-timer)/60.)
    eigvl.tofile(eigvl_filename)
    eigvc.tofile(eigvc_filename)

#compute AtNiAi
rcondA = 1.e-4
AtNiAi_filename = datadir + tag + '_%i_%i%s.AtNiAi%i'%(npix, npix, vartag, np.log10(rcondA))

max_eigv = max(eigvl)
if min(eigvl) < 0 and np.abs(min(eigvl)) > max_eigv * rcondA:
    print "!WARNING!: negative eigenvalue %.2e is smaller than the added identity %.2e! min rcond %.2e needed."%(min(eigvl), max_eigv * rcondA, np.abs(min(eigvl))/max_eigv)
eigvli = 1 / (max_eigv * rcondA + eigvl)


if os.path.isfile(AtNiAi_filename) and not force_recompute_AtNiAi:
    print "Reading AtNiAi matrix from %s"%AtNiAi_filename
    AtNiAi = np.fromfile(AtNiAi_filename, dtype='float32').reshape((npix, npix))

else:
    print "Computing AtNiAi matrix...",
    sys.stdout.flush()
    timer = time.time()
    AtNiAi = (eigvc*eigvli).dot(eigvc.transpose())
    #AtNiAi = pinv_sym(AtNi.dot(A), rcond = rcondA)
    print "%f minutes used"%(float(time.time()-timer)/60.)
    AtNiAi.tofile(AtNiAi_filename)
print "Memory usage: %.3fMB"%(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1000)
sys.stdout.flush()


#compute raw x
x = np.zeros(12*nside**2, dtype='float32')
x[pix_mask] = AtNiAi.dot(AtNi.dot(data))


#simulation solution
sim_sol = np.zeros(12*nside**2, dtype='float32')
sim_sol[pix_mask] = AtNiAi.dot(AtNi.dot(sim_data))
noise_sol = np.zeros(12*nside**2, dtype='float32')
noise_sol[pix_mask] = AtNiAi.dot(AtNi.dot(noise_data))
sim_sol_clean = np.zeros(12*nside**2, dtype='float32')
sim_sol_clean[pix_mask] = AtNiAi.dot(AtNi.dot(sim_data_clean))

chisq = np.sum(Ni * np.abs((A.dot(x[pix_mask]) - data))**2) / float(len(data) - npix)
chisq_sim = np.sum(Ni * np.abs((A.dot(sim_sol[pix_mask]) - sim_data))**2) / float(len(sim_data) - npix)

del(A)
del(AtNi)



#compare measurement and simulation
if plot_projection:
    xproj = (x[pix_mask].dot(eigvc))[::-1] #eigvl, eigvc = sla.eigh(AtNi.dot(A))
    cleanproj = (sim_sol_clean[pix_mask].dot(eigvc))[::-1]
    print "normalization", np.median(xproj[:200]/cleanproj[:200])
    simproj = (sim_sol[pix_mask].dot(eigvc))[::-1]

    plt.subplot('211')
    plt.plot(xproj/np.median(xproj[:200]/cleanproj[:200]), 'b')
    plt.plot(cleanproj, 'g')
    plt.plot(simproj, 'r')
    plt.ylim(-3e4, 3e4)
    plt.subplot('212')
    plt.plot(xproj/np.median(xproj[:200]/cleanproj[:200])-cleanproj, 'b')
    plt.plot(simproj-cleanproj, 'r')
    plt.plot(eigvli[::-1]**.5, 'g')#(1/np.abs(eigvl[::-1])**.5)
    plt.ylim(-3e4, 3e4)
    plt.show()
    #hydrid_map = np.zeros_like(equatorial_GSM_standard)
    #hybrid = simproj
    #for cut in [0,100,500,1000,2000,3000,len(eigvl)]:
        #hybrid[:cut] = xproj[:cut]
        #hydrid_map = np.zeros_like(equatorial_GSM_standard)
        #hydrid_map[pix_mask] = eigvc.dot(hybrid[::-1])
        #hpv.mollview(np.log10(hydrid_map), min=0,max=4, coord=plotcoord, title='cut:%i'%cut)
    #dumb_w_filter = (np.abs(xproj[::-1]) / (eigvli**.5 + np.abs(xproj[::-1])))**2
    #hydrid_map[pix_mask] = eigvc.dot(xproj[::-1]* dumb_w_filter)
    #hpv.mollview(np.log10(hydrid_map), min=0,max=4, coord=plotcoord, title='dumb_wiener')
    #plt.show()


#compute S
S_filename = datadir + tag + '_%i_%i.2S_%s'%(len(AtNiAi), len(AtNiAi), S_type)
if os.path.isfile(S_filename) and not force_recompute_S:
    print "Reading S matrix %s..."%S_type,
    sys.stdout.flush()
    S = np.fromfile(S_filename, dtype = 'float32').reshape((len(AtNiAi), len(AtNiAi)))
else:
    print "Computing S matrix %s..."%S_type,
    sys.stdout.flush()
    timer = time.time()
    angular_scale = S_scale / (freq/300*np.max([la.norm(ubl) for ubl in ubls]))
    S = np.identity(12 * nside**2)
    S = np.maximum(np.array([hp.sphtfunc.smoothing(pix_vec, sigma = angular_scale, verbose = False) for pix_vec in S]), 0)[pix_mask][:, pix_mask]
    ps_mask = (equatorial_GSM_standard[pix_mask] > S_thresh) #mask for points with high flux
    S[ps_mask] = 0 #can't do these two operations at once
    S[:, ps_mask] = 0 #can't do these two operations at once
    S = S + np.diag(ps_mask.astype(int))
    S = S + np.identity(len(S)) * 1.e-2#to make S positive definite

    if 'uniform' in S_type:
        S = S * np.median(equatorial_GSM_standard)**2
    else:
        S = ((S*equatorial_GSM_standard[pix_mask]).transpose()*equatorial_GSM_standard[pix_mask]).transpose()
    print "%f minutes used"%(float(time.time()-timer)/60.)
    sys.stdout.flush()
    S.astype('float32').tofile(S_filename)
print "Memory usage: %.3fMB"%(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1000)
sys.stdout.flush()


##generalized eigenvalue problem
#genSEv_filename = datadir + tag + '_%i_%i.genSEv_%s_%i'%(len(S), len(S), S_type, np.log10(rcondA))
#genSEvec_filename = datadir + tag + '_%i_%i.genSEvec_%s_%i'%(len(S), len(S), S_type, np.log10(rcondA))
#print "Computing generalized eigenvalue problem...",
#sys.stdout.flush()
#timer = time.time()
#genSEv, genSEvec = sla.eigh(S, b=AtNiAi)
#print "%f minutes used"%(float(time.time()-timer)/60.)
#genSEv.tofile(genSEv_filename)
#genSEvec.tofile(genSEvec_filename)

#genSEvecplot = np.zeros_like(equatorial_GSM_standard)
#for eigs in [-1,-2,1,0]:
    #genSEvecplot[pix_mask] = genSEvec[:,eigs]
    #hpv.mollview(genSEvecplot, coord=plotcoord, title=genSEv[eigs])

#plt.show()
#quit()

SEi_filename = datadir + tag + '_%i_%i%s.CSEi_%s_%i'%(len(S), len(S), vartag, S_type, np.log10(rcondA))
if os.path.isfile(SEi_filename) and not force_recompute_SEi:
    print "Reading Wiener filter component...",
    sys.stdout.flush()
    SEi = sv.InverseCholeskyMatrix.fromfile(SEi_filename, len(S), 'float32')
else:
    print "Computing Wiener filter component...",
    sys.stdout.flush()
    timer = time.time()
    SEi = sv.InverseCholeskyMatrix(S + AtNiAi).astype('float32')
    SEi.tofile(SEi_filename)
    print "%f minutes used"%(float(time.time()-timer)/60.)
print "Memory usage: %.3fMB"%(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1000)
sys.stdout.flush()

print "Applying Wiener filter...",
sys.stdout.flush()
w_solution = np.zeros_like(x)
w_solution[pix_mask] = S.dot(SEi.dotv(x[pix_mask]))
w_GSM = np.zeros_like(equatorial_GSM_standard)
w_GSM[pix_mask] = S.dot(SEi.dotv(equatorial_GSM_standard[pix_mask]))
w_sim_sol = np.zeros_like(sim_sol)
w_sim_sol[pix_mask] = S.dot(SEi.dotv(sim_sol[pix_mask]))
print "Memory usage: %.3fMB"%(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1000)
sys.stdout.flush()
if False:
    hpv.mollview(equatorial_GSM_standard, min=0,max=5000, coord='CG', title='GSM')
    hpv.mollview(w_GSM, min=0,max=5000, coord='CG', title='wiener GSM')
    hpv.mollview(x, min=0,max=5000, coord='CG', title='raw solution')
    hpv.mollview(w_solution, min=0,max=5000, coord='CG', title='wiener solution')
    hpv.mollview(sim_sol, min=0,max=5000, coord='CG', title='simulated noisy solution')
    hpv.mollview(w_sim_sol, min=0,max=5000, coord='CG', title='simulated wiener noisy solution')
else:
    #hpv.mollview(np.log10(gsm_standard), min=0,max=4, coord='G', title='GSM')
    hpv.mollview(np.log10(equatorial_GSM_standard), min=0,max=4, coord=plotcoord, title='GSM')
    hpv.mollview(np.log10(w_GSM), min=0,max=4, coord=plotcoord, title='wiener GSM')
    hpv.mollview(np.log10(x), min=0,max=4, coord=plotcoord, title='raw solution, chi^2=%.2f'%chisq)
    hpv.mollview(np.log10(w_solution), min=0,max=4, coord=plotcoord, title='wiener solution')
    hpv.mollview(np.log10(w_GSM - w_solution), min=0,max=4, coord=plotcoord, title='wiener GSM - wiener solution')
    #hpv.mollview(np.log10(np.abs(w_solution)), min=0,max=4, coord=plotcoord, title='abs wiener solution')
    hpv.mollview(np.log10(sim_sol), min=0,max=4, coord=plotcoord, title='simulated noisy solution, chi^2=%.2f'%chisq_sim)
    hpv.mollview(np.log10(w_sim_sol), min=0,max=4, coord=plotcoord, title='simulated wiener noisy solution')
plt.show()

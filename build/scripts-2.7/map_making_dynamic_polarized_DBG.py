import simulate_visibilities.Bulm as Bulm
import simulate_visibilities.simulate_visibilities as sv
import numpy as np
import numpy.linalg as la
import scipy.linalg as sla
import time, ephem, sys, os, resource, datetime, warnings
import aipy as ap
import matplotlib.pyplot as plt
import healpy as hp
import healpy.pixelfunc as hpf
import healpy.visufunc as hpv
import scipy.interpolate as si

PI = np.pi
TPI = np.pi * 2



def pixelize(sky, nside_distribution, nside_standard, nside_start, thresh, final_index, thetas, phis, sizes):
    # thetas = []
    # phis = []
    for inest in range(12 * nside_start ** 2):
        pixelize_helper(sky, nside_distribution, nside_standard, nside_start, inest, thresh, final_index, thetas, phis,
                        sizes)
        # newt, newp = pixelize_helper(sky, nside_distribution, nside_standard, nside_start, inest, thresh, final_index, thetas, phis)
        # thetas += newt.tolist()
        # phis += newp.tolist()
        # return np.array(thetas), np.array(phis)


def pixelize_helper(sky, nside_distribution, nside_standard, nside, inest, thresh, final_index, thetas, phis, sizes):
    # print "visiting ", nside, inest
    starti, endi = inest * nside_standard ** 2 / nside ** 2, (inest + 1) * nside_standard ** 2 / nside ** 2
    ##local mean###if nside == nside_standard or np.std(sky[starti:endi])/np.mean(sky[starti:endi]) < thresh:
    #if np.mean(sky[starti:endi]) == 0.:
    #    nside_distribution[starti:endi] = 0
    #    final_index[starti:endi] = 0

    #el
    if nside == nside_standard or np.std(sky[starti:endi]) < thresh:
        nside_distribution[starti:endi] = nside
        final_index[starti:endi] = len(thetas)  # range(len(thetas), len(thetas) + endi -starti)
        # return hp.pix2ang(nside, [inest], nest=True)
        newt, newp = hp.pix2ang(nside, [inest], nest=True)
        thetas += newt.tolist()
        phis += newp.tolist()
        sizes += (np.ones_like(newt) * nside_standard ** 2 / nside ** 2).tolist()
        # sizes += (np.ones_like(newt) / nside**2).tolist()

    else:
        # thetas = []
        # phis = []
        for jnest in range(inest * 4, (inest + 1) * 4):
            pixelize_helper(sky, nside_distribution, nside_standard, nside * 2, jnest, thresh, final_index, thetas,
                            phis, sizes)
            # newt, newp = pixelize_helper(sky, nside_distribution, nside_standard, nside * 2, jnest, thresh)
            # thetas += newt.tolist()
            # phis += newp.tolist()
            # return np.array(thetas), np.array(phis)


def dot(A, B, C, nchunk=10):
    if A.ndim != 2 or B.ndim != 2 or C.ndim != 2:
        raise ValueError("A B C not all have 2 dims: %i %i %i" % (str(A.ndim), str(B.ndim), str(C.ndim)))

    chunk = len(C) / nchunk
    for i in range(nchunk):
        C[i * chunk:(i + 1) * chunk] = A[i * chunk:(i + 1) * chunk].dot(B)
    if chunk * nchunk < len(C):
        C[chunk * nchunk:] = A[chunk * nchunk:].dot(B)


def ATNIA(A, Ni, C, nchunk=10):  # C=AtNiA
    if A.ndim != 2 or C.ndim != 2 or Ni.ndim != 1:
        raise ValueError("A, AtNiA and Ni not all have correct dims: %i %i" % (str(A.ndim), str(C.ndim), str(Ni.ndim)))

    chunk = len(C) / nchunk
    for i in range(nchunk):
        C[i * chunk:(i + 1) * chunk] = (A[:, i * chunk:(i + 1) * chunk].transpose() * Ni).dot(A)
    if chunk * nchunk < len(C):
        C[chunk * nchunk:] = (A[:, chunk * nchunk:].transpose() * Ni).dot(A)


nside_start = 32
nside_beamweight = 16
nside_standard = 32#//512
bnside = 512
plotcoord = 'CG'
thresh = 2.0
valid_pix_thresh = -1#//1e-3
# S_scale = 2
# S_thresh = 1000#Kelvin
# S_type = 'gsm%irm%i'%(S_scale,S_thresh)
S_type = 'dySP'  # dynamic S polarized [[.25,0,0,.25], [0,p,0,0], [0,0,p,0], [.25,0,0,.25]]
remove_additive = True

lat_degree = 45.2977
C = 299.792458
kB = 1.3806488 * 1.e-23
script_dir = os.path.dirname(os.path.realpath(__file__))

plot_pixelization = True
plot_projection = True
plot_data_error = True

force_recompute = False
force_recompute_AtNiAi_eig = False
force_recompute_AtNiAi = False
force_recompute_S = False
force_recompute_SEi = False

####################################################
################data file and load beam##############
####################################################
tag = "q3A_abscal"  # L stands for lenient in flagging
datatag = '_2015_05_09'
vartag = '_2015_05_09'
datadir = '/home/omniscope/data/GSM_data/absolute_calibrated_data/'
nt = {"q3A_abscal": 253, "q3AL_abscal": 368}[tag]
nf = 1
nUBL = 78

# deal with beam: create a callable function of the form y(freq) in MHz and returns npix by 4
freqs = range(110, 200, 10)
raw_beam_data = np.concatenate([np.fromfile(
    '/home/omniscope/data/mwa_beam/healpix_%i_%s.bin' % (bnside, p), dtype='complex64').reshape(
    (len(freqs), 12 * bnside ** 2, 2)) for p in ['x', 'y']], axis=-1).transpose(0, 2, 1) #freq by 4 by pix
local_beam = si.interp1d(freqs, raw_beam_data, axis=0)

##debug starts
theta = PI/2
ps_vec = sv.stoc([1, theta, PI/2])
# local_zenith_vect = np.array([sv.stoc([1, theta, 0]), sv.stoc([1, theta, PI])])
#
# ps_equ_north_plane = np.cross([0,0,1], ps_vec)
# ps_equ_north_plane /= la.norm(ps_equ_north_plane)#normal vector of the plane defined by point source vec and north vec in equatorial
# ps_local_north_plane_t = np.cross(local_zenith_vect, ps_vec)
# ps_local_north_plane_t /= la.norm(ps_local_north_plane_t, axis = -1)[:, None]#normal vector of the plane defined by point source vec and north vec in local coord
# print -np.sign(np.cross(ps_local_north_plane_t, ps_equ_north_plane).dot(ps_vec)) * np.arccos(ps_local_north_plane_t.dot(ps_equ_north_plane)) / PI
# sys.exit(0)
# phi0 = np.cross([0,0,1], -ps_vec)
# phi0 = phi0/la.norm(phi0)
# print "phi0", sv.ctos(phi0)/PI
# alpha0 = np.cross([0,0,1], phi0)
# alpha0 = alpha0/la.norm(alpha0)
# print "alpha0", sv.ctos(alpha0)/PI
# phi1t = np.cross(local_zenith_vect, -ps_vec)
#
# if np.min(la.norm(local_zenith_vect-(-ps_vec), axis = -1)) == 0.:
#     if la.norm(np.cross([0,0,1], -ps_vec)) != 0:
#         phi1t[np.argmin(la.norm(local_zenith_vect-(-ps_vec), axis = -1))] = np.cross([0,0,1], -ps_vec)
#     else:
#         phi1t[np.argmin(la.norm(local_zenith_vect-(-ps_vec), axis = -1))] = np.array([0, 1, 0])
# phi1t = phi1t / (la.norm(phi1t, axis=-1))
# print "phi1t", sv.ctos(phi1t)/PI
# Ranglet = np.arctan2(phi1t.dot(alpha0), phi1t.dot(phi0))
# print "final", Ranglet/PI
# sys.exit(0)


sv.plot_jones(local_beam(160))

vstest = sv.Visibility_Simulator()
vstest.initial_zenith = np.array([0, 0])

beam_heal_equ = np.array(
            [sv.rotate_healpixmap(beam_healpixi, 0, np.pi / 2 - vstest.initial_zenith[1], vstest.initial_zenith[0]) for
             beam_healpixi in local_beam(160)])
print beam_heal_equ.shape

# ps_xxxyyxyy = [1,0,0,0]
# plt.subplot(2,1,1)
# plt.plot(np.abs(vstest.calculate_pol_pointsource_visibility(0, 0, [0,1,0], 160, beam_healpix_hor=local_beam(160), tlist=np.arange(-12,12,.01)%24)[0].dot(ps_xxxyyxyy)).reshape(4,2400).transpose())
# plt.subplot(2,1,2)
# plt.plot(np.angle(vstest.calculate_pol_pointsource_visibility(0, 0, [0,1,0], 160, beam_healpix_hor=local_beam(160), tlist=np.arange(-12,12,.01)%24)[0].dot(ps_xxxyyxyy)).reshape(4,2400).transpose())
# plt.show()
# sys.exit(0)

A = {}

for p in ['x', 'y']:
    pol = p + p

    # tf file, t in lst hours
    tf_filename = datadir + tag + '_%s%s_%i_%i.tf' % (p, p, nt, nf)
    tflist = np.fromfile(tf_filename, dtype='complex64').reshape((nt, nf))
    tlist = np.real(tflist[:, 0])
    flist = np.imag(tflist[0, :])
    freq = flist[0]

    # tf mask file, 0 means flagged bad data
    try:
        tfm_filename = datadir + tag + '_%s%s_%i_%i.tfm' % (p, p, nt, nf)
        tfmlist = np.fromfile(tfm_filename, dtype='float32').reshape((nt, nf))
        tmask = np.array(tfmlist[:, 0].astype('bool'))
        # print tmask
    except:
        print "No mask file found"
        tmask = np.ones_like(tlist).astype(bool)
    # print freq, tlist

    # ubl file
    ubl_filename = datadir + tag + '_%s%s_%i_%i.ubl' % (p, p, nUBL, 3)
    ubls = np.fromfile(ubl_filename, dtype='float32').reshape((nUBL, 3))
    print "%i UBLs to include, longest baseline is %i wavelengths" % (
    len(ubls), np.max(np.linalg.norm(ubls, axis=1)) / (C / freq))

    A_filename = datadir + tag + '_%s%s_%i_%i.A' % (p, p, len(tlist) * len(ubls), 12 * nside_beamweight ** 2)

    if os.path.isfile(A_filename) and not force_recompute:
        print "Reading A matrix from %s" % A_filename
        sys.stdout.flush()
        A[p] = np.fromfile(A_filename, dtype='complex64').reshape((len(ubls), len(tlist), 12 * nside_beamweight ** 2))[
               :, tmask].reshape((len(ubls) * len(tlist[tmask]), 12 * nside_beamweight ** 2))
    else:
        # beam
        if p == 'x':
            beam_healpix = abs(local_beam(freq)[0]) ** 2 + abs(local_beam(freq)[1]) ** 2
        elif p == 'y':
            beam_healpix = abs(local_beam(freq)[2]) ** 2 + abs(local_beam(freq)[3]) ** 2
        # hpv.mollview(beam_healpix, title='beam %s'%p)
        # plt.show()

        vs = sv.Visibility_Simulator()
        vs.initial_zenith = np.array([0, lat_degree * np.pi / 180])  # self.zenithequ
        beam_heal_equ = np.array(
            sv.rotate_healpixmap(beam_healpix, 0, np.pi / 2 - vs.initial_zenith[1], vs.initial_zenith[0]))
        print "Computing A matrix for %s pol..." % p
        sys.stdout.flush()
        timer = time.time()
        A[p] = np.empty((len(tlist) * len(ubls), 12 * nside_beamweight ** 2), dtype='complex64')
        for i in range(12 * nside_beamweight ** 2):
            dec, ra = hpf.pix2ang(nside_beamweight, i)  # gives theta phi
            dec = np.pi / 2 - dec
            print "\r%.1f%% completed, %f minutes left" % (100. * float(i) / (12. * nside_beamweight ** 2),
                                                           (12. * nside_beamweight ** 2 - i) / (i + 1) * (
                                                           float(time.time() - timer) / 60.)),
            sys.stdout.flush()

            A[p][:, i] = np.array(
                [vs.calculate_pointsource_visibility(ra, dec, d, freq, beam_heal_equ=beam_heal_equ, tlist=tlist) for d
                 in ubls]).flatten()

        print "%f minutes used" % (float(time.time() - timer) / 60.)
        sys.stdout.flush()
        A[p].tofile(A_filename)
        A[p] = A[p].reshape((len(ubls), len(tlist), 12 * nside_beamweight ** 2))[:, tmask].reshape(
            (len(ubls) * len(tlist[tmask]), 12 * nside_beamweight ** 2))

####################################################
###beam weights using an equal pixel A matrix######
#################################################
print "Computing beam weight...",
sys.stdout.flush()
beam_weight = ((la.norm(A['x'], axis=0) ** 2 + la.norm(A['y'], axis=0) ** 2) ** .5)[
    hpf.nest2ring(nside_beamweight, range(12 * nside_beamweight ** 2))]
beam_weight = beam_weight / np.mean(beam_weight)
beam_weight = np.array([beam_weight for i in range(nside_standard ** 2 / nside_beamweight ** 2)]).transpose().flatten()
print "done."
sys.stdout.flush()

################################################
#####################GSM###########################
#############################################
pca1 = hp.fitsfunc.read_map(script_dir + '/../data/gsm1.fits' + str(nside_standard))
pca2 = hp.fitsfunc.read_map(script_dir + '/../data/gsm2.fits' + str(nside_standard))
pca3 = hp.fitsfunc.read_map(script_dir + '/../data/gsm3.fits' + str(nside_standard))
components = np.loadtxt(script_dir + '/../data/components.dat')
scale_loglog = si.interp1d(np.log(components[:, 0]), np.log(components[:, 1]))
w1 = si.interp1d(components[:, 0], components[:, 2])
w2 = si.interp1d(components[:, 0], components[:, 3])
w3 = si.interp1d(components[:, 0], components[:, 4])
gsm_standard = np.exp(scale_loglog(np.log(freq))) * (w1(freq) * pca1 + w2(freq) * pca2 + w3(freq) * pca3)

# rotate sky map and converts to nest
equatorial_GSM_standard = np.zeros(12 * nside_standard ** 2, 'float')
print "Rotating GSM_standard and converts to nest...",
sys.stdout.flush()
equ2013_to_gal_matrix = hp.rotator.Rotator(coord='cg').mat.dot(sv.epoch_transmatrix(2000, stdtime=2013.58))
ang0, ang1 = hp.rotator.rotateDirection(equ2013_to_gal_matrix,
                                        hpf.pix2ang(nside_standard, range(12 * nside_standard ** 2), nest=True))
equatorial_GSM_standard = hpf.get_interp_val(gsm_standard, ang0, ang1)
print "done."
sys.stdout.flush()



########################################################################
########################processing dynamic pixelization######################
########################################################################

nside_distribution = np.zeros(12 * nside_standard ** 2)
final_index = np.zeros(12 * nside_standard ** 2)
thetas, phis, sizes = [], [], []
abs_thresh = np.mean(equatorial_GSM_standard * beam_weight) * thresh
pixelize(equatorial_GSM_standard * beam_weight, nside_distribution, nside_standard, nside_start, abs_thresh,
         final_index, thetas, phis, sizes)
npix = len(thetas)
valid_pix_mask = hpf.get_interp_val(beam_weight, thetas, phis, nest=True) > valid_pix_thresh * max(beam_weight)
valid_npix = np.sum(valid_pix_mask)
fake_solution = (hpf.get_interp_val(equatorial_GSM_standard, thetas, phis, nest=True) * sizes)[valid_pix_mask]
fake_solution = np.concatenate(
    (fake_solution, np.zeros_like(fake_solution), np.zeros_like(fake_solution), np.zeros_like(fake_solution)))
sizes = np.concatenate((np.array(sizes)[valid_pix_mask], np.array(sizes)[valid_pix_mask],
                        np.array(sizes)[valid_pix_mask], np.array(sizes)[valid_pix_mask]))


def sol2map(solx, renorm=True):
    final_index4 = np.concatenate(
        (final_index, final_index + npix, final_index + npix * 2, final_index + npix * 3)).astype(int)
    full_sol = np.zeros(4 * npix)
    full_sol[np.concatenate((valid_pix_mask, valid_pix_mask, valid_pix_mask, valid_pix_mask))] = solx / (sizes if renorm else 1)
    return full_sol[final_index4]


# final_index_filename = datadir + tag + '_%i.dyind%i_%.3f'%(nside_standard, npix, thresh)
# final_index.astype('float32').tofile(final_index_filename)
# sizes_filename = final_index_filename.replace('dyind', "dysiz")
# np.array(sizes).astype('float32').tofile(sizes_filename)
if plot_pixelization:
    ##################################################################
    ####################################sanity check########################
    ###############################################################
    # npix = 0
    # for i in nside_distribution:
    # npix += i**2/nside_standard**2
    # print npix, len(thetas)

    stds = np.std((equatorial_GSM_standard * beam_weight).reshape(12 * nside_standard ** 2 / 4, 4), axis=1)

    ##################################################################
    ####################################plotting########################
    ###############################################################
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=RuntimeWarning)
        hpv.mollview(beam_weight, min=0, max=4, coord=plotcoord, title='beam', nest=True)
        hpv.mollview(np.log10(equatorial_GSM_standard), min=0, max=4, coord=plotcoord, title='GSM', nest=True)
        hpv.mollview(np.log10(sol2map(fake_solution)[:len(equatorial_GSM_standard)]), min=0, max=4, coord=plotcoord,
                     title='GSM gridded', nest=True)
        hpv.mollview(np.log10(stds / abs_thresh), min=np.log10(thresh) - 3, max=3, coord=plotcoord, title='std',
                     nest=True)
        hpv.mollview(np.log2(nside_distribution), min=np.log2(nside_start), max=np.log2(nside_standard),
                     coord=plotcoord,
                     title='count %i %.3f' % (len(thetas), float(len(thetas)) / (12 * nside_standard ** 2)), nest=True)
    plt.show()


##################################################################
####################compute dynamic A matrix########################
###############################################################
ubls = {}
for p in ['x', 'y']:
    ubl_filename = datadir + tag + '_%s%s_%i_%i.ubl' % (p, p, nUBL, 3)
    ubls[p] = np.fromfile(ubl_filename, dtype='float32').reshape((nUBL, 3))
common_ubls = np.array([u for u in ubls['x'] if (u in ubls['y'] or -u in ubls['y'])])
ubl_index = {}  # stored index in each pol's ubl for the common ubls
for p in ['x', 'y']:
    ubl_index[p] = np.zeros(len(common_ubls), dtype='int')
    for i, u in enumerate(common_ubls):
        if u in ubls[p]:
            ubl_index[p][i] = np.argmin(la.norm(ubls[p] - u, axis=-1)) + 1
        elif -u in ubls[p]:
            ubl_index[p][i] = - np.argmin(la.norm(ubls[p] + u, axis=-1)) - 1
        else:
            raise Exception('Logical Error')
# vs = sv.Visibility_Simulator()
# vs.initial_zenith = np.array([0, lat_degree*np.pi/180])#self.zenithequ
# beam_heal_equ = np.array([sv.rotate_healpixmap(beam_healpixi, 0, np.pi/2 - vs.initial_zenith[1], vs.initial_zenith[0]) for beam_healpixi in local_beam(freq)])
# print vs.calculate_pol_pointsource_visibility(0, .5, ubls[0], freq, beam_heal_equ = beam_heal_equ, tlist = tlist).shape
# sys.exit(0)

A_filename = datadir + tag + '_%i_%i.AdpcIQUV%i_%.3f' % (len(tlist) * len(common_ubls), valid_npix, nside_standard, thresh)


def get_A():
    if os.path.isfile(A_filename) and not force_recompute:
        print "Reading A matrix from %s" % A_filename
        sys.stdout.flush()
        A = np.fromfile(A_filename, dtype='complex64').reshape((len(common_ubls), 4, len(tlist), 4, valid_npix))
    else:
        # beam
        beam_healpix = local_beam(freq)
        # hpv.mollview(beam_healpix, title='beam %s'%p)
        # plt.show()

        vs = sv.Visibility_Simulator()
        vs.initial_zenith = np.array([0, lat_degree * np.pi / 180])  # self.zenithequ
        beam_heal_equ = np.array(
            [sv.rotate_healpixmap(beam_healpixi, 0, np.pi / 2 - vs.initial_zenith[1], vs.initial_zenith[0]) for
             beam_healpixi in local_beam(freq)])
        print "Computing A matrix..."
        sys.stdout.flush()
        A = np.empty((len(common_ubls), 4 * len(tlist), 4, valid_npix), dtype='complex64')
        timer = time.time()
        for n, i in enumerate(np.arange(npix)[valid_pix_mask]):
            ra = phis[i]
            dec = np.pi / 2 - thetas[i]
            print "\r%.1f%% completed, %f minutes left" % (100. * float(n) / (valid_npix), float(valid_npix - n) / (n + 1) * (float(time.time() - timer) / 60.)),
            sys.stdout.flush()

            A[..., n] = vs.calculate_pol_pointsource_visibility(ra, dec, common_ubls, freq, beam_heal_equ=beam_heal_equ, tlist=tlist)\
                .dot([[.5, .5, 0, 0], [0, 0, .5, .5j], [0, 0, .5, -.5j], [.5, -.5, 0, 0]])

        print "%f minutes used" % (float(time.time() - timer) / 60.)
        sys.stdout.flush()
        A.tofile(A_filename)
        A.shape = (len(common_ubls), 4, len(tlist), 4, valid_npix)
    tmask = np.ones_like(tlist).astype(bool)
    for p in ['x', 'y']:
        # tf mask file, 0 means flagged bad data
        try:
            tfm_filename = datadir + tag + '_%s%s_%i_%i.tfm' % (p, p, nt, nf)
            tfmlist = np.fromfile(tfm_filename, dtype='float32').reshape((nt, nf))
            tmask = tmask & np.array(tfmlist[:, 0].astype('bool'))
            # print tmask
        except:
            print "No mask file found"
            # print freq, tlist
    # Merge A
    A.shape = (len(common_ubls) * 4 * len(tlist[tmask]), 4 * valid_npix)
    try:
        return np.concatenate((np.real(A), np.imag(A)))
    except MemoryError:
        print "Not enough memory, concatenating A on disk ", A_filename + 'tmpre', A_filename + 'tmpim',
        sys.stdout.flush()
        Ashape = list(A.shape)
        Ashape[0] = Ashape[0] * 2
        np.real(A).tofile(A_filename + 'tmpre')
        np.imag(A).tofile(A_filename + 'tmpim')
        del (A)
        os.system("cat %s >> %s" % (A_filename + 'tmpim', A_filename + 'tmpre'))

        os.system("rm %s" % (A_filename + 'tmpim'))
        A = np.fromfile(Ashape, dtype='float32')
        os.system("rm %s" % (A_filename + 'tmpre'))
        print "done."
        sys.stdout.flush()
        return A


A = get_A()
exit(0)
# Compute autocorr
beam_healpix = local_beam(freq)
vs = sv.Visibility_Simulator()
vs.initial_zenith = np.array([0, lat_degree * np.pi / 180])  # self.zenithequ
beam_heal_equ = np.array(
    [sv.rotate_healpixmap(beam_healpixi, 0, np.pi / 2 - vs.initial_zenith[1], vs.initial_zenith[0]) for beam_healpixi in
     local_beam(freq)])
print "Computing autocorr..."
sys.stdout.flush()
timer = time.time()
autocorr = np.empty((4 * len(tlist), 4, valid_npix), dtype='complex64')

for n, i in enumerate(np.arange(npix)[valid_pix_mask]):
    ra = phis[i]
    dec = np.pi / 2 - thetas[i]
    print "\r%.1f%% completed, %f minutes left" % (
    100. * float(n) / (valid_npix), float(valid_npix - n) / (n + 1) * (float(time.time() - timer) / 60.)),
    sys.stdout.flush()

    autocorr[..., n] = \
    vs.calculate_pol_pointsource_visibility(ra, dec, [[0, 0, 0]], freq, beam_heal_equ=beam_heal_equ, tlist=tlist)[
        0].dot([[.5, .5, 0, 0], [0, 0, .5, .5j], [0, 0, .5, -.5j], [.5, -.5, 0, 0]])

print "%f minutes used" % (float(time.time() - timer) / 60.)
sys.stdout.flush()
autocorr_vis = autocorr.reshape(4 * len(tlist), 4 * valid_npix).dot(fake_solution).reshape(4, len(tlist))
autocorr_vis = np.ones_like(autocorr_vis)

data = {}
Ni = {}
data_shape = {}
ubl_sort = {}
for p in ['x', 'y']:
    for p2 in ['x', 'y']:
        pol = p + p2
        # tf file
        tf_filename = datadir + tag + '_%s%s_%i_%i.tf' % (p, p2, nt, nf)
        tflist = np.fromfile(tf_filename, dtype='complex64').reshape((nt, nf))
        tlist = np.real(tflist[:, 0])

        # ubl file
        ubl_filename = datadir + tag + '_%s%s_%i_%i.ubl' % (p, p2, nUBL, 3)
        ubls = np.fromfile(ubl_filename, dtype='float32').reshape((nUBL, 3))
        print "%i UBLs to include, longest baseline is %i wavelengths" % (
        len(common_ubls), np.max(np.linalg.norm(common_ubls, axis=1)) / (C / freq))


        # get Ni (1/variance) and data
        var_filename = datadir + tag + '_%s%s_%i_%i' % (p, p2, nt, nUBL) + vartag + '.var'
        Ni[pol] = 1. / (np.fromfile(var_filename, dtype='float32').reshape((nt, nUBL))[tmask].transpose()[
                            abs(ubl_index[p]) - 1].flatten() * (
                        1.e-26 * (C / freq) ** 2 / 2 / kB / (4 * np.pi / (12 * nside_standard ** 2))) ** 2)
        data_filename = datadir + tag + '_%s%s_%i_%i' % (p, p2, nt, nUBL) + datatag
        data[pol] = np.fromfile(data_filename, dtype='complex64').reshape((nt, nUBL))[tmask].transpose()[
            abs(ubl_index[p]) - 1]
        data[pol][ubl_index[p] < 0] = data[pol][ubl_index[p] < 0].conjugate()
        data[pol] = (data[pol].flatten() * 1.e-26 * (C / freq) ** 2 / 2 / kB / (
        4 * np.pi / (12 * nside_standard ** 2))).conjugate()  # there's a conjugate convention difference
        data_shape[pol] = (len(common_ubls), np.sum(tmask))
        ubl_sort[p] = np.argsort(la.norm(common_ubls, axis=1))
print "Memory usage: %.3fMB" % (resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1000)
sys.stdout.flush()

# Merge data
original_data = np.array([data['xx'], data['xy'], data['yx'], data['yy']]).reshape(
    [4] + list(data_shape['xx'])).transpose((1, 0, 2))
data = np.array([data['xx'], data['xy'], data['yx'], data['yy']]).reshape([4] + list(data_shape['xx'])).transpose(
    (1, 0, 2)).flatten()
data = np.concatenate((np.real(data), np.imag(data))).astype('float32')  #r/i by ubl by pol by time
Ni = np.concatenate((Ni['xx'], Ni['xy'], Ni['yx'], Ni['yy'])).reshape([4] + list(data_shape['xx'])).transpose(
    (1, 0, 2)).flatten()
Ni = np.concatenate((Ni / 2, Ni / 2))
print "Memory usage: %.3fMB" % (resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1000)
sys.stdout.flush()

# simulate visibilities

# clean_sim_data = np.array([Aiter.dot(fake_solution) for Aiter in A])
clean_sim_data = A.dot(fake_solution.astype(A.dtype))

def get_complex_data(flat_real_data, nubl, nt):
    if len(flat_real_data) != 2 * nubl * 4 * nt:
        raise ValueError("Incorrect dimensions: data has length %i where nubl %i and nt %i together require length of %i."%(len(flat_real_data), nubl, nt, 2 * nubl * 4 * nt))

    flat_real_data.shape = (2, nubl, 4, nt)
    result = flat_real_data[0] + 1.j * flat_real_data[1]
    flat_real_data.shape = 2 * nubl * 4 * nt
    return result



def get_vis_normalization(data, clean_sim_data):
    a = np.linalg.norm(data.reshape(2, data_shape['xx'][0], 4, data_shape['xx'][1])[:, :, [0, 3]], axis=0).flatten()
    b = np.linalg.norm(clean_sim_data.reshape(2, data_shape['xx'][0], 4, data_shape['xx'][1])[:, :, [0, 3]],
                       axis=0).flatten()
    return a.dot(b) / b.dot(b)


vis_normalization = get_vis_normalization(data, clean_sim_data)
print "Normalization from visibilities", vis_normalization
diff_data = (clean_sim_data * vis_normalization - data).reshape(2, len(data) / 2)
diff_data = diff_data[0] + 1j * diff_data[1]
diff_norm = {}
diff_norm['x'] = la.norm(diff_data.reshape(data_shape['xx'][0], 4, data_shape['xx'][1])[:, 0], axis=1)
diff_norm['y'] = la.norm(diff_data.reshape(data_shape['yy'][0], 4, data_shape['yy'][1])[:, 3], axis=1)

if plot_data_error:
    plt.plot(diff_norm['x'][ubl_sort['x']])
    plt.plot(diff_norm['y'][ubl_sort['y']])

# todo use autocorr rather than constant as removal term
if remove_additive:
    niter = 0

    additive = 0
    while niter == 0 or (abs(vis_normalization - get_vis_normalization(data, clean_sim_data)) > 1e-2 and niter < 20):
        niter += 1
        vis_normalization = get_vis_normalization(data, clean_sim_data)
        print "Normalization from visibilities", vis_normalization
        diff_data = (clean_sim_data * vis_normalization - data).reshape(2, data_shape['xx'][0], 4, data_shape['xx'][1])
        diff_data = diff_data[0] + 1j * diff_data[1]
        diff_norm = {}
        diff_norm['x'] = la.norm(diff_data[:, 0], axis=1)
        diff_norm['y'] = la.norm(diff_data[:, 3], axis=1)

        additive_inc = np.zeros_like(diff_data)
        for p in range(4):
            if p == 0 or p == 3:
                additive_inc[:, p] = np.outer(
                    autocorr_vis[p].dot(diff_data[:, p].transpose()) / np.sum(autocorr_vis[p] ** 2), autocorr_vis[p])
            else:
                additive_inc[:, p] = np.outer(
                    (autocorr_vis[0] + autocorr_vis[3]).dot(diff_data[:, p].transpose()) / np.sum(
                        (autocorr_vis[0] + autocorr_vis[3]) ** 2), (autocorr_vis[0] + autocorr_vis[3]))

        additive = additive + additive_inc
        data = data + np.concatenate((np.real(additive_inc.flatten()), np.imag(additive_inc.flatten())))

    if plot_data_error:
        vis_normalization = get_vis_normalization(data, clean_sim_data)
        print "Normalization from visibilities", vis_normalization
        diff_data = (clean_sim_data * vis_normalization - data).reshape(2, len(data) / 2)
        diff_data = diff_data[0] + 1j * diff_data[1]
        diff_norm = {}
        diff_norm['x'] = la.norm(diff_data.reshape(data_shape['xx'][0], 4, data_shape['xx'][1])[:, 0], axis=1)
        diff_norm['y'] = la.norm(diff_data.reshape(data_shape['yy'][0], 4, data_shape['yy'][1])[:, 3], axis=1)
        plt.plot(diff_norm['x'][ubl_sort['x']])
        plt.plot(diff_norm['y'][ubl_sort['y']])
plt.show()


# vis_normalization = np.median(np.concatenate((np.real(data) / np.real(clean_sim_data), np.imag(data) / np.imag(clean_sim_data))))
# print "Normalization from visibilities", vis_normalization
# diff_data = (clean_sim_data * vis_normalization - data)
# diff_norm = {}
# diff_norm['x'] = la.norm(diff_data[:data_shape['x'][0] * data_shape['x'][1]].reshape(*data_shape['x']), axis = 1)
# diff_norm['y'] = la.norm(diff_data[data_shape['x'][0] * data_shape['x'][1]:].reshape(*data_shape['y']), axis = 1)

# if plot_data_error:
# plt.plot(diff_norm['x'][ubl_sort['x']], label='original x error')
# plt.plot(diff_norm['y'][ubl_sort['y']], label='original y error')

# if remove_additive:
# niter = 0
# additive = {'x':0, 'y':0}
# additive_inc = {'x':0, 'y':0}
# while niter == 0 or (abs(vis_normalization - np.median(np.concatenate((np.real(data) / np.real(clean_sim_data), np.imag(data) / np.imag(clean_sim_data))))) > 1e-2 and niter < 20):
# niter += 1
# vis_normalization = np.median(np.concatenate((np.real(data) / np.real(clean_sim_data), np.imag(data) / np.imag(clean_sim_data))))
# print "Normalization from visibilities", vis_normalization
# diff_data = clean_sim_data * vis_normalization - data
# diff_norm = {}
# diff_norm['x'] = la.norm(diff_data[:data_shape['x'][0] * data_shape['x'][1]].reshape(*data_shape['x']), axis = 1)
# diff_norm['y'] = la.norm(diff_data[data_shape['x'][0] * data_shape['x'][1]:].reshape(*data_shape['y']), axis = 1)
# additive_inc['x'] = np.repeat(np.mean(diff_data[:data_shape['x'][0] * data_shape['x'][1]].reshape(*data_shape['x']), axis = 1, keepdims = True), data_shape['x'][1], axis = 1)
# additive_inc['y'] = np.repeat(np.mean(diff_data[data_shape['x'][0] * data_shape['x'][1]:].reshape(*data_shape['y']), axis = 1, keepdims = True), data_shape['y'][1], axis = 1)
# additive['x'] = additive['x'] + additive_inc['x']
# additive['y'] = additive['y'] + additive_inc['y']
# data = data + np.concatenate((additive_inc['x'].flatten(), additive_inc['y'].flatten()))

# if plot_data_error:
# vis_normalization = np.median(np.concatenate((np.real(data) / np.real(clean_sim_data), np.imag(data) / np.imag(clean_sim_data))))
# print "Normalization from visibilities", vis_normalization
# diff_data = clean_sim_data * vis_normalization - data
# diff_norm = {}
# diff_norm['x'] = la.norm(diff_data[:data_shape['x'][0] * data_shape['x'][1]].reshape(*data_shape['x']), axis = 1)
# diff_norm['y'] = la.norm(diff_data[data_shape['x'][0] * data_shape['x'][1]:].reshape(*data_shape['y']), axis = 1)
# plt.plot(diff_norm['x'][ubl_sort['x']], label='new x error')
# plt.plot(diff_norm['y'][ubl_sort['y']], label='new y error')
# plt.legend();plt.show()

##renormalize the model
fake_solution = fake_solution * vis_normalization
clean_sim_data = clean_sim_data * vis_normalization
sim_data = clean_sim_data + np.random.randn(len(data)) / Ni ** .5


# compute AtNi and AtNi.y

AtNi = A.transpose() * Ni
print "Memory usage: %.3fMB" % (resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1000)
sys.stdout.flush()

AtNi_data = AtNi.dot(data.astype(AtNi.dtype))
AtNi_sim_data = AtNi.dot(sim_data.astype(AtNi.dtype))
# AtNi_data = np.array([AtNiiter.dot(data) for AtNiiter in AtNi])
# AtNi_sim_data = np.array([AtNiiter.dot(sim_data) for AtNiiter in AtNi])


precision = 'float64'
# compute AtNiA eigensystems
eigvl_filename = datadir + tag + '_%i%s_IQUV_%s.AtNiAel' % (valid_npix, vartag, precision)
eigvc_filename = datadir + tag + '_%i_%i%s_IQUV_%s.AtNiAev' % (valid_npix, valid_npix, vartag, precision)
if os.path.isfile(eigvl_filename) and os.path.isfile(eigvc_filename) and not force_recompute_AtNiAi_eig:
    print "Reading eigen system of AtNiA from %s and %s" % (eigvl_filename, eigvc_filename)
    sys.stdout.flush()
    del (AtNi)
    del (A)
    if precision != 'longdouble':
        eigvl = np.fromfile(eigvl_filename, dtype=precision)
        eigvc = np.fromfile(eigvc_filename, dtype=precision).reshape((4 * valid_npix, 4 * valid_npix))
    else:
        eigvl = np.fromfile(eigvl_filename, dtype='float64')
        eigvc = np.fromfile(eigvc_filename, dtype='float64').reshape((4 * valid_npix, 4 * valid_npix))
else:
    print "Allocating AtNiA..."
    sys.stdout.flush()
    timer = time.time()
    AtNiA = np.zeros((len(AtNi), len(AtNi)), dtype=precision)
    print "Computing AtNiA...", datetime.datetime.now()
    sys.stdout.flush()
    ATNIA(A, Ni, AtNiA)
    # for i in range(len(AtNiA)):
    # AtNiA[i] = AtNi[i].dot(A)

    print "%f minutes used" % (float(time.time() - timer) / 60.)
    sys.stdout.flush()
    del (AtNi)
    del (A)
    print "Computing AtNiA eigensystem...", datetime.datetime.now()
    sys.stdout.flush()
    timer = time.time()
    eigvl, eigvc = sla.eigh(AtNiA)
    print "%f minutes used" % (float(time.time() - timer) / 60.)
    sys.stdout.flush()
    del (AtNiA)

    if la.norm(eigvl) == 0:
        print "ERROR: Eigensistem calculation failed...matrix %i by %i is probably too large." % (
        4 * valid_npix, 4 * valid_npix)
    eigvl.tofile(eigvl_filename)
    eigvc.tofile(eigvc_filename)

plt.plot(eigvl)

# compute AtNiAi
precision = 'float64'
if eigvl.dtype != precision or eigvc.dtype != precision:
    print "casting eigen system from %s to %s" % (eigvl.dtype, precision)
    eigvl = eigvl.astype(precision)
    eigvc = eigvc.astype(precision)
max_eigv = np.max(eigvl)
lambd = 1e-12
rcondA = (lambd) / max_eigv
eigvli = 1. / (max_eigv * rcondA + np.maximum(eigvl, 0))


def get_AtNiAi(rcondA):
    AtNiAi_filename = datadir + tag + '_%i_%i%s_IQUV.AtNiAi%s%.1f' % (
    valid_npix, valid_npix, vartag, precision, np.log10(rcondA))
    if os.path.isfile(AtNiAi_filename) and not force_recompute_AtNiAi:
        print "Reading AtNiAi matrix from %s" % AtNiAi_filename
        return np.fromfile(AtNiAi_filename, dtype=precision).reshape((4 * valid_npix, 4 * valid_npix))

    else:

        eigvli = 1. / (max_eigv * rcondA + np.maximum(eigvl, 0))
        print "Allocating AtNiAi..."
        sys.stdout.flush()
        timer = time.time()
        AtNiAi = np.zeros((len(eigvc), len(eigvc)), dtype=eigvc.dtype)
        print "Computing AtNiAi...", datetime.datetime.now()
        sys.stdout.flush()
        ATNIA(eigvc.transpose(), eigvli, AtNiAi)
        print "%f minutes used" % (float(time.time() - timer) / 60.)
        sys.stdout.flush()
        AtNiAi.tofile(AtNiAi_filename)
        return AtNiAi


AtNiAi = get_AtNiAi(rcondA)
print "Memory usage: %.3fMB" % (resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1000)
sys.stdout.flush()

# solve for x
x = AtNiAi.dot(AtNi_data.astype(AtNiAi.dtype))
sim_x = AtNiAi.dot(AtNi_sim_data.astype(AtNiAi.dtype))
sim_x_clean = fake_solution
del (AtNiAi)
A = get_A()
if remove_additive:
    chisq = np.sum(Ni * np.abs((A.dot(x.astype(A.dtype)) - data)) ** 2) / float(
        len(data) - valid_npix - data_shape['xx'][0] - data_shape['yy'][0])
else:
    chisq = np.sum(Ni * np.abs((A.dot(x.astype(A.dtype)) - data)) ** 2) / float(len(data) - valid_npix)
chisq_sim = np.sum(Ni * np.abs((A.dot(sim_x.astype(A.dtype)) - sim_data)) ** 2) / float(len(sim_data) - valid_npix)

#####investigate optimal rcondA
print "lambda we use is", max_eigv * rcondA
print "best lambda inferred from data is", (len(data) - chisq * float(len(data) - valid_npix)) / np.sum(x ** 2)
print "best lambda inferred from simulated data is", (len(data) - chisq_sim * float(
    len(sim_data) - valid_npix)) / np.sum(sim_x ** 2)
del (A)
# compare measurement and simulation
if plot_projection:
    xproj = (x.dot(eigvc))[::-1]
    cleanproj = (sim_x_clean.dot(eigvc))[::-1]
    print "normalization", np.median(xproj[:200] / cleanproj[:200])
    simproj = (sim_x.dot(eigvc))[::-1]

    plt.subplot('211')
    plt.plot(xproj, 'b')
    plt.plot(cleanproj, 'g')
    plt.plot(simproj, 'r')
    plt.ylim(-3e5, 3e5)
    plt.subplot('212')
    plt.plot(xproj - cleanproj, 'b')
    plt.plot(simproj - cleanproj, 'r')
    plt.plot(eigvli[::-1] ** .5, 'g')  # (1/np.abs(eigvl[::-1])**.5)
    plt.ylim(-3e5, 3e5)
    plt.show()


    plt.plot(range(0, 30000, 100), np.log10(np.mean(np.abs(xproj - cleanproj)[:30000].reshape(300, 100)**2, axis=1)**.5), 'b--', label='data diff')
    plt.plot(range(0, 30000, 100), np.log10(np.mean(np.abs(simproj - cleanproj)[:30000].reshape(300, 100)**2, axis=1)**.5), 'r--', label='noisy sim diff')
    plt.plot(range(0, 30000, 100), np.log10(eigvli[::-1][:30000:100] ** .5), 'g--', label='eigenvalue diff')
    plt.plot(range(0, 30000, 100), np.log10(np.mean(np.abs(cleanproj)[:30000].reshape(300, 100)**2, axis=1)**.5), 'g', label='GSM solution')
    plt.plot(range(0, 30000, 100), np.log10(np.mean(np.abs(xproj)[:30000].reshape(300, 100)**2, axis=1)**.5), 'b', label='data solution')
    plt.legend()
    plt.show()



# compute S
print "computing S...",
sys.stdout.flush()
timer = time.time()

pol_frac = .4  # assuming QQ=UU=pol_frac*II
S = np.zeros((len(x), len(x)), dtype='float32')
for i in range(len(x) / 4):
    S[i::len(x) / 4, i::len(x) / 4] = np.array([[1, 0, 0, 0], [0, pol_frac, 0, 0], [0, 0, pol_frac, 0], [0, 0, 0, 0]]) * \
                                      sim_x_clean[
                                          i] ** 2  # np.array([[1+pol_frac,0,0,1-pol_frac],[0,pol_frac,pol_frac,0],[0,pol_frac,pol_frac,0],[1-pol_frac,0,0,1+pol_frac]]) / 4 * (2*sim_x_clean[i])**2
# S = np.diag(sim_x_clean**2.)
print "Done."
print "%f minutes used" % (float(time.time() - timer) / 60.)
sys.stdout.flush()

##generalized eigenvalue problem
# genSEv_filename = datadir + tag + '_%i_%i.genSEv_%s_%i'%(len(S), len(S), S_type, np.log10(rcondA))
# genSEvec_filename = datadir + tag + '_%i_%i.genSEvec_%s_%i'%(len(S), len(S), S_type, np.log10(rcondA))
# print "Computing generalized eigenvalue problem...",
# sys.stdout.flush()
# timer = time.time()
# genSEv, genSEvec = sla.eigh(S, b=AtNiAi)
# print "%f minutes used"%(float(time.time()-timer)/60.)
# genSEv.tofile(genSEv_filename)
# genSEvec.tofile(genSEvec_filename)

# genSEvecplot = np.zeros_like(equatorial_GSM_standard)
# for eigs in [-1,-2,1,0]:
# genSEvecplot[pix_mask] = genSEvec[:,eigs]
# hpv.mollview(genSEvecplot, coord=plotcoord, title=genSEv[eigs])

# plt.show()
# quit()

#####compute wiener filter##############
# lambd = 1e-12
# rcondA = (lambd) / max_eigv
SEi_filename = datadir + tag + '_%i_%i%s.CSEi_IQUV_%s_%s_%.1f' % (
len(S), len(S), vartag, S_type, precision, np.log10(rcondA))
if os.path.isfile(SEi_filename) and not force_recompute_SEi:
    print "Reading Wiener filter component...",
    sys.stdout.flush()
    SEi = sv.InverseCholeskyMatrix.fromfile(SEi_filename, len(S), precision)
else:
    print "Computing Wiener filter component...",
    sys.stdout.flush()
    timer = time.time()
    AtNiAi = get_AtNiAi(rcondA)
    SEi = sv.InverseCholeskyMatrix(S + AtNiAi).astype(precision)
    SEi.tofile(SEi_filename, overwrite=True)
    print "%f minutes used" % (float(time.time() - timer) / 60.)
print "Memory usage: %.3fMB" % (resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1000)
sys.stdout.flush()

#####apply wiener filter##############
print "Applying Wiener filter...",
sys.stdout.flush()
w_solution = S.dot(SEi.dotv(x))
w_GSM = S.dot(SEi.dotv(sim_x_clean))
w_sim_sol = S.dot(SEi.dotv(sim_x))
print "Memory usage: %.3fMB" % (resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1000)
sys.stdout.flush()


def plot_IQU(solution, title, col, ncol=6, eigen=False, eigrange=0.03):
    # Es=solution[np.array(final_index).tolist()].reshape((4, len(final_index)/4))
    # I = Es[0] + Es[3]
    # Q = Es[0] - Es[3]
    # U = Es[1] + Es[2]
    IQUV = sol2map(solution, renorm=(not eigen))
    IQUV.shape = (4, IQUV.shape[0] / 4)
    I = IQUV[0]
    Q = IQUV[1]
    U = IQUV[2]
    V = IQUV[3]
    pangle = 180 * np.arctan2(Q, U) / 2 / PI
    plotcoordtmp = 'C'
    if eigen:
        hpv.mollview(I, min=-eigrange, max=eigrange, coord=plotcoordtmp, title=title, nest=True, sub=(4, ncol, col))
    else:
        hpv.mollview(np.log10(I), min=0, max=4, coord=plotcoordtmp, title=title, nest=True, sub=(4, ncol, col))

    if eigen:
        hpv.mollview(Q, min=-eigrange, max=eigrange, coord=plotcoordtmp, title=title, nest=True, sub=(4, ncol, ncol + col))
        hpv.mollview(U, min=-eigrange, max=eigrange, coord=plotcoordtmp, title=title, nest=True, sub=(4, ncol, 2 * ncol + col))
    else:
        hpv.mollview((Q ** 2 + U ** 2) ** .5 / I, min=0, max=1, coord=plotcoordtmp, title=title, nest=True,
                     sub=(4, ncol, ncol + col))
        from matplotlib import cm
        cool_cmap = cm.hsv
        cool_cmap.set_under("w")  # sets background to white
        hpv.mollview(pangle, min=-90, max=90, coord=plotcoordtmp, title=title, nest=True, sub=(4, ncol, 2 * ncol + col),
                     cmap=cool_cmap)

    if eigen:
        hpv.mollview(V, min=-eigrange, max=eigrange, coord=plotcoordtmp, title=title, nest=True,
                 sub=(4, ncol, 3 * ncol + col))
    else:
        hpv.mollview(np.arcsinh(V) / np.log(10), min=-np.arcsinh(10. ** 4) / np.log(10),
                 max=np.arcsinh(10. ** 4) / np.log(10), coord=plotcoordtmp, title=title, nest=True,
                 sub=(4, ncol, 3 * ncol + col))
    if col == ncol:
        plt.show()


plot_IQU(fake_solution, 'GSM gridded', 1)
plot_IQU(x, 'raw solution, chi^2=%.2f' % chisq, 2)
plot_IQU(sim_x, 'raw simulated solution, chi^2=%.2f' % chisq_sim, 3)
plot_IQU(w_GSM, 'wienered GSM', 4)
plot_IQU(w_solution, 'wienered solution', 5)
plot_IQU(w_sim_sol, 'wienered simulated solution', 6)

# hpv.mollview(np.log10(fake_solution[np.array(final_index).tolist()]), min= 0, max =4, coord=plotcoord, title='GSM gridded', nest=True)
# hpv.mollview(np.log10((x/sizes)[np.array(final_index).tolist()]), min=0, max=4, coord=plotcoord, title='raw solution, chi^2=%.2f'%chisq, nest=True)
# hpv.mollview(np.log10((sim_x/sizes)[np.array(final_index).tolist()]), min=0, max=4, coord=plotcoord, title='raw simulated solution, chi^2=%.2f'%chisq_sim, nest=True)
# hpv.mollview(np.log10((w_GSM/sizes)[np.array(final_index).tolist()]), min=0, max=4, coord=plotcoord, title='wienered GSM', nest=True)
# hpv.mollview(np.log10((w_solution/sizes)[np.array(final_index).tolist()]), min=0, max=4, coord=plotcoord, title='wienered solution', nest=True)
# hpv.mollview(np.log10((w_sim_sol/sizes)[np.array(final_index).tolist()]), min=0, max=4, coord=plotcoord, title='wienered simulated solution', nest=True)
# plt.show()

#gradually replace GSM model projections by data solution projections and see when it starts to look bad
partial_sols = np.zeros((6, len(x)))
for i in range(len(partial_sols)):
    n_replace = i * 2000
    tmp_proj = np.copy(cleanproj)
    tmp_proj[:n_replace] = xproj[:n_replace]
    partial_sols[i] = tmp_proj[::-1].dot(np.transpose(eigvc))
    plot_IQU(partial_sols[i], str(n_replace), i + 1, ncol=len(partial_sols))

#plot 2000 sections of model projection and solution projection and see if any section looks particularly bad
partial_sols = np.zeros((6, len(x)))
for i in range(len(partial_sols)):
    n_replace = i * 2000
    tmp_proj = np.zeros_like(x)
    tmp_proj[n_replace:(n_replace + 2000)] = xproj[n_replace:(n_replace + 2000)]
    partial_sols[i] = tmp_proj[::-1].dot(np.transpose(eigvc))
    plot_IQU(partial_sols[i], str(n_replace) + '-' + str(n_replace + 2000), i + 1, ncol=len(partial_sols))

partial_sols = np.zeros((6, len(x)))
for i in range(len(partial_sols)):
    n_replace = i * 2000
    tmp_proj = np.zeros_like(x)
    tmp_proj[n_replace:(n_replace + 2000)] = cleanproj[n_replace:(n_replace + 2000)]
    partial_sols[i] = tmp_proj[::-1].dot(np.transpose(eigvc))
    plot_IQU(partial_sols[i], str(n_replace) + '-' + str(n_replace + 2000), i + 1, ncol=len(partial_sols))

#Plot the polarization factors of the first few eigen modes
prange = 40
for i in range(4):
    plt.subplot(5, 1, i+1)
    plt.plot(la.norm(eigvc[i*len(eigvc)/4:(i+1)*len(eigvc)/4, ::-1], axis=0)[:prange]**2)
plt.subplot(5, 1, 5)
plt.plot(np.abs(xproj[:prange]))
plt.plot(np.abs(cleanproj[:prange]))
plt.show()

#plot the first few eigen modes
for i in range(10):
    plot_IQU(eigvc[:, -i-1], str(i), i+1, ncol=10, eigen=True, eigrange=0.03)


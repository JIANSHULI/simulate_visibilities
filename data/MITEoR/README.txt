MITEoR Visibility Data Release May 22, 2016.
Jeff Zheng. E-mail: jeff.h.zheng@gmail.com

###############################################
Visibility Data
###############################################
All data files are ascii text file in .txt format. The file names start with frequency in MHz, followed by polarization (x is EW and y is NS) and optional observation number (A or B).

The files contain 2D data arrays, with the first dimension (slower varying) being time, and the second dimension (faster varying) being baseline.

The first column of each row is the local sidereal time in hours (0-24). The coordinate for MITEoR is LAT: 45.297728 LON: -69.987182.

After the first column, each row comes in triplets.

The first entry (first row first column) is always 0.

The triplets in the first row are coordinates for the baseline vectors in meters, in south, east and up direction, (S, E, U).

The triplets for the rest of the rows are the real part, imaginary part, and the variance for the visibilities, (Re, Im, Var). The variance is the sum of variance in real and imaginary parts.

For example, for a toy text file that reads:

0 1 2 3 4 5 6
7 8 9 10 11 12 13
14 15 16 17 18 19 20

This file contains 2 time stamps and 2 baselines. The time stamps in local sidereal hour are 7 and 14, and the baseline vectors are (1,2,3) and (4,5,6).
The visibilities for baseline (1,2,3) are 8+9i and 15+16i, and for (4,5,6) 11+12i and 18+19i.
The variances for baseline (1,2,3) are 10 and 17, and for (4,5,6) 13 and 20.

###############################################
Beam Data
###############################################
The beam model was simulated by Victor Buza using E&M software based on the MWA bowtie on a strip of ground screen.
In each of the x.txt or y.txt, there is a 2D array, the first (slower varying) dimension is frequency, with the 9 rows corresponding to 9 frequencies, 110 MHz to 190 MHz with 10 MHz spacing. The second (faster varying) dimension is sky direction in HEALPIX format with nside = 64. At each heal pix direction, there are four numbers, (az re/im, alt re/im). To obtain the unpolarized beam, simply take the root-mean-square of all four numbers. When simulating visibilities such as xx pol, one needs to square the beam.

#!/usr/bin/python
import time
import os
import sys
import re
import pandas as pd
import numpy as np
import tabix
import glob
import ConfigParser
from bisect import bisect_left
# from joblib import Parallel, delayed
# import multiprocessing

start = time.time()

# n_cores = multiprocessing.cpu_count()
# print str(n_cores)+" cores detected"

if len(sys.argv)<2:
	sys.exit('ERROR: not enough arguments\nUSAGE ./getLD.py <filedir>')

filedir = sys.argv[1]
if re.match(".+\/$", filedir) is None:
	filedir += '/'

###################
# get config files
###################
cfg = ConfigParser.ConfigParser()
cfg.read(os.path.dirname(os.path.realpath(__file__))+'/app.config')

param = ConfigParser.ConfigParser()
param.read(filedir+'params.config')

###################
# get parameters
###################
leadSNPs = param.get('inputfiles', 'leadSNPsfile')
if leadSNPs == "NA":
    print "prefedined lead SNPs are not provided"
    leadSNPs = None
else:
    print "predefined lead SNPs are procided"
    leadSNPs = filedir+"input.lead"
addleadSNPs = int(param.get('inputfiles', 'addleadSNPs')) #1 to add, 0 to not add
regions = param.get('inputfiles', 'regionsfile')
if regions == "NA":
    print "predefined genomic regions are not provided"
    regions = None
else:
    print "predefined gwnomic regions are provided"
    regions = filedir+"input.regions"

pop = param.get('params', 'pop')
leadP = float(param.get('params', 'leadP'))
KGSNPs = int(param.get('params', 'Incl1KGSNPs')) #1 to add, 0 to not add
gwasP = float(param.get('params', 'gwasP'))
maf = float(param.get('params', 'MAF'))
r2 = float(param.get('params', 'r2'))
mergeDist = int(param.get('params', 'mergeDist'))
MHC = int(param.get('params', 'exMHC')) # 1 to exclude, 0 to not
extMHC = param.get('params', 'extMHC')
MHCstart = 29624758 # hg19
MHCend = 33160276 # hg19
if extMHC != "NA":
    mhc = extMHC.split("-")
    MHCstart = int(mhc[0])
    MHCend = int(mhc[1])

# orcol = param.get('inputfiles', 'orcol')
# becol = param.get('inputfiles', 'becol')
# secol = param.get('inputfiles', 'secol')
#
# if orcol == "NA":
#     orcol = None
# if becol == "NA":
#     becol = None
# if secol == "NA":
#     secol = None

###################
# input files
###################
gwas = filedir+"input.snps"

###################
# get column index
###################
chrcol = 0
poscol = 1
refcol = 2
altcol = 3
rsIDcol = 4
pcol = 5
orcol = None
becol = None
secol = None

f = open(gwas, 'r')
head = f.readline()
f.close()
head = head.strip().split()
for i in range(0,len(head)):
	if head[i] == "or":
		orcol = i
	elif head[i] == "beta":
		becol = i
	elif head[i] == "se":
		secol = i

###################
# output files
###################
ldout = filedir+"ld.txt"
snpsout = filedir+"snps.txt"
annotout = filedir+"annot.txt"
annovin = filedir+"annoc.input"

with open(ldout, 'w') as o:
	o.write("\t".join(["SNP1","SNP2","r2"])+"\n")

ohead = "\t".join(["uniqID", "rsID", "chr", "pos", "ref", "alt", "MAF", "gwasP"])
if orcol:
	ohead += "\tor"
if becol:
	ohead += "\tbeta"
if secol:
	ohead += "\tse"
ohead += "\n"
with open(snpsout, 'w') as o:
	o.write(ohead)

ohead = "\t".join(["uniqID", "CADD", "RDB"])
chr15files = cfg.get('data', 'chr15')
chr15files = glob.glob(chr15files+"/*.bed.gz")
chr15files.sort()
for c in chr15files:
	m = re.match(r".+\/(E\d+)_.+", c)
	ohead += "\t"+m.group(1)
ohead += "\n"
with open(annotout, 'w') as o:
	o.write(ohead)

###################
# region file
# 0: chr, 1: start, 2: end
###################
if regions:
	regions = pd.read_table(regions, comment="#", delim_whitespace=True)
	regions = regions.as_matrix()

###################
# lead SNPs file
# 0: rsID, 1: chr, 2: pos
###################
def rsIDup(snps, rsIDi):
	dbSNPfile = cfg.get('data', 'dbSNP')
	#rsIDs = pd.read_table(dbSNPfile+"/RsMerge146.txt", header=None)
	#rsIDs = rsIDs.as_matrix()
	#rsIDs = rsIDs[rsIDs[:,0].argsort()]
	#rsIDset = set(rsIDs[:,0])
	rsID = np.memmap(dbSNPfile+"/RsMerge146.npy", mode='r', dtype='int', shape=(11684784, 3))

	for i in range(0, len(snps)):
		rs = int(snps[i,rsIDi].replace('rs', ''))
		if rs in rsID[:,0]:
			rs = 'rs'+str(rsID[rsID[:,0]==rs,1])
			snps[i, rsIDi] = rs
	return snps

if leadSNPs:
	leadSNPs = pd.read_table(leadSNPs, comment="#", delim_whitespace=True)
	leadSNPs = leadSNPs.as_matrix()
	leadSNPs = rsIDup(leadSNPs, 0)

###################
# get chr row numbers
###################
gwasfile_chr = []
chr_cur = 0
row = 0
gwasf = open(gwas, 'r')
gwasf.readline()
for l in gwasf:
	row += 1
	l = re.match(r"(\d+)\t.+", l)
	chr_tmp = int(l.group(1))
	if chr_tmp == chr_cur:
		gwasfile_chr[chr_cur-1][2] += 1
	else:
		chr_cur = chr_tmp
		gwasfile_chr.append([chr_cur, row, 1])
gwasf.close()

gwasfile_chr = np.array(gwasfile_chr)
for l in gwasfile_chr:
	print "\t".join(l.astype(str))
refgenome = cfg.get('data', 'refgenome')

def chr_process(ichrom):
	chrom = gwasfile_chr[ichrom][0]
	print "Start chromosome "+str(chrom)+" ..."
	regions_tmp = None
	if regions is not None:
		regions_tmp = regions[regions[:,0]==chrom]
		if len(regions_tmp)==0:
			return [], [], []

	leadSNPs_tmp = None
	if leadSNPs is not None:
		leadSNPs_tmp = leadSNPs[leadSNPs[:,1]==chrom]
		if len(leadSNPs_tmp) == 0 and addleadSNPs == 0:
			return [], [], []

	gwas_in = pd.read_table(gwas, header=None, skiprows=gwasfile_chr[ichrom][1], nrows=gwasfile_chr[ichrom][2])
	gwas_in = gwas_in.as_matrix()

	if chrom == 6 and MHC == 1:
		print "Excluding MHC regions ..."
        gwas_in = gwas_in[(gwas_in[:,poscol].astype(int)<MHCstart) | (gwas_in[:,poscol].astype(int)>MHCend)]

	if regions_tmp:
		gwas_tmp = np.array()
		for l in regions_tmp:
			tmp = gwas_in[(gwas_in[:,poscol].astype(int)>=l[1]) & (gwas_in[:,poscol].astype(int)<=l[2])]
			if len(tmp)>0:
				if len(gwas_tmp)>0:
					gwas_tmp = np.r_(gwas_tmp, tmp)
				else:
					gwas_tmp = tmp
		if len(gwas_tmp) == 0:
			return [], [], []
		gwas_in = gwas_tmp

	print str(len(gwas_in))+" SNPs in chromosome "+str(chrom)
	ld = []
	canSNPs = []
	annot = []
	IndSigSNPs = []
	nlead = 0

	ldfile = refgenome+"/"+pop+"ld/"+pop+".chr"+str(chrom)+".ld.gz"
	annotfile = refgenome+"/"+pop+"/"+"chr"+str(chrom)+".data.txt.gz"

	rsIDset = set(list(gwas_in[:, rsIDcol]))
	checkeduid = []

	if leadSNPs_tmp is not None:
		for l in leadSNPs_tmp:
			if not l[0] in rsIDset:
				print "Input lead SNP "+l[0]+" does not exists in input gwas file"
				continue

			igwas = np.where(gwas_in[:,rsIDcol]==l[0])[0][0]
			allele = [gwas_in[igwas, refcol], gwas_in[igwas, altcol]]
			allele.sort()
			l_uid = ":".join([str(gwas_in[igwas, chrcol]), str(gwas_in[igwas, poscol])]+allele)
			IndSigSNPs.append([l_uid, l[0], str(ichrom), str(l[2]), str(gwas_in[igwas, pcol])])
			pos = int(l[2])
			#check uniq ID
			tb = tabix.open(annotfile)
			lead_id = False
			check_id = tb.querys(str(chrom)+":"+str(pos)+"-"+str(pos))
			for m in check_id:
				if m[6] == l_uid:
					lead_id = True
					break
			if lead_id == False:
				continue
			nlead += 1
			tb = tabix.open(ldfile)
			ld_tb = tb.querys(str(chrom)+":"+str(pos)+"-"+str(pos))
			ld_tmp = []
			ld_tmp.append([l[2], l[0], 1])
			for m in ld_tb:
				if m[2] != l[0]:
					continue
				if float(m[6]) >= r2:
					ld_tmp.append([m[4], m[5], m[6]])
			ld_tmp = np.array(ld_tmp)
			minpos = min(ld_tmp[:,0].astype(int))
			maxpos = max(ld_tmp[:,0].astype(int))
			tb = tabix.open(annotfile)
			annot_tb = tb.querys(str(chrom)+":"+str(minpos)+"-"+str(maxpos))
			for m in annot_tb:
				if chrom==6 and MHC==1 and int(m[1])>=MHCstart and int(m[1])<=MHCend:
					continue
				if float(m[5]) < maf:
					continue
				if m[4] in ld_tmp[:,1]:
					ild = np.where(ld_tmp[:,1]==m[4])[0][0]
					if int(m[1]) in gwas_in[:, poscol]:
						jgwas = np.where(gwas_in[:, poscol]==int(m[1]))[0][0]
						if float(gwas_in[jgwas, pcol])>gwasP:
							continue
						allele = [gwas_in[jgwas, refcol], gwas_in[jgwas, altcol]]
						allele.sort()
						uid = ":".join([str(gwas_in[jgwas, chrcol]), str(gwas_in[jgwas, poscol])]+allele)
						if uid != m[6]:
							continue

						ld.append([l_uid, m[6], ld_tmp[ild, 2])
						if m[6] in checkeduid:
							continue
						checkeduid.append(m[6])
						p = str(gwas_in[jgwas, pcol])
						snp = [m[6], m[4], m[0], m[1], gwas_in[jgwas, refcol], gwas_in[jgwas, altcol], m[5], p]
						if orcol:
							snp.append(str(gwas_in[jgwas, orcol]))
						if becol:
							snp.append(str(gwas_in[jgwas, becol]))
						if secol:
							snp.append(str(gwas_in[jgwas, secol]))
						canSNPs.append(snp)
						annot.append([m[6], m[7], m[8]]+m[53:len(m)])
					elif KGSNPs==1:
						ld.append([l_uid, m[6], ld_tmp[ild, 2]])
						if m[6] in checkeduid:
							continue
						checkeduid.append(m[6])
						snp = [m[6], m[4], m[0], m[1], m[2], m[3], m[5], "NA"]
						if orcol:
							snp.append("NA")
						if becol:
							snp.append("NA")
						if secol:
							snp.append("NA")
						canSNPs.append(snp)
						annot.append([m[6], m[7], m[8]]+m[53:len(m)])
		if len(gwas_in[gwas_in[:,pcol]<=leadP]) == 0:
			return ld, canSNPs, annot

	if len(gwas_in[gwas_in[:,pcol].astype(float)<=leadP]) == 0:
		return ld, canSNPs, annot
	gwas_in = gwas_in[gwas_in[:,pcol].argsort()]
	if leadSNPs is None or addleadSNPs == 1:
		for l in gwas_in:
			if float(l[pcol])>leadP:
				break
			allele = [l[refcol], l[altcol]]
			allele.sort()
			l_uid = ":".join([str(l[chrcol]), str(l[poscol])]+allele)
			if not l_uid in checkeduid:
				pos = l[poscol]
				#check uniq ID
				tb = tabix.open(annotfile)
				lead_id = False
				check_id = tb.querys(str(chrom)+":"+str(pos)+"-"+str(pos))
				for m in check_id:
					if m[6] == l_uid:
						lead_id = True
				if lead_id == False:
					continue
				nlead += 1
				tb = tabix.open(ldfile)
				ld_tb = tb.querys(str(chrom)+":"+str(pos)+"-"+str(pos))
				ld_tmp = []
				ld_tmp.append([l[poscol], l[rsIDcol], 1])
				for m in ld_tb:
					if m[2] != l[rsIDcol]:
						continue
					if float(m[6]) >= r2:
						ld_tmp.append([m[4], m[5], m[6]])
				ld_tmp = np.array(ld_tmp)
				minpos = min(ld_tmp[:,0].astype(int))
				maxpos = max(ld_tmp[:,0].astype(int))
				tb = tabix.open(annotfile)
				annot_tb = tb.querys(str(chrom)+":"+str(minpos)+"-"+str(maxpos))
				for m in annot_tb:
					if chrom==6 and MHC==1 and int(m[1])>=MHCstart and int(m[1])<=MHCend:
						continue
					if float(m[5]) < maf:
						continue
					if m[4] in ld_tmp[:,1]:
						ild = np.where(ld_tmp[:,1]==m[4])[0][0]
						if int(m[1]) in gwas_in[:, poscol]:
							jgwas = np.where(gwas_in[:, poscol]==int(m[1]))[0][0]
							if float(gwas_in[jgwas, pcol])>gwasP:
								continue
							allele = [gwas_in[jgwas, refcol], gwas_in[jgwas, altcol]]
							allele.sort()
							uid = ":".join([str(gwas_in[jgwas, chrcol]), str(gwas_in[jgwas, poscol])]+allele)
							if uid != m[6]:
								continue
							ld.append([l_uid, m[6], ld_tmp[ild, 2]])
							if m[6] in checkeduid:
								continue
							checkeduid.append(m[6])
							p = str(gwas_in[jgwas, pcol])
							snp = [m[6], m[4], m[0], m[1], gwas_in[jgwas, refcol], gwas_in[jgwas, altcol], m[5], p]
							if orcol:
								snp.append(str(gwas_in[jgwas, orcol]))
							if becol:
								snp.append(str(gwas_in[jgwas, becol]))
							if secol:
								snp.append(str(gwas_in[jgwas, secol]))
							canSNPs.append(snp)
							annot.append([m[6], m[7], m[8]]+m[53:len(m)])
						elif KGSNPs==1:
							ld.append([l_uid, m[6], ld_tmp[ild, 2]])
							if m[6] in checkeduid:
								continue
							checkeduid.append(m[6])
							snp = [m[6], m[4], m[0], m[1], m[2], m[3], m[5], "NA"]
							if orcol:
								snp.append("NA")
							if becol:
								snp.append("NA")
							if secol:
								snp.append("NA")
							canSNPs.append(snp)
							annot.append([m[6], m[7], m[8]]+m[53:len(m)])

	if len(canSNPs)>0:
		ld = np.array(ld)
		canSNPs = np.array(canSNPs)
		annot = np.array(annot)
		n = canSNPs[:,3].astype(int).argsort()
		canSNPs = canSNPs[n]
		annot = annot[n]
		# np.savetxt(filedir+"tmp.ld"+str(chrom)+".txt", ld, delimiter = "\t", fmt="%s")
		# np.savetxt(filedir+"tmp.snps"+str(chrom)+".txt", canSNPs, delimiter = "\t",  fmt="%s")
		# np.savetxt(filedir+"tmp.annot"+str(chrom)+".txt", annot, delimiter = "\t",  fmt="%s")
	return ld, canSNPs, annot

ld = []
canSNPs = []
annot = []
IndSigSNPs = []

for i in range(0, len(gwasfile_chr)):
	ld_tmp, canSNPs_tmp, annot_tmp = chr_process(i)
	if len(canSNPs_tmp)>0:
		if len(canSNPs)>0:
			ld = np.r_[ld, ld_tmp]
			canSNPs = np.r_[canSNPs, canSNPs_tmp]
			annot = np.r_[annot, annot_tmp]
		else:
			ld = ld_tmp
			canSNPs = canSNPs_tmp
			annot = annot_tmp
# Parallel(n_jobs=n_cores)(delayed(chr_process)(i) for i in range(0, len(gwasfile_chr)))
if len(canSNPs) > 0:
	with open(ldout, 'a') as o:
		np.savetxt(o, ld, delimiter="\t", fmt="%s")
	with open(snpsout, 'a') as o:
		np.savetxt(o, canSNPs, delimiter="\t", fmt="%s")
	with open(annotout, 'a') as o:
		np.savetxt(o, annot, delimiter="\t", fmt="%s")



print time.time() - start

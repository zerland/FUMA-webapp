#!/usr/bin/python
import time
import os
import subprocess
import sys
import re
import pandas as pd
import numpy as np
import tabix
import glob
import ConfigParser
from bisect import bisect_left

##### initialize parameters #####
class getParams:
	def __init__(self, filedir, cfg, param_cfg):
		# cfg = ConfigParser.ConfigParser()
		# cfg.read(f1)
		# param_cfg = ConfigParser.ConfigParser()
		# param_cfg.read(f2)

		leadSNPs = param_cfg.get('inputfiles', 'leadSNPsfile')
		if leadSNPs == "NA":
		    print "prefedined lead SNPs are not provided"
		    leadSNPs = None
		else:
		    print "predefined lead SNPs are procided"
		    leadSNPs = filedir+cfg.get('inputfiles', 'leadSNPs')
		addleadSNPs = int(param_cfg.get('inputfiles', 'addleadSNPs')) #1 to add, 0 to not add
		regions = param_cfg.get('inputfiles', 'regionsfile')
		if regions == "NA":
		    print "predefined genomic regions are not provided"
		    regions = None
		else:
		    print "predefined gwnomic regions are provided"
		    regions = filedir+cfg.get('inputfiles', 'regions')

		pop = param_cfg.get('params', 'pop')
		leadP = float(param_cfg.get('params', 'leadP'))
		KGSNPs = int(param_cfg.get('params', 'Incl1KGSNPs')) #1 to add, 0 to not add
		gwasP = float(param_cfg.get('params', 'gwasP'))
		maf = float(param_cfg.get('params', 'MAF'))
		r2 = float(param_cfg.get('params', 'r2'))
		mergeDist = int(param_cfg.get('params', 'mergeDist'))*1000
		MHC = int(param_cfg.get('params', 'exMHC')) # 1 to exclude, 0 to not
		extMHC = param_cfg.get('params', 'extMHC')
		MHCstart = 29614758 # hg19
		MHCend = 33170276 # hg19
		if extMHC != "NA":
		    mhc = extMHC.split("-")
		    MHCstart = int(mhc[0])
		    MHCend = int(mhc[1])

		###### input files #####
		gwas = filedir+cfg.get('inputfiles', 'snps')
		annot_dir = cfg.get('data', 'annot')
		refgenome_dir = cfg.get('data', 'refgenome')

		##### get column index ######
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

		##### annovar #####
		annov = cfg.get('annovar', 'annovdir')
		humandb = cfg.get('annovar', 'humandb')

		##### dbSNP file #####
		dbSNPfile = cfg.get('data', 'dbSNP')+"/RsMerge146.npy"

		##### set aprams #####
		self.leadSNPs = leadSNPs
		self.addleadSNPs = addleadSNPs
		self.regions = regions
		self.pop = pop
		self.leadP = leadP
		self.KGSNPs = KGSNPs #1 to add, 0 to not add
		self.gwasP = gwasP
		self.maf = maf
		self.r2 = r2
		self.mergeDist = mergeDist
		self.MHC = MHC # 1 to exclude, 0 to not
		self.extMHC = extMHC
		self.MHCstart = MHCstart
		self.MHCend = MHCend
		self.gwas = gwas
		self.annot_dir = annot_dir
		self.refgenome_dir = refgenome_dir
		self.chrcol = chrcol
		self.poscol = poscol
		self.refcol = refcol
		self.altcol = altcol
		self.rsIDcol = rsIDcol
		self.pcol = pcol
		self.orcol = orcol
		self.becol = becol
		self.secol = secol
		self.annov = annov
		self.humandb = humandb
		self.dbSNPfile = dbSNPfile

##### Return index of a1 which exists in a2 #####
def ArrayIn(a1, a2):
	# results = [i for i, x in enumerate(a1) if x in a2]
	results = np.where(np.in1d(a1, a2))[0]
	return results

##### return unique element in list #####
def unique(a):
	unique = []
	[unique.append(s) for s in a if s not in unique]
	return unique

##### update rsID #####
# need to optimize
def rsIDup(snps, rsIDi, dbSNPfile):
	rsID = np.memmap(dbSNPfile, mode='r', dtype='int', shape=(11684784, 3))

	for i in range(0, len(snps)):
		rs = int(snps[i,rsIDi].replace('rs', ''))
		if rs in rsID[:,0]:
			rs = 'rs'+str(rsID[rsID[:,0]==rs,1])
			snps[i, rsIDi] = rs
	return snps

##### separate GWAS file by chromosome #####
def separateGwasByChr(gwas):
	gwasfile_chr = []
	chr_cur = 0
	cur_i = 0
	row = 0
	gwasf = open(gwas, 'r')
	gwasf.readline()
	for l in gwasf:
		row += 1
		l = re.match(r"^(\d+)\t.+", l)
		chr_tmp = int(l.group(1))
		if chr_tmp == chr_cur:
			gwasfile_chr[cur_i-1][2] += 1
		else:
			chr_cur = chr_tmp
			gwasfile_chr.append([chr_cur, row, 1])
			cur_i += 1
	gwasf.close()

	gwasfile_chr = np.array(gwasfile_chr)
	return gwasfile_chr

##### get LD scructure and MAF per chromosome #####
def chr_process(ichrom, gwasfile_chr, regions, leadSNPs, params):
	### Parameters
	addleadSNPs = params.addleadSNPs
	pop = params.pop
	leadP = params.leadP
	KGSNPs = params.KGSNPs
	gwasP = params.gwasP
	maf = params.maf
	r2 = params.r2
	MHC = params.MHC # 1 to exclude, 0 to not
	extMHC = params.extMHC
	MHCstart = params.MHCstart
	MHCend = params.MHCend
	annot_dir = params.annot_dir
	refgenome_dir = params.refgenome_dir
	chrcol = params.chrcol
	poscol = params.poscol
	refcol = params.refcol
	altcol = params.altcol
	rsIDcol = params.rsIDcol
	pcol = params.pcol
	orcol = params.orcol
	becol = params.becol
	secol = params.secol

	chrom = gwasfile_chr[ichrom][0]
	print "Start chromosome "+str(chrom)+" ..."

	### check pre-defined regions
	regions_tmp = None
	if regions is not None:
		regions_tmp = regions[regions[:,0]==chrom]
		if len(regions_tmp)==0:
			return [], [], []

	### check pre-defined lead SNPs
	leadSNPs_tmp = None
	if leadSNPs is not None:
		leadSNPs_tmp = leadSNPs[leadSNPs[:,1]==chrom]
		if len(leadSNPs_tmp) == 0 and addleadSNPs == 0:
			return [], [], []

	### read gwas file for the current chromsome
	gwas_in = pd.read_table(params.gwas, header=None, skiprows=gwasfile_chr[ichrom][1], nrows=gwasfile_chr[ichrom][2])
	gwas_in = gwas_in.as_matrix()

	### exclude MHC region
	if chrom == 6 and MHC == 1:
		print "Excluding MHC regions ..."
		gwas_in = gwas_in[(gwas_in[:,poscol].astype(int)<MHCstart) | (gwas_in[:,poscol].astype(int)>MHCend)]

	### filter SNPs for pre-defined regions (if provided)
	if regions_tmp is not None:
		gwas_tmp = []
		for l in regions_tmp:
			tmp = gwas_in[(gwas_in[:,poscol].astype(int)>=l[1]) & (gwas_in[:,poscol].astype(int)<=l[2])]
			if len(tmp)>0:
				if len(gwas_tmp)>0:
					gwas_tmp = np.r_[gwas_tmp, tmp]
				else:
					gwas_tmp = tmp
		if len(gwas_tmp) == 0:
			return [], [], []
		gwas_in = gwas_tmp

	print str(len(gwas_in))+" SNPs in chromosome "+str(chrom)

	### init variables
	ld = []
	canSNPs = []
	# annot = []
	IndSigSNPs = []
	nlead = 0
	pos_set = set(gwas_in[:,poscol])
	posall = gwas_in[:,poscol]

	ldfile = refgenome_dir+"/"+pop+"ld/"+pop+".chr"+str(chrom)+".ld.gz"
	maffile = refgenome_dir+"/"+pop+"/"+pop+".chr"+str(chrom)+".frq.gz"
	# annotfile = refgenome_dir+"/"+pop+"/"+"chr"+str(chrom)+".data.txt.gz"

	rsIDset = set(gwas_in[:, rsIDcol])
	checkeduid = set()

	### process pre-defined lead SNPs
	if leadSNPs_tmp is not None:
		for l in leadSNPs_tmp:
			if not l[0] in rsIDset:
				print "Input lead SNP "+l[0]+" does not exists in input gwas file"
				continue # rsID of lead SNPs needs to be matched with the one in GWAS file

			igwas = np.where(gwas_in[:,rsIDcol]==l[0])[0][0]
			allele = [gwas_in[igwas, refcol], gwas_in[igwas, altcol]]
			allele.sort()
			l_uid = ":".join([str(gwas_in[igwas, chrcol]), str(gwas_in[igwas, poscol])]+allele)
			# checkeduid.add(l_uid)
			pos = int(l[2])
			#check uniq ID
			tb = tabix.open(maffile)
			lead_id = False
			lead_maf = False
			check_id = tb.querys(str(chrom)+":"+str(pos)+"-"+str(pos))
			for m in check_id:
				a = [m[3], m[4]]
				a.sort()
				tmp_uid = ":".join([m[0], m[1]]+a)
				if tmp_uid == l_uid:
					lead_id = True
					if float(m[5]) >= maf:
						lead_maf = True
					break
			if not lead_id or not lead_maf:
				continue
			nlead += 1
			tb = tabix.open(ldfile)
			ld_tb = tb.querys(str(chrom)+":"+str(pos)+"-"+str(pos))
			ld_tmp = []
			ld_tmp.append([l[2], l[0], 1])
			for m in ld_tb:
				if int(m[1]) != pos:
					continue
				if float(m[6]) >= r2:
					ld_tmp.append([m[4], m[5], m[6]])
			ld_tmp = np.array(ld_tmp)

			minpos = min(ld_tmp[:,0].astype(int))
			maxpos = max(ld_tmp[:,0].astype(int))
			tb = tabix.open(maffile)
			maf_tb = tb.querys(str(chrom)+":"+str(minpos)+"-"+str(maxpos))
			nonGWASSNPs = 0
			GWASSNPs = 0
			for m in maf_tb:
				if chrom==6 and MHC==1 and int(m[1])>=MHCstart and int(m[1])<=MHCend:
					continue
				if float(m[5]) < maf:
					continue
				if m[1] in ld_tmp[:,0]:
					ild = np.where(ld_tmp[:,0]==m[1])[0][0]
					if int(m[1]) in pos_set:
						# jgwas = np.where(gwas_in[:, poscol]==int(m[1]))[0][0]
						jgwas = bisect_left(posall, int(m[1]))

						allele = [gwas_in[jgwas, refcol], gwas_in[jgwas, altcol]]
						allele.sort()
						uid = ":".join([str(gwas_in[jgwas, chrcol]), str(gwas_in[jgwas, poscol])]+allele)

						a = [m[3], m[4]]
						a.sort()
						tmp_uid = ":".join([m[0], m[1]]+a)
						if uid != tmp_uid:
							checkall = False
							jgwas += 1
							while int(m[1]) == gwas_in[jgwas, poscol]:
								allele = [gwas_in[jgwas, refcol], gwas_in[jgwas, altcol]]
								allele.sort()
								uid = ":".join([str(gwas_in[jgwas, chrcol]), str(gwas_in[jgwas, poscol])]+allele)
								if uid == tmp_uid:
									checkall = True
									break
								jgwas += 1
							if not checkall:
								continue

						if float(gwas_in[jgwas, pcol])>gwasP:
							continue

						ld.append([l_uid, uid, ld_tmp[ild, 2]])

						if uid in checkeduid:
							continue

						checkeduid.add(uid)
						p = str(gwas_in[jgwas, pcol])
						snp = [uid, gwas_in[jgwas, rsIDcol], m[0], m[1], gwas_in[jgwas, refcol], gwas_in[jgwas, altcol], m[5], p]
						if orcol:
							snp.append(str(gwas_in[jgwas, orcol]))
						if becol:
							snp.append(str(gwas_in[jgwas, becol]))
						if secol:
							snp.append(str(gwas_in[jgwas, secol]))
						canSNPs.append(snp)
						# annot.append([m[6], m[7], m[8]]+m[53:len(m)])
						GWASSNPs += 1
					elif KGSNPs==1:
						a = [m[3], m[4]]
						a.sort()
						tmp_uid = ":".join([m[0], m[1]]+a)
						ld.append([l_uid, tmp_uid, ld_tmp[ild, 2]])
						if tmp_uid in checkeduid:
							continue
						checkeduid.add(tmp_uid)
						snp = [tmp_uid, m[2], m[0], m[1], m[4], m[3], m[5], "NA"]
						if orcol:
							snp.append("NA")
						if becol:
							snp.append("NA")
						if secol:
							snp.append("NA")
						canSNPs.append(snp)
						# annot.append([m[6], m[7], m[8]]+m[53:len(m)])
						nonGWASSNPs += 1

			IndSigSNPs.append([l_uid, l[0], str(l[1]), str(l[2]), str(gwas_in[igwas, pcol]), str(nonGWASSNPs+GWASSNPs), str(GWASSNPs)])

		if len(gwas_in[gwas_in[:,pcol]<=leadP]) == 0:
			if len(canSNPs)>0:
				ld = np.array(ld)
				canSNPs = np.array(canSNPs)
				annot = np.array(annot)
				IndSigSNPs = np.array(IndSigSNPs)
				IndSigSNPs = IndSigSNPs[IndSigSNPs[:,3].astype(int).argsort()]
				n = canSNPs[:,3].astype(int).argsort()
				canSNPs = canSNPs[n]
				# annot = annot[n]
				return ld, canSNPs, IndSigSNPs
			else:
				return [], [], []

	if len(gwas_in[gwas_in[:,pcol].astype(float)<=leadP]) == 0:
		if len(canSNPs)>0:
			ld = np.array(ld)
			canSNPs = np.array(canSNPs)
			annot = np.array(annot)
			IndSigSNPs = np.array(IndSigSNPs)
			IndSigSNPs = IndSigSNPs[IndSigSNPs[:,3].astype(int).argsort()]
			n = canSNPs[:,3].astype(int).argsort()
			canSNPs = canSNPs[n]
			# annot = annot[n]
			return ld, canSNPs, IndSigSNPs
		else:
			return [], [], []

	p_order = gwas_in[:,pcol].argsort()
	if leadSNPs is None or addleadSNPs == 1:
		for pi in p_order:
			l = gwas_in[pi]
			if chrom==6 and int(l[poscol])>25000000 and int(l[poscol])<35000000:
				continue
			if float(l[pcol])>leadP:
				break
			allele = [l[refcol], l[altcol]]
			allele.sort()
			l_uid = ":".join([str(l[chrcol]), str(l[poscol])]+allele)
			if not l_uid in checkeduid:
				# checkeduid.add(l_uid)
				pos = l[poscol]
				#check uniq ID
				tb = tabix.open(maffile)
				lead_id = False
				lead_maf = False
				check_id = tb.querys(str(chrom)+":"+str(pos)+"-"+str(pos))
				for m in check_id:
					a = [m[3], m[4]]
					a.sort()
					tmp_uid = ":".join([m[0], m[1]]+a)
					if tmp_uid == l_uid:
						lead_id = True
						if float(m[5]) >= maf:
							lead_maf = True
						break
				if not lead_id or not lead_maf:
					continue
				nlead += 1
				tb = tabix.open(ldfile)
				ld_tb = tb.querys(str(chrom)+":"+str(pos)+"-"+str(pos))
				ld_tmp = []
				ld_tmp.append([l[poscol], l[rsIDcol], 1])
				for m in ld_tb:
					if int(m[1]) != pos:
						continue
					if float(m[6]) >= r2:
						ld_tmp.append([m[4], m[5], m[6]])
				ld_tmp = np.array(ld_tmp)
				minpos = min(ld_tmp[:,0].astype(int))
				maxpos = max(ld_tmp[:,0].astype(int))
				tb = tabix.open(maffile)
				maf_tb = tb.querys(str(chrom)+":"+str(minpos)+"-"+str(maxpos))
				nonGWASSNPs = 0
				GWASSNPs = 0
				for m in maf_tb:
					if chrom==6 and MHC==1 and int(m[1])>=MHCstart and int(m[1])<=MHCend:
						continue
					if float(m[5]) < maf:
						continue
					if int(m[1]) in ld_tmp[:,0].astype(int):
						ild = np.where(ld_tmp[:,0].astype(int)==int(m[1]))[0][0]
						if int(m[1]) in pos_set:
							# jgwas = np.where(gwas_in[:, poscol]==int(m[1]))[0][0]
							jgwas = bisect_left(posall, int(m[1]))

							allele = [gwas_in[jgwas, refcol], gwas_in[jgwas, altcol]]
							allele.sort()
							uid = ":".join([str(gwas_in[jgwas, chrcol]), str(gwas_in[jgwas, poscol])]+allele)

							a = [m[3], m[4]]
							a.sort()
							tmp_uid = ":".join([m[0], m[1]]+a)
							if uid != tmp_uid:
								checkall = False
								jgwas += 1
								while int(m[1]) == gwas_in[jgwas, poscol]:
									allele = [gwas_in[jgwas, refcol], gwas_in[jgwas, altcol]]
									allele.sort()
									uid = ":".join([str(gwas_in[jgwas, chrcol]), str(gwas_in[jgwas, poscol])]+allele)
									if uid == tmp_uid:
										checkall = True
										break
									jgwas += 1
								if not checkall:
									continue

							if float(gwas_in[jgwas, pcol])>gwasP:
								continue

							ld.append([l_uid, tmp_uid, ld_tmp[ild, 2]])
							if tmp_uid in checkeduid:
								continue
							checkeduid.add(tmp_uid)
							p = str(gwas_in[jgwas, pcol])
							snp = [tmp_uid, gwas_in[jgwas, rsIDcol], m[0], m[1], gwas_in[jgwas, refcol], gwas_in[jgwas, altcol], m[5], p]
							if orcol:
								snp.append(str(gwas_in[jgwas, orcol]))
							if becol:
								snp.append(str(gwas_in[jgwas, becol]))
							if secol:
								snp.append(str(gwas_in[jgwas, secol]))
							canSNPs.append(snp)
							# annot.append([m[6], m[7], m[8]]+m[53:len(m)])
							GWASSNPs += 1
						elif KGSNPs==1:
							a = [m[3], m[4]]
							a.sort()
							tmp_uid = ":".join([m[0], m[1]]+a)
							ld.append([l_uid, tmp_uid, ld_tmp[ild, 2]])
							if tmp_uid in checkeduid:
								continue
							checkeduid.add(tmp_uid)
							snp = [tmp_uid, m[2], m[0], m[1], m[4], m[3], m[5], "NA"]
							if orcol:
								snp.append("NA")
							if becol:
								snp.append("NA")
							if secol:
								snp.append("NA")
							canSNPs.append(snp)
							# annot.append([m[6], m[7], m[8]]+m[53:len(m)])
							nonGWASSNPs += 1
				IndSigSNPs.append([l_uid, l[4], str(l[0]), str(l[1]), str(l[5]), str(nonGWASSNPs+GWASSNPs), str(GWASSNPs)])

	### separate process for extended MHC region

	if chrom == 6:
		print "processing MHC region..."
		mhc_gwas = gwas_in[np.where((gwas_in[:,poscol].astype(int)>25000000) & (gwas_in[:, poscol].astype(int)<35000000))]
		if len(mhc_gwas) > 0:
			mhc_pos = list(mhc_gwas[mhc_gwas[:,pcol]<=leadP, poscol])
			if len(mhc_pos) > 0:
				mhc_spos = set(mhc_pos)
				mhc_ld = []
				start = mhc_pos[0]
				step = 10000
				end = start
				for tmp_pos in mhc_pos:
					if tmp_pos - start < step:
						end = tmp_pos
					else:
						tb = tabix.open(ldfile)
						ld_tb = tb.querys(str(chrom)+":"+str(start)+"-"+str(end))
						for l in ld_tb:
							if int(l[1]) in mhc_spos and float(l[6])>=r2:
									mhc_ld.append([int(l[1]), int(l[4]), float(l[6])])
						start = tmp_pos
						end = start
				tb = tabix.open(ldfile)
				ld_tb = tb.querys(str(chrom)+":"+str(start)+"-"+str(end))
				for l in ld_tb:
					if int(l[1]) in mhc_spos and float(l[6])>=r2:
							mhc_ld.append([l[1], l[4], l[6]])
				for pos in mhc_pos:
					mhc_ld.append([str(pos), str(pos), '1'])

				mhc_ld = np.array(mhc_ld)
				p_order = mhc_gwas[:,pcol].argsort()
				nlead = 0
				for pi in p_order:
					l = mhc_gwas[pi]
					if float(l[pcol]) > leadP:
						break
					allele = [l[refcol], l[altcol]]
					allele.sort()
					l_uid = ":".join([str(l[chrcol]), str(l[poscol])]+allele)
					pos = int(l[poscol])
					#check uniq ID
					tb = tabix.open(maffile)
					lead_id = False
					lead_maf = False
					check_id = tb.querys(str(chrom)+":"+str(pos)+"-"+str(pos))
					for m in check_id:
						a = [m[3], m[4]]
						a.sort()
						tmp_uid = ":".join([m[0], m[1]]+a)
						if tmp_uid == l_uid:
							lead_id = True
							if float(m[5]) >= maf:
								lead_maf = True
							break
					if not lead_id or not lead_maf:
						continue

					if l_uid in checkeduid:
						continue
					# checkeduid.add(l_uid)
					ld.append([l_uid, l_uid, 1])
					ld_tmp = mhc_ld[mhc_ld[:,0].astype(int)==int(l[poscol])]
					minpos = min(ld_tmp[:,1].astype(int))
					maxpos = max(ld_tmp[:,1].astype(int))
					tb = tabix.open(maffile)
					maf_tb = tb.querys(str(chrom)+":"+str(minpos)+"-"+str(maxpos))
					nonGWASSNPs = 0
					GWASSNPs = 0
					for m in maf_tb:
						if chrom==6 and MHC==1 and int(m[1])>=MHCstart and int(m[1])<=MHCend:
							continue
						if float(m[5]) < maf:
							continue
						if int(m[1]) in ld_tmp[:,1].astype(int):
							ild = np.where(ld_tmp[:,1]==m[1])[0][0]
							if int(m[1]) in pos_set:
								jgwas = bisect_left(posall, int(m[1]))

								allele = [gwas_in[jgwas, refcol], gwas_in[jgwas, altcol]]
								allele.sort()
								uid = ":".join([str(gwas_in[jgwas, chrcol]), str(gwas_in[jgwas, poscol])]+allele)

								a = [m[3], m[4]]
								a.sort()
								tmp_uid = ":".join([m[0], m[1]]+a)

								if uid != tmp_uid:
									checkall = False
									jgwas += 1
									while int(m[1]) == gwas_in[jgwas, poscol]:
										allele = [gwas_in[jgwas, refcol], gwas_in[jgwas, altcol]]
										allele.sort()
										uid = ":".join([str(gwas_in[jgwas, chrcol]), str(gwas_in[jgwas, poscol])]+allele)
										if uid == tmp_uid:
											checkall = True
											break
										jgwas += 1
									if not checkall:
										continue

								if float(gwas_in[jgwas, pcol])>gwasP:
									continue

								ld.append([l_uid, tmp_uid, ld_tmp[ild, 2]])
								if tmp_uid in checkeduid:
									continue
								checkeduid.add(tmp_uid)
								p = str(gwas_in[jgwas, pcol])
								snp = [tmp_uid, gwas_in[jgwas, rsIDcol], m[0], m[1], gwas_in[jgwas, refcol], gwas_in[jgwas, altcol], m[5], p]
								if orcol:
									snp.append(str(gwas_in[jgwas, orcol]))
								if becol:
									snp.append(str(gwas_in[jgwas, becol]))
								if secol:
									snp.append(str(gwas_in[jgwas, secol]))
								canSNPs.append(snp)
								# annot.append([m[6], m[7], m[8]]+m[53:len(m)])
								GWASSNPs += 1
							elif KGSNPs==1:
								a = [m[3], m[4]]
								a.sort()
								tmp_uid = ":".join([m[0], m[1]]+a)
								ld.append([l_uid, tmp_uid, ld_tmp[ild, 2]])
								if tmp_uid in checkeduid:
									continue
								checkeduid.add(tmp_uid)
								snp = [tmp_uid, m[2], m[0], m[1], m[4], m[3], m[5], "NA"]
								if orcol:
									snp.append("NA")
								if becol:
									snp.append("NA")
								if secol:
									snp.append("NA")
								canSNPs.append(snp)
								# annot.append([m[6], m[7], m[8]]+m[53:len(m)])
								nonGWASSNPs += 1
					IndSigSNPs.append([l_uid, l[4], str(l[0]), str(l[1]), str(l[5]), str(nonGWASSNPs+GWASSNPs), str(GWASSNPs)])
					nlead += 1

	if len(canSNPs)>0:
		ld = np.array(ld)
		canSNPs = np.array(canSNPs)
		# annot = np.array(annot)
		IndSigSNPs = np.array(IndSigSNPs)
		IndSigSNPs = IndSigSNPs[IndSigSNPs[:,3].astype(int).argsort()]
		n = canSNPs[:,3].astype(int).argsort()
		canSNPs = canSNPs[n]
		# annot = annot[n]
	return ld, canSNPs, IndSigSNPs

##### get annotations for candidate SNPs #####
def getAnnot(snps, annot_dir):
	chroms = unique(snps[:,2].astype(int))
	out = []
	for chrom in chroms:
		annotfile = annot_dir+"/chr"+str(chrom)+".annot.txt.gz"

		tmp = snps[snps[:,2].astype(int)==chrom]
		if len(tmp)==0:
			continue
		ranges = []
		start = min(tmp[:,3].astype(int))
		end = min(tmp[:,3].astype(int))
		cur_start = start
		cur_end = end
		for l in tmp:
			if int(l[3])-cur_start < 1000000:
				cur_end = int(l[3])
			else:
				ranges.append([cur_start, cur_end])
				cur_start = int(l[3])
				cur_end = int(l[3])
		ranges.append([cur_start, cur_end])

		tmp = tmp[tmp[:,0].argsort()]
		suid = set(tmp[:,0])

		tmp_out = []
		for i in range(0, len(ranges)):
			tb = tabix.open(annotfile)
			annot_tb = tb.querys(str(chrom)+":"+str(ranges[i][0])+"-"+str(ranges[i][1]))
			for l in annot_tb:
				a = [l[2], l[3]]
				a.sort()
				uid = ":".join([l[0], l[1]]+a)
				if uid in suid:
					j = bisect_left(tmp[:,0], uid)
					tmp_out.append([tmp[j,2], tmp[j,3], uid]+l[4:])
		tmp_out = np.array(tmp_out)
		tmp_out = tmp_out[np.lexsort((tmp_out[:,0], tmp_out[:,1])), 2:]

		if len(out)==0:
			out = tmp_out
		else:
			out = np.r_[out, tmp_out]
	return out

def getLeadSNPs(chrom, snps, IndSigSNPs, params):
	leadSNPs = []
	checked = []
	IndSigSNPs = IndSigSNPs[IndSigSNPs[:,4].astype(float).argsort()]
	for snp in IndSigSNPs:
		if snp[1] in checked:
			continue
		ldfile = params.refgenome_dir+'/'+params.pop+'ld/'+params.pop+'.chr'+str(snp[2])+'.ld.gz';
		tb = tabix.open(ldfile)
		ld_tmp = tb.querys(snp[2]+":"+snp[3]+"-"+snp[3])
		inSNPs = []
		inSNPs.append(snp[1])

		for l in ld_tmp:
			if float(l[6])<0.1:
				continue
			if int(l[1]) != int(snp[3]):
				continue
			if int(l[4]) in IndSigSNPs[:,3].astype(int):
				rsID = IndSigSNPs[IndSigSNPs[:,3].astype(int)==int(l[4]),1][0]
				checked.append(rsID)
				inSNPs.append(rsID)
		leadSNPs.append([snp[0], snp[1], snp[2], snp[3], snp[4], str(len(inSNPs)), ":".join(inSNPs)])
	leadSNPs = np.array(leadSNPs)
	leadSNPs = leadSNPs[leadSNPs[:,3].astype(int).argsort()]

	return leadSNPs

def getGenomicRiskLoci(gidx, chrom, snps, ld, IndSigSNPs, leadSNPs, params):
	loci = []
	iloci = 0
	chrom = 0
	inInd = []
	inLead = []
	nonGWASSNPs = []
	GWASSNPs = []
	uid2gl = {}
	for i in range(0, len(leadSNPs)):
		if i == 0:
			chrom = int(leadSNPs[i, 2])
			rsIDs = list(leadSNPs[i,6].split(":"))
			uid = list(snps[ArrayIn(snps[:,1], rsIDs),0])
			for s in uid:
				uid2gl[s] = gidx+1
			inInd = rsIDs
			inLead = [leadSNPs[i,1]]
			n = ArrayIn(snps[:,0], ld[ArrayIn(ld[:,0], uid),1])
			snps_tmp = snps[n]
			nonGWASSNPs += list(snps_tmp[snps_tmp[:,7]=="NA", 0])
			GWASSNPs += list(snps_tmp[snps_tmp[:,7]!="NA", 0])
			start = min(snps[n,3].astype(int))
			end = max(snps[n,3].astype(int))
			loci.append([str(gidx+1)]+list(leadSNPs[i,range(0,5)])+[str(start), str(end), str(len(nonGWASSNPs)+len(GWASSNPs)), str(len(GWASSNPs)), str(len(inInd)), ":".join(inInd), str(len(inLead)), ":".join(inLead)])
		else:
			rsIDs = list(leadSNPs[i,6].split(":"))
			uid = list(snps[ArrayIn(snps[:,1], rsIDs),0])
			for s in uid:
				uid2gl[s] = gidx+1
			inInd += rsIDs
			inInd = unique(inInd)
			inLead += [leadSNPs[i,1]]
			n = ArrayIn(snps[:,0], ld[ArrayIn(ld[:,0], uid),1])
			snps_tmp = snps[n]
			nonGWASSNPs += list(snps_tmp[snps_tmp[:,7]=="NA", 0])
			GWASSNPs += list(snps_tmp[snps_tmp[:,7]!="NA", 0])
			nonGWASSNPs = unique(nonGWASSNPs)
			GWASSNPs = unique(GWASSNPs)
			start = min(snps_tmp[:,3].astype(int))
			end = max(snps_tmp[:,3].astype(int))
			if start <= int(loci[iloci][7]) or start-int(loci[iloci][7])<=params.mergeDist:
				loci[iloci][6] = str(min(start, int(loci[iloci][6])))
				loci[iloci][7] = str(max(end, int(loci[iloci][7])))
				loci[iloci][8] = str(len(nonGWASSNPs)+len(GWASSNPs))
				loci[iloci][9] = str(len(GWASSNPs))
				loci[iloci][10] = str(len(inInd))
				loci[iloci][11] = ":".join(inInd)
				loci[iloci][12] = str(len(inLead))
				loci[iloci][13] = ":".join(inLead)
				if float(leadSNPs[i,4]) < float(loci[iloci][5]):
					loci[iloci][1] = leadSNPs[i,0]
					loci[iloci][2] = leadSNPs[i,1]
					loci[iloci][4] = leadSNPs[i,3]
					loci[iloci][5] = leadSNPs[i,4]
			else:
				gidx += 1
				iloci += 1
				inInd = []
				inLead = []
				nonGWASSNPs = []
				GWASSNPs = []
				rsIDs = list(leadSNPs[i,6].split(":"))
				uid = list(snps[ArrayIn(snps[:,1], rsIDs),0])
				for s in uid:
					uid2gl[s] = gidx+1
				inInd = rsIDs
				inLead = [leadSNPs[i,1]]
				n = ArrayIn(snps[:,0], ld[ArrayIn(ld[:,0], uid),1])
				snps_tmp = snps[n,]
				nonGWASSNPs += list(snps_tmp[snps_tmp[:,7]=="NA", 0])
				GWASSNPs += list(snps_tmp[snps_tmp[:,7]!="NA", 0])
				start = min(snps[n,3].astype(int))
				end = max(snps[n,3].astype(int))
				loci.append([str(gidx+1)]+list(leadSNPs[i,range(0,5)])+[str(start), str(end), str(len(nonGWASSNPs)+len(GWASSNPs)), str(len(GWASSNPs)), str(len(inInd)), ":".join(inInd), str(len(inLead)), ":".join(inLead)])
	loci = np.array(loci)
	gidx += 1
	return loci, uid2gl, gidx

def main():
	starttime = time.time()

	##### check arguments #####
	if len(sys.argv)<2:
		sys.exit('ERROR: not enough arguments\nUSAGE ./getLD.py <filedir>')

	filedir = sys.argv[1]
	if re.match(".+\/$", filedir) is None:
		filedir += '/'

	##### get config files #####
	cfg = ConfigParser.ConfigParser()
	cfg.read(os.path.dirname(os.path.realpath(__file__))+'/app.config')

	param_cfg = ConfigParser.ConfigParser()
	param_cfg.read(filedir+'params.config')

	##### get parameters #####
	params = getParams(filedir, cfg, param_cfg)
	# params = getParams(os.path.dirname(os.path.realpath(__file__))+'/app.config', filedir+'params.config')

	##### output files #####
	ldout = filedir+"ld.txt"
	snpsout = filedir+"snps.txt"
	annotout = filedir+"annot.txt"
	indsigout = filedir+"IndSigSNPs.txt"
	leadout = filedir+"leadSNPs.txt"
	glout = filedir+"GenomicRiskLoci.txt"
	annovin = filedir+"annov.input"

	##### write headers #####
	with open(ldout, 'w') as o:
		o.write("\t".join(["SNP1","SNP2","r2"])+"\n")

	ohead = "\t".join(["uniqID", "rsID", "chr", "pos", "ref", "alt", "MAF", "gwasP"])
	if params.orcol:
		ohead += "\tor"
	if params.becol:
		ohead += "\tbeta"
	if params.secol:
		ohead += "\tse"
	ohead += "\tr2\tIndSigSNP\tGenomicLocus"
	ohead += "\n"
	with open(snpsout, 'w') as o:
		o.write(ohead)

	tmp = subprocess.check_output('gzip -cd '+params.annot_dir+'/chr1.annot.txt.gz | head -1', shell=True)
	tmp = tmp.strip().split()

	ohead = "\t".join(["uniqID"]+tmp[4:])
	ohead += "\n"
	with open(annotout, 'w') as o:
		o.write(ohead)

	with open(indsigout, 'w') as o:
		o.write("\t".join(["No", "GenomicLocus", "uniqID", "rsID", "chr", "pos", "p","nSNPs", "nGWASSNPs"])+"\n")

	with open(leadout, 'w') as o:
		o.write("\t".join(["No", "GenomicLocus", "uniqID", "rsID", "chr", "pos", "p","nIndSigSNPs", "IndSigSNPs"])+"\n")

	with open(glout, 'w') as o:
		o.write("\t".join(["GenomicLocus", "uniqID", "rsID", "chr", "pos", "p", "start", "end", "nSNPs", "nGWASSNPs", "nIndSigSNPs", "IndSigSNPs", "nLeadSNPs", "LeadSNPs"])+"\n")

	##### region file #####
	# 0: chr, 1: start, 2: end
	regions = None
	if params.regions:
		regions = pd.read_table(params.regions, comment="#", delim_whitespace=True)
		regions = regions.as_matrix()

	##### lead SNPs file #####
	# 0: rsID, 1: chr, 2: pos
	inleadSNPs = None
	if params.leadSNPs:
		inleadSNPs = pd.read_table(params.leadSNPs, comment="#", delim_whitespace=True)
		inleadSNPs = inleadSNPs.as_matrix()
		inleadSNPs = rsIDup(inleadSNPs, 0, params.dbSNPfile)

	##### get row index for each chromosome #####
	# input file needs to be sorted by chr and position
	gwasfile_chr = separateGwasByChr(params.gwas)

	##### process per chromosome #####
	nSNPs = 0
	gidx = 0 #risk loci index
	IndSigIdx = 0
	leadIdx = 0
	for i in range(0, len(gwasfile_chr)):
		chrom = chrom = gwasfile_chr[i][0]
		ld, snps, IndSigSNPs = chr_process(i, gwasfile_chr, regions, inleadSNPs, params)
		if len(snps)>0:
			nSNPs += len(IndSigSNPs)
			### get annot
			annot = getAnnot(snps, params.annot_dir)
			tmp_uids = list(annot[:,0])
			annot = annot[[tmp_uids.index(x) for x in snps[:,0]]]
			### get lead SNPs
			leadSNPs = getLeadSNPs(chrom, snps, IndSigSNPs, params)
			### get Genomic risk loci
			loci, uid2gl, gidx = getGenomicRiskLoci(gidx, chrom, snps, ld, IndSigSNPs, leadSNPs, params)

			### add columns for sig SNPs
			addcol = []
			for i in range(0,len(IndSigSNPs)):
				addcol.append([str(IndSigIdx+i+1), str(uid2gl[IndSigSNPs[i,0]])])
			IndSigSNPs = np.c_[addcol, IndSigSNPs]
			IndSigIdx += len(IndSigSNPs)

			addcol = []
			for i in range(0,len(leadSNPs)):
				addcol.append([str(leadIdx+i+1), str(uid2gl[leadSNPs[i,0]])])
			leadSNPs = np.c_[addcol, leadSNPs]
			leadIdx += len(leadSNPs)

			### snps add columns
			pd_ld = pd.DataFrame(ld)
			pd_ld[[2]] = pd_ld[[2]].astype(float)
			idx = pd_ld.groupby(1)[2].transform(max) == pd_ld[2]
			uid1 = np.array(pd_ld[0][idx].tolist())
			uid2 = np.array(pd_ld[1][idx].tolist())
			r2 = np.array(pd_ld[2][idx].tolist())
			tmp = list(snps[:,0])
			uid2 = list(uid2)
			idx = [uid2.index(x) for x in tmp]
			uid1 = uid1[idx]
			r2 = r2[idx]
			rsIDs = snps[[tmp.index(x) for x in uid1],1]
			tmp = list(IndSigSNPs[:,2])
			gl = IndSigSNPs[[tmp.index(x) for x in uid1],1]
			snps = np.c_[snps, r2, rsIDs, gl]

			### write outputs
			with open(snpsout, 'a') as o:
				np.savetxt(o, snps, delimiter="\t", fmt="%s")

			with open(ldout, 'a') as o:
				np.savetxt(o, ld, delimiter="\t", fmt="%s")

			with open(annotout, 'a') as o:
				np.savetxt(o, annot, delimiter="\t", fmt="%s")

			with open(annovin, 'a') as o:
				for l in snps:
					o.write("\t".join([l[2], l[3], l[3], l[4], l[5]])+"\n")

			with open(indsigout, 'a') as o:
				np.savetxt(o, IndSigSNPs, delimiter="\t", fmt="%s")

			with open(leadout, 'a') as o:
				np.savetxt(o, leadSNPs, delimiter="\t", fmt="%s")

			with open(glout, 'a') as o:
				np.savetxt(o, loci, delimiter="\t", fmt="%s")

	##### exit if there is no SNPs with P<=leadP
	if nSNPs==0:
		sys.exit("No candidate SNP was identified")

	##### ANNOVAR #####
	annovout = filedir+"annov"
	os.system(params.annov+"/annotate_variation.pl -out "+annovout+" -build hg19 "+annovin+" "+params.humandb+"/ -dbtype ensGene")
	annov1 = filedir+"annov.variant_function"
	annov2 = filedir+"annov.txt"
	os.system(os.path.dirname(os.path.realpath(__file__))+"/annov_geneSNPs.pl "+annov1+" "+annov2)
	os.system("rm "+filedir+"annov.input "+filedir+"annov.*function "+filedir+"annov.log")

	print "getLD.py run time: "+str(time.time()-starttime)

if __name__ == "__main__": main()
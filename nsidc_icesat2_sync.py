#!/usr/bin/env python
u"""
nsidc_icesat2_sync.py
Written by Tyler Sutterley (06/2019)

Program to acquire ICESat-2 datafiles from NSIDC server:
https://wiki.earthdata.nasa.gov/display/EL/How+To+Access+Data+With+Python
https://nsidc.org/support/faq/what-options-are-available-bulk-downloading-data-
	https-earthdata-login-enabled
http://www.voidspace.org.uk/python/articles/authentication.shtml#base64

Register with NASA Earthdata Login system:
https://urs.earthdata.nasa.gov

Add NSIDC_DATAPOOL_OPS to NASA Earthdata Applications
https://urs.earthdata.nasa.gov/oauth/authorize?client_id=_JLuwMHxb2xX6NwYTb4dRA

CALLING SEQUENCE:
	python nsidc_icesat2_sync.py --user=<username> --version=1 ATL03
	where <username> is your NASA Earthdata username

INPUTS:
	ATL03: Global Geolocated Photon Data
	ATL04: Normalized Relative Backscatter
	ATL06: Land Ice Height
	ATL07: Sea Ice Height
	ATL08: Land and Vegetation Height
	ATL09: Atmospheric Layer Characteristics
	ATL10: Sea Ice Freeboard
	ATL12: Ocean Surface Height
	ATL13: Inland Water Surface Height

COMMAND LINE OPTIONS:
	--help: list the command line options
	-Y X, --year=X: years to sync separated by commas
	-S X, --subdirectory=X: subdirectories to sync separated by commas
	--version=X: ICESat-2 data version
	--granule=X: ICESat-2 granule
	-U X, --user=X: username for NASA Earthdata Login
	-D X, --directory: working data directory (default: $PYTHONDATA)
	-M X, --mode=X: Local permissions mode of the directories and files synced
	-l, --log: output log of files downloaded
	-L, --list: print files to be transferred, but do not execute transfer
	-C, --clobber: Overwrite existing data in transfer

PYTHON DEPENDENCIES:
	lxml: Pythonic XML and HTML processing library using libxml2/libxslt
		http://lxml.de/
		https://github.com/lxml/lxml

UPDATE HISTORY:
	Updated 06/2019: use strptime to extract last modified time of remote files
	Written 01/2019
"""
from __future__ import print_function

import sys
import os
import re
import getopt
import shutil
import base64
import getpass
import builtins
import posixpath
import lxml.etree
import calendar, time
if sys.version_info[0] == 2:
	from cookielib import CookieJar
	import urllib2
else:
	from http.cookiejar import CookieJar
	import urllib.request as urllib2

#-- PURPOSE: check internet connection
def check_connection():
	#-- attempt to connect to https host for NSIDC
	try:
		urllib2.urlopen('https://n5eil01u.ecs.nsidc.org/',timeout=1)
	except urllib2.URLError:
		raise RuntimeError('Check internet connection')
	else:
		return True

#-- PURPOSE: sync the ICESat-2 elevation data from NSIDC
def nsidc_icesat2_sync(ddir, PRODUCTS, VERSION, GRANULES, USER='', PASSWORD='',
	YEARS=None,SUBDIRECTORY=None,LOG=False,LIST=False,MODE=None,CLOBBER=False):

	#-- output of synchronized files
	if LOG:
		#-- output to log file
		LOGDIR = os.path.join(ddir,'icesat2.dir','sync_logs.dir')
		#-- check if log directory exists and recursively create if not
		os.makedirs(LOGDIR,MODE) if not os.path.exists(LOGDIR) else None
		#-- format: NSIDC_IceBridge_sync_2002-04-01.log
		today = time.strftime('%Y-%m-%d',time.localtime())
		LOGFILE = 'NSIDC_IceSat-2_sync_{0}.log'.format(today)
		fid = open(os.path.join(LOGDIR,LOGFILE),'w')
		print('IceBridge Data Sync Log ({0})'.format(today), file=fid)
	else:
		#-- standard output (terminal output)
		fid = sys.stdout

	#-- https://docs.python.org/3/howto/urllib2.html#id5
	#-- create a password manager
	password_mgr = urllib2.HTTPPasswordMgrWithDefaultRealm()
	#-- Add the username and password for NASA Earthdata Login system
	password_mgr.add_password(None, 'https://urs.earthdata.nasa.gov',
		USER, PASSWORD)
	#-- Encode username/password for request authorization headers
	base64_string = base64.b64encode('{0}:{1}'.format(USER,PASSWORD).encode())
	#-- compile HTML parser for lxml
	parser = lxml.etree.HTMLParser()
	#-- Create cookie jar for storing cookies. This is used to store and return
	#-- the session cookie given to use by the data server (otherwise will just
	#-- keep sending us back to Earthdata Login to authenticate).
	cookie_jar = CookieJar()
	#-- create "opener" (OpenerDirector instance)
	opener = urllib2.build_opener(
		urllib2.HTTPBasicAuthHandler(password_mgr),
	    #urllib2.HTTPHandler(debuglevel=1),  # Uncomment these two lines to see
	    #urllib2.HTTPSHandler(debuglevel=1), # details of the requests/responses
		urllib2.HTTPCookieProcessor(cookie_jar))
	#-- add Authorization header to opener
	authorization_header = "Basic {0}".format(base64_string.decode())
	opener.addheaders = [("Authorization", authorization_header)]
	#-- Now all calls to urllib2.urlopen use our opener.
	urllib2.install_opener(opener)
	#-- All calls to urllib2.urlopen will now use handler
	#-- Make sure not to include the protocol in with the URL, or
	#-- HTTPPasswordMgrWithDefaultRealm will be confused.

	#-- remote https server for ICESat-2 Data
	HOST = 'https://n5eil01u.ecs.nsidc.org'
	#-- regular expression operator for finding files of a particular granule
	remote_regex_pattern = '{0}_(\d+)_03140110_(\d+)_{1:02d}.(.*?)'
	#-- regular expression operator for finding subdirectories
	if SUBDIRECTORY:
		#-- Sync particular subdirectories for product
		R2 = re.compile('('+'|'.join(SUBDIRECTORY)+')', re.VERBOSE)
	elif YEARS:
		#-- Sync particular years for product
		regex_pattern = '|'.join('{0:d}'.format(y) for y in YEARS)
		R2 = re.compile('({0}).(\d+).(\d+)'.format(regex_pattern), re.VERBOSE)
	else:
		#-- Sync all available years for product
		R2 = re.compile('(\d+).(\d+).(\d+)', re.VERBOSE)

	#-- for each icesat2 product listed
	for p in PRODUCTS:
		print('PRODUCT={0}'.format(p), file=fid) if LOG else None
		#-- input directory for product
		DIRECTORY = os.path.join(ddir,'{0}.{1:03d}'.format(p,VERSION))
		#-- get directories from remote directory
		remote_directories = ['ATLAS','{0}.{1:03d}'.format(p,VERSION)]
		d = posixpath.join(HOST,*remote_directories)
		req = urllib2.Request(url=d)
		#-- read and parse request for subdirectories (find column names)
		tree = lxml.etree.parse(urllib2.urlopen(req), parser)
		colnames = tree.xpath('//td[@class="indexcolname"]//a/@href')
		remote_sub = [sd for sd in colnames if R2.match(sd)]
		#-- for each remote subdirectory
		for sd in remote_sub:
			#-- check if data directory exists and recursively create if not
			local_dir = os.path.join(DIRECTORY,sd)
			os.makedirs(local_dir,MODE) if not os.path.exists(local_dir) else None
			#-- find ICESat-2 data files
			req=urllib2.Request(url=posixpath.join(d,dir,sd))
			#-- read and parse request for remote files (columns and dates)
			tree = lxml.etree.parse(urllib2.urlopen(req), parser)
			colnames = tree.xpath('//td[@class="indexcolname"]//a/@href')
			collastmod = tree.xpath('//td[@class="indexcollastmod"]/text()')
			remote_file_lines = [i for i,f in enumerate(colnames) if
				re.match(remote_regex_pattern,f)]
			#-- sync each ICESat-2 data file
			for i in remote_file_lines:
				#-- remote and local versions of the file
				remote_file = posixpath.join(d,dir,sd,colnames[i])
				local_file = os.path.join(local_dir,colnames[i])
				#-- get last modified date and convert into unix time
				LMD = time.strptime(collastmod[i].rstrip(),'%Y-%m-%d %H:%M')
				remote_mtime = calendar.timegm(LMD)
				#-- sync ICESat-2 files with NSIDC server
				http_pull_file(fid, remote_file, remote_mtime, local_file,
					LIST, CLOBBER, MODE)
		#-- close request
		req = None

	#-- close log file and set permissions level to MODE
	if LOG:
		fid.close()
		os.chmod(os.path.join(LOGDIR,LOGFILE), MODE)

#-- PURPOSE: pull file from a remote host checking if file exists locally
#-- and if the remote file is newer than the local file
def http_pull_file(fid,remote_file,remote_mtime,local_file,LIST,CLOBBER,MODE):
	#-- if file exists in file system: check if remote file is newer
	TEST = False
	OVERWRITE = ' (clobber)'
	#-- check if local version of file exists
	if os.access(local_file, os.F_OK):
		#-- check last modification time of local file
		local_mtime = os.stat(local_file).st_mtime
		#-- if remote file is newer: overwrite the local file
		if (remote_mtime > local_mtime):
			TEST = True
			OVERWRITE = ' (overwrite)'
	else:
		TEST = True
		OVERWRITE = ' (new)'
	#-- if file does not exist locally, is to be overwritten, or CLOBBER is set
	if TEST or CLOBBER:
		#-- Printing files transferred
		print('{0} --> '.format(remote_file), file=fid)
		print('\t{0}{1}\n'.format(local_file,OVERWRITE), file=fid)
		#-- if executing copy command (not only printing the files)
		if not LIST:
			#-- Create and submit request. There are a wide range of exceptions
			#-- that can be thrown here, including HTTPError and URLError.
			request = urllib2.Request(remote_file)
			response = urllib2.urlopen(request)
			#-- chunked transfer encoding size
			CHUNK = 16 * 1024
			#-- copy contents to local file using chunked transfer encoding
			#-- transfer should work properly with ascii and binary data formats
			with open(local_file, 'wb') as f:
				shutil.copyfileobj(response, f, CHUNK)
			#-- keep remote modification time of file and local access time
			os.utime(local_file, (os.stat(local_file).st_atime, remote_mtime))
			os.chmod(local_file, MODE)

#-- PURPOSE: help module to describe the optional input parameters
def usage():
	print('\nHelp: {0}'.format(os.path.basename(sys.argv[0])))
	print(' -Y X, --year=X\t\tYears to sync separated by commas')
	print(' -S X, --subdirectory=X\tSubdirectories to sync separated by commas')
	print(' -U X, --user=X\t\tUsername for NASA Earthdata Login')
	print(' -D X, --directory=X\tWorking data directory')
	print(' -M X, --mode=X\t\tPermission mode of directories and files synced')
	print(' -L, --list\t\tOnly print files that are to be transferred')
	print(' -C, --clobber\t\tOverwrite existing data in transfer')
	print(' -l, --log\t\tOutput log file')
	today = time.strftime('%Y-%m-%d',time.localtime())
	LOGFILE = 'NSIDC_IceSat-2_sync_{0}.log'.format(today)
	print('    Log file format: {0}\n'.format(LOGFILE))

#-- Main program that calls nsidc_icesat2_sync()
def main():
	#-- Read the system arguments listed after the program
	long_options=['help','year=','subdirectory=','user=','directory=',
		'list','log','mode=','clobber']
	optlist,arglist = getopt.getopt(sys.argv[1:],'hY:S:U:D:LCM:l',long_options)

	#-- command line parameters
	YEARS = None
	SUBDIRECTORY = None
	VERSION = None
	GRANULES = None
	USER = ''
	DIRECTORY = os.getcwd()
	LIST = False
	LOG = False
	#-- permissions mode of the local directories and files (number in octal)
	MODE = 0o775
	CLOBBER = False
	for opt, arg in optlist:
		if opt in ('-h','--help'):
			usage()
			sys.exit()
		elif opt in ("-Y","--year"):
			YEARS = [int(Y) for Y in arg.split(',')]
		elif opt in ("-S","--subdirectory"):
			SUBDIRECTORY = arg.split(',')
		elif opt in ("-U","--user"):
			USER = arg
		elif opt in ("-D","--directory"):
			DIRECTORY = os.path.expanduser(arg)
		elif opt in ("-L","--list"):
			LIST = True
		elif opt in ("-l","--log"):
			LOG = True
		elif opt in ("-M","--mode"):
			MODE = int(arg, 8)
		elif opt in ("-C","--clobber"):
			CLOBBER = True

	#-- Pre-ICESat-2 and IceBridge Products
	PROD = {}
	PROD['ATL03'] = 'Global Geolocated Photon Data'
	PROD['ATL04'] = 'Normalized Relative Backscatter'
	PROD['ATL06'] = 'Land Ice Height'
	PROD['ATL07'] = 'Sea Ice Height'
	PROD['ATL08'] = 'Land and Vegetation Height'
	PROD['ATL09'] = 'Atmospheric Layer Characteristics'
	PROD['ATL10'] = 'Sea Ice Freeboard'
	PROD['ATL12'] = 'Ocean Surface Height'
	PROD['ATL13'] = 'Inland Water Surface Height'

	#-- enter dataset to transfer as system argument
	if not arglist:
		for key,val in PROD.items():
			print('{0}: {1}'.format(key, val))
		raise Exception('No System Arguments Listed')

	#-- check that each data product entered was correctly typed
	keys = ','.join(sorted([key for key in PROD.keys()]))
	for p in arglist:
		if p not in PROD.keys():
			raise IOError('Incorrect Data Product Entered ({0})'.format(keys))

	#-- NASA Earthdata hostname
	HOST = 'urs.earthdata.nasa.gov'
	#-- check that NASA Earthdata credentials were entered
	if not USER:
		USER = builtins.input('Username for {0}: '.format(HOST))
	#-- enter password securely from command-line
	PASSWORD = getpass.getpass('Password for {0}@{1}: '.format(USER,HOST))

	#-- check internet connection before attempting to run program
	if check_connection():
		nsidc_icesat2_sync(DIRECTORY, arglist, VERSION, GRANULES, USER=USER,
			PASSWORD=PASSWORD, YEARS=YEARS, SUBDIRECTORY=SUBDIRECTORY, LOG=LOG,
			LIST=LIST, MODE=MODE, CLOBBER=CLOBBER)

#-- run main program
if __name__ == '__main__':
	main()

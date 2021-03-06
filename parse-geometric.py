#!/usr/bin/python
import xml.etree.ElementTree as ET
import re
import math
from pprint import pprint
import sys
import codecs
import argparse
import sys
import string
from copy import copy
import os

config = {}

def loadConfig():
	global config
	ign = {}
	execfile('config.py', ign, config)

def getConfig(filename):
	filename = os.path.basename(filename)
	filename = filename.replace('.xml','')
	global config
	# start off with defaults
	retval = copy(config['default'])
	# Apply overrides
	try:
		thisOverride = config['override'][filename]
		for kv in thisOverride.keys():
			retval[kv] = thisOverride[kv]
	except:
		pass
	return retval

def findRects(groups, minW, maxW, minH, maxH):
	rects = []
	for g in groups:
		gc = g.getchildren()
		if len(gc)==5:
			xvals = map(lambda v:float(v.attrib['x']), gc)
			yvals = map(lambda v:float(v.attrib['y']), gc)
			x1 = min(xvals)
			y1 = min(yvals)
			x2 = max(xvals)
			y2 = max(yvals)
			w = x2-x1
			h = y2-y1
			if w > minW and w < maxW and h > minH and h < maxH:
				rects.append([x1, y1, x2, y2])

	# Extract lines from the 2 point GROUP that satisfy our size
	# requirements, and are horizontal OR vertical.
	#
	# Each line [x1,y1,x2,y2] is stored such that
	#       x1<=x2 and y1<=y2
	#
	hlines = []
	vlines = []
	for g in groups:
		gc = g.getchildren()
		if len(gc)==2:
			xvals = map(lambda v:float(v.attrib['x']), gc)
			yvals = map(lambda v:float(v.attrib['y']), gc)
			x1 = xvals[0]
			y1 = yvals[0]
			x2 = xvals[1]
			y2 = yvals[1]
			if x1 == x2:
				l = math.fabs(y2-y1)
				if l>minH and l<maxH:
					if y1<y2:
						vlines.append([x1,y1,x2,y2])
					else:
						vlines.append([x1,y2,x2,y1])
			if y1 == y2:
				l = math.fabs(x2-x1)
				if l>minW and l<maxW:
					if x1<x2:
						hlines.append([x1,y1,x2,y2])
					else:
						hlines.append([x2,y1,x1,y2])

	# Vertical sort function, based on Y
	def sortV(l1, l2):
		if l1[1]<l2[1]:
			return -1
		elif l1[1]>l2[1]:
			return 1
		return 0

	# Sort lines by Y. This will help the next phase.
	hlines.sort(cmp=sortV)
	vlines.sort(cmp=sortV)

	# Coordinate value tolerance based match.
	def coordMatch(v1, v2):
		if math.fabs(v1-v2)<0.5:
			return True
		return False

	# Combine the lines to create rectangles where possible.
	# A rectangle needs 2 horiz and 2 vert lines
	#
	# We start with a horizontal line (hcand1). Next, we find
	# an attachable vertical line vcand1. hcand2 is then chosen
	# to fit vcand1. vcand2 is chosen to attach to hcand2 and
	# hcand1.
	#
	#          hcand1
	#    +-----------------------+
	#    |                       |
	#  v |                       |v
	#  c |                       |c
	#  a |                       |a
	#  n |                       |n
	#  d |                       |d
	#  1 |                       |2
	#    +-----------------------+
	#          hcand2
	#
	while hlines:
		hcand1 = hlines[0]
		vcand1 = None
		hcand2 = None
		vcand2 = None
		# find a vertical line that starts at first corner
		for vl in vlines:
			if coordMatch(hcand1[0], vl[0]) and coordMatch(hcand1[1], vl[1]):
				vcand1 = vl
				break
		if vcand1:
			# find a horizontal line that starts at first corner
			for hl in hlines:
				if coordMatch(vcand1[2], hl[0]) and coordMatch(vcand1[3], hl[1]):
					hcand2 = hl
					break
		if hcand2:
			for vl in vlines:
				if coordMatch(hcand2[2], vl[2]) and coordMatch(hcand2[3], vl[3]) and coordMatch(vl[0], hcand1[2]) and coordMatch(vl[1], hcand1[3]):
					vcand2 = vl
					break
		if vcand2:
			rects.append([hcand1[0], hcand1[1], hcand2[2], hcand2[3]])
			hlines.remove(hcand2)
			vlines.remove(vcand1)
			vlines.remove(vcand2)
		hlines.remove(hcand1)

	return rects

def computeDataRegions(filename, cfg, thisPage):
	# Every page has a xi:include attribute at the end of the page
	# This includes a vector XML file. The XML file contains lines and 
	# rectangles. 
	#
	# pdf2xml conversion results in this being stored in 
	# the <filename>_data directory.
	#
	# We use this vector file to load rectangles (5 point GROUP).
	#
	# The rectangles that are close to our target box size (with some
	# fuzz) are retained.
	#
	# Line GROUPs in the vector file are taken.  Lines that are
	# horizontal OR vertical and satisfy the target box size requirements
	# are retained.  Out of these, rectangles are created where possible.
	#
	# The rectangles from the 5 point GROUP and the 2 point GROUP are
	# the final rectangles that are considered to contain voter data.
	#
	shapeFileName = thisPage.getchildren()[-1].attrib['href']
	try:
		doc = ET.parse(os.path.join(os.path.dirname(filename), shapeFileName))
	except:
		# maybe the path in the file is OK
		doc = ET.parse(shapeFileName)
	root = doc.getroot()
	groups = root.findall('GROUP')

	minW = cfg['infoBoxWidthRange'][0]
	maxW = cfg['infoBoxWidthRange'][1]
	minH = cfg['infoBoxHeightRange'][0]
	maxH = cfg['infoBoxHeightRange'][1]

	rectsVoter = findRects(groups, minW, maxW, minH, maxH)
	def cmpRects(r1,r2):
		r1_y = r1[1]
		r2_y = r2[1]
		if r1_y < r2_y:
			return -1
		elif r1_y > r2_y:
			return 1
		r1_x = r1[0]
		r2_x = r2[0]
		if r1_x < r2_x:
			return -1
		elif r1_x > r2_x:
			return 1
		return 0
	# Sort with Y first, then X
	rectsVoter.sort(cmp=cmpRects)
	return rectsVoter

def extractVoterInfo(cfg, textRect, textNodes, pageNo, debugMatch):
	if len(textNodes) == 0:
		return None
	v_tolerance = cfg['lineSeparation']
	def cmpBoxFields(a, b):
		y1 = float(a.attrib['y'])
		y2 = float(b.attrib['y'])
		if math.fabs(y1-y2) > v_tolerance:
			if y1 < y2:
				return -1
			elif y1 > y2:
				return 1
		x1 = float(a.attrib['x'])
		x2 = float(b.attrib['x'])
		if x1 < x2:
			return -1
		elif x1 > x2:
			return 1
		return 0

	textNodes.sort(cmp=cmpBoxFields)

	boxTextNodes = copy(textNodes)

	reVoterId = re.compile('[A-Z].*[0-9]{6,}')
	reElector = re.compile("Elector's") # Words seem to be getting split in the PDF
	reRelative = re.compile("(Father|Husband|Mother)'s")
	reHouse = re.compile("House")
	rePhoto = re.compile("Photo")
	reAge = re.compile("Age")
	reSex = re.compile("Sex")
	reSerial = re.compile("[0-9]+")

	info = {}

	info['page'] = pageNo

	# First item in the list needs to be the serial number
	ob = reSerial.match(textNodes[0].text)
	if ob:
		info["serial"] = ob.group()
		textNodes.pop(0)
	else:
		# If the first item is not a serial number, then
		# keep adding till you find the number
		# This handles the case where there's an extra "(S)"
		# No idea what this stands for !
		serial = textNodes[0].text
		idx = 1
		while True:
			#print 'considering :',textNodes[idx].text
			ob = reSerial.match(textNodes[idx].text)
			if ob:
				#print 'matched'
				serial = serial + ' ' + textNodes[idx].text
				info['serial'] = serial
				idx = idx + 1
				break
			serial = serial + ' ' + textNodes[idx].text
			idx = idx + 1
			if len(serial)>10:
				print '!!! ERROR - invalid serial'
				return None
		for i in range(idx):
			textNodes.pop(0)

	# Next item is the EPIC number. This may be missed in
	# some nodes!
	info["epic"] = ""
	ob = reVoterId.match(textNodes[0].text)
	if ob:
		info["epic"] = ob.group()
		textNodes.pop(0)

	# Filter out certain keywords that will not make it into the data
	blacklist = ['Name',':', 'Photo','Not', 'Available']
	textNodes = filter(lambda x: x.text not in blacklist, textNodes)
	outNodes = []
	textCoords = []
	for s in textNodes:
		try:
			txt = s.text.strip()
		except:
			continue
		for token in blacklist:
			txt = txt.replace(token, '')
			txt = txt.strip()
		if len(txt)>0:
			outNodes.append(txt)
			textCoords.append([float(s.attrib['x']), float(s.attrib['y']), float(s.attrib['width']), float(s.attrib['height'])])
	textNodes = outNodes

	appendTo = None
	info["name"] = ""
	info["relative"] = ""
	info["relation"] = ""
	info["residence"] = ""
	info["age"] = ""
	info["sex"] = ""

	infoKeys = info.keys()
	info["debug"] = {}
	for k in infoKeys:
		info['debug'][k] = []
	info['debug']['rejected'] = []

	appendTo = "name" # By default after EPIC
	for content,coords in zip(textNodes, textCoords):
		nodeChanged = False
		for tryMatch in zip(['name','relative','residence','age','sex'], [reElector, reRelative, reHouse, reAge, reSex]):
			ob = tryMatch[1].match(content)
			if ob:
				# Geometric constraint: these labels are aligned
				# to the left
				if tryMatch[0] in ["age", "name", "relative", "residence"]:
					if coords[0]>(textRect[0]+20):
						continue
				appendTo = tryMatch[0]
				nodeChanged = True
				if tryMatch[0] == 'relative':
					info["relation"] = ob.groups()[0]
				break
		if (not nodeChanged) and (appendTo is not None):
			if (len(info[appendTo])==0) and (appendTo=='residence'):
				content = re.sub('^No\.', '', content)
			info[appendTo] =( '%s %s'%(info[appendTo], content)).strip()
			info["debug"][appendTo].append(coords)
		else:
			info['debug']['rejected'].append(coords)

	if debugMatch(pageNo, info['epic']):
		print 'Matching record at page %3d'%(pageNo)
		indent = '  '
		print indent,
		print boxTextNodes[0].text,
		prevTok = boxTextNodes[0]
		for tok in boxTextNodes[1:]:
			if float(tok.attrib['y'])>(float(prevTok.attrib['y'])+v_tolerance):
				print 
				print indent,
			try:
				print tok.text,
			except:
				print 'Unicode',
			prevTok = tok
		print
		print 'Output for record:'
		pprint(info)

	#print info
	return info

def getVoterInfo(cfg, thisPage, rects, pageNo, debugMatch):
	def pointInRect(x, y, r):
		eps = 0.1
		if x<(r[0]-eps):
			return False
		if y<(r[1]-eps):
			return False
		if x>(r[2]-eps):
			return False
		if y>(r[3]-eps):
			return False
		return True

	tokens = thisPage.findall('.//TOKEN')

	voterInfo = []
	for thisRect in rects:
		# Figure out all the text nodes that belong to
		# this rect
		thisRectNodes = []
		for tok in tokens:
			x = float(tok.attrib['x'])
			y = float(tok.attrib['y'])
			w = float(tok.attrib['width'])
			h = float(tok.attrib['height'])
			if pointInRect(x,y, thisRect):
				thisRectNodes.append(tok)	

		# 
		info = extractVoterInfo(cfg, thisRect, thisRectNodes,pageNo, debugMatch)
		if info is not None:
			voterInfo.append(info)
	return voterInfo

#
# Script execution starts here...
#

# Parse command line arguments
parser = argparse.ArgumentParser()
parser.add_argument("filename", type=str, help="file to process")
parser.add_argument("--output", type=str, help="Write results to this file, defauts to voterlist.csv")
parser.add_argument("-e", "--epic", type=str, help="EPIC number filter, use with debugging")
parser.add_argument("-p", "--page", type=int, help="Page number, use with debugging")
parser.add_argument("-s", "--source-pdf", type=str, help="Use this source PDF file for annotation. This will typically be the original source for the XML file.")
parser.add_argument("-d", "--debug", help="Generate debug information. If both 'epic' and 'page' are specified, then match both. If both are not given, then all records are dumped.  If only one is specified, then only that aspect is matched.", action="store_true")
args = parser.parse_args()

# Default to voterlist.csv if no other filename is given
if not args.output:
	args.output = 'voterlist.csv'

# Parse document, find all pages
print '%s => %s ...'%(args.filename, args.output),
sys.stdout.flush()

doc = ET.parse(args.filename) #'indented-vl-eng.xml'
root = doc.getroot()
pages = root.findall('PAGE')

loadConfig()
cfg = getConfig(args.filename)

voterInfo = []

def debugMatch(pageNo, epic):
	if not args.debug:
		return False

	# debug all ?
	if (args.epic is None) and (args.page is None):
		return True

	if (args.epic is not None) and (args.page is not None):
		if (args.epic == epic) and (args.page == pageNo):
			return True
		return False

	if (args.epic is not None) and (args.epic == epic):
		return True

	if (args.page is not None) and (args.page == pageNo):
		return True

	return False

# For each page, figure out the rects that
# contain voter info, then extract data
# from each.
for pageInfo in zip(range(len(pages)),pages):
	pageNo = pageInfo[0]+1
	# Skip pages if debug page filter is active
	if args.debug and (args.page is not None):
		if pageNo != args.page:
			continue
	rects = computeDataRegions(args.filename, cfg, pageInfo[1])
	#print 'Info about %d voters is in page %d'%(len(rects),pageInfo[0]+1)
	vInfo = getVoterInfo(cfg, pageInfo[1], rects, pageNo, debugMatch)
	if len(vInfo)>0:
		voterInfo.extend(vInfo)

print 'Total %d records.'%(len(voterInfo))

f= codecs.open(args.output,'w','utf-8')

sep = '|' # field separator

fieldOrder = ['page', 'serial', 'epic', 'name', 'age', 'sex', 'relation', 
              'relative', 'residence' ]
print >>f, string.join(fieldOrder, sep)

for vInfo in voterInfo:
	values = map(lambda fieldName: vInfo[fieldName], fieldOrder)
	values[0] = str(values[0]) # Convert page number to string
	print >>f, string.join(values, sep) 

f.close()

def createRect(r, x, y, w, h):
	attribs = {
		'style':"fill:none;stroke:#ff0000;stroke-opacity:1",
		'd':"M %f %f L %f %f L %f %f L %f %f L %f %f"%(x, y, x+w, y, x+w, y+h, x, y+h, x, y) }
	rect = ET.SubElement(r, 'ns0:path', attribs)
	return rect

if (args.debug is not None) and (args.page is not None) and (args.source_pdf is not None):
	output = 'debug.svg'
	print 'Creating %s for page %d ...'%(output, args.page)
	os.system("pdf2svg %s %s %d"%(args.source_pdf, output, args.page))
	svgDoc = ET.parse(output)
	svgRoot = svgDoc.getroot()
	for vInfo in voterInfo:
		debugInfo = vInfo['debug']
		for kv in debugInfo.keys():
			for rect in debugInfo[kv]:
				createRect(svgRoot, rect[0],rect[1],rect[2],rect[3])
	svgDoc.write(output)

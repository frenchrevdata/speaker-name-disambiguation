#!/usr/bin/env python
# -*- coding=utf-8 -*-

"""
Iterates through all speeches but only looks at the speaker name in order to do speaker disambiguation
"""

from bs4 import BeautifulSoup
import unicodedata
import os
import csv
import pickle
import regex as re
import pandas as pd
import numpy as np
from nltk import word_tokenize
from nltk.util import ngrams
import collections
from collections import Counter
import os
import gzip
from make_ngrams import compute_ngrams
import xlsxwriter
from processing_functions import remove_diacritic, load_speakerlist, write_to_excel
from make_ngrams import make_ngrams
from parse_speaker_names import compute_speaker_Levenshtein_distance, read_names


#Seance followed by less than or equal to 4 line breaks (\n) then date value =
daily_regex = '(?:Séance[\s\S]{0,200}<date value=\")(?:[\s\S]+)(?:Séance[\s\S]{0,200}<date value=\")'
page_regex = '(?:n=\"([A-Z0-9]+)" id="[a-z0-9_]+")\/>([\s\S]{1,9000})<pb '
vol_regex = 'AP_ARTFL_vols\/AP(vol[0-9]{1,2}).xml'
footnote_regex = r'<note place="foot">[\w\W]+<\/note>'

speechid_to_speaker = {}
speakers_seen = set()
speaker_dists = []
speaker_dists_split = []
names_not_caught = set()

def parseFiles(raw_speeches, multiple_speakers):
	# Assumes all xml files are stored in a Docs folder in the same directory as the python file
    files = os.listdir("AP_ARTFL_vols/")
    dates = set()
    for filename in files:
        if filename.endswith(".xml"):
        	print(filename)
        	filename = open('AP_ARTFL_vols/' + filename, "r")
        	# Extracts volume number
        	volno = re.findall(vol_regex, str(filename))[0]
        	contents = filename.read()
        	soup = BeautifulSoup(contents, 'lxml')
        	pages = re.findall(page_regex, contents)
        	# Find all the sessions in the xml
        	sessions = soup.find_all(['div3'], {"type": ["other"]})
        	sessions_other = soup.find_all(['div2'], {"type": ["session"]})
        	sessions = sessions + sessions_other
        	# sessions = soup.find_all(['div2', 'div3'], {"type": ["session", "other"]})

        	for session in sessions:
		        date = extractDate(session)
		        # Restricts to valid dates we want to look at
		        if (date >= "1789-05-05") and (date <= "1795-01-04") and (date != "error"):
		        	# Datas is a dataset keeping track of dates already looked at
		        	# Accounts for multiple sessions per day
		        	if date in dates:
		        		date = date + "_soir"
		        		if date in dates:
		        			date = date + "2"
		        			findSpeeches(raw_speeches, multiple_speakers, session, date, volno)
		        		else:
		        			findSpeeches(raw_speeches, multiple_speakers, session, date, volno)
		        			dates.add(date)		        		
		        	else:
		        		findSpeeches(raw_speeches, multiple_speakers, session, date, volno)
		        		dates.add(date)
	        filename.close()


def findSpeeches(raw_speeches, multiple_speakers, daily_soup, date, volno):
	id_base = date.replace("/","_")
	number_of_speeches = 0
	presidents = [">le President", "Le President", "Mle President", "President", "le' President", "Le Preesident", "Le Preseident", "Le Presidant", "Le Presideait", "le Presiden", "le President", "Le president", "le president", "Le President,", "Le Presideut", "Le Presidtent", "le Presient", "le Presldent", "le'President"]
	full_speaker_names = pickle.load(open("dated_names.pickle", "rb"))
	for talk in daily_soup.find_all('sp'):
		# Tries to extract the speaker name and edits it for easier pairing with the Excel file
		try:
			speaker = talk.find('speaker').get_text()
			speaker = remove_diacritic(speaker).decode('utf-8')
			speaker = speaker.replace("M.","").replace("MM ", "").replace("MM. ","").replace("M ", "").replace("de ","").replace("M. ","").replace("M, ","").replace("M- ","").replace("M; ","").replace("M* ","").replace(".","").replace(":","").replace("-", " ")
			if speaker.endswith(","):
				speaker = speaker[:-1]
			if speaker.endswith(", "):
				speaker = speaker[:-1]
			if speaker.startswith(' M. '):
				speaker = speaker[3:]
			if speaker.startswith(' '):
				speaker = speaker[1:]
			if speaker.endswith(' '):
				speaker = speaker[:-1]
		except AttributeError:
			speaker = ""

		speaker = speaker.lower()

		# Removes the footnotes
		while talk.find("note"):
			ftnotes = talk.note.extract()

		# Piece together full speech if in multiple paragraph tags
		speech = talk.find_all('p')
		text = ""
		full_speech = ""
		parano = 0
		speaker_note = ""
		for section in speech:
			# Find information in parathenses, generally has the department name
			if parano == 0:
				para = section.get_text()
				if len(para) > 1:
					if para[0] == "(" or para[1] == "(":
						speaker_notes = re.findall(r'\([\s\S]{0,300}\)', para)
						if speaker_notes:
							speaker_note = speaker_notes[0]
						else:
							speaker_note = ""
			text = text + " " + section.get_text()
			parano += 1
		full_speech = remove_diacritic(text).decode('utf-8')
		full_speech = re.sub(r'\([0-9]{1,3}\)[\w\W]{1,100}', ' ', full_speech)
		full_speech = full_speech.replace("\n"," ").replace("--"," ").replace("!"," ")
		full_speech = re.sub(r'([ ]{2,})', ' ', full_speech)
		full_speech = re.sub(r'([0-9]{1,4})', ' ', full_speech)

		# Conduct name_disambiguation
		full_speaker_names = read_names("APnames.xlsx")
		# full_speaker_names = pickle.load(open("dated_names.pickle", "rb"))
		if (speaker.find(",") != -1) and (speaker.find(" et ") != -1):
			#only store multiple speakers when length of speech greater than 100
			speaker_name = "multi"
			if len(full_speech) >= 100:
				multiple_speakers[speaker] = [full_speech, str(volno), str(date)]
		elif (speaker.find(" et ") != -1):
			speaker_name = "multi"
			if len(full_speech) >= 100:
				multiple_speakers[speaker] = [full_speech, str(volno), str(date)]
		else:
			# Check to make sure have not already tried to disambiguate that speaker
			if speaker not in speakers_seen:
				matches = compute_speaker_Levenshtein_distance(speaker, full_speaker_names)
				speaker_dists.append([speaker, matches, volno, date, speaker_note])
				for full_speaker in matches:
					speaker_dists_split.append([speaker, full_speaker[0], full_speaker[1], volno, date, speaker_note])
		speakers_seen.add(speaker)


# Parses dates from file being analyzed
def extractDate(soup_file):
	dates = soup_file.find_all('date')
	relevant_dates = []
	for date in dates:
		if date.attrs:
			relevant_dates.append(date)
	if (len(relevant_dates) > 0):
		return(relevant_dates[0]['value'])
	else:
		return("error")

if __name__ == '__main__':
	import sys

	raw_speeches = {}
	multiple_speakers = {}
	parseFiles(raw_speeches, multiple_speakers)

	# Stores data in files to then be merged with AN dataset
	speaker_distances = pd.DataFrame(speaker_dists, columns = ["Speaker Name", "Levenshtein Dists", "Volno", "Date", "Departments/Notes"])
	write_to_excel(speaker_distances, "speaker_distances.xlsx")

	speaker_distances_split = pd.DataFrame(speaker_dists_split, columns = ["Speaker Name", "Full Name", "Distance", "Volno", "Date", "Department/Notes"])
	write_to_excel(speaker_distances_split, "speaker_distances_split.xlsx")

	
    
       
   	

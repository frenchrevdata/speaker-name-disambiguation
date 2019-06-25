#!/usr/bin/env python
# -*- coding=utf-8 -*-

"""
Does the majority of the data parsing of the XML files and outputs two critical files -- raw_speeches and speechid_to_speaker.
It also keeps track of errors in the XML files.
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
from processing_functions import remove_diacritic, load_speakerlist
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
footnotes = []
names_not_caught = set()
speeches_per_day = {}
speakers_using_find = set()
speakers = set()
speaker_num_total_speeches = {}
speaker_num_total_chars = {}
speakers_per_session = {}
global speaker_list

def parseFiles(raw_speeches, multiple_speakers):
	# Assumes all xml files are stored in a Docs folder in the same directory as the python file
    files = os.listdir("AP_ARTFL_vols/")
    dates = set()
    num_sessions = 0
    num_morethan1_session = 0
    for filename in files:
        if filename.endswith(".xml"):
        	print(filename)
        	filename = open('AP_ARTFL_vols/' + filename, "r")
        	# Extracts volume number to keep track of for names_not_caught and speakers_using_find
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
		        	num_sessions += 1
		        	if date in dates:
		        		num_morethan1_session += 1
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
	pickle_filename = "num_sessions.pickle"
    with open("num_sessions.pickle", 'wb') as handle:
    	pickle.dump(num_sessions, handle, protocol = 0)
    pickle_filename = "num_morethan1_session.pickle"
    with open("num_morethan1_session.pickle", 'wb') as handle:
    	pickle.dump(num_morethan1_session, handle, protocol = 0)

def findSpeeches(raw_speeches, multiple_speakers, daily_soup, date, volno):
	id_base = date.replace("/","_")
	number_of_speeches = 0
	presidents = [">le President", "Le President", "Mle President", "President", "le' President", "Le Preesident", "Le Preseident", "Le Presidant", "Le Presideait", "le Presiden", "le President", "Le president", "le president", "Le President,", "Le Presideut", "Le Presidtent", "le Presient", "le Presldent", "le'President"]
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
			# ftnotes = remove_diacritic(ftnotes.get_text()).decode('utf-8')
			# ftnotes = ftnotes.replace("\n","").replace("\r","").replace("\t","").replace("  "," ")
			# speech_id = "" + id_base + "_" + str(number_of_speeches + 1)
			# footnotes.append([ftnotes, speaker, speech_id, volno])


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


		# full_speaker_names = read_names("APnames.xlsx")
		full_speaker_names = pickle.load(open("dated_names.pickle", "rb"))
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
			if speaker not in speakers_seen:
				matches = compute_speaker_Levenshtein_distance(speaker, full_speaker_names)
				speaker_dists.append([speaker, matches, volno, date, speaker_note])
				for full_speaker in matches:
					speaker_dists_split.append([speaker, full_speaker[0], full_speaker[1], volno, date, speaker_note])
		speakers_seen.add(speaker)

			# if speaker not in speaker_dists:
			# 	speaker_dists[speaker] = compute_speaker_Levenshtein_distance(speaker)	

			# speakers_not_matched = []

			# if speaker not in speaker_dists:
			# 	speaker_distances = compute_speaker_Levenshtein_distance(speaker)
			# 	# Need to look at only the top two and if less than or equal to 1 distance keep it, otherwise say not found
			# 	if speaker_distances[0][1] <= 1:
			# 		speaker = speaker_distances[0][0]
			# 	else:
			# 		speaker_dists[speaker] = speaker_distances	


		# Speaker name is set to the full speaker name extracted from the Excel file
		speaker_name = ""


		# Only look at speeches not form the president
		if speaker not in presidents:
			if speaker in speaker_list.index.values:
				for j, name in enumerate(speaker_list.index.values):
					if speaker == name:
						speaker_name = speaker_list["FullName"].iloc[j]
			else:
				for i, name in enumerate(speaker_list['LastName']):
					# Ensures not looking at a list of speakers
					if (speaker.find(",") != -1) and (speaker.find(" et ") != -1):
						#only store multiple speakers when length of speech greater than 100
						speaker_name = "multi"
						if len(full_speech) >= 100:
							multiple_speakers[speaker] = [full_speech, str(volno), str(date)]
					else:
						# Looks if speaker name embedded in any names in the Excel file
						if speaker.find(name) != -1 :
							speaker_name = speaker_list["FullName"].iloc[i]
							# Adds the speakers_using_find list to do a manual check to ensure that no names are mischaracterized
							speakers_using_find.add(speaker + " : " + remove_diacritic(speaker_name).decode('utf-8') + "; " + str(volno) + "; " + str(date) + "\n")
		else:
			speaker_name = "president"
		# Creates the unique speech id
		if (speaker_name is not "") and (speaker_name is not "multi") and (speaker_name is not "president"):
			speaker_name = remove_diacritic(speaker_name).decode('utf-8')
			number_of_speeches = number_of_speeches + 1
			if(speaker_name in speaker_num_total_speeches):
				speaker_num_total_speeches[speaker_name] = speaker_num_total_speeches[speaker_name] + 1
			else:
				speaker_num_total_speeches[speaker_name] = 1
			if(speaker_name in speaker_num_total_chars):
				speaker_num_total_chars[speaker_name] = speaker_num_total_chars[speaker_name] + len(full_speech)
			else:
				speaker_num_total_chars[speaker_name] = len(full_speech)
			if id_base in speakers_per_session:
				speakers_per_session[id_base].add(speaker_name)
			else:
				speakers_per_session[id_base] = set()
				speakers_per_session[id_base].add(speaker_name)
			speakers.add(speaker_name)
			speech_id = "" + id_base + "_" + str(number_of_speeches)
			speechid_to_speaker[speech_id] = speaker_name
			raw_speeches[speech_id] = full_speech
		else:
			if (speaker_name is not "multi") and (speaker_name is not "president"):
				names_not_caught.add(speaker + "; " + str(volno) + "; " + str(date) + "\n")

	speeches_per_day[id_base] = number_of_speeches


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
	speaker_list = load_speakerlist('Copy of AP_Speaker_Authority_List_Edited_3.xlsx')

	raw_speeches = {}
	multiple_speakers = {}
	parseFiles(raw_speeches, multiple_speakers)

	speaker_distances = pd.DataFrame(speaker_dists, columns = ["Speaker Name", "Levenshtein Dists", "Volno", "Date", "Departments/Notes"])

	write_to = pd.ExcelWriter("speaker_distances.xlsx")
	speaker_distances.to_excel(write_to, 'Sheet1')
	write_to.save()

	speaker_distances_split = pd.DataFrame(speaker_dists_split, columns = ["Speaker Name", "Full Name", "Distance", "Volno", "Date", "Department/Notes"])

	write_to = pd.ExcelWriter("speaker_distances_split.xlsx")
	speaker_distances_split.to_excel(write_to, 'Sheet1')
	write_to.save()

	footnotes = pd.DataFrame(footnotes, columns = ["Footnote", "Speaker", "Speechid", "Volno"])

	write_to = pd.ExcelWriter("footnotes.xlsx")
	footnotes.to_excel(write_to, 'Sheet1')
	write_to.save()

	# w = csv.writer(open("speaker_dists.csv", "w"))
	# for key, val in speaker_dists.items():
	# 	w.writerow([key,val])

	# # Writes data to relevant files
	# txtfile = open("names_not_caught.txt", 'w')
	# for name in sorted(names_not_caught):
	# 	txtfile.write(name)
	# txtfile.close()

	# file = open('speakers_using_find.txt', 'w')
	# for item in sorted(speakers_using_find):
	# 	file.write(item)
	# file.close()

	# file = open('speakers.txt', 'w')
	# for item in sorted(speakers):
	# 	file.write(item + "\n")
	# file.close()

	# pickle_filename = "speechid_to_speaker.pickle"
	# with open(pickle_filename, 'wb') as handle:
	# 	pickle.dump(speechid_to_speaker, handle, protocol = 0)
	# w = csv.writer(open("rspeechid_to_speaker.csv", "w"))
	# for key, val in speechid_to_speaker.items():
	# 	w.writerow([key,val])

	# pickle_filename_2 = "raw_speeches.pickle"
	# with open(pickle_filename_2, 'wb') as handle:
	# 	pickle.dump(raw_speeches, handle, protocol = 0)
	# w = csv.writer(open("raw_speeches.csv", "w"))
	# for key, val in raw_speeches.items():
	# 	w.writerow([key,val])

	# pickle_filename_3 = "multiple_speakers.pickle"
	# with open(pickle_filename_3, 'wb') as handle:
	# 	pickle.dump(multiple_speakers, handle, protocol = 0)

	# pickle_filename_2 = "speaker_num_total_speeches.pickle"
	# with open(pickle_filename_2, 'wb') as handle:
	# 	pickle.dump(speaker_num_total_speeches, handle, protocol = 0)

	# pickle_filename_2 = "speaker_num_total_chars.pickle"
	# with open(pickle_filename_2, 'wb') as handle:
	# 	pickle.dump(speaker_num_total_chars, handle, protocol = 0)

	# pickle_filename_2 = "speakers.pickle"
	# with open(pickle_filename_2, 'wb') as handle:
	# 	pickle.dump(speakers, handle, protocol = 0)

	# pickle_filename_2 = "speeches_per_session.pickle"
	# with open(pickle_filename_2, 'wb') as handle:
	# 	pickle.dump(speeches_per_day, handle, protocol = 0)

	# pickle_filename = "speakers_per_session.pickle"
	# with open(pickle_filename, 'wb') as handle:
	# 	pickle.dump(speakers_per_session, handle, protocol = 0)

	# w = csv.writer(open("speaker_num_total_speeches.csv", "w"))
	# for key, val in speaker_num_total_speeches.items():
	# 	w.writerow([key, val])

	# w = csv.writer(open("speaker_num_total_chars.csv", "w"))
	# for key, val in speaker_num_total_chars.items():
	# 	w.writerow([key, val])

	# w = csv.writer(open("speeches_per_session.csv", "w"))
	# for key, val in speeches_per_day.items():
	# 	w.writerow([key, val])

	# w = csv.writer(open("multiple_speakers.csv", "w"))
	# for key, val in multiple_speakers.items():
	# 	w.writerow([key, val])

    
       
   	

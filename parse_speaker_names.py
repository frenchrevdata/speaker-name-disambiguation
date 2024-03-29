#!/usr/bin/env python
# -*- coding=utf-8 -*-

"""
Helper file for name disambiguation
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
from processing_functions import remove_diacritic, load_speakerlist, cosine_similarity
from make_ngrams import make_ngrams
from itertools import islice, izip
from Levenshtein import distance

def read_names(name_file):
	pd_list = pd.read_excel(name_file)
	pd_list = pd_list.set_index('Last Name')
	speakers = pd_list.index.tolist()
	for speaker in speakers:
		ind = speakers.index(speaker)
		speakers[ind] = remove_diacritic(speaker).decode('utf-8').lower()
	pd_list.index = speakers
	full_names = []
	for full_name in pd_list["Full Name"]:
		full_names.append(remove_diacritic(full_name).decode('utf-8').lower())
	pd_list["Full Name"] = full_names
	speakers_to_remove = []
	speakers_to_keep = []

	# Need to look if dates of speaker are within the timeframe of the Girondins/Montgnards
	for j, speaker in enumerate(pd_list.index.values):
		valid_date = False
		depute_de = pd_list["Depute de"].iloc[j]
		if depute_de == 1792.0 or depute_de == 1793.0:
			valid_date = True
		depute_a = pd_list["Depute a"].iloc[j]
		if depute_a == 1792.0 or depute_a == 1793.0:
			valid_date = True
		if (depute_de <= 1792.0 and depute_a >= 1792.0) or (depute_de <= 1793.0 and depute_a >= 1793.0):
			valid_date = True
		depute_de2 = pd_list["Depute puis de 2"].iloc[j]
		if depute_de2:
			if depute_de2 == 1792.0 or depute_de2 == 1793.0:
				valid_date = True
		depute_a2 = pd_list["Depute a 2"].iloc[j]
		if depute_a2:
			if depute_a2 == 1792 or depute_a2 == 1793.0:
				valid_date = True
		if depute_de2 and depute_a2:
			if (depute_de2 <= 1792.0 and depute_a2 >= 1792.0) or (depute_de2 <= 1793.0 and depute_a2 >= 1793.0):
				valid_date = True
		depute_de3 = pd_list["Depute puis de 3"].iloc[j]
		if depute_de3:
			if depute_de3 == 1792.0 or depute_de3 == 1793.0:
				valid_date = True
		depute_a3 = pd_list["Depute a 3"].iloc[j]
		if depute_a3:
			if depute_a3 == 1792.0 or depute_a3 == 1793.0:
				valid_date = True
		if depute_de3 and depute_a3:
			if (depute_de3 <= 1792.0 and depute_a3 >= 1792.0) or (depute_de3 <= 1793.0 and depute_a3 >= 1793.0):
				valid_date = True


		if valid_date == False:
			speakers_to_remove.append(j)
		if valid_date == True:
			speakers_to_keep.append(j)


	pd_list = pd_list.iloc[speakers_to_keep]
	pickle_filename = "dated_names.pickle"
	with open(pickle_filename, 'wb') as handle:
		pickle.dump(pd_list, handle, protocol = 0)
	return pd_list


# Finds the distance of the speaker name extracted from the XML to the last name
# in the AN data and the full name in the AN data
def compute_speaker_Levenshtein_distance(speaker_name, full_speaker_names):
	distance_size = {}

	# Finds distance to full name
	for i, speaker in enumerate(full_speaker_names['Full Name']):
		# Levenshtein distance
		if isinstance(speaker_name, str):
			speaker_name = unicode(speaker_name,"ascii", errors = "ignore")
		if isinstance(speaker, str):
			speaker = unicode(speaker,"ascii", errors = "ignore")
		dist = distance(speaker, speaker_name)
		distance_size[speaker] = dist

	# Finds distance to last name
	for j, speaker in enumerate(full_speaker_names.index.values):
		# Levenshtein distance
		dist = distance(speaker, speaker_name)
		full_name = full_speaker_names["Full Name"].iloc[j]
		if full_name in distance_size:
			if dist < distance_size[full_name]:
				distance_size[full_name] = dist
		else:
			distance_size[full_name] = dist

	dist_size_sorted = sorted(distance_size.items(), key = lambda kv: kv[1])

	return dist_size_sorted[:2]


if __name__ == '__main__':
	import sys



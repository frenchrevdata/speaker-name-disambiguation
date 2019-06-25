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

def read_names_file(name_file):
	# pd_list = pd.read_excel("an_names.xls")
	pd_list = pd.read_excel(name_file)
	pd_list = pd_list.set_index('Full Name')
	speakers = pd_list.index.tolist()
	for speaker in speakers:
		ind = speakers.index(speaker)
		speakers[ind] = remove_diacritic(speaker).decode('utf-8').lower()
	pd_list.index = speakers
	return pd_list


def read_speaker_dist(name_file):
	pd_list = pd.read_excel(name_file)
	pd_list = pd_list.set_index('Full Name')
	return pd_list

def match_data(full_speaker_names, speaker_dist_df):
	new_df = full_speaker_names.join(speaker_dist_df, how="outer")

	write_to = pd.ExcelWriter("merged_speaker_names_df.xlsx")
	new_df.to_excel(write_to, 'Sheet1')
	write_to.save()


if __name__ == '__main__':
	import sys
	full_speaker_names = read_names_file("APnames.xlsx")
	speaker_dist_df = read_speaker_dist("speaker_distances_split.xlsx")
	match_data(full_speaker_names, speaker_dist_df)
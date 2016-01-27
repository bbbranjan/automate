from django.shortcuts import render

# Create your views here.
from django.http import HttpResponse
from django.shortcuts import render_to_response, render
from . import tinderbot

import operator
import argparse
import sys
import pynder
import urllib

#rake stuff
import re
import operator

sys.path.insert(0, 'src/')

from PIL import Image
from Pixel import * 
from Region import *
from utils import *

def index(request):
    return render_to_response('index.html')

def main(request):
    if request.method=='POST':
        min_percent = request.POST.get('percentage')
        compute(request, min_percent)
    return render(request,'main.html')

#nude.py functions
def contains_nudity(image_path):
    image = Image.open(image_path)
    imgPixels = image.load()
    width = image.size[0]
    height = image.size[1]
    pixels = [ [None]*height for i in range(width) ]

    for i in xrange(0, width):
        for j in xrange(0, height):
            pixels[i][j] = Pixel(i, j, imgPixels[i,j][0], imgPixels[i,j][1], imgPixels[i,j][2])
    
    skin_pixels = []
    skin_regions = []
    create_skin_regions(pixels, skin_pixels, skin_regions, width, height)

    if len(skin_regions) < 3:
        return 0.0
    skin_regions.sort(key = operator.attrgetter('size'), reverse=True)

    bounding_region = create_bounding_region(pixels, skin_regions, width, height)
    return analyze_regions(skin_pixels, skin_regions, bounding_region, width, height)


def color_skin(image_path):
    save_path = image_path[:-4] + "-skinified.jpg"
    color_skin_regions(image_path, save_path)


#rake functions
def is_number(s):
    try:
        float(s) if '.' in s else int(s)
        return True
    except ValueError:
        return False


def load_stop_words(stop_word_file):
    """
    Utility function to load stop words from a file and return as a list of words
    @param stop_word_file Path and file name of a file containing stop words.
    @return list A list of stop words.
    """
    stop_words = []
    for line in open(stop_word_file):
        if line.strip()[0:1] != "#":
            for word in line.split():  # in case more than one per line
                stop_words.append(word)
    return stop_words


def separate_words(text, min_word_return_size):
    """
    Utility function to return a list of all words that are have a length greater than a specified number of characters.
    @param text The text that must be split in to words.
    @param min_word_return_size The minimum no of characters a word must have to be included.
    """
    splitter = re.compile('[^a-zA-Z0-9_\\+\\-/]')
    words = []
    for single_word in splitter.split(text):
        current_word = single_word.strip().lower()
        #leave numbers in phrase, but don't count as words, since they tend to invalidate scores of their phrases
        if len(current_word) > min_word_return_size and current_word != '' and not is_number(current_word):
            words.append(current_word)
    return words


def split_sentences(text):
    """
    Utility function to return a list of sentences.
    @param text The text that must be split in to sentences.
    """
    sentence_delimiters = re.compile(u'[.!?,;:\t\\\\"\\(\\)\\\'\u2019\u2013]|\\s\\-\\s')
    sentences = sentence_delimiters.split(text)
    return sentences


def build_stop_word_regex(stop_word_file_path):
    stop_word_list = load_stop_words(stop_word_file_path)
    stop_word_regex_list = []
    for word in stop_word_list:
        word_regex = r'\b' + word + r'(?![\w-])'  # added look ahead for hyphen
        stop_word_regex_list.append(word_regex)
    stop_word_pattern = re.compile('|'.join(stop_word_regex_list), re.IGNORECASE)
    return stop_word_pattern


def generate_candidate_keywords(sentence_list, stopword_pattern):
    phrase_list = []
    for s in sentence_list:
        tmp = re.sub(stopword_pattern, '|', s.strip())
        phrases = tmp.split("|")
        for phrase in phrases:
            phrase = phrase.strip().lower()
            if phrase != "":
                phrase_list.append(phrase)
    return phrase_list


def calculate_word_scores(phraseList):
    word_frequency = {}
    word_degree = {}
    for phrase in phraseList:
        word_list = separate_words(phrase, 0)
        word_list_length = len(word_list)
        word_list_degree = word_list_length - 1
        #if word_list_degree > 3: word_list_degree = 3 #exp.
        for word in word_list:
            word_frequency.setdefault(word, 0)
            word_frequency[word] += 1
            word_degree.setdefault(word, 0)
            word_degree[word] += word_list_degree  #orig.
            #word_degree[word] += 1/(word_list_length*1.0) #exp.
    for item in word_frequency:
        word_degree[item] = word_degree[item] + word_frequency[item]

    # Calculate Word scores = deg(w)/frew(w)
    word_score = {}
    for item in word_frequency:
        word_score.setdefault(item, 0)
        word_score[item] = word_degree[item] / (word_frequency[item] * 1.0)  #orig.
    #word_score[item] = word_frequency[item]/(word_degree[item] * 1.0) #exp.
    return word_score


def generate_candidate_keyword_scores(phrase_list, word_score):
    keyword_candidates = {}
    for phrase in phrase_list:
        keyword_candidates.setdefault(phrase, 0)
        word_list = separate_words(phrase, 0)
        candidate_score = 0
        for word in word_list:
            candidate_score += word_score[word]
        keyword_candidates[phrase] = candidate_score
    return keyword_candidates


class Rake(object):
    def __init__(self, stop_words_path):
        self.stop_words_path = stop_words_path
        self.__stop_words_pattern = build_stop_word_regex(stop_words_path)

    def run(self, text):
        sentence_list = split_sentences(text)

        phrase_list = generate_candidate_keywords(sentence_list, self.__stop_words_pattern)

        word_scores = calculate_word_scores(phrase_list)

        keyword_candidates = generate_candidate_keyword_scores(phrase_list, word_scores)

        sorted_keywords = sorted(keyword_candidates.iteritems(), key=operator.itemgetter(1), reverse=True)
        return sorted_keywords

#####

def compute(request, min_percent):
    limit=3

    session = pynder.Session('chait9', 'CAAGm0PX4ZCpsBAO0R8SZAWsFZAZA2pbWs7LkyXhpLXhqDQW9kcAAZC6SDcE3Qb3ofqr2pYHmZBSQFnbctn6P8ctT9p32XPizhAQYOCVQaIPMbgq22wZBCaS00Dft9S2xhSTFKOIIbidiS2GIhngEToT4CZASnUlrU0mhWzBbJTXTyEIj188PbDB6if9uB5IZB7SMzZAmKatG96ERw6pSO1glpB')
    total_users=session.nearby_users()
    if len(total_users) > limit:
        few_users=total_users[:limit]
    else:
        few_users=total_users
    userid=0
    count=0
    for user in few_users:
        print('\n')

        total_skin_percent=0.0
        bio_score=0.0
        final_percent=0.0

        try:
            for i in range(3):
                image_name = 'photo' + str(count) + str(i) + '.jpg'
                photo_url = str(user.get_photos(width='640')[i])
                print photo_url
                image = urllib.URLopener()
                image.retrieve(photo_url,image_name)

                parser = argparse.ArgumentParser(description='Detect nudity in images.')
                parser.add_argument(image_name, type=str, nargs=1)
#                parser.add_argument('-c', action='store_true')
                args = parser.parse_args()

                #color_skin(image_name)
                #print "Skin regions covered in image saved at " + image_name[:-4] + "-skinified.jpeg"
                skin_percent = 100*contains_nudity(image_name)
                print "Skin region percentage = " + str(skin_percent)
                total_skin_percent += skin_percent
                
                if count==0:
                    request.photo_url0=photo_url
                elif count==1:
                    request.photo_url1=photo_url
                elif count==2:
                    request.photo_url2=photo_url
            
            

        except IndexError:
                print('')

        total_skin_percent /= len(few_users)
        print total_skin_percent
        
        # THE BIO STUFF
        try:
            text = user.bio.lower().replace('\n','. ')
            # Split text into sentences
            sentenceList = split_sentences(text)
            #stoppath = "FoxStoplist.txt" #Fox stoplist contains "numbers", so it will not find "natural numbers" like in Table 1.1
            stoppath = "SmartStoplist.txt"  #SMART stoplist misses some of the lower-scoring keywords in Figure 1.5, which means that the top 1/3 cuts off one of the 4.0 score words in Table 1.1
            stopwordpattern = build_stop_word_regex(stoppath)

            # generate candidate keywords
            phraseList = generate_candidate_keywords(sentenceList, stopwordpattern)

            # calculate individual word scores
            wordscores = calculate_word_scores(phraseList)

            # generate candidate keyword scores
            keywordcandidates = generate_candidate_keyword_scores(phraseList, wordscores)
            #if debug: print keywordcandidates

            sortedKeywords = sorted(keywordcandidates.iteritems(), key=operator.itemgetter(1), reverse=True)
            #if debug: print sortedKeywords

            totalKeywords = len(sortedKeywords)
            #if debug: print totalKeywords

            rake = Rake("SmartStoplist.txt")
            keywords = rake.run(text)
            print text
            print keywords          

            word_list = {'hook up':-10, 'hookup':-10, 'single':-5, 'booty':-9, 'fuck':-10, 'sex':-7, 'swip':-3, 'conversation':5, 'stories':7, 'right':-5, 'shag':-10, 'fit':-5, 'call':-2, 'personality':4, 'body':-6, 'cuddle':-3, 'mature':-1, 'smile':3, 'exchange':-8, 'temp':-8, 'sleep':-9}
            max_score = max(wordscores.values())

            #keywords -> list of tuples. Each element- (word, wordscore)
            for element in keywords:
                for word in word_list.keys():
                    if (element[0] in word) or (word in element[0]):
                        bio_score += ( -1.0*word_list[word]*totalKeywords/len(text.split()) ) * ( element[1]*1.0 / max_score )

        except: pass

        #print bio_score

        final_percent = (total_skin_percent/50 + bio_score/5)*100
        print final_percent
        
        if count==0:
            request.photo_looks0=final_percent
            few_users[0].like()
        elif count==1:
            request.photo_looks1=final_percent
            few_users[1].like()
        elif count==2:
            request.photo_looks2=final_percent
            few_users[2].like()
        if final_percent < min_percent:
            count = count - 1
        count = count + 1
       
        

# -*- coding: utf-8 -*-
"""
Created on Sun Jun 19 16:01:09 2022

@author: glens
"""
#news API Key: 1410e45925c849f48b78138091c1635a
import requests
from bs4 import BeautifulSoup
import textstat
import os
import mysql.connector
#set library lang to espanol
textstat.set_lang('es')
from mailApp import sendEmail

def getNewsUrls(subject):
    from datetime import date, timedelta
    date = date.today()
    date = date - timedelta(1)
    date = date.strftime("%Y-%m-%d")

    url = ('https://newsapi.org/v2/everything?'
           'q='+subject+'&'
           'language=es&'
           'from='+date+'&'
           'sortBy=popularity&'
           'apiKey=' + os.environ.get('NEWS_API'))
    response = requests.get(url)
    print('response: ' + str(response))
    articles = response.json()['articles']
    articleUrls = []

    for x in range(len(articles)):
        articleUrls.append(articles[x]['url'])
    return(articleUrls)


def evaluateDifficulty(urls):
    difficulty = []
    for url in urls:
        try:
            res = requests.get(url)
            if str(res) == '<Response [200]>':
                soup = BeautifulSoup(res.text, 'html.parser')
                text = soup.find('body').text
                rating = textstat.fernandez_huerta(text)
                entry = [url, rating]
                difficulty.append(entry)
                print('ranking successful')
            else:
                continue
        except:
            print('error occured')
            continue
    print(difficulty)
    return difficulty


#function to assign human readable difficulty level and stack rank articles by diff
#collecting easiest article in case no easy articles returned
def sortUrlsByDiff(articles):
    count = 0
    urlDict = {'Fluent': [], 'Difficult': [],'Standard': [], 'Easy': []}
    difficulty = []
    while count < (len(articles) - 1) and any(n == [] for n in urlDict.values()):

        #print('Count: ' + str(count))
        url = articles[count]
        #print('URL: ' + url)
        try:
                res = requests.get(url)
                if str(res) == '<Response [200]>':
                    soup = BeautifulSoup(res.text, 'html.parser')
                    text = soup.find('body').text
                    rating = textstat.fernandez_huerta(text)
                    urlRank = [url, rating]
                    difficulty.append(urlRank)
                    if rating < 30:
                        urlDict['Fluent'].append(url)
                    elif rating < 50:
                        urlDict['Difficult'].append(url)
                    elif rating < 70:
                        urlDict['Standard'].append(url)
                    elif rating >= 70:
                        urlDict['Easy'].append(url)
                    print('Assigned: ' + str(rating))
                    count += 1
                else:
                    print('Unexpected Response: ' + str(res))
                    count += 1
                    continue
        except:
                print('error occured')
                count += 1
                continue
    difficulty.sort(key = lambda x: x[1])
    hardestArticle = difficulty[0]
    easiestArticle = difficulty[len(difficulty)-1]
    return urlDict, easiestArticle, hardestArticle

#assigns only 1 article per difficulty and hydrates missing difficulties
def trimUrlList(results):
    #parse out variables from list
    urlDict = results[0]
    easiestArticle = results[1]
    easiestArticleUrl = easiestArticle[0]
    easiestArticleRating = easiestArticle[1]

    hardestArticle = results[2]
    hardestArticleUrl = hardestArticle[0]
    hardestArticleRating = hardestArticle[1]

    #assign difficulty rating
    if easiestArticleRating > 70:
        easiestArticleRating = 'Easy'
    elif easiestArticleRating > 50:
        easiestArticleRating = 'Standard'
    elif easiestArticleRating > 30:
        easiestArticleRating = 'Difficult'
    elif easiestArticleRating <= 30:
        easiestArticleRating = 'Fluent'

    #assign only a single URL per diff rating. Also assigns closest URL for unmatched hard or easy ratings
    for key, value in urlDict.items():
        if len(value) > 0:
            urlDict[key] = value[0]
        elif len(value) == 0:
            if key == 'Easy' or key == 'Standard':
                urlDict[key] = [easiestArticleUrl, easiestArticleRating] #need to account for this len == 2 situation if no article found
            elif key == 'Difficult' or key == 'Fluent':
                urlDict[key] = [hardestArticleUrl, hardestArticleRating] #need to account for this len == 2 situation if no article found
    return urlDict


#log daily updated sample URls to enable sendNow article function
def logSamples(urlDict, topic):
#grab envVars locally or in prod
    path = ''
    if os.name == 'nt':
        path = 'C:/Users/glens/.spyder-py3/Practice Projects/SpanishDaily/SpanishDaily/home/gharold/utils/env_vars.py'
    elif os.name == 'posix':
        path = '/home/gharold/utils/env_vars.py'
    exec(open(path).read())
    connection = mysql.connector.connect(
        host=os.environ.get('DB_HOST'),
        user=os.environ.get('DB_USER'),
        password=os.environ.get('DB_PASS'),
        database=os.environ.get('DB_NAME')
    )

    topicTranslator = {
    'deportes': 'Sports',
    'noticias': 'News',
    'política': 'Politics',
    'viaje': 'Travel',
    'tecnología': 'Tech',
    'finanzas': 'Finance'
    }

    topic = topicTranslator[topic]

    for diff, url in urlDict.items():
        #converted unavailabe diffs to URLs
        if type(url) == list:
            url = url[0]
        print('url: ' + url)
        print('diff: ' + diff)
        print('topic: ' + topic)
        #set cursor
        cur = connection.cursor()
        #replace with fresh URLs
        cur.execute('UPDATE samples SET Url = %s WHERE diff = %s and topic = %s', (url, diff, topic))
        connection.commit()
    cur.close()
    connection.close()
    return 'success'

#master function to combine all above based on just a topic search
def evalTopic(topic):
    urls = getNewsUrls(topic)
    urlDict = sortUrlsByDiff(urls)
    urlDict = trimUrlList(urlDict)
    return urlDict


def sendEmails(urlDict, topic):
    #connect to db
    connection = mysql.connector.connect(
        host=os.environ.get('DB_HOST'),
        user=os.environ.get('DB_USER'),
        password=os.environ.get('DB_PASS'),
        database=os.environ.get('DB_NAME')
    )

    topicTranslator = {
    'deportes': 'Sports',
    'noticias': 'News',
    'política': 'Politics',
    'viaje': 'Travel',
    'tecnología': 'Tech',
    'finanzas': 'Finance'
    }

    topic = topicTranslator[topic]

    #set cursor
    cur = connection.cursor(dictionary=True)
     #query db to pull all emails that have 'topic' as a preference
     ##SELECT email, spanishLevel, preference FROM users INNER JOIN preferences ON users.userId=preferences.preference WHERE preferences.preference = %s

     #topics = ['Sports', 'News', 'Politics', 'Travel', 'Tech', 'Finance']
    diffs = ['Easy', 'Standard', 'Difficult', 'Fluent']

    print('urlDict: ')
    print(urlDict)
    #for every topic, loop through all spanish levels
    for diff in diffs:
        url = urlDict[diff]
        print('url: ')
        print(url)
        #grab users in the relevant topic/diff category
        cur.execute("SELECT email, spanishLevel, preference FROM users INNER JOIN preferences ON users.userId=preferences.userId WHERE preferences.preference = %s AND users.spanishLevel = %s AND users.sendEmail = 1", (topic, diff))
        recipients = []
        results = cur.fetchall()
        for sDict in results:
            recipients.append(sDict['email'])
        print(recipients)
        sendEmail(url, diff, topic, recipients)

    cur.close()
    connection.close()
    return 'success'



#topics to loop through daily
topics = ['deportes', 'noticias', 'política', 'viaje', 'tecnología', 'finanzas']

#grab envVars locally or in prod
path = ''
if os.name == 'nt':
    path = 'C:/Users/glens/.spyder-py3/Practice Projects/SpanishDaily/SpanishDaily/home/gharold/utils/env_vars.py'
elif os.name == 'posix':
    path = '/home/gharold/utils/env_vars.py'

exec(open(path).read())

for topic in topics:
    urlDict = evalTopic(topic)
    print(urlDict)
    logSamples(urlDict, topic)
    sendEmails(urlDict, topic)
#bug - articles being sent to non-subbed users, see politics and >1 news

print('Program Complete')


# =============================================================================
# urlDict structure:
#     {'Difficulty': 'URL.com',
#      'Difficulty': ['URL.com', 'attemptedDiff']} //this is only if the intended diff was not available
# =============================================================================

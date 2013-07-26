from lxml import html as lhtml
from pyquery import PyQuery as pq
from lxml import etree
import requests
from models import Proxy, AmazonMongoTradeIn, AmazonMongoTradeIn_NJ, Amazon_Textbook_Section_NR, Amazon_NR, Price_NR, Book_NR, ProfitableBooks_NR, MetaTable_NR
import re
import tasks
import random

def getROI(theBuy, theSell):
    '''Calculate the Return On Investment of the book -- assuming 3.99 Shipping cost
    '''
    theBuy = float(theBuy)
    theSell = float(theSell)
    actb = (theBuy - (theSell + 3.99)) / (theSell + 3.99)
    actb = round(actb * 100, 2)
    return actb


def isGoodProfit(obj):
    '''Looking for profit margins of >50%
    '''
    theBuy = float(obj.latest_price.buy)
    theSell = float(obj.latest_price.sell)
    actb = (theBuy - (theSell + 3.99)) / (theSell + 3.99)
    actb = round(actb * 100, 2)
    if actb >= 50.0:
        return True
    return False


def retrievePage(url, proxy=None):
    '''
    Adding headers and handling proxies for requests
    '''
    headers = {
		"Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
		"Accept-Encoding":"gzip,deflate,sdch",
		"Accept-Language":"en-US,en;q=0.8",
		"Cache-Control":"no-cache",
		"Host":"www.amazon.com",
		"Pragma":"no-cache",
		"Proxy-Connection":"keep-alive",
		"User-Agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_7_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/28.0.1500.71 Safari/537.36",
	}

    if (proxy):
        # Randomize proxies
        r = requests.get(url,proxies=proxy,headers=headers, timeout=10.0)
    else:
        r = requests.get(url, headers=headers, timeout=5.0 )
    if not r.ok:
        raise Exception("Invalid response")

    return r.content


def toAscii(content):
    return unicode(content).encode('ascii', 'ignore')


def detailAllBooks():
    objs = AmazonMongoTradeIn_NJ.objects.values_list('productcode', flat=True)
    objs = random.shuffle(objs)
    print 'Objs len is %d' % (len(objs),)
    print 'ok done with that'
    tasks.process_lots_of_items(objs)


def countBooksInCategory(url):
    '''Counts how may books are in each category, to intelligently scrape the correct number of pages.'''
    print 'counting book in %s' % (url,)
    content = retrievePage("http://amazon.com" + url)
    d = pq(content)

    s = d("#resultCount")
    resultsNoComma = 0

    if len(s):
        txt = s[0].text_content().strip()
        #print txt
        matches = re.search(r'of\s+([,\d]+) Results', txt)

        if matches != None:
            resultsNoComma = re.sub(",", "", matches.group(1))

    return resultsNoComma


# Edited on Jul23
def getAmazonBooksOnTradeinPage(url, page):
    '''Gets all the books on the tradein page'''
    print ('Getting books for ' + url + '&page=' + str(page))
    content = retrievePage("http://amazon.com" + url + "&page=" + str(page))
    d = pq(content)

    s = d('.list.results > div')
    for result in s:
        aa = d('.image a',result)
        title = d('span.lrg.bold',result).text()
        re_product_code = re.compile(r'/dp/(.*?)/')
        pc = re.findall(re_product_code, aa[0].get('href'))

        # print aa
        # print title
        # print pc

        am = AmazonMongoTradeIn_NJ()

        am.pckey = pc[0]
        am.title = title
        am.productcode = pc[0]
        am.profitable = 0

        am.save()


# Works on Jul 23
def addFacetToScan(url):
    '''
    Adding a subdirectory under Facet
    '''
    content = retrievePage(url)

    d = pq(content)

    thecontainer = d('.expand')
    if thecontainer is None:
        return

    currentHeading = d('li strong')
    currentHeading = currentHeading.parent()
    lst = currentHeading.parent()
    children = lst.children('li')
    index = children.index(currentHeading[0])
    s = children[index:]
    s = s[1:]

    #Get all navigable directories
    # No more to get -- this is a leaf node so add it to scan
    if not len(s):
        # print 'Adding finally!'
        addCategoryToScan(url)

    for cat in s:
    # Get to the anchor tag
        p1 = pq(cat)
        el = p1('a')
        if el:
            tasks.task_addFacetToScan.delay("http://www.amazon.com" + el[0].get('href'))
            # print 'Adding facet %s' % ("http://www.amazon.com" + el[0].get('href'),)
            # addFacetToScan("http://www.amazon.com" + el[0].get('href'))
    # print 'Made it thru!'


# Works on Apr 27
def addCategoryToScan(url):
    content = retrievePage(url)
    html = lhtml.fromstring(content)
    d = pq(content)
    s = d('h1#breadCrumb')
    # s = html.xpath("//h1[@id='breadCrumb']")
    breadcrumb = toAscii(s[0].text_content())

    # print breadcrumb
    # containers = html.xpath(".//*[@id='bestRefinement']")
    containers = d('#bestRefinement > a')
    # thecontainer = getFormatContainer(containers)

    #currently always going here - Apr27
    if containers is None:
        ats = Amazon_Textbook_Section_NR(title=breadcrumb, url=url)
        try:
            ats.save()
        except:
            pass
        return

    # s = thecontainer.xpath(".//div[@class='refinement']")
    for cat in containers:
        el = cat
        if len(el):
            ats = Amazon_Textbook_Section_NR(title=breadcrumb + " " + el.text_content(), url=el.get('href'))
            ats.save()


def scanCategories():
    objs = Amazon_Textbook_Section_NR.objects.all()
    for obj in objs:
        # scanCategoryAndAddBooks(obj)
        tasks.task_scanCategoryAndAddBooks.delay(obj)


def scanCategoryAndAddBooks(cat):
    books = countBooksInCategory(cat.url)
    print "Counted " + str(books)
    pages = int(books) / 12 + 1
    for i in range(1, pages + 1):
        tasks.scanTradeInPage.delay(cat.url, i)
        # tasks.scanTradeInPage(cat.url,i)


def parseUsedPage(amnj):
    # if not am.latest_price:
    #     am.price = Price_NR()
    url = 'http://www.amazon.com/gp/offer-listing/%s/ref=dp_olp_used?ie=UTF8&condition=used' % (amnj.productcode)
    theProxy = Proxy.objects.filter(active=True).order_by('?')[0]
    proxy = {theProxy.proxy_type:theProxy.ip_and_port}
    try:
        content = retrievePage(url, proxy)
    except Exception as e:
        theProxy.active = False
        theProxy.save()
        print 'WhooooooopS! We are not ok: ' + str(e)
        return
    # html = lhtml.fromstring(content)
    d = pq(content)

    matches = re.search(r'a \$?(\d*\.\d{2}) Amazon.com Gift Card', d('#olpProduct + div').text())
    buyprice = None
    if matches != None:
        buyprice = matches.group(1)

    # results = html.xpath("//tbody[@class='result']")
    results = d('.olpOffer')

    for result in results:
        try:
            if re.search('Acceptable', d('.olpCondition',result).text()):
                continue
            if re.search('nternational', d('.comments',result).text()):
                continue
        except:
            continue

        sellprice = re.match('\$?(\d*\.\d{2})', d('.olpOfferPrice',result).text())
        if sellprice != None and buyprice != None:
            sellprice = sellprice.group(1)
            amnj.buy = buyprice
            amnj.sell = sellprice
            # price = Price_NR(buy=buyprice, sell=sellprice)
        else:
            amnj.buy = buyprice
            amnj.sell = 0

        if amnj.buy and amnj.sell:
            roi = getROI(amnj.buy, amnj.sell)
            if roi:
                amnj.profitable = roi
            else:
                amnj.profitable = 0



        try:
            amnj.save()
        except:
            print 'Throwing!'
            print amnj.buy
            print amnj.sell
            print amnj.profitable
        print 'After! ' + str(amnj)
        break


def addProxies(s):
    s = s.splitlines()
    for i in s:
        try:
            Proxy(ip_and_port=i,proxy_type='http').save()
        except:
            pass



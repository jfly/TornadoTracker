import os
import time
import argparse
import datetime
import ParseTornado

from dropbox.client import DropboxClient
from dropbox.session import DropboxSession

TOKENS = 'dropbox_token.txt'
APP_KEY_SECRET = 'dropbox_key_secret.txt'
assert os.path.exists(APP_KEY_SECRET)
APP_KEY, APP_SECRET = open(APP_KEY_SECRET).read().strip().split("\n")

ACCESS_TYPE = 'app_folder'

DROPBOX_WAIT_PERIOD = 60

analyzedFolder = None
indexHtmlFile = None
parserByTimestamp = {}

# Number wrapper that doesn't print out a trailing L for longs
class CustomInt(object):
    def __init__(self, i):
        self.i = i
    def __repr__(self):
        return str(self.i)

def generateHtml():
    table = "<table class='gridtable'>\n"
    table += "<thead>\n"
    table += "<tr>\n"
    table += "<th>Date</th><th>Value</th><th></th>\n"
    table += "</tr>\n"
    table += "</thead>\n"
    data = []
    for timestamp, parser in sorted(parserByTimestamp.iteritems()):
        digits = parser.digits()
        if parser.failedTest():
            table += "<tr class='failTest'>\n"
        elif any(d is None for d in digits):
            table += "<tr class='fail'>\n"
        else:
            table += "<tr class='success'>\n"
            value = int("".join(str(d) for d in digits))
            data.append([CustomInt(timestamp*1000), value])
        link = os.path.relpath(parser.htmlFile, analyzedFolder)
        image = os.path.relpath(parser.stepImage(8), analyzedFolder)
        prettyDate = datetime.datetime.fromtimestamp(timestamp).ctime()
        table += "<td><a href='%s'>%s</a></td><td>%s</td><td><img style='height: 20px;' src='%s'/></td>\n" % ( link, prettyDate, "".join(str(d) for d in digits), image )
        table += "</tr>\n"

    table += "</tbody>\n</table>\n"

    html = """<html>
<head>
<title>Tornado Tracker</title>
<style type="text/css">
table.gridtable {
    font-family: verdana,arial,sans-serif;
    font-size:11px;
    border-width: 1px;
    border-color: #666666;
    border-collapse: collapse;
}
table.gridtable th {
    border-width: 1px;
    padding: 8px;
    border-style: solid;
    border-color: #666666;
}
table.gridtable td {
    border-width: 1px;
    padding: 8px;
    border-style: solid;
    border-color: #666666;
}

table.gridtable tr.success {
    background-color: green;
}

table.gridtable tr.fail {
}

table.gridtable tr.failTest {
    background-color: red;
}

#graphContainer {
    height: 100%%;
}
</style>

<script type="text/javascript" src="http://ajax.googleapis.com/ajax/libs/jquery/1.9.1/jquery.min.js"></script>
<script src="http://code.highcharts.com/stock/highstock.js"></script>
<script src="http://code.highcharts.com/stock/modules/exporting.js"></script>
<script type="text/javascript">
$(function() {
    Highcharts.setOptions({
        global: {
            useUTC: false
        },
        lang: {
            showDetailsTitle: 'Show Details',
        }
    });
    var highchart = $('#graphContainer').highcharts('StockChart', {
        title: {
            text: 'Number of coin op presses'
        },
        
        xAxis: {
            gapGridLineWidth: 1,
            ordinal: false
        },
        
        rangeSelector : {
            buttons : [{
                type : 'hour',
                count : 1,
                text : '1h'
            }, {
                type : 'day',
                count : 1,
                text : '1D'
            }, {
                type : 'all',
                count : 1,
                text : 'All'
            }],
            selected : 2,
            inputEnabled : false
        },
        
        series: [{
            name : 'presses',
            data: %s,
            gapSize: null,
            tooltip: {
                valueDecimals: 0
            },
            threshold: null
        }],
        exporting: {
            buttons: {
                'toggleDetailsButton': {
                    _id: 'toggleDetailsButton',
                    x: -62,
                    symbolFill: '#B5C9DF',
                    hoverSymbolFill: '#779ABF',
                    onclick: function() {
                        toggleDetails();
                        // Adding/removing details may induce/remove a vertical
                        // scrollbar. Fortunately, highcharts listens for window
                        // resizes to reflow the table. Unfortunately, we can't
                        // call that code directly, but jquery lets us tickle it.
                        $(window).trigger('resize');
                    },
                    _titleKey: "showDetailsTitle",
                    text: "Toggle Details"
                }
            }
        }
    });
    function toggleDetails() {
        var sheetContainer = document.getElementById("sheetContainer");
        if(sheetContainer.style.display == '') {
            sheetContainer.style.display = 'none';
        } else {
            sheetContainer.style.display = '';
        }
    }
    toggleDetails(); // hide details
});
</script>
</head>
<body>
<div id="graphContainer"></div>
<div id="sheetContainer">
<p>Last updated %s</p>
%s
</div>
</body>
</html>
""" % ( repr(data), datetime.datetime.now().ctime(), table )
    f = open(indexHtmlFile, 'w')
    f.write(html)
    f.close()
    print "Updated %s" % indexHtmlFile
def rm(path):
    if os.path.isdir(path):
        shutil.rmtree(path)
    elif os.path.exists(path):
        os.unlink(path)

def handleEntries(client, entries, forceReparse=False):
    for i, (path, metadata) in enumerate(entries):
        print "Processing entry %s/%s: %s" % ( i+1, len(entries), path )
        timestamp, ext = os.path.splitext(os.path.basename(path))
        if ext == ".jpg":
            parsedImageDir = os.path.join(analyzedFolder, timestamp)
            if metadata is None:
                rm(parsedImageDir)
                continue

            if metadata['is_dir']:
                continue

            def imageFileGetter():
                return client.get_file(path)
            timestamp, correctDigits = ParseTornado.splitTimestampAndCorrect(path)
            parser = ParseTornado.Parser(timestamp, imageFileGetter, analyzedFolder, correctDigits=correctDigits)
            parserByTimestamp[parser.timestamp] = parser
            digits = parser.digits(forceReparse=forceReparse)
            if any(d is None for d in digits):
                print "Failed to parse, see %s" % parser.htmlFile
            else:
                print "Successfully parsed, see %s" % parser.htmlFile

            # TODO - add option to parse files on disk for quick testing purposes
            skipGenerateIndex = False
            if not skipGenerateIndex:
                generateHtml()

def connectDropbox():
    sess = DropboxSession(APP_KEY, APP_SECRET, ACCESS_TYPE)

    if os.path.exists(TOKENS):
        token_file = open(TOKENS)
        token_key, token_secret = token_file.read().split('|')
        token_file.close()
        sess.set_token(token_key, token_secret)
    else:
        request_token = sess.obtain_request_token()

        url = sess.build_authorize_url(request_token)

        # Make the user sign in and authorize this token
        print "url:", url
        print "Please visit this website and press the 'Allow' button, then hit 'Enter' here."

        raw_input()

        # This will fail if the user didn't visit the above URL and hit 'Allow'
        access_token = sess.obtain_access_token(request_token)

        # Save the key to the file so we don't need to do this again
        token_file = open(TOKENS, 'w')

        token_key = access_token.key
        token_secret = access_token.secret
        token_file.write("%s|%s" % (token_key, token_secret))

        token_file.close()

    client = DropboxClient(sess)
    print "Linked account: %s" % client.account_info()
    return client

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('analyzed_folder', type=str, help='folder to put analysis in')
    args = parser.parse_args()
    global analyzedFolder, indexHtmlFile
    analyzedFolder = args.analyzed_folder
    if not os.path.isdir(analyzedFolder):
        os.makedirs(analyzedFolder)
    indexHtmlFile = os.path.join(analyzedFolder, "index.html")

    client = connectDropbox()
    cursor = None

    entries = []
    has_more = True
    while has_more:
        delta = client.delta(cursor)
        reset = delta['reset']
        if reset:
            entries = []
        entries += delta['entries']
        cursor = delta['cursor']
        has_more = delta['has_more']

    allowedTimestamps = set()
    for path, metadata in entries:
        timestamp, ext = os.path.splitext(os.path.basename(path))
        if ext == ".jpg" and metadata:
            allowedTimestamps.add(timestamp)

    # On startup, we first remove all vestigial directories
    for f in os.listdir(analyzedFolder):
        if not os.path.isdir(f):
            continue
        if f not in allowedTimestamps:
            rm(f)

    handleEntries(client, entries, forceReparse=False)

    while True:
        print "Checking delta from cursor %s" % cursor

        delta = client.delta(cursor)
        entries = delta['entries']
        reset = delta['reset']
        cursor = delta['cursor']
        has_more = delta['has_more']

        if reset:
            shutil.rmtree(analyzedFolder)
            os.path.mkdir(analyzedFolder)
        
        handleEntries(client, entries, forceReparse=True)

        if not has_more:
            time.sleep(DROPBOX_WAIT_PERIOD)

if __name__ == "__main__":
    main()

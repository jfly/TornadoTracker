#!/usr/bin/env python

import os
import sys
import argparse
import datetime
import pyinotify

import ParseTornado

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('image_folder', type=str, help='folder to watch for image files')
    parser.add_argument('analyzed_folder', type=str, help='folder to put analysis in')
    args = parser.parse_args()

    assert os.path.isdir(args.image_folder)
    if not os.path.isdir(args.analyzed_folder):
        os.makedirs(args.analyzed_folder)
    indexHtmlFile = os.path.join(args.analyzed_folder, "index.html")

    class EventHandler(pyinotify.ProcessEvent):
        def process_IN_CREATE(self, event):
            handleFile(event.pathname, forceReparse=True)

        def process_IN_DELETE(self, event):
            pass

        def process_IN_MODIFY(self, event):
            handleFile(event.pathname, forceReparse=True)

        def process_IN_MOVED_TO(self, event):
            handleFile(event.pathname, forceReparse=True)


    parserByTimestamp = {}
    def handleFile(fileName, forceReparse=False):
        rest, ext = os.path.splitext(fileName)
        if ext != ".jpg":
            return
        parser = ParseTornado.Parser(fileName, args.analyzed_folder)
        parserByTimestamp[parser.timestamp] = parser
        value = parser.value(forceReparse=forceReparse)
        if value is None:
            print "Failed to parse, see %s" % parser.htmlFile
        else:
            print "Successfully parsed, see %s" % parser.htmlFile

        generateHtml()

    def generateHtml():
        table = "<table class='gridtable'>\n"
        table += "<thead>\n"
        table += "<tr>\n"
        table += "<th>Date</th><th>Value</th>\n"
        table += "</tr>\n"
        table += "</thead>\n"
        for timestamp, parser in sorted(parserByTimestamp.iteritems()):
            val = parser.value()
            if val is None:
                table += "<tr class='fail'>\n"
            else:
                table += "<tr class='success'>\n"
            link = os.path.relpath(parser.htmlFile, args.analyzed_folder)
            prettyDate = datetime.datetime.fromtimestamp(timestamp).ctime()
            table += "<td><a href='%s'>%s</a></td><td>%s</td>\n" % ( link, prettyDate, parser.value() )
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
    background-color: red;
}
</style>
</head>
<body>
<p>Last updated %s</p>
%s
</body>
</html>
""" % ( datetime.datetime.now().ctime(), table )
        f = open(indexHtmlFile, 'w')
        f.write(html)
        f.close()
        print "Updated %s" % indexHtmlFile


    wm = pyinotify.WatchManager()
    handler = EventHandler()
    notifier = pyinotify.Notifier(wm, handler)
    mask = pyinotify.IN_DELETE | pyinotify.IN_CREATE | pyinotify.IN_MODIFY | pyinotify.IN_MOVED_TO
    wm.add_watch(args.image_folder, mask, quiet=False)

    # This is actually not racy. If a file is added while we're processing
    # all the files already present, we'll still be notified once we
    # get around to calling notifier.loop().
    for f in sorted(os.listdir(args.image_folder)):
        handleFile(os.path.join(args.image_folder, f))


    print "\nNow watching directory %s\n" % args.image_folder
    notifier.loop()


if __name__ == "__main__":
    main()

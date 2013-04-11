import Image, ImageDraw
import math
import os
import sys
import shutil
import traceback
import cgitb

def angleMean(angles):
    n = len(angles)
    return math.atan2(1.0/n * sum(math.sin(a) for a in angles), 1.0/n * sum(math.cos(a) for a in angles) )

def distance(u, v):
    return sum((u_i - v_i)**2 for u_i, v_i in zip(u, v))**.5

def scale(scalar, v):
    return tuple( scalar*v_i for v_i in v )

def add(u, v):
    return tuple( u_i + v_i for u_i, v_i in zip(u, v) )

def sub(u, v):
    return add(u, scale(-1, v))

def mag(u):
    return distance(u, (0,)*len(u))

def markPoint(image, point, color='black', size=100, strokeWidth=1):
    draw = ImageDraw.Draw(image)
    topLeft = add(point, (-0.5*size, -0.5*size))
    bottomRight = add(point, (0.5*size, 0.5*size))
    draw.ellipse(topLeft + bottomRight, fill=None, outline=color)
    draw.line(topLeft + bottomRight, fill=color, width=strokeWidth)
    draw.line(add((0, size), topLeft) + add((0, -size), bottomRight), fill=color, width=strokeWidth)

class Group(object):
    def __init__(self, center):
        self.center = center
        self.points = [ center ]

    def addPoint(self, point):
        # update center
        self.center = scale(1.0/(len(self.points) + 1), add(scale(len(self.points), self.center), point))
        self.points.append(point)

def findGroups(points, groupDiameter):
    groups = []
    for point in points:
        foundGroup = False
        for group in groups:
            if distance(point, group.center) <= groupDiameter:
                group.addPoint(point)
                foundGroup = True
                break

        if not foundGroup:
            groups.append(Group(point))

    return groups

def resize(image):
    originalToThumbnailRatio = image.size[0] / 300.0
    width = int(image.size[0] / originalToThumbnailRatio)
    height = int(image.size[1] / originalToThumbnailRatio)

    image = image.resize((width, height))
    return image, originalToThumbnailRatio

def findPixels(size, pixdata, color, colorDelta):
    width, height = size

    pixels = []
    for x in range(width):
        for y in range(height):
            pixel = pixdata[x, y]
            
            # Holy crap function calls are *slow*
            #distanceToColor = sum(abs(c) for c in sub(color, pixel))
            distanceToColor = abs(color[0]-pixel[0]) + abs(color[1]-pixel[1]) + abs(color[2]-pixel[2])

            if distanceToColor < colorDelta:
                pixels.append((x, y))
    return pixels

def normalize(parser, image):
    originalImage = image
    image, originalToThumbnailRatio = resize(image)

    parser.addStep("Resized image down to something manageable.", image)

    # The counter has a red square at the bottom left and bottom right,
    # and a green square at the top left and top right.
    # We try to detect pixels that might belong to those here.
    trueRed = ( 255, 0, 0 )
    trueGreen = ( 0, 255, 0 )
    # When flash is involved, green and red can look more like these two
    cameraRed = ( 196, 75, 129 )
    cameraGreen = ( 80, 161, 168 )

    pixdata = image.load() # http://stackoverflow.com/questions/12228829/python-image-library-make-area-of-image-transparent#comment16387831_12229109
    trueRedPixels = findPixels(image.size, pixdata, trueRed, 250)
    cameraRedPixels = findPixels(image.size, pixdata, cameraRed, 50)
    redPixels = set(trueRedPixels) | set(cameraRedPixels)

    trueGreenPixels = findPixels(image.size, pixdata, trueGreen, 270)
    cameraGreenPixels = findPixels(image.size, pixdata, cameraGreen, 50)
    greenPixels = set(trueGreenPixels) | set(cameraGreenPixels)

    groupDiameter = 0.1*max(*image.size)
    redGroups = findGroups(redPixels, groupDiameter)
    redGroups.sort(key=lambda g: len(g.points))
    greenGroups = findGroups(greenPixels, groupDiameter)
    greenGroups.sort(key=lambda g: len(g.points))

    markPixelsImage = image.copy()
    for i, redGroup in enumerate(redGroups):
        markPoint(markPixelsImage, redGroup.center, color='red', size=groupDiameter, strokeWidth=2*i+1)
    for i, greenGroup in enumerate(greenGroups):
        markPoint(markPixelsImage, greenGroup.center, color='green', size=groupDiameter, strokeWidth=2*i+1)
    parser.addStep("Found %s red groups & %s green groups (larger strokes indicate higher pixel density)." % ( len(redGroups), len(greenGroups) ), markPixelsImage)

    redGroups = redGroups[-2:]
    greenGroups = greenGroups[-2:]

    markPixelsImage = image.copy()
    for i, redGroup in enumerate(redGroups):
        markPoint(markPixelsImage, redGroup.center, color='red', size=groupDiameter, strokeWidth=2)
    for i, greenGroup in enumerate(greenGroups):
        markPoint(markPixelsImage, greenGroup.center, color='green', size=groupDiameter, strokeWidth=2)
    parser.addStep("Picked 2 heaviest groups of reds and 2 heaviest groups of greens.", markPixelsImage)

    b1, b2 = [ g.center for g in redGroups ]
    t1, t2 = [ g.center for g in greenGroups ]
    if distance(b1, t1) < distance(b1, t2):
        # b1 <-> t1 must be an edge, and by process of elimination,
        # b2 <-> t2 must be an edge as well
        pass
    else:
        # b1 <-> t2 must be an edge, and by process of elimination,
        # b2 <-> t1 must be an edge as well
        b1, b2 = b2, b1
        # now b1 <-> t1 and b2 <-> t2 are edges

    # We want t1 to be exactly on top of b1
    #  *--t1
    #  |  /|
    #  | / |
    #  b1--*
    deltaY = -(t1[1] - b1[1]) # the PIL coordinate system increases Y as we go south
    deltaX = t1[0] - b1[0]
    ccwAngleToRotate1 = 90 - math.degrees(math.atan2(deltaY, deltaX))


    deltaY = -(t2[1] - b2[1]) # the PIL coordinate system increases Y as we go south
    deltaX = t2[0] - b2[0]
    ccwAngleToRotate2 = 90 - math.degrees(math.atan2(deltaY, deltaX))

    ccwAngleToRotate = math.degrees(angleMean([math.radians(ccwAngleToRotate1), math.radians(ccwAngleToRotate2)]))
    # Since our red and green dots aren't exactly identical, we need to rotate a
    # bit more than what we've computed.
    magicOffset = 1.0

    markEdgesImage = image.copy()
    draw = ImageDraw.Draw(markEdgesImage)
    draw.line((b1[0], b1[1], t1[0], t1[1]), fill='orange', width=5)
    draw.line((b2[0], b2[1], t2[0], t2[1]), fill='red', width=5)
    parser.addStep("Identified a vertical edge (orange) that needs to be rotated %s degrees counter clockwise, and a vertical edge (red) that needs to be rotated %s degrees counter clockwise. Averaging angles is <a href='http://en.wikipedia.org/wiki/Circular_mean'>hard</a>, but I'm going to give it a shot because because I'm a hard worker. Going to rotate %s degrees ccw (+ magic offset of %s degree(s))." % (ccwAngleToRotate1, ccwAngleToRotate2, ccwAngleToRotate, magicOffset), markEdgesImage)

    b1, b2 = [ scale(originalToThumbnailRatio, g.center) for g in redGroups ]
    t1, t2 = [ scale(originalToThumbnailRatio, g.center) for g in greenGroups ]
    image = originalImage

    image, transform = applyAffineTransform(image, ccwAngleToRotate + magicOffset, [b1, b2, t1, t2])
    width, height = image.size
    bl = transform(*b1)
    br = transform(*b2)
    tl = transform(*t1)
    tr = transform(*t2)

    if bl[0] > br[0]:
        # Swap if necessary so that bl is at the bottom left
        bl, br = br, bl
        tl, tr = tr, tl

    markCornersImage = image.copy()
    markPoint(markCornersImage, bl, color='red', strokeWidth=5)
    markPoint(markCornersImage, br, color='orange', strokeWidth=5)
    markPoint(markCornersImage, tl, color='green', strokeWidth=5)
    markPoint(markCornersImage, tr, color='blue', strokeWidth=5)
    parser.addStep("Rotated and clipped image. Discovered bl (red) br (orange) tl (green) tr (blue) corners.", markCornersImage)

    # Sanity checking that we've picked out a rectangle, and that it's oriented.
    verticalEdge1 = sub(tl, bl)
    verticalEdge2 = sub(tr, br)
    bottomHorizontalEdge = sub(br, bl)
    topHorizontalEdge = sub(tr, tl)
    THRESHOLD = .05*max(width, height)
    assert abs(mag(verticalEdge1) - mag(verticalEdge2)) <= THRESHOLD
    assert abs(mag(bottomHorizontalEdge) - mag(topHorizontalEdge)) <= THRESHOLD
    assert abs(verticalEdge1[0]) <= THRESHOLD
    assert abs(verticalEdge2[0]) <= THRESHOLD
    assert abs(bottomHorizontalEdge[1]) <= THRESHOLD
    assert abs(topHorizontalEdge[1]) <= THRESHOLD

    image = extractBlackArea(parser, image, bl, br, tl, tr)
    parser.addStep("Cropped out black area.", image)

    return image

def extractBlackArea(parser, image, bl, br, tl, tr):
    width, height = image.size
    bl = list(bl)
    br = list(br)
    tl = list(tl)
    tr = list(tr)
    pixdata = image.load()

    left = max(tl[0], bl[0])
    right = min(tr[0], br[0])
    top = max(tl[1], tr[1])
    bottom = min(bl[1], br[1])
    def moveUntilMostlyBlack(i, direction, isRow):
        if isRow:
            def average(y):
                return sum(sum(pixdata[x, y]) for x in range(width))/width
            lower = 0
            upper = height - 1
        else:
            def average(x):
                return sum(sum(pixdata[x, y]) for y in range(height))/height
            lower = 0
            upper = width - 1

        i = max(lower, i)
        i = min(upper, i)
        firstAve = average(i)
        while lower <= i <= upper:
            ave = average(i)
            if ave < .75*firstAve:
                return i
            i += direction

        return i

    top = moveUntilMostlyBlack(top, 1, isRow=True)
    bottom = moveUntilMostlyBlack(bottom, -1, isRow=True)
    left = moveUntilMostlyBlack(left, 1, isRow=False)
    right = moveUntilMostlyBlack(right, -1, isRow=False)

    left = int(left)
    right = int(right)
    top = int(top)
    bottom = int(bottom)

    markedImage = image.copy()
    draw = ImageDraw.Draw(markedImage)
    color = 'red'
    draw.line((0, top, width-1, top), fill=color, width=5)
    draw.line((0, bottom, width-1, bottom), fill=color, width=5)
    draw.line((left, 0, left, height-1), fill=color, width=5)
    draw.line((right, 0, right, height-1), fill=color, width=5)
    parser.addStep("Found black area boundaries.", markedImage)

    image = image.transform((right-left, bottom-top), Image.EXTENT, (left, top, right, bottom))
    return image

# copy-pasted from PIL source code, with some changes
def applyAffineTransform(image, angle, boundaryPoints):
    angle = -angle * math.pi / 180
    matrix = [
         math.cos(angle), math.sin(angle), 0.0,
         -math.sin(angle), math.cos(angle), 0.0
    ]
    def transform(x, y, (a, b, c, d, e, f)=matrix):
        return a*x + b*y + c, d*x + e*y + f

    # calculate output size
    xx = []
    yy = []
    for x, y in boundaryPoints:
        x, y = transform(x, y)
        xx.append(x)
        yy.append(y)
    w = int(math.ceil(max(xx)) - math.floor(min(xx)))
    h = int(math.ceil(max(yy)) - math.floor(min(yy)))
    center = scale(1.0/len(boundaryPoints), reduce(lambda u, v: add(u, v), boundaryPoints))

    # adjust center
    x, y = transform(w / 2.0, h / 2.0)
    matrix[2] = center[0] - x
    matrix[5] = center[1] - y

    # http://negativeprobability.blogspot.com/2011/11/affine-transformations-and-their.html
    inv_matrix = [
        math.cos(angle), -math.sin(angle), -matrix[2]*math.cos(angle)+matrix[5]*math.sin(angle),
        math.sin(angle), math.cos(angle), -matrix[2]*math.sin(angle)-matrix[5]*math.cos(angle)
    ]
    def transform2(x, y, (a, b, c, d, e, f)=inv_matrix):
        return a*x + b*y + c, d*x + e*y + f

    return ( image.transform((w, h), Image.AFFINE, matrix), transform2 )

class Parser(object):
    def __init__(self, imageFileName, analyzedDirectory):
        self.imageFileName = os.path.abspath(imageFileName)

        self.timestamp, ext = os.path.splitext(os.path.basename(imageFileName))
        self.timestamp = int(self.timestamp)
        self.dataDir = os.path.join(analyzedDirectory, str(self.timestamp))

        self.htmlFile = os.path.join(self.dataDir, 'index.html')
        self.parsedValueTextFile = os.path.join(self.dataDir, "parsed.txt")

        if os.path.exists(self.dataDir):
            if os.path.isfile(self.parsedValueTextFile):
                firstLine = open(self.parsedValueTextFile).readline()
                try:
                    self.value_ = int(firstLine)
                except ValueError:
                    print "%s isn't an integer!" % firstLine
                    self.value_ = None
            else:
                self.value_ = None

        self.steps = []

    def addStep(self, description, postStepImage):
        stepNumber = len(self.steps) + 1
        self.steps.append((description, postStepImage))

    def generateHtml(self, einfo=None):
        index = open(self.htmlFile, 'w')
        index.write("""<html>
<body>
""")
        for i, (description, image) in enumerate(self.steps):
            stepNumber = i + 1

            relativeImageFileName = "step%s.jpg" % stepNumber
            absoluteImageFileName = os.path.join(self.dataDir, relativeImageFileName)
            index.write("<h2>%s. %s</h2>\n" % ( stepNumber, description ))
            index.write("<img src='%s'/>\n" % ( relativeImageFileName ))
            image.save(absoluteImageFileName)

        if einfo:
            index.write(cgitb.html(einfo))

        index.write("""
</body>
</html>
""")
        index.close()

    def value(self, forceReparse=False):
        if not forceReparse and hasattr(self, 'value_'):
            return self.value_

        einfo = None
        try:
            if os.path.isdir(self.dataDir):
                shutil.rmtree(self.dataDir)
            os.makedirs(self.dataDir)
            image = Image.open(self.imageFileName)
            image = normalize(self, image)
        except:
            self.value_ = None
            einfo = sys.exc_info()
        else:
            self.value_ = 4242 #<<<
            f = open(self.parsedValueTextFile, "w")
            f.write("%s\n" % self.value_)
            f.close()

        self.generateHtml(einfo)
        return self.value_


def main():
    analyzedDirectory = '/home/jeremy/tmp/'
    # straight up
    fileName = "/home/jeremy/Dropbox/Apps/Tornado Tracker/1365395374.jpg"
    # yee rotated
    #fileName = "/home/jeremy/Dropbox/Apps/Tornado Tracker/1365394659.jpg"
    # rotated other way (almost works, but flash screws up extractBlackArea())
    #fileName = "/home/jeremy/Dropbox/Apps/Tornado Tracker/1365394667.jpg"

    parser = Parser(fileName, analyzedDirectory)
    print parser.value()
    print parser.htmlFile

if __name__ == "__main__":
    main()

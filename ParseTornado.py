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

def findPixels(image, color, colorDelta):
    pixdata = image.load() # http://stackoverflow.com/questions/12228829/python-image-library-make-area-of-image-transparent#comment16387831_12229109
    width, height = image.size

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

# I am so damn good at OOP design and naming functions yeah you should hire me.
def parse(parser, image):
    originalImage = image
    image, originalToThumbnailRatio = resize(image)

    parser.addStep("Resized image down to something manageable.", [image])

    # The counter has a red square at the bottom left and bottom right,
    # and a green square at the top left and top right.
    # We try to detect pixels that might belong to those here.
    trueRed = ( 255, 0, 0 )
    trueGreen = ( 0, 255, 0 )
    # When flash is involved, green and red can look more like these two
    cameraRed = ( 196, 75, 129 )
    cameraGreen = ( 80, 161, 168 )
    # Another green
    anotherGreen = ( 28, 133, 119 )

    trueRedPixels = findPixels(image, trueRed, 250)
    cameraRedPixels = findPixels(image, cameraRed, 50)
    redPixels = set(trueRedPixels) | set(cameraRedPixels)

    trueGreenPixels = findPixels(image, trueGreen, 270)
    cameraGreenPixels = findPixels(image, cameraGreen, 50)
    anotherGreenPixels = findPixels(image, anotherGreen, 50)
    greenPixels = set(trueGreenPixels) | set(cameraGreenPixels) | set(anotherGreenPixels)

    groupDiameter = 0.08*max(*image.size)
    redGroups = findGroups(redPixels, groupDiameter)
    redGroups.sort(key=lambda g: len(g.points))
    greenGroups = findGroups(greenPixels, groupDiameter)
    greenGroups.sort(key=lambda g: len(g.points))

    markPixelsImage = image.copy()
    for i, redGroup in enumerate(redGroups):
        markPoint(markPixelsImage, redGroup.center, color='red', size=groupDiameter, strokeWidth=2*i+1)
    for i, greenGroup in enumerate(greenGroups):
        markPoint(markPixelsImage, greenGroup.center, color='green', size=groupDiameter, strokeWidth=2*i+1)
    parser.addStep("Found %s red groups & %s green groups (larger strokes indicate higher pixel density)." % ( len(redGroups), len(greenGroups) ), [markPixelsImage])

    redGroups = redGroups[-2:]
    greenGroups = greenGroups[-2:]


    markPixelsImage = image.copy()

    for i, redGroup in enumerate(redGroups):
        markPoint(markPixelsImage, redGroup.center, color='red', size=groupDiameter, strokeWidth=2)
    for i, greenGroup in enumerate(greenGroups):
        markPoint(markPixelsImage, greenGroup.center, color='green', size=groupDiameter, strokeWidth=2)
    parser.addStep("Picked 2 heaviest groups of reds and 2 heaviest groups of greens.", [markPixelsImage])

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
    parser.addStep("Identified a vertical edge (orange) that needs to be rotated %s degrees counter clockwise, and a vertical edge (red) that needs to be rotated %s degrees counter clockwise. Averaging angles is <a href='http://en.wikipedia.org/wiki/Circular_mean'>hard</a>, but I'm going to give it a shot because because I'm a hard worker. Going to rotate %s degrees ccw (+ magic offset of %s degree(s))." % (ccwAngleToRotate1, ccwAngleToRotate2, ccwAngleToRotate, magicOffset), [markEdgesImage])

    b1 = scale(originalToThumbnailRatio, b1)
    b2 = scale(originalToThumbnailRatio, b2)
    t1 = scale(originalToThumbnailRatio, t1)
    t2 = scale(originalToThumbnailRatio, t2)
    image = originalImage

    image, transform = applyAffineTransform(image, ccwAngleToRotate + magicOffset, [b1, b2, t1, t2])
    width, height = image.size
    bl = transform(*b1)
    br = transform(*b2)
    tl = transform(*t1)
    tr = transform(*t2)

    if bl[0] > br[0]:
        assert tl[0] > tr[0]
        # Swap if necessary so that bl is at the bottom left
        bl, br = br, bl
        tl, tr = tr, tl

    markCornersImage = image.copy()
    markPoint(markCornersImage, bl, color='red', strokeWidth=5)
    markPoint(markCornersImage, br, color='orange', strokeWidth=5)
    markPoint(markCornersImage, tl, color='green', strokeWidth=5)
    markPoint(markCornersImage, tr, color='blue', strokeWidth=5)
    parser.addStep("Rotated and clipped image. Discovered bl (red) br (orange) tl (green) tr (blue) corners.", [markCornersImage])

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
    parser.addStep("Cropped out black area.", [image])

    # image is now just the black area with 5 digits.
    # We extract those 5 digits now. This is going to be very hardcoded and
    # awful.
    width, height = image.size
    left = int(0.07*width)
    right = int(width - 0.12*width)
    top = int(0.4*height)
    bottom = int(height - 0.2*height)
    image = image.transform((right-left, bottom-top), Image.EXTENT, (left, top, right, bottom))
    parser.addStep("Cropped out excess black.", [image])

    width, height = image.size
    assert 4.4 <= 1.0*width/height <= 4.8
    digitWidth = 0.14*width
    digitSpacing = (width - 5*digitWidth)/4.0
    left = 0
    digitImages = []
    for nthDigit in range(5):
        digitImage = image.copy()
        right = left + digitWidth
        digitImage = digitImage.transform((int(digitWidth), height), Image.EXTENT, (int(left), 0, int(right), height))
        blackWhiten(digitImage)
        digitImages.append(digitImage)
        left = right + digitSpacing

    parser.addStep("Extracted digits.", digitImages)

    digitImages = [ di.copy() for di in digitImages ]
    parsedDigits = []
    for digitImage in digitImages:
        parsedDigits.append(identifyDigit(digitImage))
    numberStr = " ".join(str(d) for d in parsedDigits)
    parser.addStep("Parsed digits: %s." % numberStr, digitImages)

    numberStr = " ".join(str(d) for d in parsedDigits)

    return parsedDigits

class Digit(object):
    def __init__(self, value, (width, height), onMarks, offMarks):
        self.value = value
        self.width = width
        self.height = height
        self.onMarks = onMarks
        self.offMarks = offMarks

    def matches(self, image):
        pixdata = image.load()
        width, height = image.size
        
        def on(pixel):
            allBlack = sum(pixel) == 0
            allWhite = sum(pixel) == 3*255
            assert allBlack ^ allWhite
            return allWhite

        def perfectMatch(offsetX, offsetY, mark=False):
            for shouldOn, marks in [ (True, self.onMarks), (False, self.offMarks) ]:
                for x, y in marks:
                    x = int(1.0*x/self.width * width) + offsetX
                    y = int(1.0*y/self.height * height) + offsetY
                    if not ( 0 <= x < width) or not ( 0 <= y < height ):
                        return False
                    
                    if mark:
                        color = (255, 0, 0) if shouldOn else (0, 255, 0)
                        pixdata[x, y] = color
                    else:
                        if shouldOn != on(pixdata[x, y]):
                            return False
            return True

        wiggleX = int(math.ceil(0.06*width))
        wiggleY = int(math.ceil(0.2*height))
        for offsetX in range(-wiggleX, wiggleX):
            for offsetY in range(-wiggleY, wiggleY):
                if perfectMatch(offsetX, offsetY):
                    perfectMatch(offsetX, offsetY, mark=True)
                    return True
        return False

canonicalZero = Digit(
    0,
    (74, 113),
    onMarks=(
        (37, 27), (37, 85),
        (23, 34), (23, 44), (23, 54), (23, 64), (23, 75),
        (51, 34), (51, 44), (51, 54), (51, 64), (51, 75),
        (23, 51), (55, 51),
    ),
    offMarks=(
        (39, 56),
        (37, 56),
        (35, 56),
        (33, 56),
    )
)

canonicalOne = Digit(
    1,
    (74, 113),
    onMarks=(
        (40, 25),
        (40, 35),
        (40, 45),
        (40, 55),
        (40, 65),
        (40, 75),
    ),
    offMarks=(
        (25, 25), # now we won't think a 7 is a 1
    )
)

canonicalTwo = Digit(
    2,
    (72, 111),
    onMarks=(
        (23, 90), (33, 90), (44, 90), (52, 90),
        (29, 81), (35, 75), (41, 71), (47, 64), (52, 58), (53, 49),
        (50, 43), (47, 39), (39, 36), (32, 38),
    ),
    offMarks=(
        (23, 51),
    )
)

canonicalThree = Digit(
    3,
    (74, 113),
    onMarks=(
        (37, 27), (34, 81), (37, 85),
        (45, 30),
        (23, 34), (23, 75),
        (51, 34), (51, 75),
        (55, 51),
    ),
    offMarks=(
        (23, 45),
        (23, 50),
        (23, 55),
    )
)

# TODO - this seems silly
otherCanonicalThree = Digit(
    3,
    (72, 112),
    onMarks=(
        (28, 40), (34, 36), (43, 37),
        (51, 42), (51, 43), (51, 44), (51, 45), (51, 46), (51, 47), (51, 48), (51, 49), (51, 50), (51, 51), (51, 52), (51, 53), (51, 54),
        (50, 62), (52, 70), (53, 81), 
        (48, 85), (39, 88), (30, 87), (24, 82),
    ),
    offMarks=(
        (23, 51),
    )
)

canonicalFour = Digit(
    4,
    (74, 113),
    onMarks=(
        (49, 28), (49, 38), (49, 48), (49, 58), (49, 68), (49, 78), (49, 83),
        (58, 70), (48, 70), (38, 70), (28, 70), (24, 70),
        (29, 59), (33, 53), (38, 45), (43, 37), (45, 32),
    ),
    offMarks=(
        (23, 51),
    )
)

canonicalFive = Digit(
    5,
    (74, 113),
    onMarks=(
        (23, 34), (43, 34),
        (23, 43),
        (23, 57), (43, 57),
                  (52, 71),
        (23, 83), (43, 89),
    ),
    offMarks=(
        (50, 45),
    )
)

canonicalSix = Digit(
    6,
    (74, 113),
    onMarks=(
        (37, 27), (37, 85),
        (23, 34), (23, 55), (23, 60), (23, 65), (23, 70), (23, 75),
        (51, 75),
        (37, 56),
        (19, 60),
    ),
    offMarks=(
        (51, 40),
    )
)

canonicalSeven = Digit(
    7,
    (72, 111),
    onMarks=(
        (30, 22), (30, 24), (47, 24),
        (48, 37),
        (44, 50),
        (42, 58),
        (41, 66),
        (38, 77),
    ),
    offMarks=()
)

canonicalEight = Digit(
    8,
    (74, 113),
    onMarks=(
        (35, 29),
        (37, 27), (37, 85),
        (22, 34), (22, 44), (25, 54), (25, 64), (20, 75),
        (56, 34), (63, 75),
        (37, 50), (39, 50), (42, 50),
        (37, 55), (39, 55), (42, 55),
        (37, 60), (39, 60), (42, 60),
        (50, 45),
        (25, 51),
        (56, 40), (58, 44), (56, 48), (56, 54),
    ),
    offMarks=()
)

canonicalNine = Digit(
    9,
    (72, 111),
    onMarks=(
        (40, 33),
        (50, 38), (55, 43),
        (26, 47), (55, 47),
        (52, 60), (35, 60),
        (54, 78), 
        (42, 86),
        (42, 88),
        (35, 95), (42, 95), (50, 95), (55, 92), (60, 90),
        (57, 85), (57, 80), (57, 79), (57, 78), (57, 77), (57, 75), (57, 75), (57, 70), (57, 65),
    ),
    offMarks=(
        (20, 69),
    )
)

canonicalDigits = (
    # These are rougly sorted in decreasing "difficulty" to match, because
    # we take the first match we find.
    canonicalEight,
    canonicalZero,

    canonicalTwo,
    canonicalThree,
    otherCanonicalThree,
    canonicalSix,

    canonicalNine,
    canonicalFive,
    canonicalFour,
    canonicalSeven,

    canonicalOne,
)
def identifyDigit(digitImage):
    value = None
    for canonicalDigit in canonicalDigits:
        if canonicalDigit.matches(digitImage):
            value = canonicalDigit.value
            break
    return value

def blackWhiten(image):
    pixdata = image.load()
    width, height = image.size

    MAGIC_WHITENESS_THRESHOLD = 145
    pixels = []
    for x in range(width):
        for y in range(height):
            r, g, b = pixdata[x, y]
            if r + g + b < 3*MAGIC_WHITENESS_THRESHOLD:
                pixdata[x, y] = (0, 0, 0)
            else:
                pixdata[x, y] = (255, 255, 255)

def extractBlackArea(parser, image, bl, br, tl, tr):
    width, height = image.size
    l = list(bl)
    br = list(br)
    tl = list(tl)
    tr = list(tr)
    pixdata = image.load()

    left = int(max(tl[0], bl[0]))
    right = int(min(tr[0], br[0]))
    top = int(max(tl[1], tr[1]))
    bottom = int(min(bl[1], br[1]))
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
                break
            i += direction

        return i

    top = moveUntilMostlyBlack(top, 1, isRow=True)
    bottom = moveUntilMostlyBlack(bottom, -1, isRow=True)
    left = moveUntilMostlyBlack(left, 1, isRow=False)
    right = moveUntilMostlyBlack(right, -1, isRow=False)
    assert 0 <= top <= bottom
    assert 0 <= left <= right

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
    parser.addStep("Found black area boundaries.", [markedImage])

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

def parsePrecomputedTextFile(fileName, strict=False):
    lines = open(fileName).read().split("\n")
    try:
        return [ None if line == repr(None) else int(line) for line in lines if line ]
    except ValueError:
        print "%s isn't an integer!" % line
        if strict:
            raise
        return [ None ]

class Parser(object):
    def __init__(self, imageFileName, analyzedDirectory):
        self.imageFileName = os.path.abspath(imageFileName)

        self.timestamp, ext = os.path.splitext(os.path.basename(imageFileName))
        self.timestamp = int(self.timestamp)
        self.trainingFile = os.path.join(os.path.dirname(imageFileName), str(self.timestamp) + ".training")
        self.dataDir = os.path.join(analyzedDirectory, str(self.timestamp))

        self.htmlFile = os.path.join(self.dataDir, 'index.html')
        self.parsedValueTextFile = os.path.join(self.dataDir, "parsed.txt")

        if os.path.exists(self.dataDir):
            if os.path.isfile(self.parsedValueTextFile):
                self.digits_ = parsePrecomputedTextFile(self.parsedValueTextFile)
            else:
                self.digits_ = [ None ]

        if os.path.isfile(self.trainingFile):
            self.correctDigits_ = parsePrecomputedTextFile(self.trainingFile, strict=True)

        self.steps = []

    def addStep(self, description, postStepImages):
        stepNumber = len(self.steps) + 1
        self.steps.append((description, postStepImages))

    def stepImage(self, stepNumber, nthImage=0):
        imageFileName = "step%s-%s.png" % ( stepNumber, nthImage )
        absoluteImageFileName = os.path.join(self.dataDir, imageFileName)
        return absoluteImageFileName

    def generateHtml(self, einfo=None):
        index = open(self.htmlFile, 'w')
        index.write("""<html>
<body>
""")
        for i, (description, images) in enumerate(self.steps):
            stepNumber = i + 1

            index.write("<h2>%s. %s</h2>\n" % ( stepNumber, description ))
            for nthImage, image in enumerate(images):
                absoluteImageFileName = self.stepImage(stepNumber, nthImage)
                relativeImageFileName = os.path.basename(absoluteImageFileName)
                index.write("<img src='%s'/>\n" % ( relativeImageFileName ))
                image.save(absoluteImageFileName)

        if einfo:
            index.write(cgitb.html(einfo))

        index.write("""
</body>
</html>
""")
        index.close()

    def digits(self, forceReparse=False):
        if not forceReparse and hasattr(self, 'digits_'):
            return self.digits_

        einfo = None
        try:
            if os.path.isdir(self.dataDir):
                shutil.rmtree(self.dataDir)
            os.makedirs(self.dataDir)
            image = Image.open(self.imageFileName)
            self.digits_ = parse(self, image)
        except:
            self.digits_ = [ None ]
            einfo = sys.exc_info()
        else:
            f = open(self.parsedValueTextFile, "w")
            f.write("%s\n" % "\n".join(str(d) for d in self.digits_))
            f.close()

        self.generateHtml(einfo)

        return self.digits_

    def failedTest(self):
        assert hasattr(self, 'digits_')
        if hasattr(self, 'correctDigits_'):
            if self.correctDigits_ != self.digits_:
                return True
        return False


def main():
    analyzedDirectory = '/home/jeremy/tmp/'
    fileName = "/home/jeremy/Dropbox/Apps/Tornado Tracker/1366000773.jpg"

    parser = Parser(fileName, analyzedDirectory)
    print parser.digits(forceReparse=True)
    print parser.htmlFile

if __name__ == "__main__":
    main()

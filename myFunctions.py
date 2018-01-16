from __future__ import division
from __future__ import print_function
#from keras.callbacks import ModelCheckpoint
#from keras.models import Model, load_model
#from keras.layers import Input, Conv2D, MaxPooling2D, UpSampling2D, concatenate
#from keras.optimizers import Adam
#from keras import losses
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter
import scipy
from scipy import misc
import math
import os
import copy

def calcPerimeter(image):
    image = shell(image)
    whitePoints = np.array(np.where(np.isin(image, 255)))
    perimeter = 0
    continueSumming = True
    currentPoint = np.zeros([2, 1], dtype='int')
    currentPoint[0] = np.where(np.isin(image, 255))[0][0]
    currentPoint[1] = np.where(np.isin(image, 255))[1][0]
    while continueSumming:
        whitePoints = whitePoints - currentPoint
        distances = np.sqrt(np.square(whitePoints[0, :]) + np.square(whitePoints[1, :]))
        closestIndex = np.argmin(distances)
        perimeter = perimeter + min(distances)
        currentPoint[0] = whitePoints[0][closestIndex]
        currentPoint[1] = whitePoints[1][closestIndex]
        whitePoints = np.delete(whitePoints, closestIndex, 1)
        if len(whitePoints[0]) == 0:
            continueSumming = False
    return perimeter

def shell(image):
    image2 = getImagePerimeterPoints(image)
    xPoints = np.where(np.isin(image, 255))[0]
    yPoints = np.where(np.isin(image, 255))[1]
    for i, j in zip(xPoints, yPoints):
        conditionList = [image2[i, j-1] != 0, image2[i+1, j] != 0, image2[i, j+1] != 0, image2[i-1, j] != 0]
        if sum(conditionList) > 1:
            image2[i, j] = 0
    return image2

def calcSegmentLength(line):
    length = 0
    for j in range(line.shape[1]-1):
        length = length + np.sqrt(np.square(line[0, j+1] - line[0, j]) +
                        np.square(line[1, j+1] - line[1, j]) +
                        np.square(line[2, j+1] - line[2, j]))
    return length

def calc3DTortuosity(centreLine, windowLength):
    centreLineTortuosity = np.ndarray([centreLine.shape[1]])
    halfWindow = int(math.floor(windowLength/2))
    paddedCentreLine = np.pad(centreLine, halfWindow, 'edge')[halfWindow:-halfWindow, :]
    for i in range(centreLine.shape[1]):
        evalPoint = i + halfWindow
        absoluteDistance = np.sqrt(np.square(paddedCentreLine[0, evalPoint+halfWindow] - paddedCentreLine[0, evalPoint-halfWindow]) +
            np.square(paddedCentreLine[1, evalPoint + halfWindow] - paddedCentreLine[1, evalPoint - halfWindow]) +
            np.square(paddedCentreLine[2, evalPoint + halfWindow] - paddedCentreLine[2, evalPoint - halfWindow]))
        curveDistance = 0
        for j in range(windowLength-1):
            curveDistance = curveDistance + np.sqrt(np.square(paddedCentreLine[0, i+j+1] - paddedCentreLine[0, i+j]) +
                                                    np.square(paddedCentreLine[1, i+j+1] - paddedCentreLine[1, i+j]) +
                                                    np.square(paddedCentreLine[2, i+j+1] - paddedCentreLine[2, i+j]))
        tortuosity = curveDistance / absoluteDistance
        centreLineTortuosity[i] = tortuosity
    return centreLineTortuosity

def findAAABounds(wallVolume, OuterDiameter):
    maxDia = len(OuterDiameter[0:-100]) + np.argmax(OuterDiameter[-100:])
    maxVol = len(wallVolume[0:-100]) + np.argmax(wallVolume[-100:])
    acceptableSteps = np.linspace(1, 50, 50, dtype='int').tolist()
    timeSerieses = [wallVolume, OuterDiameter, wallVolume, OuterDiameter]
    directions = [-1, -1, 1, 1]
    points = []
    maxLocations = [maxVol, maxDia, maxVol, maxDia]
    for timeSeries, direction, start in zip(timeSerieses, directions, maxLocations):
        looking = True
        copyStart = copy.deepcopy(start)
        while looking:
            if any(((np.append(timeSeries, np.zeros(60, dtype = 'int'))[copyStart + direction*step] - np.append(timeSeries, np.zeros(60, dtype = 'int'))[copyStart])/step < -np.max(timeSeries)/200 and np.append(timeSeries, np.zeros(60, dtype = 'int'))[copyStart + direction*step] != 0) for step in acceptableSteps):
                copyStart = copyStart + direction
            else:
                looking = False
        points.append(copyStart)
    if abs(points[3] - points[2]) > 10:
        print('Warning: Your algorithm is unsure about where the aneurysm ends, wall thickness suggests ' + str(points[2]) + ' and diameter suggests ' + str(points[3]))
    if abs(points[1] - points[0]) > 10:
        print('Warning: Your algorithm is unsure about where the aneurysm starts, wall thickness suggests ' + str(points[0]) + ' and diameter suggests ' + str(points[1]))
    return [int((points[0] + points[1])/2), int((points[2] + points[3])/2)]

def isDoubleAAA(image):
    OuterTop = np.array(np.where(np.isin(image, 255)))[:, 0]
    OuterBottom = np.array(np.where(np.isin(image, 255)))[:, -1]
    continueLoop = True
    while continueLoop:
        x = (OuterTop - OuterBottom)/np.max(abs((OuterBottom - OuterTop)))
        if image[OuterBottom[0] + int(x[0]), OuterBottom[1] + int(x[1])] == 255 or image[OuterBottom[0] + 2*int(x[0]), OuterBottom[1] + 2*int(x[1])] == 255 or image[OuterBottom[0] + 5*int(x[0]), OuterBottom[1] + 5*int(x[1])] == 255:
            OuterBottom[0] = OuterBottom[0] + int(x[0])
            OuterBottom[1] = OuterBottom[1] + int(x[1])
        else:
            return True
        if np.square(OuterTop[0] - OuterBottom[0]) + np.square(OuterTop[1] - OuterBottom[1]) < 200:
            return False


def Construct3DBinaryArray(innerImageDirectory, outerImageDirectory, arrayDirectory, patientID, nonAugmentedVersion, binNum, returnArray, saveArray):

    imageType = 'InnerBinary'

    fileList = sorted(os.listdir(innerImageDirectory))
    imgTotal = len(fileList)
    totalCounter = 0
    maxSliceNum = len(fileList) if len(fileList) < findLargestNumberInFolder(fileList) else findLargestNumberInFolder(fileList)

    npImageArray = np.ndarray((binNum * maxSliceNum, 5, 256, 256, 2), dtype='float32')

    print('Loop starting')
    for filename in fileList:
        split1 = filename.split(imageType)
        if nonAugmentedVersion == True:
            split2 = split1[0].split('NonAugment')
            augNum = 777777777777777
        elif nonAugmentedVersion == False:
            split2 = split1[0].split('Augment')
            augNum = int(split2[1])
        split3 = split1[1].split('Patient')
        sliceNum = int(split3[0])
        if nonAugmentedVersion == False:
            arrayIndex = int(sliceNum - 1 + (augNum - 1 - ((math.floor((augNum - 1) / binNum)) * binNum)) * maxSliceNum)
            outerImageFileName = 'Augment' + split2[1] + 'OuterBinary' + split3[0] + 'Patient' + patientID + '.png'
        elif nonAugmentedVersion == True:
            arrayIndex = totalCounter
            outerImageFileName = 'NonAugment' + 'OuterBinary' + split3[0] + 'Patient' + patientID + '.png'

        outerImage = misc.imread(outerImageDirectory + outerImageFileName, flatten=True)
        innerImage = misc.imread(innerImageDirectory + filename, flatten=True)

        for i in range(2):

            if i == 0:
                image = innerImage
            elif i == 1:
                image = outerImage

            if sliceNum > 4 and sliceNum < maxSliceNum - 3:
                # assign to this index
                npImageArray[arrayIndex, 2, :, :, i] = image

                # assign to previous indexes
                npImageArray[arrayIndex - 2, 3, :, :, i] = image
                npImageArray[arrayIndex - 4, 4, :, :, i] = image

                # assign to future indexes
                npImageArray[arrayIndex + 2, 1, :, :, i] = image
                npImageArray[arrayIndex + 4, 0, :, :, i] = image

            elif sliceNum > 2 and sliceNum < 5:  # gets slices 3 and 4
                # assign to this index
                npImageArray[arrayIndex, 2, :, :, i] = image
                npImageArray[arrayIndex, 1, :, :, i] = image
                npImageArray[arrayIndex, 0, :, :, i] = image  # this is done for contingency

                # assign to previous indexes
                npImageArray[arrayIndex - 2, 3, :, :, i] = image

                # assign to future indexes
                npImageArray[arrayIndex + 2, 1, :, :, i] = image
                npImageArray[arrayIndex + 4, 0, :, :, i] = image

            elif sliceNum < 2:  # gets slices 1 and 2
                # assign to this index
                npImageArray[arrayIndex, 2, :, :, i] = image
                npImageArray[arrayIndex, 1, :, :, i] = image
                npImageArray[arrayIndex, 0, :, :, i] = image  # this is necessary

                # assign to future indexes
                npImageArray[arrayIndex + 2, 1, :, :, i] = image
                npImageArray[arrayIndex + 4, 0, :, :, i] = image
            elif sliceNum > maxSliceNum - 5 and sliceNum < maxSliceNum - 1:  # gets slices which are 3rd and 4th from the end
                # assign to this index
                npImageArray[arrayIndex, 2, :, :, i] = image
                npImageArray[arrayIndex, 3, :, :, i] = image
                npImageArray[arrayIndex, 4, :, :, i] = image  # this is done for contingency

                # assign to previous indexes
                npImageArray[arrayIndex - 2, 3, :, :, i] = image
                npImageArray[arrayIndex - 4, 4, :, :, i] = image

                # assign to future indexes
                npImageArray[arrayIndex + 2, 1, :, :, i] = image

            elif sliceNum > maxSliceNum - 3:  # gets the end and the one before it
                # assigns to this index
                npImageArray[arrayIndex, 2, :, :, i] = image
                npImageArray[arrayIndex, 3, :, :, i] = image
                npImageArray[arrayIndex, 4, :, :, i] = image  # this is needed

                # assigns to prevous indexes
                npImageArray[arrayIndex - 2, 3, :, :, i] = image
                npImageArray[arrayIndex - 4, 4, :, :, i] = image

        totalCounter = totalCounter + 1

        if ((augNum % binNum == 0) or (nonAugmentedVersion == True)) and (sliceNum == maxSliceNum):
            if saveArray ==  True:
                if (nonAugmentedVersion == True):
                    np.save(arrayDirectory + '3DNonAugment' + 'Patient' + patientID + '_' + 'Binary' + '.npy', npImageArray)
                else:
                    np.save(arrayDirectory + '3DAugment' + "%03d" % (augNum - binNum + 1) + '-' + "%03d" % (
                    augNum) + 'Patient' + patientID + '_' + 'Binary' + '.npy', npImageArray)
                    print('Saved one at augNum ' + str(augNum))
            if returnArray == True:
                return npImageArray

def Construct3DDicomArray(imageDirectory, arrayDirectory, patientID, nonAugmentedVersion, binNum, returnArray, saveArray):

    imageType = 'Original'

    fileList = sorted(os.listdir(imageDirectory))
    imgTotal = len(fileList)
    totalCounter = 0
    maxSliceNum = len(fileList) if len(fileList) < findLargestNumberInFolder(fileList) else findLargestNumberInFolder(fileList)

    npImageArray = np.ndarray((binNum*maxSliceNum, 5, 256, 256, 1), dtype='float32')

    print('Loop starting')
    for filename in fileList:
        split1 = filename.split(imageType)
        if nonAugmentedVersion == True:
            split2 = split1[0].split('NonAugment')
            augNum = 777777777777777
        elif nonAugmentedVersion == False:
            split2 = split1[0].split('Augment')
            augNum = int(split2[1])
        split3 = split1[1].split('Patient')
        sliceNum = int(split3[0])
        if nonAugmentedVersion == False:
            arrayIndex = int(sliceNum - 1 + (augNum-1-((math.floor((augNum-1)/binNum))*binNum))*maxSliceNum)
        elif nonAugmentedVersion == True:
            arrayIndex = totalCounter

        image = misc.imread(imageDirectory + filename, flatten=True)

        if sliceNum > 4 and sliceNum < maxSliceNum - 3:
            #assign to this index
            npImageArray[arrayIndex, 2, :, :, 0] = image

            #assign to previous indexes
            npImageArray[arrayIndex-2, 3, :, :, 0] = image
            npImageArray[arrayIndex-4, 4, :, :, 0] = image

            #assign to future indexes
            npImageArray[arrayIndex+2, 1, :, :, 0] = image
            npImageArray[arrayIndex+4, 0, :, :, 0] = image

        elif sliceNum > 2 and sliceNum < 5: #gets slices 3 and 4
            #assign to this index
            npImageArray[arrayIndex, 2, :, :, 0] = image
            npImageArray[arrayIndex, 1, :, :, 0] = image
            npImageArray[arrayIndex, 0, :, :, 0] = image #this is done for contingency

            #assign to previous indexes
            npImageArray[arrayIndex - 2, 3, :, :, 0] = image

            # assign to future indexes
            npImageArray[arrayIndex + 2, 1, :, :, 0] = image
            npImageArray[arrayIndex + 4, 0, :, :, 0] = image

        elif sliceNum < 2: #gets slices 1 and 2
            # assign to this index
            npImageArray[arrayIndex, 2, :, :, 0] = image
            npImageArray[arrayIndex, 1, :, :, 0] = image
            npImageArray[arrayIndex, 0, :, :, 0] = image  # this is necessary

            # assign to future indexes
            npImageArray[arrayIndex + 2, 1, :, :, 0] = image
            npImageArray[arrayIndex + 4, 0, :, :, 0] = image
        elif sliceNum > maxSliceNum - 5 and sliceNum < maxSliceNum - 1: #gets slices which are 3rd and 4th from the end
            # assign to this index
            npImageArray[arrayIndex, 2, :, :, 0] = image
            npImageArray[arrayIndex, 3, :, :, 0] = image
            npImageArray[arrayIndex, 4, :, :, 0] = image  # this is done for contingency

            # assign to previous indexes
            npImageArray[arrayIndex - 2, 3, :, :, 0] = image
            npImageArray[arrayIndex - 4, 4, :, :, 0] = image

            # assign to future indexes
            npImageArray[arrayIndex + 2, 1, :, :, 0] = image

        elif sliceNum > maxSliceNum - 3: #gets the end and the one before it
            #assigns to this index
            npImageArray[arrayIndex, 2, :, :, 0] = image
            npImageArray[arrayIndex, 3, :, :, 0] = image
            npImageArray[arrayIndex, 4, :, :, 0] = image #this is needed

            #assigns to prevous indexes
            npImageArray[arrayIndex - 2, 3, :, :, 0] = image
            npImageArray[arrayIndex - 4, 4, :, :, 0] = image

        totalCounter = totalCounter + 1

        if ((augNum%binNum == 0) or (nonAugmentedVersion == True)) and (sliceNum == maxSliceNum):
            if saveArray == True:
                if (nonAugmentedVersion == True):
                    np.save(arrayDirectory + '3DNonAugment' + 'Patient' + patientID + '_' + imageType + '.npy', npImageArray)
                else:
                    np.save(arrayDirectory + '3DAugment' + "%03d" % (augNum-binNum+1) + '-' + "%03d" % (augNum) + 'Patient' + patientID + '_' + imageType + '.npy', npImageArray)
                print('Saved one at augNum ' + str(augNum))
            if returnArray == True:
                return npImageArray
        

def findLargestNumberInFolder(list):
    def findLargestNumber(text):
        li = [0]
        for i in range(len(text)):
            num = ""
            if text[i].isdigit():
                while text[i].isdigit():
                    num = num + text[i]
                    i = i + 1
                li.append(int(num))
        return max(li)
    largestNum = 0
    for i in range(len(list)):
        if (findLargestNumber(list[i]) > largestNum):
            largestNum = findLargestNumber(list[i])
    return largestNum

def getImagePerimeterPoints(inputImage):
    image = Image.fromarray(inputImage)
    image = image.filter(ImageFilter.FIND_EDGES)
    outputImage = np.array(image)
    return outputImage

def getImageBoundingBox(inputImage):
    from scipy import ndimage
    import numpy as np

    image = ndimage.gaussian_filter(inputImage, sigma=1)

    minX = 500
    maxX = 10
    maxY = 10
    minY = 500
    for i in range(image.shape[1]):
        for j in range(image.shape[0]):
            if (image[j,i] > 200):
                if (i < minX):
                    minX = i
                elif (i > maxX):
                    maxX = i
                if (j < minY):
                    minY = j
                elif (j > maxY):
                    maxY = j
    return np.array([minX, maxX, minY, maxY])

def getFolderBoundingBox(filePath):
    import os
    import numpy as np
    from scipy import misc
    cumulativeImage = np.zeros(shape=(512,512), dtype='float32')
    fileList = sorted(os.listdir(filePath))

    for filename in fileList:
        newFile = np.array(misc.imread(filePath + filename, flatten=True))
        cumulativeImage = np.add(cumulativeImage, newFile)

    return getImageBoundingBox(cumulativeImage)

def getFolderCoM(dicomFolder):
    import dicom
    import os
    from scipy import ndimage
    import numpy as np
    import math

    inputImage = np.ndarray([512, 512])
    fileList = sorted(os.listdir(dicomFolder))
    sampleFileList = filter(lambda k: '80' in k, fileList)
    i = 0
    xTotal = 0
    yTotal = 0
    for filename in sampleFileList:
        i = i + 1
        image = dicom.read_file(dicomFolder + filename)
        inputImage[:, :] = image.pixel_array

        # Gets image centre of mass, note y coordinate comes first and then x coordinate
        CoM = ndimage.measurements.center_of_mass(inputImage)
        xTotal = xTotal + CoM[1]
        yTotal = yTotal + CoM[0]

    xAvg = math.floor(xTotal / i)
    yAvg = math.floor(yTotal / i)

    # Sets the limits for a 256x256 bounding box
    xMin = int(xAvg - 128 if xAvg - 128 > 0 else 0)
    xMax = int(xMin + 256)
    yMin = int(yAvg - 128 if yAvg - 128 > 0 else 0)
    yMax = int(yMin + 256)
    return np.array([xMin, xMax, yMin, yMax])


def lukesAugment(image):
    from PIL import Image, ImageStat, ImageOps
    import numpy as np

    def f(x):
            return 135.6*np.tanh((x-150)/70) + 132

    f = np.vectorize(f)  # or use a different name if you want to keep the original f
    image = f(image)


    #image = ImageOps.equalize(image)
    image = Image.fromarray((image))

    return image

import requests
#import json
#import numpy as np
import pandas as pd
import datetime
import warnings

baseURL = "http://environment.data.gov.uk/hydrology"

def getReadingsData(stationID):
        
    readingParams = {"station": stationID, "observedProperty": "waterLevel",
        "mineq-date": "2023-01-01", "period": 86400, "valueType": "max"}
    response = requests.get(baseURL+readingURL, params=readingParams)
    if response.status_code == 200:
        measuresData = pd.json_normalize(response.json()["items"])
    else:
        raise Exception("API error {0}".format(response.status_code))

    return measuresData

def cleanMeasuresData(rawMeasuresData):
        
    dayUIDs = rawMeasuresData.groupby("date").idxmax()["value"]
    dayUIDs = dayUIDs.dropna()
    
    return rawMeasuresData.iloc[dayUIDs,:]

def getLocalMaximums(measuresData, n=5):
    
    measuresData = measuresData.sort_values('date')
    measuresData = measuresData.assign(
        lastValue = lambda df: df.value.shift(1),
        nextValue = lambda df: df.value.shift(-1)
    ).assign(
        localMax = lambda df: (df.value > df.lastValue) & (df.value > df.nextValue)
    )
    maximums = measuresData.query('localMax')
    
    return maximums.nlargest(n, 'value')

def getDataNearTargetDate(stationID, targetDate):

    # stationID = nettlehamID
    # targetDate = dateOfInterest

    targetDate = datetime.datetime.strptime(targetDate, "%Y-%m-%d")

    startDate = targetDate - datetime.timedelta(days=5)
    startDate = datetime.datetime.strftime(startDate, "%Y-%m-%d")
    endDate = targetDate + datetime.timedelta(days=5)
    endDate = datetime.datetime.strftime(endDate, "%Y-%m-%d")

    readingURL = "/data/readings.json"
    readingParams = {"station": stationID, "observedProperty": "waterLevel",
        "mineq-date": startDate, "period": 900, "maxeq-date": endDate} 
    response = requests.get(baseURL+readingURL, params=readingParams)
    if response.status_code == 200:
        levelMeasures = pd.json_normalize(response.json()["items"])
    else:
        raise Exception("API error {0}".format(response.status_code))

    if levelMeasures.shape[0] > 0:
        levelMeasures = levelMeasures.sort_values('dateTime')
    else:
        warnings.warn("No detailed data available around "+targetDate, Warning)

    return levelMeasures

def getDataNearMaximums(maximumObs, stationID):

    dataAroundPeaks = pd.DataFrame()
    for i in range(maximumObs.shape[0]):
        peakLoc = maximumObs.date.iloc[i]
        dataAroundPeak = getDataNearTargetDate(stationID, peakLoc)
        dataAroundPeak = dataAroundPeak.assign(peakDate = peakLoc)
        dataAroundPeak = dataAroundPeak.reset_index()
        dataAroundPeaks = pd.concat([dataAroundPeaks, dataAroundPeak])

    return dataAroundPeaks


readingURL = "/data/readings.json"

if __name__ == "__main__":

    nettlehamID = "a941c6ca-6b2e-45b3-a515-198c39d4ceaa"
    levelMeasures = getReadingsData(nettlehamID)
    measuresUnique = cleanMeasuresData(levelMeasures)

    measuresUnique.plot(x="date", y="value")

    warnings.simplefilter("always")

    peaks = getLocalMaximums(measuresUnique)
    dataNearPeaks = getDataNearMaximums(peaks, nettlehamID)

    valuesAroundPeaks = dataNearPeaks.pivot(columns = 'peakDate', values = 'value')
    valuesAroundPeaks.plot()